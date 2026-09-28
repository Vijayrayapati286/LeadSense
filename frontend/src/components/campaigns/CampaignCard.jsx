import { Link } from 'react-router-dom';
import { FiEdit2, FiTrash2, FiArrowRight } from 'react-icons/fi';
import SurfaceCard from '../ui/SurfaceCard';
import StatusBadge from '../ui/StatusBadge';
import StatBlock from '../ui/StatBlock';
import { formatDate } from '../../utils/helpers';

/**
 * Shared campaign card — fixed layout so every card is the same height.
 */
export default function CampaignCard({
  campaign,
  onDelete,
  detailsTo,
  detailsState,
  detailsLabel = 'Details',
  hideEdit = false,
  hideDelete = false,
}) {
  const c = campaign;
  const to = detailsTo || `/campaigns/${c.id}`;
  const subtitle = c.subject || c.description || 'No description';

  return (
    <SurfaceCard
      variant="flat"
      className="flex h-full min-h-[248px] flex-col gap-4 border-t-4 border-t-primary-400 p-5 shadow-card transition duration-200 hover:-translate-y-0.5 hover:shadow-card-hover"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="truncate font-semibold text-slate-950">{c.campaign_name}</h3>
          <p className="mt-0.5 truncate text-body-sm text-slate-500" title={subtitle}>
            {subtitle}
          </p>
          {c.owner ? (
            <p className="mt-1 truncate text-caption text-slate-400">{c.owner}</p>
          ) : null}
        </div>
        <div className="shrink-0">
          <StatusBadge status={c.status} />
        </div>
      </div>

      {/* Fixed-height tag row so cards stay equal even when tags are missing */}
      <div className="flex h-7 items-center gap-1.5 overflow-hidden">
        {c.department ? (
          <span className="badge badge-info shrink-0">{c.department}</span>
        ) : (
          <span className="invisible badge">—</span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <StatBlock label="Emails Sent" value={c.emails_sent} />
        <StatBlock label="Created" value={formatDate(c.created_at)} />
      </div>

      <div className="mt-auto flex items-center justify-between border-t border-slate-100 pt-3">
        <div className="flex flex-wrap items-center gap-2">
          {!hideEdit && (
            <Link
              to={`/campaigns/${c.id}/edit`}
              className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50 active:scale-[.98]"
            >
              <FiEdit2 size={13} /> Edit
            </Link>
          )}
          {!hideDelete && onDelete && (
            <button
              type="button"
              onClick={() => onDelete(c.id)}
              className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:border-red-200 hover:bg-red-50 hover:text-red-600 active:scale-[.98]"
            >
              <FiTrash2 size={13} /> Delete
            </button>
          )}
        </div>
        <Link
          to={to}
          state={detailsState}
          className="inline-flex items-center gap-1 text-sm font-medium text-primary-600 transition hover:text-primary-700"
        >
          {detailsLabel} <FiArrowRight size={14} />
        </Link>
      </div>
    </SurfaceCard>
  );
}
