export const THEME_STORAGE_KEY = 'leadsense-theme';

const DEFAULT_TOKENS = {
  '--ls-primary-50': '239 246 255',
  '--ls-primary-100': '219 234 254',
  '--ls-primary-200': '191 219 254',
  '--ls-primary-300': '147 197 253',
  '--ls-primary-400': '96 165 250',
  '--ls-primary-500': '59 130 246',
  '--ls-primary-600': '37 99 235',
  '--ls-primary-700': '29 78 216',
  '--ls-primary-800': '30 64 175',
  '--ls-primary-900': '30 58 138',
  '--ls-sidebar': '11 18 32',
  '--ls-surface': '255 255 255',
  '--ls-surface-muted': '248 249 251',
  '--ls-surface-inset': '241 245 249',
  '--ls-accent': '37 99 235',
  '--ls-accent-hover': '29 78 216',
  '--shadow-button': '0 4px 14px rgba(37, 99, 235, 0.2)',
  '--page-glow-a': 'rgba(59, 130, 246, 0.08)',
  '--page-glow-b': 'rgba(14, 165, 233, 0.05)',
  '--hero-glow': 'rgba(59, 130, 246, 0.14)',
  '--link-color': '#2563eb',
};

const SUNSET_CORAL_TOKENS = {
  '--ls-primary-50': '255 244 238',
  '--ls-primary-100': '255 228 214',
  '--ls-primary-200': '255 201 173',
  '--ls-primary-300': '255 168 122',
  '--ls-primary-400': '255 138 76',
  '--ls-primary-500': '255 107 53',
  '--ls-primary-600': '255 94 0',
  '--ls-primary-700': '224 78 0',
  '--ls-primary-800': '184 61 0',
  '--ls-primary-900': '122 40 0',
  '--ls-sidebar': '30 30 36',
  '--ls-surface': '255 255 255',
  '--ls-surface-muted': '255 247 242',
  '--ls-surface-inset': '255 236 227',
  '--ls-accent': '255 94 0',
  '--ls-accent-hover': '224 78 0',
  '--shadow-button': '0 4px 14px rgba(255, 94, 0, 0.28)',
  '--page-glow-a': 'rgba(255, 107, 53, 0.14)',
  '--page-glow-b': 'rgba(255, 180, 140, 0.1)',
  '--hero-glow': 'rgba(255, 107, 53, 0.18)',
  '--link-color': '#ff5e00',
};

export const THEME_TOKENS = {
  default: DEFAULT_TOKENS,
  'sunset-coral': SUNSET_CORAL_TOKENS,
};

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
  const tokens = THEME_TOKENS[id] || DEFAULT_TOKENS;
  Object.entries(tokens).forEach(([name, value]) => {
    root.style.setProperty(name, value);
  });
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
