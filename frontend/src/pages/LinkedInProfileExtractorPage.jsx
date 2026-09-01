import { useEffect, useRef, useState } from 'react';
import {
  FiArrowRight,
  FiClipboard,
  FiDownload,
  FiFile,
  FiLayers,
  FiLink,
  FiSearch,
  FiUpload,
  FiUser,
} from 'react-icons/fi';
import { useToast } from '../hooks/useToast';
import { linkedinProfileService } from '../services/services';
import { downloadBlob } from '../utils/helpers';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import GitDiffCompare, { buildDiff } from '../components/bulk/GitDiffCompare';
import ExtractionReviewPanel from '../components/bulk/ExtractionReviewPanel';
import { ExtractorNav, WorkspaceHeader } from '../components/ui/GrowthWorkspace';

const PROFILE_STORE = 'leadsense.linkedin.savedProfiles';

function profileStoreKey(raw) {
  const text = (raw || '').trim().toLowerCase();
  const match = text.match(/linkedin\.com\/in\/([^/?#]+)/);
  return match ? match[1].replace(/\/+$/, '') : text;
}

function loadSavedProfiles() {
  try {
    return JSON.parse(localStorage.getItem(PROFILE_STORE) || '{}');
  } catch {
    return {};
  }
}

function getSavedProfile(rawUrl) {
  if (!rawUrl) return null;
  return loadSavedProfiles()[profileStoreKey(rawUrl)] || null;
}

function saveProfile(rawUrl, data) {
  const all = loadSavedProfiles();
  const key = profileStoreKey(rawUrl || data?.profile_url);
  if (!key) return;
  all[key] = { ...data, saved_at: new Date().toISOString() };
  localStorage.setItem(PROFILE_STORE, JSON.stringify(all));
}

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

const STAGES = [
  { id: 'uploading', label: 'Uploading' },
  { id: 'extracting', label: 'Extracting' },
  { id: 'comparing', label: 'Comparing' },
  { id: 'review', label: 'Review' },
  { id: 'completed', label: 'Completed' },
];

function stageIndex(phase) {
  const idx = STAGES.findIndex((s) => s.id === phase);
  return idx < 0 ? 0 : idx;
}

export default function LinkedInProfileExtractorPage() {
  const toast = useToast();
  const fileInputRef = useRef(null);
  const pollRef = useRef(null);
  const reviewRetryRef = useRef(0);

  const [mode, setMode] = useState('single');
  const [url, setUrl] = useState('');
  const [extracting, setExtracting] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [existingSnapshot, setExistingSnapshot] = useState(null);
  const [awaitingApproval, setAwaitingApproval] = useState(false);

  const [bulkFile, setBulkFile] = useState(null);
  const [bulkJob, setBulkJob] = useState(null);
  const [bulkJobId, setBulkJobId] = useState(null);
  const [bulkProcessing, setBulkProcessing] = useState(false);
  const [bulkDownloading, setBulkDownloading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [reviewItems, setReviewItems] = useState([]);
  const [reviewBusy, setReviewBusy] = useState(false);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  // If the job finished (or has successes) but the board is still empty, retry load.
  useEffect(() => {
    if (!bulkJobId || !bulkJob) return undefined;
    const successCount = bulkJob.success ?? bulkJob.completed ?? 0;
    if (successCount > 0 && reviewItems.length === 0 && reviewRetryRef.current < 5) {
      const timer = setTimeout(() => {
        reviewRetryRef.current += 1;
        refreshReviewItems(bulkJobId);
      }, 400);
      return () => clearTimeout(timer);
    }
    return undefined;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bulkJobId, bulkJob?.success, bulkJob?.completed, bulkJob?.status, reviewItems.length]);

  const refreshReviewItems = async (jobId) => {
    if (!jobId) return;
    try {
      const [allPayload, conflictsPayload] = await Promise.all([
        linkedinProfileService.listBulkJobItems(jobId, { page_size: 500 }),
        linkedinProfileService.getBulkConflicts(jobId, { page_size: 500 }).catch(() => ({ items: [] })),
      ]);
      const conflictMap = new Map(
        (conflictsPayload.items || []).map((row) => [row.item_id, row]),
      );
      const merged = (allPayload.items || []).map((item) => {
        const conflictRow = conflictMap.get(item.item_id);
        return conflictRow ? { ...item, conflicts: conflictRow.conflicts } : item;
      });
      setReviewItems(merged);
      if (merged.length > 0) reviewRetryRef.current = 0;
    } catch {
      // Review refresh is best-effort during polling.
    }
  };

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
    setExistingSnapshot(null);
    setAwaitingApproval(false);

    try {
      const response = await linkedinProfileService.extract(trimmed);
      if (!response.success || !response.data) {
        const message = response.message || 'No data found for this profile';
        setError(message);
        toast.error(message);
        return;
      }
      const data = response.data;
      setResult(data);
      const previous =
        getSavedProfile(trimmed) || getSavedProfile(data.profile_url);
      if (previous) {
        setExistingSnapshot(previous);
        const hasMajor = buildDiff(previous, data).some(
          (row) => row.major && row.status !== 'unchanged' && row.status !== 'empty',
        );
        if (hasMajor) {
          setAwaitingApproval(true);
          toast.warning('Major changes vs existing record — review and approve');
        } else {
          saveProfile(trimmed, data);
          toast.success('Profile extracted');
        }
      } else {
        saveProfile(trimmed, data);
        toast.success('Profile extracted');
      }
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

  const handlePasteUrl = async () => {
    try {
      const text = await navigator.clipboard.readText();
      setUrl(text.trim());
    } catch {
      toast.error('Could not read clipboard');
    }
  };

  const handleDownloadBulkJob = async (jobId, { silent = false } = {}) => {
    if (!jobId) return;
    setBulkDownloading(true);
    try {
      const { blob, filename } = await linkedinProfileService.downloadBulkJob(jobId);
      downloadBlob(blob, filename || `bulk_${jobId}.xlsx`);
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
    await refreshReviewItems(jobId);
  };

  const pollBulkJob = (jobId) => {
    if (pollRef.current) clearInterval(pollRef.current);

    pollRef.current = setInterval(async () => {
      try {
        const status = await linkedinProfileService.getBulkJob(jobId);
        setBulkJob(status);
        // Refresh the review board whenever anything has been processed so
        // extracted rows appear live for the user during the run.
        if ((status.processed || status.success || status.completed || status.failed || 0) > 0) {
          await ingestResults(jobId);
        }

        if (status.status === 'done') {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setBulkProcessing(false);
          await ingestResults(jobId);
          toast.success(
            `Extraction completed — ${status.success ?? status.completed} succeeded, ${status.failed} failed.`,
          );
        } else if (status.status === 'failed') {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setBulkProcessing(false);
          await ingestResults(jobId);
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

  const handleResolveItem = async (item, decisions) => {
    if (!item || !bulkJobId) return;
    setReviewBusy(true);
    try {
      const result = await linkedinProfileService.resolveConflict(bulkJobId, item.item_id, decisions);
      if (result?.icp_synced) {
        toast.success('Resolved and added to ICP Database');
      } else {
        toast.success('Record resolved');
      }
      await refreshReviewItems(bulkJobId);
      const status = await linkedinProfileService.getBulkJob(bulkJobId);
      setBulkJob(status);
      const pending = (status.needs_review || 0) > 0;
      if (!pending) {
        toast.success('All conflicts resolved. You can download a clean Excel.');
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || err.message || 'Resolve failed');
      throw err;
    } finally {
      setReviewBusy(false);
    }
  };

  const acceptBulkFile = (file) => {
    if (!file) return;
    setBulkFile(file);
  };

  const handleBulkDrop = (event) => {
    event.preventDefault();
    setDragOver(false);
    if (bulkProcessing) return;
    acceptBulkFile(event.dataTransfer.files?.[0] || null);
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
    setReviewItems([]);
    setReviewBusy(false);
    reviewRetryRef.current = 0;

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
    <div className="workspace-shell">
      <WorkspaceHeader
        eyebrow="Prospect intelligence"
        title={<>Turn profile links into clean, actionable records.</>}
        description="Extract one public profile or process an entire sheet. LeadSense compares every result, highlights meaningful changes, and keeps your ICP database trustworthy."
      >
        <ExtractorNav />
      </WorkspaceHeader>

      <div className="surface-card min-h-[560px] overflow-hidden flex flex-col animate-rise-in">
        <div className="flex items-center justify-between gap-4 px-6 lg:px-8 pt-4 border-b border-slate-100 bg-slate-50/70">
          <div className="flex gap-6">
          <button
            type="button"
            onClick={() => setMode('single')}
            className={`inline-flex items-center gap-2 pb-3 text-sm font-medium border-b-2 -mb-px transition-colors ${
              mode === 'single'
                ? 'border-primary-600 text-primary-600'
                : 'border-transparent text-gray-400 hover:text-gray-600'
            }`}
          >
            <FiLink size={16} />
            Single profile
          </button>
          <button
            type="button"
            onClick={() => setMode('bulk')}
            className={`inline-flex items-center gap-2 pb-3 text-sm font-medium border-b-2 -mb-px transition-colors ${
              mode === 'bulk'
                ? 'border-primary-600 text-primary-600'
                : 'border-transparent text-gray-400 hover:text-gray-600'
            }`}
          >
            <FiLayers size={16} />
            Bulk URLs
          </button>
          </div>
        </div>

      {mode === 'single' ? (
        <div className="flex-1 flex flex-col p-6 sm:p-8 lg:p-10">
          <div className="max-w-3xl w-full mx-auto flex-1 flex flex-col justify-center space-y-8">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-primary-600">
                New extraction
              </p>
              <label
                className="block mt-1 text-2xl font-semibold text-gray-900"
                htmlFor="linkedin-profile-url"
              >
                Public LinkedIn profile URL
              </label>
              <p className="text-sm text-gray-500 mt-1">
                Paste a public <span className="font-medium text-gray-700">/in/</span> profile. The
                URL is cleaned automatically.
              </p>
            </div>
            <span className="shrink-0 rounded-full bg-gray-100 px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-gray-500">
              One link at a time
            </span>
          </div>

          <div>
            <div className="relative">
              <FiLink className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
              <input
                id="linkedin-profile-url"
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://www.linkedin.com/in/your-name"
                className="w-full rounded-2xl border border-gray-300 bg-white pl-11 pr-28 py-4 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                disabled={extracting}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !extracting) handleExtract();
                }}
              />
              <button
                type="button"
                onClick={handlePasteUrl}
                disabled={extracting}
                className="absolute right-2 top-1/2 -translate-y-1/2 inline-flex items-center gap-1.5 rounded-xl border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
              >
                <FiClipboard size={14} />
                Paste
              </button>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2">
            <p className="text-xs text-gray-500 flex items-center gap-2">
              <FiSearch size={14} className="text-gray-400" />
              Public profiles only — no login required.
            </p>
            <button
              type="button"
              onClick={handleExtract}
              disabled={extracting}
              className="btn-primary inline-flex items-center justify-center gap-2 rounded-2xl px-6 py-2.5"
            >
              {extracting ? (
                <>
                  <LoadingSpinner size="sm" />
                  Extracting…
                </>
              ) : (
                <>
                  <FiUser size={16} />
                  Extract profile
                  <FiArrowRight size={16} />
                </>
              )}
            </button>
          </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 flex flex-col p-6 sm:p-8 lg:p-10">
          <div className="flex-1 flex flex-col max-w-5xl w-full mx-auto space-y-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full bg-primary-50 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-primary-700">
                  New extraction
                </span>
                <span className="rounded-full bg-gray-100 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-gray-500">
                  Sheet upload
                </span>
              </div>
              <p className="mt-3 text-2xl font-semibold text-primary-700">Upload Excel or CSV</p>
              <p className="text-sm text-gray-500 mt-1 max-w-2xl">
                Columns such as Name, LinkedIn URL, Designation, Company, Person Location, and Company Location are detected
                automatically. Original rows are kept in the result file.
              </p>
            </div>
          </div>

          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xls,.xlsm,.csv,.tsv,.txt,.ods"
            className="hidden"
            onChange={(e) => setBulkFile(e.target.files?.[0] || null)}
          />

          <button
            type="button"
            onClick={() => !bulkProcessing && fileInputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              if (!bulkProcessing) setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleBulkDrop}
            disabled={bulkProcessing}
            className={`w-full rounded-2xl border-2 border-dashed px-6 py-10 text-left transition-colors ${
              dragOver
                ? 'border-primary-500 bg-primary-50'
                : bulkFile
                  ? 'border-primary-200 bg-primary-50/40'
                  : 'border-gray-200 bg-gray-50 hover:border-primary-300 hover:bg-white'
            }`}
          >
            <div className="flex flex-col sm:flex-row sm:items-center gap-4">
              <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-white border border-gray-200 text-primary-600">
                {bulkFile ? <FiFile size={22} /> : <FiUpload size={22} />}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-gray-900">
                  {bulkFile ? bulkFile.name : 'Drop your sheet here, or click to browse'}
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  {bulkFile
                    ? `${(bulkFile.size / 1024).toFixed(1)} KB · Excel, CSV, TSV, or ODS`
                    : 'Supports .xlsx, .xls, .csv, .tsv, .txt, and .ods'}
                </p>
              </div>
              <span className="shrink-0 inline-flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700">
                <FiUpload size={16} />
                {bulkFile ? 'Replace file' : 'Choose file'}
              </span>
            </div>
          </button>

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2">
            <p className="text-xs text-gray-500">
              Processing runs in the background — upload, wait, then download.
            </p>
            <button
              type="button"
              onClick={handleBulkUpload}
              disabled={bulkProcessing || !bulkFile}
              className="btn-primary inline-flex items-center justify-center gap-2 rounded-2xl px-6 py-2.5"
            >
              {bulkProcessing ? 'Working…' : (
                <>
                  Start extraction
                  <FiArrowRight size={16} />
                </>
              )}
            </button>
          </div>

          {showBulkProgress && (
            <div className="space-y-5">
              <ol className="grid grid-cols-2 sm:grid-cols-5 gap-2" aria-label="Extraction progress">
                {STAGES.map((stage, idx) => {
                  const done = idx < activeStage || phase === 'completed';
                  const current = stage.id === phase || (phase === 'completed' && idx === 3);
                  return (
                    <li
                      key={stage.id}
                      aria-current={current ? 'step' : undefined}
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
                    <span>Mismatched: {(bulkJob.needs_review || 0) || (bulkJob.mismatched ?? 0)}</span>
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-medium text-gray-800">
                    Review extracted vs uploaded records
                  </p>
                  {reviewItems.length > 0 ? (
                    <p className="text-xs text-gray-500">
                      Showing {reviewItems.filter((i) => (i.extraction_status || '').toUpperCase() === 'SUCCESS').length}{' '}
                      extracted
                      {bulkProcessing ? ' · updating live…' : ''}
                    </p>
                  ) : null}
                </div>
                {(bulkJob.needs_review || 0) > 0 ? (
                  <p className="text-sm text-amber-800">
                    {bulkJob.needs_review} record{bulkJob.needs_review === 1 ? '' : 's'} need
                    resolution — click a row to open the comparison popup.
                  </p>
                ) : null}
                <ExtractionReviewPanel
                  items={reviewItems}
                  busy={reviewBusy}
                  onResolve={handleResolveItem}
                  emptyMessage={
                    bulkProcessing
                      ? 'Extraction in progress — rows will appear here as each profile is extracted…'
                      : (bulkJob.success || bulkJob.completed || 0) > 0
                        ? 'Could not load extracted rows. Refresh the page or re-open this job from History.'
                        : 'Records will appear here as extraction and verification complete.'
                  }
                />
              </div>

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
                    <p>{bulkJob.needs_review ?? bulkJob.mismatched ?? 0} Need review</p>
                    <p>{bulkJob.resolved ?? 0} Conflicts resolved</p>
                  </div>
                  <div className="flex justify-center gap-6 text-xs text-gray-600">
                    <span>Extraction ✓ Completed</span>
                    <span>
                      Verification {(bulkJob.needs_review || 0) > 0 ? '⚠ Needs review' : '✓ Completed'}
                    </span>
                    <span>Excel {bulkJob.download_ready ? '✓ Ready' : '… Generating'}</span>
                  </div>
                  {(() => {
                    const openConflicts = bulkJob.needs_review || 0;
                    return (
                      <div className="flex flex-col items-center gap-3">
                        {openConflicts > 0 && (
                          <p className="text-sm text-amber-800">
                            Resolve {openConflicts} conflict{openConflicts === 1 ? '' : 's'} in the
                            review panel above for a clean download, or export the file as-is.
                          </p>
                        )}
                        <div className="flex flex-wrap justify-center gap-2">
                          <button
                            type="button"
                            onClick={() => handleDownloadBulkJob(bulkJobId)}
                            disabled={
                              bulkDownloading || !bulkJob.download_ready || openConflicts > 0
                            }
                            className="btn-primary inline-flex items-center gap-2"
                          >
                            {bulkDownloading && !openConflicts ? (
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
                          {openConflicts > 0 && (
                            <button
                              type="button"
                              onClick={() => handleDownloadBulkJob(bulkJobId)}
                              disabled={bulkDownloading || !bulkJob.download_ready}
                              className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                            >
                              <FiDownload size={16} />
                              Download with conflicts
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })()}
                </div>
              )}
            </div>
          )}
          </div>
        </div>
      )}
      </div>

      {error && !(extracting || bulkProcessing) && (
        <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2" role="alert">
          {error}
        </p>
      )}

      {mode === 'single' && result && existingSnapshot && (
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 sm:p-8 space-y-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-400">
              Git compare
            </p>
            <h2 className="text-lg font-semibold text-gray-900 mt-1">Existing vs extracted</h2>
            <p className="text-sm text-gray-500 mt-1">
              Red rows are major identity changes. Approve them before they replace the saved
              record.
            </p>
          </div>
          <GitDiffCompare
            existing={existingSnapshot}
            extracted={result}
            requireApproval={awaitingApproval}
            onApprove={
              awaitingApproval
                ? () => {
                    saveProfile(url || result.profile_url, result);
                    setAwaitingApproval(false);
                    toast.success('Major changes approved and saved');
                  }
                : undefined
            }
            onReject={
              awaitingApproval
                ? () => {
                    setResult(existingSnapshot);
                    setAwaitingApproval(false);
                    toast.success('Kept existing record');
                  }
                : undefined
            }
          />
        </div>
      )}

      {mode === 'single' && result && !awaitingApproval && (
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 sm:p-8 space-y-5">
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
