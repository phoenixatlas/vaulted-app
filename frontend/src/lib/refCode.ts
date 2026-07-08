/**
 * Referral code capture + persistence utilities.
 *
 * Flow:
 *   1. User taps a `https://app.phoenix-atlas.com/?ref=CODE` link → hits the
 *      web preview or deep-links into the native app.
 *   2. `captureRefCodeFromUrl()` is called on `_layout.tsx` mount — it reads
 *      the URL query string (web) or the initial deep-link URL (native) and
 *      persists any `?ref=CODE` value to AsyncStorage.
 *   3. `getPendingRefCode()` is read by the register screen and passed to
 *      `auth.register()`, which POSTs it on `/auth/register`.
 *   4. `clearPendingRefCode()` is called after a successful register so the
 *      code doesn't leak into subsequent sign-ups on the same device.
 *
 * Design notes:
 *  - Code is uppercased + trimmed at capture time — matches backend
 *    normalisation.
 *  - Any code longer than 16 chars is discarded (defensive against a bad
 *    query string).
 */

import * as Linking from "expo-linking";
import { Platform } from "react-native";
import { storage } from "@/src/utils/storage";

const REF_CODE_KEY = "vaulted_pending_ref_code";

/** Uppercase + trim + length-cap. Empty strings return null. */
function normalise(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const trimmed = raw.trim().toUpperCase();
  if (!trimmed) return null;
  if (trimmed.length > 16) return null;
  // Alphanumeric only — reject query-string weirdness
  if (!/^[A-Z0-9]+$/.test(trimmed)) return null;
  return trimmed;
}

/** Parse `?ref=CODE` (or `&ref=CODE`) out of a full URL. */
function parseRefFromUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = Linking.parse(url);
    const q = parsed.queryParams || {};
    const raw =
      (typeof q.ref === "string" && q.ref) ||
      (Array.isArray(q.ref) && q.ref[0]) ||
      null;
    return normalise(raw as string | null);
  } catch {
    return null;
  }
}

/**
 * Called once at app mount (from _layout.tsx). Reads the initial URL —
 * on web this is `window.location.href`, on native it's the deep-link
 * URL that opened the app (if any). Persists any `?ref=CODE` found.
 */
export async function captureRefCodeFromUrl(): Promise<string | null> {
  try {
    let initialUrl: string | null = null;
    if (Platform.OS === "web") {
      // On web we can just read location directly
      initialUrl = typeof window !== "undefined" ? window.location.href : null;
    } else {
      initialUrl = await Linking.getInitialURL();
    }
    const code = parseRefFromUrl(initialUrl);
    if (code) {
      await storage.setItem(REF_CODE_KEY, code);
      return code;
    }
    return null;
  } catch {
    return null;
  }
}

/** Read the currently-persisted pending referral code (if any). */
export async function getPendingRefCode(): Promise<string | null> {
  return storage.getItem<string>(REF_CODE_KEY, "");
}

/** Clear the persisted code after a successful register. */
export async function clearPendingRefCode(): Promise<void> {
  await storage.removeItem(REF_CODE_KEY);
}
