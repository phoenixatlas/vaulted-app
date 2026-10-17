import { useEffect, useMemo, useState } from "react";
import {
  View, Text, TextInput, Pressable, StyleSheet, KeyboardAvoidingView,
  Platform, ScrollView, ActivityIndicator,
} from "react-native";
import { Link, useRouter, useLocalSearchParams } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { SafeAreaView } from "react-native-safe-area-context";
import { useAuth } from "@/src/lib/auth";
import { useI18n } from "@/src/lib/i18n";
import { colors, spacing, radius } from "@/src/lib/theme";
import { api } from "@/src/lib/api";
import { getPendingRefCode, clearPendingRefCode } from "@/src/lib/refCode";
import PreviewBanner from "@/src/components/PreviewBanner";
import { PasswordInput } from "@/src/components/PasswordInput";

type ValidateResp = {
  valid: boolean;
  referrer_name_masked?: string;
  reward_per_side_gbp?: number;
};

export default function Register() {
  const { register } = useAuth();
  const { t } = useI18n();
  const router = useRouter();
  const params = useLocalSearchParams<{ ref?: string }>();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Mismatch is a warning (not an error) until the user has typed at
  // least one character in the confirm box — avoids red flashes while
  // they're still typing the main password.
  const passwordsMismatch = useMemo(
    () => confirmPassword.length > 0 && password !== confirmPassword,
    [password, confirmPassword],
  );
  const passwordsMatch = useMemo(
    () => password.length >= 6 && password === confirmPassword,
    [password, confirmPassword],
  );

  // Referral code — checked in this order: URL param, then persisted storage.
  const [refCode, setRefCode] = useState<string | null>(null);
  const [refInfo, setRefInfo] = useState<ValidateResp | null>(null);

  // Bootstrap the code + validate it against backend so we can render a
  // trust-building "Invited by Sarah B." banner before signup.
  useEffect(() => {
    let alive = true;
    (async () => {
      const fromUrl = (params?.ref || "").toString().trim().toUpperCase();
      const persisted = fromUrl || (await getPendingRefCode()) || null;
      if (!persisted || !alive) return;
      setRefCode(persisted);
      try {
        const info = await api<ValidateResp>(`/referrals/validate/${persisted}`, { auth: false });
        if (alive) setRefInfo(info);
      } catch {
        // Silent — invalid codes shouldn't block signup
      }
    })();
    return () => { alive = false; };
  }, [params?.ref]);

  const submit = async () => {
    setErr(null);
    // Client-side gate — surface the mismatch before hitting the API
    // so the user never sees a confusing backend error message when
    // the real problem is a typo in one of the two password boxes.
    if (password.length < 6) {
      setErr("Password must be at least 6 characters.");
      return;
    }
    if (password !== confirmPassword) {
      setErr("Passwords don't match. Please check and try again.");
      return;
    }
    setLoading(true);
    try {
      await register(email.trim(), password, name.trim(), refCode);
      await clearPendingRefCode();
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
          <Text style={s.subtitle}>Your keys, your Funds. Get started in seconds.</Text>

          <PreviewBanner
            message="Preview mode - by signing up you're joining Vaulted's build cohort. Live services will open once we're FCA authorized. Do not deposit funds you cannot afford to lose."
          />

          {refCode && refInfo?.valid && (
            <View style={s.inviteBanner} testID="reg-invite-banner">
              <Ionicons name="gift" size={18} color={colors.brandDeep} />
              <View style={{ flex: 1 }}>
                <Text style={s.inviteTitle}>
                  Invited by {refInfo.referrer_name_masked}
                </Text>
                <Text style={s.inviteBody}>
                  Verify your identity after signup and you&apos;ll get £
                  {(refInfo.reward_per_side_gbp ?? 5).toFixed(0)} credit toward transfer fees.
                </Text>
              </View>
            </View>
          )}

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
            <PasswordInput
              testID="reg-password-input"
              value={password}
              onChangeText={setPassword}
              placeholder="At least 6 characters"
              passwordType="new-password"
            />
          </View>
          <View style={s.field}>
            <Text style={s.label}>Confirm password</Text>
            <PasswordInput
              testID="reg-password-confirm-input"
              value={confirmPassword}
              onChangeText={setConfirmPassword}
              placeholder="Re-enter your password"
              passwordType="new-password"
              onSubmitEditing={submit}
              returnKeyType="done"
              containerStyle={passwordsMismatch ? { borderColor: colors.error, borderWidth: 1, borderRadius: radius.md } : undefined}
            />
            {passwordsMismatch ? (
              <View style={s.hintRow}>
                <Ionicons name="alert-circle" size={14} color={colors.error} />
                <Text style={s.hintError}>Passwords don&apos;t match yet.</Text>
              </View>
            ) : passwordsMatch ? (
              <View style={s.hintRow}>
                <Ionicons name="checkmark-circle" size={14} color={colors.success} />
                <Text style={s.hintOk}>Passwords match.</Text>
              </View>
            ) : null}
          </View>

          {err && <Text testID="reg-error" style={s.error}>{err}</Text>}

          <Pressable
            testID="reg-submit-button"
            onPress={submit}
            disabled={loading || passwordsMismatch || password.length < 6 || confirmPassword.length === 0}
            style={({ pressed }) => [
              s.cta,
              (loading || passwordsMismatch || password.length < 6 || confirmPassword.length === 0) && { opacity: 0.5 },
              pressed && { opacity: 0.85 },
            ]}
          >
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

  inviteBanner: { flexDirection: "row", gap: 10, alignItems: "flex-start", padding: spacing.md, backgroundColor: colors.brandTertiary, borderRadius: radius.md, borderWidth: 1, borderColor: "rgba(201,163,91,0.40)", marginBottom: spacing.xl },
  inviteTitle: { fontSize: 13, fontWeight: "700", color: colors.brandDeep, marginBottom: 2 },
  inviteBody: { fontSize: 12, color: colors.onSurfaceSecondary, lineHeight: 16 },

  field: { marginBottom: spacing.lg },
  label: { fontSize: 13, color: colors.onSurfaceSecondary, marginBottom: spacing.xs, fontWeight: "500" },
  input: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.lg, paddingVertical: 14, fontSize: 16, color: colors.onSurface, backgroundColor: colors.surface },
  cta: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: 16, alignItems: "center", marginTop: spacing.sm, shadowColor: colors.brand, shadowOpacity: 0.30, shadowRadius: 12, shadowOffset: { width: 0, height: 4 } },
  ctaText: { color: "#0F0B08", fontSize: 16, fontWeight: "700", letterSpacing: 0.3 },
  switchRow: { flexDirection: "row", justifyContent: "center", marginTop: spacing.xl },
  muted: { color: colors.onSurfaceSecondary, fontSize: 14 },
  linkText: { color: colors.brand, fontSize: 14, fontWeight: "600" },
  error: { color: colors.error, marginBottom: spacing.sm, fontSize: 14 },
  hintRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 6 },
  hintError: { fontSize: 12, color: colors.error, fontWeight: "500" },
  hintOk: { fontSize: 12, color: colors.success, fontWeight: "500" },
});
