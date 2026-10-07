/**
 * KotaniSettlementsCard — rolls up settled offramp activity by day so
 * operators can watch the rail breathe without pulling raw CSVs. The
 * reconciliation chip is the key signal: a persistent delta_pct > 0.5%
 * on any currency is early-warning that Kotani's effective rate has
 * drifted from our quoted rate (fee change, FX revaluation, etc.).
 */
import { View, Text, ActivityIndicator } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, spacing } from "@/src/lib/theme";
import { s } from "./styles";
import type { SettlementsResp } from "./types";

type Props = {
  data: SettlementsResp | null;
  loading: boolean;
  errorMsg?: string;
};

export function KotaniSettlementsCard({ data, loading, errorMsg }: Props) {
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
