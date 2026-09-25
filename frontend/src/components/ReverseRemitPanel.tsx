/**
 * ReverseRemitPanel — Africa → UK/EU corridor UI.
 *
 * Sits inside `/remit` under the "Send to UK/EU" direction toggle. Renders a
 * simplified quote card because reverse settlement isn't live yet — we only
 * show a *live rate quote* powered by Kotani onramp + FX cache, and channel
 * users into the waitlist so we can measure demand.
 *
 * Auth-optional: works logged-out too (landing embed uses this same shape).
 */
import { useEffect, useMemo, useState } from "react";
import {
  View, Text, TextInput, StyleSheet, Pressable, ScrollView, ActivityIndicator,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { colors, spacing, radius } from "@/src/lib/theme";

type SourceCorridor = {
  code: string;
  country: string;
  currency: string;
  flag: string;
  fund_via: string;
  eta: string;
  use_cases: string[];
  min_amount: number;
  max_amount: number;
};

type DestFiat = {
  code: string;
  currency: string;
  symbol: string;
  country: string;
  flag: string;
  receive_via: string;
  eta: string;
};

type ReverseQuote = {
  quote_id: string;
  status: string;
  waitlist_cta: boolean;
  source: { country: string; country_code: string; currency: string; flag: string; amount: number; fund_via: string };
  bridge: { chain: string; token: string; amount: number };
  destination: {
    country: string; currency: string; flag: string; symbol: string;
    receive_via: string; amount: number; amount_gross: number;
  };
  fees: {
    kotani_fee_fiat: number; kotani_fee_usd: number;
    vaulted_fee_usd: number; vaulted_fee_dest: number; total_fee_usd: number;
  };
  rates: { source_per_usdc: number; all_in_source_per_dest: number; usd_per_dest: number };
  kotani: { rate_id: string | null; mode: "live" | "mock" | "estimated" };
  eta: string;
};

const AMOUNT_DEFAULTS: Record<string, string> = {
  NG: "100000",   // ~£46
  KE: "10000",    // ~£54
  GH: "1000",     // ~£53
  ZA: "2000",     // ~£84
};

export default function ReverseRemitPanel({
  onJoinWaitlist,
  initialSource,
  userEmail,
}: {
  onJoinWaitlist?: (params: { corridor: string; email: string }) => void;
  initialSource?: string;
  userEmail?: string | null;
}) {
  const [sources, setSources] = useState<SourceCorridor[]>([]);
  const [destinations, setDestinations] = useState<DestFiat[]>([]);
  const [src, setSrc] = useState<string>(initialSource || "NG");
  const [dst, setDst] = useState<string>("GBP");
  const [amount, setAmount] = useState<string>(AMOUNT_DEFAULTS[initialSource || "NG"] || "100000");
  const [quote, setQuote] = useState<ReverseQuote | null>(null);
  const [loading, setLoading] = useState(false);
  const [quoteErr, setQuoteErr] = useState<string | null>(null);

  // Waitlist state
  const [email, setEmail] = useState<string>(userEmail || "");
  const [joining, setJoining] = useState(false);
  const [joined, setJoined] = useState(false);
  const [joinErr, setJoinErr] = useState<string | null>(null);

  // Fetch catalog once
  useEffect(() => {
    api<{ sources: SourceCorridor[]; destinations: DestFiat[] }>("/remit/reverse/corridors")
      .then((d) => { setSources(d.sources); setDestinations(d.destinations); })
      .catch(() => {});
  }, []);

  // Reset amount to sane default when source changes
  useEffect(() => {
    if (AMOUNT_DEFAULTS[src]) setAmount(AMOUNT_DEFAULTS[src]);
  }, [src]);

  const currentSource = useMemo(() => sources.find((s) => s.code === src), [sources, src]);

  // Live re-quote (debounced 500ms)
  useEffect(() => {
    const amt = parseFloat(amount);
    if (!amt || amt <= 0 || !src || !dst) { setQuote(null); return; }
    setLoading(true);
    setQuoteErr(null);
    const handle = setTimeout(async () => {
      try {
        const q = await api<ReverseQuote>("/remit/reverse/quote", {
          method: "POST",
          body: { source_country: src, source_amount: amt, destination_currency: dst },
        });
        setQuote(q);
      } catch (e: any) {
        setQuote(null);
        setQuoteErr(e?.message || "Quote failed");
      } finally {
        setLoading(false);
      }
    }, 500);
    return () => clearTimeout(handle);
  }, [amount, src, dst]);

  const handleJoinWaitlist = async () => {
    setJoinErr(null);
    const trimmed = email.trim();
    if (!trimmed || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) {
      setJoinErr("Enter a valid email");
      return;
    }
    setJoining(true);
    try {
      await api("/waitlist/join", {
        method: "POST",
        body: { email: trimmed, corridor: src, direction: "inbound", source: "app-reverse-remit" },
      });
      setJoined(true);
      onJoinWaitlist?.({ corridor: src, email: trimmed });
    } catch (e: any) {
      setJoinErr(e?.message || "Could not join — try again shortly.");
    } finally {
      setJoining(false);
    }
  };

  const destSymbol = quote?.destination.symbol || (destinations.find(d => d.code === dst)?.symbol) || "£";

  return (
    <View>
      {/* Info banner — sets expectation up front */}
      <View style={s.infoBanner}>
        <Ionicons name="information-circle" size={16} color={colors.brand} />
        <Text style={s.infoBannerText}>
          Sending from Africa to the UK/EU launches in Phase 2. Get a live rate quote today and reserve your spot.
        </Text>
      </View>

      {/* Source corridor picker */}
      <Text style={s.label}>You send from</Text>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ gap: spacing.sm, paddingVertical: 4 }}
        style={{ marginBottom: spacing.md }}
      >
        {sources.map((c) => (
          <Pressable
            key={c.code}
            testID={`reverse-src-${c.code}`}
            onPress={() => setSrc(c.code)}
            style={[s.corridorChip, src === c.code && s.corridorChipActive]}
          >
            <Text style={s.corridorFlag}>{c.flag}</Text>
            <View>
              <Text style={[s.corridorCountry, src === c.code && { color: colors.brand }]}>{c.country}</Text>
              <Text style={s.corridorCcy}>{c.currency} · {c.eta}</Text>
            </View>
          </Pressable>
        ))}
      </ScrollView>

      {/* Amount */}
      <Text style={s.label}>Amount ({currentSource?.currency})</Text>
      <View style={s.amountCard}>
        <TextInput
          testID="reverse-amount"
          value={amount}
          onChangeText={(v) => setAmount(v.replace(/[^0-9.]/g, ""))}
          keyboardType="decimal-pad"
          placeholder="0"
          placeholderTextColor={colors.onSurfaceTertiary}
          style={s.amountInput}
        />
        <Text style={s.amountCcy}>{currentSource?.currency || "—"}</Text>
      </View>
      {currentSource && (
        <Text style={s.helperText}>
          Min {currentSource.min_amount.toLocaleString()} · Max {currentSource.max_amount.toLocaleString()} {currentSource.currency}
        </Text>
      )}

      {/* Destination fiat picker */}
      <Text style={s.label}>Recipient receives</Text>
      <View style={s.destRow}>
        {destinations.map((d) => (
          <Pressable
            key={d.code}
            testID={`reverse-dst-${d.code}`}
            onPress={() => setDst(d.code)}
            style={[s.destPill, dst === d.code && s.destPillActive]}
          >
            <Text style={s.destFlag}>{d.flag}</Text>
            <Text style={[s.destPillText, dst === d.code && { color: "#0F0B08" }]}>{d.code}</Text>
          </Pressable>
        ))}
      </View>

      {/* Quote card */}
      <View style={s.quoteCard} testID="reverse-quote-card">
        {loading ? (
          <View style={{ paddingVertical: spacing.xl, alignItems: "center" }}>
            <ActivityIndicator color={colors.brand} />
            <Text style={s.quoteLoadingText}>Fetching live rate…</Text>
          </View>
        ) : quoteErr ? (
          <Text style={s.errorInline}>{quoteErr}</Text>
        ) : quote ? (
          <>
            <View style={s.quoteRowHero}>
              <Text style={s.quoteMuted}>Recipient gets</Text>
              <View style={{ flexDirection: "row", alignItems: "baseline", gap: 6 }}>
                <Text style={s.quoteBig}>{destSymbol}{quote.destination.amount.toLocaleString(undefined, { maximumFractionDigits: 2 })}</Text>
                <Text style={s.quoteCcy}>{quote.destination.currency}</Text>
              </View>
              <Text style={s.quoteVia}>{quote.destination.flag} {quote.destination.receive_via}</Text>
              {quote.kotani.mode !== "live" && (
                <View style={s.estBadge}>
                  <Text style={s.estBadgeText}>
                    {quote.kotani.mode === "estimated"
                      ? "Estimated · Kotani onramp enabling"
                      : "Sandbox estimate"}
                  </Text>
                </View>
              )}
            </View>
            <View style={s.divider} />
            <View style={s.quoteRow}>
              <Text style={s.quoteMuted}>All-in rate</Text>
              <Text style={s.quoteVal}>
                1 {quote.destination.currency} = {quote.rates.all_in_source_per_dest.toLocaleString(undefined, { maximumFractionDigits: 2 })} {quote.source.currency}
              </Text>
            </View>
            <View style={s.quoteRow}>
              <Text style={s.quoteMuted}>Stablecoin bridge</Text>
              <Text style={s.quoteVal}>{quote.bridge.amount.toLocaleString(undefined, { maximumFractionDigits: 4 })} {quote.bridge.token} · {quote.bridge.chain}</Text>
            </View>
            <View style={s.quoteRow}>
              <Text style={s.quoteMuted}>On-ramp fee</Text>
              <Text style={s.quoteVal}>{quote.fees.kotani_fee_fiat.toLocaleString(undefined, { maximumFractionDigits: 0 })} {quote.source.currency}</Text>
            </View>
            <View style={s.quoteRow}>
              <Text style={s.quoteMuted}>Vaulted fee</Text>
              <Text style={s.quoteVal}>{destSymbol}{quote.fees.vaulted_fee_dest.toFixed(2)}</Text>
            </View>
            <View style={s.quoteRow}>
              <Text style={s.quoteMuted}>Delivery ETA</Text>
              <Text style={s.quoteVal}>{quote.eta} + PSP</Text>
            </View>
          </>
        ) : (
          <Text style={s.quoteMuted}>Enter an amount to see a live rate</Text>
        )}
      </View>

      {/* Use cases pills */}
      {currentSource && (
        <View style={s.useCasesRow}>
          {currentSource.use_cases.map((uc) => (
            <View key={uc} style={s.useCasePill}>
              <Ionicons name="checkmark-circle" size={12} color={colors.brand} />
              <Text style={s.useCasePillText}>{uc}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Waitlist CTA */}
      <View style={s.waitlistCard}>
        {joined ? (
          <View style={{ alignItems: "center", paddingVertical: spacing.md }}>
            <Ionicons name="checkmark-circle" size={32} color={colors.success} />
            <Text style={s.waitlistDoneTitle}>You&apos;re on the list.</Text>
            <Text style={s.waitlistDoneSub}>We&apos;ll email you the moment {currentSource?.country} → UK/EU goes live.</Text>
          </View>
        ) : (
          <>
            <Text style={s.waitlistTitle}>Reserve your spot</Text>
            <Text style={s.waitlistSub}>
              Get first access when {currentSource?.country || "your corridor"} → UK/EU launches. Early joiners get 50% off Vaulted fees for 3 months.
            </Text>
            <View style={s.waitlistInputRow}>
              <TextInput
                testID="reverse-waitlist-email"
                value={email}
                onChangeText={setEmail}
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="email-address"
                placeholder="you@example.com"
                placeholderTextColor={colors.onSurfaceTertiary}
                style={s.waitlistInput}
              />
              <Pressable
                testID="reverse-waitlist-join"
                onPress={handleJoinWaitlist}
                disabled={joining}
                style={({ pressed }) => [s.waitlistBtn, (pressed || joining) && { opacity: 0.7 }]}
              >
                {joining ? <ActivityIndicator color="#0F0B08" /> : <Text style={s.waitlistBtnText}>Join</Text>}
              </Pressable>
            </View>
            {joinErr && <Text style={s.errorInline}>{joinErr}</Text>}
          </>
        )}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  label: { fontSize: 13, color: colors.onSurfaceSecondary, marginBottom: spacing.xs, marginTop: spacing.md, fontWeight: "500" },
  helperText: { fontSize: 11, color: colors.onSurfaceTertiary, lineHeight: 15, marginTop: 4 },
  errorInline: { color: colors.error, fontSize: 12, marginTop: spacing.sm },

  infoBanner: {
    flexDirection: "row", alignItems: "flex-start", gap: 8,
    padding: spacing.md, borderRadius: radius.md,
    backgroundColor: "rgba(201,163,91,0.08)",
    borderWidth: 1, borderColor: "rgba(201,163,91,0.25)",
    marginBottom: spacing.md,
  },
  infoBannerText: { color: colors.onSurface, fontSize: 12, lineHeight: 16, flex: 1 },

  corridorChip: {
    flexDirection: "row", alignItems: "center", gap: 10,
    paddingHorizontal: 14, paddingVertical: 10,
    borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    backgroundColor: colors.surface, minWidth: 160,
  },
  corridorChipActive: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  corridorFlag: { fontSize: 24 },
  corridorCountry: { fontSize: 14, fontWeight: "700", color: colors.onSurface },
  corridorCcy: { fontSize: 11, color: colors.onSurfaceTertiary, marginTop: 2 },

  amountCard: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, backgroundColor: colors.surface,
  },
  amountInput: { flex: 1, fontSize: 26, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.5 },
  amountCcy: { fontSize: 14, fontWeight: "700", color: colors.onSurfaceSecondary, letterSpacing: 0.5 },

  destRow: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.md },
  destPill: {
    flexDirection: "row", alignItems: "center", gap: 8,
    paddingHorizontal: 16, paddingVertical: 12,
    borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    backgroundColor: colors.surface, flex: 1, justifyContent: "center",
  },
  destPillActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  destFlag: { fontSize: 20 },
  destPillText: { fontSize: 14, fontWeight: "700", color: colors.onSurface },

  quoteCard: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg,
    padding: spacing.lg, backgroundColor: colors.surfaceSecondary, marginTop: spacing.sm,
  },
  quoteRowHero: { paddingBottom: spacing.md, gap: 4 },
  quoteBig: { fontSize: 32, fontWeight: "800", color: colors.onSurface, letterSpacing: -0.8 },
  quoteCcy: { fontSize: 15, color: colors.onSurfaceSecondary, fontWeight: "700" },
  quoteVia: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 6 },
  quoteRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 6 },
  quoteMuted: { fontSize: 12, color: colors.onSurfaceSecondary },
  quoteVal: { fontSize: 12, color: colors.onSurface, fontWeight: "600" },
  quoteLoadingText: { color: colors.onSurfaceTertiary, marginTop: 8, fontSize: 12 },
  divider: { height: 1, backgroundColor: colors.divider, marginVertical: spacing.sm },

  estBadge: {
    alignSelf: "flex-start", marginTop: 8,
    paddingHorizontal: 8, paddingVertical: 3,
    borderRadius: radius.pill,
    backgroundColor: "rgba(201,163,91,0.12)",
    borderWidth: 1, borderColor: "rgba(201,163,91,0.35)",
  },
  estBadgeText: { fontSize: 10, color: colors.brandDeep, fontWeight: "700", letterSpacing: 0.4 },

  useCasesRow: {
    flexDirection: "row", flexWrap: "wrap", gap: 6,
    marginTop: spacing.md, marginBottom: spacing.sm,
  },
  useCasePill: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    borderWidth: 1, borderColor: "rgba(201,163,91,0.35)",
  },
  useCasePillText: { fontSize: 11, color: colors.onSurface, fontWeight: "600" },

  waitlistCard: {
    marginTop: spacing.lg,
    padding: spacing.lg,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceInverse,
    borderWidth: 1, borderColor: "rgba(201,163,91,0.4)",
  },
  waitlistTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurfaceInverse, marginBottom: 6 },
  waitlistSub: { fontSize: 12, color: colors.brandSecondary, lineHeight: 16, marginBottom: spacing.md },
  waitlistInputRow: { flexDirection: "row", gap: 8 },
  waitlistInput: {
    flex: 1,
    borderWidth: 1, borderColor: "rgba(255,255,255,0.15)",
    borderRadius: radius.pill,
    paddingHorizontal: spacing.lg, paddingVertical: 12,
    fontSize: 14, color: colors.onSurfaceInverse,
    backgroundColor: "rgba(255,255,255,0.05)",
  },
  waitlistBtn: {
    backgroundColor: colors.brand, borderRadius: radius.pill,
    paddingHorizontal: 20, paddingVertical: 12, justifyContent: "center",
  },
  waitlistBtnText: { color: "#0F0B08", fontSize: 14, fontWeight: "800" },
  waitlistDoneTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurfaceInverse, marginTop: 8 },
  waitlistDoneSub: { fontSize: 12, color: colors.brandSecondary, textAlign: "center", marginTop: 4, lineHeight: 16 },
});
