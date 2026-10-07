/**
 * Admin — Dashboard index (orchestrator)
 * =======================================
 * Route: /admin
 *
 * Thin coordinator that owns data-fetch + session state. Every card is
 * a self-contained component under /src/features/admin/ — this file
 * only glues them together.
 *
 * Only accessible to users whose email is in the backend's ADMIN_EMAILS
 * env var. Backend enforces via require_admin — this screen is UI only.
 */
import { useCallback, useEffect, useState } from "react";
import { View, Text, Pressable, ScrollView, RefreshControl } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { api, ApiError, registerUnauthorizedHandler } from "@/src/lib/api";
import { AdminBiometricGate, AdminBiometricNudge } from "@/src/components/AdminBiometricGate";
import { colors } from "@/src/lib/theme";
import {
  KotaniHealthCard,
  WaitlistCard,
  DailySignupsCard,
  CorridorMatrixCard,
  ReferralLeaderboardCard,
  InvestorLeadsCard,
  BookClicksCard,
  KotaniWebhookEchoCard,
  KotaniSmokeTestCard,
  KotaniSettlementsCard,
  PartnerUseCaseCard,
  LetterheadCard,
  ToolsCard,
  WeeklyDigestCard,
  WaitlistSyncCard,
  adminStyles as s,
  type KotaniHealth,
  type WaitlistStats,
  type InvestorLeadsResp,
  type DailySignupsResp,
  type ReferralsResp,
  type BookClicksResp,
  type KotaniWebhookEchoResp,
  type SmokeTestResp,
  type SettlementsResp,
  type UseCaseSendsResp,
} from "@/src/features/admin";

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
    // Every call runs independently via grab() — a failure on any
    // single endpoint only marks that card as unavailable instead of
    // nuking the entire dashboard.
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
    if (any401) {
      setSessionExpired(true);
      setLoading(false);
      setRefreshing(false);
      return;
    }
    setSessionExpired(false);
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

          <KotaniHealthCard
            health={health}
            loading={loading}
            errorMsg={cardErrors.kotani}
            globalErr={err}
            onReprobe={load}
          />

          <WaitlistCard stats={waitlist} loading={loading} errorMsg={cardErrors.waitlist} />

          <WaitlistSyncCard onSynced={load} />

          <KotaniWebhookEchoCard
            data={webhookEcho}
            loading={loading}
            errorMsg={cardErrors.webhookEcho}
            onReplay={onReplayWebhook}
            replayStatus={replayStatus}
          />

          <KotaniSmokeTestCard
            result={smokeResult}
            running={smokeRunning}
            corridor={smokeCorridor}
            onRun={onRunSmokeTest}
          />

          <KotaniSettlementsCard
            data={settlements}
            loading={loading}
            errorMsg={cardErrors.settlements}
          />

          <WeeklyDigestCard />

          <DailySignupsCard data={dailySignups} loading={loading} errorMsg={cardErrors.daily} />

          <CorridorMatrixCard stats={waitlist} loading={loading} errorMsg={cardErrors.waitlist} />

          <ReferralLeaderboardCard data={referrals} loading={loading} errorMsg={cardErrors.referrals} />

          <InvestorLeadsCard data={investors} loading={loading} errorMsg={cardErrors.investors} />

          <BookClicksCard data={bookClicks} loading={loading} errorMsg={cardErrors.bookClicks} />

          <LetterheadCard />

          <PartnerUseCaseCard
            sendsData={useCaseSends}
            loading={loading}
            errorMsg={cardErrors.usecaseSends}
            onSent={load}
          />

          <ToolsCard />
        </ScrollView>
      )}
    </SafeAreaView>
  );
}
