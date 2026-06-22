import { useState } from "react";
import {
  View, Text, TextInput, Pressable, StyleSheet, KeyboardAvoidingView,
  Platform, ScrollView, ActivityIndicator,
} from "react-native";
import { Link, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { SafeAreaView } from "react-native-safe-area-context";
import { useAuth } from "@/src/lib/auth";
import { useI18n } from "@/src/lib/i18n";
import { colors, spacing, radius } from "@/src/lib/theme";

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
          <View style={s.brandRow}>
            <View style={s.logo}>
              <Ionicons name="shield-checkmark" size={28} color={colors.brand} />
            </View>
            <Text style={s.brandText}>Vaulted</Text>
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
  root: { flex: 1, backgroundColor: colors.surface },
  scroll: { padding: spacing.xl, paddingTop: spacing.xxl, flexGrow: 1 },
  brandRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.xxl },
  logo: { width: 44, height: 44, borderRadius: radius.md, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  brandText: { fontSize: 22, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.5 },
  title: { fontSize: 30, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.8 },
  subtitle: { fontSize: 15, color: colors.onSurfaceSecondary, marginTop: spacing.sm, marginBottom: spacing.xl },
  field: { marginBottom: spacing.lg },
  label: { fontSize: 13, color: colors.onSurfaceSecondary, marginBottom: spacing.xs, fontWeight: "500" },
  input: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.lg, paddingVertical: 14, fontSize: 16, color: colors.onSurface,
    backgroundColor: colors.surface,
  },
  cta: {
    backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: 16,
    alignItems: "center", marginTop: spacing.sm,
  },
  ctaText: { color: "#fff", fontSize: 16, fontWeight: "600" },
  switchRow: { flexDirection: "row", justifyContent: "center", marginTop: spacing.xl },
  muted: { color: colors.onSurfaceSecondary, fontSize: 14 },
  linkText: { color: colors.brand, fontSize: 14, fontWeight: "600" },
  error: { color: colors.error, marginBottom: spacing.sm, fontSize: 14 },
});
