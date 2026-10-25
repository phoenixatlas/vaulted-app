/**
 * TransferTimeline — vertical step list: done ✓ / current (pulsing dot) /
 * pending (hollow) / failed (red ✕), each with an optional detail + time.
 */
import { View, Text, StyleSheet, ActivityIndicator } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, spacing } from "@/src/lib/theme";

export type Step = {
  key: string; label: string; detail?: string | null; at?: string | null;
  state: "done" | "current" | "pending" | "failed";
};

const fmt = (iso?: string | null) => {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
};

export default function TransferTimeline({ steps }: { steps: Step[] }) {
  return (
    <View testID="transfer-timeline">
      {steps.map((s, i) => {
        const last = i === steps.length - 1;
        const tint =
          s.state === "done" ? colors.success :
          s.state === "failed" ? colors.error :
          s.state === "current" ? colors.brand : colors.border;
        return (
          <View key={s.key} style={st.row} testID={`timeline-step-${s.key}`}>
            <View style={st.rail}>
              <View style={[st.dot, { borderColor: tint, backgroundColor: s.state === "done" || s.state === "failed" ? tint : colors.surface }]}>
                {s.state === "done" && <Ionicons name="checkmark" size={13} color="#fff" />}
                {s.state === "failed" && <Ionicons name="close" size={13} color="#fff" />}
                {s.state === "current" && <ActivityIndicator size="small" color={colors.brand} style={{ transform: [{ scale: 0.7 }] }} />}
              </View>
              {!last && <View style={[st.line, { backgroundColor: s.state === "done" ? colors.success : colors.border }]} />}
            </View>
            <View style={[st.content, !last && { paddingBottom: spacing.lg }]}>
              <Text style={[st.label, s.state === "pending" && { color: colors.onSurfaceTertiary }]}>{s.label}</Text>
              {!!s.detail && <Text style={[st.detail, s.state === "failed" && { color: colors.error }]}>{s.detail}</Text>}
              <Text style={st.time} testID={`timeline-state-${s.key}`}>
                {s.state === "current" ? "In progress…" : s.state === "pending" ? "Waiting" : s.state === "failed" ? "Needs attention" : fmt(s.at)}
              </Text>
            </View>
          </View>
        );
      })}
    </View>
  );
}

const st = StyleSheet.create({
  row: { flexDirection: "row", gap: spacing.md },
  rail: { alignItems: "center", width: 24 },
  dot: { width: 24, height: 24, borderRadius: 12, borderWidth: 2, alignItems: "center", justifyContent: "center" },
  line: { width: 2, flex: 1, marginVertical: 2 },
  content: { flex: 1, paddingTop: 2 },
  label: { fontSize: 15, fontWeight: "700", color: colors.onSurface },
  detail: { fontSize: 13, color: colors.onSurfaceSecondary, marginTop: 2 },
  time: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 4 },
});
