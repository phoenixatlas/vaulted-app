import { useEffect, useMemo, useState } from "react";
import {
  View, Text, StyleSheet, Pressable, Share, Platform, ActivityIndicator, ScrollView,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter, useLocalSearchParams } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import QRCode from "react-native-qrcode-svg";
import * as Clipboard from "expo-clipboard";
import { api } from "@/src/lib/api";
import { useI18n } from "@/src/lib/i18n";
import { colors, spacing, radius, ASSET_ICON_COLORS } from "@/src/lib/theme";

type Asset = "ETH" | "USDC" | "BTC" | "SOL" | "XLM" | "XRP";

type WalletInfo = {
  address: string;
  network: string;
  faucet?: string | null;
  explorer?: string;
};

const CHAIN_LABEL: Record<Asset, string> = {
  ETH: "Ethereum",
  USDC: "USD Coin",
  BTC: "Bitcoin",
  SOL: "Solana",
  XLM: "Stellar",
  XRP: "XRP Ledger",
};
const CHAIN_PATH: Record<Asset, string> = {
  ETH: "/wallet/eth/info",
  USDC: "/wallet/usdc/info",
  BTC: "/wallet/btc/info",
  SOL: "/wallet/sol/info",
  XLM: "/wallet/xlm/info",
  XRP: "/wallet/xrp/info",
};
const CHAIN_BADGE: Record<Asset, string> = {
  ETH: "ERC-20",
  USDC: "ERC-20",
  BTC: "P2PKH",
  SOL: "ED25519",
  XLM: "ED25519",
  XRP: "SECP256K1",
};

export default function Receive() {
  const { t } = useI18n();
  const router = useRouter();
  const { asset: initial } = useLocalSearchParams<{ asset?: Asset }>();
  const [asset, setAsset] = useState<Asset>((initial as Asset) || "ETH");
  const [infoByAsset, setInfoByAsset] = useState<Partial<Record<Asset, WalletInfo>>>({});
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [errByAsset, setErrByAsset] = useState<Partial<Record<Asset, string>>>({});

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (infoByAsset[asset] || errByAsset[asset]) return;
      setLoading(true);
      try {
        const r = await api<WalletInfo & { explorer?: string }>(CHAIN_PATH[asset]);
        if (!cancelled) setInfoByAsset((m) => ({ ...m, [asset]: r }));
      } catch (e: any) {
        if (!cancelled) {
          let msg = e?.message ?? "Couldn't load address";
          if (typeof msg === "string" && msg.includes("mnemonic missing")) {
            msg = "This account was created before multi-chain onboarding. Re-import or migrate the wallet to enable this chain.";
          }
          setErrByAsset((m) => ({ ...m, [asset]: msg }));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [asset, infoByAsset, errByAsset]);

  const info = infoByAsset[asset];
  const assetErr = errByAsset[asset];
  const accent = useMemo(() => ASSET_ICON_COLORS[asset] ?? colors.brand, [asset]);

  const onCopy = async () => {
    if (!info?.address) return;
    await Clipboard.setStringAsync(info.address);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  const onShare = async () => {
    if (info?.address) await Share.share({ message: info.address });
  };

  return (
    <SafeAreaView style={s.root} edges={["top", "bottom"]}>
      <View style={s.header}>
        <Pressable testID="receive-back" onPress={() => router.back()}>
          <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
        </Pressable>
        <Text style={s.title}>{t("receive_crypto")}</Text>
        <View style={{ width: 26 }} />
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.chipRow} contentContainerStyle={{ gap: spacing.sm, paddingHorizontal: spacing.xl }}>
        {(["ETH", "USDC", "BTC", "SOL", "XLM", "XRP"] as Asset[]).map((a) => (
          <Pressable
            key={a}
            testID={`receive-asset-${a}`}
            onPress={() => setAsset(a)}
            style={[s.chip, asset === a && { backgroundColor: colors.brand, borderColor: colors.brand }]}
          >
            <View style={[s.chipDot, { backgroundColor: ASSET_ICON_COLORS[a] }]} />
            <Text style={[s.chipText, asset === a && { color: "#0F0B08" }]}>{a}</Text>
          </Pressable>
        ))}
      </ScrollView>

      <ScrollView contentContainerStyle={s.body} keyboardShouldPersistTaps="handled">
        <View style={[s.chainBadge, { borderColor: accent }]}>
          <View style={[s.dot, { backgroundColor: accent }]} />
          <Text style={s.chainLabel}>{CHAIN_LABEL[asset]} · {info?.network ?? "…"}</Text>
          <Text style={s.chainKind}>{CHAIN_BADGE[asset]}</Text>
        </View>

        <View style={s.qrCard}>
          {assetErr ? (
            <View style={s.qrPlaceholder}>
              <Ionicons name="alert-circle-outline" size={36} color={colors.brandDeep} />
              <Text style={s.qrErrText}>{assetErr}</Text>
            </View>
          ) : loading || !info?.address ? (
            <View style={s.qrPlaceholder}><ActivityIndicator color={colors.brand} /></View>
          ) : (
            <QRCode
              value={info.address}
              size={208}
              color="#0F0B08"
              backgroundColor="transparent"
            />
          )}
        </View>

        <Text style={s.label}>{t("your_address")}</Text>
        <View style={s.addrBox}>
          <Text testID="receive-address" style={s.addrText} selectable>
            {assetErr ? "—" : info?.address ?? "…"}
          </Text>
        </View>

        <View style={s.actionRow}>
          <Pressable testID="receive-copy" onPress={onCopy} style={s.actionBtn}>
            <Ionicons name={copied ? "checkmark" : "copy-outline"} size={18} color={colors.brandDeep} />
            <Text style={s.actionText}>{copied ? t("copied") : t("copy")}</Text>
          </Pressable>
          <Pressable testID="receive-share" onPress={onShare} style={s.actionBtn}>
            <Ionicons name="share-outline" size={18} color={colors.brandDeep} />
            <Text style={s.actionText}>{t("share")}</Text>
          </Pressable>
        </View>

        {info?.faucet ? (
          <Pressable
            testID="receive-faucet"
            onPress={() => Share.share({ message: info.faucet ?? "" })}
            style={s.faucetCard}
          >
            <Ionicons name="water-outline" size={16} color={colors.brand} />
            <View style={{ flex: 1 }}>
              <Text style={s.faucetTitle}>{t("get_testnet_funds")}</Text>
              <Text style={s.faucetLink} numberOfLines={1}>{info.faucet}</Text>
            </View>
            <Ionicons name="open-outline" size={14} color={colors.brand} />
          </Pressable>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.xl, paddingTop: spacing.sm, paddingBottom: spacing.md },
  title: { fontSize: 17, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.3 },
  chipRow: { paddingBottom: spacing.lg, flexGrow: 0 },
  chip: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill, backgroundColor: colors.brandTertiary, borderWidth: 1, borderColor: "rgba(201,163,91,0.40)" },
  chipDot: { width: 7, height: 7, borderRadius: 4 },
  chipText: { fontSize: 12, fontWeight: "700", color: colors.brandDeep, letterSpacing: 0.5 },
  body: { padding: spacing.xl, alignItems: "center", gap: spacing.md, paddingBottom: spacing.xxl + spacing.xl },
  chainBadge: { flexDirection: "row", alignItems: "center", gap: 8, borderWidth: 1, paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill, backgroundColor: "rgba(201,163,91,0.10)" },
  dot: { width: 8, height: 8, borderRadius: 4 },
  chainLabel: { fontSize: 12, fontWeight: "700", color: colors.onSurface, letterSpacing: 0.2 },
  chainKind: { fontSize: 10, fontWeight: "700", color: colors.brandDeep, backgroundColor: "rgba(201,163,91,0.18)", paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, marginLeft: 4 },
  qrCard: { width: 240, height: 240, borderRadius: radius.lg, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", marginTop: spacing.sm, borderWidth: 1, borderColor: "rgba(201,163,91,0.30)" },
  qrPlaceholder: { width: 208, height: 208, alignItems: "center", justifyContent: "center", paddingHorizontal: 12, gap: 10 },
  qrErrText: { color: colors.brandDeep, fontSize: 12, textAlign: "center", lineHeight: 16, fontWeight: "500" },
  label: { fontSize: 11, color: colors.brandDeep, marginTop: spacing.lg, fontWeight: "700", letterSpacing: 0.5, textTransform: "uppercase" },
  addrBox: { backgroundColor: colors.surfaceSecondary, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, maxWidth: "100%" },
  addrText: { color: colors.onSurface, fontSize: 13, fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace", textAlign: "center" },
  actionRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm },
  actionBtn: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill, backgroundColor: colors.brandTertiary, borderWidth: 1, borderColor: "rgba(201,163,91,0.40)" },
  actionText: { color: colors.brandDeep, fontWeight: "700", fontSize: 13 },
  faucetCard: { flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.md, backgroundColor: colors.surfaceInverse, borderRadius: radius.md, marginTop: spacing.lg, width: "100%", borderWidth: 1, borderColor: "rgba(201,163,91,0.35)" },
  faucetTitle: { color: colors.onSurfaceInverse, fontWeight: "700", fontSize: 13 },
  faucetLink: { color: "rgba(245,233,201,0.7)", fontSize: 11, marginTop: 2 },
});
