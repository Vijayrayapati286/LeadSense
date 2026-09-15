import { STATUS_BADGE_CLASSES } from '../../design-tokens';

export default function StatusBadge({ status, label, className = '' }) {
  const key = status?.toLowerCase();
  const badgeClass = STATUS_BADGE_CLASSES[key] || 'badge-neutral';
  const text = label || status;

  return (
    <span className={`badge ${badgeClass} capitalize ${className}`}>
      <span className="badge-dot" aria-hidden="true" />
      {text}
    </span>
  );
}
