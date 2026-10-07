/**
 * Admin — Dashboard index
 * =======================
 * Route: /admin
 *
 * Landing surface for operator tools. Currently shows:
 *   - Kotani Pay sandbox health card (mode, per-service probes, refresh)
 *   - Quick link to /admin/kyc-override for manual EDD approvals
 *
 * Only accessible to users whose email is in the backend's ADMIN_EMAILS
 * env var. Backend enforces via require_admin — this screen is UI only.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  View, Text, Pressable, StyleSheet, ScrollView,
  ActivityIndicator, RefreshControl, Linking, Platform, TextInput,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { api, API_BASE, ApiError, registerUnauthorizedHandler } from "@/src/lib/api";
import { AdminBiometricGate, AdminBiometricNudge, adminBiometric } from "@/src/components/AdminBiometricGate";
import { colors, spacing, radius } from "@/src/lib/theme";
import { DailySignupChart, CorridorMatrixHeatmap, ReferralLeaderboard } from "@/src/components/AdminCharts";

type Probe = {
  ok: boolean;
  detail?: string;
  error_code?: number;
  service?: string;
  integrator_enabled?: boolean;
  status_code?: number;
};

type KotaniHealth = {
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

type WaitlistStats = {
  total: number;
  by_corridor: Record<string, number>;
  breakdown: { corridor: string; corridor_name: string; count: number }[];
  corridors: Record<string, string>;
  by_direction?: { outbound: number; inbound: number };
  matrix?: { corridor: string; corridor_name: string; direction: string; count: number }[];
};

type InvestorLead = {
  email: string;
  name?: string;
  company?: string;
  role?: string;
  note?: string;
  first_seen_at?: string;
  last_seen_at?: string;
  downloads?: number;
};

type InvestorLeadsResp = {
  total: number;
  total_repeat_visitors: number;
  top_companies: { company: string; count: number }[];
  leads: InvestorLead[];
};

type DailySignupsResp = {
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

type ReferralsResp = {
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

type BookClicksResp = {
  total: number;
  by_source: { source: string; count: number }[];
  recent: { source: string; created_at?: string; ref?: string }[];
  booking_url: string;
};

type WebhookDelivery = {
  received_at: string;
  signature_present: boolean;
  signature_valid: boolean;
  event_header?: string | null;
  integrator_header?: string | null;
  raw_body?: string;
};

type SmokeStep = {
  name: string;
  call: string;
  ok: boolean;
  ms: number;
  detail?: any;
  error?: string | null;
};

type SmokeTestResp = {
  corridor: string;
  verdict: "all_green" | "partial" | "all_failed";
  passed: number;
  total: number;
  elapsed_ms: number;
  steps: SmokeStep[];
  started_at: string;
};

type SettlementDay = {
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

type SettlementsResp = {
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

type Contact = {
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
type ContactsResp = {
  total: number;
  by_bank: Record<string, Contact[]>;
  contacts: Contact[];
};

type UseCaseSendRow = {
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

type UseCaseSendsResp = {
  total: number;
  sent_count: number;
  delivered_count: number;
  opened_count: number;
  rows: UseCaseSendRow[];
};

type KotaniWebhookEchoResp = {
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

// Country-code → flag emoji. Kept in sync with the landing dropdown so the
// admin dashboard reads the same as the acquisition surface.
const CORRIDOR_FLAGS: Record<string, string> = {
  KE: "🇰🇪", GH: "🇬🇭", NG: "🇳🇬", UG: "🇺🇬",
  TZ: "🇹🇿", ZM: "🇿🇲", ZA: "🇿🇦", XX: "🌐",
};

export default function AdminHome() {
  // Wrap the real admin UI behind a biometric gate (opt-in, per-device).
  // The gate is a no-op on web and on devices without biometric hardware,
  // so this doesn't lock desktop operators out of the dashboard.
  return (
    <AdminBiometricGate>
      <AdminHomeInner />
    </AdminBiometricGate>
  );
}

function AdminHomeInner() {
  const router = useRouter();
  const [health, setHealth] = useState<KotaniHealth | null>(null);
  const [waitlist, setWaitlist] = useState<WaitlistStats | null>(null);
  const [investors, setInvestors] = useState<InvestorLeadsResp | null>(null);
  const [dailySignups, setDailySignups] = useState<DailySignupsResp | null>(null);
  const [referrals, setReferrals] = useState<ReferralsResp | null>(null);
  const [bookClicks, setBookClicks] = useState<BookClicksResp | null>(null);
  const [webhookEcho, setWebhookEcho] = useState<KotaniWebhookEchoResp | null>(null);
  const [replayStatus, setReplayStatus] = useState<string | null>(null);
  const [smokeResult, setSmokeResult] = useState<SmokeTestResp | null>(null);
  const [smokeRunning, setSmokeRunning] = useState(false);
  const [smokeCorridor, setSmokeCorridor] = useState<string>("KE");
  const [settlements, setSettlements] = useState<SettlementsResp | null>(null);
  const [useCaseSends, setUseCaseSends] = useState<UseCaseSendsResp | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // Set to true when ANY admin endpoint returns 401 — flips the whole
  // screen into a "session expired" state so the operator sees ONE clear
  // "sign in again" prompt instead of 9 cards each saying "Not
  // authenticated". Reset on successful load after re-login.
  const [sessionExpired, setSessionExpired] = useState(false);

  // Register a global 401 handler so even side-effect fetches (replay
  // webhook, run smoke test, send use case) trigger the session-expired
  // state. Deregister on unmount so a stale handler can't fire for a
  // different screen's requests.
  useEffect(() => {
    registerUnauthorizedHandler(() => setSessionExpired(true));
    return () => registerUnauthorizedHandler(null);
  }, []);

  // Per-endpoint error strings — surfaced in each card's "Unavailable"
  // state so operators can actually see which call failed and why
  // (403 → not in ADMIN_EMAILS; 404 → endpoint missing on this deploy;
  //  500 → server-side bug; network error → CORS / timeout).
  const [cardErrors, setCardErrors] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    // Switch into a loading state so skeleton rows + button spinners
    // can render immediately. Previously load() silently refetched —
    // taps on "Re-probe" / "Pull-to-refresh" felt dead even though the
    // request was firing. We keep `refreshing` under the caller's
    // control so pull-to-refresh keeps its native indicator.
    setLoading(true);
    setErr(null);
    const errors: Record<string, string> = {};
    let any401 = false;
    // Collect each endpoint's error separately so we can tag it on the
    // card instead of showing a generic "Unavailable" message. Also
    // detect 401s via the ApiError.status field so we can flip the
    // whole screen into "session expired" mode rather than making the
    // operator read nine identical error strings.
    const grab = async <T,>(key: string, path: string): Promise<T | null> => {
      try {
        return await api<T>(path);
      } catch (e: any) {
        if (e instanceof ApiError && e.status === 401) {
          any401 = true;
        }
        errors[key] = e?.message ? String(e.message) : "Request failed";
        return null;
      }
    };
    // Every call now runs independently via grab() — a failure on any
    // single endpoint only marks that card as unavailable instead of
    // nuking the entire dashboard. Previously /admin/kotani/health was
    // special-cased with `catch (e) => { throw e; }` which rejected the
    // whole Promise.all whenever Kotani returned "Not authenticated",
    // leaving the other 5 cards with an empty errorMsg.
    const [h, w, inv, daily, refs, clicks, echo, settle, sends] = await Promise.all([
      grab<KotaniHealth>("kotani", "/admin/kotani/health"),
      grab<WaitlistStats>("waitlist", "/admin/waitlist/stats"),
      grab<InvestorLeadsResp>("investors", "/admin/investor/leads"),
      grab<DailySignupsResp>("daily", "/admin/waitlist/analytics/daily-signups?days=30"),
      grab<ReferralsResp>("referrals", "/admin/waitlist/analytics/referrals?limit=10"),
      grab<BookClicksResp>("bookClicks", "/admin/investor/book-clicks"),
      grab<KotaniWebhookEchoResp>("webhookEcho", "/admin/kotani/webhook-echo"),
      grab<SettlementsResp>("settlements", "/admin/kotani/settlements?days=30"),
      grab<UseCaseSendsResp>("usecaseSends", "/admin/usecase/sends?limit=20"),
    ]);
    setHealth(h);
    setWaitlist(w);
    setInvestors(inv);
    setDailySignups(daily);
    setReferrals(refs);
    setBookClicks(clicks);
    setWebhookEcho(echo);
    setSettlements(settle);
    setUseCaseSends(sends);
    setCardErrors(errors);
    // If anything returned 401, pivot the whole screen to session-expired
    // mode and stop here — no point showing nine identical error cards.
    if (any401) {
      setSessionExpired(true);
      setLoading(false);
      setRefreshing(false);
      return;
    }
    setSessionExpired(false);
    // Full-page banner only when EVERY card failed — avoids drowning
    // out individual card errors.
    const allFailed =
      !h && !w && !inv && !daily && !refs && !clicks && !echo && !settle && !sends &&
      Object.keys(errors).length >= 9;
    if (allFailed) {
      const first = errors.kotani || errors.waitlist || Object.values(errors)[0] || "Unknown error";
      setErr(first.includes("403") || first.toLowerCase().includes("admin")
        ? "Admin access required — ensure your account is in ADMIN_EMAILS on the backend."
        : first);
    }
    setLoading(false);
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    load();
  }, [load]);

  const onReplayWebhook = useCallback(async () => {
    setReplayStatus("Sending synthetic webhook…");
    try {
      const res = await api<{ status_code: number; response: any }>(
        "/admin/kotani/webhook-echo/replay",
        { method: "POST", body: {} }
      );
      setReplayStatus(
        res.status_code === 200
          ? `✓ Dispatcher returned 200 (bucket=${res.response?.bucket || "n/a"})`
          : `✗ Dispatcher returned ${res.status_code}`
      );
      // Refresh the echo card so the new delivery appears in the list.
      setTimeout(() => load(), 400);
    } catch (e: any) {
      setReplayStatus(`✗ ${e?.message || "Replay failed"}`);
    }
  }, [load]);

  const onRunSmokeTest = useCallback(async (corridor: string) => {
    setSmokeRunning(true);
    setSmokeCorridor(corridor);
    setSmokeResult(null);
    try {
      const res = await api<SmokeTestResp>(
        `/admin/kotani/smoke-test?corridor=${encodeURIComponent(corridor)}`,
        { method: "POST", body: {} }
      );
      setSmokeResult(res);
    } catch (e: any) {
      setSmokeResult({
        corridor,
        verdict: "all_failed",
        passed: 0,
        total: 0,
        elapsed_ms: 0,
        steps: [{ name: "Request failed", call: "N/A", ok: false, ms: 0, error: e?.message || "Unknown error" }],
        started_at: new Date().toISOString(),
      });
    } finally {
      setSmokeRunning(false);
    }
  }, []);

  return (
    <SafeAreaView style={s.container} edges={["top", "bottom"]}>
      {/* Header */}
      <View style={s.header}>
        <Pressable onPress={() => router.back()} style={s.backBtn} hitSlop={8}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <View style={{ flex: 1 }}>
          <Text style={s.headerTitle}>Admin</Text>
          <Text style={s.headerSub}>Operator tools & health probes</Text>
        </View>
      </View>

      {sessionExpired ? (
        /* Full-screen takeover when every call returned 401. Clearer
         * than nine identical "Not authenticated" cards, and gives the
         * operator a single primary action. */
        <View style={s.expiredWrap}>
          <View style={s.expiredCard}>
            <View style={s.expiredIcon}>
              <Ionicons name="lock-closed" size={28} color={colors.brand} />
            </View>
            <Text style={s.expiredTitle}>Session expired</Text>
            <Text style={s.expiredBody}>
              Your sign-in has timed out. Admin endpoints need a fresh
              authentication token. Please sign in again — nothing has
              changed on the backend, and all your Kotani / Resend
              settings are safe.
            </Text>
            <Pressable
              onPress={() => router.replace({
                pathname: "/(auth)/login",
                params: { returnTo: "/admin" },
              } as any)}
              style={s.expiredBtn}
            >
              <Ionicons name="log-in-outline" size={16} color={colors.onBrand} />
              <Text style={s.expiredBtnText}>Sign in again</Text>
            </Pressable>
            <Pressable
              onPress={() => {
                setSessionExpired(false);
                setLoading(true);
                load();
              }}
              hitSlop={8}
              style={{ marginTop: 10 }}
            >
              <Text style={s.expiredRetry}>Retry without signing in</Text>
            </Pressable>
          </View>
        </View>
      ) : (

      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={s.scrollContent}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brand} />}
      >
        <AdminBiometricNudge />
        {/* Kotani health card */}
        <View style={s.card}>
          <View style={s.cardHeaderRow}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
              <Ionicons name="pulse" size={18} color={colors.brand} />
              <Text style={s.cardTitle}>Kotani Pay · Sandbox</Text>
            </View>
            {health && (
              <View style={[
                s.modePill,
                health.overall_ready ? s.modePillReady : health.diagnostic.mode === "live" ? s.modePillLive : s.modePillMock,
              ]}>
                <Text style={s.modePillText}>
                  {health.overall_ready ? "READY" : health.diagnostic.mode.toUpperCase()}
                </Text>
              </View>
            )}
          </View>

          {loading ? (
            <View style={s.loadingBox}>
              <ActivityIndicator color={colors.brand} />
              <Text style={s.loadingText}>Probing Kotani sandbox…</Text>
            </View>
          ) : (cardErrors.kotani && !health) ? (
            <View style={s.errorBox}>
              <Ionicons name="alert-circle-outline" size={18} color={colors.error} />
              <Text style={s.errorText}>{cardErrors.kotani}</Text>
            </View>
          ) : err ? (
            <View style={s.errorBox}>
              <Ionicons name="alert-circle-outline" size={18} color={colors.error} />
              <Text style={s.errorText}>{err}</Text>
            </View>
          ) : health ? (
            <>
              {/* Config summary */}
              <View style={s.diagRow}>
                <Text style={s.diagLabel}>Base URL</Text>
                <Text style={s.diagValue} numberOfLines={1}>{health.diagnostic.base_url}</Text>
              </View>
              <View style={s.diagRow}>
                <Text style={s.diagLabel}>API key</Text>
                <Text style={[s.diagValue, health.diagnostic.api_key_configured ? s.diagValueOk : s.diagValueMissing]}>
                  {health.diagnostic.api_key_configured ? "configured" : "missing"}
                </Text>
              </View>
              <View style={s.diagRow}>
                <Text style={s.diagLabel}>Webhook secret</Text>
                <Text style={[s.diagValue, health.diagnostic.webhook_secret_configured ? s.diagValueOk : s.diagValueMissing]}>
                  {health.diagnostic.webhook_secret_configured ? "configured" : "missing"}
                </Text>
              </View>

              <View style={s.divider} />

              {/* Per-service probes */}
              <Text style={s.probesHeader}>Service probes</Text>
              <ProbeRow name="Health check" endpoint="GET /health" probe={health.probes.health} />
              <ProbeRow name="Rate quote" endpoint="POST /api/v3/rate/offramp" probe={health.probes.rate_quote} />
              <ProbeRow
                name="Customer create"
                endpoint="POST /api/v3/customer/mobile-money"
                probe={health.probes.customer_create}
                showsIntegratorFlag
              />

              {/* Kotani-side blocker call-out (only when the specific 403 shows) */}
              {!health.probes.customer_create.ok && health.probes.customer_create.service === "mobile_money_customers" && (
                <View style={s.blockerBox}>
                  <View style={{ flexDirection: "row", alignItems: "flex-start", gap: 6 }}>
                    <Ionicons name="lock-closed" size={14} color={colors.brandDeep} style={{ marginTop: 2 }} />
                    <Text style={s.blockerText}>
                      Waiting on Kotani support to flip <Text style={s.mono}>integratorEnabled</Text> to true for{" "}
                      <Text style={s.mono}>{health.probes.customer_create.service}</Text>. Pull-to-refresh this
                      screen after they confirm and the READY badge will appear automatically.
                    </Text>
                  </View>
                </View>
              )}

              {/* Last checked + refresh */}
              <View style={s.footerRow}>
                <Text style={s.footerText}>
                  {loading
                    ? "Re-probing…"
                    : `Last checked · ${new Date(health.checked_at).toLocaleString()}`}
                </Text>
                <Pressable
                  onPress={() => load()}
                  disabled={loading}
                  style={[s.refreshBtn, loading && { opacity: 0.6 }]}
                  hitSlop={10}
                >
                  {loading ? (
                    <ActivityIndicator size="small" color={colors.brand} />
                  ) : (
                    <Ionicons name="refresh" size={14} color={colors.brand} />
                  )}
                  <Text style={s.refreshBtnText}>
                    {loading ? "Probing…" : "Re-probe"}
                  </Text>
                </Pressable>
              </View>
            </>
          ) : null}
        </View>

        {/* Waitlist stats card */}
        <WaitlistCard stats={waitlist} loading={loading} errorMsg={cardErrors.waitlist} />

        {/* Kotani webhook echo + setup checklist */}
        <KotaniWebhookEchoCard
          data={webhookEcho}
          loading={loading}
          errorMsg={cardErrors.webhookEcho}
          onReplay={onReplayWebhook}
          replayStatus={replayStatus}
        />

        {/* Kotani end-to-end smoke test */}
        <KotaniSmokeTestCard
          result={smokeResult}
          running={smokeRunning}
          corridor={smokeCorridor}
          onRun={onRunSmokeTest}
        />

        {/* Live settlement rollup (per-day) */}
        <KotaniSettlementsCard
          data={settlements}
          loading={loading}
          errorMsg={cardErrors.settlements}
        />

        {/* Daily signup trend card */}
        <DailySignupsCard data={dailySignups} loading={loading} errorMsg={cardErrors.daily} />

        {/* Corridor × direction matrix card */}
        <CorridorMatrixCard stats={waitlist} loading={loading} errorMsg={cardErrors.waitlist} />

        {/* Referral leaderboard card */}
        <ReferralLeaderboardCard data={referrals} loading={loading} errorMsg={cardErrors.referrals} />

        {/* Investor leads card */}
        <InvestorLeadsCard data={investors} loading={loading} errorMsg={cardErrors.investors} />

        {/* Book-a-call attribution card */}
        <BookClicksCard data={bookClicks} loading={loading} errorMsg={cardErrors.bookClicks} />

        {/* Reusable letterhead template downloads */}
        <View style={s.card}>
          <Text style={s.cardTitle}>Company letterhead</Text>
          <Text style={s.subtle}>
            Download your branded Phoenix-Atlas / Vaulted letterhead. The DOCX
            is editable in Word Online — drop it in OneDrive and the gold
            header + Companies House footer repeat on every page you add.
          </Text>
          <Pressable
            style={s.toolRow}
            onPress={() => {
              const url = `${API_BASE}/api/letterhead.docx`;
              if (Platform.OS === "web") {
                window.open(url, "_blank");
              } else {
                Linking.openURL(url).catch(() => {});
              }
            }}
          >
            <Ionicons name="document-text-outline" size={18} color={colors.brand} />
            <View style={{ flex: 1 }}>
              <Text style={s.toolTitle}>Editable Word template (.docx)</Text>
              <Text style={s.toolSub}>Save to OneDrive · type over the placeholders</Text>
            </View>
            <Ionicons name="download-outline" size={16} color={colors.onSurfaceTertiary} />
          </Pressable>
          <Pressable
            style={s.toolRow}
            onPress={() => {
              const url = `${API_BASE}/api/letterhead.pdf`;
              if (Platform.OS === "web") {
                window.open(url, "_blank");
              } else {
                Linking.openURL(url).catch(() => {});
              }
            }}
          >
            <Ionicons name="document-outline" size={18} color={colors.brand} />
            <View style={{ flex: 1 }}>
              <Text style={s.toolTitle}>Print-ready A4 PDF</Text>
              <Text style={s.toolSub}>Overlay in Pages/Word or print and sign</Text>
            </View>
            <Ionicons name="download-outline" size={16} color={colors.onSurfaceTertiary} />
          </Pressable>
        </View>

        {/* Partner / investor use case downloads + one-click dispatcher */}
        <PartnerUseCaseCard
          sendsData={useCaseSends}
          loading={loading}
          errorMsg={cardErrors.usecaseSends}
          onSent={() => load()}
        />

        {/* Quick links */}
        <View style={s.card}>
          <Text style={s.cardTitle}>Tools</Text>
          <Pressable
            style={s.toolRow}
            onPress={() => router.push("/admin/kyc-override")}
          >
            <Ionicons name="shield-checkmark-outline" size={18} color={colors.brand} />
            <View style={{ flex: 1 }}>
              <Text style={s.toolTitle}>Manual EDD approval</Text>
              <Text style={s.toolSub}>Upgrade a user{"\u2019"}s KYC tier with documented evidence</Text>
            </View>
            <Ionicons name="chevron-forward" size={16} color={colors.onSurfaceTertiary} />
          </Pressable>
          <Pressable
            style={s.toolRow}
            onPress={async () => {
              const on = await adminBiometric.isEnabled();
              if (on) {
                await adminBiometric.disable();
              } else {
                await adminBiometric.enable();
              }
              // Nudge the user to re-open the screen so the gate state
              // picks up on next mount.
              router.replace("/admin" as any);
            }}
          >
            <Ionicons name="finger-print" size={18} color={colors.brand} />
            <View style={{ flex: 1 }}>
              <Text style={s.toolTitle}>Biometric lock</Text>
              <Text style={s.toolSub}>
                Toggle Face ID / Touch ID gate for this device (web unaffected).
              </Text>
            </View>
            <Ionicons name="chevron-forward" size={16} color={colors.onSurfaceTertiary} />
          </Pressable>
        </View>
      </ScrollView>
      )}
    </SafeAreaView>
  );
}

function ProbeRow({
  name, endpoint, probe, showsIntegratorFlag,
}: {
  name: string;
  endpoint: string;
  probe: Probe;
  showsIntegratorFlag?: boolean;
}) {
  return (
    <View style={s.probeRow}>
      <View style={{ flex: 1 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 2 }}>
          <Ionicons
            name={probe.ok ? "checkmark-circle" : "close-circle"}
            size={14}
            color={probe.ok ? colors.success : colors.error}
          />
          <Text style={s.probeName}>{name}</Text>
        </View>
        <Text style={s.probeEndpoint}>{endpoint}</Text>
        <Text style={[s.probeDetail, !probe.ok && s.probeDetailFail]} numberOfLines={3}>
          {probe.detail || (probe.ok ? "ok" : "failed")}
        </Text>
        {showsIntegratorFlag && !probe.ok && probe.error_code === 403 && (
          <View style={{ flexDirection: "row", gap: 6, marginTop: 4, flexWrap: "wrap" }}>
            <Chip label={`service: ${probe.service}`} />
            <Chip label={`integratorEnabled: ${probe.integrator_enabled ? "true" : "false"}`} bad={!probe.integrator_enabled} />
          </View>
        )}
      </View>
    </View>
  );
}

function Chip({ label, bad }: { label: string; bad?: boolean }) {
  return (
    <View style={[s.chip, bad && s.chipBad]}>
      <Text style={[s.chipText, bad && s.chipTextBad]}>{label}</Text>
    </View>
  );
}

// WaitlistCard — corridor breakdown of the marketing waitlist. Renders a
// "how many joined and where do they want to send to" glanceable summary.
// Bars are relative to the largest corridor so a small waitlist still fills
// the card visually. Empty state is friendly (no signups yet).
function WaitlistCard({
  stats, loading, errorMsg,
}: {
  stats: WaitlistStats | null;
  loading: boolean;
  errorMsg?: string;
}) {
  if (loading && !stats) {
    return (
      <View style={s.card}>
        <View style={s.cardHeaderRow}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <Ionicons name="people-outline" size={18} color={colors.brand} />
            <Text style={s.cardTitle}>Waitlist</Text>
          </View>
        </View>
        <View style={s.loadingBox}>
          <ActivityIndicator color={colors.brand} />
          <Text style={s.loadingText}>Loading signups…</Text>
        </View>
      </View>
    );
  }
  if (!stats) {
    return (
      <View style={s.card}>
        <View style={s.cardHeaderRow}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <Ionicons name="people-outline" size={18} color={colors.brand} />
            <Text style={s.cardTitle}>Waitlist</Text>
          </View>
        </View>
        <Text style={s.subtle}>
          Unavailable. {errorMsg ? `(${errorMsg})` : "Endpoint returned an error."}
        </Text>
      </View>
    );
  }

  // Sort by count descending, then alphabetically for stability.
  const rows = [...stats.breakdown].sort((a, b) => {
    if (b.count !== a.count) return b.count - a.count;
    return a.corridor.localeCompare(b.corridor);
  });
  const maxCount = rows[0]?.count || 1;

  return (
    <View style={s.card}>
      <View style={s.cardHeaderRow}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Ionicons name="people-outline" size={18} color={colors.brand} />
          <Text style={s.cardTitle}>Waitlist</Text>
        </View>
        <View style={s.totalPill}>
          <Text style={s.totalPillText}>{stats.total} total</Text>
        </View>
      </View>

      {stats.total === 0 ? (
        <View style={s.emptyBox}>
          <Ionicons name="sparkles-outline" size={24} color={colors.onSurfaceTertiary} />
          <Text style={s.emptyText}>No signups yet. Share the landing to fill this up.</Text>
        </View>
      ) : (
        <View style={{ gap: 8 }}>
          {rows.map((row) => (
            <CorridorBar
              key={row.corridor}
              code={row.corridor}
              name={row.corridor_name}
              count={row.count}
              max={maxCount}
              total={stats.total}
            />
          ))}
        </View>
      )}
    </View>
  );
}

function CorridorBar({
  code, name, count, max, total,
}: {
  code: string;
  name: string;
  count: number;
  max: number;
  total: number;
}) {
  const pct = max > 0 ? (count / max) * 100 : 0;
  const shareOfTotal = total > 0 ? (count / total) * 100 : 0;
  const flag = CORRIDOR_FLAGS[code] || "🌐";
  return (
    <View>
      <View style={s.corridorRow}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6, flexShrink: 1 }}>
          <Text style={s.corridorFlag}>{flag}</Text>
          <Text style={s.corridorName} numberOfLines={1}>{name}</Text>
          <Text style={s.corridorCode}>{code}</Text>
        </View>
        <View style={{ flexDirection: "row", alignItems: "baseline", gap: 6 }}>
          <Text style={s.corridorCount}>{count}</Text>
          <Text style={s.corridorPct}>· {shareOfTotal.toFixed(0)}%</Text>
        </View>
      </View>
      <View style={s.barTrack}>
        <View style={[s.barFill, { width: `${Math.max(4, pct)}%` }]} />
      </View>
    </View>
  );
}

// InvestorLeadsCard — captured leads from the "Get the one-pager" form on
// the landing page. Shows total, repeat visitors (2+ downloads), top

// DailySignupsCard — Line chart of daily waitlist signups over the last 30 days.
// Includes totals summary + peak day.
function DailySignupsCard({
  data,
  loading,
  errorMsg,
}: {
  data: DailySignupsResp | null;
  loading: boolean;
  errorMsg?: string;
}) {
  if (loading && !data) {
    return (
      <View style={s.card}>
        <Text style={s.cardTitle}>Daily signups</Text>
        <Text style={s.subtle}>Loading…</Text>
      </View>
    );
  }
  if (!data) {
    return (
      <View style={s.card}>
        <Text style={s.cardTitle}>Daily signups</Text>
        <Text style={s.subtle}>
          Unavailable. {errorMsg ? `(${errorMsg})` : "Endpoint returned an error."}
        </Text>
      </View>
    );
  }
  const { series, totals } = data;
  const peakLabel = totals.peak_day
    ? new Date(totals.peak_day).toLocaleDateString(undefined, { month: "short", day: "numeric" })
    : "—";
  return (
    <View style={s.card}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
        <Text style={s.cardTitle}>Daily signups</Text>
        <View style={s.pill}>
          <Text style={s.pillText}>Last {data.days} days</Text>
        </View>
      </View>
      <Text style={s.subtle}>Waitlist signups per day, split by direction. Inbound = Africa &rarr; UK/EU.</Text>

      {/* Summary row */}
      <View style={s.miniStatsRow}>
        <View style={s.miniStat}>
          <Text style={s.miniStatNum}>{totals.signups}</Text>
          <Text style={s.miniStatLabel}>total</Text>
        </View>
        <View style={s.miniStat}>
          <Text style={s.miniStatNum}>{totals.average_per_day}</Text>
          <Text style={s.miniStatLabel}>/day avg</Text>
        </View>
        <View style={s.miniStat}>
          <Text style={s.miniStatNum}>{totals.peak_count}</Text>
          <Text style={s.miniStatLabel}>peak · {peakLabel}</Text>
        </View>
      </View>

      <View style={{ alignItems: "center", marginTop: spacing.md }}>
        <DailySignupChart series={series} height={160} width={320} />
      </View>
    </View>
  );
}

// CorridorMatrixCard — Heatmap-style breakdown of corridor × direction.
function CorridorMatrixCard({
  stats,
  loading,
  errorMsg,
}: {
  stats: WaitlistStats | null;
  loading: boolean;
  errorMsg?: string;
}) {
  if (loading && !stats) {
    return (
      <View style={s.card}>
        <Text style={s.cardTitle}>Corridor breakdown</Text>
        <Text style={s.subtle}>Loading…</Text>
      </View>
    );
  }
  if (!stats || !stats.matrix) {
    return (
      <View style={s.card}>
        <Text style={s.cardTitle}>Corridor breakdown</Text>
        <Text style={s.subtle}>
          {errorMsg ? `Unavailable. (${errorMsg})` : "No data yet."}
        </Text>
      </View>
    );
  }
  return (
    <View style={s.card}>
      <Text style={s.cardTitle}>Corridor breakdown</Text>
      <Text style={s.subtle}>
        Signups per corridor per direction. Darker cell = more demand. Ideal for investor calls to show live corridor pull.
      </Text>
      <View style={{ marginTop: spacing.md }}>
        <CorridorMatrixHeatmap matrix={stats.matrix} corridors={stats.corridors} />
      </View>
    </View>
  );
}

// ReferralLeaderboardCard — Top referrers + Founding Members count.
function ReferralLeaderboardCard({
  data,
  loading,
  errorMsg,
}: {
  data: ReferralsResp | null;
  loading: boolean;
  errorMsg?: string;
}) {
  if (loading && !data) {
    return (
      <View style={s.card}>
        <Text style={s.cardTitle}>Referral leaderboard</Text>
        <Text style={s.subtle}>Loading…</Text>
      </View>
    );
  }
  if (!data) {
    return (
      <View style={s.card}>
        <Text style={s.cardTitle}>Referral leaderboard</Text>
        <Text style={s.subtle}>
          Unavailable. {errorMsg ? `(${errorMsg})` : "Endpoint returned an error."}
        </Text>
      </View>
    );
  }
  return (
    <View style={s.card}>
      <Text style={s.cardTitle}>Referral leaderboard</Text>
      <Text style={s.subtle}>
        Top waitlist referrers. Every {data.totals.boost_interval} refs moves them up {data.totals.boost_spots} spots; {data.totals.founding_threshold}+ unlocks the Founding Member badge.
      </Text>
      <ReferralLeaderboard leaders={data.leaders} totals={data.totals} />
    </View>
  );
}

// company breakdown, and the 5 most recent leads with role + note preview.
function InvestorLeadsCard({
  data,
  loading,
  errorMsg,
}: {
  data: InvestorLeadsResp | null;
  loading: boolean;
  errorMsg?: string;
}) {
  if (loading && !data) {
    return (
      <View style={s.card}>
        <Text style={s.cardTitle}>Investor leads</Text>
        <Text style={s.subtle}>Loading…</Text>
      </View>
    );
  }
  if (!data) {
    return (
      <View style={s.card}>
        <Text style={s.cardTitle}>Investor leads</Text>
        <Text style={s.subtle}>
          Unavailable. {errorMsg ? `(${errorMsg})` : "Endpoint returned an error."}
        </Text>
      </View>
    );
  }
  const recent = (data.leads || []).slice(0, 5);
  return (
    <View style={s.card}>
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
        <Text style={s.cardTitle}>Investor leads</Text>
        <View style={{ flexDirection: "row", gap: 6 }}>
          <View style={s.pill}><Text style={s.pillText}>{data.total} total</Text></View>
          {data.total_repeat_visitors > 0 && (
            <View style={[s.pill, { backgroundColor: colors.brandTertiary, borderColor: colors.brand }]}>
              <Text style={[s.pillText, { color: colors.brandDeep }]}>{data.total_repeat_visitors} repeat</Text>
            </View>
          )}
        </View>
      </View>
      <Text style={s.subtle}>
        PDF downloads from the &ldquo;For Investors&rdquo; section on phoenix-atlas.com. Repeat visitors = 2+ downloads.
      </Text>

      {data.total === 0 ? (
        <Text style={[s.subtle, { marginTop: spacing.md }]}>
          No leads yet — share phoenix-atlas.com/#invest with your first prospect.
        </Text>
      ) : (
        <>
          {/* Top companies */}
          {data.top_companies.length > 0 && (
            <View style={{ marginTop: spacing.md, marginBottom: spacing.sm }}>
              <Text style={s.microLabel}>TOP COMPANIES</Text>
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
                {data.top_companies.map((c, i) => (
                  <View key={c.company + i} style={s.companyChip}>
                    <Text style={s.companyChipName}>{c.company}</Text>
                    <Text style={s.companyChipCount}>{c.count}</Text>
                  </View>
                ))}
              </View>
            </View>
          )}

          {/* Recent leads */}
          <View style={{ marginTop: spacing.md }}>
            <Text style={s.microLabel}>MOST RECENT</Text>
            {recent.map((lead) => (
              <View key={lead.email} style={s.leadRow}>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={s.leadName} numberOfLines={1}>
                    {lead.name || lead.email}
                    {lead.role ? <Text style={s.leadRole}>{"  ·  "}{lead.role}</Text> : null}
                  </Text>
                  <Text style={s.leadEmail} numberOfLines={1}>
                    {lead.company ? `${lead.company} · ` : ""}{lead.email}
                  </Text>
                  {lead.note ? (
                    <Text style={s.leadNote} numberOfLines={2}>&ldquo;{lead.note}&rdquo;</Text>
                  ) : null}
                </View>
                {(lead.downloads || 0) > 1 && (
                  <View style={s.leadBadge}>
                    <Text style={s.leadBadgeText}>×{lead.downloads}</Text>
                  </View>
                )}
              </View>
            ))}
          </View>
        </>
      )}
    </View>
  );
}


// BookClicksCard — surfaces how many investors have hit "Book a call" and
// which surface (hero / invest section / post-download / email) is doing
// the heaviest lifting. Feeds the same funnel as InvestorLeadsCard and
// tells Umar where to invest more copy or design weight.
function BookClicksCard({
  data,
  loading,
  errorMsg,
}: {
  data: BookClicksResp | null;
  loading: boolean;
  errorMsg?: string;
}) {
  if (loading && !data) {
    return (
      <View style={s.card}>
        <Text style={s.cardTitle}>Book-a-call clicks</Text>
        <Text style={s.subtle}>Loading…</Text>
      </View>
    );
  }
  if (!data) {
    return (
      <View style={s.card}>
        <Text style={s.cardTitle}>Book-a-call clicks</Text>
        <Text style={s.subtle}>
          Unavailable. {errorMsg ? `(${errorMsg})` : "Endpoint returned an error."}
        </Text>
      </View>
    );
  }
  // Nicer human labels for each landing-page surface. Falls back to raw.
  const SOURCE_LABEL: Record<string, string> = {
    hero: "Hero link",
    "invest-section": "Investor section CTA",
    "post-download": "After PDF download",
    "modal-open": "Modal → Google Calendar",
    email: "Investor email",
    "shortlink": "PDF shortlink redirect",
  };
  const label = (raw: string) =>
    SOURCE_LABEL[raw] || raw.replace(/-shortlink$/i, " (PDF)");

  return (
    <View style={s.card}>
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
        <Text style={s.cardTitle}>Book-a-call clicks</Text>
        <View style={s.pill}><Text style={s.pillText}>{data.total} total</Text></View>
      </View>
      <Text style={s.subtle}>
        Every &ldquo;Book a 20-min call&rdquo; CTA across the landing page, PDFs and investor emails.
      </Text>

      {data.total === 0 ? (
        <Text style={[s.subtle, { marginTop: spacing.md }]}>
          No clicks yet — CTAs live on the hero, investor section, post-download modal, and inside each investor email.
        </Text>
      ) : (
        <View style={{ marginTop: spacing.md, gap: 8 }}>
          {data.by_source.map((row) => {
            const maxCount = Math.max(...data.by_source.map((r) => r.count), 1);
            const pct = Math.max(6, Math.round((row.count / maxCount) * 100));
            return (
              <View key={row.source} style={{ gap: 4 }}>
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                  <Text style={s.leadName} numberOfLines={1}>{label(row.source)}</Text>
                  <Text style={s.leadRole}>{row.count}</Text>
                </View>
                <View style={{ height: 6, borderRadius: 3, backgroundColor: colors.divider, overflow: "hidden" }}>
                  <View style={{ width: `${pct}%`, height: "100%", backgroundColor: colors.brand }} />
                </View>
              </View>
            );
          })}
        </View>
      )}
    </View>
  );
}


// KotaniWebhookEchoCard — surfaces the raw deliveries that landed on
// /api/offramp/callback plus a step-by-step setup checklist. This is the
// first stop for diagnosing "my Kotani dashboard says no webhooks are
// firing" because it answers all three questions in one card: (1) did
// Kotani even POST anything? (2) is the signature verifying? (3) are the
// right event types subscribed?
function KotaniWebhookEchoCard({
  data,
  loading,
  errorMsg,
  onReplay,
  replayStatus,
}: {
  data: KotaniWebhookEchoResp | null;
  loading: boolean;
  errorMsg?: string;
  onReplay: () => void;
  replayStatus?: string | null;
}) {
  const copyUrl = useCallback(() => {
    if (!data?.expected_webhook_url) return;
    if (Platform.OS === "web" && typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(data.expected_webhook_url).catch(() => {});
    }
  }, [data]);

  if (loading && !data) {
    return (
      <View style={s.card}>
        <Text style={s.cardTitle}>Kotani webhooks</Text>
        <View style={s.loadingBox}>
          <ActivityIndicator color={colors.brand} />
          <Text style={s.loadingText}>Checking deliveries…</Text>
        </View>
      </View>
    );
  }
  if (!data) {
    return (
      <View style={s.card}>
        <Text style={s.cardTitle}>Kotani webhooks</Text>
        <Text style={s.subtle}>
          Unavailable. {errorMsg ? `(${errorMsg})` : "Endpoint returned an error."}
        </Text>
      </View>
    );
  }

  const { config_checklist: cc, deliveries, expected_webhook_url } = data;
  const noneYet = data.total_received === 0;

  const ChecklistRow = ({ ok, label }: { ok: boolean; label: string }) => (
    <View style={s.checklistRow}>
      <Ionicons
        name={ok ? "checkmark-circle" : "ellipse-outline"}
        size={16}
        color={ok ? colors.success : colors.onSurfaceTertiary}
      />
      <Text style={[s.checklistText, !ok && { color: colors.onSurfaceSecondary }]}>
        {label}
      </Text>
    </View>
  );

  return (
    <View style={s.card}>
      <View style={s.cardHeaderRow}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Ionicons name="radio-outline" size={18} color={colors.brand} />
          <Text style={s.cardTitle}>Kotani webhooks</Text>
        </View>
        <View style={[
          s.modePill,
          noneYet ? s.modePillMock : (cc.signature_invalid_count > 0 ? s.modePillLive : s.modePillReady),
        ]}>
          <Text style={s.modePillText}>
            {noneYet ? "AWAITING" : cc.signature_invalid_count > 0 ? "SIG ERRORS" : "RECEIVING"}
          </Text>
        </View>
      </View>

      {/* Expected URL block — the thing to paste into Kotani dashboard */}
      <View style={s.webhookUrlBox}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <Text style={s.microLabel}>WEBHOOK URL · PASTE INTO KOTANI DASHBOARD</Text>
          <View style={[
            s.hostBadge,
            data.host_type === "render" && s.hostBadgeOk,
            data.host_type === "preview" && s.hostBadgeWarn,
            (data.host_type === "unset" || data.host_type === "localhost") && s.hostBadgeErr,
          ]}>
            <Text style={s.hostBadgeText}>{data.host_label}</Text>
          </View>
        </View>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginTop: 4 }}>
          <Text selectable style={s.webhookUrl} numberOfLines={2}>
            {expected_webhook_url || "⚠ APP_PUBLIC_URL env var not set"}
          </Text>
          {expected_webhook_url && Platform.OS === "web" ? (
            <Pressable onPress={copyUrl} hitSlop={8} style={s.copyBtn}>
              <Ionicons name="copy-outline" size={14} color={colors.brand} />
            </Pressable>
          ) : null}
        </View>
        {data.host_warning ? (
          <View style={s.hostWarnBox}>
            <Ionicons name="warning-outline" size={13} color={colors.warning} />
            <Text style={s.hostWarnText}>{data.host_warning}</Text>
          </View>
        ) : null}
      </View>

      {/* Setup checklist */}
      <Text style={[s.microLabel, { marginTop: spacing.md }]}>SETUP CHECKLIST</Text>
      <View style={{ marginTop: 6, gap: 4 }}>
        <ChecklistRow ok={cc.api_key_configured} label="API key configured in backend .env" />
        <ChecklistRow ok={cc.webhook_secret_configured} label="Webhook signing secret in backend .env" />
        <ChecklistRow ok={cc.webhook_url_registered} label={
          cc.webhook_url_registered
            ? `${data.total_received} delivery(ies) received`
            : "Kotani is not posting to this URL yet"
        } />
        <ChecklistRow
          ok={cc.signature_invalid_count === 0 && cc.webhook_url_registered}
          label={
            cc.signature_invalid_count > 0
              ? `${cc.signature_invalid_count} delivery(ies) failed signature verification`
              : "Signatures verifying cleanly"
          }
        />
      </View>

      {/* Recommended events to subscribe */}
      <Text style={[s.microLabel, { marginTop: spacing.md }]}>SUBSCRIBE TO THESE EVENTS</Text>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
        {data.recommended_events.map((e) => (
          <View key={e} style={s.eventChip}>
            <Text style={s.eventChipText}>{e}</Text>
          </View>
        ))}
      </View>

      {/* Deliveries list */}
      <Text style={[s.microLabel, { marginTop: spacing.md }]}>LATEST DELIVERIES</Text>
      {noneYet ? (
        <View style={[s.emptyBox, { paddingVertical: spacing.md }]}>
          <Ionicons name="hourglass-outline" size={20} color={colors.onSurfaceTertiary} />
          <Text style={s.emptyText}>
            No webhooks received yet. Configure the URL above in Kotani → Settings, then hit &ldquo;Fire test delivery&rdquo;.
          </Text>
        </View>
      ) : (
        <View style={{ gap: 6, marginTop: 6 }}>
          {deliveries.slice(0, 6).map((d, i) => (
            <View key={i} style={s.deliveryRow}>
              <Ionicons
                name={d.signature_valid ? "checkmark-circle" : "close-circle"}
                size={14}
                color={d.signature_valid ? colors.success : colors.error}
              />
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={s.deliveryEvent} numberOfLines={1}>
                  {d.event_header || "(no event header — direct callback)"}
                </Text>
                <Text style={s.deliveryTime}>
                  {new Date(d.received_at).toLocaleString()}
                </Text>
              </View>
            </View>
          ))}
        </View>
      )}

      {/* Replay button — fire a synthetic webhook end-to-end */}
      <View style={s.footerRow}>
        <Text style={s.footerText} numberOfLines={1}>
          {replayStatus || "Verify dispatcher end-to-end:"}
        </Text>
        <Pressable onPress={onReplay} style={s.refreshBtn} hitSlop={8}>
          <Ionicons name="flash" size={14} color={colors.brand} />
          <Text style={s.refreshBtnText}>Fire test delivery</Text>
        </Pressable>
      </View>
    </View>
  );
}


// KotaniSmokeTestCard — one-tap end-to-end validator for the offramp rail.
// Fires rate-quote → customer-create → booking → dispatcher through the
// *real* Kotani sandbox so operators can see exactly where things break.
// Especially useful today while we're waiting on Kotani support to flip
// `integratorEnabled` — this card shows the per-service error payload so
// you can forward it verbatim in the support ticket.
function KotaniSmokeTestCard({
  result,
  running,
  corridor,
  onRun,
}: {
  result: SmokeTestResp | null;
  running: boolean;
  corridor: string;
  onRun: (corridor: string) => void;
}) {
  const CORRIDORS = ["KE", "NG", "GH", "UG", "TZ", "ZA"];

  const verdictColor =
    result?.verdict === "all_green" ? s.smokeVerdictGreen
    : result?.verdict === "partial" ? s.smokeVerdictYellow
    : result?.verdict === "all_failed" ? s.smokeVerdictRed
    : null;

  const verdictText =
    result?.verdict === "all_green"
      ? "All stages passed. The offramp rail is fully live for this corridor."
      : result?.verdict === "partial"
      ? "Some stages blocked — check the step details below and forward any Kotani error payloads to their support team."
      : result?.verdict === "all_failed"
      ? "Nothing passed. Check your API key, webhook secret, and Render deploy status."
      : "";

  const detailPreview = (step: SmokeStep): string | null => {
    if (!step.detail) return null;
    const d = step.detail;
    if (d.kotani_error) return `Kotani: ${d.kotani_error}`;
    if (d.status_code) return `HTTP ${d.status_code}`;
    if (d.rate_id) return `rateId · ${String(d.rate_id).slice(0, 10)}… · ${d.fiat_amount ?? "—"} ${d.currency ?? ""}`;
    if (d.customer_key) return `customerKey · ${String(d.customer_key).slice(0, 14)}…`;
    if (d.reference_id) return `ref · ${String(d.reference_id).slice(0, 18)}… · ${d.status || "created"}`;
    if (d.status) return String(d.status);
    return null;
  };

  return (
    <View style={s.card}>
      <View style={s.cardHeaderRow}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Ionicons name="flash-outline" size={18} color={colors.brand} />
          <Text style={s.cardTitle}>Offramp smoke test</Text>
        </View>
        {running ? (
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            <ActivityIndicator size="small" color={colors.brand} />
            <Text style={s.subtle}>Running…</Text>
          </View>
        ) : null}
      </View>

      <Text style={s.subtle}>
        Dry-run the full crypto → M-Pesa pipeline against the Kotani sandbox. No real USDC moves.
      </Text>

      {/* Corridor picker */}
      <View style={s.smokeCorridorRow}>
        {CORRIDORS.map((c) => {
          const active = c === corridor;
          return (
            <Pressable
              key={c}
              onPress={() => !running && onRun(c)}
              disabled={running}
              style={[s.corridorPill, active && s.corridorPillActive]}
              hitSlop={6}
            >
              <Text style={[s.corridorPillText, active && s.corridorPillTextActive]}>{c}</Text>
            </Pressable>
          );
        })}
      </View>

      {/* Verdict banner */}
      {result && verdictColor ? (
        <View style={[s.smokeVerdictBox, verdictColor]}>
          <Text style={s.smokeVerdictTitle}>
            {result.verdict === "all_green" ? "🎉 All green" :
             result.verdict === "partial" ? `⚠ ${result.passed} / ${result.total} passed` :
             "✗ All stages failed"}
            {" · "}
            <Text style={{ fontSize: 11, color: colors.onSurfaceSecondary, fontWeight: "500" }}>
              {result.corridor} · {result.elapsed_ms}ms
            </Text>
          </Text>
          <Text style={s.smokeVerdictText}>{verdictText}</Text>
        </View>
      ) : null}

      {/* Step details */}
      {result?.steps.map((step, i) => (
        <View key={i} style={s.smokeStepRow}>
          <Ionicons
            name={step.ok ? "checkmark-circle" : "close-circle"}
            size={18}
            color={step.ok ? colors.success : colors.error}
            style={{ marginTop: 1 }}
          />
          <View style={{ flex: 1, minWidth: 0 }}>
            <View style={{ flexDirection: "row", alignItems: "center" }}>
              <Text style={s.smokeStepName}>{step.name}</Text>
              <Text style={s.smokeStepMs}>{step.ms}ms</Text>
            </View>
            <Text style={s.smokeStepCall}>{step.call}</Text>
            {step.ok ? (
              detailPreview(step) ? <Text style={s.smokeStepDetail}>{detailPreview(step)}</Text> : null
            ) : (
              <Text style={s.smokeStepError}>
                {step.error || detailPreview(step) || "Failed"}
              </Text>
            )}
          </View>
        </View>
      ))}

      {!result && !running ? (
        <View style={[s.emptyBox, { paddingVertical: spacing.md, marginTop: 10 }]}>
          <Ionicons name="flash-outline" size={20} color={colors.onSurfaceTertiary} />
          <Text style={s.emptyText}>
            Tap a corridor above to run a fresh end-to-end test. Takes ~5s.
          </Text>
        </View>
      ) : null}
    </View>
  );
}


// KotaniSettlementsCard — rolls up settled offramp activity by day so
// operators can watch the rail breathe without pulling raw CSVs. The
// reconciliation chip is the key signal: a persistent delta_pct > 0.5%
// on any currency is early-warning that Kotani's effective rate has
// drifted from our quoted rate (fee change, FX revaluation, etc.).
function KotaniSettlementsCard({
  data,
  loading,
  errorMsg,
}: {
  data: SettlementsResp | null;
  loading: boolean;
  errorMsg?: string;
}) {
  if (loading && !data) {
    return (
      <View style={s.card}>
        <Text style={s.cardTitle}>Settlements</Text>
        <View style={s.loadingBox}>
          <ActivityIndicator color={colors.brand} />
          <Text style={s.loadingText}>Loading daily rollup…</Text>
        </View>
      </View>
    );
  }
  if (!data) {
    return (
      <View style={s.card}>
        <Text style={s.cardTitle}>Settlements</Text>
        <Text style={s.subtle}>
          Unavailable. {errorMsg ? `(${errorMsg})` : "Endpoint returned an error."}
        </Text>
      </View>
    );
  }

  const noneYet = data.overall.tx_count === 0;
  const topCrypto = Object.entries(data.overall.crypto_sent)
    .sort((a, b) => b[1] - a[1])[0];
  const topFiat = Object.entries(data.overall.fiat_delivered)
    .sort((a, b) => b[1] - a[1])[0];

  return (
    <View style={s.card}>
      <View style={s.cardHeaderRow}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Ionicons name="trending-up-outline" size={18} color={colors.brand} />
          <Text style={s.cardTitle}>Settlements</Text>
        </View>
        <View style={s.modePill}>
          <Text style={s.modePillText}>LAST {data.window_days}D</Text>
        </View>
      </View>

      {noneYet ? (
        <View style={[s.emptyBox, { paddingVertical: spacing.md }]}>
          <Ionicons name="receipt-outline" size={20} color={colors.onSurfaceTertiary} />
          <Text style={s.emptyText}>
            No settled offramps yet. First successful payout will appear here within seconds of Kotani webhook delivery.
          </Text>
        </View>
      ) : (
        <>
          {/* Overall stats grid */}
          <View style={s.settleOverallGrid}>
            <View style={s.settleStatBox}>
              <Text style={s.settleStatLabel}>Transactions</Text>
              <Text style={s.settleStatValue}>{data.overall.tx_count}</Text>
              <Text style={s.settleStatSub}>
                across {Object.keys(data.overall.corridor_breakdown).length} corridor(s)
              </Text>
            </View>
            <View style={s.settleStatBox}>
              <Text style={s.settleStatLabel}>USD equivalent</Text>
              <Text style={s.settleStatValue}>
                ${data.overall.usd_equivalent.toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </Text>
              <Text style={s.settleStatSub}>stablecoin notional</Text>
            </View>
            <View style={s.settleStatBox}>
              <Text style={s.settleStatLabel}>Crypto sent</Text>
              <Text style={s.settleStatValue}>
                {topCrypto ? `${topCrypto[1].toLocaleString(undefined, { maximumFractionDigits: 2 })}` : "—"}
              </Text>
              <Text style={s.settleStatSub}>{topCrypto ? topCrypto[0] : "—"}</Text>
            </View>
            <View style={s.settleStatBox}>
              <Text style={s.settleStatLabel}>Fiat delivered</Text>
              <Text style={s.settleStatValue}>
                {topFiat ? `${topFiat[1].toLocaleString(undefined, { maximumFractionDigits: 0 })}` : "—"}
              </Text>
              <Text style={s.settleStatSub}>{topFiat ? topFiat[0] : "—"}</Text>
            </View>
          </View>

          {/* Daily rows (top 7) */}
          <Text style={[s.microLabel, { marginTop: spacing.md }]}>DAILY BREAKDOWN</Text>
          {data.daily.slice(0, 7).map((d) => (
            <View key={d.date} style={s.settleRow}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "baseline" }}>
                <Text style={s.settleDay}>{d.date}</Text>
                <Text style={s.settleDaySub}>{d.tx_count} tx · ${d.usd_equivalent.toLocaleString(undefined, { maximumFractionDigits: 0 })}</Text>
              </View>
              <Text style={s.settleDaySub}>
                {Object.entries(d.fiat_delivered)
                  .map(([cur, amt]) => `${amt.toLocaleString(undefined, { maximumFractionDigits: 0 })} ${cur}`)
                  .join(" · ")}
              </Text>
              {d.reconciliation.length > 0 ? (
                <View style={s.settleReconRow}>
                  {d.reconciliation.map((r) => (
                    <View
                      key={r.currency}
                      style={[s.settleReconChip, Math.abs(r.delta_pct) > 0.5 && s.settleReconChipWarn]}
                    >
                      <Text style={s.settleReconChipText}>
                        {r.currency} Δ {r.delta >= 0 ? "+" : ""}{r.delta.toFixed(2)} ({r.delta_pct >= 0 ? "+" : ""}{r.delta_pct.toFixed(2)}%)
                      </Text>
                    </View>
                  ))}
                </View>
              ) : null}
            </View>
          ))}
        </>
      )}
    </View>
  );
}


// PartnerUseCaseCard — one-click dispatcher + download panel for the PSB
// use-case brief. Combines three capabilities in a single card:
//   • Form to fill in recipient + optional cover note, then "Send via Resend"
//   • Direct PDF / DOCX downloads if you want to review before sending
//   • Sent-history list with delivery / open status (populated by Resend
//     webhook → /api/admin/usecase/resend-webhook)
function PartnerUseCaseCard({
  sendsData,
  loading,
  errorMsg,
  onSent,
}: {
  sendsData: UseCaseSendsResp | null;
  loading: boolean;
  errorMsg?: string;
  onSent: () => void;
}) {
  const [bankShort, setBankShort] = useState("9PSB");
  const [bankName, setBankName] = useState("9mobile 9Payment Service Bank Ltd");
  const [recipientEmail, setRecipientEmail] = useState("");
  const [recipientName, setRecipientName] = useState("");
  const [recipientTitle, setRecipientTitle] = useState("");
  const [coverNote, setCoverNote] = useState("");
  const [sending, setSending] = useState(false);
  const [sendResult, setSendResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  // Contact book — pulled lazily when the card mounts so we don't block
  // initial admin load on a secondary endpoint.
  const [contacts, setContacts] = useState<ContactsResp | null>(null);
  const [showContacts, setShowContacts] = useState(false);
  const [savingContact, setSavingContact] = useState(false);
  const reloadContacts = useCallback(async () => {
    try {
      const res = await api<ContactsResp>("/admin/contacts");
      setContacts(res);
    } catch {
      /* non-fatal — card still works without contacts */
    }
  }, []);
  useEffect(() => { reloadContacts(); }, [reloadContacts]);

  // When the user types a new bank_short, auto-pick its primary contact
  // from the contact book (no overwrite if they've already typed).
  useEffect(() => {
    if (!contacts || recipientEmail || recipientName) return;
    const bank = (bankShort || "").toUpperCase();
    const list = contacts.by_bank[bank];
    if (!list?.length) return;
    const primary = list.find((c) => c.is_primary) || list[0];
    if (primary) {
      setRecipientEmail(primary.email);
      setRecipientName(primary.name);
      if (primary.title) setRecipientTitle(primary.title);
      if (primary.bank_name && !bankName) setBankName(primary.bank_name);
    }
  }, [bankShort, contacts]); // eslint-disable-line react-hooks/exhaustive-deps -- auto-fill only runs when fields empty

  const applyContact = useCallback(async (c: Contact) => {
    setRecipientEmail(c.email);
    setRecipientName(c.name);
    setRecipientTitle(c.title || "");
    setBankShort(c.bank_short);
    if (c.bank_name) setBankName(c.bank_name);
    setShowContacts(false);
    // Fire-and-forget touch so this contact ranks higher next time.
    api(`/admin/contacts/${c.id}/touch`, { method: "POST", body: {} }).catch(() => undefined);
  }, []);

  const saveCurrentAsContact = useCallback(async () => {
    if (!recipientEmail.includes("@") || !recipientName.trim() || !bankShort.trim()) return;
    setSavingContact(true);
    try {
      await api("/admin/contacts", {
        method: "POST",
        body: {
          bank_short: bankShort.trim(),
          bank_name: bankName.trim() || undefined,
          name: recipientName.trim(),
          title: recipientTitle.trim() || undefined,
          email: recipientEmail.trim(),
        },
      });
      await reloadContacts();
    } catch {
      /* swallow — minor UX feature */
    } finally {
      setSavingContact(false);
    }
  }, [bankName, bankShort, recipientEmail, recipientName, recipientTitle, reloadContacts]);

  const canSend =
    recipientEmail.includes("@") && recipientEmail.includes(".") &&
    bankShort.trim().length > 0 && !sending;

  const currentContactSaved = useMemo(() => {
    if (!contacts || !recipientEmail) return false;
    return contacts.contacts.some((c) => c.email.toLowerCase() === recipientEmail.toLowerCase());
  }, [contacts, recipientEmail]);

  const onSend = async () => {
    if (!canSend) return;
    setSending(true);
    setSendResult(null);
    try {
      const res = await api<{ ok: boolean; send_id: string; status: string; error?: string }>(
        "/admin/usecase/send",
        {
          method: "POST",
          body: {
            recipient_email: recipientEmail.trim(),
            recipient_name: recipientName.trim(),
            recipient_title: recipientTitle.trim() || undefined,
            bank_short: bankShort.trim(),
            bank_name: bankName.trim() || undefined,
            cover_note: coverNote.trim() || undefined,
          },
        }
      );
      if (res.ok) {
        setSendResult({ ok: true, msg: `✓ Sent to ${recipientEmail}` });
        setCoverNote("");
        // Refresh sends list so the new row appears.
        setTimeout(() => onSent(), 500);
      } else {
        setSendResult({ ok: false, msg: `✗ ${res.error || "Send failed"}` });
      }
    } catch (e: any) {
      setSendResult({ ok: false, msg: `✗ ${e?.message || "Network error"}` });
    } finally {
      setSending(false);
    }
  };

  const statusChip = (row: UseCaseSendRow): { label: string; color: string } => {
    if (row.opened_at) return { label: "OPENED", color: colors.success };
    if (row.clicked_at) return { label: "CLICKED", color: colors.success };
    if (row.delivered_at) return { label: "DELIVERED", color: colors.brand };
    if (row.status === "bounced") return { label: "BOUNCED", color: colors.error };
    if (row.status === "failed") return { label: "FAILED", color: colors.error };
    if (row.status === "sent") return { label: "SENT", color: colors.onSurfaceSecondary };
    return { label: row.status.toUpperCase(), color: colors.onSurfaceTertiary };
  };

  return (
    <View style={s.card}>
      <View style={s.cardHeaderRow}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Ionicons name="briefcase-outline" size={18} color={colors.brand} />
          <Text style={s.cardTitle}>Partner use case · {bankShort}</Text>
        </View>
        <View style={s.modePill}>
          <Text style={s.modePillText}>INFRA PITCH</Text>
        </View>
      </View>
      <Text style={s.subtle}>
        Fill in the recipient, add a personal note, hit send. Vaulted
        attaches the 2-page PDF and emails via Resend from your reply-to
        address — any reply lands back in your inbox.
      </Text>

      {/* Minimal form */}
      <View style={{ marginTop: 10, gap: 8 }}>
        <View style={{ flexDirection: "row", gap: 8 }}>
          <View style={{ flex: 1 }}>
            <Text style={s.inputLabel}>Bank short</Text>
            <TextInput
              value={bankShort}
              onChangeText={setBankShort}
              placeholder="9PSB"
              placeholderTextColor={colors.onSurfaceTertiary}
              style={s.input}
              autoCapitalize="characters"
            />
          </View>
          <View style={{ flex: 2 }}>
            <Text style={s.inputLabel}>Bank name</Text>
            <TextInput
              value={bankName}
              onChangeText={setBankName}
              placeholder="e.g. 9mobile 9PSB Ltd"
              placeholderTextColor={colors.onSurfaceTertiary}
              style={s.input}
            />
          </View>
        </View>
        <View>
          <Text style={s.inputLabel}>Recipient email *</Text>
          <TextInput
            value={recipientEmail}
            onChangeText={setRecipientEmail}
            placeholder="director@9psb.com.ng"
            placeholderTextColor={colors.onSurfaceTertiary}
            style={s.input}
            autoCapitalize="none"
            keyboardType="email-address"
          />
        </View>

        {/* Contact book picker + save-as-contact action */}
        {contacts && contacts.total > 0 ? (
          <View style={{ flexDirection: "row", alignItems: "center", gap: 10, marginTop: -2 }}>
            <Pressable onPress={() => setShowContacts((v) => !v)} hitSlop={6}>
              <Text style={s.disclosureBtn}>
                {showContacts ? "▾" : "▸"} {contacts.total} saved contact{contacts.total !== 1 ? "s" : ""}
              </Text>
            </Pressable>
            {recipientEmail && !currentContactSaved ? (
              <Pressable
                onPress={saveCurrentAsContact}
                disabled={savingContact}
                hitSlop={6}
                style={{ marginLeft: "auto" }}
              >
                <Text style={[s.disclosureBtn, { color: colors.success }]}>
                  {savingContact ? "Saving…" : "+ Save to contacts"}
                </Text>
              </Pressable>
            ) : null}
          </View>
        ) : null}
        {showContacts && contacts ? (
          <View style={{ gap: 4, marginTop: 2 }}>
            {Object.entries(contacts.by_bank).map(([bank, list]) => (
              <View key={bank}>
                <Text style={[s.inputLabel, { marginTop: 6, marginBottom: 4 }]}>{bank}</Text>
                {list.map((c) => (
                  <Pressable
                    key={c.id}
                    onPress={() => applyContact(c)}
                    style={s.contactRow}
                    hitSlop={4}
                  >
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <Text style={s.contactName} numberOfLines={1}>
                        {c.name}{" "}
                        {c.is_primary ? <Text style={s.contactPrimary}>· primary</Text> : null}
                      </Text>
                      <Text style={s.contactMeta} numberOfLines={1}>
                        {c.email}{c.title ? ` · ${c.title}` : ""}
                      </Text>
                    </View>
                    <Ionicons name="arrow-forward-circle-outline" size={16} color={colors.brand} />
                  </Pressable>
                ))}
              </View>
            ))}
          </View>
        ) : null}

        <View style={{ flexDirection: "row", gap: 8 }}>
          <View style={{ flex: 1 }}>
            <Text style={s.inputLabel}>Recipient name</Text>
            <TextInput
              value={recipientName}
              onChangeText={setRecipientName}
              placeholder="Dr. Branka Mracajac"
              placeholderTextColor={colors.onSurfaceTertiary}
              style={s.input}
            />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={s.inputLabel}>Title</Text>
            <TextInput
              value={recipientTitle}
              onChangeText={setRecipientTitle}
              placeholder="Managing Director"
              placeholderTextColor={colors.onSurfaceTertiary}
              style={s.input}
            />
          </View>
        </View>
        <Pressable onPress={() => setExpanded((v) => !v)} hitSlop={6}>
          <Text style={s.disclosureBtn}>
            {expanded ? "▾ Hide cover note" : "▸ Add a personal cover note (optional)"}
          </Text>
        </Pressable>
        {expanded ? (
          <TextInput
            value={coverNote}
            onChangeText={setCoverNote}
            placeholder="e.g. 'Following up on our call last week — attached is the detailed brief we discussed.'"
            placeholderTextColor={colors.onSurfaceTertiary}
            style={[s.input, { height: 80, textAlignVertical: "top", paddingVertical: 10 }]}
            multiline
          />
        ) : null}
      </View>

      {/* Send button + result */}
      <Pressable
        onPress={onSend}
        disabled={!canSend}
        style={[s.sendBtn, !canSend && s.sendBtnDisabled]}
      >
        {sending ? (
          <ActivityIndicator size="small" color={colors.onBrand} />
        ) : (
          <>
            <Ionicons name="paper-plane" size={16} color={colors.onBrand} />
            <Text style={s.sendBtnText}>Send use case to {bankShort}</Text>
          </>
        )}
      </Pressable>
      {sendResult ? (
        <Text style={[s.sendResult, sendResult.ok ? s.sendResultOk : s.sendResultErr]}>
          {sendResult.msg}
        </Text>
      ) : null}

      {/* Download / preview links */}
      <View style={s.downloadStrip}>
        <Pressable
          onPress={() => {
            const q = `?bank_short=${encodeURIComponent(bankShort)}&bank_name=${encodeURIComponent(bankName)}`;
            const url = `${API_BASE}/api/usecase/psb.pdf${q}`;
            if (Platform.OS === "web") window.open(url, "_blank");
            else Linking.openURL(url).catch(() => {});
          }}
          style={s.downloadBtn}
          hitSlop={6}
        >
          <Ionicons name="document-outline" size={13} color={colors.brand} />
          <Text style={s.downloadBtnText}>Preview PDF</Text>
        </Pressable>
        <Pressable
          onPress={() => {
            const q = `?bank_short=${encodeURIComponent(bankShort)}&bank_name=${encodeURIComponent(bankName)}`;
            const url = `${API_BASE}/api/usecase/psb.docx${q}`;
            if (Platform.OS === "web") window.open(url, "_blank");
            else Linking.openURL(url).catch(() => {});
          }}
          style={s.downloadBtn}
          hitSlop={6}
        >
          <Ionicons name="document-text-outline" size={13} color={colors.brand} />
          <Text style={s.downloadBtnText}>Edit DOCX</Text>
        </Pressable>
      </View>

      {/* Send history (collapsed by default) */}
      {sendsData && sendsData.total > 0 ? (
        <>
          <Pressable
            onPress={() => setShowHistory((v) => !v)}
            style={s.historyToggle}
            hitSlop={6}
          >
            <Text style={s.historyToggleText}>
              {showHistory ? "▾" : "▸"} Sent history ({sendsData.total})
            </Text>
            <View style={{ flexDirection: "row", gap: 10 }}>
              <Text style={s.historyStat}>
                📬 {sendsData.delivered_count} delivered
              </Text>
              <Text style={s.historyStat}>
                👀 {sendsData.opened_count} opened
              </Text>
            </View>
          </Pressable>
          {showHistory ? (
            <View style={{ gap: 6, marginTop: 6 }}>
              {sendsData.rows.slice(0, 10).map((row) => {
                const chip = statusChip(row);
                return (
                  <View key={row.send_id} style={s.historyRow}>
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <Text style={s.historyRecipient} numberOfLines={1}>
                        {row.recipient_name || row.recipient_email}
                        <Text style={{ color: colors.onSurfaceTertiary }}>
                          {"  ·  "}{row.bank_short}
                        </Text>
                      </Text>
                      <Text style={s.historyMeta} numberOfLines={1}>
                        {row.recipient_email} · {new Date(row.attempted_at || "").toLocaleString()}
                      </Text>
                    </View>
                    <View style={[s.historyChip, { borderColor: chip.color + "60", backgroundColor: chip.color + "20" }]}>
                      <Text style={[s.historyChipText, { color: chip.color }]}>{chip.label}</Text>
                    </View>
                  </View>
                );
              })}
            </View>
          ) : null}
        </>
      ) : null}

      {errorMsg && !sendsData ? (
        <Text style={[s.subtle, { color: colors.error, marginTop: 8, fontSize: 11 }]}>
          History unavailable: {errorMsg}
        </Text>
      ) : null}
    </View>
  );
}


const s = StyleSheet.create({
  // Session-expired takeover
  expiredWrap: {
    flex: 1, alignItems: "center", justifyContent: "center",
    paddingHorizontal: 24, paddingBottom: 60,
  },
  expiredCard: {
    width: "100%", maxWidth: 420,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1, borderColor: colors.border,
    padding: 28, alignItems: "center",
  },
  expiredIcon: {
    width: 60, height: 60, borderRadius: 30,
    backgroundColor: colors.brand + "20",
    alignItems: "center", justifyContent: "center",
    marginBottom: 16,
  },
  expiredTitle: {
    fontSize: 20, fontWeight: "800", color: colors.onSurface,
    letterSpacing: -0.3, marginBottom: 10,
  },
  expiredBody: {
    fontSize: 13, color: colors.onSurfaceSecondary,
    lineHeight: 19, textAlign: "center", marginBottom: 22,
  },
  expiredBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
    paddingVertical: 11, paddingHorizontal: 24,
    backgroundColor: colors.brand,
    borderRadius: radius.md,
    minWidth: 180, minHeight: 44,
  },
  expiredBtnText: {
    color: colors.onBrand, fontSize: 14, fontWeight: "700", letterSpacing: 0.2,
  },
  expiredRetry: {
    fontSize: 12, color: colors.onSurfaceTertiary,
    textDecorationLine: "underline",
  },

  // PartnerUseCaseCard dispatcher
  inputLabel: {
    fontSize: 10, fontWeight: "700", color: colors.onSurfaceSecondary,
    letterSpacing: 0.4, textTransform: "uppercase", marginBottom: 4,
  },
  input: {
    paddingHorizontal: 10, paddingVertical: 8,
    borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.sm,
    backgroundColor: colors.surfaceSecondary,
    color: colors.onSurface,
    fontSize: 13,
  },
  disclosureBtn: {
    fontSize: 11.5, color: colors.brandDeep, fontWeight: "600",
    marginTop: 2, paddingVertical: 4,
  },
  sendBtn: {
    marginTop: 14,
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
    paddingVertical: 11, paddingHorizontal: 16,
    backgroundColor: colors.brand,
    borderRadius: radius.md,
    minHeight: 44,
  },
  sendBtnDisabled: {
    backgroundColor: colors.border,
    opacity: 0.7,
  },
  sendBtnText: {
    color: colors.onBrand, fontSize: 13.5, fontWeight: "700", letterSpacing: 0.2,
  },
  sendResult: { fontSize: 12, marginTop: 8, textAlign: "center" },
  sendResultOk: { color: colors.success, fontWeight: "600" },
  sendResultErr: { color: colors.error, fontWeight: "600" },
  downloadStrip: {
    flexDirection: "row", gap: 8, marginTop: 10, flexWrap: "wrap",
  },
  downloadBtn: {
    flexDirection: "row", alignItems: "center", gap: 5,
    paddingHorizontal: 10, paddingVertical: 6,
    borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary,
  },
  downloadBtnText: {
    fontSize: 11, color: colors.brand, fontWeight: "600", letterSpacing: 0.2,
  },
  historyToggle: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    paddingVertical: 8, paddingHorizontal: 2,
    marginTop: 10,
    borderTopWidth: 1, borderTopColor: colors.border,
  },
  historyToggleText: { fontSize: 12, fontWeight: "700", color: colors.onSurface },
  historyStat: { fontSize: 10.5, color: colors.onSurfaceSecondary },
  historyRow: {
    flexDirection: "row", alignItems: "center", gap: 10,
    paddingVertical: 7, paddingHorizontal: 10,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.sm,
  },
  historyRecipient: { fontSize: 12, fontWeight: "700", color: colors.onSurface },
  historyMeta: { fontSize: 10, color: colors.onSurfaceTertiary, marginTop: 2 },
  historyChip: {
    paddingHorizontal: 7, paddingVertical: 3,
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  historyChipText: { fontSize: 9.5, fontWeight: "800", letterSpacing: 0.3 },

  // Contact book
  contactRow: {
    flexDirection: "row", alignItems: "center", gap: 8,
    paddingVertical: 8, paddingHorizontal: 10,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.sm,
    marginTop: 4,
  },
  contactName: { fontSize: 12, fontWeight: "700", color: colors.onSurface },
  contactPrimary: { fontSize: 10, color: colors.brandDeep, fontWeight: "600" },
  contactMeta: { fontSize: 10.5, color: colors.onSurfaceTertiary, marginTop: 2 },

  // KotaniSmokeTestCard
  smokeCorridorRow: {
    flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 10,
  },
  corridorPill: {
    paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
    minWidth: 40, alignItems: "center",
  },
  corridorPillActive: {
    backgroundColor: colors.brand + "25",
    borderColor: colors.brand,
  },
  corridorPillText: { fontSize: 11, fontWeight: "700", color: colors.onSurfaceSecondary, letterSpacing: 0.5 },
  corridorPillTextActive: { color: colors.brandDeep },
  smokeStepRow: {
    flexDirection: "row", alignItems: "flex-start", gap: 10,
    paddingVertical: 8, paddingHorizontal: 10,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.sm,
    marginTop: 6,
  },
  smokeStepName: { fontSize: 12, fontWeight: "700", color: colors.onSurface },
  smokeStepCall: { fontSize: 10, color: colors.onSurfaceTertiary, fontFamily: "Menlo", marginTop: 1 },
  smokeStepDetail: { fontSize: 10.5, color: colors.onSurfaceSecondary, marginTop: 4, lineHeight: 14 },
  smokeStepError: { fontSize: 10.5, color: colors.error, marginTop: 4, lineHeight: 14 },
  smokeStepMs: { fontSize: 9.5, color: colors.onSurfaceTertiary, marginLeft: "auto" },
  smokeVerdictBox: {
    marginTop: 10, paddingHorizontal: 12, paddingVertical: 10,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  smokeVerdictGreen: {
    backgroundColor: colors.success + "15",
    borderColor: colors.success + "50",
  },
  smokeVerdictYellow: {
    backgroundColor: colors.warning + "15",
    borderColor: colors.warning + "50",
  },
  smokeVerdictRed: {
    backgroundColor: colors.error + "15",
    borderColor: colors.error + "50",
  },
  smokeVerdictTitle: { fontSize: 13, fontWeight: "800", color: colors.onSurface, letterSpacing: -0.2 },
  smokeVerdictText: { fontSize: 11.5, color: colors.onSurfaceSecondary, marginTop: 3, lineHeight: 16 },

  // KotaniSettlementsCard
  settleOverallGrid: {
    flexDirection: "row", flexWrap: "wrap", gap: 10, marginTop: 10,
  },
  settleStatBox: {
    flex: 1, minWidth: "47%",
    paddingHorizontal: 10, paddingVertical: 10,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.sm,
    borderWidth: 1, borderColor: colors.border,
  },
  settleStatLabel: { fontSize: 10, color: colors.onSurfaceTertiary, letterSpacing: 0.4, textTransform: "uppercase" },
  settleStatValue: { fontSize: 18, fontWeight: "800", color: colors.onSurface, marginTop: 3, letterSpacing: -0.3 },
  settleStatSub: { fontSize: 10, color: colors.onSurfaceSecondary, marginTop: 2 },
  settleRow: {
    paddingVertical: 10, paddingHorizontal: 10,
    borderTopWidth: 1, borderTopColor: colors.border,
  },
  settleDay: { fontSize: 11.5, fontWeight: "700", color: colors.onSurface },
  settleDaySub: { fontSize: 10.5, color: colors.onSurfaceSecondary, marginTop: 2 },
  settleReconRow: { flexDirection: "row", gap: 8, marginTop: 6, flexWrap: "wrap" },
  settleReconChip: {
    paddingHorizontal: 7, paddingVertical: 3,
    borderRadius: radius.sm,
    backgroundColor: colors.surface,
    borderWidth: 1, borderColor: colors.border,
  },
  settleReconChipText: { fontSize: 10, color: colors.onSurfaceSecondary, fontFamily: "Menlo" },
  settleReconChipWarn: { borderColor: colors.warning + "80", backgroundColor: colors.warning + "15" },

  container: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: "row", alignItems: "center", gap: 12,
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
    borderBottomWidth: 1, borderBottomColor: colors.divider,
  },
  backBtn: { padding: 4 },
  headerTitle: { fontSize: 20, fontWeight: "700", color: colors.onSurface },
  headerSub: { fontSize: 12, color: colors.onSurfaceSecondary, marginTop: 2 },

  scrollContent: { padding: spacing.lg, gap: spacing.md, paddingBottom: 48 },

  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
    borderWidth: 1, borderColor: colors.divider,
  },
  cardHeaderRow: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    marginBottom: spacing.sm,
  },
  cardTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface },

  modePill: {
    paddingHorizontal: 10, paddingVertical: 4,
    borderRadius: radius.pill,
  },
  modePillLive: { backgroundColor: colors.brand + "22", borderWidth: 1, borderColor: colors.brand },
  modePillMock: { backgroundColor: colors.onSurfaceTertiary + "22" },
  modePillReady: { backgroundColor: colors.success + "22", borderWidth: 1, borderColor: colors.success },
  modePillText: { fontSize: 10, fontWeight: "700", color: colors.onSurface, letterSpacing: 0.5 },

  loadingBox: { flexDirection: "row", alignItems: "center", gap: 8, padding: spacing.md },
  loadingText: { fontSize: 13, color: colors.onSurfaceSecondary },

  errorBox: {
    flexDirection: "row", alignItems: "center", gap: 8,
    padding: spacing.sm, backgroundColor: colors.error + "11",
    borderRadius: radius.sm, borderLeftWidth: 3, borderLeftColor: colors.error,
  },
  errorText: { fontSize: 12, color: colors.error, flex: 1 },

  diagRow: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    paddingVertical: 6, gap: 12,
  },
  diagLabel: { fontSize: 12, color: colors.onSurfaceSecondary },
  diagValue: { fontSize: 12, color: colors.onSurface, fontFamily: "Menlo", flex: 1, textAlign: "right" },
  diagValueOk: { color: colors.success },
  diagValueMissing: { color: colors.error },

  divider: { height: 1, backgroundColor: colors.divider, marginVertical: spacing.sm },
  probesHeader: {
    fontSize: 11, fontWeight: "700", color: colors.onSurfaceSecondary,
    letterSpacing: 0.5, marginBottom: 6, textTransform: "uppercase",
  },
  probeRow: {
    paddingVertical: 8,
    borderTopWidth: 1, borderTopColor: colors.divider + "80",
  },
  probeName: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  probeEndpoint: { fontSize: 10, color: colors.onSurfaceTertiary, fontFamily: "Menlo", marginLeft: 22 },
  probeDetail: { fontSize: 11, color: colors.onSurfaceSecondary, marginTop: 3, marginLeft: 22 },
  probeDetailFail: { color: colors.error },

  chip: {
    paddingHorizontal: 8, paddingVertical: 2,
    borderRadius: radius.pill,
    backgroundColor: colors.onSurfaceTertiary + "22",
  },
  chipBad: { backgroundColor: colors.error + "22" },
  chipText: { fontSize: 10, color: colors.onSurfaceSecondary, fontFamily: "Menlo" },
  chipTextBad: { color: colors.error },

  blockerBox: {
    backgroundColor: colors.brand + "10", borderRadius: radius.sm,
    padding: spacing.sm, marginTop: spacing.sm,
    borderLeftWidth: 3, borderLeftColor: colors.brand,
  },
  blockerText: { fontSize: 11.5, color: colors.brandDeep, flex: 1, lineHeight: 16 },
  mono: { fontFamily: "Menlo", fontSize: 11 },

  footerRow: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    marginTop: spacing.sm, paddingTop: spacing.sm,
    borderTopWidth: 1, borderTopColor: colors.divider,
  },
  footerText: { fontSize: 10, color: colors.onSurfaceTertiary },
  refreshBtn: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: 10, paddingVertical: 4,
    borderRadius: radius.pill,
    backgroundColor: colors.brand + "18",
  },
  refreshBtnText: { fontSize: 11, color: colors.brand, fontWeight: "600" },

  toolRow: {
    flexDirection: "row", alignItems: "center", gap: 10,
    paddingVertical: spacing.sm,
  },
  toolTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  toolSub: { fontSize: 11, color: colors.onSurfaceSecondary, marginTop: 2 },

  // Waitlist card
  totalPill: {
    paddingHorizontal: 10, paddingVertical: 4,
    borderRadius: radius.pill,
    backgroundColor: colors.brand + "18",
  },
  totalPillText: { fontSize: 11, color: colors.brand, fontWeight: "700", letterSpacing: 0.3 },
  emptyBox: {
    alignItems: "center", gap: 8, paddingVertical: spacing.md,
  },
  emptyText: { fontSize: 12, color: colors.onSurfaceSecondary, textAlign: "center" },

  corridorRow: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    marginBottom: 4, gap: 8,
  },
  corridorFlag: { fontSize: 14 },
  corridorName: { fontSize: 12.5, color: colors.onSurface, fontWeight: "600", flexShrink: 1 },
  corridorCode: {
    fontSize: 9.5, color: colors.onSurfaceTertiary,
    fontFamily: "Menlo", letterSpacing: 0.5,
  },
  corridorCount: { fontSize: 13, color: colors.onSurface, fontWeight: "700" },
  corridorPct: { fontSize: 10, color: colors.onSurfaceSecondary },
  barTrack: {
    height: 5, borderRadius: 3, overflow: "hidden",
    backgroundColor: colors.divider,
  },
  barFill: {
    height: "100%",
    backgroundColor: colors.brand,
    borderRadius: 3,
  },

  // InvestorLeadsCard extras
  pill: {
    paddingHorizontal: 10, paddingVertical: 4,
    borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
  },
  pillText: { fontSize: 10, fontWeight: "700", color: colors.onSurface, letterSpacing: 0.3 },
  subtle: { fontSize: 12, color: colors.onSurfaceSecondary, lineHeight: 16 },
  microLabel: {
    fontSize: 10, letterSpacing: 1.1,
    color: colors.onSurfaceTertiary, fontWeight: "700",
  },
  companyChip: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: 10, paddingVertical: 5,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    borderWidth: 1, borderColor: "rgba(201,163,91,0.35)",
  },
  companyChipName: { fontSize: 11, color: colors.onSurface, fontWeight: "600" },
  companyChipCount: { fontSize: 10, color: colors.brandDeep, fontWeight: "700" },
  leadRow: {
    flexDirection: "row", alignItems: "center", gap: 8,
    paddingVertical: 10,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.divider,
  },
  leadName: { fontSize: 13, color: colors.onSurface, fontWeight: "700" },
  leadRole: { color: colors.onSurfaceSecondary, fontWeight: "500", fontSize: 12 },
  leadEmail: { fontSize: 11, color: colors.onSurfaceSecondary, marginTop: 1 },
  leadNote: { fontSize: 11, color: colors.onSurfaceTertiary, marginTop: 4, fontStyle: "italic", lineHeight: 15 },
  leadBadge: {
    paddingHorizontal: 8, paddingVertical: 3,
    borderRadius: radius.pill,
    backgroundColor: colors.brand,
  },
  leadBadgeText: { fontSize: 10, fontWeight: "800", color: "#0F0B08" },

  // DailySignupsCard mini stats row
  miniStatsRow: {
    flexDirection: "row",
    gap: 12,
    marginTop: spacing.md,
    padding: 10,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border,
  },
  miniStat: { flex: 1, alignItems: "center" },
  miniStatNum: { fontSize: 18, fontWeight: "800", color: colors.onSurface, letterSpacing: -0.5 },
  miniStatLabel: { fontSize: 10, color: colors.onSurfaceSecondary, marginTop: 2, letterSpacing: 0.3, textAlign: "center" },

  // KotaniWebhookEchoCard
  webhookUrlBox: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.sm,
    padding: 10,
    borderWidth: 1, borderColor: colors.border,
  },
  webhookUrl: {
    flex: 1,
    fontSize: 11.5,
    fontFamily: "Menlo",
    color: colors.onSurface,
    lineHeight: 16,
  },
  copyBtn: {
    padding: 6,
    borderRadius: radius.sm,
    backgroundColor: colors.brand + "18",
  },
  checklistRow: { flexDirection: "row", alignItems: "center", gap: 8, paddingVertical: 3 },
  checklistText: { fontSize: 12, color: colors.onSurface, flex: 1 },
  eventChip: {
    paddingHorizontal: 8, paddingVertical: 4,
    borderRadius: radius.pill,
    backgroundColor: colors.brand + "15",
    borderWidth: 1, borderColor: colors.brand + "40",
  },
  eventChipText: { fontSize: 10, color: colors.brandDeep, fontFamily: "Menlo" },
  deliveryRow: {
    flexDirection: "row", alignItems: "center", gap: 8,
    paddingVertical: 6, paddingHorizontal: 8,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.sm,
  },
  deliveryEvent: { fontSize: 11.5, color: colors.onSurface, fontWeight: "600" },
  deliveryTime: { fontSize: 10, color: colors.onSurfaceTertiary, marginTop: 1 },

  // Host badge + warning
  hostBadge: {
    paddingHorizontal: 6, paddingVertical: 2,
    borderRadius: radius.pill,
    backgroundColor: colors.onSurfaceTertiary + "20",
    borderWidth: 1, borderColor: colors.border,
  },
  hostBadgeOk: {
    backgroundColor: colors.success + "20",
    borderColor: colors.success + "60",
  },
  hostBadgeWarn: {
    backgroundColor: colors.warning + "20",
    borderColor: colors.warning + "60",
  },
  hostBadgeErr: {
    backgroundColor: colors.error + "20",
    borderColor: colors.error + "60",
  },
  hostBadgeText: {
    fontSize: 9.5, fontWeight: "700", color: colors.onSurface, letterSpacing: 0.3,
  },
  hostWarnBox: {
    flexDirection: "row", gap: 6, alignItems: "flex-start",
    marginTop: 8, paddingHorizontal: 8, paddingVertical: 6,
    backgroundColor: colors.warning + "12",
    borderRadius: radius.sm,
    borderWidth: 1, borderColor: colors.warning + "35",
  },
  hostWarnText: { flex: 1, fontSize: 11, color: colors.onSurfaceSecondary, lineHeight: 15 },
});
