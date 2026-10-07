/**
 * DailySignupsCard — Line chart of daily waitlist signups over the
 * last 30 days. Includes totals summary + peak day.
 */
import { View, Text } from "react-native";
import { spacing } from "@/src/lib/theme";
import { DailySignupChart } from "@/src/components/AdminCharts";
import { s } from "./styles";
import type { DailySignupsResp } from "./types";

type Props = {
  data: DailySignupsResp | null;
  loading: boolean;
  errorMsg?: string;
};

export function DailySignupsCard({ data, loading, errorMsg }: Props) {
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
