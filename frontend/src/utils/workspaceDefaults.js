const STORAGE_KEY = 'leadsense.workspace';

export function syncWorkspaceDefaults(settings) {
  if (!settings) return;
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      default_page_size: settings.default_page_size,
      default_ai_tone: settings.default_ai_tone,
      default_use_recipient_timezone: settings.default_use_recipient_timezone,
    }),
  );
}

export function getWorkspaceDefaults() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
  } catch {
    return {};
  }
}

export function getDefaultPageSize(fallback = 10) {
  const size = Number(getWorkspaceDefaults().default_page_size);
  return Number.isFinite(size) && size > 0 ? size : fallback;
}

export function getDefaultAiTone(fallback = 'formal') {
  return getWorkspaceDefaults().default_ai_tone || fallback;
}
