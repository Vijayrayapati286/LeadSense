import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  FiAlertCircle,
  FiCheckCircle,
  FiClock,
  FiDownload,
  FiLayers,
  FiPlus,
  FiRefreshCw,
  FiSearch,
  FiX,
  FiXCircle,
} from 'react-icons/fi';
import HistoryJobCard from '../components/bulk/HistoryJobCard';
import Pagination from '../components/ui/Pagination';
import {
  EmptyState,
  LoadingAnnouncement,
  MetricCard,
  SkeletonCards,
  WorkspaceHeader,
} from '../components/ui/GrowthWorkspace';
import { useToast } from '../hooks/useToast';
import { linkedinProfileService } from '../services/services';
import { downloadBlob } from '../utils/helpers';

const PAGE_SIZE = 20;
const RECENTS_PAGE_SIZE = 50;

const FILTERS = [
  { key: 'all', label: 'All', params: {}, dot: 'bg-slate-400', idle: 'text-slate-500 hover:bg-white hover:text-slate-900', active: 'bg-white text-slate-900 shadow-sm ring-1 ring-slate-200' },
  { key: 'completed', label: 'Completed', params: { status: 'done', needs_review: false }, dot: 'bg-emerald-500', idle: 'text-slate-500 hover:bg-emerald-50 hover:text-emerald-700', active: 'bg-white text-emerald-700 shadow-sm ring-1 ring-emerald-200' },
  { key: 'processing', label: 'Processing', params: { status: 'pending,running' }, dot: 'bg-primary-500', idle: 'text-slate-500 hover:bg-primary-50 hover:text-primary-700', active: 'bg-white text-primary-700 shadow-sm ring-1 ring-primary-200' },
  { key: 'needs_review', label: 'Needs review', params: { needs_review: true }, dot: 'bg-amber-400', idle: 'text-slate-500 hover:bg-amber-50 hover:text-amber-700', active: 'bg-white text-amber-700 shadow-sm ring-1 ring-amber-200' },
  { key: 'failed', label: 'Failed', params: { status: 'failed' }, dot: 'bg-rose-500', idle: 'text-slate-500 hover:bg-rose-50 hover:text-rose-700', active: 'bg-white text-rose-700 shadow-sm ring-1 ring-rose-200' },
  {
    key: 'recents',
    label: 'Recents',
    params: { status: 'done', needs_review: false },
    dot: 'bg-sky-500',
    idle: 'text-slate-500 hover:bg-sky-50 hover:text-sky-700',
    active: 'bg-white text-sky-700 shadow-sm ring-1 ring-sky-200',
  },
];

function filterFor(key) {
  return FILTERS.find((f) => f.key === key) || FILTERS[0];
}

function jobDate(job) {
  const raw = job.completed_at || job.updated_at || job.created_at;
  return raw ? new Date(raw).getTime() : 0;
}

function jobDateKey(job) {
  const raw = job.completed_at || job.updated_at || job.created_at;
  if (!raw) return '';
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return '';
  return d.toISOString().slice(0, 10);
}

export default function BulkHistoryPage() {
  const toast = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const filterKey = searchParams.get('filter') || 'all';
  const appliedQ = searchParams.get('q') || '';
  const isRecents = filterKey === 'recents';

  const [draftQ, setDraftQ] = useState(appliedQ);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({ total: 0, items: [], page: 1 });
  const [counts, setCounts] = useState({ all: 0, completed: 0, needs_review: 0, failed: 0, recents: 0 });
  const [downloadingId, setDownloadingId] = useState(null);
  const [addingId, setAddingId] = useState(null);
  const [downloadingAll, setDownloadingAll] = useState(false);
  const [sortOrder, setSortOrder] = useState('newest'); // newest | oldest
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  useEffect(() => {
    setDraftQ(appliedQ);
  }, [appliedQ]);

  const applyParams = useCallback(
    (nextFilter, nextQ) => {
      const next = {};
      if (nextFilter && nextFilter !== 'all') next.filter = nextFilter;
      if (nextQ?.trim()) next.q = nextQ.trim();
      setSearchParams(next);
      setPage(1);
    },
    [setSearchParams],
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const payload = await linkedinProfileService.listBulkJobs({
        q: appliedQ || undefined,
        page: isRecents ? 1 : page,
        page_size: isRecents ? RECENTS_PAGE_SIZE : PAGE_SIZE,
        ...filterFor(filterKey).params,
      });
      setData(payload);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to load history');
    } finally {
      setLoading(false);
    }
  }, [appliedQ, filterKey, isRecents, page, toast]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleAddToIcp(job) {
    if (!job?.job_id || addingId || downloadingId || downloadingAll) return;
    setAddingId(job.job_id);
    try {
      const result = await linkedinProfileService.addBulkJobToIcp(job.job_id);
      toast.success(
        `Added to ICP: ${result?.added ?? 0} new, ${result?.updated ?? 0} updated (${result?.eligible ?? 0} verified)`,
      );
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Could not add profiles to ICP');
    } finally {
      setAddingId(null);
    }
  }

  async function handleDownload(job) {
    if (!job?.job_id || downloadingId || downloadingAll) return;
    setDownloadingId(job.job_id);
    try {
      const { blob, filename } = await linkedinProfileService.downloadBulkJob(job.job_id);
      downloadBlob(blob, filename || `bulk_${job.job_id}.xlsx`);
      toast.success('Verified sheet downloaded');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Excel not ready');
    } finally {
      setDownloadingId(null);
    }
  }

  const displayItems = useMemo(() => {
    let items = [...(data.items || [])];
    if (isRecents) {
      items = items.filter((job) => job.download_ready);
      if (dateFrom) {
        items = items.filter((job) => jobDateKey(job) >= dateFrom);
      }
      if (dateTo) {
        items = items.filter((job) => jobDateKey(job) <= dateTo);
      }
      items.sort((a, b) => {
        const diff = jobDate(a) - jobDate(b);
        return sortOrder === 'oldest' ? diff : -diff;
      });
    }
    return items;
  }, [data.items, dateFrom, dateTo, isRecents, sortOrder]);

  async function handleDownloadAll() {
    const ready = displayItems.filter((job) => job.download_ready);
    if (!ready.length || downloadingAll || downloadingId) return;
    setDownloadingAll(true);
    let ok = 0;
    let failed = 0;
    try {
      for (const job of ready) {
        try {
          setDownloadingId(job.job_id);
          const { blob, filename } = await linkedinProfileService.downloadBulkJob(job.job_id);
          downloadBlob(blob, filename || `bulk_${job.job_id}.xlsx`);
          ok += 1;
          // Brief pause so browsers don't block multiple downloads.
          await new Promise((r) => setTimeout(r, 400));
        } catch {
          failed += 1;
        }
      }
      if (ok && !failed) toast.success(`Downloaded ${ok} sheet${ok === 1 ? '' : 's'}`);
      else if (ok) toast.success(`Downloaded ${ok}; ${failed} failed`);
      else toast.error('Could not download sheets');
    } finally {
      setDownloadingId(null);
      setDownloadingAll(false);
    }
  }

  // Bucket totals come from the API rather than the current page, so the
  // headline numbers stay true once history spans more than one page.
  useEffect(() => {
    let cancelled = false;
    const countOnly = { q: appliedQ || undefined, page: 1, page_size: 1 };
    Promise.all([
      ...['all', 'completed', 'needs_review', 'failed'].map((key) =>
        linkedinProfileService
          .listBulkJobs({ ...countOnly, ...filterFor(key).params })
          .then((r) => r.total || 0)
          .catch(() => 0),
      ),
      linkedinProfileService
        .listBulkJobs({ ...countOnly, status: 'done', needs_review: false, page_size: RECENTS_PAGE_SIZE })
        .then((r) => (r.items || []).filter((j) => j.download_ready).length)
        .catch(() => 0),
    ]).then(([all, completed, needs_review, failed, recents]) => {
      if (!cancelled) setCounts({ all, completed, needs_review, failed, recents });
    });
    return () => {
      cancelled = true;
    };
  }, [appliedQ]);

  const items = isRecents ? displayItems : data.items || [];
  const total = isRecents ? displayItems.length : data.total || 0;
  const rangeStart = total === 0 ? 0 : isRecents ? 1 : (page - 1) * PAGE_SIZE + 1;
  const rangeEnd = isRecents ? total : Math.min(page * PAGE_SIZE, total);

  function renderEmpty() {
    if (appliedQ) {
      return (
        <EmptyState
          title={`No jobs match “${appliedQ}”`}
          description="Search looks at file names and job IDs. Try a shorter term or clear the search."
          icon={FiSearch}
          action={
            <button type="button" onClick={() => applyParams(filterKey, '')} className="btn-secondary">
              Clear search
            </button>
          }
        />
      );
    }
    if (isRecents) {
      return (
        <EmptyState
          title="No recent verified sheets"
          description="Completed extractions with a downloadable Excel will show up here. Adjust the date filter or finish a run first."
          icon={FiClock}
          action={
            <button type="button" onClick={() => applyParams('all', '')} className="btn-secondary">
              View all jobs
            </button>
          }
        />
      );
    }
    if (filterKey !== 'all') {
      return (
        <EmptyState
          title={`No ${filterFor(filterKey).label.toLowerCase()} jobs`}
          description="Nothing sits in this bucket right now."
          icon={FiLayers}
          action={
            <button type="button" onClick={() => applyParams('all', '')} className="btn-secondary">
              View all jobs
            </button>
          }
        />
      );
    }
    return (
      <EmptyState
        title="No extractions yet"
        description="Upload a spreadsheet of LinkedIn profiles and every run will be tracked here from processing to verified output."
        icon={FiPlus}
        action={
          <Link to="/linkedin-extractor" className="btn-primary inline-flex">
            Start an extraction
          </Link>
        }
      />
    );
  }

  return (
    <div className="workspace-shell">
      <WorkspaceHeader
        eyebrow="Profile intelligence"
        title="Extraction history"
        description="Track every uploaded sheet from processing to verified output. Reopen a job, resolve exceptions, or download a clean result."
        actions={
          <Link to="/linkedin-extractor" className="btn-primary inline-flex items-center gap-2">
            <FiPlus size={16} /> New extraction
          </Link>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="All jobs"
          value={counts.all}
          hint="Across every status"
          tone="gold"
          icon={FiLayers}
          onClick={() => applyParams('all', appliedQ)}
          active={filterKey === 'all'}
        />
        <MetricCard
          label="Completed"
          value={counts.completed}
          hint="Clean and ready"
          tone="green"
          icon={FiCheckCircle}
          onClick={() => applyParams('completed', appliedQ)}
          active={filterKey === 'completed'}
        />
        <MetricCard
          label="Needs review"
          value={counts.needs_review}
          hint="Waiting on a decision"
          tone="sky"
          icon={FiAlertCircle}
          onClick={() => applyParams('needs_review', appliedQ)}
          active={filterKey === 'needs_review'}
        />
        <MetricCard
          label="Failed"
          value={counts.failed}
          hint="Could not complete"
          tone="red"
          icon={FiXCircle}
          onClick={() => applyParams('failed', appliedQ)}
          active={filterKey === 'failed'}
        />
      </div>

      <section className="surface-card overflow-hidden">
        <div className="flex flex-col gap-4 border-b border-slate-100 p-4 sm:p-5">
          <div className="flex max-w-full gap-1 overflow-x-auto rounded-xl bg-slate-100 p-1">
            {FILTERS.map((f) => (
              <button
                key={f.key}
                type="button"
                onClick={() => applyParams(f.key, appliedQ)}
                aria-pressed={filterKey === f.key}
                className={`filter-chip ${filterKey === f.key ? f.active : f.idle}`}
              >
                <span
                  className={`h-1.5 w-1.5 rounded-full transition-transform duration-200 ${f.dot} ${
                    filterKey === f.key ? 'scale-125' : 'opacity-60'
                  }`}
                  aria-hidden="true"
                />
                {f.label}
              </button>
            ))}
          </div>

          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              applyParams(filterKey, draftQ);
            }}
          >
            <div className="relative flex-1">
              <FiSearch className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                value={draftQ}
                onChange={(e) => setDraftQ(e.target.value)}
                placeholder="Search by file name or job ID"
                aria-label="Search extraction history"
                className="control pl-10 pr-10"
              />
              {draftQ ? (
                <button
                  type="button"
                  onClick={() => {
                    setDraftQ('');
                    applyParams(filterKey, '');
                  }}
                  aria-label="Clear search"
                  className="absolute right-3 top-1/2 -translate-y-1/2 rounded-full p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                >
                  <FiX size={14} />
                </button>
              ) : null}
            </div>
            <button type="submit" className="btn-primary">
              Search
            </button>
            <button type="button" onClick={load} className="icon-btn" aria-label="Refresh history">
              <FiRefreshCw size={16} />
            </button>
          </form>

          {isRecents ? (
            <div className="flex flex-col gap-3 rounded-xl border border-sky-100 bg-sky-50/60 p-3 sm:flex-row sm:flex-wrap sm:items-end sm:justify-between">
              <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-end">
                <label className="block text-xs font-medium text-slate-600">
                  Sort by date
                  <select
                    value={sortOrder}
                    onChange={(e) => setSortOrder(e.target.value)}
                    className="control mt-1 min-w-[9rem] bg-white"
                  >
                    <option value="newest">Newest first</option>
                    <option value="oldest">Oldest first</option>
                  </select>
                </label>
                <label className="block text-xs font-medium text-slate-600">
                  From
                  <input
                    type="date"
                    value={dateFrom}
                    onChange={(e) => setDateFrom(e.target.value)}
                    className="control mt-1 bg-white"
                  />
                </label>
                <label className="block text-xs font-medium text-slate-600">
                  To
                  <input
                    type="date"
                    value={dateTo}
                    onChange={(e) => setDateTo(e.target.value)}
                    className="control mt-1 bg-white"
                  />
                </label>
                {(dateFrom || dateTo) ? (
                  <button
                    type="button"
                    onClick={() => {
                      setDateFrom('');
                      setDateTo('');
                    }}
                    className="btn-secondary text-xs"
                  >
                    Clear dates
                  </button>
                ) : null}
              </div>
              <button
                type="button"
                onClick={handleDownloadAll}
                disabled={!displayItems.length || downloadingAll || !!downloadingId}
                className="btn-primary inline-flex items-center gap-2 self-start sm:self-auto"
              >
                <FiDownload size={14} />
                {downloadingAll ? 'Downloading…' : `Download all (${displayItems.length})`}
              </button>
            </div>
          ) : null}

          {!loading && total > 0 ? (
            <p className="text-xs text-slate-500">
              Showing <span className="font-semibold text-slate-700">{rangeStart}–{rangeEnd}</span> of {total}{' '}
              {isRecents ? 'sheet' : 'job'}
              {total === 1 ? '' : 's'}
              {appliedQ ? <> matching “{appliedQ}”</> : null}
            </p>
          ) : null}
        </div>

        <div className="p-4 sm:p-5">
          {loading ? (
            <>
              <LoadingAnnouncement label="Loading extraction history" />
              <SkeletonCards count={4} />
            </>
          ) : items.length ? (
            <div className="space-y-2">
              {items.map((job, index) => (
                <div key={job.job_id} className="stagger-item" style={{ '--item-index': index }}>
                  <HistoryJobCard
                    job={job}
                    onDownload={isRecents ? undefined : handleDownload}
                    downloading={downloadingId === job.job_id}
                    onAddToIcp={handleAddToIcp}
                    adding={addingId === job.job_id}
                  />
                </div>
              ))}
              {!isRecents && total > PAGE_SIZE ? (
                <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
              ) : null}
            </div>
          ) : (
            renderEmpty()
          )}
        </div>
      </section>
    </div>
  );
}
