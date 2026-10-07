/**
 * KotaniHealthCard
 * ================
 * Live sandbox health + per-service probes with pull-to-refresh.
 * Delegates refetch to the parent via `onReprobe` so the parent's
 * global `loading` flag stays authoritative.
 */
import { View, Text, Pressable, ActivityIndicator } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors } from "@/src/lib/theme";
import { s } from "./styles";
import { ProbeRow } from "./common";
import type { KotaniHealth } from "./types";

type Props = {
  health: KotaniHealth | null;
  loading: boolean;
  errorMsg?: string;
  globalErr?: string | null;
  onReprobe: () => void;
};

export function KotaniHealthCard({ health, loading, errorMsg, globalErr, onReprobe }: Props) {
  return (
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

      {loading && !health ? (
        <View style={s.loadingBox}>
          <ActivityIndicator color={colors.brand} />
          <Text style={s.loadingText}>Probing Kotani sandbox…</Text>
        </View>
      ) : (errorMsg && !health) ? (
        <View style={s.errorBox}>
          <Ionicons name="alert-circle-outline" size={18} color={colors.error} />
          <Text style={s.errorText}>{errorMsg}</Text>
        </View>
      ) : globalErr ? (
        <View style={s.errorBox}>
          <Ionicons name="alert-circle-outline" size={18} color={colors.error} />
          <Text style={s.errorText}>{globalErr}</Text>
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
              onPress={onReprobe}
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
  );
}
