import { useEffect, useRef, useState } from 'react';
import { FiDownload, FiSearch, FiUpload, FiUser } from 'react-icons/fi';
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

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export default function LinkedInProfileExtractorPage() {
  const toast = useToast();
  const fileInputRef = useRef(null);
  const pollRef = useRef(null);

  const [mode, setMode] = useState('single');
  const [url, setUrl] = useState('');
  const [extracting, setExtracting] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const [bulkFile, setBulkFile] = useState(null);
  const [bulkJob, setBulkJob] = useState(null);
  const [bulkJobId, setBulkJobId] = useState(null);
  const [bulkProcessing, setBulkProcessing] = useState(false);
  const [bulkDownloading, setBulkDownloading] = useState(false);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

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

  const handleDownloadBulkJob = async (jobId, { silent = false } = {}) => {
    if (!jobId) return;
    setBulkDownloading(true);
    try {
      const { data: blob } = await linkedinProfileService.downloadBulkJob(jobId);
      downloadBlob(blob, `bulk_${jobId}.xlsx`);
      if (!silent) {
        toast.success('Downloaded extracted profiles');
      }
    } catch (err) {
      const message =
        (typeof err.response?.data?.detail === 'string' && err.response.data.detail) ||
        err.message ||
        'Download failed';
      if (!silent) toast.error(message);
    } finally {
      setBulkDownloading(false);
    }
  };

  const pollBulkJob = (jobId) => {
    if (pollRef.current) clearInterval(pollRef.current);

    pollRef.current = setInterval(async () => {
      try {
        const status = await linkedinProfileService.getBulkJob(jobId);
        setBulkJob(status);

        if (status.status === 'done') {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setBulkProcessing(false);
          toast.success(
            `Extraction completed — ${status.success ?? status.completed} succeeded, ${status.failed} failed.`,
          );
        } else if (status.status === 'failed') {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setBulkProcessing(false);
          const message = status.error || 'Bulk extraction failed';
          setError(message);
          if (status.download_ready) {
            toast.warning('Job failed, but partial results are available to download');
          } else {
            toast.error(message);
          }
        }
      } catch (err) {
        clearInterval(pollRef.current);
        pollRef.current = null;
        setBulkProcessing(false);
        const message = err.message || 'Failed to check bulk job status';
        setError(message);
        toast.error(message);
      }
    }, 2500);
  };

  const handleBulkUpload = async () => {
    if (!bulkFile) {
      toast.error('Choose an Excel or CSV file first');
      return;
    }

    setBulkProcessing(true);
    setError('');
    setBulkJob(null);
    setBulkJobId(null);

    try {
      const response = await linkedinProfileService.bulkExtract(bulkFile);
      setBulkJobId(response.job_id);
      setBulkJob({ ...response, status: 'pending', completed: 0, failed: 0, download_ready: false });
      toast.success(`Processing ${response.total} LinkedIn URLs…`);
      pollBulkJob(response.job_id);
    } catch (err) {
      setBulkProcessing(false);
      const message =
        (typeof err.response?.data?.detail === 'string' && err.response.data.detail) ||
        err.message ||
        'Bulk upload failed';
      setError(message);
      toast.error(message);
    }
  };

  const bulkProcessed = bulkJob
    ? (bulkJob.processed ?? ((bulkJob.completed || 0) + (bulkJob.failed || 0)))
    : 0;
  const bulkProgress =
    bulkJob && bulkJob.total ? Math.round((bulkProcessed / bulkJob.total) * 100) : 0;

  return (
    <div className="max-w-3xl mx-auto space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">LeadSense Profile Extractor</h1>
        <p className="text-gray-500 mt-1">
          Extract LinkedIn profile data server-side via Apify — paste one URL or upload a sheet
          with many URLs.
        </p>
      </div>

      <div className="flex gap-2 border-b border-gray-200">
        <button
          type="button"
          onClick={() => setMode('single')}
          className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
            mode === 'single'
              ? 'border-primary-600 text-primary-700'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          Single URL
        </button>
        <button
          type="button"
          onClick={() => setMode('bulk')}
          className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
            mode === 'bulk'
              ? 'border-primary-600 text-primary-700'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          Bulk URL Extraction
        </button>
      </div>

      {mode === 'single' ? (
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
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
          <div>
            <p className="text-sm font-medium text-gray-700">Upload Excel or CSV</p>
            <p className="text-xs text-gray-500 mt-1">
              Include a column named <strong>LinkedIn URL</strong> (or URL / Profile URL) with
              public /in/ profile links. Extraction runs in the background — you can download the
              result when it finishes.
            </p>
          </div>

          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xls,.xlsm,.csv,.tsv,.txt,.ods"
            className="hidden"
            onChange={(e) => setBulkFile(e.target.files?.[0] || null)}
          />

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={bulkProcessing}
              className="btn-secondary flex items-center gap-2"
            >
              <FiUpload size={16} />
              Choose file
            </button>
            {bulkFile ? (
              <span className="text-sm text-gray-600 truncate max-w-xs">{bulkFile.name}</span>
            ) : (
              <span className="text-sm text-gray-400">No file selected</span>
            )}
            <button
              type="button"
              onClick={handleBulkUpload}
              disabled={bulkProcessing || !bulkFile}
              className="btn-primary flex items-center gap-2"
            >
              {bulkProcessing ? (
                <>
                  <LoadingSpinner size="sm" />
                  Processing…
                </>
              ) : (
                <>
                  <FiDownload size={16} />
                  Extract
                </>
              )}
            </button>
          </div>

          {bulkJob && (bulkProcessing || bulkJob.status === 'done' || bulkJob.download_ready) && (
            <div className="space-y-2">
              {bulkJob.status === 'done' && (
                <p className="text-sm font-medium text-green-700">Extraction Completed ✓</p>
              )}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs text-gray-600">
                <span>Total: {bulkJob.total ?? 0}</span>
                <span>Processed: {bulkProcessed}</span>
                <span>Success: {bulkJob.success ?? bulkJob.completed ?? 0}</span>
                <span>Retrying: {bulkJob.retrying ?? 0}</span>
                <span>Final Failed: {bulkJob.failed ?? 0}</span>
              </div>
              <div className="flex justify-between text-xs text-gray-600">
                <span>
                  {bulkProcessed} / {bulkJob.total} processed
                </span>
                <span>{bulkProgress}%</span>
              </div>
              <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
                <div
                  className="h-full bg-primary-600 transition-all duration-300"
                  style={{ width: `${bulkProgress}%` }}
                />
              </div>
              {bulkJob.download_ready && bulkJobId && !bulkProcessing && (
                <button
                  type="button"
                  onClick={() => handleDownloadBulkJob(bulkJobId)}
                  disabled={bulkDownloading}
                  className="btn-secondary flex items-center gap-2 text-sm"
                >
                  {bulkDownloading ? (
                    <>
                      <LoadingSpinner size="sm" />
                      Downloading…
                    </>
                  ) : (
                    <>
                      <FiDownload size={16} />
                      Download Result Excel
                    </>
                  )}
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {error && !(extracting || bulkProcessing) && (
        <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2" role="alert">
          {error}
        </p>
      )}

      {mode === 'single' && result && (
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
