import StatusBadge from './StatusBadge';

const LABELS = {
  verified: 'Verified',
  failed: 'Failed',
  unchecked: 'Not checked',
};

/** MillionVerifier status badge for prospect / campaign lists. */
export default function EmailVerificationBadge({ status, result, className = '' }) {
  const key = (status || 'unchecked').toLowerCase();
  const label = LABELS[key] || status || 'Not checked';
  const title =
    result && key !== 'unchecked'
      ? `${label} (${result})`
      : key === 'unchecked'
        ? 'Not verified yet — checked when the email is sent'
        : label;

  return (
    <span title={title} className={className}>
      <StatusBadge status={`email_${key}`} label={label} />
    </span>
  );
}
