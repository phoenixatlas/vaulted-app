import { useEffect, useState } from "react";
import {
  View, Text, TextInput, StyleSheet, Pressable, ScrollView, ActivityIndicator,
  KeyboardAvoidingView, Platform, Linking,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { useAuth } from "@/src/lib/auth";
import { useI18n } from "@/src/lib/i18n";
import { colors, spacing, radius, ASSET_ICON_COLORS } from "@/src/lib/theme";

type Asset = {
  id: string; symbol: string; name: string; amount: number; fiat_value: number;
  on_chain?: boolean; network?: string | null;
};

export default function SendCrypto() {
  const { t } = useI18n();
  const { user } = useAuth();
  const router = useRouter();
  const [assets, setAssets] = useState<Asset[]>([]);
  const [sel, setSel] = useState<string>("ETH");
  const [amount, setAmount] = useState("");
  const [addr, setAddr] = useState("");
  const [memo, setMemo] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [gasGwei, setGasGwei] = useState<number | null>(null);

  useEffect(() => {
    api<{ assets: Asset[] }>("/wallet/assets").then((d) => setAssets(d.assets));
    api<{ gas_price_gwei: number }>("/wallet/eth/info").then((d) => setGasGwei(d.gas_price_gwei)).catch(() => {});
  }, []);

  const selected = assets.find((a) => a.symbol === sel);
  const isEth = sel === "ETH";
  const isPro = !!user?.is_pro;
  const baseServiceFee = isEth ? 0.10 : 0.10;
  const serviceFee = isPro ? baseServiceFee * 0.5 : baseServiceFee;

  const submit = async () => {
    setErr(null);
    const amt = parseFloat(amount);
    if (!amt || amt <= 0) { setErr("Enter a valid amount"); return; }
    if (!addr.trim()) { setErr("Enter recipient address"); return; }
    setSubmitting(true);
    try {
      let tx: any;
      if (isEth) {
        tx = await api("/wallet/eth/send", {
          method: "POST",
          body: { to_address: addr.trim(), amount_eth: amt },
        });
      } else {
        tx = await api("/wallet/send", {
          method: "POST",
          body: { asset: sel, amount: amt, to_address: addr.trim(), memo: memo.trim() || null },
        });
      }
      // Multi-sig: backend returns approval_required:true instead of a tx
      if (tx && tx.approval_required) {
        router.replace({ pathname: "/approvals" });
        return;
      }
      router.replace({ pathname: "/receipt", params: { ...(tx as any) } });
    } catch (e: any) { setErr(e.message); } finally { setSubmitting(false); }
  };

  return (
    <SafeAreaView style={s.root} edges={["top", "bottom"]}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1 }}>
        <View style={s.header}>
          <Pressable testID="send-back" onPress={() => router.back()}><Ionicons name="chevron-back" size={26} color={colors.onSurface} /></Pressable>
          <Text style={s.title}>{t("send_crypto")}</Text>
          <View style={{ width: 26 }} />
        </View>
        <ScrollView contentContainerStyle={{ padding: spacing.xl }} keyboardShouldPersistTaps="handled">
          <Text style={s.label}>Asset</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm, paddingVertical: 4 }} style={{ marginBottom: spacing.lg }}>
            {assets.map((a) => (
              <Pressable key={a.symbol} testID={`chip-${a.symbol}`} onPress={() => setSel(a.symbol)} style={[s.chip, sel === a.symbol && s.chipActive]}>
                <View style={[s.chipDot, { backgroundColor: ASSET_ICON_COLORS[a.symbol] ?? colors.brand }]} />
                <Text style={[s.chipText, sel === a.symbol && { color: colors.brand }]}>{a.symbol}</Text>
                {a.on_chain && <Ionicons name="globe-outline" size={12} color={sel === a.symbol ? colors.brand : colors.onSurfaceTertiary} />}
              </Pressable>
            ))}
          </ScrollView>
          {selected && (
            <View style={s.balRow}>
              <Text style={s.bal}>Available: {selected.amount.toLocaleString(undefined, {maximumFractionDigits: 6})} {selected.symbol}</Text>
              {isEth && (
                <View style={s.netPill}><Ionicons name="globe" size={10} color={colors.brand} /><Text style={s.netText}>Sepolia</Text></View>
              )}
            </View>
          )}

          <Text style={s.label}>{t("amount")}</Text>
          <TextInput testID="send-amount" value={amount} onChangeText={setAmount} keyboardType="decimal-pad" placeholder="0.00" placeholderTextColor={colors.onSurfaceTertiary} style={s.input} />

          <Text style={s.label}>{t("recipient")}</Text>
          <TextInput testID="send-address" value={addr} onChangeText={setAddr} autoCapitalize="none" placeholder={isEth ? "0x..." : "address"} placeholderTextColor={colors.onSurfaceTertiary} style={s.input} />

          {!isEth && (
            <>
              <Text style={s.label}>{t("memo")}</Text>
              <TextInput testID="send-memo" value={memo} onChangeText={setMemo} placeholder="optional" placeholderTextColor={colors.onSurfaceTertiary} style={s.input} />
            </>
          )}

          <View style={s.feeCard} testID="fee-summary">
            <View style={s.feeRow}>
              <Text style={s.feeLabel}>Network fee {isEth && gasGwei ? `(~${gasGwei.toFixed(2)} gwei)` : ""}</Text>
              <Text style={s.feeValue}>{isEth ? "~0.00002 ETH" : "$0.00"}</Text>
            </View>
            <View style={s.feeRow}>
              <Text style={s.feeLabel}>Vaulted service fee</Text>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                {isPro && <Text style={s.strike}>${baseServiceFee.toFixed(2)}</Text>}
                <Text style={s.feeValue}>${serviceFee.toFixed(2)}</Text>
                {isPro && <View style={s.proPill}><Text style={s.proPillText}>PRO -50%</Text></View>}
              </View>
            </View>
          </View>

          {err && <Text testID="send-error" style={s.error}>{err}</Text>}

          <Pressable testID="send-confirm" disabled={submitting} onPress={submit} style={({ pressed }) => [s.cta, pressed && { opacity: 0.85 }]}>
            {submitting ? <ActivityIndicator color="#fff" /> : <Text style={s.ctaText}>{t("confirm")} {isEth ? "on Sepolia" : ""}</Text>}
          </Pressable>

          {isEth && (
            <Pressable testID="faucet-link" onPress={() => Linking.openURL("https://sepoliafaucet.com/")} style={s.faucet}>
              <Ionicons name="water-outline" size={16} color={colors.brand} />
              <Text style={s.faucetText}>Need test ETH? Open Sepolia faucet</Text>
            </Pressable>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.xl, paddingTop: spacing.sm, paddingBottom: spacing.md },
  title: { fontSize: 17, fontWeight: "700", color: colors.onSurface },
  label: { fontSize: 13, color: colors.onSurfaceSecondary, marginBottom: spacing.xs, fontWeight: "500", marginTop: spacing.md },
  input: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.lg, paddingVertical: 14, fontSize: 16, color: colors.onSurface, backgroundColor: colors.surface },
  balRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm },
  bal: { color: colors.onSurfaceTertiary, fontSize: 12 },
  netPill: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.brandTertiary, paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.pill },
  netText: { fontSize: 10, color: colors.brand, fontWeight: "700" },
  chip: { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 14, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, flexShrink: 0, height: 36 },
  chipActive: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  chipDot: { width: 10, height: 10, borderRadius: 5 },
  chipText: { color: colors.onSurface, fontWeight: "600", fontSize: 13 },
  feeCard: { marginTop: spacing.lg, padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, gap: 6 },
  feeRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  feeLabel: { fontSize: 12, color: colors.onSurfaceSecondary },
  feeValue: { fontSize: 12, color: colors.onSurface, fontWeight: "600" },
  strike: { fontSize: 11, color: colors.onSurfaceTertiary, textDecorationLine: "line-through" },
  proPill: { backgroundColor: colors.brand, paddingHorizontal: 6, paddingVertical: 2, borderRadius: radius.pill },
  proPillText: { color: "#fff", fontSize: 9, fontWeight: "800", letterSpacing: 0.5 },
  cta: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: 16, alignItems: "center", marginTop: spacing.xl },
  ctaText: { color: "#fff", fontSize: 16, fontWeight: "600" },
  faucet: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, marginTop: spacing.lg, padding: spacing.sm },
  faucetText: { color: colors.brand, fontSize: 13, fontWeight: "500" },
  error: { color: colors.error, marginTop: spacing.md, fontSize: 14 },
});
