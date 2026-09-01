/** Shared design vocabulary — tone maps for metrics, charts, and badges. */

export const METRIC_TONES = {
  blue: 'bg-blue-50 text-blue-600',
  green: 'bg-emerald-50 text-emerald-600',
  amber: 'bg-amber-50 text-amber-600',
  red: 'bg-rose-50 text-rose-600',
  cyan: 'bg-cyan-50 text-cyan-600',
  violet: 'bg-violet-50 text-violet-600',
};

export const CHART_COLORS = ['#3578f6', '#14b87a', '#ffac32', '#f2535a'];

export const STATUS_BADGE_CLASSES = {
  active: 'badge-success',
  draft: 'badge-neutral',
  completed: 'badge-info',
  paused: 'badge-warning',
  sent: 'badge-success',
  failed: 'badge-danger',
  pending: 'badge-warning',
  hard_bounce: 'badge-danger',
  soft_bounce_threshold_exceeded: 'badge-warning',
  domain_rejected: 'badge-danger',
  mail_server_blocked: 'badge-danger',
  complaint: 'badge-warning',
  manual: 'badge-neutral',
  not_contacted: 'badge-neutral',
  queued: 'badge-info',
  delivered: 'badge-success',
  opened: 'badge-info',
  clicked: 'badge-info',
  replied: 'badge-success',
  bounced: 'badge-danger',
  invalid_email: 'badge-danger',
  suppressed: 'badge-warning',
};
