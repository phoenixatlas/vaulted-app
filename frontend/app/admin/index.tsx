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

export default function AdminHome() {
  const router = useRouter();
  const [health, setHealth] = useState<KotaniHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const r = await api<KotaniHealth>("/admin/kotani/health");
      setHealth(r);
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
});
