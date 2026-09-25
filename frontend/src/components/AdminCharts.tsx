/**
 * Analytics chart primitives for the admin dashboard.
 *
 * Pure react-native-svg — no chart libraries added because our chart needs
 * are small and adding a dep for two components would be overkill.
 *
 * Exports:
 *   <DailySignupChart series={[{date, total, outbound, inbound}]} />
 *   <CorridorMatrixHeatmap matrix={[{corridor, direction, count}]}
 *                          corridors={{KE: "Kenya", ...}} />
 *   <ReferralLeaderboard leaders={...} totals={...} />
 */
import { useMemo } from "react";
import { View, Text, StyleSheet } from "react-native";
import Svg, { Path, Circle, Line, Text as SvgText, G } from "react-native-svg";
import { colors, spacing, radius } from "@/src/lib/theme";

// ---------- DailySignupChart ----------
type DailyPoint = { date: string; total: number; outbound: number; inbound: number };

export function DailySignupChart({
  series,
  height = 160,
  width = 320,
}: {
  series: DailyPoint[];
  height?: number;
  width?: number;
}) {
  const { pathTotal, pathInbound, xTicks, yTicks, max, points } = useMemo(() => {
    if (!series.length) {
      return { pathTotal: "", pathInbound: "", xTicks: [], yTicks: [], max: 1, points: [] as any[] };
    }
    const values = series.map((p) => p.total);
    const localMax = Math.max(1, ...values);
    const chartPadding = { top: 16, right: 14, bottom: 22, left: 30 };
    const chartW = width - chartPadding.left - chartPadding.right;
    const chartH = height - chartPadding.top - chartPadding.bottom;

    const sx = (i: number) => chartPadding.left + (i / Math.max(1, series.length - 1)) * chartW;
    const sy = (v: number) => chartPadding.top + chartH - (v / localMax) * chartH;

    // Build SVG path — for a smoother look we use straight line segments
    // (no bezier); with 30 daily points that reads clean enough and stays predictable.
    const buildPath = (getV: (p: DailyPoint) => number) =>
      series
        .map((p, i) => `${i === 0 ? "M" : "L"} ${sx(i).toFixed(1)} ${sy(getV(p)).toFixed(1)}`)
        .join(" ");

    const pts = series.map((p, i) => ({ x: sx(i), y: sy(p.total), ...p }));

    // Show up to 5 x-axis labels evenly spaced across the range
    const xStep = Math.max(1, Math.floor(series.length / 5));
    const xTickPositions = series
      .map((p, i) => ({ i, p }))
      .filter((_, i, arr) => i === 0 || i === arr.length - 1 || i % xStep === 0);

    // y-axis: 0, mid, max
    const yValues = [0, Math.ceil(localMax / 2), localMax];

    return {
      pathTotal: buildPath((p) => p.total),
      pathInbound: buildPath((p) => p.inbound),
      xTicks: xTickPositions,
      yTicks: yValues,
      max: localMax,
      points: pts,
    };
  }, [series, height, width]);

  if (!series.length) {
    return (
      <View style={{ padding: spacing.md, alignItems: "center" }}>
        <Text style={{ color: colors.onSurfaceTertiary, fontSize: 12 }}>No signups in this window yet.</Text>
      </View>
    );
  }

  const chartPadding = { top: 16, right: 14, bottom: 22, left: 30 };
  const chartW = width - chartPadding.left - chartPadding.right;
  const chartH = height - chartPadding.top - chartPadding.bottom;

  return (
    <View>
      <Svg width={width} height={height}>
        {/* y-axis gridlines */}
        {yTicks.map((v, i) => {
          const y = chartPadding.top + chartH - (v / max) * chartH;
          return (
            <G key={`y-${i}`}>
              <Line x1={chartPadding.left} y1={y} x2={width - chartPadding.right} y2={y}
                    stroke={colors.divider} strokeWidth={0.5} strokeDasharray="2,3" />
              <SvgText x={chartPadding.left - 6} y={y + 3} fontSize="9"
                       fill={colors.onSurfaceTertiary} textAnchor="end" fontWeight="600">
                {v}
              </SvgText>
            </G>
          );
        })}

        {/* Inbound line (accent) */}
        {pathInbound && (
          <Path d={pathInbound} stroke={colors.brandDeep} strokeWidth={1.5}
                fill="none" strokeDasharray="3,3" opacity={0.7} />
        )}

        {/* Total line (primary) */}
        <Path d={pathTotal} stroke={colors.brand} strokeWidth={2} fill="none" />

        {/* Point markers — only if fewer than 60 points otherwise it's too dense */}
        {points.length <= 60 && points.map((pt: any, i: number) => (
          <Circle key={`pt-${i}`} cx={pt.x} cy={pt.y} r={2.2} fill={colors.brand} />
        ))}

        {/* x-axis labels */}
        {xTicks.map(({ i, p }: any) => {
          const x = chartPadding.left + (i / Math.max(1, series.length - 1)) * chartW;
          // Format YYYY-MM-DD → "Sep 25"
          const parts = p.date.split("-");
          const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
          const label = `${monthNames[Number(parts[1]) - 1]} ${Number(parts[2])}`;
          return (
            <SvgText key={`x-${i}`} x={x} y={height - 6} fontSize="9"
                     fill={colors.onSurfaceTertiary} textAnchor="middle">
              {label}
            </SvgText>
          );
        })}
      </Svg>

      {/* Legend */}
      <View style={styles.legendRow}>
        <View style={styles.legendItem}>
          <View style={[styles.legendSwatch, { backgroundColor: colors.brand }]} />
          <Text style={styles.legendText}>Total</Text>
        </View>
        <View style={styles.legendItem}>
          <View style={[styles.legendSwatch, { backgroundColor: colors.brandDeep, opacity: 0.7 }]} />
          <Text style={styles.legendText}>Inbound (reverse)</Text>
        </View>
      </View>
    </View>
  );
}

// ---------- CorridorMatrixHeatmap ----------
type MatrixEntry = { corridor: string; corridor_name: string; direction: string; count: number };

export function CorridorMatrixHeatmap({
  matrix,
  corridors,
}: {
  matrix: MatrixEntry[];
  corridors: Record<string, string>;
}) {
  // Build a 2D count grid keyed by corridor + direction.
  const { rows, maxCount } = useMemo(() => {
    const dict: Record<string, { outbound: number; inbound: number }> = {};
    let localMax = 0;
    for (const m of matrix) {
      if (!m.corridor || m.corridor === "XX") continue;
      const cell = (dict[m.corridor] = dict[m.corridor] || { outbound: 0, inbound: 0 });
      const dir = m.direction === "inbound" ? "inbound" : "outbound";
      cell[dir] += m.count;
      if (cell[dir] > localMax) localMax = cell[dir];
    }
    const list = Object.entries(dict)
      .map(([code, cell]) => ({
        code,
        name: corridors[code] || code,
        outbound: cell.outbound,
        inbound: cell.inbound,
      }))
      .sort((a, b) => (b.outbound + b.inbound) - (a.outbound + a.inbound));
    return { rows: list, maxCount: Math.max(1, localMax) };
  }, [matrix, corridors]);

  if (!rows.length) {
    return (
      <View style={{ padding: spacing.md, alignItems: "center" }}>
        <Text style={{ color: colors.onSurfaceTertiary, fontSize: 12 }}>No corridor breakdowns yet.</Text>
      </View>
    );
  }

  // Heatmap cell colour — brand-gold at max, transparent at 0.
  const cellColor = (count: number) => {
    const alpha = Math.max(0.06, Math.min(1, count / maxCount));
    return `rgba(201, 163, 91, ${alpha.toFixed(2)})`;
  };

  return (
    <View>
      {/* Header row */}
      <View style={styles.matrixHeader}>
        <Text style={[styles.matrixHeaderText, { flex: 2 }]}>Corridor</Text>
        <Text style={[styles.matrixHeaderText, styles.matrixHeaderCell]}>UK/EU → Africa</Text>
        <Text style={[styles.matrixHeaderText, styles.matrixHeaderCell]}>Africa → UK/EU</Text>
      </View>
      {rows.map((r) => (
        <View key={r.code} style={styles.matrixRow}>
          <View style={{ flex: 2, flexDirection: "row", alignItems: "center", gap: 8 }}>
            <Text style={styles.matrixCode}>{r.code}</Text>
            <Text style={styles.matrixName}>{r.name}</Text>
          </View>
          <View style={[styles.matrixCell, { backgroundColor: cellColor(r.outbound) }]}>
            <Text style={[styles.matrixCount, r.outbound === 0 && { opacity: 0.4 }]}>{r.outbound}</Text>
          </View>
          <View style={[styles.matrixCell, { backgroundColor: cellColor(r.inbound) }]}>
            <Text style={[styles.matrixCount, r.inbound === 0 && { opacity: 0.4 }]}>{r.inbound}</Text>
          </View>
        </View>
      ))}
    </View>
  );
}

// ---------- ReferralLeaderboard ----------
type Leader = {
  email_redacted: string;
  email_hash: string;
  referral_count: number;
  corridor?: string;
  founding_member: boolean;
};

export function ReferralLeaderboard({
  leaders,
  totals,
}: {
  leaders: Leader[];
  totals: {
    total_referred_signups: number;
    founding_members: number;
    boost_interval: number;
    boost_spots: number;
    founding_threshold: number;
  };
}) {
  if (!leaders.length) {
    return (
      <View style={{ paddingTop: spacing.sm }}>
        <Text style={{ color: colors.onSurfaceTertiary, fontSize: 12 }}>
          No referrals yet. Every {totals.boost_interval} referrals moves the referrer up {totals.boost_spots} spots; {totals.founding_threshold}+ unlocks a Founding Member badge.
        </Text>
      </View>
    );
  }
  return (
    <View style={{ marginTop: spacing.sm }}>
      <View style={styles.leaderStatsRow}>
        <View style={styles.leaderStat}>
          <Text style={styles.leaderStatNum}>{totals.total_referred_signups}</Text>
          <Text style={styles.leaderStatLabel}>referred signups</Text>
        </View>
        <View style={styles.leaderStat}>
          <Text style={[styles.leaderStatNum, { color: colors.brand }]}>{totals.founding_members}</Text>
          <Text style={styles.leaderStatLabel}>founding members</Text>
        </View>
      </View>
      {leaders.map((l, idx) => (
        <View key={l.email_hash + idx} style={styles.leaderRow}>
          <View style={styles.leaderRank}>
            <Text style={styles.leaderRankText}>{idx + 1}</Text>
          </View>
          <View style={{ flex: 1 }}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
              <Text style={styles.leaderEmail}>{l.email_redacted}</Text>
              {l.founding_member && (
                <View style={styles.foundingBadge}>
                  <Text style={styles.foundingBadgeText}>FOUNDING</Text>
                </View>
              )}
            </View>
            {l.corridor && <Text style={styles.leaderCorridor}>Corridor: {l.corridor}</Text>}
          </View>
          <View style={styles.leaderRefCount}>
            <Text style={styles.leaderRefNum}>{l.referral_count}</Text>
            <Text style={styles.leaderRefLabel}>refs</Text>
          </View>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  legendRow: {
    flexDirection: "row",
    gap: spacing.md,
    marginTop: 6,
    marginLeft: 30,
  },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 6 },
  legendSwatch: { width: 12, height: 3, borderRadius: 2 },
  legendText: { fontSize: 10, color: colors.onSurfaceSecondary, fontWeight: "600" },

  matrixHeader: {
    flexDirection: "row",
    paddingBottom: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.divider,
    marginBottom: 4,
    alignItems: "center",
  },
  matrixHeaderText: { fontSize: 10, color: colors.onSurfaceTertiary, fontWeight: "700", letterSpacing: 0.5 },
  matrixHeaderCell: { flex: 1, textAlign: "center" },
  matrixRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 8,
    gap: 6,
  },
  matrixCode: {
    fontSize: 11, fontWeight: "800",
    color: colors.brandDeep,
    backgroundColor: colors.brandTertiary,
    paddingHorizontal: 8, paddingVertical: 3,
    borderRadius: radius.pill, letterSpacing: 0.5,
  },
  matrixName: { fontSize: 13, color: colors.onSurface, fontWeight: "600" },
  matrixCell: {
    flex: 1,
    alignItems: "center", justifyContent: "center",
    paddingVertical: 10,
    borderRadius: radius.sm,
    borderWidth: 1, borderColor: colors.divider,
  },
  matrixCount: { fontSize: 15, fontWeight: "700", color: colors.onSurface },

  leaderStatsRow: {
    flexDirection: "row",
    gap: 12,
    marginBottom: spacing.md,
    padding: 10,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border,
  },
  leaderStat: { flex: 1, alignItems: "center" },
  leaderStatNum: { fontSize: 20, fontWeight: "800", color: colors.onSurface, letterSpacing: -0.5 },
  leaderStatLabel: { fontSize: 10, color: colors.onSurfaceSecondary, marginTop: 2, letterSpacing: 0.3 },
  leaderRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingVertical: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.divider,
  },
  leaderRank: {
    width: 26, height: 26, borderRadius: 999,
    backgroundColor: colors.brandTertiary,
    alignItems: "center", justifyContent: "center",
  },
  leaderRankText: { fontSize: 11, fontWeight: "800", color: colors.brandDeep },
  leaderEmail: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  leaderCorridor: { fontSize: 10, color: colors.onSurfaceTertiary, marginTop: 2 },
  leaderRefCount: { alignItems: "flex-end", minWidth: 44 },
  leaderRefNum: { fontSize: 16, fontWeight: "800", color: colors.brand },
  leaderRefLabel: { fontSize: 9, color: colors.onSurfaceTertiary, letterSpacing: 0.3, fontWeight: "600" },
  foundingBadge: {
    paddingHorizontal: 6, paddingVertical: 2,
    borderRadius: radius.pill,
    backgroundColor: colors.brand,
  },
  foundingBadgeText: { color: "#0F0B08", fontSize: 8, fontWeight: "800", letterSpacing: 0.6 },
});
