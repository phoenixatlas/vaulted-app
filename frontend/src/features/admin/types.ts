/**
 * Admin Dashboard — Shared Types
 * ================================
 * Centralises every response/body shape used by the admin cards.
 * Keeping these together makes it easy to see what the backend
 * contract is and to update all cards when a route evolves.
 */

export type Probe = {
  ok: boolean;
  detail?: string;
  error_code?: number;
  service?: string;
  integrator_enabled?: boolean;
  status_code?: number;
};

export type KotaniHealth = {
  diagnostic: {
    mode: "live" | "mock";
    base_url: string;
    api_key_configured: boolean;
    webhook_secret_configured: boolean;
    mock_override_env: boolean;
  };
  overall_ready: boolean;
  probes: {
    health: Probe;
    rate_quote: Probe;
    customer_create: Probe;
  };
  history: { checked_at: string; overall_ready: boolean }[];
  checked_at: string;
};

export type WaitlistStats = {
  total: number;
  by_corridor: Record<string, number>;
  breakdown: { corridor: string; corridor_name: string; count: number }[];
  corridors: Record<string, string>;
  by_direction?: { outbound: number; inbound: number };
  matrix?: { corridor: string; corridor_name: string; direction: string; count: number }[];
};

export type InvestorLead = {
  email: string;
  name?: string;
  company?: string;
  role?: string;
  note?: string;
  first_seen_at?: string;
  last_seen_at?: string;
  downloads?: number;
};

export type InvestorLeadsResp = {
  total: number;
  total_repeat_visitors: number;
  top_companies: { company: string; count: number }[];
  leads: InvestorLead[];
};

export type DailySignupsResp = {
  days: number;
  series: { date: string; outbound: number; inbound: number; total: number }[];
  totals: {
    signups: number;
    outbound: number;
    inbound: number;
    peak_day: string | null;
    peak_count: number;
    average_per_day: number;
  };
};

export type ReferralsResp = {
  leaders: {
    email_redacted: string;
    email_hash: string;
    referral_count: number;
    corridor?: string;
    founding_member: boolean;
  }[];
  totals: {
    total_referred_signups: number;
    founding_members: number;
    boost_interval: number;
    boost_spots: number;
    founding_threshold: number;
  };
};

export type BookClicksResp = {
  total: number;
  by_source: { source: string; count: number }[];
  recent: { source: string; created_at?: string; ref?: string }[];
  booking_url: string;
};

export type WebhookDelivery = {
  received_at: string;
  signature_present: boolean;
  signature_valid: boolean;
  event_header?: string | null;
  integrator_header?: string | null;
  raw_body?: string;
};

export type SmokeStep = {
  name: string;
  call: string;
  ok: boolean;
  ms: number;
  detail?: any;
  error?: string | null;
};

export type SmokeTestResp = {
  corridor: string;
  verdict: "all_green" | "partial" | "all_failed";
  passed: number;
  total: number;
  elapsed_ms: number;
  steps: SmokeStep[];
  started_at: string;
};

export type SettlementDay = {
  date: string;
  tx_count: number;
  crypto_sent: Record<string, number>;
  fiat_delivered: Record<string, number>;
  usd_equivalent: number;
  corridors: Record<string, number>;
  reconciliation: {
    currency: string;
    quoted: number;
    settled: number;
    delta: number;
    delta_pct: number;
  }[];
  sample_tx_ids: string[];
};

export type SettlementsResp = {
  window_days: number;
  since: string;
  overall: {
    tx_count: number;
    crypto_sent: Record<string, number>;
    fiat_delivered: Record<string, number>;
    usd_equivalent: number;
    corridor_breakdown: Record<string, number>;
  };
  daily: SettlementDay[];
};

export type Contact = {
  id: string;
  bank_short: string;
  bank_name?: string;
  name: string;
  title?: string | null;
  email: string;
  notes?: string | null;
  is_primary: boolean;
  last_used_at?: string | null;
};

export type ContactsResp = {
  total: number;
  by_bank: Record<string, Contact[]>;
  contacts: Contact[];
};

export type UseCaseSendRow = {
  send_id: string;
  resend_id?: string | null;
  status: string;
  recipient_email: string;
  recipient_name?: string;
  recipient_title?: string | null;
  bank_short: string;
  bank_name?: string;
  subject: string;
  sent_at?: string | null;
  attempted_at?: string;
  delivered_at?: string | null;
  opened_at?: string | null;
  clicked_at?: string | null;
  error?: string | null;
  sent_by?: string | null;
  cover_note_present?: boolean;
};

export type UseCaseSendsResp = {
  total: number;
  sent_count: number;
  delivered_count: number;
  opened_count: number;
  rows: UseCaseSendRow[];
};

export type KotaniWebhookEchoResp = {
  expected_webhook_url: string | null;
  host_type: "unset" | "preview" | "render" | "localhost" | "custom";
  host_label: string;
  host_warning: string | null;
  diagnostic: KotaniHealth["diagnostic"];
  config_checklist: {
    webhook_url_registered: boolean;
    signature_valid_count: number;
    signature_invalid_count: number;
    webhook_secret_configured: boolean;
    api_key_configured: boolean;
    mode: string;
  };
  recommended_events: string[];
  total_received: number;
  deliveries: WebhookDelivery[];
  setup_hint: string;
};

// Country-code → flag emoji. Kept in sync with the landing dropdown so
// the admin dashboard reads the same as the acquisition surface.
export const CORRIDOR_FLAGS: Record<string, string> = {
  KE: "🇰🇪", GH: "🇬🇭", NG: "🇳🇬", UG: "🇺🇬",
  TZ: "🇹🇿", ZM: "🇿🇲", ZA: "🇿🇦", XX: "🌐",
};
