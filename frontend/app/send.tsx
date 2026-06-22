import { useEffect, useState } from "react";
import {
  View, Text, TextInput, StyleSheet, Pressable, ScrollView, ActivityIndicator,
  KeyboardAvoidingView, Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { useI18n } from "@/src/lib/i18n";
import { colors, spacing, radius, ASSET_ICON_COLORS } from "@/src/lib/theme";

type Asset = { id: string; symbol: string; name: string; amount: number; fiat_value: number };

export default function SendCrypto() {
  const { t } = useI18n();
  const router = useRouter();
  const [assets, setAssets] = useState<Asset[]>([]);
  const [sel, setSel] = useState<string>("BTC");
  const [amount, setAmount] = useState("");
  const [addr, setAddr] = useState("");
  const [memo, setMemo] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => { api<{ assets: Asset[] }>("/wallet/assets").then((d) => setAssets(d.assets)); }, []);

  const selected = assets.find((a) => a.symbol === sel);

  const submit = async () => {
    setErr(null);
    const amt = parseFloat(amount);
    if (!amt || amt <= 0) { setErr("Enter a valid amount"); return; }
    if (!addr.trim()) { setErr("Enter recipient address"); return; }
    setSubmitting(true);
    try {
      const tx = await api("/wallet/send", { method: "POST", body: { asset: sel, amount: amt, to_address: addr.trim(), memo: memo.trim() || null } });
      router.replace({ pathname: "/receipt", params: { id: (tx as any).id, ...tx as any } });
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
              </Pressable>
            ))}
          </ScrollView>
          {selected && <Text style={s.bal}>Available: {selected.amount} {selected.symbol}</Text>}

          <Text style={s.label}>{t("amount")}</Text>
          <TextInput testID="send-amount" value={amount} onChangeText={setAmount} keyboardType="decimal-pad" placeholder="0.00" placeholderTextColor={colors.onSurfaceTertiary} style={s.input} />

          <Text style={s.label}>{t("recipient")}</Text>
          <TextInput testID="send-address" value={addr} onChangeText={setAddr} autoCapitalize="none" placeholder="0x..." placeholderTextColor={colors.onSurfaceTertiary} style={s.input} />

          <Text style={s.label}>{t("memo")}</Text>
          <TextInput testID="send-memo" value={memo} onChangeText={setMemo} placeholder="optional" placeholderTextColor={colors.onSurfaceTertiary} style={s.input} />

          {err && <Text testID="send-error" style={s.error}>{err}</Text>}

          <Pressable testID="send-confirm" disabled={submitting} onPress={submit} style={({ pressed }) => [s.cta, pressed && { opacity: 0.85 }]}>
            {submitting ? <ActivityIndicator color="#fff" /> : <Text style={s.ctaText}>{t("confirm")}</Text>}
          </Pressable>
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
  bal: { color: colors.onSurfaceTertiary, fontSize: 12, marginBottom: spacing.sm },
  chip: { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 14, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, flexShrink: 0, height: 36 },
  chipActive: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  chipDot: { width: 10, height: 10, borderRadius: 5 },
  chipText: { color: colors.onSurface, fontWeight: "600", fontSize: 13 },
  cta: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: 16, alignItems: "center", marginTop: spacing.xl },
  ctaText: { color: "#fff", fontSize: 16, fontWeight: "600" },
  error: { color: colors.error, marginTop: spacing.md, fontSize: 14 },
});
