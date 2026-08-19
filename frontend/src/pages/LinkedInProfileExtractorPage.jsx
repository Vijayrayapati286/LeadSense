import { useEffect, useRef, useState } from 'react';
import { FiCheck, FiDownload, FiSearch, FiUpload, FiUser, FiX } from 'react-icons/fi';
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

const COMPARE_FIELDS = [
  { key: 'name', label: 'Name', matchKey: 'name_match' },
  { key: 'designation', label: 'Designation', matchKey: 'designation_match' },
  { key: 'company', label: 'Company', matchKey: 'company_match' },
  { key: 'location', label: 'Location', matchKey: 'location_match' },
];

const STAGES = [
  { id: 'uploading', label: 'Uploading' },
  { id: 'extracting', label: 'Extracting' },
  { id: 'comparing', label: 'Comparing' },
  { id: 'completed', label: 'Completed' },
];

function stageIndex(phase) {
  const idx = STAGES.findIndex((s) => s.id === phase);
  return idx < 0 ? 0 : idx;
}

function DataCard({ title, icon, values, meet }) {
  return (
    <div
      className={`bg-white rounded-2xl border border-gray-200 shadow-sm p-5 w-full max-w-sm ${
        meet === 'left' ? 'animate-meet-left' : meet === 'right' ? 'animate-meet-right' : ''
      }`}
    >
      <p className="text-sm font-semibold text-gray-800 mb-4">
        {icon} {title}
      </p>
      <dl className="space-y-3">
        {COMPARE_FIELDS.map((field) => (
          <div key={field.key}>
            <dt className="text-[11px] uppercase tracking-wide text-gray-400">{field.label}</dt>
            <dd className="text-sm text-gray-900 mt-0.5">{values?.[field.key] || '—'}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function ComparisonPanel({ item, animKey }) {
  const [visibleFields, setVisibleFields] = useState(0);
  const [showSummary, setShowSummary] = useState(false);
  const compared = COMPARE_FIELDS.filter((f) => item[f.matchKey] !== null && item[f.matchKey] !== undefined);
  const matched = compared.filter((f) => item[f.matchKey] === true).length;

  useEffect(() => {
    setVisibleFields(0);
    setShowSummary(false);
    const timers = COMPARE_FIELDS.map((_, i) =>
      setTimeout(() => setVisibleFields(i + 1), 800 + i * 380),
    );
    const summaryTimer = setTimeout(() => setShowSummary(true), 800 + COMPARE_FIELDS.length * 380 + 200);
    return () => {
      timers.forEach(clearTimeout);
      clearTimeout(summaryTimer);
    };
  }, [animKey, item?.item_id]);

  const status = item.verification_status || 'NOT_VERIFIED';
  const isMatch = status === 'VERIFIED';

  return (
    <div key={animKey} className="space-y-5">
      <div className="flex flex-col lg:flex-row items-stretch justify-center gap-4 lg:gap-8">
        <DataCard title="Uploaded Data" icon="📄" values={item.uploaded} meet="left" />
        <div className="flex flex-col items-center justify-center min-w-[88px]">
          <div className="text-primary-500 font-semibold text-lg animate-scan-pulse">↔</div>
          <p className="text-xs text-gray-500 mt-1 animate-scan-pulse">Comparing…</p>
          <div className="mt-3 h-16 w-px bg-gradient-to-b from-transparent via-primary-400 to-transparent animate-scan-pulse" />
        </div>
        <DataCard title="Extracted Data" icon="🔍" values={item.extracted} meet="right" />
      </div>

      <div className="bg-gray-50 rounded-xl border border-gray-100 p-4 space-y-2">
        {COMPARE_FIELDS.slice(0, visibleFields).map((field) => {
          const match = item[field.matchKey];
          const skipped = match === null || match === undefined;
          return (
            <div
              key={field.key}
              className={`flex flex-wrap items-center justify-between gap-2 text-sm rounded-lg px-3 py-2 animate-field-in ${
                match === false ? 'bg-amber-50' : 'bg-white'
              }`}
            >
              <span className="font-medium text-gray-700 w-28">{field.label}</span>
              <span className="text-gray-500 flex-1 min-w-[140px]">
                {item.uploaded?.[field.key] || '—'} → {item.extracted?.[field.key] || '—'}
              </span>
              {skipped ? (
                <span className="text-xs text-gray-400">skipped</span>
              ) : match ? (
                <span className="text-green-600 font-medium flex items-center gap-1">
                  <FiCheck /> MATCH
                </span>
              ) : (
                <span className="text-red-600 font-medium flex items-center gap-1">
                  <FiX /> MISMATCH
                </span>
              )}
            </div>
          );
        })}
      </div>

      {showSummary && (
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <p className="font-semibold text-gray-900">Verification Complete</p>
          <p className="text-sm text-gray-600 mt-1">
            Match Score: {item.verification_score ?? 0}% · {matched} / {compared.length || 0} fields
            matched
          </p>
          <p className={`mt-2 text-sm font-medium ${isMatch ? 'text-green-700' : 'text-amber-700'}`}>
            {isMatch ? '✓ MATCH' : `⚠ ${status}`}
          </p>
        </div>
      )}
    </div>
  );
}

export default function LinkedInProfileExtractorPage() {
  const toast = useToast();
  const fileInputRef = useRef(null);
  const pollRef = useRef(null);
  const seenCompareRef = useRef(new Set());
  const compareTimerRef = useRef(null);

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
  const [compareItem, setCompareItem] = useState(null);
  const [compareAnimKey, setCompareAnimKey] = useState(0);
  const [compareQueue, setCompareQueue] = useState([]);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (compareTimerRef.current) clearTimeout(compareTimerRef.current);
    };
  }, []);

  useEffect(() => {
    if (compareItem) return undefined;
    if (compareQueue.length === 0) return undefined;
    const next = compareQueue[0];
    setCompareQueue((q) => q.slice(1));
    setCompareItem(next);
    setCompareAnimKey((k) => k + 1);
    return undefined;
  }, [compareQueue, compareItem]);

  useEffect(() => {
    if (!compareItem) return undefined;
    const timer = setTimeout(() => setCompareItem(null), 2800);
    return () => clearTimeout(timer);
  }, [compareItem]);

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

  const ingestResults = async (jobId) => {
    try {
      const payload = await linkedinProfileService.getBulkJobResults(jobId, 20);
      const fresh = (payload.items || []).filter((row) => !seenCompareRef.current.has(row.item_id));
      if (!fresh.length) return;
      fresh.forEach((row) => seenCompareRef.current.add(row.item_id));
      setCompareQueue((q) => [...q, ...fresh.reverse()]);
    } catch {
      /* status poll still drives progress */
    }
  };

  const pollBulkJob = (jobId) => {
    if (pollRef.current) clearInterval(pollRef.current);

    pollRef.current = setInterval(async () => {
      try {
        const status = await linkedinProfileService.getBulkJob(jobId);
        setBulkJob(status);
        if ((status.success || status.completed || 0) > 0) {
          ingestResults(jobId);
        }

        if (status.status === 'done') {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setBulkProcessing(false);
          ingestResults(jobId);
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
            toast.warning('Job failed, but results are available to download');
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
    }, 1500);
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
    setCompareItem(null);
    setCompareQueue([]);
    seenCompareRef.current = new Set();

    try {
      const response = await linkedinProfileService.bulkExtract(bulkFile);
      setBulkJobId(response.job_id);
      setBulkJob({
        ...response,
        status: 'pending',
        phase: 'uploading',
        completed: 0,
        failed: 0,
        download_ready: false,
      });
      toast.success(`Processing ${response.total} rows in the background`);
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
    ? bulkJob.processed ?? (bulkJob.completed || 0) + (bulkJob.failed || 0)
    : 0;
  const bulkProgress =
    bulkJob && bulkJob.total ? Math.round((bulkProcessed / bulkJob.total) * 100) : 0;
  const phase = bulkJob?.phase || (bulkProcessing ? 'uploading' : 'uploading');
  const activeStage = stageIndex(phase);
  const showBulkProgress = bulkJob && (bulkProcessing || ['done', 'failed'].includes(bulkJob.status));

  return (
    <div className="max-w-5xl mx-auto space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">LeadSense Profile Extractor</h1>
        <p className="text-gray-500 mt-1">
          Paste a public LinkedIn profile URL, or upload a sheet. Processing runs in the background
          — you only need to upload and download.
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
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-5">
          <div>
            <p className="text-sm font-medium text-gray-700">Upload Excel or CSV</p>
            <p className="text-xs text-gray-500 mt-1">
              Columns such as Name, LinkedIn URL, Designation, Company, and Location are detected
              automatically. Original rows are kept in the result file.
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
              {bulkProcessing ? 'Working…' : 'Start extraction'}
            </button>
          </div>

          {showBulkProgress && (
            <div className="space-y-5">
              <ol className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {STAGES.map((stage, idx) => {
                  const done = idx < activeStage || phase === 'completed';
                  const current = stage.id === phase || (phase === 'completed' && idx === 3);
                  return (
                    <li
                      key={stage.id}
                      className={`rounded-xl px-3 py-2 text-center text-xs font-medium border ${
                        current
                          ? 'border-primary-500 bg-primary-50 text-primary-800'
                          : done
                            ? 'border-green-200 bg-green-50 text-green-800'
                            : 'border-gray-100 bg-gray-50 text-gray-400'
                      }`}
                    >
                      {done && !current ? '✓ ' : ''}
                      {stage.label}
                    </li>
                  );
                })}
              </ol>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="rounded-xl border border-gray-100 p-4">
                  <p className="text-xs uppercase tracking-wide text-gray-400">Extraction</p>
                  <p className="text-lg font-semibold text-gray-900 mt-1">
                    {bulkProcessed} / {bulkJob.total ?? 0}
                  </p>
                  <div className="mt-2 h-2 rounded-full bg-gray-100 overflow-hidden">
                    <div
                      className="h-full bg-primary-600 transition-all duration-500"
                      style={{ width: `${bulkProgress}%` }}
                    />
                  </div>
                  <div className="mt-3 grid grid-cols-3 gap-2 text-xs text-gray-600">
                    <span>Success: {bulkJob.success ?? bulkJob.completed ?? 0}</span>
                    <span>Retrying: {bulkJob.retrying ?? 0}</span>
                    <span>Failed: {bulkJob.failed ?? 0}</span>
                  </div>
                </div>
                <div className="rounded-xl border border-gray-100 p-4">
                  <p className="text-xs uppercase tracking-wide text-gray-400">Verification</p>
                  <p className="text-lg font-semibold text-gray-900 mt-1">
                    {(bulkJob.verified || 0) + (bulkJob.mismatched || 0) + (bulkJob.review || 0)} /{' '}
                    {bulkJob.total ?? 0} compared
                  </p>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-gray-600">
                    <span>Matched: {bulkJob.verified ?? 0}</span>
                    <span>Mismatched: {bulkJob.mismatched ?? 0}</span>
                  </div>
                </div>
              </div>

              {compareItem && bulkJob.status !== 'done' && (
                <ComparisonPanel item={compareItem} animKey={compareAnimKey} />
              )}

              {(bulkJob.status === 'done' || bulkJob.status === 'failed') && (
                <div
                  className={`rounded-2xl border p-8 text-center space-y-4 ${
                    (bulkJob.success || bulkJob.completed || 0) > 0
                      ? 'border-green-100 bg-green-50/60'
                      : 'border-amber-200 bg-amber-50/70'
                  }`}
                >
                  <p
                    className={`text-xl font-semibold ${
                      (bulkJob.success || bulkJob.completed || 0) > 0
                        ? 'text-green-800'
                        : 'text-amber-900'
                    }`}
                  >
                    {(bulkJob.success || bulkJob.completed || 0) > 0
                      ? '✓ Extraction Complete'
                      : 'Extraction finished with errors'}
                  </p>
                  {bulkJob.error ? (
                    <p className="text-sm text-red-700 bg-white/80 rounded-lg px-3 py-2">{bulkJob.error}</p>
                  ) : null}
                  <p className="text-gray-700">{bulkJob.total ?? 0} URLs processed</p>
                  <div className="text-sm text-gray-700 space-y-1">
                    <p>{bulkJob.success ?? bulkJob.completed ?? 0} Successful</p>
                    <p>{bulkJob.failed ?? 0} Failed</p>
                    <p>{bulkJob.verified ?? 0} Verified</p>
                    <p>{bulkJob.mismatched ?? 0} Mismatch</p>
                  </div>
                  <div className="flex justify-center gap-6 text-xs text-gray-600">
                    <span>Extraction ✓ Completed</span>
                    <span>Verification ✓ Completed</span>
                    <span>Excel {bulkJob.download_ready ? '✓ Ready' : '… Generating'}</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleDownloadBulkJob(bulkJobId)}
                    disabled={bulkDownloading || !bulkJob.download_ready}
                    className="btn-primary inline-flex items-center gap-2"
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
                </div>
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
