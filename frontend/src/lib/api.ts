import { storage } from "@/src/utils/storage";

// Backend URL: prefer env var (Emergent / local dev), fallback to production Render URL.
// Auto-prepends https:// if the env var was saved without a protocol — makes the
// Vercel web build robust to env var misconfigurations.
const RAW_BASE =
  (process.env.EXPO_PUBLIC_BACKEND_URL && process.env.EXPO_PUBLIC_BACKEND_URL.trim()) ||
  "https://vaulted-app.onrender.com";
const BASE = /^https?:\/\//i.test(RAW_BASE) ? RAW_BASE : `https://${RAW_BASE}`;
const TOKEN_KEY = "vaulted_token";
const REFRESH_KEY = "vaulted_refresh_token";

// Exposed so views that need to build full URLs for downloads
// (e.g. /admin letterhead download card) don't have to re-derive this.
export const API_BASE = BASE;

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export async function setToken(token: string | null) {
  if (token) await storage.secureSet(TOKEN_KEY, token);
  else await storage.secureRemove(TOKEN_KEY);
}

export async function getToken(): Promise<string | null> {
  return storage.secureGet<string>(TOKEN_KEY, "");
}

export async function setRefreshToken(token: string | null) {
  if (token) await storage.secureSet(REFRESH_KEY, token);
  else await storage.secureRemove(REFRESH_KEY);
}

export async function getRefreshToken(): Promise<string | null> {
  return storage.secureGet<string>(REFRESH_KEY, "");
}

/**
 * Store BOTH tokens from a login/register/refresh response. Centralised so
 * callers can't accidentally forget to persist the refresh token.
 */
export async function saveSession(resp: { access_token?: string; refresh_token?: string | null }) {
  if (resp.access_token) await setToken(resp.access_token);
  if (resp.refresh_token !== undefined) {
    await setRefreshToken(resp.refresh_token || null);
  }
}

type UnauthorizedHandler = (err: ApiError) => void;
let _onUnauthorized: UnauthorizedHandler | null = null;
export function registerUnauthorizedHandler(handler: UnauthorizedHandler | null) {
  _onUnauthorized = handler;
}

// Single-flight refresh lock — if 7 cards all 401 at once we fire ONE
// /auth/refresh and let all callers await the same promise. Prevents a
// burst from rotating the same refresh token concurrently (which would
// trigger reuse-detection on the server and nuke the session family).
let _refreshInFlight: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (_refreshInFlight) return _refreshInFlight;
  _refreshInFlight = (async () => {
    const rt = await getRefreshToken();
    if (!rt) return null;
    try {
      const r = await fetch(`${BASE}/api/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: rt }),
      });
      if (!r.ok) {
        // Refresh itself failed — session is dead; clear both tokens so
        // the next cold start lands on /sign-in rather than looping.
        await setToken(null);
        await setRefreshToken(null);
        return null;
      }
      const data = await r.json();
      if (data?.access_token) await setToken(data.access_token);
      if (data?.refresh_token) await setRefreshToken(data.refresh_token);
      return (data?.access_token as string) || null;
    } catch {
      return null;
    }
  })().finally(() => { _refreshInFlight = null; });
  return _refreshInFlight;
}

type Options = { method?: string; body?: any; auth?: boolean };

export async function api<T = any>(path: string, opts: Options = {}, _retried = false): Promise<T> {
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
    const detail = (data && (data.detail || data.message)) || `Request failed (${res.status})`;
    const message = typeof detail === "string" ? detail : JSON.stringify(detail);
    const err = new ApiError(message, res.status);

    // 401 → try a silent refresh exactly once, then retry the original
    // request. Skip the refresh for /auth/refresh itself or we'd loop.
    if (res.status === 401 && !_retried && path !== "/auth/refresh" && opts.auth !== false) {
      const fresh = await refreshAccessToken();
      if (fresh) {
        // Retry transparently with the new token.
        return api<T>(path, opts, true);
      }
    }

    if (res.status === 401) {
      try {
        await setToken(null);
        await setRefreshToken(null);
      } catch { /* non-fatal */ }
      if (_onUnauthorized) {
        try { _onUnauthorized(err); } catch { /* handler must not re-raise */ }
      }
    }
    throw err;
  }
  return data as T;
}
