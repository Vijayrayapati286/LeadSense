import { useState } from 'react';
import { FiSearch, FiDownload, FiUser } from 'react-icons/fi';
import { useToast } from '../hooks/useToast';
import { salesNavService } from '../services/services';
import LoadingSpinner from '../components/ui/LoadingSpinner';

function triggerBlobDownload(blob, filename) {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
}

function filenameFromDisposition(header, fallback = 'salesnav_contacts.xlsx') {
  if (!header) return fallback;
  const match = /filename\*?=(?:UTF-8''|")?([^\";]+)/i.exec(header);
  if (!match) return fallback;
  try {
    return decodeURIComponent(match[1].replace(/"/g, '').trim());
  } catch {
    return match[1].replace(/"/g, '').trim() || fallback;
  }
}

async function errorMessageFromAxios(err, fallback = 'Extraction failed') {
  let message = fallback;
  const data = err.response?.data;
  if (data instanceof Blob) {
    try {
      const text = await data.text();
      const parsed = JSON.parse(text);
      message = parsed.detail || message;
    } catch {
      /* keep default */
    }
  } else if (typeof data?.detail === 'string') {
    message = data.detail;
  } else if (err.message) {
    message = err.message;
  }
  return message;
}

export default function SalesNavExtractPage() {
  const toast = useToast();
  const [mode, setMode] = useState('search'); // 'search' | 'profile'
  const [searchUrl, setSearchUrl] = useState('');
  const [profileUrl, setProfileUrl] = useState('');
  const [extracting, setExtracting] = useState(false);

  const handleExtractSearch = async () => {
    const url = searchUrl.trim();
    if (!url) {
      toast.error('Paste a Sales Navigator search URL first');
      return;
    }
    if (!url.includes('linkedin.com/sales')) {
      toast.error('URL must be a LinkedIn Sales Navigator link');
      return;
    }

    setExtracting(true);
    try {
      const response = await salesNavService.extract(url);
      const filename = filenameFromDisposition(response.headers['content-disposition']);
      triggerBlobDownload(response.data, filename);
      toast.success('Excel downloaded');
    } catch (err) {
      toast.error(await errorMessageFromAxios(err));
    } finally {
      setExtracting(false);
    }
  };

  const handleExtractProfile = async () => {
    const url = profileUrl.trim();
    if (!url) {
      toast.error('Paste a LinkedIn profile URL first');
      return;
    }
    if (!url.includes('linkedin.com/')) {
      toast.error('URL must be a LinkedIn profile link');
      return;
    }

    setExtracting(true);
    try {
      const response = await salesNavService.extractProfile(url);
      const filename = filenameFromDisposition(
        response.headers['content-disposition'],
        'salesnav_profile.xlsx',
      );
      triggerBlobDownload(response.data, filename);
      toast.success('Profile Excel downloaded');
    } catch (err) {
      toast.error(await errorMessageFromAxios(err, 'Profile extraction failed'));
    } finally {
      setExtracting(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Sales Navigator Extractor</h1>
        <p className="text-gray-500 mt-1">
          Extract Name, About, and Company. Missing fields are null.
        </p>
      </div>

      <div className="flex gap-2">
        <button
          type="button"
          disabled={extracting}
          onClick={() => setMode('search')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            mode === 'search'
              ? 'bg-primary-600 text-white'
              : 'bg-white border border-gray-200 text-gray-700 hover:bg-gray-50'
          }`}
        >
          Search extract
        </button>
        <button
          type="button"
          disabled={extracting}
          onClick={() => setMode('profile')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            mode === 'profile'
              ? 'bg-primary-600 text-white'
              : 'bg-white border border-gray-200 text-gray-700 hover:bg-gray-50'
          }`}
        >
          Profile test
        </button>
      </div>

      {mode === 'search' ? (
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
          <label className="block text-sm font-medium text-gray-700" htmlFor="salesnav-url">
            Sales Navigator search URL
          </label>
          <textarea
            id="salesnav-url"
            rows={4}
            value={searchUrl}
            onChange={(e) => setSearchUrl(e.target.value)}
            placeholder="https://www.linkedin.com/sales/search/people?..."
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            disabled={extracting}
          />

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handleExtractSearch}
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
                  <FiDownload size={16} />
                  Extract Contacts
                </>
              )}
            </button>
            {!extracting && (
              <span className="text-xs text-gray-500 flex items-center gap-1">
                <FiSearch size={12} />
                Apify · usually 2–5 minutes for large result sets
              </span>
            )}
          </div>

          {extracting && (
            <p className="text-sm text-gray-600 bg-gray-50 rounded-lg px-3 py-2">
              Checking your LinkedIn session, then extracting contacts via Apify. Keep this tab open until the download starts.
            </p>
          )}

          <div className="text-sm text-gray-500 space-y-1 pt-2">
            <p>1. Apply filters in Sales Navigator and run search.</p>
            <p>2. Copy the browser URL and paste it above.</p>
            <p>3. Click Extract Contacts.</p>
          </div>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
          <label className="block text-sm font-medium text-gray-700" htmlFor="profile-url">
            Profile URL (test)
          </label>
          <textarea
            id="profile-url"
            rows={3}
            value={profileUrl}
            onChange={(e) => setProfileUrl(e.target.value)}
            placeholder="https://www.linkedin.com/in/... or https://www.linkedin.com/sales/lead/..."
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            disabled={extracting}
          />

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handleExtractProfile}
              disabled={extracting}
              className="btn-primary flex items-center gap-2"
            >
              {extracting ? (
                <>
                  <LoadingSpinner size="sm" />
                  Testing…
                </>
              ) : (
                <>
                  <FiUser size={16} />
                  Extract Profile
                </>
              )}
            </button>
            {!extracting && (
              <span className="text-xs text-gray-500 flex items-center gap-1">
                <FiSearch size={12} />
                Playwright · usually under 30 seconds
              </span>
            )}
          </div>

          {extracting && (
            <p className="text-sm text-gray-600 bg-gray-50 rounded-lg px-3 py-2">
              Opening the profile with your LinkedIn session and reading Name, About, and Company.
            </p>
          )}

          <div className="text-sm text-gray-500 space-y-1 pt-2">
            <p>Paste any one profile URL to verify cookie + extraction quickly.</p>
            <p>Accepted: /in/..., /sales/lead/..., /sales/people/...</p>
            <p>Returns a 1-row Excel with Name, About, Company (null if missing).</p>
          </div>
        </div>
      )}
    </div>
  );
}
