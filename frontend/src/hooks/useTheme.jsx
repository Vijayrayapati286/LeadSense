import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import { applyTheme, chartAccentFor, readStoredTheme, THEME_STORAGE_KEY } from '../theme';

const ThemeContext = createContext(null);

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(() => readStoredTheme());

  const setTheme = useCallback((next) => {
    const id = applyTheme(next);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, id);
    } catch {
      /* storage can be unavailable in private contexts */
    }
    setThemeState(id);
  }, []);

  const value = useMemo(
    () => ({
      theme,
      setTheme,
      chartAccent: chartAccentFor(theme),
    }),
    [theme, setTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within ThemeProvider');
  }
  return context;
}
