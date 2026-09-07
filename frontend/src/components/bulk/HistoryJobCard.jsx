import { Link } from 'react-router-dom';
import { FiChevronRight, FiDownload } from 'react-icons/fi';
import { StatusBadge, statusMeta } from '../ui/GrowthWorkspace';
import { formatDateTime } from '../../utils/helpers';

const DOT_COLOR = {
  done: 'bg-emerald-500',
  failed: 'bg-rose-500',
  running: 'bg-primary-500',
  pending: 'bg-slate-400',
  needs_review: 'bg-amber-400',
};

function pct(value, total) {
  if (!total) return 0;
  return Math.max(0, Math.min(100, (value / total) * 100));
}

function shortDate(dateStr) {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

export default function HistoryJobCard({ job, onSelect }) {
  const total = job.total || 0;
  const success = job.completed ?? job.success ?? 0;
  const failed = job.failed || 0;
  const needsReview = job.needs_review || 0;
  const clean = Math.max(success - needsReview, 0);
  const processed = success + failed;

  const statusKey = needsReview > 0 && job.status === 'done' ? 'needs_review' : job.status || 'pending';
  const dotColor = DOT_COLOR[statusKey] || DOT_COLOR.pending;

  const segments = [
    { key: 'clean', value: clean, color: 'bg-emerald-500' },
    { key: 'review', value: needsReview, color: 'bg-amber-400' },
    { key: 'failed', value: failed, color: 'bg-rose-500' },
  ].filter((s) => s.value > 0);

  const progressPct = total ? Math.round(pct(processed || clean, total)) : 0;
  const title = job.original_file_name || 'Untitled upload';
  const uploadedAt = job.created_at || job.started_at;
  const dateLabel = job.status === 'done' && job.completed_at ? 'Completed' : 'Uploaded';

  const className =
    'group block w-full rounded-xl border border-slate-200 bg-white px-4 py-3.5 text-left transition-all hover:border-slate-300 hover:shadow-sm focus:outline-none focus:ring-4 focus:ring-primary-100 sm:px-5';

  const body = (
    <>
    <div className="flex items-center gap-3 sm:gap-4">
      {/* Status dot + file info */}
      <div className="flex min-w-0 flex-1 items-center gap-3 sm:max-w-[min(100%,16rem)] lg:max-w-xs">
        <span
          className={`h-2.5 w-2.5 shrink-0 rounded-full ${dotColor} ${statusKey === 'running' ? 'animate-pulse' : ''}`}
          aria-hidden="true"
        />
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-slate-900 sm:text-[15px]">{title}</p>
          <p className="mt-0.5 truncate text-xs text-slate-500">
            {total.toLocaleString()} profiles
            <span aria-hidden="true"> · </span>
            <span className="hidden sm:inline">{formatDateTime(uploadedAt)}</span>
            <span className="sm:hidden">{shortDate(uploadedAt)}</span>
          </p>
        </div>
      </div>

      {/* Progress bar + percent */}
      <div className="hidden min-w-0 flex-1 items-center gap-3 md:flex lg:max-w-sm xl:max-w-md">
        <div className="flex h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
          {segments.length ? (
            segments.map((segment) => (
              <div
                key={segment.key}
                className={`h-full ${segment.color} transition-all duration-500`}
                style={{ width: `${pct(segment.value, total)}%` }}
              />
            ))
          ) : (
            <div
              className={`h-full bg-slate-300 transition-all duration-500 ${statusKey === 'running' ? 'animate-pulse' : ''}`}
              style={{ width: `${progressPct}%` }}
            />
          )}
        </div>
        <span className="w-9 shrink-0 text-right text-xs tabular-nums text-slate-500">{progressPct}%</span>
      </div>

      {/* Status badge */}
      <StatusBadge status={statusKey} className="hidden shrink-0 sm:inline-flex" />

      {/* Date column */}
      <div className="hidden shrink-0 text-right lg:block lg:min-w-[4.5rem]">
        <p className="text-[10px] font-medium uppercase tracking-wide text-slate-400">{dateLabel}</p>
        <p className="text-sm font-semibold tabular-nums text-slate-900">
          {shortDate(job.completed_at || uploadedAt)}
        </p>
      </div>

      {/* Download hint + chevron */}
      <div className="flex shrink-0 items-center gap-2">
        {job.download_ready ? (
          <span className="hidden items-center gap-1 text-xs font-medium text-primary-600 xl:inline-flex">
            <FiDownload size={12} aria-hidden="true" />
            Excel
          </span>
        ) : null}
        <StatusBadge status={statusKey} className="sm:hidden" />
        <FiChevronRight
          className="text-slate-300 transition-transform group-hover:translate-x-0.5 group-hover:text-slate-500"
          size={18}
          aria-hidden="true"
        />
      </div>
    </div>

    <div className="mt-2.5 flex items-center gap-3 md:hidden">
      <div className="flex h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
        {segments.length ? (
          segments.map((segment) => (
            <div
              key={`mobile-${segment.key}`}
              className={`h-full ${segment.color} transition-all duration-500`}
              style={{ width: `${pct(segment.value, total)}%` }}
            />
          ))
        ) : (
          <div
            className={`h-full bg-slate-300 transition-all duration-500 ${statusKey === 'running' ? 'animate-pulse' : ''}`}
            style={{ width: `${progressPct}%` }}
          />
        )}
      </div>
      <span className="w-9 shrink-0 text-right text-xs tabular-nums text-slate-500">{progressPct}%</span>
    </div>
    </>
  );

  const ariaLabel = `${title}, ${statusMeta(statusKey).label}, ${total} profiles, ${progressPct}% processed`;

  if (onSelect) {
    return (
      <button type="button" onClick={() => onSelect(job)} className={className} aria-label={ariaLabel}>
        {body}
      </button>
    );
  }

  return (
    <Link to={`/linkedin-history/${job.job_id}`} className={className} aria-label={ariaLabel}>
      {body}
    </Link>
  );
}
