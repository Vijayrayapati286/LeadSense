import { FiClock } from 'react-icons/fi';
import { formatDateTime } from '../../utils/helpers';

function initials(name) {
  const parts = String(name || '').trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return '?';
  return (parts[0][0] + (parts[1]?.[0] || '')).toUpperCase();
}

function relativeTime(value) {
  if (!value) return '';
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return '';
  const seconds = Math.round((Date.now() - then) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return formatDateTime(value);
}

export default function AuditLogPanel({ entries }) {
  const rows = entries || [];

  if (rows.length === 0) {
    return (
      <div className="py-10 text-center">
        <span className="empty-state-icon"><FiClock size={20} /></span>
        <p className="mt-3 text-sm font-medium text-slate-700">No changes yet</p>
        <p className="mt-1 text-xs text-slate-500">
          Field-level edits appear here as soon as someone resolves a conflict.
        </p>
      </div>
    );
  }

  return (
    <ol className="relative space-y-5 border-l border-slate-200 pl-5">
      {rows.map((entry) => (
        <li key={entry.id} className="relative">
          <span className="absolute -left-[1.6875rem] flex h-6 w-6 items-center justify-center rounded-full bg-primary-50 text-[10px] font-bold text-primary-700 ring-4 ring-white">
            {initials(entry.actor)}
          </span>
          <div className="flex flex-wrap items-baseline gap-x-1.5">
            <span className="text-sm font-semibold text-slate-900">{entry.actor || 'Unknown user'}</span>
            <span className="text-sm text-slate-500">updated</span>
            <span className="badge badge-info">{entry.field}</span>
          </div>
          {entry.change_summary ? (
            <p className="mt-1.5 text-xs leading-relaxed text-slate-600">{entry.change_summary}</p>
          ) : null}
          <p className="mt-1.5 text-[11px] text-slate-400">
            Row {entry.source_row_number ?? '—'}
            {entry.resolved_at ? (
              <>
                {' · '}
                <time dateTime={entry.resolved_at} title={formatDateTime(entry.resolved_at)}>
                  {relativeTime(entry.resolved_at)}
                </time>
              </>
            ) : null}
          </p>
        </li>
      ))}
    </ol>
  );
}
