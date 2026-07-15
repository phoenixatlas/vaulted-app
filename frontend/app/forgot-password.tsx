import { useState } from "react";
import {
  View, Text, TextInput, Pressable, StyleSheet, KeyboardAvoidingView,
  Platform, ScrollView, ActivityIndicator, Image,
} from "react-native";
import { useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { colors, spacing, radius, BRAND_IMAGES } from "@/src/lib/theme";

export default function ForgotPassword() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  const submit = async () => {
    setErr(null);
    const trimmed = email.trim().toLowerCase();
    if (!trimmed || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) {
      setErr("Enter a valid email address");
      return;
    }
    setLoading(true);
    try {
      await api("/auth/forgot-password", { method: "POST", body: { email: trimmed }, auth: false });
      setSent(true);
    } catch (e: any) {
      // Even on error, show the generic "sent" UI so we never leak enumeration signal.
      setSent(true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={s.root} edges={["top", "bottom"]}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">
          <Pressable testID="forgot-back" onPress={() => router.back()} style={s.backBtn} hitSlop={12}>
            <Ionicons name="chevron-back" size={26} color={colors.brand} />
          </Pressable>

          <View style={s.brandBlock}>
            <View style={s.brandRow}>
              <Image source={BRAND_IMAGES.mark} style={s.brandMark} resizeMode="contain" />
              <Text style={s.brandWordmark}>Vaulted</Text>
            </View>
            <Text style={s.brandTagline}>Password Reset</Text>
          </View>

          {!sent ? (
            <>
              <Text style={s.title}>Forgot your password?</Text>
              <Text style={s.subtitle}>Enter the email you signed up with and we'll send you a link to set a new one.</Text>

              <View style={s.field}>
                <Text style={s.label}>Email</Text>
                <TextInput
                  testID="forgot-email-input"
                  value={email}
                  onChangeText={setEmail}
                  autoCapitalize="none"
                  autoCorrect={false}
                  keyboardType="email-address"
                  placeholder="you@vaulted.app"
                  placeholderTextColor={colors.onSurfaceTertiary}
                  style={s.input}
                  onSubmitEditing={submit}
                  returnKeyType="send"
                />
              </View>

              {err && <Text testID="forgot-error" style={s.error}>{err}</Text>}

              <Pressable
                testID="forgot-submit-button"
                onPress={submit}
                disabled={loading}
                style={({ pressed }) => [s.cta, pressed && { opacity: 0.85 }]}
              >
                {loading ? <ActivityIndicator color="#0F0B08" /> : <Text style={s.ctaText}>Send reset link</Text>}
              </Pressable>

              <Pressable
                testID="forgot-back-to-login"
                onPress={() => router.replace("/(auth)/login")}
                style={s.linkRow}
                hitSlop={8}
              >
                <Ionicons name="arrow-back" size={14} color={colors.brand} />
                <Text style={s.linkText}>Back to sign in</Text>
              </Pressable>
            </>
          ) : (
            <View testID="forgot-sent" style={s.sentCard}>
              <View style={s.checkCircle}>
                <Ionicons name="mail" size={30} color={colors.brand} />
              </View>
              <Text style={s.title}>Check your inbox</Text>
              <Text style={s.subtitle}>
                If an account exists for that email, we've sent a link to reset your password. The link expires in 30 minutes.
              </Text>
              <Pressable
                testID="forgot-return-to-login"
                onPress={() => router.replace("/(auth)/login")}
                style={({ pressed }) => [s.cta, pressed && { opacity: 0.85 }]}
              >
                <Text style={s.ctaText}>Back to sign in</Text>
              </Pressable>
              <Text style={s.helperText}>Didn't get an email? Check your spam folder, or try again in a few minutes.</Text>
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
  backBtn: { alignSelf: "flex-start", padding: 6, marginBottom: spacing.md },
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
  cta: {
    backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: 16,
    alignItems: "center", marginTop: spacing.sm,
  },
  ctaText: { color: "#0F0B08", fontSize: 16, fontWeight: "700", letterSpacing: 0.3 },
  linkRow: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, marginTop: spacing.xl },
  linkText: { color: colors.brand, fontSize: 14, fontWeight: "600" },
  error: { color: "#E0735F", marginBottom: spacing.sm, fontSize: 14 },
  sentCard: { alignItems: "center", gap: spacing.md, marginTop: spacing.md },
  checkCircle: {
    width: 76, height: 76, borderRadius: 38, backgroundColor: "rgba(201,163,91,0.14)",
    alignItems: "center", justifyContent: "center", marginBottom: spacing.md,
    borderWidth: 1, borderColor: "rgba(201,163,91,0.35)",
  },
  helperText: { fontSize: 12, color: "rgba(245,233,201,0.5)", textAlign: "center", marginTop: spacing.lg, lineHeight: 18 },
});
