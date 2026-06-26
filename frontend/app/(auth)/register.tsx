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

export default function Register() {
  const { register } = useAuth();
  const { t } = useI18n();
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    setErr(null);
    setLoading(true);
    try {
      await register(email.trim(), password, name.trim());
      router.replace("/onboarding/seed");
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
          <Pressable testID="back-to-login" onPress={() => router.back()} style={s.back}>
            <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
          </Pressable>
          <Text style={s.title}>{t("sign_up")}</Text>
          <Text style={s.subtitle}>Your keys, your coins. Get started in seconds.</Text>

          <View style={s.field}>
            <Text style={s.label}>{t("name")}</Text>
            <TextInput testID="reg-name-input" value={name} onChangeText={setName} placeholder="Jane Doe" placeholderTextColor={colors.onSurfaceTertiary} style={s.input} />
          </View>
          <View style={s.field}>
            <Text style={s.label}>{t("email")}</Text>
            <TextInput testID="reg-email-input" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" placeholder="you@vaulted.app" placeholderTextColor={colors.onSurfaceTertiary} style={s.input} />
          </View>
          <View style={s.field}>
            <Text style={s.label}>{t("password")}</Text>
            <TextInput testID="reg-password-input" value={password} onChangeText={setPassword} secureTextEntry placeholder="At least 6 characters" placeholderTextColor={colors.onSurfaceTertiary} style={s.input} />
          </View>

          {err && <Text testID="reg-error" style={s.error}>{err}</Text>}

          <Pressable testID="reg-submit-button" onPress={submit} disabled={loading} style={({ pressed }) => [s.cta, pressed && { opacity: 0.85 }]}>
            {loading ? <ActivityIndicator color="#fff" /> : <Text style={s.ctaText}>{t("sign_up")}</Text>}
          </Pressable>

          <View style={s.switchRow}>
            <Text style={s.muted}>{t("have_account")} </Text>
            <Link testID="goto-login" href="/(auth)/login" style={s.linkText}>{t("sign_in")}</Link>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  scroll: { padding: spacing.xl, flexGrow: 1 },
  back: { marginBottom: spacing.lg, alignSelf: "flex-start" },
  title: { fontSize: 30, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.8 },
  subtitle: { fontSize: 15, color: colors.onSurfaceSecondary, marginTop: spacing.sm, marginBottom: spacing.xl },
  field: { marginBottom: spacing.lg },
  label: { fontSize: 13, color: colors.onSurfaceSecondary, marginBottom: spacing.xs, fontWeight: "500" },
  input: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.lg, paddingVertical: 14, fontSize: 16, color: colors.onSurface, backgroundColor: colors.surface },
  cta: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: 16, alignItems: "center", marginTop: spacing.sm, shadowColor: colors.brand, shadowOpacity: 0.30, shadowRadius: 12, shadowOffset: { width: 0, height: 4 } },
  ctaText: { color: "#0F0B08", fontSize: 16, fontWeight: "700", letterSpacing: 0.3 },
  switchRow: { flexDirection: "row", justifyContent: "center", marginTop: spacing.xl },
  muted: { color: colors.onSurfaceSecondary, fontSize: 14 },
  linkText: { color: colors.brand, fontSize: 14, fontWeight: "600" },
  error: { color: colors.error, marginBottom: spacing.sm, fontSize: 14 },
});
