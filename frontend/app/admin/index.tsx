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
import { useCallback, useEffect, useState } from "react";
import {
  View, Text, Pressable, StyleSheet, ScrollView,
  ActivityIndicator, RefreshControl,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
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

// Country-code → flag emoji. Kept in sync with the landing dropdown so the
// admin dashboard reads the same as the acquisition surface.
const CORRIDOR_FLAGS: Record<string, string> = {
  KE: "🇰🇪", GH: "🇬🇭", NG: "🇳🇬", UG: "🇺🇬",
  TZ: "🇹🇿", ZM: "🇿🇲", ZA: "🇿🇦", XX: "🌐",
};

export default function AdminHome() {
  const router = useRouter();
  const [health, setHealth] = useState<KotaniHealth | null>(null);
  const [waitlist, setWaitlist] = useState<WaitlistStats | null>(null);
  const [investors, setInvestors] = useState<InvestorLeadsResp | null>(null);
  const [dailySignups, setDailySignups] = useState<DailySignupsResp | null>(null);
  const [referrals, setReferrals] = useState<ReferralsResp | null>(null);
  const [bookClicks, setBookClicks] = useState<BookClicksResp | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const [h, w, inv, daily, refs, clicks] = await Promise.all([
        api<KotaniHealth>("/admin/kotani/health").catch((e) => { throw e; }),
        api<WaitlistStats>("/admin/waitlist/stats").catch(() => null),
        api<InvestorLeadsResp>("/admin/investor/leads").catch(() => null),
        api<DailySignupsResp>("/admin/waitlist/analytics/daily-signups?days=30").catch(() => null),
        api<ReferralsResp>("/admin/waitlist/analytics/referrals?limit=10").catch(() => null),
        api<BookClicksResp>("/admin/investor/book-clicks").catch(() => null),
      ]);
      setHealth(h);
      setWaitlist(w);
      setInvestors(inv);
      setDailySignups(daily);
      setReferrals(refs);
      setBookClicks(clicks);
    } catch (e: any) {
      // 403 usually = your account isn't in ADMIN_EMAILS on this environment.
      setErr(e?.message || "Failed to load admin health");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    load();
  }, [load]);

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

      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={s.scrollContent}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brand} />}
      >
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
                  Last checked · {new Date(health.checked_at).toLocaleString()}
                </Text>
                <Pressable onPress={load} style={s.refreshBtn} hitSlop={8}>
                  <Ionicons name="refresh" size={14} color={colors.brand} />
                  <Text style={s.refreshBtnText}>Re-probe</Text>
                </Pressable>
              </View>
            </>
          ) : null}
        </View>

        {/* Waitlist stats card */}
        <WaitlistCard stats={waitlist} loading={loading} />

        {/* Daily signup trend card */}
        <DailySignupsCard data={dailySignups} loading={loading} />

        {/* Corridor × direction matrix card */}
        <CorridorMatrixCard stats={waitlist} loading={loading} />

        {/* Referral leaderboard card */}
        <ReferralLeaderboardCard data={referrals} loading={loading} />

        {/* Investor leads card */}
        <InvestorLeadsCard data={investors} loading={loading} />

        {/* Book-a-call attribution card */}
        <BookClicksCard data={bookClicks} loading={loading} />

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
        </View>
      </ScrollView>
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
  stats, loading,
}: {
  stats: WaitlistStats | null;
  loading: boolean;
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
  if (!stats) return null;  // Fetch failed silently (non-admin, etc.)

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
}: {
  data: DailySignupsResp | null;
  loading: boolean;
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
        <Text style={s.subtle}>Unavailable.</Text>
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
}: {
  stats: WaitlistStats | null;
  loading: boolean;
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
        <Text style={s.subtle}>No data yet.</Text>
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
}: {
  data: ReferralsResp | null;
  loading: boolean;
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
        <Text style={s.subtle}>Unavailable.</Text>
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
}: {
  data: InvestorLeadsResp | null;
  loading: boolean;
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
        <Text style={s.subtle}>Unavailable (endpoint returned an error).</Text>
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
}: {
  data: BookClicksResp | null;
  loading: boolean;
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
        <Text style={s.subtle}>Unavailable (endpoint returned an error).</Text>
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


const s = StyleSheet.create({
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
});
