import { useState } from "react";
import {
  View, Text, TextInput, StyleSheet, Pressable, ActivityIndicator,
  KeyboardAvoidingView, Platform, ScrollView,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { useI18n } from "@/src/lib/i18n";
import { startDepositCheckout, syncStripeSession } from "@/src/lib/stripe";
import { useAuth } from "@/src/lib/auth";
import { colors, spacing, radius } from "@/src/lib/theme";

export default function Fiat() {
  const params = useLocalSearchParams<{ mode?: string }>();
  const mode = params.mode === "withdraw" ? "withdraw" : "deposit";
  const { t } = useI18n();
  const router = useRouter();
  const { refresh } = useAuth();
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<"stripe" | "card" | "bank" | "applepay">("stripe");
  const [err, setErr] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    setErr(null);
    const amt = parseFloat(amount);
    if (!amt || amt <= 0) {
      setErr("Enter a valid amount");
      return;
    }
    setSubmitting(true);
    try {
      if (mode === "deposit" && method === "stripe") {
        const r = await startDepositCheckout(amt);
        if (r.status === "success" && r.session_id) {
          const synced = await syncStripeSession(r.session_id);
          await refresh();
          router.replace({
            pathname: "/receipt",
            params: { ...(synced.applied && synced.applied.amount_usd ? { amount: String(synced.applied.amount_usd) } : { amount: String(amt) }), category: "fiat", asset: "USD", type: "deposit", counterparty: "Stripe Card Top-up", receipt_id: r.session_id.slice(-8).toUpperCase() } as any,
          });
        } else if (r.status === "cancel") {
          setErr("Checkout canceled");
        } else if (r.session_id) {
          // Web flow already navigated; nothing to do
        }
      } else {
        const tx = await api(`/fiat/${mode}`, {
          method: "POST",
          body: { amount: amt, currency: "USD", method: method === "stripe" ? "card" : method },
        });
        router.replace({ pathname: "/receipt", params: tx as any });
      }
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const MethodChip = ({ id, icon, label, badge }: any) => (
    <Pressable testID={`method-${id}`} onPress={() => setMethod(id)} style={[s.method, method === id && s.methodActive]}>
      <Ionicons name={icon} size={18} color={method === id ? colors.brand : colors.onSurfaceSecondary} />
      <Text style={[s.methodText, method === id && { color: colors.brand }]}>{label}</Text>
      {badge && <View style={s.liveBadge}><Text style={s.liveText}>{badge}</Text></View>}
    </Pressable>
  );

  return (
    <SafeAreaView style={s.root} edges={["top", "bottom"]}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1 }}>
        <View style={s.header}>
          <Pressable testID="fiat-back" onPress={() => router.back()}>
            <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
          </Pressable>
          <Text style={s.title}>{mode === "deposit" ? t("deposit_funds") : t("withdraw_funds")}</Text>
          <View style={{ width: 26 }} />
        </View>
        <ScrollView contentContainerStyle={{ padding: spacing.xl }} keyboardShouldPersistTaps="handled">
          <Text style={s.bigLabel}>USD amount</Text>
          <View style={s.amountWrap}>
            <Text style={s.amountSign}>$</Text>
            <TextInput
              testID="fiat-amount"
              value={amount}
              onChangeText={setAmount}
              keyboardType="decimal-pad"
              placeholder="0"
              placeholderTextColor={colors.onSurfaceTertiary}
              style={s.amountInput}
            />
          </View>

          <Text style={s.label}>Payment method</Text>
          <View style={s.methodsRow}>
            {mode === "deposit" && <MethodChip id="stripe" icon="card" label="Card via Stripe" badge="LIVE" />}
            <MethodChip id="card" icon="card-outline" label={mode === "deposit" ? "Card (demo)" : "Card"} />
            <MethodChip id="bank" icon="business-outline" label="Bank" />
            <MethodChip id="applepay" icon="logo-apple" label="Apple Pay" />
          </View>

          {err && <Text testID="fiat-error" style={s.error}>{err}</Text>}
          <Pressable
            testID="fiat-confirm"
            disabled={submitting}
            onPress={submit}
            style={({ pressed }) => [s.cta, pressed && { opacity: 0.85 }]}
          >
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
  bigLabel: { fontSize: 13, color: colors.onSurfaceSecondary, marginBottom: spacing.sm, fontWeight: "500" },
  amountWrap: { flexDirection: "row", alignItems: "center", borderRadius: radius.lg, backgroundColor: colors.surfaceSecondary, paddingHorizontal: spacing.lg, paddingVertical: spacing.lg },
  amountSign: { fontSize: 36, fontWeight: "700", color: colors.onSurfaceTertiary, marginRight: 6 },
  amountInput: { flex: 1, fontSize: 36, fontWeight: "700", color: colors.onSurface, padding: 0 },
  label: { fontSize: 13, color: colors.onSurfaceSecondary, marginTop: spacing.xl, marginBottom: spacing.sm, fontWeight: "500" },
  methodsRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  method: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border },
  methodActive: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  methodText: { color: colors.onSurfaceSecondary, fontWeight: "600", fontSize: 13 },
  liveBadge: { backgroundColor: colors.brand, paddingHorizontal: 6, paddingVertical: 2, borderRadius: radius.pill, marginLeft: 4 },
  liveText: { color: "#fff", fontSize: 9, fontWeight: "800", letterSpacing: 0.5 },
  cta: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: 16, alignItems: "center", marginTop: spacing.xl },
  ctaText: { color: "#fff", fontSize: 16, fontWeight: "600" },
  error: { color: colors.error, marginTop: spacing.md, fontSize: 14 },
});
