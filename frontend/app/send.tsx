import { useEffect, useState } from "react";
import {
  View, Text, TextInput, StyleSheet, Pressable, ScrollView, ActivityIndicator,
  KeyboardAvoidingView, Platform, Linking,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { useAuth } from "@/src/lib/auth";
import { useI18n } from "@/src/lib/i18n";
import { colors, spacing, radius, ASSET_ICON_COLORS } from "@/src/lib/theme";
import { authenticate, getCapabilities } from "@/src/lib/biometric";

type Asset = {
  id: string; symbol: string; name: string; amount: number; fiat_value: number;
  on_chain?: boolean; network?: string | null; wallet_address?: string | null;
};

type EvmChain = {
  chain: string; display_name: string; short: string; network: string;
  chain_id: number; usdc_balance: number; native_balance: number;
  faucet_native?: string | null; faucet_usdc?: string | null;
  wallet_address?: string;
};

export default function SendCrypto() {
  const { t } = useI18n();
  const { user } = useAuth();
  const router = useRouter();
  const [assets, setAssets] = useState<Asset[]>([]);
  const [sel, setSel] = useState<string>("ETH");
  const [amount, setAmount] = useState("");
  const [addr, setAddr] = useState("");
  const [memo, setMemo] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [gasGwei, setGasGwei] = useState<number | null>(null);
  // EVM L2 chain picker (Sepolia | Polygon | Base | Arbitrum) — only shown when USDC selected.
  const [evmChains, setEvmChains] = useState<EvmChain[]>([]);
  const [usdcChain, setUsdcChain] = useState<string>("sepolia");

  useEffect(() => {
    api<{ assets: Asset[] }>("/wallet/assets").then((d) => setAssets(d.assets));
    api<{ gas_price_gwei: number }>("/wallet/eth/info").then((d) => setGasGwei(d.gas_price_gwei)).catch(() => {});
    api<{ chains: EvmChain[] }>("/wallet/evm/chains").then((d) => setEvmChains(d.chains)).catch(() => {});
  }, []);

  const selected = assets.find((a) => a.symbol === sel);
  const isEth = sel === "ETH";
  const isUsdc = sel === "USDC";
  const isBtc = sel === "BTC";
  const isSol = sel === "SOL";
  const isXlm = sel === "XLM";
  const isXrp = sel === "XRP";
  const isOnChain = isEth || isUsdc || isBtc || isSol || isXlm || isXrp;
  const sendDisabled = !isOnChain;
  const isPro = !!user?.is_pro;
  const baseServiceFee = 0.10;
  const serviceFee = isPro ? baseServiceFee * 0.5 : baseServiceFee;
  const selectedEvmChain = evmChains.find((c) => c.chain === usdcChain);
  const networkLabel = isEth
    ? "Sepolia"
    : isUsdc
      ? (selectedEvmChain?.short ?? "Sepolia")
      : isBtc ? "Testnet3" : isSol ? "Devnet" : isXlm ? "Testnet" : isXrp ? "Testnet" : "";
  const addrPlaceholder = isEth || isUsdc ? "0x..." : isBtc ? "tb1q... / m... / n..." : isSol ? "Base58 address" : isXlm ? "G... (56 chars)" : isXrp ? "r... (25-35 chars)" : "address";

  const submit = async () => {
    setErr(null);
    if (sendDisabled) {
      setErr(`${sel} sends are coming soon. Receive works now.`);
      return;
    }
    const amt = parseFloat(amount);
    if (!amt || amt <= 0) { setErr("Enter a valid amount"); return; }
    if (!addr.trim()) { setErr("Enter recipient address"); return; }

    // If the user has biometric lock enabled, require a scan before signing.
    if (user?.biometric_enabled) {
      const caps = await getCapabilities();
      if (caps.available) {
        const auth = await authenticate({ reason: `Confirm send of ${amt} ${sel}` });
        if (!auth.success) { setErr("Biometric authentication failed"); return; }
      }
    }

    setSubmitting(true);
    try {
      let tx: any;
      if (isEth) {
        tx = await api("/wallet/eth/send", {
          method: "POST",
          body: { to_address: addr.trim(), amount_eth: amt },
        });
      } else if (isUsdc) {
        // Route to the appropriate EVM chain based on the L2 picker
        tx = await api("/wallet/evm/usdc/send", {
          method: "POST",
          body: { chain: usdcChain, to_address: addr.trim(), amount_usdc: amt },
        });
      } else if (isBtc) {
        tx = await api("/wallet/btc/send", {
          method: "POST",
          body: { to_address: addr.trim(), amount: amt },
        });
      } else if (isSol) {
        tx = await api("/wallet/sol/send", {
          method: "POST",
          body: { to_address: addr.trim(), amount: amt },
        });
      } else if (isXlm) {
        tx = await api("/wallet/xlm/send", {
          method: "POST",
          body: { to_address: addr.trim(), amount: amt, memo: memo.trim() || null },
        });
      } else if (isXrp) {
        tx = await api("/wallet/xrp/send", {
          method: "POST",
          body: { to_address: addr.trim(), amount: amt, memo: memo.trim() || null },
        });
      } else {
        tx = await api("/wallet/send", {
          method: "POST",
          body: { asset: sel, amount: amt, to_address: addr.trim(), memo: memo.trim() || null },
        });
      }
      // Multi-sig: backend returns approval_required:true instead of a tx
      if (tx && tx.approval_required) {
        router.replace({ pathname: "/approvals" });
        return;
      }
      router.replace({ pathname: "/receipt", params: { ...(tx as any) } });
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
                {a.on_chain && <Ionicons name="globe-outline" size={12} color={sel === a.symbol ? colors.brand : colors.onSurfaceTertiary} />}
              </Pressable>
            ))}
          </ScrollView>
          {selected && (
            <View style={s.balRow}>
              <Text style={s.bal}>Available: {selected.amount.toLocaleString(undefined, {maximumFractionDigits: 6})} {selected.symbol}</Text>
              {isOnChain && (
                <View style={s.netPill}><Ionicons name="globe" size={10} color={colors.brand} /><Text style={s.netText}>{networkLabel}</Text></View>
              )}
            </View>
          )}

          {isUsdc && evmChains.length > 0 && (
            <View style={{ marginBottom: spacing.md }}>
              <Text style={s.label}>Network</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm, paddingVertical: 4 }}>
                {evmChains.map((c) => {
                  const active = usdcChain === c.chain;
                  const isL1 = c.chain === "sepolia";
                  return (
                    <Pressable
                      key={c.chain}
                      testID={`usdc-chain-${c.chain}`}
                      onPress={() => setUsdcChain(c.chain)}
                      style={[s.l2Chip, active && s.l2ChipActive]}
                    >
                      <View style={{ flex: 1 }}>
                        <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                          <Text style={[s.l2ChipTitle, active && { color: colors.brand }]}>{c.short}</Text>
                          {!isL1 && (
                            <View style={s.cheapPill}>
                              <Text style={s.cheapPillText}>~$0.01 gas</Text>
                            </View>
                          )}
                        </View>
                        <Text style={s.l2ChipMuted}>{c.usdc_balance.toLocaleString(undefined, { maximumFractionDigits: 4 })} USDC</Text>
                      </View>
                    </Pressable>
                  );
                })}
              </ScrollView>
            </View>
          )}

          <Text style={s.label}>{t("amount")}</Text>
          <TextInput testID="send-amount" value={amount} onChangeText={setAmount} keyboardType="decimal-pad" placeholder="0.00" placeholderTextColor={colors.onSurfaceTertiary} style={s.input} />

          <Text style={s.label}>{t("recipient")}</Text>
          <TextInput testID="send-address" value={addr} onChangeText={setAddr} autoCapitalize="none" placeholder={addrPlaceholder} placeholderTextColor={colors.onSurfaceTertiary} style={s.input} />

          {!isOnChain && (
            <>
              <Text style={s.label}>{t("memo")}</Text>
              <TextInput testID="send-memo" value={memo} onChangeText={setMemo} placeholder="optional" placeholderTextColor={colors.onSurfaceTertiary} style={s.input} />
            </>
          )}
          {(isXlm || isXrp) && (
            <>
              <Text style={s.label}>Memo (optional)</Text>
              <TextInput testID="send-memo" value={memo} onChangeText={setMemo} placeholder={isXlm ? "Text memo (max 28 chars)" : "Memo (attached to the tx)"} placeholderTextColor={colors.onSurfaceTertiary} style={s.input} />
            </>
          )}

          <View style={s.feeCard} testID="fee-summary">
            <View style={s.feeRow}>
              <Text style={s.feeLabel}>
                Network fee{isEth && gasGwei ? ` (~${gasGwei.toFixed(2)} gwei)` : isBtc ? " (miner fee)" : isSol ? " (~0.000005 SOL)" : isXlm ? " (~100 stroops)" : isXrp ? " (~10 drops)" : isUsdc && usdcChain !== "sepolia" ? ` (${selectedEvmChain?.short ?? "L2"})` : ""}
              </Text>
              <Text style={s.feeValue}>
                {isEth ? "~0.00002 ETH" : isBtc ? "auto" : isSol ? "~5000 lamports" : isXlm ? "~0.00001 XLM" : isXrp ? "~0.00001 XRP" : isUsdc ? (usdcChain === "sepolia" ? "~$2 (L1)" : "~$0.01") : "$0.00"}
              </Text>
            </View>
            <View style={s.feeRow}>
              <Text style={s.feeLabel}>Vaulted service fee</Text>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                {isPro && <Text style={s.strike}>${baseServiceFee.toFixed(2)}</Text>}
                <Text style={s.feeValue}>${serviceFee.toFixed(2)}</Text>
                {isPro && <View style={s.proPill}><Text style={s.proPillText}>PRO -50%</Text></View>}
              </View>
            </View>
          </View>

          {sendDisabled && (
            <View style={s.warnCard} testID="send-disabled-warn">
              <Ionicons name="time-outline" size={16} color={colors.brandDeep} />
              <Text style={s.warnText}>{sel} send is coming soon. Receive works now — tap an asset on the wallet to grab your address.</Text>
            </View>
          )}

          {err && <Text testID="send-error" style={s.error}>{err}</Text>}

          <Pressable
            testID="send-confirm"
            disabled={submitting || sendDisabled}
            onPress={submit}
            style={({ pressed }) => [s.cta, (pressed || sendDisabled) && { opacity: 0.55 }]}
          >
            {submitting
              ? <ActivityIndicator color="#0F0B08" />
              : <Text style={s.ctaText}>
                  {sendDisabled
                    ? `${sel} send coming soon`
                    : `${t("confirm")} ${isEth ? "on Sepolia" : isUsdc ? `USDC on ${selectedEvmChain?.short ?? "Sepolia"}` : isBtc ? "on BTC Testnet" : isSol ? "on SOL Devnet" : isXlm ? "on Stellar Testnet" : isXrp ? "on XRPL Testnet" : ""}`.trim()}
                </Text>}
          </Pressable>

          {isEth && (
            <Pressable testID="faucet-link" onPress={() => Linking.openURL("https://sepoliafaucet.com/")} style={s.faucet}>
              <Ionicons name="water-outline" size={16} color={colors.brand} />
              <Text style={s.faucetText}>Need test ETH? Open Sepolia faucet</Text>
            </Pressable>
          )}
          {isBtc && (
            <Pressable testID="faucet-link-btc" onPress={() => Linking.openURL("https://coinfaucet.eu/en/btc-testnet/")} style={s.faucet}>
              <Ionicons name="water-outline" size={16} color={colors.brand} />
              <Text style={s.faucetText}>Need test BTC? Open testnet faucet</Text>
            </Pressable>
          )}
          {isSol && (
            <Pressable testID="faucet-link-sol" onPress={() => Linking.openURL("https://faucet.solana.com/")} style={s.faucet}>
              <Ionicons name="water-outline" size={16} color={colors.brand} />
              <Text style={s.faucetText}>Need devnet SOL? Open Solana faucet</Text>
            </Pressable>
          )}
          {isXlm && selected && (
            <Pressable testID="faucet-link-xlm" onPress={() => Linking.openURL(`https://friendbot.stellar.org/?addr=${encodeURIComponent(selected.wallet_address || "")}`)} style={s.faucet}>
              <Ionicons name="water-outline" size={16} color={colors.brand} />
              <Text style={s.faucetText}>Need test XLM? Tap here (Friendbot funds you 10,000 XLM)</Text>
            </Pressable>
          )}
          {isXrp && selected && (
            <Pressable testID="faucet-link-xrp" onPress={() => Linking.openURL(`https://xrpl.org/xrp-testnet-faucet.html`)} style={s.faucet}>
              <Ionicons name="water-outline" size={16} color={colors.brand} />
              <Text style={s.faucetText}>Need test XRP? Open XRPL testnet faucet (100 XRP)</Text>
            </Pressable>
          )}
          {isUsdc && selectedEvmChain?.faucet_usdc && (
            <Pressable testID="faucet-link-usdc" onPress={() => Linking.openURL(selectedEvmChain.faucet_usdc!)} style={s.faucet}>
              <Ionicons name="water-outline" size={16} color={colors.brand} />
              <Text style={s.faucetText}>Need test USDC on {selectedEvmChain.short}? Open the Circle faucet</Text>
            </Pressable>
          )}
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
  balRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm },
  bal: { color: colors.onSurfaceTertiary, fontSize: 12 },
  netPill: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.brandTertiary, paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.pill },
  netText: { fontSize: 10, color: colors.brand, fontWeight: "700" },
  chip: { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 14, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, flexShrink: 0, height: 36 },
  chipActive: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  chipDot: { width: 10, height: 10, borderRadius: 5 },
  chipText: { color: colors.onSurface, fontWeight: "600", fontSize: 13 },
  feeCard: { marginTop: spacing.lg, padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, gap: 6 },
  feeRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  feeLabel: { fontSize: 12, color: colors.onSurfaceSecondary },
  feeValue: { fontSize: 12, color: colors.onSurface, fontWeight: "600" },
  strike: { fontSize: 11, color: colors.onSurfaceTertiary, textDecorationLine: "line-through" },
  proPill: { backgroundColor: colors.brand, paddingHorizontal: 6, paddingVertical: 2, borderRadius: radius.pill },
  proPillText: { color: "#fff", fontSize: 9, fontWeight: "800", letterSpacing: 0.5 },
  cta: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: 16, alignItems: "center", marginTop: spacing.xl },
  ctaText: { color: "#0F0B08", fontSize: 16, fontWeight: "600" },
  faucet: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, marginTop: spacing.lg, padding: spacing.sm },
  faucetText: { color: colors.brand, fontSize: 13, fontWeight: "500" },
  warnCard: { flexDirection: "row", gap: 8, alignItems: "flex-start", padding: spacing.md, backgroundColor: colors.brandTertiary, borderRadius: radius.md, borderWidth: 1, borderColor: "rgba(201,163,91,0.40)", marginTop: spacing.lg },
  warnText: { color: colors.brandDeep, fontSize: 12, lineHeight: 16, fontWeight: "500", flex: 1 },
  error: { color: colors.error, marginTop: spacing.md, fontSize: 14 },
  l2Chip: { minWidth: 140, paddingHorizontal: spacing.md, paddingVertical: 10, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  l2ChipActive: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  l2ChipTitle: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  l2ChipMuted: { fontSize: 11, color: colors.onSurfaceTertiary, marginTop: 2 },
  cheapPill: { backgroundColor: colors.success, paddingHorizontal: 6, paddingVertical: 2, borderRadius: radius.pill },
  cheapPillText: { color: "#fff", fontSize: 8, fontWeight: "800", letterSpacing: 0.4 },
});
