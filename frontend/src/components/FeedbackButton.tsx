/**
 * FeedbackButton — floating "Feedback" pill for beta testers.
 * Only rendered while Beta test mode is on and someone is signed in.
 * On phones it grabs a screenshot of the current screen before the form
 * opens; on web it sends the note only.
 */
import { useState } from "react";
import {
  View, Text, Pressable, Modal, TextInput, Image, Switch, ActivityIndicator,
  StyleSheet, Platform, KeyboardAvoidingView,
} from "react-native";
import { usePathname } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Constants from "expo-constants";
import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "@/src/lib/auth";
import { useAppConfig } from "@/src/lib/appConfig";
import { API_BASE, getToken } from "@/src/lib/api";
import { uploadForm } from "@/src/utils/upload";
import { colors, spacing, radius } from "@/src/lib/theme";

export default function FeedbackButton() {
  const { user } = useAuth();
  const cfg = useAppConfig();
  const pathname = usePathname();
  const insets = useSafeAreaInsets();
  const [open, setOpen] = useState(false);
  const [shot, setShot] = useState<string | null>(null);
  const [includeShot, setIncludeShot] = useState(true);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<"idle" | "sent" | "error">("idle");
  const [err, setErr] = useState("");

  if (!user || !cfg?.beta_test_mode) return null;

  const start = async () => {
    setShot(null);
    if (Platform.OS !== "web") {
      try {
        const { captureScreen } = await import("react-native-view-shot");
        setShot(await captureScreen({ format: "jpg", quality: 0.6 }));
      } catch { setShot(null); }
    }
    setIncludeShot(true);
    setStatus("idle");
    setOpen(true);
  };

  const close = () => { setOpen(false); setNote(""); setErr(""); };

  const send = async () => {
    if (!note.trim()) { setErr("Tell us what happened."); return; }
    setBusy(true);
    setErr("");
    try {
      const token = await getToken();
      const res = await uploadForm(`${API_BASE}/api/feedback`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        fields: {
          note: note.trim(), screen: pathname || "", platform: Platform.OS,
          app_version: String(Constants.expoConfig?.version ?? ""),
        },
        files: shot && includeShot ? { screenshot: { uri: shot, name: "screenshot.jpg", mimeType: "image/jpeg" } } : {},
      });
      if (!res.ok) throw new Error(`Failed (${res.status})`);
      setStatus("sent");
      setNote("");
    } catch (e: any) {
      setStatus("error");
      setErr(e?.message || "Could not send feedback.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Pressable
        testID="feedback-fab"
        onPress={start}
        accessibilityLabel="Send beta feedback"
        style={[st.fab, { top: "58%" }]}
      >
        <Ionicons name="chatbox-ellipses" size={18} color={colors.onBrand} />
      </Pressable>

      <Modal visible={open} transparent animationType="slide" onRequestClose={close}>
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={st.backdrop}>
          <Pressable style={{ flex: 1 }} onPress={close} />
          <View style={[st.sheet, { paddingBottom: insets.bottom + spacing.lg }]} testID="feedback-sheet">
            {status === "sent" ? (
              <View style={{ alignItems: "center", paddingVertical: spacing.lg }}>
                <Ionicons name="checkmark-circle" size={44} color={colors.success} />
                <Text style={st.title}>Thanks, that's been sent</Text>
                <Text style={st.sub}>The Vaulted team will take a look.</Text>
                <Pressable testID="feedback-done" onPress={close} style={st.primary}><Text style={st.primaryText}>Done</Text></Pressable>
              </View>
            ) : (
              <>
                <Text style={st.title}>Send feedback</Text>
                <Text style={st.sub}>What went wrong, or what could be better?</Text>
                <TextInput
                  testID="feedback-note"
                  value={note}
                  onChangeText={(v) => { setNote(v); if (err) setErr(""); }}
                  placeholder="e.g. The rate didn't load on the Send screen"
                  placeholderTextColor={colors.onSurfaceTertiary}
                  multiline
                  style={st.input}
                />
                {shot ? (
                  <View style={st.shotRow}>
                    <Image source={{ uri: shot }} style={st.thumb} />
                    <Text style={st.shotLabel}>Include screenshot</Text>
                    <Switch testID="feedback-include-shot" value={includeShot} onValueChange={setIncludeShot}
                      trackColor={{ true: colors.brand, false: colors.border }} />
                  </View>
                ) : (
                  <Text style={st.hint}>{Platform.OS === "web" ? "Screenshots are only attached from the phone app." : "Screenshot unavailable for this screen."}</Text>
                )}
                {!!err && <Text style={st.err}>{err}</Text>}
                <Pressable testID="feedback-send" onPress={send} disabled={busy} style={[st.primary, busy && { opacity: 0.7 }]}>
                  {busy ? <ActivityIndicator color={colors.onBrand} /> : <Text style={st.primaryText}>Send</Text>}
                </Pressable>
                <Pressable onPress={close} style={st.cancel}><Text style={st.cancelText}>Cancel</Text></Pressable>
              </>
            )}
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </>
  );
}

const st = StyleSheet.create({
  // Slim tab hugging the right edge so it never covers inputs or buttons.
  fab: {
    position: "absolute", right: 0, width: 44, height: 48, alignItems: "center", justifyContent: "center",
    backgroundColor: colors.brand, borderTopLeftRadius: radius.md, borderBottomLeftRadius: radius.md, opacity: 0.92,
    shadowColor: "#000", shadowOpacity: 0.2, shadowRadius: 8, shadowOffset: { width: 0, height: 3 }, elevation: 6,
  },
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)" },
  sheet: { backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.xl },
  title: { fontSize: 18, fontWeight: "700", color: colors.onSurface, marginTop: spacing.sm },
  sub: { fontSize: 13, color: colors.onSurfaceSecondary, marginTop: 4, marginBottom: spacing.md },
  input: {
    minHeight: 110, textAlignVertical: "top", borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    padding: spacing.md, fontSize: 15, color: colors.onSurface, backgroundColor: colors.surfaceSecondary,
  },
  shotRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, marginTop: spacing.md },
  thumb: { width: 44, height: 80, borderRadius: 6, borderWidth: 1, borderColor: colors.border },
  shotLabel: { flex: 1, fontSize: 14, color: colors.onSurface, fontWeight: "500" },
  hint: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: spacing.sm },
  err: { color: colors.error, fontSize: 13, marginTop: spacing.sm },
  primary: { backgroundColor: colors.brand, borderRadius: radius.md, minHeight: 48, alignItems: "center", justifyContent: "center", marginTop: spacing.lg, alignSelf: "stretch" },
  primaryText: { color: colors.onBrand, fontWeight: "700", fontSize: 15 },
  cancel: { minHeight: 44, alignItems: "center", justifyContent: "center" },
  cancelText: { color: colors.onSurfaceSecondary, fontWeight: "600" },
});
