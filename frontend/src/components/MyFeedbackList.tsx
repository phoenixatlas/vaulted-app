/**
 * MyFeedbackList — a tester's past reports with the Vaulted team's replies.
 */
import { useEffect, useState } from "react";
import { View, Text, ScrollView, ActivityIndicator, StyleSheet } from "react-native";
import { api } from "@/src/lib/api";
import { colors, spacing, radius } from "@/src/lib/theme";

type Reply = { id: string; message: string; at: string; by: string };
type Report = { id: string; note: string; screen: string; created_at: string; replies?: Reply[]; unread_reply?: boolean };

export default function MyFeedbackList({ onRead }: { onRead: () => void }) {
  const [rows, setRows] = useState<Report[] | null>(null);

  useEffect(() => {
    api<{ feedback: Report[]; unread: number }>("/feedback/mine")
      .then((d) => {
        setRows(d.feedback);
        if (d.unread) api("/feedback/mine/read", { method: "POST" }).then(onRead).catch(() => undefined);
      })
      .catch(() => setRows([]));
  }, [onRead]);

  if (!rows) return <ActivityIndicator color={colors.brand} style={{ marginVertical: spacing.xl }} />;
  if (!rows.length) return <Text style={st.empty}>You haven't sent any feedback yet.</Text>;

  return (
    <ScrollView style={{ maxHeight: 380 }} testID="my-feedback-list">
      {rows.map((r) => (
        <View key={r.id} style={st.item}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            {r.unread_reply && <View style={st.newDot} />}
            <Text style={st.meta}>{new Date(r.created_at).toLocaleDateString()} · {r.screen || "app"}</Text>
          </View>
          <Text style={st.note}>{r.note}</Text>
          {(r.replies || []).map((rep) => (
            <View key={rep.id} style={st.reply} testID={`feedback-reply-${rep.id}`}>
              <Text style={st.replyBy}>{rep.by} replied</Text>
              <Text style={st.replyText}>{rep.message}</Text>
            </View>
          ))}
          {!r.replies?.length && <Text style={st.waiting}>No reply yet</Text>}
        </View>
      ))}
    </ScrollView>
  );
}

const st = StyleSheet.create({
  empty: { color: colors.onSurfaceSecondary, textAlign: "center", marginVertical: spacing.xl },
  item: { paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider },
  meta: { fontSize: 11, color: colors.onSurfaceTertiary },
  note: { fontSize: 14, color: colors.onSurface, marginTop: 4 },
  reply: { marginTop: spacing.sm, padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.brandTertiary },
  replyBy: { fontSize: 11, fontWeight: "700", color: colors.brandDeep },
  replyText: { fontSize: 14, color: colors.onSurface, marginTop: 2 },
  waiting: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 4 },
  newDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.error },
});
