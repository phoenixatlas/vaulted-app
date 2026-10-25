/**
 * FeedbackCard — latest beta tester reports (note, screen, screenshot).
 */
import { useEffect, useState } from "react";
import { View, Text, Image, Pressable, ActivityIndicator } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { api, API_BASE } from "@/src/lib/api";
import { colors } from "@/src/lib/theme";
import { s } from "./styles";

type Report = {
  id: string; email: string; name?: string; note: string; screen: string; platform: string;
  screenshot_path?: string | null; shot_token?: string; created_at: string;
};

export function FeedbackCard() {
  const [rows, setRows] = useState<Report[] | null>(null);
  const [total, setTotal] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  useEffect(() => {
    api<{ feedback: Report[]; total: number }>("/admin/feedback")
      .then((d) => { setRows(d.feedback); setTotal(d.total); })
      .catch((e) => setErr(e?.message || "Load failed"));
  }, []);

  // Short-lived per-screenshot token from the list call — works in <img> on web and Image on native.
  const shotSource = (r: Report) => ({
    uri: `${API_BASE}/api/admin/feedback/${r.id}/screenshot?t=${encodeURIComponent(r.shot_token || "")}`,
  });

  return (
    <View style={s.card} testID="admin-feedback-card">
      <View style={s.cardHeaderRow}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Ionicons name="chatbox-ellipses" size={18} color={colors.brand} />
          <Text style={s.cardTitle}>Beta feedback{rows ? ` · ${total}` : ""}</Text>
        </View>
        {!rows && !err && <ActivityIndicator color={colors.brand} />}
      </View>
      {err && (
        <View style={s.errorBox}>
          <Ionicons name="alert-circle-outline" size={18} color={colors.error} />
          <Text style={s.errorText}>{err}</Text>
        </View>
      )}
      {rows && rows.length === 0 && <Text style={{ color: colors.onSurfaceSecondary, marginTop: 8 }}>No feedback yet.</Text>}
      {rows?.map((r) => (
        <View key={r.id} style={{ borderTopWidth: 1, borderTopColor: colors.divider, paddingVertical: 10 }}>
          <Text style={{ fontSize: 14, color: colors.onSurface }}>{r.note}</Text>
          <Text style={{ fontSize: 11, color: colors.onSurfaceTertiary, marginTop: 4 }}>
            {r.email} · {r.screen || "?"} · {r.platform} · {new Date(r.created_at).toLocaleString()}
          </Text>
          {!!r.screenshot_path && !!r.shot_token && (
            openId === r.id ? (
              <Pressable onPress={() => setOpenId(null)}>
                <Image source={shotSource(r)} style={{ width: "100%", height: 420, marginTop: 8, borderRadius: 8 }} resizeMode="contain" />
              </Pressable>
            ) : (
              <Pressable testID={`feedback-shot-${r.id}`} onPress={() => setOpenId(r.id)} style={{ minHeight: 36, justifyContent: "center" }}>
                <Text style={{ color: colors.brandDeep, fontWeight: "700", fontSize: 12 }}>View screenshot</Text>
              </Pressable>
            )
          )}
        </View>
      ))}
    </View>
  );
}
