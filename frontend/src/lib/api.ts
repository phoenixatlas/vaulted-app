import { storage } from "@/src/utils/storage";

// Backend URL: prefer env var (Emergent / local dev), fallback to production Render URL.
// This makes the Vercel web build robust to env var misconfigurations.
const BASE =
  (process.env.EXPO_PUBLIC_BACKEND_URL && process.env.EXPO_PUBLIC_BACKEND_URL.trim()) ||
  "https://vaulted-app.onrender.com";
const TOKEN_KEY = "vaulted_token";

export async function setToken(token: string | null) {
  if (token) await storage.secureSet(TOKEN_KEY, token);
  else await storage.secureRemove(TOKEN_KEY);
}

export async function getToken(): Promise<string | null> {
  return storage.secureGet<string>(TOKEN_KEY, "");
}

type Options = { method?: string; body?: any; auth?: boolean };

export async function api<T = any>(path: string, opts: Options = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (opts.auth !== false) {
    const t = await getToken();
    if (t) headers.Authorization = `Bearer ${t}`;
  }
  const res = await fetch(`${BASE}/api${path}`, {
    method: opts.method || "GET",
    headers,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = (data && (data.detail || data.message)) || `Request failed (${res.status})`;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data as T;
}
