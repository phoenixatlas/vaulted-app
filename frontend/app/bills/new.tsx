/** New International Bill Payment: purpose → invoice → FX quote → submit. */
import { useEffect, useState } from "react";
import { View, Text, TextInput, Pressable, ScrollView, ActivityIndicator, KeyboardAvoidingView, Platform, Switch } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import * as DocumentPicker from "expo-document-picker";
import { router, useLocalSearchParams } from "expo-router";
import { api, API_BASE, getToken } from "@/src/lib/api";
import { uploadForm } from "@/src/utils/upload";
import { colors, spacing } from "@/src/lib/theme";
import { BillConfig, BillHeader, BillQuote, Chip, QuoteRow, TestModeBanner, bs, money } from "@/src/features/bills/shared";

type Invoice = { invoice_path: string; invoice_name: string };

export default function NewBill() {
  const params = useLocalSearchParams<{ category?: string }>();
  const [cfg, setCfg] = useState<BillConfig | null>(null);
  const [category, setCategory] = useState(params.category || "education");
  const [subtype, setSubtype] = useState("");
  const [purpose, setPurpose] = useState<Record<string, string>>({});
  const [payer, setPayer] = useState("NG");
  const [payout, setPayout] = useState("GBP");
  const [amount, setAmount] = useState("");
  const [payee, setPayee] = useState({ name: "", bank_name: "", account_number: "", routing: "", swift: "", address: "", reference: "" });
  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [quote, setQuote] = useState<BillQuote | null>(null);
  const [declared, setDeclared] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { api<BillConfig>("/bills/config").then(setCfg).catch((e) => setErr(e.message)); }, []);
  const cat = cfg?.categories.find((c) => c.id === category);
  const cur = cfg?.payout_currencies.find((c) => c.code === payout);
  useEffect(() => { setQuote(null); }, [category, payer, payout, amount]);

  const pickInvoice = async () => {
    setErr(null);
    const res = await DocumentPicker.getDocumentAsync({ type: ["application/pdf", "image/jpeg", "image/png"], copyToCacheDirectory: true });
    if (res.canceled || !res.assets?.[0]) return;
    const f = res.assets[0];
    setBusy("upload");
    try {
      const token = await getToken();
      const r = await uploadForm(`${API_BASE}/api/bills/invoice`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        files: { file: { uri: f.uri, name: f.name || "invoice.pdf", mimeType: f.mimeType } },
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "Upload failed");
      setInvoice(d);
    } catch (e: any) { setErr(e.message || "Upload failed"); } finally { setBusy(null); }
  };

  const getQuote = async () => {
    setErr(null); setBusy("quote");
    try {
      setQuote(await api<BillQuote>("/bills/quote", { method: "POST", body: { category, payer_country: payer, payout_currency: payout, amount: Number(amount) } }));
    } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  };

  const missing = !subtype ? "Choose what the payment is for."
    : cat?.fields.some((f) => !(purpose[f.key] || "").trim()) ? "Fill in the purpose details."
    : !payee.name || !payee.bank_name || !payee.account_number || !payee.reference ? "Fill in the payee's bank details from the invoice."
    : !invoice ? "Upload the supporting invoice."
    : !quote ? "Get your FX quote."
    : !declared ? "Confirm the declaration." : null;

  const submit = async () => {
    if (missing) { setErr(missing); return; }
    setErr(null); setBusy("submit");
    try {
      const bill = await api<{ id: string }>("/bills", { method: "POST", body: {
        category, subtype, payer_country: payer, payout_currency: payout, amount: Number(amount),
        beneficiary_name: purpose.beneficiary_name, beneficiary_ref: purpose.beneficiary_ref, institution: purpose.institution,
        payee, invoice_path: invoice!.invoice_path, invoice_name: invoice!.invoice_name, quote_id: quote!.id, declaration: declared } });
      router.replace(`/bills/${bill.id}`);
    } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  };

  const field = (key: keyof typeof payee, label: string, opts: object = {}) => (
    <TextInput testID={`bill-payee-${key}`} placeholder={label} placeholderTextColor={colors.onSurfaceTertiary} style={bs.input}
      value={payee[key]} onChangeText={(v) => setPayee((p) => ({ ...p, [key]: v }))} autoCapitalize="characters" {...opts} />
  );

  if (!cfg) return <SafeAreaView style={{ flex: 1, justifyContent: "center" }}><ActivityIndicator color={colors.brand} /></SafeAreaView>;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <BillHeader title="New bill payment" />
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingRight: spacing.lg + 8, paddingBottom: 140 }} keyboardShouldPersistTaps="handled">
          <TestModeBanner />
          <Text style={bs.section}>1 · Payment purpose</Text>
          <View style={{ flexDirection: "row", gap: 8, flexWrap: "wrap" }}>
            {cfg.categories.map((c) => (
              <Chip key={c.id} testID={`bill-category-${c.id}`} label={c.label} active={c.id === category}
                onPress={() => { setCategory(c.id); setSubtype(""); }} />
            ))}
          </View>
          <Text style={[bs.qLabel, { marginTop: spacing.md, marginBottom: 6 }]}>What is it for?</Text>
          <View style={{ flexDirection: "row", gap: 8, flexWrap: "wrap", marginBottom: spacing.md }}>
            {cat?.subtypes.map((s) => <Chip key={s} testID={`bill-subtype-${s.split(" ")[0].toLowerCase()}`} label={s} active={s === subtype} onPress={() => setSubtype(s)} />)}
          </View>
          {cat?.fields.map((f) => (
            <TextInput key={f.key} testID={`bill-purpose-${f.key}`} placeholder={f.label} placeholderTextColor={colors.onSurfaceTertiary}
              style={bs.input} value={purpose[f.key] || ""} onChangeText={(v) => setPurpose((p) => ({ ...p, [f.key]: v }))} />
          ))}

          <Text style={bs.section}>2 · Payee details (from the invoice)</Text>
          {field("name", "Payee / account name")}
          {field("bank_name", "Bank name", { autoCapitalize: "words" })}
          {field("account_number", payout === "EUR" || payout === "GBP" ? "IBAN or account number" : "Account number")}
          {payout !== "EUR" && field("routing", cur?.routing_label || "Routing code")}
          {field("swift", "SWIFT / BIC (international)")}
          {field("address", "Payee address (optional)", { autoCapitalize: "words" })}
          {field("reference", "Payment reference on the invoice")}
          <Pressable testID="bill-upload-invoice" onPress={pickInvoice} style={[bs.card, { flexDirection: "row", alignItems: "center", gap: 10, minHeight: 56 }]}>
            {busy === "upload" ? <ActivityIndicator color={colors.brand} /> :
              <Ionicons name={invoice ? "checkmark-circle" : "cloud-upload-outline"} size={22} color={invoice ? colors.success : colors.brandDeep} />}
            <Text style={{ flex: 1, color: colors.onSurface, fontWeight: "600" }} numberOfLines={1}>
              {invoice ? invoice.invoice_name : "Upload invoice or supporting document (PDF, JPG, PNG)"}
            </Text>
          </Pressable>

          <Text style={bs.section}>3 · Amount & FX quote</Text>
          <Text style={[bs.qLabel, { marginBottom: 6 }]}>Paying from</Text>
          <View style={{ flexDirection: "row", gap: 8, flexWrap: "wrap", marginBottom: spacing.md }}>
            {cfg.payer_countries.map((c) => <Chip key={c.code} testID={`bill-payer-${c.code}`} label={`${c.name} (${c.currency})`} active={c.code === payer} onPress={() => setPayer(c.code)} />)}
          </View>
          <Text style={[bs.qLabel, { marginBottom: 6 }]}>Institution is paid in</Text>
          <View style={{ flexDirection: "row", gap: 8, flexWrap: "wrap", marginBottom: spacing.md }}>
            {cfg.payout_currencies.map((c) => <Chip key={c.code} testID={`bill-payout-${c.code}`} label={c.code} active={c.code === payout} onPress={() => setPayout(c.code)} />)}
          </View>
          <TextInput testID="bill-amount" placeholder={`Invoice amount in ${payout}`} placeholderTextColor={colors.onSurfaceTertiary}
            style={bs.input} keyboardType="decimal-pad" value={amount} onChangeText={setAmount} />
          <Pressable testID="bill-get-quote" disabled={!Number(amount) || busy === "quote"} onPress={getQuote}
            style={[bs.cta, { marginTop: 0, opacity: Number(amount) ? 1 : 0.5 }]}>
            {busy === "quote" ? <ActivityIndicator color="#0F0B08" /> : <Text style={bs.ctaText}>Get FX quote</Text>}
          </Pressable>

          {quote && (
            <View style={[bs.card, { marginTop: spacing.md }]} testID="bill-quote">
              <QuoteRow label="Institution receives" value={money(quote.payout_amount, quote.payout_currency)} strong />
              <QuoteRow label="Mid-market rate" value={`1 ${quote.payout_currency} = ${quote.mid_market_rate.toLocaleString()} ${quote.payer_currency}`} />
              <QuoteRow label={`Your rate (incl. ${quote.fx_margin_pct.toFixed(1)}% FX margin)`} value={`${quote.rate.toLocaleString()} ${quote.payer_currency}`} />
              <QuoteRow label="Converted amount" value={money(quote.principal, quote.payer_currency)} />
              <QuoteRow label="Partner fee" value={money(quote.fee, quote.payer_currency)} />
              <QuoteRow label="You pay" value={money(quote.total, quote.payer_currency)} strong />
              <QuoteRow label="Partner" value={`${quote.provider.label} (${quote.provider.mode} mode)`} />
              <QuoteRow label="Rail · Settlement" value={`${quote.rail} · ${quote.provider.settlement}`} />
              <Text style={[bs.qLabel, { marginTop: 6 }]}>Quote valid 15 minutes. Test mode — no money is collected.</Text>
            </View>
          )}

          <View style={{ flexDirection: "row", alignItems: "center", gap: 12, marginTop: spacing.lg }}>
            <Switch testID="bill-declaration" value={declared} onValueChange={setDeclared} />
            <Text style={{ flex: 1, fontSize: 13, color: colors.onSurface }}>
              I confirm this payment is for the stated {cat?.label.toLowerCase()} purpose and the invoice is genuine.
            </Text>
          </View>
          {err && <Text style={bs.err} testID="bill-error">{err}</Text>}
          <Pressable testID="bill-submit" onPress={submit} disabled={busy === "submit"} style={[bs.cta, missing ? { opacity: 0.6 } : null]}>
            {busy === "submit" ? <ActivityIndicator color="#0F0B08" /> : <Text style={bs.ctaText}>Submit for review</Text>}
          </Pressable>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
