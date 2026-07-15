import { useEffect, useMemo, useState } from "react";
import {
  View, Text, TextInput, StyleSheet, Pressable, ScrollView, ActivityIndicator,
  KeyboardAvoidingView, Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { useAuth } from "@/src/lib/auth";
import { colors, spacing, radius } from "@/src/lib/theme";
import { authenticate, getCapabilities } from "@/src/lib/biometric";
import { startRemitFundCheckout, syncStripeSession } from "@/src/lib/stripe";

type Corridor = {
  code: string;
  country: string;
  currency: string;
  flag: string;
  receive_via: string;
  eta: string;
};

type Quote = {
  quote_id: string;
  source: { currency: string; amount: number; amount_usd: number; amount_gbp?: number };
  destination: {
    code: string; country: string; currency: string; flag: string;
    receive_via: string; eta: string; amount: number;
  };
  chain: { chain: string; crypto_amount: number; crypto_price_usd: number; chain_fee_usd: number } | null;
  fees: { vaulted_service_usd: number; chain_fee_usd: number; total_fee_usd: number };
  fx_rate: number;
  fx_fetched_at: string;
  free_tier: {
    limit_per_month: number;
    used_this_month: number;
    remaining_this_month: number | null;
    paywall_required: boolean;
    is_pro: boolean;
  };
  kyc?: {
    allowed: boolean;
    current_tier: string;
    current_tier_label: string;
    limit: { per_send_gbp: number; monthly_gbp: number };
    usage: { this_month_gbp: number; monthly_remaining_gbp: number; monthly_used_pct: number };
    reason: "over_per_send" | "over_monthly" | null;
    upgrade?: {
      target_tier: string;
      target_tier_label: string;
      target_per_send_gbp: number;
      target_monthly_gbp: number;
      requires: string;
      why: string;
    } | null;
  };
  sufficient_balance: boolean;
  reason_if_no_chain?: string | null;
};

const SOURCE_FIATS = ["GBP", "USD", "EUR"] as const;
type SourceFiat = typeof SOURCE_FIATS[number];

const FIAT_SYMBOL: Record<SourceFiat, string> = { GBP: "£", USD: "$", EUR: "€" };

type FundingMethod = "crypto" | "card" | "apple_pay" | "google_pay" | "bank";

type FundingOption = { id: FundingMethod; label: string; icon: keyof typeof Ionicons.glyphMap; sub: string };

// Always show all 5 options so both Apple Pay and Google Pay customers
// can pick their preferred rail regardless of the device the app is
// running on. Stripe Checkout automatically surfaces the correct wallet
// button (Apple Pay on Safari/iOS, Google Pay on Chrome/Android).
const FUNDING_OPTIONS: FundingOption[] = [
  { id: "crypto", label: "Crypto balance", icon: "wallet-outline", sub: "XLM · XRP · USDC" },
  { id: "card", label: "Card", icon: "card-outline", sub: "Visa · Mastercard · Amex" },
  { id: "apple_pay", label: "Apple Pay", icon: "logo-apple", sub: "Fastest on iPhone" },
  { id: "google_pay", label: "Google Pay", icon: "logo-google", sub: "Fastest on Android" },
  { id: "bank", label: "Bank transfer", icon: "business-outline", sub: "BACS · SEPA · ACH" },
];

export default function Remit() {
  const router = useRouter();
  const { user } = useAuth();
  const [corridors, setCorridors] = useState<Corridor[]>([]);
  const [dest, setDest] = useState<string>("KE");
  const [srcFiat, setSrcFiat] = useState<SourceFiat>("GBP");
  const [amount, setAmount] = useState("50");
  const [addr, setAddr] = useState("");
  const [recipientName, setRecipientName] = useState("");
  const [funding, setFunding] = useState<FundingMethod>("crypto");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [quoteLoading, setQuoteLoading] = useState(false);
  const [quoteErr, setQuoteErr] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Load corridor catalog once
  useEffect(() => {
    api<{ corridors: Corridor[] }>("/remit/corridors").then((d) => setCorridors(d.corridors)).catch(() => {});
  }, []);

  // Re-quote whenever amount/dest/srcFiat changes, debounced.
  useEffect(() => {
    const amt = parseFloat(amount);
    if (!amt || amt <= 0 || !dest) { setQuote(null); return; }
    setQuoteLoading(true);
    setQuoteErr(null);
    const handle = setTimeout(async () => {
      try {
        const q = await api<Quote>("/remit/quote", {
          method: "POST",
          body: { source_fiat: srcFiat, amount: amt, destination_code: dest },
        });
        setQuote(q);
      } catch (e: any) {
        setQuote(null);
        setQuoteErr(e?.message || "Quote failed");
      } finally {
        setQuoteLoading(false);
      }
    }, 400);
    return () => clearTimeout(handle);
  }, [amount, dest, srcFiat]);

  const selectedCorridor = useMemo(() => corridors.find((c) => c.code === dest), [corridors, dest]);
  const isPro = !!user?.is_pro;
  const paywall = quote?.free_tier?.paywall_required;
  const kycRequired = quote?.kyc && !quote.kyc.allowed;
  const isFiatFunding = funding !== "crypto";
  // For fiat funding, the "addr" field holds recipient bank/M-Pesa/IBAN
  // details as a free-form string. For crypto funding, it must be a
  // valid chain address matching the chain the router picked.
  const addrPlaceholder = isFiatFunding
    ? dest === "KE"
      ? "M-Pesa phone (e.g. +254 712 345 678)"
      : dest === "GB"
        ? "Sort code + account number, or IBAN"
        : "Account number, IBAN, or mobile-money phone"
    : quote?.chain?.chain === "XRP"
      ? "r... recipient XRP address"
      : quote?.chain?.chain === "XLM"
        ? "G... recipient Stellar address"
        : "recipient wallet address";
  const addrLabel = isFiatFunding ? "Recipient account or phone" : "Recipient wallet address";
  const addrHelperText = isFiatFunding
    ? `We'll settle to your recipient in ${selectedCorridor?.currency ?? "local currency"} via ${selectedCorridor?.receive_via ?? "our local partner"}. Payouts settle within ${selectedCorridor?.eta ?? "the standard corridor window"}.`
    : `Phase B: recipient receives ${quote?.chain?.chain ?? "crypto"} in their wallet. Direct-to-${selectedCorridor?.currency ?? "local currency"} settlement (via M-Pesa / bank / mobile money) launches with our partner integrations in Phase C.`;
  // Fiat funding bypasses the on-chain sufficient_balance check.
  const canSubmit = !!quote && (isFiatFunding || quote.sufficient_balance);

  const submit = async () => {
    setErr(null);
    if (!quote) { setErr("Waiting for a live quote — try again in a moment."); return; }
    if (!isFiatFunding && !quote.sufficient_balance) {
      setErr("Not enough crypto — top up XLM, XRP, or USDC on the Wallet tab, or switch to Card / Apple Pay / Google Pay / Bank transfer above.");
      return;
    }
    if (!addr.trim()) {
      setErr(isFiatFunding
        ? "Enter the recipient's account number, IBAN, or mobile-money phone."
        : "Enter the recipient's wallet address.");
      return;
    }
    if (isFiatFunding && !recipientName.trim()) {
      setErr("Recipient full name is required for bank / mobile-money payouts.");
      return;
    }
    if (paywall) { router.push("/vault-pro"); return; }
    if (kycRequired) { router.push({ pathname: "/kyc", params: { reason: "over_limit" } }); return; }

    if (user?.biometric_enabled) {
      const caps = await getCapabilities();
      if (caps.available) {
        const auth = await authenticate({ reason: `Send ${FIAT_SYMBOL[srcFiat]}${amount} to ${selectedCorridor?.country}` });
        if (!auth.success) { setErr("Biometric authentication failed"); return; }
      }
    }

    setSubmitting(true);
    try {
      if (isFiatFunding) {
        // Fiat rails path — Stripe Checkout with card / Apple Pay / Google Pay / bank transfer.
        const result = await startRemitFundCheckout({
          source_fiat: srcFiat,
          amount: parseFloat(amount),
          destination_code: dest,
          recipient_address: addr.trim(),
          recipient_name: recipientName.trim() || null,
          payment_method: funding as "card" | "apple_pay" | "google_pay" | "bank",
        });
        if (result.status === "success" && result.session_id) {
          // Sync the session so backend books the send + returns the tx
          const synced = await syncStripeSession(result.session_id);
          const applied: any = synced?.applied || {};
          if (applied?.kind === "remit_fund" && applied?.tx) {
            const tx = applied.tx;
            // Kotani M-Pesa off-ramp state — populated for KES payouts.
            // Passed to the receipt screen so the "M-Pesa receipt" row
            // and delivered/processing status can render correctly.
            const kotani = tx.kotani || applied.kotani || null;
            router.replace({
              pathname: "/receipt",
              params: {
                ...tx,
                remit_json: JSON.stringify(tx.remit || {}),
                kotani_json: kotani ? JSON.stringify(kotani) : "",
                kotani_reference_id: kotani?.reference_id || "",
                kotani_status: kotani?.status || "",
                mpesa_receipt: kotani?.mpesa_receipt || "",
                funding_method: "stripe",
              } as any,
            });
            return;
          }
          setErr("Payment confirmed but the send couldn't be booked. Please check Activity or contact support.");
        } else if (result.status === "cancel") {
          setErr("Payment cancelled — no charge was made.");
        } else if (result.status === "error") {
          setErr(result.error || "Payment failed. Please try a different method.");
        }
        return;
      }

      // Crypto rails path (existing)
      const tx = await api<any>("/remit/send", {
        method: "POST",
        body: {
          source_fiat: srcFiat,
          amount: parseFloat(amount),
          destination_code: dest,
          recipient_address: addr.trim(),
          recipient_name: recipientName.trim() || null,
        },
      });
      router.replace({ pathname: "/receipt", params: { ...(tx as any), remit_json: JSON.stringify(tx.remit || {}) } });
    } catch (e: any) {
      // 402 → paywall
      if (e?.status === 402 || (e?.message || "").includes("free_tier_exhausted")) {
        router.push("/vault-pro");
        return;
      }
      // 403 → KYC required (over limit) or corridor blocked
      if (e?.status === 403 || (e?.message || "").includes("kyc_required")) {
        router.push({ pathname: "/kyc", params: { reason: "over_limit" } });
        return;
      }
      setErr(e?.message || "Send failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={s.root} edges={["top", "bottom"]}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1 }}>
        <View style={s.header}>
          <Pressable testID="remit-back" onPress={() => router.back()}>
            <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
          </Pressable>
          <Text style={s.title}>Send Money</Text>
          <View style={{ width: 26 }} />
        </View>

        <ScrollView contentContainerStyle={{ padding: spacing.xl, paddingBottom: 120 }} keyboardShouldPersistTaps="handled">
          {/* Source fiat picker */}
          <Text style={s.label}>You send</Text>
          <View style={s.amountCard}>
            <TextInput
              testID="remit-amount"
              value={amount}
              onChangeText={(v) => setAmount(v.replace(/[^0-9.]/g, ""))}
              keyboardType="decimal-pad"
              placeholder="0"
              placeholderTextColor={colors.onSurfaceTertiary}
              style={s.amountInput}
            />
            <View style={s.fiatPickerRow}>
              {SOURCE_FIATS.map((f) => (
                <Pressable
                  key={f}
                  testID={`remit-src-${f}`}
                  onPress={() => setSrcFiat(f)}
                  style={[s.fiatPill, srcFiat === f && s.fiatPillActive]}
                >
                  <Text style={[s.fiatPillText, srcFiat === f && { color: "#0F0B08" }]}>{f}</Text>
                </Pressable>
              ))}
            </View>
          </View>

          {/* Destination corridor picker */}
          <Text style={s.label}>To</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm, paddingVertical: 4 }} style={{ marginBottom: spacing.lg }}>
            {corridors.map((c) => (
              <Pressable
                key={c.code}
                testID={`remit-dest-${c.code}`}
                onPress={() => setDest(c.code)}
                style={[s.corridorChip, dest === c.code && s.corridorChipActive]}
              >
                <Text style={s.corridorFlag}>{c.flag}</Text>
                <View>
                  <Text style={[s.corridorCountry, dest === c.code && { color: colors.brand }]}>{c.country}</Text>
                  <Text style={s.corridorCcy}>{c.currency} · {c.eta}</Text>
                </View>
              </Pressable>
            ))}
          </ScrollView>

          {/* Pay-with selector — crypto wallet OR fiat (card / Apple Pay / bank) */}
          <Text style={s.label}>Pay with</Text>
          <View style={s.fundingGrid}>
            {FUNDING_OPTIONS.map((opt) => {
              const active = funding === opt.id;
              return (
                <Pressable
                  key={opt.id}
                  testID={`remit-funding-${opt.id}`}
                  onPress={() => setFunding(opt.id)}
                  style={[s.fundingCard, active && s.fundingCardActive]}
                >
                  <Ionicons name={opt.icon} size={20} color={active ? colors.brand : colors.onSurfaceSecondary} />
                  <Text style={[s.fundingLabel, active && { color: colors.onSurface }]}>{opt.label}</Text>
                  <Text style={s.fundingSub}>{opt.sub}</Text>
                </Pressable>
              );
            })}
          </View>

          {/* Quote card — recipient gets */}
          <View style={s.quoteCard} testID="remit-quote-card">
            {quoteLoading ? (
              <View style={{ paddingVertical: spacing.xl, alignItems: "center" }}>
                <ActivityIndicator color={colors.brand} />
                <Text style={s.quoteLoadingText}>Getting live quote…</Text>
              </View>
            ) : quoteErr ? (
              <Text style={s.errorInline}>{quoteErr}</Text>
            ) : quote ? (
              <>
                <View style={s.quoteRowHero}>
                  <Text style={s.quoteMuted}>Recipient gets</Text>
                  <View style={{ flexDirection: "row", alignItems: "baseline", gap: 6 }}>
                    <Text style={s.quoteBig}>{quote.destination.amount.toLocaleString(undefined, { maximumFractionDigits: 2 })}</Text>
                    <Text style={s.quoteCcy}>{quote.destination.currency}</Text>
                  </View>
                  <Text style={s.quoteVia}>{quote.destination.flag} {quote.destination.receive_via} · {quote.destination.eta}</Text>
                </View>
                <View style={s.divider} />
                <View style={s.quoteRow}>
                  <Text style={s.quoteMuted}>Exchange rate</Text>
                  <Text style={s.quoteVal}>1 {quote.source.currency} = {quote.fx_rate.toLocaleString(undefined, { maximumFractionDigits: 4 })} {quote.destination.currency}</Text>
                </View>
                {!isFiatFunding && (
                  <View style={s.quoteRow}>
                    <Text style={s.quoteMuted}>Chain</Text>
                    <Text style={s.quoteVal}>
                      {quote.chain
                        ? `${quote.chain.chain} · ${quote.chain.crypto_amount.toLocaleString(undefined, { maximumFractionDigits: 6 })} ${quote.chain.chain}`
                        : "—"}
                    </Text>
                  </View>
                )}
                <View style={s.quoteRow}>
                  <Text style={s.quoteMuted}>Vaulted service fee{isPro && " (Pro -50%)"}</Text>
                  <Text style={s.quoteVal}>${quote.fees.vaulted_service_usd.toFixed(2)}</Text>
                </View>
                {!isFiatFunding && (
                  <View style={s.quoteRow}>
                    <Text style={s.quoteMuted}>Network fee</Text>
                    <Text style={s.quoteVal}>{quote.fees.chain_fee_usd === 0 ? "≈ free" : `$${quote.fees.chain_fee_usd.toFixed(4)}`}</Text>
                  </View>
                )}
                {!isFiatFunding && !quote.sufficient_balance && (
                  <View style={s.warnBox}>
                    <Ionicons name="alert-circle-outline" size={16} color={colors.brandDeep} />
                    <Text style={s.warnText}>
                      {quote.reason_if_no_chain} You can also pay with Card, Apple Pay, or Bank transfer above — no crypto needed.
                    </Text>
                  </View>
                )}
                {isFiatFunding && (
                  <View style={s.fundingHintBox}>
                    <Ionicons name="information-circle-outline" size={16} color={colors.brand} />
                    <Text style={s.fundingHintText}>
                      {`You'll pay ${FIAT_SYMBOL[srcFiat]}${amount} securely via Stripe. Recipient receives ${quote.destination.amount.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${quote.destination.currency}.`}
                    </Text>
                  </View>
                )}
              </>
            ) : (
              <Text style={s.quoteMuted}>Enter an amount to see a live quote</Text>
            )}
          </View>

          {/* Free tier banner */}
          {quote && !isPro && quote.free_tier.remaining_this_month !== null && (
            <View style={[s.freeTierBanner, paywall && s.freeTierBannerPaywall]} testID="remit-free-tier">
              <Ionicons name={paywall ? "lock-closed" : "gift-outline"} size={16} color={paywall ? colors.error : colors.brand} />
              <Text style={[s.freeTierText, paywall && { color: colors.error }]}>
                {paywall
                  ? "You've used all 3 free cross-border sends this month. Upgrade to Vault Pro for unlimited."
                  : `${quote.free_tier.remaining_this_month} of ${quote.free_tier.limit_per_month} free cross-border sends left this month.`}
              </Text>
              {paywall && (
                <Pressable testID="remit-upgrade-cta" onPress={() => router.push("/vault-pro")} style={s.upgradeBtn}>
                  <Text style={s.upgradeBtnText}>Upgrade</Text>
                </Pressable>
              )}
            </View>
          )}
          {quote && isPro && (
            <View style={s.proBanner} testID="remit-pro-banner">
              <Ionicons name="shield-checkmark" size={16} color={colors.brand} />
              <Text style={s.proBannerText}>Vault Pro · Unlimited cross-border sends + 50% off service fees</Text>
            </View>
          )}

          {quote?.kyc && (
            <View
              style={[s.kycBanner, kycRequired && s.kycBannerRequired, quote.kyc.current_tier === "kyc_lite" && s.kycBannerVerified]}
              testID="remit-kyc-banner"
            >
              <Ionicons
                name={quote.kyc.current_tier === "kyc_lite" ? "shield-checkmark" : kycRequired ? "lock-closed" : "person-circle-outline"}
                size={16}
                color={quote.kyc.current_tier === "kyc_lite" ? colors.success : kycRequired ? colors.error : colors.brand}
              />
              <View style={{ flex: 1 }}>
                {kycRequired ? (
                  <>
                    <Text style={[s.kycBannerTitle, { color: colors.error }]}>Verification needed to send this amount</Text>
                    <Text style={s.kycBannerSub}>
                      Your {quote.kyc.current_tier_label} tier caps sends at £{quote.kyc.limit.per_send_gbp.toLocaleString()}. Verify to unlock £{quote.kyc.upgrade?.target_per_send_gbp?.toLocaleString() ?? "1,000"} per send.
                    </Text>
                  </>
                ) : quote.kyc.current_tier === "kyc_lite" ? (
                  <Text style={s.kycBannerSub}>
                    <Text style={{ fontWeight: "700", color: colors.onSurface }}>{quote.kyc.current_tier_label}</Text> · £{quote.kyc.usage.monthly_remaining_gbp.toLocaleString()} of £{quote.kyc.limit.monthly_gbp.toLocaleString()} remaining this month
                  </Text>
                ) : (
                  <Text style={s.kycBannerSub}>
                    {quote.kyc.current_tier_label} tier · up to £{quote.kyc.limit.per_send_gbp.toLocaleString()}/send. Verify to unlock higher limits.
                  </Text>
                )}
              </View>
              {(kycRequired || quote.kyc.current_tier === "unverified") && (
                <Pressable
                  testID="remit-kyc-cta"
                  onPress={() => router.push({ pathname: "/kyc", params: kycRequired ? { reason: "over_limit" } : {} })}
                  style={s.kycCta}
                >
                  <Text style={s.kycCtaText}>Verify</Text>
                </Pressable>
              )}
            </View>
          )}

          {/* Recipient details — differs for fiat vs crypto rails */}
          {isFiatFunding ? (
            <>
              <Text style={s.label}>Recipient full name <Text style={s.required}>*</Text></Text>
              <TextInput
                testID="remit-name"
                value={recipientName}
                onChangeText={setRecipientName}
                placeholder="e.g. Njeri Mwangi"
                placeholderTextColor={colors.onSurfaceTertiary}
                style={s.input}
                autoCapitalize="words"
              />
              <Text style={s.helperText}>Match this to the name on their bank / M-Pesa account exactly.</Text>

              <Text style={s.label}>{addrLabel} <Text style={s.required}>*</Text></Text>
              <TextInput
                testID="remit-addr"
                value={addr}
                onChangeText={setAddr}
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType={dest === "KE" || dest === "NG" ? "phone-pad" : "default"}
                placeholder={addrPlaceholder}
                placeholderTextColor={colors.onSurfaceTertiary}
                style={s.input}
              />
              <Text style={s.helperText}>{addrHelperText}</Text>
            </>
          ) : (
            <>
              <Text style={s.label}>{addrLabel}</Text>
              <TextInput
                testID="remit-addr"
                value={addr}
                onChangeText={setAddr}
                autoCapitalize="none"
                placeholder={addrPlaceholder}
                placeholderTextColor={colors.onSurfaceTertiary}
                style={s.input}
              />
              <Text style={s.helperText}>{addrHelperText}</Text>

              <Text style={s.label}>Recipient name (optional)</Text>
              <TextInput
                testID="remit-name"
                value={recipientName}
                onChangeText={setRecipientName}
                placeholder="e.g. Mama Njeri"
                placeholderTextColor={colors.onSurfaceTertiary}
                style={s.input}
              />
            </>
          )}

          {err && <Text testID="remit-error" style={s.errorInline}>{err}</Text>}

          <Pressable
            testID="remit-confirm"
            disabled={submitting || !canSubmit}
            onPress={submit}
            style={({ pressed }) => [s.cta, (pressed || !canSubmit) && { opacity: 0.6 }]}
          >
            {submitting ? (
              <ActivityIndicator color="#0F0B08" />
            ) : (
              <Text style={s.ctaText}>
                {paywall
                  ? "Upgrade to send"
                  : canSubmit
                    ? isFiatFunding
                      ? `Pay ${FIAT_SYMBOL[srcFiat]}${amount} & send to ${selectedCorridor?.country ?? ""}`
                      : `Send ${FIAT_SYMBOL[srcFiat]}${amount} to ${selectedCorridor?.country ?? ""}`
                    : "Top up to send"}
              </Text>
            )}
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
  label: { fontSize: 13, color: colors.onSurfaceSecondary, marginBottom: spacing.xs, marginTop: spacing.md, fontWeight: "500" },
  input: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.lg, paddingVertical: 14, fontSize: 15, color: colors.onSurface, backgroundColor: colors.surface },

  amountCard: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, backgroundColor: colors.surface },
  amountInput: { flex: 1, fontSize: 28, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.5 },
  fiatPickerRow: { flexDirection: "row", gap: 6 },
  fiatPill: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border },
  fiatPillActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  fiatPillText: { fontSize: 12, fontWeight: "700", color: colors.onSurface, letterSpacing: 0.4 },

  corridorChip: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, minWidth: 160 },
  corridorChipActive: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  corridorFlag: { fontSize: 24 },
  corridorCountry: { fontSize: 14, fontWeight: "700", color: colors.onSurface },
  corridorCcy: { fontSize: 11, color: colors.onSurfaceTertiary, marginTop: 2 },

  quoteCard: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, padding: spacing.lg, backgroundColor: colors.surfaceSecondary, marginTop: spacing.sm },
  quoteRowHero: { paddingBottom: spacing.md, gap: 4 },
  quoteBig: { fontSize: 32, fontWeight: "800", color: colors.onSurface, letterSpacing: -0.8 },
  quoteCcy: { fontSize: 15, color: colors.onSurfaceSecondary, fontWeight: "700" },
  quoteVia: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 6 },
  quoteRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 6 },
  quoteMuted: { fontSize: 12, color: colors.onSurfaceSecondary },
  quoteVal: { fontSize: 12, color: colors.onSurface, fontWeight: "600" },
  quoteLoadingText: { color: colors.onSurfaceTertiary, marginTop: 8, fontSize: 12 },
  divider: { height: 1, backgroundColor: colors.divider, marginVertical: spacing.sm },

  warnBox: { flexDirection: "row", alignItems: "flex-start", gap: 8, marginTop: spacing.md, padding: spacing.sm, backgroundColor: "rgba(201,163,91,0.10)", borderRadius: radius.md, borderWidth: 1, borderColor: "rgba(201,163,91,0.30)" },
  warnText: { color: colors.brandDeep, fontSize: 12, lineHeight: 16, flex: 1 },

  fundingGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginBottom: spacing.md },
  fundingCard: {
    flexBasis: "48%", flexGrow: 1,
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    padding: spacing.md, backgroundColor: colors.surface, gap: 4,
  },
  fundingCardActive: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  fundingLabel: { fontSize: 13, fontWeight: "700", color: colors.onSurfaceSecondary, marginTop: 4 },
  fundingSub: { fontSize: 11, color: colors.onSurfaceTertiary },
  fundingHintBox: { flexDirection: "row", alignItems: "flex-start", gap: 8, marginTop: spacing.md, padding: spacing.sm, backgroundColor: "rgba(201,163,91,0.08)", borderRadius: radius.md, borderWidth: 1, borderColor: "rgba(201,163,91,0.25)" },
  fundingHintText: { color: colors.onSurface, fontSize: 12, lineHeight: 16, flex: 1 },

  freeTierBanner: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: spacing.md, padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.brandTertiary, borderWidth: 1, borderColor: "rgba(201,163,91,0.30)" },
  freeTierBannerPaywall: { backgroundColor: "rgba(200,60,60,0.10)", borderColor: "rgba(200,60,60,0.40)" },
  freeTierText: { flex: 1, fontSize: 12, color: colors.onSurface, lineHeight: 16 },
  upgradeBtn: { backgroundColor: colors.brand, paddingHorizontal: 12, paddingVertical: 6, borderRadius: radius.pill },
  upgradeBtnText: { color: "#0F0B08", fontSize: 12, fontWeight: "800" },

  proBanner: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: spacing.md, padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceInverse, borderWidth: 1, borderColor: "rgba(201,163,91,0.40)" },
  proBannerText: { flex: 1, fontSize: 12, color: colors.onSurfaceInverse, lineHeight: 16, fontWeight: "500" },
  kycBanner: { flexDirection: "row", alignItems: "center", gap: 10, marginTop: spacing.md, padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  kycBannerRequired: { backgroundColor: "rgba(200,60,60,0.08)", borderColor: "rgba(200,60,60,0.40)" },
  kycBannerVerified: { backgroundColor: "rgba(60,180,90,0.06)", borderColor: "rgba(60,180,90,0.30)" },
  kycBannerTitle: { fontSize: 12, fontWeight: "700", marginBottom: 2 },
  kycBannerSub: { fontSize: 11, color: colors.onSurfaceSecondary, lineHeight: 15 },
  kycCta: { backgroundColor: colors.brand, paddingHorizontal: 12, paddingVertical: 6, borderRadius: radius.pill },
  kycCtaText: { color: "#0F0B08", fontSize: 12, fontWeight: "800" },

  helperText: { fontSize: 11, color: colors.onSurfaceTertiary, lineHeight: 15, marginTop: 4 },
  required: { color: "#E0735F" },
  errorInline: { color: colors.error, fontSize: 13, marginTop: spacing.sm },

  cta: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: 16, alignItems: "center", marginTop: spacing.xl },
  ctaText: { color: "#0F0B08", fontSize: 16, fontWeight: "700" },
});
