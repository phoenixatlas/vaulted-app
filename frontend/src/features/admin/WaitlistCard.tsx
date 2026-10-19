/**
 * WaitlistCard — corridor breakdown of the marketing waitlist.
 * Renders a "how many joined and where do they want to send to"
 * glanceable summary. Bars are relative to the largest corridor so a
 * small waitlist still fills the card visually.
 *
 * NEW: shows a server-side `fetched_at` timestamp AND a "peek" button
 * that pulls the 20 most recent signups directly from Mongo so admins
 * can visually reconcile a user's report ("I just joined as #9")
 * against ground truth. All diagnostic requests use `no-store` on the
 * backend and append a cache-buster param here, so no CDN/browser
 * cache can hide a fresh row.
 */
import { useState } from "react";
import { View, Text, ActivityIndicator, Pressable, ScrollView } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, spacing, radius } from "@/src/lib/theme";
import { s } from "./styles";
import { api } from "@/src/lib/api";
import {
  CORRIDOR_FLAGS,
  type WaitlistStats,
  type WaitlistRecentResp,
  type WaitlistRecentRow,
} from "./types";

type Props = {
  stats: WaitlistStats | null;
  loading: boolean;
  errorMsg?: string;
};

function timeAgo(iso?: string): string {
  if (!iso) return "unknown";
  const then = Date.parse(iso);
  if (!isFinite(then)) return "unknown";
  const diff = Date.now() - then;
  if (diff < 10_000) return "just now";
  if (diff < 60_000) return `${Math.floor(diff / 1000)}s ago`;
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return `${Math.floor(diff / 86_400_000)}d ago`;
}

function maskEmail(email: string): string {
  // Keep first 3 chars + domain for admin visual check, redact the rest.
  // We're an admin surface so this is defence-in-depth more than a hard
  // requirement, but it keeps screenshots shareable with investors.
  const [local = "", domain = ""] = (email || "").split("@");
  if (!domain) return email;
  const visible = local.slice(0, Math.min(3, local.length));
  const hidden = "•".repeat(Math.max(1, local.length - visible.length));
  return `${visible}${hidden}@${domain}`;
}

export function WaitlistCard({ stats, loading, errorMsg }: Props) {
  const [peekOpen, setPeekOpen] = useState(false);
  const [peekLoading, setPeekLoading] = useState(false);
  const [peekData, setPeekData] = useState<WaitlistRecentResp | null>(null);
  const [peekError, setPeekError] = useState<string | null>(null);

  const openPeek = async () => {
    setPeekOpen(true);
    setPeekLoading(true);
    setPeekError(null);
    try {
      // Cache-buster `_t` param guarantees no intermediate (SW/CDN) hands
      // us a stale body. Backend also sets `Cache-Control: no-store`.
      const res = await api<WaitlistRecentResp>(
        `/admin/waitlist/recent?limit=20&_t=${Date.now()}`,
      );
      setPeekData(res);
    } catch (e: any) {
      setPeekError(e?.message || "Could not load recent signups");
    } finally {
      setPeekLoading(false);
    }
  };

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

      {/* Freshness line — tells the operator the exact server-side
          moment this count was computed. Pulling-to-refresh updates it. */}
      <View style={localStyles.freshRow}>
        <Ionicons name="time-outline" size={11} color={colors.onSurfaceTertiary} />
        <Text style={localStyles.freshText}>
          Count fetched {timeAgo(stats.fetched_at)}
          {stats.fetched_at ? ` · ${new Date(stats.fetched_at).toLocaleTimeString()}` : ""}
        </Text>
        <View style={{ flex: 1 }} />
        <Pressable
          testID="waitlist-peek"
          onPress={openPeek}
          style={({ pressed }) => [localStyles.peekBtn, pressed && { opacity: 0.6 }]}
        >
          <Ionicons name="eye-outline" size={12} color={colors.brandDeep} />
          <Text style={localStyles.peekBtnText}>Peek recent</Text>
        </Pressable>
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

      {/* Diagnostic peek: the 20 newest signups, straight from Mongo.
          Collapses by default so the card stays small; expanding is a
          one-tap operation designed for exactly this kind of "did my
          user land in the DB?" reconciliation. */}
      {peekOpen && (
        <View style={localStyles.peekPanel}>
          <View style={localStyles.peekHeader}>
            <Ionicons name="list-outline" size={14} color={colors.brandDeep} />
            <Text style={localStyles.peekTitle}>
              Most recent signups
              {peekData ? ` (showing ${peekData.count} of ${peekData.total})` : ""}
            </Text>
            <View style={{ flex: 1 }} />
            <Pressable
              testID="waitlist-peek-refresh"
              onPress={openPeek}
              disabled={peekLoading}
              hitSlop={6}
            >
              <Ionicons
                name={peekLoading ? "sync" : "refresh"}
                size={14}
                color={colors.brandDeep}
              />
            </Pressable>
            <Pressable
              testID="waitlist-peek-close"
              onPress={() => setPeekOpen(false)}
              hitSlop={6}
              style={{ marginLeft: 8 }}
            >
              <Ionicons name="close" size={14} color={colors.onSurfaceSecondary} />
            </Pressable>
          </View>
          {peekLoading && !peekData ? (
            <View style={{ paddingVertical: 10 }}>
              <ActivityIndicator color={colors.brand} />
            </View>
          ) : peekError ? (
            <Text style={localStyles.peekError}>⚠ {peekError}</Text>
          ) : peekData && peekData.rows.length === 0 ? (
            <Text style={localStyles.peekEmpty}>Mongo returned 0 rows.</Text>
          ) : peekData ? (
            <ScrollView style={{ maxHeight: 280 }} nestedScrollEnabled>
              {peekData.rows.map((r: WaitlistRecentRow, idx: number) => {
                const pos = peekData.total - idx; // newest row = highest position
                return (
                  <View key={`${r.email}-${idx}`} style={localStyles.peekRow}>
                    <View style={localStyles.peekPos}>
                      <Text style={localStyles.peekPosText}>#{pos}</Text>
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={localStyles.peekEmail} numberOfLines={1}>
                        {maskEmail(r.email)}
                      </Text>
                      <Text style={localStyles.peekMeta} numberOfLines={1}>
                        {r.joined_at
                          ? new Date(r.joined_at).toLocaleString()
                          : "no timestamp"}
                        {r.corridor ? ` · ${r.corridor}` : ""}
                        {r.direction ? ` · ${r.direction}` : ""}
                        {r.source ? ` · ${r.source}` : ""}
                      </Text>
                    </View>
                  </View>
                );
              })}
              {peekData.fetched_at && (
                <Text style={localStyles.peekFooter}>
                  Pulled live {timeAgo(peekData.fetched_at)}
                </Text>
              )}
            </ScrollView>
          ) : null}
        </View>
      )}
    </View>
  );
}

// Private styles — stay in this file because they're all specific to the
// freshness/peek diagnostic UI nobody else needs.
import { StyleSheet } from "react-native";

const localStyles = StyleSheet.create({
  freshRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginTop: spacing.xs,
    marginBottom: spacing.sm,
    paddingHorizontal: 2,
  },
  freshText: {
    fontSize: 10,
    color: colors.onSurfaceTertiary,
    fontWeight: "500",
  },
  peekBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    backgroundColor: colors.brandTertiary,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: "rgba(201,163,91,0.35)",
  },
  peekBtnText: {
    fontSize: 10,
    fontWeight: "700",
    color: colors.brandDeep,
    letterSpacing: 0.2,
  },
  peekPanel: {
    marginTop: spacing.md,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  peekHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginBottom: spacing.sm,
  },
  peekTitle: {
    fontSize: 11,
    fontWeight: "700",
    color: colors.onSurface,
    letterSpacing: 0.3,
  },
  peekRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingVertical: 6,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(0,0,0,0.04)",
  },
  peekPos: {
    minWidth: 38,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: radius.sm,
    backgroundColor: colors.surfaceSecondary,
    alignItems: "center",
  },
  peekPosText: {
    fontSize: 10,
    fontWeight: "800",
    color: colors.brandDeep,
  },
  peekEmail: {
    fontSize: 12,
    fontWeight: "600",
    color: colors.onSurface,
  },
  peekMeta: {
    fontSize: 10,
    color: colors.onSurfaceTertiary,
    marginTop: 1,
  },
  peekError: {
    fontSize: 11,
    color: colors.error,
    paddingVertical: 6,
  },
  peekEmpty: {
    fontSize: 11,
    color: colors.onSurfaceSecondary,
    paddingVertical: 6,
  },
  peekFooter: {
    fontSize: 9,
    color: colors.onSurfaceTertiary,
    textAlign: "center",
    paddingTop: 8,
    fontStyle: "italic",
  },
});

/**
 * CorridorBar — one row of the corridor breakdown histogram.
 * Width proportional to count / max; percent label on the right.
 */
function CorridorBar({
  code,
  name,
  count,
  max,
  total,
}: {
  code: string;
  name: string;
  count: number;
  max: number;
  total: number;
}) {
  const widthPct = Math.max(4, Math.round((count / max) * 100));
  const sharePct = Math.round((count / total) * 100);
  const flag = CORRIDOR_FLAGS[code] || "🌍";
  return (
    <View style={s.corridorRow}>
      <View style={s.corridorHeader}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          <Text style={{ fontSize: 14 }}>{flag}</Text>
          <Text style={s.corridorName}>{name}</Text>
        </View>
        <Text style={s.corridorCount}>
          {count} <Text style={s.corridorShare}>({sharePct}%)</Text>
        </Text>
      </View>
      <View style={s.corridorBarTrack}>
        <View style={[s.corridorBarFill, { width: `${widthPct}%` }]} />
      </View>
    </View>
  );
}
