import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ActivityIndicator, Pressable, Platform, Linking, ScrollView } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { colors, spacing, radius } from "@/src/lib/theme";
import { kycErrorInfo, PHOTO_TIPS, type KycErrorInfo } from "@/src/lib/kycErrors";

/** Stripe Identity return_url lands here after the user finishes (or bails on)
 * the hosted verification flow. We poll /kyc/status a few times because the
 * verified webhook may arrive up to ~10 seconds after Stripe's client-side
 * redirect. */
type KycStatusResp = {
  identity_verification_status: "not_started" | "requires_input" | "processing" | "verified" | "canceled";
  identity_last_error?: { code?: string | null; reason?: string | null; at?: string } | null;
  limits?: { per_send_gbp: number; monthly_gbp: number };
};

export default function KycReturn() {
  const router = useRouter();
  const [state, setState] = useState<"polling" | "verified" | "pending" | "requires_input" | "error">("polling");
  const [attempts, setAttempts] = useState(0);
  const [statusData, setStatusData] = useState<KycStatusResp | null>(null);
  const [retrying, setRetrying] = useState<null | "same" | "fresh">(null);
  const [retryErr, setRetryErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      // Poll every 2s for up to 20s
      for (let i = 0; i < 10 && alive; i++) {
        try {
          const s = await api<KycStatusResp>("/kyc/status");
          setStatusData(s);
          const status = s.identity_verification_status;
          if (status === "verified") {
            setState("verified");
            return;
          }
          if (status === "requires_input") {
            setState("requires_input");
            return;
          }
        } catch {
          /* ignore, keep polling */
        }
        setAttempts(i + 1);
        await new Promise((r) => setTimeout(r, 2000));
      }
      if (alive) setState("pending");
    })();
    return () => { alive = false; };
  }, []);

  const openStripeSession = async (forceNew: boolean) => {
    setRetrying(forceNew ? "fresh" : "same");
    setRetryErr(null);
    try {
      const { url } = await api<{ url: string; session_id: string }>(
        "/kyc/session",
        { method: "POST", body: forceNew ? { force_new: true } : {} },
      );
      if (Platform.OS === "web") {
        window.location.href = url;
      } else {
        await Linking.openURL(url);
      }
    } catch (e: any) {
      setRetryErr(e?.message || "Could not restart verification");
    } finally {
      setRetrying(null);
    }
  };

  const err: KycErrorInfo | null = state === "requires_input"
    ? kycErrorInfo(statusData?.identity_last_error?.code, statusData?.identity_last_error?.reason)
    : null;

  return (
    <SafeAreaView style={s.root} edges={["top", "bottom"]}>
      <ScrollView contentContainerStyle={s.body} showsVerticalScrollIndicator={false}>
        {state === "polling" && (
          <>
            <ActivityIndicator color={colors.brand} size="large" />
            <Text style={s.title}>Verifying your identity…</Text>
            <Text style={s.sub}>Attempt {attempts + 1}/10 · This usually takes a few seconds.</Text>
          </>
        )}

        {state === "verified" && (
          <>
            <View style={s.iconOk}><Ionicons name="checkmark" size={40} color="#fff" /></View>
            <Text style={s.title}>You&apos;re verified 🎉</Text>
            <Text style={s.sub}>
              You can now send up to £{(statusData?.limits?.per_send_gbp ?? 1000).toLocaleString()} per transfer,
              £{(statusData?.limits?.monthly_gbp ?? 5000).toLocaleString()} per month.
            </Text>
            <Pressable testID="kyc-return-continue" onPress={() => router.replace("/remit")} style={s.cta}>
              <Text style={s.ctaText}>Send money now</Text>
            </Pressable>
          </>
        )}

        {state === "requires_input" && err && (
          <>
            <View style={s.iconWarn}><Ionicons name="alert" size={40} color="#fff" /></View>
            <Text style={s.title}>{err.title}</Text>
            <Text style={s.sub}>{err.reason}</Text>

            {/* Concrete "do this next" tip block */}
            <View style={s.tipCard}>
              <View style={s.tipHeader}>
                <Ionicons name="bulb" size={16} color={colors.brandDeep} />
                <Text style={s.tipHeaderText}>What to do next</Text>
              </View>
              <Text style={s.tipBody}>{err.tip}</Text>
            </View>

            {/* Photo capture checklist (generic tips that always help) */}
            {!err.fatal && (
              <View style={s.checklistCard}>
                <Text style={s.checklistTitle}>Photo tips</Text>
                {PHOTO_TIPS.map((t) => (
                  <View key={t} style={s.checklistRow}>
                    <Ionicons name="checkmark-circle" size={14} color={colors.success} />
                    <Text style={s.checklistText}>{t}</Text>
                  </View>
                ))}
              </View>
            )}

            {/* Action buttons */}
            <View style={s.actionsCol}>
              {!err.fatal && (
                <Pressable
                  testID="kyc-return-retry"
                  disabled={!!retrying}
                  onPress={() => openStripeSession(false)}
                  style={({ pressed }) => [s.cta, pressed && { opacity: 0.9 }]}
                >
                  {retrying === "same" ? (
                    <ActivityIndicator color="#0F0B08" />
                  ) : (
                    <Text style={s.ctaText}>Try again</Text>
                  )}
                </Pressable>
              )}
              <Pressable
                testID="kyc-return-start-over"
                disabled={!!retrying}
                onPress={() => openStripeSession(true)}
                style={({ pressed }) => [s.ctaSecondary, pressed && { opacity: 0.9 }]}
              >
                {retrying === "fresh" ? (
                  <ActivityIndicator color={colors.onSurface} />
                ) : (
                  <Text style={s.ctaSecondaryText}>Start over with a new session</Text>
                )}
              </Pressable>
              <Pressable
                testID="kyc-return-later"
                onPress={() => router.replace("/(tabs)/wallet")}
                style={s.ctaTextOnly}
              >
                <Text style={s.ctaTextOnlyLabel}>I&apos;ll try later</Text>
              </Pressable>
            </View>

            {retryErr && <Text style={s.retryErr}>{retryErr}</Text>}

            {/* Escape hatch for repeat failures */}
            <Text style={s.supportLine}>
              Still stuck? Email{" "}
              <Text style={s.supportLink} onPress={() => Linking.openURL("mailto:support@phoenix-atlas.com")}>
                support@phoenix-atlas.com
              </Text>
            </Text>
          </>
        )}

        {state === "pending" && (
          <>
            <View style={s.iconInfo}><Ionicons name="hourglass" size={40} color="#fff" /></View>
            <Text style={s.title}>Still processing…</Text>
            <Text style={s.sub}>
              Your verification is taking a little longer than usual. We&apos;ll email you when it&apos;s done — you can safely leave this screen.
            </Text>
            <Pressable testID="kyc-return-done" onPress={() => router.replace("/(tabs)/wallet")} style={s.cta}>
              <Text style={s.ctaText}>Back to wallet</Text>
            </Pressable>
          </>
        )}

        {state === "error" && (
          <>
            <View style={s.iconWarn}><Ionicons name="close" size={40} color="#fff" /></View>
            <Text style={s.title}>Something went wrong</Text>
            <Text style={s.sub}>We couldn&apos;t check your verification status. Try again in a moment.</Text>
            <Pressable testID="kyc-return-back" onPress={() => router.replace("/kyc")} style={s.cta}>
              <Text style={s.ctaText}>Back to Identity</Text>
            </Pressable>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  body: {
    flexGrow: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.xl,
    gap: spacing.md,
    paddingVertical: spacing.xxl,
  },
  iconOk: { width: 72, height: 72, borderRadius: 36, backgroundColor: colors.success, alignItems: "center", justifyContent: "center" },
  iconWarn: { width: 72, height: 72, borderRadius: 36, backgroundColor: colors.error, alignItems: "center", justifyContent: "center" },
  iconInfo: { width: 72, height: 72, borderRadius: 36, backgroundColor: colors.brand, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 22, fontWeight: "800", color: colors.onSurface, textAlign: "center", marginTop: spacing.sm },
  sub: { fontSize: 13, color: colors.onSurfaceSecondary, textAlign: "center", lineHeight: 18, maxWidth: 340 },

  tipCard: {
    marginTop: spacing.md,
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.brandTertiary,
    borderWidth: 1,
    borderColor: "rgba(201,163,91,0.40)",
    width: "100%",
    maxWidth: 360,
  },
  tipHeader: { flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 6 },
  tipHeaderText: { fontSize: 12, fontWeight: "700", color: colors.brandDeep, textTransform: "uppercase", letterSpacing: 0.6 },
  tipBody: { fontSize: 13, color: colors.onSurface, lineHeight: 18 },

  checklistCard: {
    marginTop: spacing.sm,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    width: "100%",
    maxWidth: 360,
    gap: 6,
  },
  checklistTitle: { fontSize: 11, fontWeight: "700", color: colors.onSurfaceSecondary, letterSpacing: 0.6, textTransform: "uppercase", marginBottom: 4 },
  checklistRow: { flexDirection: "row", alignItems: "flex-start", gap: 8 },
  checklistText: { flex: 1, fontSize: 12, color: colors.onSurface, lineHeight: 17 },

  actionsCol: { width: "100%", maxWidth: 360, gap: spacing.sm, marginTop: spacing.lg },
  cta: {
    backgroundColor: colors.brand,
    borderRadius: radius.md,
    paddingVertical: 14,
    paddingHorizontal: 32,
    minWidth: 220,
    alignItems: "center",
  },
  ctaText: { color: "#0F0B08", fontSize: 15, fontWeight: "700" },
  ctaSecondary: {
    backgroundColor: "transparent",
    borderRadius: radius.md,
    paddingVertical: 13,
    paddingHorizontal: 32,
    minWidth: 220,
    alignItems: "center",
    borderWidth: 1,
    borderColor: colors.border,
  },
  ctaSecondaryText: { color: colors.onSurface, fontSize: 14, fontWeight: "600" },
  ctaTextOnly: { paddingVertical: 10, alignItems: "center" },
  ctaTextOnlyLabel: { color: colors.onSurfaceTertiary, fontSize: 13, fontWeight: "500" },

  retryErr: { color: colors.error, fontSize: 12, textAlign: "center", marginTop: 4 },
  supportLine: { fontSize: 11, color: colors.onSurfaceTertiary, textAlign: "center", marginTop: spacing.md },
  supportLink: { color: colors.brand, textDecorationLine: "underline" },
});
