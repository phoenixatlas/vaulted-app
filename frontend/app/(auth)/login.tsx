import { useState } from "react";
import {
  View, Text, TextInput, Pressable, StyleSheet, KeyboardAvoidingView,
  Platform, ScrollView, ActivityIndicator, Image,
} from "react-native";
import { Link, useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { useAuth } from "@/src/lib/auth";
import { useI18n } from "@/src/lib/i18n";
import { colors, spacing, radius, BRAND_IMAGES } from "@/src/lib/theme";

export default function Login() {
  const { login } = useAuth();
  const { t } = useI18n();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    setErr(null);
    setLoading(true);
    try {
      await login(email.trim(), password);
      router.replace("/(tabs)/wallet");
    } catch (e: any) {
      setErr(e.message);
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
            <Text style={s.brandTagline}>Self-custody · Encrypted · Sovereign</Text>
          </View>

          <Text style={s.title}>{t("welcome_back")}</Text>
          <Text style={s.subtitle}>Self-custody crypto wallet with secure chat & calls.</Text>

          <View style={s.field}>
            <Text style={s.label}>{t("email")}</Text>
            <TextInput
              testID="login-email-input"
              value={email}
              onChangeText={setEmail}
              autoCapitalize="none"
              keyboardType="email-address"
              placeholder="you@vaulted.app"
              placeholderTextColor={colors.onSurfaceTertiary}
              style={s.input}
            />
          </View>
          <View style={s.field}>
            <Text style={s.label}>{t("password")}</Text>
            <TextInput
              testID="login-password-input"
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              placeholder="••••••••"
              placeholderTextColor={colors.onSurfaceTertiary}
              style={s.input}
            />
          </View>

          {err && <Text testID="login-error" style={s.error}>{err}</Text>}

          <Pressable testID="login-submit-button" onPress={submit} disabled={loading} style={({ pressed }) => [s.cta, pressed && { opacity: 0.85 }]}>
            {loading ? <ActivityIndicator color="#fff" /> : <Text style={s.ctaText}>{t("sign_in")}</Text>}
          </Pressable>

          <View style={s.switchRow}>
            <Text style={s.muted}>{t("no_account")} </Text>
            <Link testID="goto-register" href="/(auth)/register" style={s.linkText}>{t("sign_up")}</Link>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surfaceInverse },
  scroll: { padding: spacing.xl, paddingTop: spacing.xxl, flexGrow: 1, backgroundColor: colors.surfaceInverse },
  brandBlock: { alignItems: "center", marginTop: spacing.lg, marginBottom: spacing.xxl, gap: spacing.sm },
  brandRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  brandMark: { width: 64, height: 64 },
  brandWordmark: { fontSize: 36, fontWeight: "700", color: colors.brand, letterSpacing: -1.2 },
  brandTagline: { fontSize: 11, color: colors.brand, letterSpacing: 2.5, fontWeight: "600", textTransform: "uppercase" },
  title: { fontSize: 30, fontWeight: "700", color: colors.onSurfaceInverse, letterSpacing: -0.8 },
  subtitle: { fontSize: 15, color: "rgba(245,233,201,0.65)", marginTop: spacing.sm, marginBottom: spacing.xl },
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
    shadowColor: colors.brand, shadowOpacity: 0.35, shadowRadius: 14, shadowOffset: { width: 0, height: 4 },
  },
  ctaText: { color: colors.surfaceInverse, fontSize: 16, fontWeight: "700", letterSpacing: 0.3 },
  switchRow: { flexDirection: "row", justifyContent: "center", marginTop: spacing.xl },
  muted: { color: "rgba(245,233,201,0.6)", fontSize: 14 },
  linkText: { color: colors.brand, fontSize: 14, fontWeight: "700" },
  error: { color: "#E0735F", marginBottom: spacing.sm, fontSize: 14 },
});
