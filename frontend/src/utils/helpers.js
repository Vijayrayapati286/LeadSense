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
  };
  return colors[status?.toLowerCase()] || 'bg-gray-100 text-gray-800';
}

/** Debounce utility */
export function debounce(fn, delay = 300) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}
