/** International Bill Payments hub — pick a purpose, see past requests. */
import { useCallback, useState } from "react";
import { View, Text, Pressable, ScrollView, RefreshControl, StyleSheet, ActivityIndicator } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { router, useFocusEffect } from "expo-router";
import { api } from "@/src/lib/api";
import { colors, spacing, radius } from "@/src/lib/theme";
import { Bill, BillHeader, BillConfig, CATEGORY_ICON, STATUS_LABEL, TestModeBanner, bs, money } from "@/src/features/bills/shared";

const STEPS = ["Choose the payment purpose.", "Upload the supporting invoice or documentation.", "Receive a transparent FX quotation."];

export default function BillsHome() {
  const [cfg, setCfg] = useState<BillConfig | null>(null);
  const [bills, setBills] = useState<Bill[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [c, b] = await Promise.all([api<BillConfig>("/bills/config"), api<{ bills: Bill[] }>("/bills")]);
      setCfg(c); setBills(b.bills); setErr(null);
    } catch (e: any) { setErr(e?.message || "Couldn't load bill payments. Pull to retry."); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <BillHeader title="International Bill Payments" />
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingRight: spacing.lg + 8, paddingBottom: 140 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load().catch(() => undefined); setRefreshing(false); }} />}>
        <Text style={st.hero}>International payments, made simpler.</Text>
        <Text style={st.sub}>Pay school fees, hospital bills and qualifying business invoices abroad — from Nigeria, Kenya, Ghana or South Africa.</Text>
        <TestModeBanner />
        {!cfg && !err && <ActivityIndicator color={colors.brand} style={{ marginVertical: spacing.lg }} />}
        {err && <Text style={bs.err} testID="bills-load-error">{err}</Text>}
        {(cfg?.categories || []).map((c) => (
          <Pressable key={c.id} testID={`bills-cat-${c.id}`} onPress={() => router.push({ pathname: "/bills/new", params: { category: c.id } })}
            style={({ pressed }) => [st.cat, pressed && { opacity: 0.85 }]}>
            <View style={st.catIcon}><Ionicons name={CATEGORY_ICON[c.id]} size={24} color={colors.brandDeep} /></View>
            <View style={{ flex: 1 }}>
              <Text style={st.catTitle}>{c.label}</Text>
              <Text style={st.catSub}>{c.tagline}</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={colors.onSurfaceTertiary} />
          </Pressable>
        ))}

        <Text style={bs.section}>How it works</Text>
        <View style={bs.card}>
          {STEPS.map((t, i) => (
            <View key={t} style={st.step}><Text style={st.stepNum}>{i + 1}</Text><Text style={st.stepText}>{t}</Text></View>
          ))}
        </View>

        <Text style={bs.section}>Your requests</Text>
        {bills.length === 0 && <Text style={st.empty} testID="bills-empty">No bill payments yet.</Text>}
        {bills.map((b) => (
          <Pressable key={b.id} testID={`bill-row-${b.id}`} onPress={() => router.push(`/bills/${b.id}`)} style={st.row}>
            <Ionicons name={CATEGORY_ICON[b.category]} size={20} color={colors.brandDeep} />
            <View style={{ flex: 1 }}>
              <Text style={st.rowTitle} numberOfLines={1}>{b.institution}</Text>
              <Text style={st.rowSub}>{money(b.quote.payout_amount, b.quote.payout_currency)} · {b.reference}</Text>
            </View>
            <Text style={[st.badge, b.status === "rejected" && { color: colors.error }, b.status === "paid" && { color: colors.success }]}>
              {STATUS_LABEL[b.status] || b.status}
            </Text>
          </Pressable>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  hero: { fontSize: 26, fontWeight: "800", color: colors.onSurface, marginBottom: 6 },
  sub: { fontSize: 14, color: colors.onSurfaceSecondary, marginBottom: spacing.lg },
  cat: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg,
    padding: spacing.lg, marginBottom: spacing.md, borderWidth: 1, borderColor: colors.border, minHeight: 72 },
  catIcon: { width: 48, height: 48, borderRadius: 24, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  catTitle: { fontSize: 17, fontWeight: "700", color: colors.onSurface },
  catSub: { fontSize: 13, color: colors.onSurfaceSecondary, marginTop: 2 },
  step: { flexDirection: "row", gap: 12, alignItems: "center", paddingVertical: 6 },
  stepNum: { width: 26, height: 26, borderRadius: 13, backgroundColor: colors.brand, color: "#0F0B08", textAlign: "center", lineHeight: 26, fontWeight: "800", overflow: "hidden" },
  stepText: { flex: 1, fontSize: 14, color: colors.onSurface },
  empty: { fontSize: 14, color: colors.onSurfaceSecondary },
  row: { flexDirection: "row", alignItems: "center", gap: 12, minHeight: 60, borderBottomWidth: 1, borderBottomColor: colors.divider },
  rowTitle: { fontSize: 15, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 12, color: colors.onSurfaceSecondary, marginTop: 2 },
  badge: { fontSize: 12, fontWeight: "700", color: colors.brandDeep },
});
