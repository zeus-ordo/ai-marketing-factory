"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  getMe,
  login as apiLogin,
  logout as apiLogout,
  refresh as apiRefresh,
  type MemberProfile,
} from "@/lib/api/auth";

interface AuthContextValue {
  user: MemberProfile | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const ACCESS_TOKEN_KEY = "access_token";
const REFRESH_TOKEN_KEY = "refresh_token";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<MemberProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const clearStoredSession = useCallback(() => {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    setUser(null);
  }, []);

  const refreshFromStorage = useCallback(async (loadProfile = false) => {
    const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
    if (!refreshToken) throw new Error("No refresh token");
    const result = await apiRefresh(refreshToken);
    localStorage.setItem(ACCESS_TOKEN_KEY, result.access_token);
    localStorage.setItem(REFRESH_TOKEN_KEY, result.refresh_token);
    if (loadProfile) {
      const profile = await getMe();
      setUser(profile);
    }
    return result;
  }, []);

  const loadUser = useCallback(async () => {
    const token = localStorage.getItem(ACCESS_TOKEN_KEY);
    if (!token) {
      setIsLoading(false);
      return;
    }
    try {
      const profile = await getMe();
      setUser(profile);
    } catch {
      try {
        await refreshFromStorage(true);
      } catch {
        // Token invalid/expired and refresh failed
        clearStoredSession();
      }
    } finally {
      setIsLoading(false);
    }
  }, [clearStoredSession, refreshFromStorage]);

  // Load user on mount
  useEffect(() => {
    void Promise.resolve().then(loadUser);
  }, [loadUser]);

  // Auto-refresh 5 minutes before expiry
  useEffect(() => {
    // Refresh every 25 minutes (access token is 1h). Read the latest refresh
    // token each time so multi-tab login/logout changes are respected.
    const interval = setInterval(async () => {
      try {
        if (!localStorage.getItem(REFRESH_TOKEN_KEY)) return;
        await refreshFromStorage(false);
      } catch {
        clearStoredSession();
      }
    }, 25 * 60 * 1000);

    return () => clearInterval(interval);
  }, [clearStoredSession, refreshFromStorage]);

  // Refresh on tab visibility change (handles sleep/wake cycles)
  useEffect(() => {
    function handleVisibilityChange() {
      if (document.visibilityState === "visible" && localStorage.getItem(REFRESH_TOKEN_KEY)) {
        // Refresh immediately when tab becomes visible
        void refreshFromStorage(false).catch(() => {
          // If refresh fails, clear session
          clearStoredSession();
        });
      }
    }
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => document.removeEventListener("visibilitychange", handleVisibilityChange);
  }, [clearStoredSession, refreshFromStorage]);

  // Multi-tab session sync via storage events
  useEffect(() => {
    function handleStorageChange(e: StorageEvent) {
      if (e.key === ACCESS_TOKEN_KEY || e.key === REFRESH_TOKEN_KEY) {
        if (e.key === REFRESH_TOKEN_KEY && !e.newValue) {
          // Logged out in another tab
          clearStoredSession();
        } else if (localStorage.getItem(ACCESS_TOKEN_KEY)) {
          // Token changed in another tab — reload profile without rotating refresh token again.
          void getMe().then(setUser).catch(() => {
            clearStoredSession();
          });
        }
      }
    }
    window.addEventListener("storage", handleStorageChange);
    return () => window.removeEventListener("storage", handleStorageChange);
  }, [clearStoredSession]);

  const login = useCallback(async (email: string, password: string) => {
    const result = await apiLogin(email, password);
    localStorage.setItem(ACCESS_TOKEN_KEY, result.access_token);
    localStorage.setItem(REFRESH_TOKEN_KEY, result.refresh_token);
    const profile = await getMe();
    setUser(profile);
  }, []);

  const logout = useCallback(async () => {
    const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
    clearStoredSession();
    if (refreshToken) {
      try {
        await apiLogout(refreshToken);
      } catch {
        // Ignore errors
      }
    }
  }, [clearStoredSession]);

  const refresh = useCallback(async () => {
    await refreshFromStorage(true);
  }, [refreshFromStorage]);

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
