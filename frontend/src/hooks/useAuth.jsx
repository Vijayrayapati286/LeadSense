import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { authService } from '../services/services';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadUser = useCallback(async () => {
    const token = localStorage.getItem('token');
    if (!token) {
      setLoading(false);
      return;
    }

    try {
      const { data } = await authService.getMe();
      setUser(data);
      localStorage.setItem('user', JSON.stringify(data));
    } catch {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const stored = localStorage.getItem('user');
    if (stored) {
      try {
        setUser(JSON.parse(stored));
      } catch {
        /* ignore */
      }
    }
    loadUser();
  }, [loadUser]);

  const login = async (token, userData) => {
    localStorage.setItem('token', token);
    if (userData) {
      setUser(userData);
      localStorage.setItem('user', JSON.stringify(userData));
    } else {
      await loadUser();
    }
  };

  const devLogin = async (email, name) => {
    const { data } = await authService.devLogin(email || name ? { email, name } : undefined);
    await login(data.access_token, data.user);
    return data;
  };

  const passwordLogin = async (email, password) => {
    const { data } = await authService.passwordLogin(email, password);
    await login(data.access_token, data.user);
    return data;
  };

  const logout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    setUser(null);
    authService.logout().catch(() => {});
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, devLogin, passwordLogin, logout, loadUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
}
