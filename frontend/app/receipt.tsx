import { View, Text, StyleSheet, Pressable } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useI18n } from "@/src/lib/i18n";
import { colors, spacing, radius } from "@/src/lib/theme";

export default function Receipt() {
  const p = useLocalSearchParams<any>();
  const { t } = useI18n();
  const router = useRouter();
  const isFiat = p.category === "fiat";
  const amount = parseFloat(String(p.amount ?? p.fiat_value ?? "0"));
  const asset = String(p.asset ?? "USD");
  const ref = String(p.receipt_id ?? p.tx_hash ?? p.id ?? "");
  const counterparty = String(p.counterparty ?? "");

  return (
    <SafeAreaView style={s.root} edges={["top", "bottom"]}>
      <View style={s.header}>
        <View style={{ width: 26 }} />
        <Text style={s.title}>{t("receipt")}</Text>
        <Pressable testID="receipt-close" onPress={() => router.replace("/(tabs)/activity")}><Ionicons name="close" size={26} color={colors.onSurface} /></Pressable>
      </View>
      <View style={s.body}>
        <View testID="receipt-card" style={s.ticket}>
          <View style={s.successIcon}><Ionicons name="checkmark" size={32} color="#fff" /></View>
          <Text style={s.successTitle}>{isFiat ? (p.type === "deposit" ? "Deposit successful" : "Withdrawal sent") : "Sent successfully"}</Text>
          <Text testID="receipt-amount" style={s.bigAmount}>{isFiat ? `$${amount.toFixed(2)}` : `${amount} ${asset}`}</Text>

          <View style={s.dotted} />

          <Row label="Date" value={new Date().toLocaleString()} />
          <Row label={isFiat ? "Method" : "To"} value={counterparty} />
          <Row label={isFiat ? "Receipt ID" : "Tx hash"} value={ref.length > 22 ? ref.slice(0, 12) + "…" + ref.slice(-6) : ref} />
          <Row label="Status" value="Completed" valueColor={colors.success} />
        </View>
        <Pressable testID="receipt-done" onPress={() => router.replace("/(tabs)/wallet")} style={s.cta}>
          <Text style={s.ctaText}>{t("done")}</Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

const Row = ({ label, value, valueColor }: any) => (
  <View style={s.row}>
    <Text style={s.rowLabel}>{label}</Text>
    <Text style={[s.rowValue, valueColor && { color: valueColor }]}>{value}</Text>
  </View>
);

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.xl, paddingTop: spacing.sm, paddingBottom: spacing.md },
  title: { fontSize: 17, fontWeight: "700", color: colors.onSurface },
  body: { flex: 1, padding: spacing.xl, alignItems: "center", justifyContent: "space-between" },
  ticket: { width: "100%", backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.xl, alignItems: "center" },
  successIcon: { width: 64, height: 64, borderRadius: 32, backgroundColor: colors.success, alignItems: "center", justifyContent: "center", marginBottom: spacing.md },
  successTitle: { fontSize: 16, color: colors.onSurfaceSecondary, fontWeight: "500" },
  bigAmount: { fontSize: 32, fontWeight: "700", color: colors.onSurface, marginTop: spacing.xs, marginBottom: spacing.md, letterSpacing: -1 },
  dotted: { width: "100%", borderBottomWidth: 1, borderStyle: "dashed", borderColor: colors.borderStrong, marginVertical: spacing.lg },
  row: { flexDirection: "row", justifyContent: "space-between", width: "100%", paddingVertical: spacing.sm },
  rowLabel: { color: colors.onSurfaceTertiary, fontSize: 13 },
  rowValue: { color: colors.onSurface, fontSize: 13, fontWeight: "600", maxWidth: "60%" },
  cta: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: 16, alignItems: "center", width: "100%" },
  ctaText: { color: "#fff", fontSize: 16, fontWeight: "600" },
});
