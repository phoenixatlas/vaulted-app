import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "@/src/lib/auth";
import { startSubscriptionCheckout, syncStripeSession, cancelSubscription } from "@/src/lib/stripe";
import { colors, spacing, radius } from "@/src/lib/theme";

const PERKS = [
  { icon: "shield-checkmark", title: "Multi-signature wallet", desc: "Require multiple approvals for large sends." },
  { icon: "flash", title: "Lower swap & send fees", desc: "Pro members pay 50% less in network fees." },
  { icon: "videocam", title: "Priority video support", desc: "Skip the queue when calling Vault Support." },
  { icon: "star", title: "Pro badge", desc: "Show off your premium status in chats and on your profile." },
];

export default function VaultPro() {
  const { user, refresh } = useAuth();
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    refresh();
  }, []);

  const subscribe = async () => {
    setMsg(null);
    setLoading(true);
    try {
      const r = await startSubscriptionCheckout();
      if (r.status === "success" && r.session_id) {
        await syncStripeSession(r.session_id);
        await refresh();
        setMsg("Welcome to Vault Pro! 🎉");
      } else if (r.status === "cancel") {
        setMsg("Checkout canceled.");
      } else if (r.session_id) {
        // Poll once anyway in case webhook fired
        try {
          await syncStripeSession(r.session_id);
          await refresh();
        } catch {}
      }
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setLoading(false);
    }
  };

  const onCancel = async () => {
    setMsg(null);
    setLoading(true);
    try {
      await cancelSubscription();
      await refresh();
      setMsg("Subscription canceled. Pro access lasts until period end.");
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setLoading(false);
    }
  };

  const isPro = !!user?.is_pro;

  return (
    <SafeAreaView style={s.root} edges={["top", "bottom"]}>
      <View style={s.header}>
        <Pressable testID="vaultpro-back" onPress={() => router.back()}>
          <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
        </Pressable>
        <Text style={s.title}>Vault Pro</Text>
        <View style={{ width: 26 }} />
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.xl, paddingBottom: spacing.xxxl }}>
        <View style={s.hero}>
          <View style={s.heroIcon}>
            <Ionicons name="star" size={28} color={colors.brand} />
          </View>
          <Text style={s.heroTitle}>{isPro ? "You're a Pro member" : "Unlock Vault Pro"}</Text>
          <Text style={s.heroPrice} testID="vaultpro-price">$9.99 / month</Text>
          <Text style={s.heroSub}>Cancel anytime. Securely billed by Stripe.</Text>
          {isPro && (
            <View style={s.activeBadge}>
              <Ionicons name="checkmark-circle" size={14} color={colors.success} />
              <Text style={s.activeText}>
                Status: {user?.subscription?.status ?? "active"}
              </Text>
            </View>
          )}
        </View>

        <View style={s.perksCard}>
          {PERKS.map((p, i) => (
            <View key={p.title}>
              <View style={s.perkRow}>
                <View style={s.perkIcon}>
                  <Ionicons name={p.icon as any} size={18} color={colors.brand} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={s.perkTitle}>{p.title}</Text>
                  <Text style={s.perkDesc}>{p.desc}</Text>
                </View>
              </View>
              {i < PERKS.length - 1 && <View style={s.divider} />}
            </View>
          ))}
        </View>

        {msg && (
          <Text testID="vaultpro-msg" style={s.msg}>
            {msg}
          </Text>
        )}

        {!isPro ? (
          <Pressable
            testID="vaultpro-subscribe"
            onPress={subscribe}
            disabled={loading}
            style={({ pressed }) => [s.cta, pressed && { opacity: 0.85 }]}
          >
            {loading ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={s.ctaText}>Subscribe with Stripe</Text>
            )}
          </Pressable>
        ) : (
          <Pressable
            testID="vaultpro-cancel"
            onPress={onCancel}
            disabled={loading}
            style={({ pressed }) => [s.ctaOutline, pressed && { opacity: 0.7 }]}
          >
            {loading ? (
              <ActivityIndicator color={colors.error} />
            ) : (
              <Text style={[s.ctaText, { color: colors.error }]}>Cancel subscription</Text>
            )}
          </Pressable>
        )}
        <Text style={s.tinyNote}>Test mode • Stripe sk_test_emergent</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: spacing.xl, paddingTop: spacing.sm, paddingBottom: spacing.md },
  title: { fontSize: 17, fontWeight: "700", color: colors.onSurface },
  hero: { alignItems: "center", paddingVertical: spacing.lg, backgroundColor: colors.brandTertiary, borderRadius: radius.lg, marginBottom: spacing.lg, paddingHorizontal: spacing.lg },
  heroIcon: { width: 56, height: 56, borderRadius: radius.pill, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", marginBottom: spacing.sm },
  heroTitle: { fontSize: 22, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.5 },
  heroPrice: { fontSize: 32, fontWeight: "700", color: colors.brand, marginTop: spacing.sm, letterSpacing: -1 },
  heroSub: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 4 },
  activeBadge: { flexDirection: "row", gap: 6, alignItems: "center", marginTop: spacing.md, backgroundColor: colors.surface, paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.pill },
  activeText: { color: colors.success, fontSize: 12, fontWeight: "600" },
  perksCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, paddingVertical: spacing.xs },
  perkRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.lg },
  perkIcon: { width: 36, height: 36, borderRadius: radius.pill, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  perkTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  perkDesc: { fontSize: 12, color: colors.onSurfaceSecondary, marginTop: 2 },
  divider: { height: 1, backgroundColor: colors.divider, marginLeft: spacing.lg + 36 + spacing.md },
  cta: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: 16, alignItems: "center", marginTop: spacing.xl },
  ctaOutline: { borderRadius: radius.md, paddingVertical: 16, alignItems: "center", marginTop: spacing.xl, borderWidth: 1, borderColor: colors.error },
  ctaText: { color: "#fff", fontSize: 16, fontWeight: "600" },
  msg: { color: colors.onSurfaceSecondary, marginTop: spacing.md, textAlign: "center" },
  tinyNote: { color: colors.onSurfaceTertiary, fontSize: 10, marginTop: spacing.lg, textAlign: "center" },
});
