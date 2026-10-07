/**
 * WaitlistCard — corridor breakdown of the marketing waitlist.
 * Renders a "how many joined and where do they want to send to"
 * glanceable summary. Bars are relative to the largest corridor so a
 * small waitlist still fills the card visually.
 */
import { View, Text, ActivityIndicator } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors } from "@/src/lib/theme";
import { s } from "./styles";
import { CORRIDOR_FLAGS, type WaitlistStats } from "./types";

type Props = {
  stats: WaitlistStats | null;
  loading: boolean;
  errorMsg?: string;
};

export function WaitlistCard({ stats, loading, errorMsg }: Props) {
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
