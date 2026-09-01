import { Link } from 'react-router-dom';
import { FiEdit2, FiTrash2, FiArrowRight } from 'react-icons/fi';
import SurfaceCard from '../ui/SurfaceCard';
import StatusBadge from '../ui/StatusBadge';
import StatBlock from '../ui/StatBlock';
import { formatDate } from '../../utils/helpers';

export default function CampaignCard({ campaign, onDelete }) {
  const c = campaign;

  return (
    <SurfaceCard
      variant="flat"
      className="flex flex-col gap-4 border-t-4 border-t-primary-400 p-5 shadow-card transition duration-200 hover:-translate-y-0.5 hover:shadow-card-hover"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="truncate font-semibold text-slate-950">{c.campaign_name}</h3>
          <p className="mt-0.5 truncate text-body-sm text-slate-500">
            {c.subject || c.target_audience || c.description || 'No description'}
          </p>
          <p className="mt-1 truncate font-mono text-caption text-slate-400">
            {c.owner} · {c.campaign_id}
          </p>
        </div>
        <div className="shrink-0">
          <StatusBadge status={c.status} />
        </div>
      </div>

      {(c.department || c.target_audience) && (
        <div className="flex flex-wrap gap-1.5">
          {c.department && (
            <span className="badge badge-info">{c.department}</span>
          )}
          {c.target_audience && (
            <span className="badge badge-warning">{c.target_audience}</span>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <StatBlock label="Emails Sent" value={c.emails_sent} />
        <StatBlock label="Created" value={formatDate(c.created_at)} />
      </div>

      <div className="flex items-center justify-between border-t border-slate-100 pt-3">
        <div className="flex flex-wrap items-center gap-2">
          <Link
            to={`/campaigns/${c.id}/edit`}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50 active:scale-[.98]"
          >
            <FiEdit2 size={13} /> Edit
          </Link>
          <button
            type="button"
            onClick={() => onDelete(c.id)}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:border-red-200 hover:bg-red-50 hover:text-red-600 active:scale-[.98]"
          >
            <FiTrash2 size={13} /> Delete
          </button>
        </div>
        <Link
          to={`/campaigns/${c.id}`}
          className="inline-flex items-center gap-1 text-sm font-medium text-primary-600 transition hover:text-primary-700"
        >
          Details <FiArrowRight size={14} />
        </Link>
      </div>
    </SurfaceCard>
  );
}
