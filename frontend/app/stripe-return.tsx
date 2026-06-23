import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ActivityIndicator, Pressable } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { syncStripeSession } from "@/src/lib/stripe";
import { useAuth } from "@/src/lib/auth";
import { colors, spacing, radius } from "@/src/lib/theme";

export default function StripeReturn() {
  const params = useLocalSearchParams<{ flow?: string; status?: string; session_id?: string }>();
  const router = useRouter();
  const { refresh } = useAuth();
  const [loading, setLoading] = useState(true);
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null);

  useEffect(() => {
    (async () => {
      if (params.status !== "success" || !params.session_id) {
        setResult({ ok: false, msg: "Payment canceled or interrupted." });
        setLoading(false);
        return;
      }
      try {
        await syncStripeSession(String(params.session_id));
        await refresh();
        if (params.flow === "subscription") setResult({ ok: true, msg: "Vault Pro activated 🎉" });
        else setResult({ ok: true, msg: "Funds added to your USDC balance." });
      } catch (e: any) {
        setResult({ ok: false, msg: e?.message ?? "Failed to confirm payment." });
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const goHome = () => router.replace(params.flow === "subscription" ? "/vault-pro" : "/(tabs)/wallet");

  return (
    <SafeAreaView style={s.root} edges={["top", "bottom"]}>
      <View style={s.body}>
        {loading ? (
          <>
            <ActivityIndicator color={colors.brand} size="large" />
            <Text style={s.note}>Confirming payment…</Text>
          </>
        ) : (
          <>
            <View style={[s.icon, { backgroundColor: result?.ok ? colors.success : colors.error }]}>
              <Ionicons name={result?.ok ? "checkmark" : "close"} size={36} color="#fff" />
            </View>
            <Text style={s.title}>{result?.ok ? "Success" : "Not completed"}</Text>
            <Text testID="stripe-return-msg" style={s.subtitle}>{result?.msg}</Text>
            <Pressable testID="stripe-return-cta" onPress={goHome} style={s.cta}>
              <Text style={s.ctaText}>Continue</Text>
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
  icon: { width: 72, height: 72, borderRadius: 36, alignItems: "center", justifyContent: "center", marginBottom: spacing.md },
  title: { fontSize: 24, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.5 },
  subtitle: { fontSize: 15, color: colors.onSurfaceSecondary, textAlign: "center", marginHorizontal: spacing.lg },
  note: { color: colors.onSurfaceSecondary, marginTop: spacing.md },
  cta: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: 14, paddingHorizontal: spacing.xxl, marginTop: spacing.lg },
  ctaText: { color: "#fff", fontSize: 15, fontWeight: "600" },
});
