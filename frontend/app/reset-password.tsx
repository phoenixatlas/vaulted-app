import { useEffect, useState } from "react";
import {
  View, Text, TextInput, Pressable, StyleSheet, KeyboardAvoidingView,
  Platform, ScrollView, ActivityIndicator, Image,
} from "react-native";
import { useRouter, useLocalSearchParams } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { colors, spacing, radius, BRAND_IMAGES } from "@/src/lib/theme";

export default function ResetPassword() {
  const router = useRouter();
  const params = useLocalSearchParams<{ token?: string }>();
  const [token, setToken] = useState<string>("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  // Grab the token from the deep-link/web URL once. Falls back to a
  // manual paste field so the flow still works if the deep link fails.
  useEffect(() => {
    if (typeof params.token === "string" && params.token.length > 20) {
      setToken(params.token);
    }
  }, [params.token]);

  const submit = async () => {
    setErr(null);
    const tk = token.trim();
    if (!tk || tk.length < 20) {
      setErr("This reset link is invalid or has expired. Request a new one from the sign-in screen.");
      return;
    }
    if (password.length < 6) {
      setErr("Password must be at least 6 characters.");
      return;
    }
    if (password !== confirm) {
      setErr("Passwords don't match.");
      return;
    }
    setLoading(true);
    try {
      await api("/auth/reset-password", {
        method: "POST",
        body: { token: tk, new_password: password },
        auth: false,
      });
      setDone(true);
    } catch (e: any) {
      setErr(e?.message || "Reset failed. The link may have expired.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={s.root} edges={["top", "bottom"]}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">
          <View style={s.brandBlock}>
            <View style={s.brandRow}>
              <Image source={BRAND_IMAGES.mark} style={s.brandMark} resizeMode="contain" />
              <Text style={s.brandWordmark}>Vaulted</Text>
            </View>
            <Text style={s.brandTagline}>Set new password</Text>
          </View>

          {!done ? (
            <>
              <Text style={s.title}>Choose a new password</Text>
              <Text style={s.subtitle}>Pick something you'll remember. Your funds stay in your self-custody wallet — only the sign-in changes.</Text>

              {!params.token && (
                <View style={s.field}>
                  <Text style={s.label}>Reset token</Text>
                  <TextInput
                    testID="reset-token-input"
                    value={token}
                    onChangeText={setToken}
                    autoCapitalize="none"
                    autoCorrect={false}
                    placeholder="Paste the token from your email"
                    placeholderTextColor={colors.onSurfaceTertiary}
                    style={s.input}
                  />
                  <Text style={s.helperText}>If the reset link didn't auto-fill this, copy it from your email.</Text>
                </View>
              )}

              <View style={s.field}>
                <Text style={s.label}>New password</Text>
                <View style={s.inputRow}>
                  <TextInput
                    testID="reset-password-input"
                    value={password}
                    onChangeText={setPassword}
                    secureTextEntry={!showPw}
                    autoCapitalize="none"
                    placeholder="At least 6 characters"
                    placeholderTextColor={colors.onSurfaceTertiary}
                    style={[s.input, { flex: 1, paddingRight: 44 }]}
                  />
                  <Pressable
                    testID="reset-toggle-visibility"
                    onPress={() => setShowPw((v) => !v)}
                    style={s.eyeBtn}
                    hitSlop={10}
                  >
                    <Ionicons name={showPw ? "eye-off-outline" : "eye-outline"} size={20} color="rgba(245,233,201,0.5)" />
                  </Pressable>
                </View>
              </View>

              <View style={s.field}>
                <Text style={s.label}>Confirm password</Text>
                <TextInput
                  testID="reset-confirm-input"
                  value={confirm}
                  onChangeText={setConfirm}
                  secureTextEntry={!showPw}
                  autoCapitalize="none"
                  placeholder="Retype the same password"
                  placeholderTextColor={colors.onSurfaceTertiary}
                  style={s.input}
                  onSubmitEditing={submit}
                />
              </View>

              {err && <Text testID="reset-error" style={s.error}>{err}</Text>}

              <Pressable
                testID="reset-submit-button"
                onPress={submit}
                disabled={loading}
                style={({ pressed }) => [s.cta, pressed && { opacity: 0.85 }]}
              >
                {loading ? <ActivityIndicator color="#0F0B08" /> : <Text style={s.ctaText}>Update password</Text>}
              </Pressable>
            </>
          ) : (
            <View testID="reset-done" style={s.sentCard}>
              <View style={s.checkCircle}>
                <Ionicons name="checkmark-circle" size={36} color={colors.brand} />
              </View>
              <Text style={s.title}>Password updated</Text>
              <Text style={s.subtitle}>You can now sign in with your new password.</Text>
              <Pressable
                testID="reset-goto-login"
                onPress={() => router.replace("/(auth)/login")}
                style={({ pressed }) => [s.cta, pressed && { opacity: 0.85 }]}
              >
                <Text style={s.ctaText}>Sign in</Text>
              </Pressable>
            </View>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surfaceInverse },
  scroll: { padding: spacing.xl, paddingTop: spacing.xxl, flexGrow: 1, backgroundColor: colors.surfaceInverse },
  brandBlock: { alignItems: "center", marginBottom: spacing.xl, gap: spacing.sm },
  brandRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  brandMark: { width: 52, height: 52 },
  brandWordmark: { fontSize: 28, fontWeight: "700", color: colors.brand, letterSpacing: -1 },
  brandTagline: { fontSize: 11, color: colors.brand, letterSpacing: 2.5, fontWeight: "600", textTransform: "uppercase" },
  title: { fontSize: 26, fontWeight: "700", color: colors.onSurfaceInverse, letterSpacing: -0.6 },
  subtitle: { fontSize: 14, color: "rgba(245,233,201,0.7)", marginTop: spacing.sm, marginBottom: spacing.xl, lineHeight: 20 },
  field: { marginBottom: spacing.lg },
  label: { fontSize: 13, color: "rgba(245,233,201,0.75)", marginBottom: spacing.xs, fontWeight: "500" },
  input: {
    borderWidth: 1, borderColor: colors.borderInverse, borderRadius: radius.md,
    paddingHorizontal: spacing.lg, paddingVertical: 14, fontSize: 16, color: colors.onSurfaceInverse,
    backgroundColor: colors.surfaceInverseSecondary,
  },
  inputRow: { position: "relative" },
  eyeBtn: { position: "absolute", right: 12, top: 0, bottom: 0, alignItems: "center", justifyContent: "center", width: 32 },
  cta: {
    backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: 16,
    alignItems: "center", marginTop: spacing.sm,
  },
  ctaText: { color: "#0F0B08", fontSize: 16, fontWeight: "700", letterSpacing: 0.3 },
  error: { color: "#E0735F", marginBottom: spacing.sm, fontSize: 14, lineHeight: 20 },
  helperText: { fontSize: 12, color: "rgba(245,233,201,0.5)", marginTop: 6, lineHeight: 16 },
  sentCard: { alignItems: "center", gap: spacing.md, marginTop: spacing.md },
  checkCircle: {
    width: 76, height: 76, borderRadius: 38, backgroundColor: "rgba(201,163,91,0.14)",
    alignItems: "center", justifyContent: "center", marginBottom: spacing.md,
    borderWidth: 1, borderColor: "rgba(201,163,91,0.35)",
  },
});
