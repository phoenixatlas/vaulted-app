import { storage } from "@/src/utils/storage";

// Backend URL: prefer env var (Emergent / local dev), fallback to production Render URL.
// Auto-prepends https:// if the env var was saved without a protocol — makes the
// Vercel web build robust to env var misconfigurations.
const RAW_BASE =
  (process.env.EXPO_PUBLIC_BACKEND_URL && process.env.EXPO_PUBLIC_BACKEND_URL.trim()) ||
  "https://vaulted-app.onrender.com";
const BASE = /^https?:\/\//i.test(RAW_BASE) ? RAW_BASE : `https://${RAW_BASE}`;
const TOKEN_KEY = "vaulted_token";

// Exposed so views that need to build full URLs for downloads
// (e.g. /admin letterhead download card) don't have to re-derive this.
export const API_BASE = BASE;

/**
 * Specialised Error subclass so UI code can distinguish auth failures
 * (session expired, missing admin role, invalid token) from everything
 * else without string-matching on error messages. Set on every non-2xx
 * response so screens can `if (e instanceof ApiError && e.status === 401)
 * // redirect to login`.
 */
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

/**
 * Optional global 401 handler. Screens that want to auto-redirect on
 * session expiry (e.g. /admin) register once at mount; the handler is
 * called with the ApiError whenever any api() call surfaces a 401 so
 * the screen can clear state, show a "session expired" toast, and
 * push the user back to /sign-in.
 *
 * Kept as module-level state (rather than a React context) so a 401 from
 * a utility fetch deep inside a hook can still trigger the redirect
 * without threading context down through every call site.
 */
type UnauthorizedHandler = (err: ApiError) => void;
let _onUnauthorized: UnauthorizedHandler | null = null;
export function registerUnauthorizedHandler(handler: UnauthorizedHandler | null) {
  _onUnauthorized = handler;
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
    const detail = (data && (data.detail || data.message)) || `Request failed (${res.status})`;
    const message = typeof detail === "string" ? detail : JSON.stringify(detail);
    const err = new ApiError(message, res.status);

    // 401 → session expired or missing token. Nuke the local token so
    // the next cold start lands on /sign-in instead of looping with a
    // stale JWT, then poke the global handler so the current screen can
    // react (redirect, toast, etc). We still throw so individual callers
    // that want their own fallback still get one.
    if (res.status === 401) {
      try { await setToken(null); } catch { /* non-fatal */ }
      if (_onUnauthorized) {
        try { _onUnauthorized(err); } catch { /* handler must not re-raise */ }
      }
    }
    throw err;
  }
  return data as T;
}
