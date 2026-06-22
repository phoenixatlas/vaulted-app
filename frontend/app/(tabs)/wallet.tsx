import { useCallback, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Pressable, RefreshControl, ActivityIndicator, ImageBackground,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { useAuth } from "@/src/lib/auth";
import { useI18n } from "@/src/lib/i18n";
import { colors, spacing, radius, ASSET_ICON_COLORS } from "@/src/lib/theme";

type Asset = { id: string; symbol: string; name: string; amount: number; price_usd: number; fiat_value: number };

export default function Wallet() {
  const { user } = useAuth();
  const { t } = useI18n();
  const router = useRouter();
  const [total, setTotal] = useState(0);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    try {
      const data = await api<{ total_usd: number; assets: Asset[] }>("/wallet/assets");
      setTotal(data.total_usd);
      setAssets(data.assets);
    } catch (e) {
      console.log("wallet load err", e);
    }
  };

  useFocusEffect(useCallback(() => { setLoading(true); load().finally(() => setLoading(false)); }, []));

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  const Action = ({ icon, label, onPress, testID }: any) => (
    <Pressable testID={testID} onPress={onPress} style={({ pressed }) => [s.action, pressed && { opacity: 0.7 }]}>
      <View style={s.actionIcon}><Ionicons name={icon} size={20} color={colors.brand} /></View>
      <Text style={s.actionLabel}>{label}</Text>
    </Pressable>
  );

  return (
    <SafeAreaView style={s.root} edges={["top"]}>
      <ScrollView
        contentContainerStyle={{ paddingBottom: spacing.xxxl }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brand} />}
      >
        <View style={s.header}>
          <View>
            <Text style={s.greet}>Hi, {user?.name?.split(" ")[0] ?? "there"}</Text>
            <Text style={s.subgreet}>{t("wallet")}</Text>
          </View>
          <Pressable testID="open-settings" onPress={() => router.push("/(tabs)/settings")} style={s.avatar}>
            <Ionicons name="person" size={20} color={colors.brand} />
          </Pressable>
        </View>

        <ImageBackground
          source={{ uri: "https://images.unsplash.com/photo-1636837955417-2d8a4e49368f?crop=entropy&cs=srgb&fm=jpg&w=1200&q=70" }}
          imageStyle={{ borderRadius: radius.lg, opacity: 0.12 }}
          style={s.hero}
        >
          <Text style={s.heroLabel}>{t("total_balance")}</Text>
          {loading ? (
            <ActivityIndicator color={colors.onSurfaceInverse} style={{ marginTop: 12 }} />
          ) : (
            <Text testID="total-balance" style={s.heroBalance}>${total.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 2 })}</Text>
          )}
          <View style={s.addrRow}>
            <Ionicons name="shield-checkmark" size={14} color={colors.onSurfaceInverse} />
            <Text style={s.addrText} numberOfLines={1}>{user?.wallet_address}</Text>
          </View>
        </ImageBackground>

        <View style={s.actionsRow}>
          <Action testID="action-send" icon="arrow-up" label={t("send")} onPress={() => router.push("/send")} />
          <Action testID="action-receive" icon="arrow-down" label={t("receive")} onPress={() => router.push("/receive")} />
          <Action testID="action-deposit" icon="add-circle-outline" label={t("deposit")} onPress={() => router.push("/fiat?mode=deposit")} />
          <Action testID="action-withdraw" icon="cash-outline" label={t("fiat")} onPress={() => router.push("/fiat?mode=withdraw")} />
        </View>

        <View style={s.sectionHeader}>
          <Text style={s.sectionTitle}>{t("assets")}</Text>
        </View>
        <View style={s.assetCard}>
          {assets.map((a, idx) => (
            <View key={a.id} testID={`asset-row-${a.symbol}`}>
              <View style={s.assetRow}>
                <View style={[s.assetIcon, { backgroundColor: ASSET_ICON_COLORS[a.symbol] ?? colors.brandTertiary }]}>
                  <Text style={s.assetSym}>{a.symbol.slice(0, 1)}</Text>
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={s.assetName}>{a.name}</Text>
                  <Text style={s.assetMuted}>{a.amount.toLocaleString(undefined, { maximumFractionDigits: 6 })} {a.symbol}</Text>
                </View>
                <View style={{ alignItems: "flex-end" }}>
                  <Text style={s.assetFiat}>${a.fiat_value.toLocaleString(undefined, { maximumFractionDigits: 2 })}</Text>
                  <Text style={s.assetMuted}>${a.price_usd.toLocaleString()}</Text>
                </View>
              </View>
              {idx < assets.length - 1 && <View style={s.divider} />}
            </View>
          ))}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: spacing.xl, paddingTop: spacing.md, paddingBottom: spacing.lg },
  greet: { fontSize: 22, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.5 },
  subgreet: { fontSize: 13, color: colors.onSurfaceSecondary, marginTop: 2 },
  avatar: { width: 40, height: 40, borderRadius: radius.pill, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  hero: { marginHorizontal: spacing.xl, borderRadius: radius.lg, backgroundColor: colors.surfaceInverse, padding: spacing.xl, overflow: "hidden" },
  heroLabel: { color: colors.onSurfaceInverse, opacity: 0.7, fontSize: 13, fontWeight: "500" },
  heroBalance: { color: colors.onSurfaceInverse, fontSize: 40, fontWeight: "700", marginTop: spacing.xs, letterSpacing: -1.2 },
  addrRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: spacing.lg, backgroundColor: "rgba(255,255,255,0.08)", paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.pill, alignSelf: "flex-start", maxWidth: "100%" },
  addrText: { color: colors.onSurfaceInverse, fontSize: 11, opacity: 0.85, maxWidth: 220 },
  actionsRow: { flexDirection: "row", justifyContent: "space-around", paddingHorizontal: spacing.xl, marginTop: spacing.xl },
  action: { alignItems: "center", gap: 6 },
  actionIcon: { width: 52, height: 52, borderRadius: radius.pill, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  actionLabel: { fontSize: 12, color: colors.onSurface, fontWeight: "500" },
  sectionHeader: { paddingHorizontal: spacing.xl, marginTop: spacing.xxl, marginBottom: spacing.md },
  sectionTitle: { fontSize: 18, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.4 },
  assetCard: { marginHorizontal: spacing.xl, borderRadius: radius.lg, backgroundColor: colors.surfaceSecondary, paddingVertical: spacing.xs },
  assetRow: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, paddingVertical: spacing.md, gap: spacing.md },
  assetIcon: { width: 40, height: 40, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  assetSym: { color: "#fff", fontWeight: "700", fontSize: 16 },
  assetName: { color: colors.onSurface, fontSize: 15, fontWeight: "600" },
  assetMuted: { color: colors.onSurfaceTertiary, fontSize: 12, marginTop: 2 },
  assetFiat: { color: colors.onSurface, fontSize: 15, fontWeight: "700" },
  divider: { height: 1, backgroundColor: colors.divider, marginLeft: spacing.lg + 40 + spacing.md },
});
