/**
 * DeleteAccountSheet — permanent account deletion (App Store 5.1.1(v)).
 * Asks for the password, then calls POST /auth/delete-account.
 */
import { useState } from "react";
import {
  Modal, View, Text, TextInput, Pressable, ActivityIndicator, StyleSheet,
  KeyboardAvoidingView, Platform,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { colors, spacing, radius } from "@/src/lib/theme";

type Props = { visible: boolean; onClose: () => void; onDeleted: () => void };

export default function DeleteAccountSheet({ visible, onClose, onDeleted }: Props) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const close = () => { setPassword(""); setErr(null); onClose(); };

  const confirm = async () => {
    if (!password) { setErr("Enter your password to confirm."); return; }
    setBusy(true);
    setErr(null);
    try {
      await api("/auth/delete-account", { method: "POST", body: { password } });
      setPassword("");
      onDeleted();
    } catch (e: any) {
      setErr(e?.status === 403 ? "Incorrect password." : e?.message || "Could not delete account.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={close}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={st.backdrop}>
        <Pressable style={{ flex: 1 }} onPress={close} />
        <View style={st.sheet} testID="delete-account-sheet">
          <View style={st.iconWrap}><Ionicons name="trash-outline" size={24} color={colors.error} /></View>
          <Text style={st.title}>Delete your account?</Text>
          <Text style={st.body}>
            This permanently removes your profile, wallet keys stored with Vaulted, contacts and chats.
            Back up your recovery phrase first. Any funds still in your wallet stay on-chain and can only
            be reached with that phrase. Records of past transfers are kept, without your details, because
            the law requires it.
          </Text>
          <TextInput
            testID="delete-account-password"
            value={password}
            onChangeText={setPassword}
            placeholder="Your password"
            placeholderTextColor={colors.onSurfaceTertiary}
            secureTextEntry
            autoCapitalize="none"
            style={st.input}
          />
          {err && <Text style={st.err}>{err}</Text>}
          <Pressable testID="delete-account-confirm" onPress={confirm} disabled={busy} style={[st.danger, busy && { opacity: 0.7 }]}>
            {busy ? <ActivityIndicator color="#fff" /> : <Text style={st.dangerText}>Delete permanently</Text>}
          </Pressable>
          <Pressable testID="delete-account-cancel" onPress={close} style={st.cancel}>
            <Text style={st.cancelText}>Cancel</Text>
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const st = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)" },
  sheet: { backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.xl, paddingBottom: spacing.xl + 16 },
  iconWrap: { width: 48, height: 48, borderRadius: 24, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", alignSelf: "center", marginBottom: spacing.md },
  title: { fontSize: 18, fontWeight: "700", color: colors.onSurface, textAlign: "center" },
  body: { fontSize: 13, lineHeight: 19, color: colors.onSurfaceSecondary, marginTop: spacing.sm, marginBottom: spacing.lg, textAlign: "center" },
  input: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.lg, paddingVertical: 14, fontSize: 15, color: colors.onSurface, backgroundColor: colors.surfaceSecondary },
  err: { color: colors.error, fontSize: 13, marginTop: spacing.sm },
  danger: { backgroundColor: colors.error, borderRadius: radius.md, paddingVertical: 15, alignItems: "center", marginTop: spacing.lg, minHeight: 48, justifyContent: "center" },
  dangerText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  cancel: { paddingVertical: 14, alignItems: "center", minHeight: 44 },
  cancelText: { color: colors.onSurfaceSecondary, fontWeight: "600", fontSize: 15 },
});
