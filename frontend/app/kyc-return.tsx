import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ActivityIndicator, Pressable } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { colors, spacing, radius } from "@/src/lib/theme";

/** Stripe Identity return_url lands here after the user finishes (or bails on)
 * the hosted verification flow. We poll /kyc/status a few times because the
 * verified webhook may arrive up to ~10 seconds after Stripe's client-side
 * redirect. */
export default function KycReturn() {
  const router = useRouter();
  const [state, setState] = useState<"polling" | "verified" | "pending" | "requires_input" | "error">("polling");
  const [attempts, setAttempts] = useState(0);

  useEffect(() => {
    let alive = true;
    (async () => {
      // Poll every 2s for up to 20s
      for (let i = 0; i < 10 && alive; i++) {
        try {
          const s = await api<any>("/kyc/status");
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

  return (
    <SafeAreaView style={s.root} edges={["top", "bottom"]}>
      <View style={s.body}>
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
            <Text style={s.sub}>You can now send up to £1,000 per transfer, £5,000 per month.</Text>
            <Pressable testID="kyc-return-continue" onPress={() => router.replace("/remit")} style={s.cta}>
              <Text style={s.ctaText}>Send money now</Text>
            </Pressable>
          </>
        )}
        {state === "requires_input" && (
          <>
            <View style={s.iconWarn}><Ionicons name="alert" size={40} color="#fff" /></View>
            <Text style={s.title}>Verification needs another attempt</Text>
            <Text style={s.sub}>Stripe couldn&apos;t verify your document. Please try again with a clearer photo.</Text>
            <Pressable testID="kyc-return-retry" onPress={() => router.replace("/kyc")} style={s.cta}>
              <Text style={s.ctaText}>Try again</Text>
            </Pressable>
          </>
        )}
        {state === "pending" && (
          <>
            <View style={s.iconInfo}><Ionicons name="hourglass" size={40} color="#fff" /></View>
            <Text style={s.title}>Still processing…</Text>
            <Text style={s.sub}>Your verification is taking a little longer than usual. We&apos;ll email you when it&apos;s done. You can leave this screen.</Text>
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
      </View>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  body: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.md },
  iconOk: { width: 72, height: 72, borderRadius: 36, backgroundColor: colors.success, alignItems: "center", justifyContent: "center" },
  iconWarn: { width: 72, height: 72, borderRadius: 36, backgroundColor: colors.error, alignItems: "center", justifyContent: "center" },
  iconInfo: { width: 72, height: 72, borderRadius: 36, backgroundColor: colors.brand, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 22, fontWeight: "800", color: colors.onSurface, textAlign: "center", marginTop: spacing.sm },
  sub: { fontSize: 13, color: colors.onSurfaceSecondary, textAlign: "center", lineHeight: 18, maxWidth: 320 },
  cta: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: 14, paddingHorizontal: 32, marginTop: spacing.lg, minWidth: 220, alignItems: "center" },
  ctaText: { color: "#0F0B08", fontSize: 15, fontWeight: "700" },
});
