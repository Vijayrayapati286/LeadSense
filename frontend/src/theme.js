export const THEME_STORAGE_KEY = 'leadsense-theme';

export const THEMES = [
  {
    id: 'default',
    name: 'Current theme',
    description: 'Blue accent on a cool slate workspace.',
    swatches: ['#2563eb', '#3b82f6', '#0b1220', '#f8f9fb'],
    chartAccent: '#3578f6',
  },
  {
    id: 'sunset-coral',
    name: 'Sunset Coral',
    description: 'Warm orange accent, peach canvas, and a charcoal sidebar.',
    swatches: ['#FF5E00', '#FF6B35', '#1E1E24', '#FAF9F8'],
    chartAccent: '#FF6B35',
  },
];

export function isThemeId(value) {
  return THEMES.some((theme) => theme.id === value);
}

export function readStoredTheme() {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    return isThemeId(stored) ? stored : 'default';
  } catch {
    return 'default';
  }
}

export function applyTheme(themeId) {
  const id = isThemeId(themeId) ? themeId : 'default';
  const root = document.documentElement;
  if (id === 'default') {
    delete root.dataset.theme;
  } else {
    root.dataset.theme = id;
  }
  return id;
}

export function applyStoredTheme() {
  return applyTheme(readStoredTheme());
}

export function chartAccentFor(themeId) {
  return THEMES.find((theme) => theme.id === themeId)?.chartAccent || THEMES[0].chartAccent;
}
