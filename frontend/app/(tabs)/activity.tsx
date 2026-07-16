import { useCallback, useState } from "react";
import { View, Text, StyleSheet, FlatList, ActivityIndicator, RefreshControl, Pressable } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { useI18n } from "@/src/lib/i18n";
import { colors, spacing, radius } from "@/src/lib/theme";
import { ExportSheet } from "@/src/components/ExportSheet";
import KycStatusBanner from "@/src/components/KycStatusBanner";

type Tx = {
  id: string; type: string; category: string; asset: string; amount: number; fiat_value: number;
  counterparty: string; status: string; created_at: string; receipt_id?: string; tx_hash?: string;
};

const typeIcon = (t: Tx) => {
  if (t.type === "send") return "arrow-up";
  if (t.type === "receive") return "arrow-down";
  if (t.type === "deposit") return "add-circle";
  if (t.type === "withdraw") return "remove-circle";
  return "swap-horizontal";
};

export default function Activity() {
  const { t } = useI18n();
  const [items, setItems] = useState<Tx[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showExport, setShowExport] = useState(false);

  const load = async () => { try { setItems(await api<Tx[]>("/transactions")); } catch (e) { console.log(e); } };
  useFocusEffect(useCallback(() => { setLoading(true); load().finally(() => setLoading(false)); }, []));
  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  return (
    <SafeAreaView style={s.root} edges={["top"]}>
      <View style={s.header}>
        <Text style={s.title}>{t("transactions")}</Text>
        <Pressable testID="open-export" onPress={() => setShowExport(true)} style={s.exportBtn}>
          <Ionicons name="download-outline" size={16} color={colors.brand} />
          <Text style={s.exportText}>{t("export")}</Text>
        </Pressable>
      </View>
      {/* Progress banner for in-flight identity verification. Users
          often check Activity to see whether their tx has settled — this
          reassures them the ID check is moving too. */}
      <KycStatusBanner />
      {loading ? <ActivityIndicator color={colors.brand} style={{ marginTop: 40 }} /> :
        items.length === 0 ? (
          <View style={s.empty}><Text style={s.emptyText}>{t("no_tx")}</Text></View>
        ) : (
          <FlatList
            data={items}
            keyExtractor={(i) => i.id}
            contentContainerStyle={{ paddingBottom: spacing.xxxl }}
            refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brand} />}
            renderItem={({ item }) => {
              const isOut = item.type === "send" || item.type === "withdraw";
              return (
                <View testID={`tx-${item.id}`} style={s.row}>
                  <View style={[s.icon, { backgroundColor: isOut ? "#FBE9E9" : colors.brandTertiary }]}>
                    <Ionicons name={typeIcon(item) as any} size={18} color={isOut ? colors.error : colors.brand} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={s.txTitle}>{item.counterparty}</Text>
                    <Text style={s.txMuted}>{new Date(item.created_at).toLocaleString()} · {item.category}</Text>
                  </View>
                  <View style={{ alignItems: "flex-end" }}>
                    <Text style={[s.amount, { color: isOut ? colors.error : colors.success }]}>
                      {isOut ? "-" : "+"}${item.fiat_value.toFixed(2)}
                    </Text>
                    <Text style={s.txMuted}>{item.amount} {item.asset}</Text>
                  </View>
                </View>
              );
            }}
            ItemSeparatorComponent={() => <View style={s.sep} />}
          />
        )}
      <ExportSheet visible={showExport} onClose={() => setShowExport(false)} />
    </SafeAreaView>
  );
}
const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.xl, paddingTop: spacing.md, paddingBottom: spacing.lg },
  title: { fontSize: 26, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.6 },
  exportBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary, borderWidth: 1, borderColor: "rgba(201,163,91,0.35)",
  },
  exportText: { fontSize: 12, color: colors.brandDeep, fontWeight: "700", letterSpacing: 0.3 },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingHorizontal: spacing.xl, paddingVertical: spacing.md },
  icon: { width: 40, height: 40, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  txTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  txMuted: { fontSize: 11, color: colors.onSurfaceTertiary, marginTop: 2 },
  amount: { fontSize: 15, fontWeight: "700" },
  sep: { height: 1, backgroundColor: colors.divider, marginLeft: spacing.xl + 40 + spacing.md },
  empty: { flex: 1, alignItems: "center", justifyContent: "center" },
  emptyText: { color: colors.onSurfaceSecondary, fontSize: 15 },
});
