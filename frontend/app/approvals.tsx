import { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, ActivityIndicator, RefreshControl } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { colors, spacing, radius } from "@/src/lib/theme";

type Approval = {
  id: string; user_name: string; user_email: string; from_address: string; to_address: string;
  amount_eth: number; cosigner_email: string; status: string; created_at: string; expires_at: string;
};

export default function PendingApprovalsScreen() {
  const [items, setItems] = useState<Approval[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    try { setItems(await api<Approval[]>("/approvals/pending")); } catch (e) { console.log(e); }
  };
  useFocusEffect(useCallback(() => { setLoading(true); load().finally(() => setLoading(false)); }, []));
  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  return (
    <SafeAreaView style={s.root} edges={["top"]}>
      <View style={s.header}>
        <Text style={s.title}>Pending approvals</Text>
      </View>
      {loading ? <ActivityIndicator color={colors.brand} style={{ marginTop: 40 }} /> :
        items.length === 0 ? (
          <View style={s.empty}>
            <View style={s.emptyIcon}><Ionicons name="checkmark-circle-outline" size={32} color={colors.brand} /></View>
            <Text style={s.emptyText}>No pending approvals</Text>
            <Text style={s.emptySub}>Your large ETH sends are showing up here while waiting for your co-signer.</Text>
          </View>
        ) : (
          <ScrollView
            contentContainerStyle={{ padding: spacing.xl, paddingBottom: spacing.xxxl }}
            refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brand} />}
          >
            {items.map((a) => (
              <View key={a.id} testID={`approval-${a.id}`} style={s.card}>
                <View style={s.cardHead}>
                  <Ionicons name="time" size={16} color={colors.warning} />
                  <Text style={s.cardHeadText}>Awaiting {a.cosigner_email}</Text>
                </View>
                <Text style={s.amount}>{a.amount_eth} ETH</Text>
                <Text style={s.muted}>to {a.to_address.slice(0, 10)}…{a.to_address.slice(-6)}</Text>
                <Text style={s.smallMuted}>Expires {new Date(a.expires_at).toLocaleString()}</Text>
              </View>
            ))}
          </ScrollView>
        )
      }
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.xl, paddingTop: spacing.md, paddingBottom: spacing.md },
  title: { fontSize: 26, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.6 },
  empty: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: 8 },
  emptyIcon: { width: 72, height: 72, borderRadius: radius.pill, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  emptyText: { fontSize: 16, fontWeight: "600", color: colors.onSurface, marginTop: spacing.md },
  emptySub: { fontSize: 12, color: colors.onSurfaceTertiary, textAlign: "center", marginHorizontal: spacing.xl },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.md },
  cardHead: { flexDirection: "row", alignItems: "center", gap: 6, marginBottom: spacing.sm },
  cardHeadText: { color: colors.warning, fontSize: 12, fontWeight: "600" },
  amount: { fontSize: 26, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.8 },
  muted: { color: colors.onSurfaceSecondary, fontSize: 12, marginTop: 4 },
  smallMuted: { color: colors.onSurfaceTertiary, fontSize: 11, marginTop: 6 },
});
