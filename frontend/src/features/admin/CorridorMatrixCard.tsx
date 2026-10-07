/**
 * CorridorMatrixCard — Heatmap-style breakdown of corridor × direction.
 */
import { View, Text } from "react-native";
import { spacing } from "@/src/lib/theme";
import { CorridorMatrixHeatmap } from "@/src/components/AdminCharts";
import { s } from "./styles";
import type { WaitlistStats } from "./types";

type Props = {
  stats: WaitlistStats | null;
  loading: boolean;
  errorMsg?: string;
};

export function CorridorMatrixCard({ stats, loading, errorMsg }: Props) {
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
