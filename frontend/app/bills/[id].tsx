/** Bill payment detail with status timeline. */
import { useCallback, useState } from "react";
import { View, Text, ScrollView, ActivityIndicator } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect, useLocalSearchParams } from "expo-router";
import { api } from "@/src/lib/api";
import { colors, spacing } from "@/src/lib/theme";
import { Bill, BillHeader, QuoteRow, STATUS_LABEL, TestModeBanner, bs, money } from "@/src/features/bills/shared";

export default function BillDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [bill, setBill] = useState<Bill | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useFocusEffect(useCallback(() => { api<Bill>(`/bills/${id}`).then(setBill).catch((e) => setErr(e.message)); }, [id]));

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <BillHeader title="Bill payment" />
      {!bill ? (
        <View style={{ padding: spacing.xl }}>{err ? <Text style={bs.err}>{err}</Text> : <ActivityIndicator color={colors.brand} />}</View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 140 }}>
          <TestModeBanner />
          <Text style={{ fontSize: 22, fontWeight: "800", color: colors.onSurface }} testID="bill-detail-institution">{bill.institution}</Text>
          <Text style={{ fontSize: 14, color: colors.onSurfaceSecondary, marginTop: 4 }}>
            {bill.subtype} · {bill.beneficiary_name} · {bill.reference}
          </Text>
          <Text testID="bill-detail-status" style={{ marginTop: spacing.md, fontSize: 15, fontWeight: "800",
            color: bill.status === "rejected" ? colors.error : bill.status === "paid" ? colors.success : colors.brandDeep }}>
            {STATUS_LABEL[bill.status] || bill.status}
          </Text>

          <Text style={bs.section}>Quote</Text>
          <View style={bs.card}>
            <QuoteRow label="Institution receives" value={money(bill.quote.payout_amount, bill.quote.payout_currency)} strong />
            <QuoteRow label="Rate" value={`${bill.quote.rate.toLocaleString()} ${bill.quote.payer_currency}`} />
            <QuoteRow label="Partner fee" value={money(bill.quote.fee, bill.quote.payer_currency)} />
            <QuoteRow label="Total" value={money(bill.quote.total, bill.quote.payer_currency)} strong />
            <QuoteRow label="Partner" value={`${bill.quote.provider.label} (${bill.quote.provider.mode} mode)`} />
            <QuoteRow label="Paid to" value={`${bill.payee.name} · ${bill.payee.bank_name}`} />
          </View>

          <Text style={bs.section}>Timeline</Text>
          {bill.timeline.map((e, i) => (
            <View key={i} style={{ flexDirection: "row", gap: 12, paddingVertical: 8 }} testID={`bill-event-${e.status}`}>
              <View style={{ width: 10, height: 10, borderRadius: 5, marginTop: 5,
                backgroundColor: e.status === "rejected" ? colors.error : e.status === "paid" ? colors.success : colors.brand }} />
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 14, color: colors.onSurface, fontWeight: "600" }}>{e.label}</Text>
                <Text style={{ fontSize: 12, color: colors.onSurfaceTertiary }}>{new Date(e.at).toLocaleString()}</Text>
              </View>
            </View>
          ))}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}
