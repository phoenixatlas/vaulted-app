import React, { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api, getToken, setToken } from "./api";
import { registerForPush } from "./push";

type User = {
  id: string;
  email: string;
  name: string;
  language: string;
  wallet_address: string;
  biometric_enabled: boolean;
  multisig_enabled: boolean;
  public_key?: string | null;
  is_pro?: boolean;
  subscription?: { tier: string; status: string; current_period_end?: number | null };
  onboarding_seed_acknowledged?: boolean;
  referral_code?: string | null;
};

type AuthCtx = {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string, referredByCode?: string | null) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  setUser: (u: User | null) => void;
};

const AuthContext = createContext<AuthCtx>(null as any);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    try {
      const t = await getToken();
      if (!t) {
        setUser(null);
        return;
      }
      const u = await api<User>("/auth/me");
      setUser(u);
    } catch {
      setUser(null);
      await setToken(null);
    }
  };

  useEffect(() => {
    (async () => {
      await refresh();
      setLoading(false);
    })();
  }, []);

  // Whenever we have an authenticated user, ensure the push token is registered
  // with the Emergent push service. No-op on web / unsupported devices.
  useEffect(() => {
    if (user?.id) {
      registerForPush(user.id).catch(() => undefined);
    }
  }, [user?.id]);

  const login = async (email: string, password: string) => {
    const res = await api<{ access_token: string; user: User }>("/auth/login", {
      method: "POST",
      body: { email, password },
      auth: false,
    });
    await setToken(res.access_token);
    setUser(res.user);
  };

  const register = async (email: string, password: string, name: string, referredByCode?: string | null) => {
    const body: any = { email, password, name };
    if (referredByCode && referredByCode.trim()) {
      body.referred_by_code = referredByCode.trim().toUpperCase();
    }
    const res = await api<{ access_token: string; user: User }>("/auth/register", {
      method: "POST",
      body,
      auth: false,
    });
    await setToken(res.access_token);
    setUser(res.user);
  };

  const logout = async () => {
    await setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refresh, setUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
