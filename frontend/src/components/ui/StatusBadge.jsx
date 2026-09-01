import { STATUS_BADGE_CLASSES } from '../../design-tokens';

export default function StatusBadge({ status, className = '' }) {
  const key = status?.toLowerCase();
  const badgeClass = STATUS_BADGE_CLASSES[key] || 'badge-neutral';

  return (
    <span className={`badge ${badgeClass} capitalize ${className}`}>
      <span className="badge-dot" aria-hidden="true" />
      {status}
    </span>
  );
}
