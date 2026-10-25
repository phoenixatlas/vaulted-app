/**
 * FeedbackCard — latest beta tester reports (note, screen, screenshot).
 */
import { useEffect, useState } from "react";
import { View, Text, Image, Pressable, ActivityIndicator, TextInput } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { api, API_BASE } from "@/src/lib/api";
import { colors } from "@/src/lib/theme";
import { s } from "./styles";

type Reply = { id: string; message: string; at: string; by: string };
type Report = {
  id: string; email: string; name?: string; note: string; screen: string; platform: string;
  screenshot_path?: string | null; shot_token?: string; created_at: string; replies?: Reply[];
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
          {(r.replies || []).map((rep) => (
            <View key={rep.id} style={{ marginTop: 6, padding: 8, borderRadius: 8, backgroundColor: colors.brandTertiary }}>
              <Text style={{ fontSize: 11, fontWeight: "700", color: colors.brandDeep }}>{rep.by} · {new Date(rep.at).toLocaleString()}</Text>
              <Text style={{ fontSize: 13, color: colors.onSurface, marginTop: 2 }}>{rep.message}</Text>
            </View>
          ))}
          <ReplyBox
            fbId={r.id}
            onSent={(rep) => setRows((prev) => prev?.map((x) => (x.id === r.id ? { ...x, replies: [...(x.replies || []), rep] } : x)) ?? prev)}
          />
        </View>
      ))}
    </View>
  );
}

function ReplyBox({ fbId, onSent }: { fbId: string; onSent: (r: Reply) => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const send = async () => {
    if (!text.trim()) return;
    setBusy(true);
    setErr("");
    try {
      const res = await api<{ reply: Reply }>(`/admin/feedback/${fbId}/reply`, { method: "POST", body: { message: text.trim() } });
      onSent(res.reply);
      setText("");
    } catch (e: any) { setErr(e?.message || "Reply failed"); }
    finally { setBusy(false); }
  };
  return (
    <View style={{ marginTop: 8 }}>
      <View style={{ flexDirection: "row", gap: 8, alignItems: "center" }}>
        <TextInput
          testID={`feedback-reply-input-${fbId}`}
          value={text}
          onChangeText={setText}
          placeholder="Reply to tester…"
          placeholderTextColor={colors.onSurfaceTertiary}
          style={{ flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingHorizontal: 12, minHeight: 44, color: colors.onSurface, fontSize: 14 }}
        />
        <Pressable
          testID={`feedback-reply-send-${fbId}`}
          onPress={send}
          disabled={busy || !text.trim()}
          style={{ minWidth: 64, minHeight: 44, borderRadius: 10, alignItems: "center", justifyContent: "center", backgroundColor: colors.brand, opacity: busy || !text.trim() ? 0.5 : 1 }}
        >
          {busy ? <ActivityIndicator color={colors.onBrand} /> : <Text style={{ color: colors.onBrand, fontWeight: "700" }}>Reply</Text>}
        </Pressable>
      </View>
      {!!err && <Text style={{ color: colors.error, fontSize: 12, marginTop: 4 }}>{err}</Text>}
    </View>
  );
}
