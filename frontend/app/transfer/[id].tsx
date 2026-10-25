/**
 * Transfer details — live tracking timeline + "Send again".
 * Polls every 8s until the transfer reaches a final state.
 */
import { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator, RefreshControl } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { useCurrency } from "@/src/lib/currency";
import TransferTimeline, { Step } from "@/src/components/TransferTimeline";
import ShareReceiptButton from "@/src/components/ShareReceiptButton";
import TellRecipientButton from "@/src/components/TellRecipientButton";
import { colors, spacing, radius } from "@/src/lib/theme";

type Detail = { tx: any; timeline: Step[]; is_final: boolean; repeat: Record<string, any> | null };

export default function TransferDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const { format } = useCurrency();
  const [data, setData] = useState<Detail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try { setData(await api<Detail>(`/transactions/${id}`)); setErr(null); }
    catch (e: any) { setErr(e?.status === 404 ? "Transfer not found." : e?.message || "Couldn't load this transfer."); }
  }, [id]);

  useEffect(() => { load(); }, [load]);
  // Poll only while this screen is focused and the transfer is still moving.
  useFocusEffect(useCallback(() => {
    if (!data || data.is_final) return;
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, [data, load]));

  const tx = data?.tx;
  const remit = tx?.remit;
  const payout = tx?.payout || tx?.kotani;
  const isTest = payout?.mode === "simulated" || payout?.mode === "mock";

  const sendAgain = () => {
    if (!data?.repeat) return;
    const params: Record<string, string> = {};
    Object.entries(data.repeat).forEach(([k, v]) => { if (v !== null && v !== undefined) params[k] = String(v); });
    router.push({ pathname: "/remit", params: { repeat: "1", ...params } });
  };

  return (
    <SafeAreaView style={s.root} edges={["top", "bottom"]}>
      <View style={s.header}>
        <Pressable testID="transfer-back" onPress={() => router.back()} hitSlop={10} style={s.headerBtn}>
          <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
        </Pressable>
        <Text style={s.title}>Transfer details</Text>
        <View style={s.headerBtn} />
      </View>

      {!data && !err && <ActivityIndicator color={colors.brand} style={{ marginTop: 60 }} />}
      {err && <Text style={s.err} testID="transfer-error">{err}</Text>}

      {tx && (
        <ScrollView
          contentContainerStyle={{ padding: spacing.xl, paddingBottom: spacing.xxxl }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} tintColor={colors.brand} />}
        >
          <View style={s.summary} testID="transfer-summary">
            <Text style={s.kicker}>{remit ? `To ${tx.recipient_name || "recipient"} · ${remit.destination_country}` : tx.category}</Text>
            <Text style={s.amount}>
              {remit ? `${Number(remit.destination_amount).toLocaleString(undefined, { maximumFractionDigits: 2 })} ${remit.destination_currency}` : format(tx.fiat_value)}
            </Text>
            {remit && <Text style={s.sub}>You sent {remit.source_amount} {remit.source_currency}</Text>}
            {!data.is_final && (
              <View style={s.liveChip}><View style={s.liveDot} /><Text style={s.liveText}>Updating live</Text></View>
            )}
          </View>

          <Text style={s.section}>Tracking</Text>
          <View style={s.card}><TransferTimeline steps={data.timeline} /></View>

          {isTest && (
            <Text style={s.testNote} testID="transfer-test-note">Test payout: no real money was sent to the recipient during the beta.</Text>
          )}

          <Text style={s.section}>Details</Text>
          <View style={s.card}>
            {!!tx.receipt_id && <Row label="Receipt ID" value={tx.receipt_id} />}
            {!!tx.recipient_bank?.name && <Row label="Bank" value={tx.recipient_bank.name} />}
            {!!tx.counterparty && <Row label="Account" value={String(tx.counterparty).length > 22 ? `${String(tx.counterparty).slice(0, 8)}…${String(tx.counterparty).slice(-6)}` : tx.counterparty} />}
            {!!payout?.provider_label && <Row label="Payout partner" value={isTest ? `${payout.provider_label} · test` : payout.provider_label} />}
            <Row label="Date" value={new Date(tx.created_at).toLocaleString()} />
          </View>

          {remit && (tx.status === "settled" || tx.status === "completed") && (
            <TellRecipientButton
              txId={tx.id}
              amountText={`${Number(remit.destination_amount).toLocaleString(undefined, { maximumFractionDigits: 2 })} ${remit.destination_currency}`}
              recipientName={tx.recipient_name}
              phone={tx.recipient_bank ? null : tx.counterparty}
            />
          )}

          {remit && (
            <ShareReceiptButton
              txId={tx.id}
              amountText={`${Number(remit.destination_amount).toLocaleString(undefined, { maximumFractionDigits: 2 })} ${remit.destination_currency}`}
              recipientName={tx.recipient_name}
            />
          )}

          {data.repeat && (
            <Pressable testID="transfer-send-again" onPress={sendAgain} style={s.cta}>
              <Ionicons name="repeat" size={18} color="#0F0B08" />
              <Text style={s.ctaText}>Send again</Text>
            </Pressable>
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const Row = ({ label, value }: { label: string; value: string }) => (
  <View style={s.row}>
    <Text style={s.rowLabel}>{label}</Text>
    <Text style={s.rowValue} numberOfLines={1}>{value}</Text>
  </View>
);

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  headerBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 17, fontWeight: "700", color: colors.onSurface },
  err: { color: colors.error, textAlign: "center", marginTop: 60, paddingHorizontal: spacing.xl },
  summary: { alignItems: "center", backgroundColor: colors.brandTertiary, borderRadius: radius.lg, padding: spacing.xl },
  kicker: { fontSize: 12, fontWeight: "700", color: colors.brandDeep, letterSpacing: 1, textTransform: "uppercase", textAlign: "center" },
  amount: { fontSize: 32, fontWeight: "700", color: colors.onSurface, marginTop: spacing.sm, letterSpacing: -1 },
  sub: { fontSize: 13, color: colors.onSurfaceSecondary, marginTop: 4 },
  liveChip: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: spacing.md, paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.pill, backgroundColor: colors.surface },
  liveDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.success },
  liveText: { fontSize: 12, fontWeight: "600", color: colors.onSurfaceSecondary },
  section: { fontSize: 13, fontWeight: "700", color: colors.onSurfaceSecondary, textTransform: "uppercase", letterSpacing: 0.8, marginTop: spacing.xl, marginBottom: spacing.sm },
  card: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, padding: spacing.lg, paddingRight: spacing.xl + 20, backgroundColor: colors.surface },
  testNote: { fontSize: 12, color: colors.onSurfaceSecondary, marginTop: spacing.sm, textAlign: "center" },
  row: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 8, gap: spacing.md },
  rowLabel: { fontSize: 13, color: colors.onSurfaceSecondary },
  rowValue: { fontSize: 13, fontWeight: "600", color: colors.onSurface, flexShrink: 1, textAlign: "right" },
  cta: { flexDirection: "row", gap: 8, backgroundColor: colors.brand, borderRadius: radius.md, minHeight: 52, alignItems: "center", justifyContent: "center", marginTop: spacing.xl },
  ctaText: { color: "#0F0B08", fontSize: 16, fontWeight: "700" },
});
