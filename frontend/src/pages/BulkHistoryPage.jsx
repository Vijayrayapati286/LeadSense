import { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { FiAlertCircle, FiCheckCircle, FiLayers, FiPlus, FiRefreshCw, FiSearch, FiX, FiXCircle } from 'react-icons/fi';
import HistoryJobCard from '../components/bulk/HistoryJobCard';
import Pagination from '../components/ui/Pagination';
import {
  EmptyState,
  ExtractorNav,
  LoadingAnnouncement,
  MetricCard,
  SkeletonCards,
  WorkspaceHeader,
} from '../components/ui/GrowthWorkspace';
import { useToast } from '../hooks/useToast';
import { linkedinProfileService } from '../services/services';

const PAGE_SIZE = 20;

const FILTERS = [
  { key: 'all', label: 'All', params: {}, dot: 'bg-slate-400', idle: 'text-slate-500 hover:bg-white hover:text-slate-900', active: 'bg-white text-slate-900 shadow-sm ring-1 ring-slate-200' },
  { key: 'completed', label: 'Completed', params: { status: 'done', needs_review: false }, dot: 'bg-emerald-500', idle: 'text-slate-500 hover:bg-emerald-50 hover:text-emerald-700', active: 'bg-white text-emerald-700 shadow-sm ring-1 ring-emerald-200' },
  { key: 'processing', label: 'Processing', params: { status: 'pending,running' }, dot: 'bg-primary-500', idle: 'text-slate-500 hover:bg-primary-50 hover:text-primary-700', active: 'bg-white text-primary-700 shadow-sm ring-1 ring-primary-200' },
  { key: 'needs_review', label: 'Needs review', params: { needs_review: true }, dot: 'bg-amber-400', idle: 'text-slate-500 hover:bg-amber-50 hover:text-amber-700', active: 'bg-white text-amber-700 shadow-sm ring-1 ring-amber-200' },
  { key: 'failed', label: 'Failed', params: { status: 'failed' }, dot: 'bg-rose-500', idle: 'text-slate-500 hover:bg-rose-50 hover:text-rose-700', active: 'bg-white text-rose-700 shadow-sm ring-1 ring-rose-200' },
];

function filterFor(key) {
  return FILTERS.find((f) => f.key === key) || FILTERS[0];
}

export default function BulkHistoryPage() {
  const toast = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const filterKey = searchParams.get('filter') || 'all';
  const appliedQ = searchParams.get('q') || '';

  const [draftQ, setDraftQ] = useState(appliedQ);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({ total: 0, items: [], page: 1 });
  const [counts, setCounts] = useState({ all: 0, completed: 0, needs_review: 0, failed: 0 });

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
        page,
        page_size: PAGE_SIZE,
        ...filterFor(filterKey).params,
      });
      setData(payload);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to load history');
    } finally {
      setLoading(false);
    }
  }, [appliedQ, filterKey, page, toast]);

  useEffect(() => {
    load();
  }, [load]);

  // Bucket totals come from the API rather than the current page, so the
  // headline numbers stay true once history spans more than one page.
  useEffect(() => {
    let cancelled = false;
    const countOnly = { q: appliedQ || undefined, page: 1, page_size: 1 };
    Promise.all(
      ['all', 'completed', 'needs_review', 'failed'].map((key) =>
        linkedinProfileService
          .listBulkJobs({ ...countOnly, ...filterFor(key).params })
          .then((r) => r.total || 0)
          .catch(() => 0),
      ),
    ).then(([all, completed, needs_review, failed]) => {
      if (!cancelled) setCounts({ all, completed, needs_review, failed });
    });
    return () => {
      cancelled = true;
    };
  }, [appliedQ]);

  const items = data.items || [];
  const total = data.total || 0;
  const rangeStart = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const rangeEnd = Math.min(page * PAGE_SIZE, total);

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
      >
        <ExtractorNav />
      </WorkspaceHeader>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="All jobs"
          value={counts.all}
          hint="Across every status"
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
          tone="amber"
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

          {!loading && total > 0 ? (
            <p className="text-xs text-slate-500">
              Showing <span className="font-semibold text-slate-700">{rangeStart}–{rangeEnd}</span> of {total} job
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
                  <HistoryJobCard job={job} />
                </div>
              ))}
              {total > PAGE_SIZE ? (
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
