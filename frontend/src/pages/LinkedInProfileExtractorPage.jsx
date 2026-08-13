import { useState } from 'react';
import { FiUser, FiSearch } from 'react-icons/fi';
import { useToast } from '../hooks/useToast';
import { linkedinProfileService } from '../services/services';
import LoadingSpinner from '../components/ui/LoadingSpinner';

function Field({ label, value }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</dt>
      <dd className="mt-1 text-sm text-gray-900 whitespace-pre-wrap">
        {value?.toString().trim() ? value : <span className="text-gray-400">—</span>}
      </dd>
    </div>
  );
}

export default function LinkedInProfileExtractorPage() {
  const toast = useToast();
  const [url, setUrl] = useState('');
  const [extracting, setExtracting] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const handleExtract = async () => {
    const trimmed = url.trim();
    if (!trimmed) {
      toast.error('Paste a LinkedIn profile URL first');
      return;
    }
    if (!trimmed.includes('linkedin.com/in/')) {
      toast.error('URL must be a public LinkedIn /in/ profile link');
      return;
    }

    setExtracting(true);
    setError('');
    setResult(null);

    try {
      const response = await linkedinProfileService.extract(trimmed);
      if (!response.success || !response.data) {
        const message = response.message || 'No data found for this profile';
        setError(message);
        toast.error(message);
        return;
      }
      setResult(response.data);
      toast.success('Profile extracted');
    } catch (err) {
      const message =
        (typeof err.response?.data?.detail === 'string' && err.response.data.detail) ||
        err.message ||
        'Profile extraction failed';
      setError(message);
      toast.error(message);
    } finally {
      setExtracting(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">LeadSense Profile Extractor</h1>
        <p className="text-gray-500 mt-1">
          Paste a public LinkedIn profile URL. Extraction runs server-side via Apify — you never
          provide LinkedIn cookies or passwords.
        </p>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
        <label className="block text-sm font-medium text-gray-700" htmlFor="linkedin-profile-url">
          Public LinkedIn profile URL
        </label>
        <input
          id="linkedin-profile-url"
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://www.linkedin.com/in/username/"
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          disabled={extracting}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !extracting) handleExtract();
          }}
        />

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={handleExtract}
            disabled={extracting}
            className="btn-primary flex items-center gap-2"
          >
            {extracting ? (
              <>
                <LoadingSpinner size="sm" />
                Extracting…
              </>
            ) : (
              <>
                <FiUser size={16} />
                Extract
              </>
            )}
          </button>
          {!extracting && (
            <span className="text-xs text-gray-500 flex items-center gap-1">
              <FiSearch size={12} />
              Apify · supreme_coder/linkedin-profile-scraper
            </span>
          )}
        </div>

        {error && !extracting && (
          <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2" role="alert">
            {error}
          </p>
        )}
      </div>

      {result && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-5">
          <div className="flex flex-wrap items-start gap-4">
            {result.image ? (
              <img
                src={result.image}
                alt={result.name || 'Profile'}
                className="h-20 w-20 rounded-full object-cover border border-gray-200"
              />
            ) : null}
            <div className="flex-1 min-w-0">
              <h2 className="text-lg font-semibold text-gray-900">
                {result.name?.trim() || 'Extracted profile'}
              </h2>
              {result.headline?.trim() ? (
                <p className="text-sm text-gray-600 mt-1">{result.headline}</p>
              ) : null}
              {result.profile_url?.trim() ? (
                <a
                  href={result.profile_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-primary-600 hover:underline mt-1 inline-block"
                >
                  View on LinkedIn
                </a>
              ) : null}
            </div>
          </div>

          <dl className="grid gap-4 sm:grid-cols-2">
            <Field label="Full Name" value={result.name} />
            <Field label="Headline" value={result.headline} />
            <Field label="Current Company" value={result.company} />
            <Field label="Job Title" value={result.job_title} />
            <Field label="Location" value={result.location} />
            <Field label="Followers" value={result.followers} />
            <Field label="Connections" value={result.connections} />
            <div className="sm:col-span-2">
              <Field label="About / Summary" value={result.summary} />
            </div>
          </dl>
        </div>
      )}
    </div>
  );
}
