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

  // Remit context (set by /remit/send)
  let remit: any = null;
  try {
    if (p.remit_json) remit = JSON.parse(String(p.remit_json));
  } catch {
    remit = null;
  }
  const isRemit = !!remit;

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
          <Text style={s.successTitle}>
            {isRemit ? `Sent to ${remit.destination_flag} ${remit.destination_country}` : isFiat ? (p.type === "deposit" ? "Deposit successful" : "Withdrawal sent") : "Sent successfully"}
          </Text>
          {isRemit ? (
            <>
              <Text testID="receipt-amount" style={s.bigAmount}>
                {remit.destination_amount?.toLocaleString(undefined, { maximumFractionDigits: 2 })} {remit.destination_currency}
              </Text>
              <Text style={s.subAmount}>
                You sent {remit.source_amount} {remit.source_currency} · via {remit.chain}
              </Text>
            </>
          ) : (
            <Text testID="receipt-amount" style={s.bigAmount}>{isFiat ? `$${amount.toFixed(2)}` : `${amount} ${asset}`}</Text>
          )}

          <View style={s.dotted} />

          <Row label="Date" value={new Date().toLocaleString()} />
          {isRemit && <Row label="FX rate" value={`1 ${remit.source_currency} = ${remit.fx_rate?.toFixed(4)} ${remit.destination_currency}`} />}
          {isRemit && <Row label="Delivery" value={remit.receive_via} />}
          <Row label={isFiat ? "Method" : isRemit ? "Recipient wallet" : "To"} value={counterparty.length > 22 ? counterparty.slice(0, 8) + "…" + counterparty.slice(-6) : counterparty} />
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
  title: { fontSize: 17, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.3 },
  body: { flex: 1, padding: spacing.xl, alignItems: "center", justifyContent: "space-between" },
  ticket: { width: "100%", backgroundColor: colors.brandTertiary, borderRadius: radius.lg, padding: spacing.xl, alignItems: "center", borderWidth: 1, borderColor: "rgba(201,163,91,0.40)", shadowColor: colors.brand, shadowOpacity: 0.15, shadowRadius: 18, shadowOffset: { width: 0, height: 6 } },
  successIcon: { width: 64, height: 64, borderRadius: 32, backgroundColor: colors.success, alignItems: "center", justifyContent: "center", marginBottom: spacing.md, borderWidth: 2, borderColor: colors.brand },
  successTitle: { fontSize: 13, color: colors.brandDeep, fontWeight: "700", letterSpacing: 1.5, textTransform: "uppercase" },
  bigAmount: { fontSize: 36, fontWeight: "700", color: colors.onSurface, marginTop: spacing.sm, marginBottom: spacing.md, letterSpacing: -1.2 },
  subAmount: { fontSize: 13, color: colors.onSurfaceSecondary, marginTop: -spacing.sm, marginBottom: spacing.md, fontWeight: "500" },
  dotted: { width: "100%", borderBottomWidth: 1, borderStyle: "dashed", borderColor: "rgba(201,163,91,0.45)", marginVertical: spacing.lg },
  row: { flexDirection: "row", justifyContent: "space-between", width: "100%", paddingVertical: spacing.sm },
  rowLabel: { color: colors.brandDeep, fontSize: 12, fontWeight: "600", letterSpacing: 0.5, textTransform: "uppercase" },
  rowValue: { color: colors.onSurface, fontSize: 13, fontWeight: "600", maxWidth: "60%" },
  cta: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: 16, alignItems: "center", width: "100%", shadowColor: colors.brand, shadowOpacity: 0.30, shadowRadius: 12, shadowOffset: { width: 0, height: 4 } },
  ctaText: { color: "#0F0B08", fontSize: 16, fontWeight: "700", letterSpacing: 0.3 },
});
