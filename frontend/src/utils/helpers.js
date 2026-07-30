/** Extract {{Placeholder}} tokens from template text */
export function extractPlaceholders(text) {
  const matches = text.match(/\{\{(\w+)\}\}/g) || [];
  return [...new Set(matches.map((m) => m.replace(/\{\{|\}\}/g, '')))];
}

/** Replace {{Key}} placeholders with values */
export function renderTemplate(text, context) {
  let result = text;
  Object.entries(context).forEach(([key, value]) => {
    result = result.replace(new RegExp(`\\{\\{${key}\\}\\}`, 'g'), value);
  });
  return result;
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** Render a small markdown subset (**bold**, "- " bullet lists, blank-line
 * paragraphs) into inline-styled HTML, mirroring the backend's send-time
 * rendering so the preview matches what recipients actually receive. */
export function renderMarkdownLite(text) {
  if (!text) return '';
  let escaped = escapeHtml(text).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

  return escaped
    .trim()
    .split(/\n\s*\n/)
    .map((block) => {
      const lines = block.split('\n').map((l) => l.trim()).filter(Boolean);
      if (lines.length === 0) return '';
      const isBulletBlock = lines.every((l) => /^[-•*]\s+/.test(l));
      if (isBulletBlock) {
        const items = lines.map((l) => l.replace(/^[-•*]\s+/, ''));
        return `<ul style="margin:0 0 14px 0;padding-left:20px;list-style-type:disc;">${items
          .map((i) => `<li style="margin-bottom:4px;">${i}</li>`)
          .join('')}</ul>`;
      }
      return `<p style="margin:0 0 14px 0;">${lines.join('<br>')}</p>`;
    })
    .join('');
}

/** True when a template body has no real content. Manual templates store
 * HTML from the rich text editor — an empty doc serializes as "<p></p>",
 * which a naive `.trim().length > 0` check wrongly treats as non-empty. */
export function isTemplateBodyEmpty(body, type) {
  if (!body) return true;
  if (type !== 'manual') return body.trim().length === 0;
  const stripped = body.replace(/<[^>]*>/g, '').replace(/&nbsp;/gi, ' ').trim();
  if (stripped.length > 0) return false;
  return !/<(img|table)\b/i.test(body);
}

/** Plain-text snippet from a template body, for compact list/card previews —
 * manual templates store real HTML, which must never be interpolated as JSX
 * text directly (shows literal tags) nor as full dangerouslySetInnerHTML in
 * a clamped summary (unnecessary formatting/sanitization for a 2-line teaser). */
export function stripHtml(body, type) {
  if (!body) return '';
  if (type !== 'manual') return body;
  return body.replace(/<[^>]*>/g, ' ').replace(/&nbsp;/gi, ' ').replace(/\s+/g, ' ').trim();
}

/** Manual templates saved before the rich text editor shipped stored plain
 * markdown-lite text (**bold**, "- " bullets). Upgrade that once into an
 * HTML doc on load so old templates still display/edit correctly, without a
 * DB migration. */
export function ensureManualBodyIsHtml(body) {
  if (!body) return body;
  if (body.trim().startsWith('<')) return body;
  return renderMarkdownLite(body);
}

/** Format date string for display */
export function formatDate(dateStr) {
  if (!dateStr) return '—';
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

/** Format datetime for display */
export function formatDateTime(dateStr) {
  if (!dateStr) return '—';
  const date = new Date(dateStr);
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** Convert an ISO datetime string to the local value a `datetime-local`
 * input expects ("YYYY-MM-DDTHH:mm"), or '' if unset. */
export function toDatetimeLocalValue(isoStr) {
  if (!isoStr) return '';
  const date = new Date(isoStr);
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** Generate campaign ID */
export function generateCampaignId() {
  const ts = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14);
  return `CMP-${ts}`;
}

/** Status badge color mapping */
export function getStatusColor(status) {
  const colors = {
    active: 'bg-green-100 text-green-800',
    draft: 'bg-gray-100 text-gray-800',
    completed: 'bg-blue-100 text-blue-800',
    paused: 'bg-amber-100 text-amber-800',
    sent: 'bg-green-100 text-green-800',
    failed: 'bg-red-100 text-red-800',
    pending: 'bg-yellow-100 text-yellow-800',
    // Blacklist reasons
    hard_bounce: 'bg-red-100 text-red-800',
    soft_bounce_threshold_exceeded: 'bg-amber-100 text-amber-800',
    domain_rejected: 'bg-red-100 text-red-800',
    mail_server_blocked: 'bg-red-100 text-red-800',
    complaint: 'bg-orange-100 text-orange-800',
    manual: 'bg-gray-100 text-gray-800',
    // Campaign-recipient tracking statuses
    not_contacted: 'bg-gray-100 text-gray-800',
    queued: 'bg-blue-100 text-blue-800',
    delivered: 'bg-green-100 text-green-800',
    opened: 'bg-blue-100 text-blue-800',
    clicked: 'bg-purple-100 text-purple-800',
    replied: 'bg-emerald-100 text-emerald-800',
    bounced: 'bg-red-100 text-red-800',
    invalid_email: 'bg-red-100 text-red-800',
    suppressed: 'bg-orange-100 text-orange-800',
  };
  return colors[status?.toLowerCase()] || 'bg-gray-100 text-gray-800';
}

/** The prospect-list upload endpoint returns a structured
 * `{ error: "missing_columns", missing_columns: [...] }` detail when Name
 * and/or Email ID can't be found in the file — this pulls that array out of
 * an axios error, or returns null for any other kind of upload failure so
 * the caller falls back to a plain toast. */
export function getMissingUploadColumns(err) {
  const detail = err?.response?.data?.detail;
  if (detail && typeof detail === 'object' && detail.error === 'missing_columns') {
    return detail.missing_columns || [];
  }
  return null;
}

/** Confirmation-dialog copy for a prospect-list upload that overlaps
 * heavily with existing prospects — see getMissingUploadColumns above for
 * the sibling "missing required column" case. */
export function buildDuplicateUploadMessage(total, duplicateCount) {
  return (
    `We found that ${duplicateCount} of ${total} prospect(s) already exist in this prospect list. ` +
    `Do you still want to import this file as a new prospect list?`
  );
}

/** Debounce utility */
export function debounce(fn, delay = 300) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}
