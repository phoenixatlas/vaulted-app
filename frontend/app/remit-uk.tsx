/** Send to UK/EU — pay a UK (Faster Payments) or euro (SEPA) bank account. Beta test mode via Flutterwave sandbox. */
import { useEffect, useState } from "react";
import { View, Text, TextInput, Pressable, ScrollView, ActivityIndicator, KeyboardAvoidingView, Platform } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { router, useLocalSearchParams } from "expo-router";
import { api } from "@/src/lib/api";
import { colors, spacing } from "@/src/lib/theme";
import { BillHeader, Chip, QuoteRow, TestModeBanner, bs, money } from "@/src/features/bills/shared";

type Quote = {
  source: { currency: string; amount: number; country: string };
  destination: { currency: string; amount: number; receive_via: string };
  rates: { all_in_source_per_dest: number };
  eta: string;
};
type Tx = { id: string; status: string; receipt_id: string; recipient_name: string; amount: number; asset: string; payout?: { mode: string; provider_label: string } };

const PURPOSES = ["University fees", "Medical treatment", "Rent / mortgage", "Family support", "Business invoice"];
const EU_COUNTRIES = [["DE", "Germany"], ["FR", "France"], ["IE", "Ireland"], ["NL", "Netherlands"], ["ES", "Spain"], ["IT", "Italy"], ["BE", "Belgium"], ["PT", "Portugal"]];

export default function RemitUK() {
  const p = useLocalSearchParams<{ src: string; dst: string; amount: string }>();
  const isGbp = (p.dst || "GBP") === "GBP";
  const [quote, setQuote] = useState<Quote | null>(null);
  const [purpose, setPurpose] = useState("");
  const [country, setCountry] = useState(isGbp ? "GB" : "DE");
  const [f, setF] = useState({ name: "", email: "", phone: "", bank_name: "", account_number: "", sort_code: "", swift_code: "", line1: "", city: "", postal_code: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<Tx | null>(null);

  useEffect(() => {
    api<Quote>("/remit/reverse/quote", { method: "POST", body: { source_country: p.src, source_amount: Number(p.amount), destination_currency: p.dst } })
      .then(setQuote).catch((e) => setErr(e.message));
  }, [p.src, p.amount, p.dst]);

  const set = (k: keyof typeof f) => (v: string) => setF((x) => ({ ...x, [k]: v }));
  const input = (k: keyof typeof f, label: string, opts: object = {}) => (
    <TextInput testID={`uk-${k}`} placeholder={label} placeholderTextColor={colors.onSurfaceTertiary} style={bs.input}
      value={f[k]} onChangeText={set(k)} {...opts} />
  );

  const missing = !purpose ? "Choose what the payment is for."
    : !f.name || !f.email || !f.bank_name || !f.account_number || !f.line1 || !f.city || !f.postal_code ? "Fill in the recipient's details."
    : isGbp && !f.sort_code ? "Enter the sort code."
    : !isGbp && !f.swift_code ? "Enter the SWIFT / BIC code." : null;

  const submit = async () => {
    if (missing) { setErr(missing); return; }
    setErr(null); setBusy(true);
    try {
      const tx = await api<Tx>("/remit/reverse/send", { method: "POST", body: {
        source_country: p.src, source_amount: Number(p.amount), destination_currency: p.dst, purpose,
        recipient: { name: f.name, email: f.email, phone: f.phone, bank_name: f.bank_name, account_number: f.account_number,
          sort_code: f.sort_code, swift_code: f.swift_code,
          address: { line1: f.line1, city: f.city, postal_code: f.postal_code, country } } } });
      setDone(tx);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  if (done) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top", "bottom"]}>
        <BillHeader title="Transfer sent" />
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingRight: spacing.lg + 40, paddingBottom: 120 }}>
          <View style={{ alignItems: "center", marginVertical: spacing.xl }} testID="uk-success">
            <Ionicons name="checkmark-circle" size={64} color={colors.success} />
            <Text style={{ fontSize: 22, fontWeight: "800", color: colors.onSurface, marginTop: spacing.md, textAlign: "center" }}>
              {money(done.amount, done.asset)} to {done.recipient_name}
            </Text>
            <Text style={{ fontSize: 14, color: colors.onSurfaceSecondary, marginTop: 6 }}>
              {done.status === "settled" ? "Delivered (test mode)" : "Processing with Flutterwave (sandbox)"}
            </Text>
          </View>
          <View style={bs.card}>
            <QuoteRow label="Receipt" value={done.receipt_id} />
            <QuoteRow label="Partner" value={`${done.payout?.provider_label || "Flutterwave"} · ${done.payout?.mode === "live" ? "sandbox" : done.payout?.mode || "test"}`} />
            <QuoteRow label="Status" value={done.status === "settled" ? "Delivered" : "Processing"} strong />
          </View>
          <Text style={[bs.qLabel, { marginTop: spacing.md }]}>Test mode — no money was collected and no real payment was made. You&apos;ll see this transfer in Activity.</Text>
          <Pressable testID="uk-done" onPress={() => router.replace("/(tabs)/activity")} style={bs.cta}>
            <Text style={bs.ctaText}>View in Activity</Text>
          </Pressable>
        </ScrollView>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <BillHeader title={isGbp ? "Pay a UK bank account" : "Pay a euro bank account"} />
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingRight: spacing.lg + 8, paddingBottom: 140 }} keyboardShouldPersistTaps="handled">
          <TestModeBanner />
          <View style={bs.card} testID="uk-quote">
            {quote ? (
              <>
                <QuoteRow label="You send" value={money(quote.source.amount, quote.source.currency)} />
                <QuoteRow label="Recipient gets" value={money(quote.destination.amount, quote.destination.currency)} strong />
                <QuoteRow label="All-in rate" value={`1 ${quote.destination.currency} = ${quote.rates.all_in_source_per_dest.toLocaleString()} ${quote.source.currency}`} />
                <QuoteRow label="Paid by" value={`${quote.destination.receive_via} · ${isGbp ? "~10 min" : "~1 working day"}`} />
              </>
            ) : <ActivityIndicator color={colors.brand} />}
          </View>

          <Text style={bs.section}>What is it for?</Text>
          <View style={{ flexDirection: "row", gap: 8, flexWrap: "wrap" }}>
            {PURPOSES.map((x) => <Chip key={x} testID={`uk-purpose-${x.split(" ")[0].toLowerCase()}`} label={x} active={x === purpose} onPress={() => setPurpose(x)} />)}
          </View>

          <Text style={bs.section}>Recipient</Text>
          {input("name", "Full name or organisation", { autoCapitalize: "words" })}
          {input("email", "Recipient email", { autoCapitalize: "none", keyboardType: "email-address" })}
          {input("phone", "Recipient phone (optional)", { keyboardType: "phone-pad" })}

          <Text style={bs.section}>Bank details</Text>
          {input("bank_name", "Bank name (e.g. Barclays)", { autoCapitalize: "words" })}
          {isGbp ? (
            <>
              {input("account_number", "Account number (8 digits)", { keyboardType: "number-pad", maxLength: 8 })}
              {input("sort_code", "Sort code (e.g. 20-00-00)", { keyboardType: "number-pad", maxLength: 8 })}
              {input("swift_code", "SWIFT / BIC (optional)", { autoCapitalize: "characters", maxLength: 11 })}
            </>
          ) : (
            <>
              {input("account_number", "IBAN", { autoCapitalize: "characters" })}
              {input("swift_code", "SWIFT / BIC", { autoCapitalize: "characters", maxLength: 11 })}
            </>
          )}

          <Text style={bs.section}>Recipient address</Text>
          {!isGbp && (
            <View style={{ flexDirection: "row", gap: 8, flexWrap: "wrap", marginBottom: spacing.sm }}>
              {EU_COUNTRIES.map(([c, n]) => <Chip key={c} testID={`uk-country-${c}`} label={n} active={c === country} onPress={() => setCountry(c)} />)}
            </View>
          )}
          {input("line1", "Street address", { autoCapitalize: "words" })}
          {input("city", "Town / city", { autoCapitalize: "words" })}
          {input("postal_code", isGbp ? "Postcode" : "Postal code", { autoCapitalize: "characters" })}

          {err && <Text style={bs.err} testID="uk-error">{err}</Text>}
          <Pressable testID="uk-submit" onPress={submit} disabled={busy || !quote} style={[bs.cta, (missing || !quote) ? { opacity: 0.6 } : null]}>
            {busy ? <ActivityIndicator color="#0F0B08" /> : <Text style={bs.ctaText}>Send {quote ? money(quote.destination.amount, quote.destination.currency) : ""}</Text>}
          </Pressable>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
