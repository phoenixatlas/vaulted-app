import * as WebBrowser from "expo-web-browser";
import { Platform } from "react-native";
import { api } from "./api";

const RETURN_HOST_PATH = "/stripe-return";

function appReturnURL(): string {
  const base = process.env.EXPO_PUBLIC_BACKEND_URL || "";
  return `${base}${RETURN_HOST_PATH}`;
}

type CheckoutResult = {
  status: "success" | "cancel" | "dismiss" | "error";
  session_id?: string;
  error?: string;
};

async function openCheckout(checkoutUrl: string): Promise<CheckoutResult> {
  try {
    if (Platform.OS === "web") {
      // On web preview, openAuthSessionAsync isn't reliable; navigate the page directly.
      window.location.href = checkoutUrl;
      return { status: "dismiss" };
    }
    const res = await WebBrowser.openAuthSessionAsync(checkoutUrl, appReturnURL());
    if (res.type !== "success" || !res.url) return { status: res.type === "cancel" ? "cancel" : "dismiss" };
    const u = new URL(res.url);
    const status = u.searchParams.get("status") as "success" | "cancel" | null;
    const session_id = u.searchParams.get("session_id") || undefined;
    return { status: status === "success" ? "success" : "cancel", session_id };
  } catch (e: any) {
    return { status: "error", error: e?.message ?? "Unknown error" };
  }
}

export async function startDepositCheckout(amount_usd: number): Promise<CheckoutResult & { session_id?: string }> {
  const r = await api<{ checkout_url: string; session_id: string }>("/stripe/checkout/deposit", {
    method: "POST",
    body: { amount_usd },
  });
  const out = await openCheckout(r.checkout_url);
  return { ...out, session_id: out.session_id || r.session_id };
}

export type RemitFundBody = {
  source_fiat: string;
  amount: number;
  destination_code: string;
  recipient_address: string;
  recipient_name?: string | null;
  memo?: string | null;
  payment_method: "card" | "apple_pay" | "google_pay" | "bank";
};

export async function startRemitFundCheckout(body: RemitFundBody): Promise<CheckoutResult & { session_id?: string; charge_amount?: number; charge_currency?: string }> {
  const r = await api<{ checkout_url: string; session_id: string; charge_amount: number; charge_currency: string }>(
    "/remit/fund",
    { method: "POST", body },
  );
  const out = await openCheckout(r.checkout_url);
  return { ...out, session_id: out.session_id || r.session_id, charge_amount: r.charge_amount, charge_currency: r.charge_currency };
}

export async function startSubscriptionCheckout(): Promise<CheckoutResult & { session_id?: string }> {
  const r = await api<{ checkout_url: string; session_id: string }>("/stripe/checkout/subscription", {
    method: "POST",
  });
  const out = await openCheckout(r.checkout_url);
  return { ...out, session_id: out.session_id || r.session_id };
}

export async function syncStripeSession(session_id: string) {
  return api<{ applied: any; user: any; payment_status: string; session_status: string }>("/stripe/sync", {
    method: "POST",
    body: { session_id },
  });
}

export async function cancelSubscription() {
  return api<{ status: string }>("/stripe/cancel", { method: "POST" });
}
