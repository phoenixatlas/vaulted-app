import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ActivityIndicator, Pressable, Linking } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { colors, spacing, radius } from "@/src/lib/theme";

type Result = { status: string; tx_hash?: string; explorer_url?: string; already?: boolean };

export default function ApprovePage() {
  const params = useLocalSearchParams<{ token?: string; decision?: string }>();
  const [loading, setLoading] = useState(true);
  const [result, setResult] = useState<Result | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      if (!params.token || !params.decision) {
        setErr("Missing approval token or decision in the URL.");
        setLoading(false);
        return;
      }
      try {
        const r = await fetch(`${process.env.EXPO_PUBLIC_BACKEND_URL}/api/approvals/decide`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token: params.token, decision: params.decision }),
        });
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
        setResult(data);
      } catch (e: any) {
        setErr(e.message);
      } finally {
        setLoading(false);
      }
    })();
  }, [params.token, params.decision]);

  const approved = result?.status === "approved";
  const rejected = result?.status === "rejected";

  return (
    <SafeAreaView style={s.root} edges={["top", "bottom"]}>
      <View style={s.body}>
        {loading ? (
          <>
            <ActivityIndicator color={colors.brand} size="large" />
            <Text style={s.note}>Confirming your decision…</Text>
          </>
        ) : err ? (
          <>
            <View style={[s.icon, { backgroundColor: colors.error }]}>
              <Ionicons name="close" size={32} color="#fff" />
            </View>
            <Text style={s.title}>Couldn't process</Text>
            <Text testID="approve-error" style={s.subtitle}>{err}</Text>
          </>
        ) : approved ? (
          <>
            <View style={[s.icon, { backgroundColor: colors.success }]}>
              <Ionicons name="checkmark" size={32} color="#fff" />
            </View>
            <Text style={s.title}>Approved & broadcasted</Text>
            <Text testID="approve-status" style={s.subtitle}>The transaction is on its way to Sepolia.</Text>
            {result.explorer_url && (
              <Pressable testID="approve-etherscan" onPress={() => Linking.openURL(result.explorer_url!)} style={s.cta}>
                <Text style={s.ctaText}>View on Etherscan</Text>
              </Pressable>
            )}
          </>
        ) : rejected ? (
          <>
            <View style={[s.icon, { backgroundColor: colors.warning }]}>
              <Ionicons name="close-circle" size={32} color="#fff" />
            </View>
            <Text style={s.title}>Rejected</Text>
            <Text testID="approve-status" style={s.subtitle}>The transaction won't be sent. The original sender has been notified.</Text>
          </>
        ) : (
          <>
            <Text style={s.title}>Already decided</Text>
            <Text testID="approve-status" style={s.subtitle}>Status: {result?.status}</Text>
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
  subtitle: { fontSize: 14, color: colors.onSurfaceSecondary, textAlign: "center", marginHorizontal: spacing.lg },
  note: { color: colors.onSurfaceSecondary, marginTop: spacing.md },
  cta: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: 14, paddingHorizontal: spacing.xxl, marginTop: spacing.lg },
  ctaText: { color: "#0F0B08", fontSize: 15, fontWeight: "600" },
});
