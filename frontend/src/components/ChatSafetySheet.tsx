/**
 * ChatSafetySheet — report / block controls for a conversation (Apple 1.2).
 */
import { useState } from "react";
import { Modal, View, Text, Pressable, StyleSheet, ActivityIndicator } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { colors, spacing, radius } from "@/src/lib/theme";

const REASONS = ["Spam or scam", "Harassment or abuse", "Inappropriate content", "Something else"];

type Props = {
  visible: boolean;
  onClose: () => void;
  conversationId: string;
  contactId?: string;
  blocked: boolean;
  onBlockedChange: (b: boolean) => void;
};

export default function ChatSafetySheet({ visible, onClose, conversationId, contactId, blocked, onBlockedChange }: Props) {
  const [mode, setMode] = useState<"menu" | "report">("menu");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const close = () => { setMode("menu"); setMsg(null); onClose(); };

  const toggleBlock = async () => {
    if (!contactId) return;
    setBusy(true); setMsg(null);
    try {
      await api("/chat/block", { method: "POST", body: { contact_id: contactId, block: !blocked } });
      onBlockedChange(!blocked);
      setMsg(blocked ? "Contact unblocked." : "Contact blocked. They can no longer message you here.");
    } catch (e: any) {
      setMsg(e?.message || "Could not update block.");
    } finally { setBusy(false); }
  };

  const report = async (reason: string) => {
    setBusy(true); setMsg(null);
    try {
      await api("/chat/report", { method: "POST", body: { conversation_id: conversationId, reason, block: true } });
      if (contactId) onBlockedChange(true);
      setMode("menu");
      setMsg("Thanks — our team will review this within 24 hours. The contact has been blocked.");
    } catch (e: any) {
      setMsg(e?.message || "Could not send report.");
    } finally { setBusy(false); }
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={close}>
      <Pressable style={st.backdrop} onPress={close} />
      <View style={st.sheet} testID="chat-safety-sheet">
        <Text style={st.title}>{mode === "report" ? "Why are you reporting?" : "Safety"}</Text>
        {busy && <ActivityIndicator color={colors.brand} />}
        {mode === "menu" ? (
          <>
            <Pressable testID="chat-report-open" onPress={() => setMode("report")} style={st.row}>
              <Ionicons name="flag-outline" size={20} color={colors.error} />
              <Text style={[st.rowText, { color: colors.error }]}>Report conversation</Text>
            </Pressable>
            {!!contactId && (
              <Pressable testID="chat-block-toggle" onPress={toggleBlock} disabled={busy} style={st.row}>
                <Ionicons name={blocked ? "checkmark-circle-outline" : "ban-outline"} size={20} color={colors.onSurface} />
                <Text style={st.rowText}>{blocked ? "Unblock contact" : "Block contact"}</Text>
              </Pressable>
            )}
          </>
        ) : (
          REASONS.map((r) => (
            <Pressable key={r} testID={`chat-report-reason-${r.split(" ")[0].toLowerCase()}`} onPress={() => report(r)} disabled={busy} style={st.row}>
              <Text style={st.rowText}>{r}</Text>
            </Pressable>
          ))
        )}
        {msg && <Text testID="chat-safety-msg" style={st.msg}>{msg}</Text>}
        <Pressable testID="chat-safety-close" onPress={mode === "report" ? () => setMode("menu") : close} style={st.cancel}>
          <Text style={st.cancelText}>{mode === "report" ? "Back" : "Close"}</Text>
        </Pressable>
      </View>
    </Modal>
  );
}

const st = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.5)" },
  sheet: { backgroundColor: colors.surface, padding: spacing.xl, paddingBottom: spacing.xxxl, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, gap: spacing.sm },
  title: { fontSize: 18, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 48, borderBottomWidth: 1, borderBottomColor: colors.divider },
  rowText: { fontSize: 15, color: colors.onSurface },
  msg: { fontSize: 13, color: colors.onSurfaceSecondary, marginTop: spacing.sm },
  cancel: { minHeight: 48, alignItems: "center", justifyContent: "center", marginTop: spacing.sm },
  cancelText: { fontSize: 15, fontWeight: "600", color: colors.brand },
});
