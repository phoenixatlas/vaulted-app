import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator, Linking, Share } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { colors, spacing, radius } from "@/src/lib/theme";

type ExportResp = { address: string; private_key: string; network: string; warning: string };

export default function ExportKey() {
  const router = useRouter();
  const [confirmed, setConfirmed] = useState(false);
  const [data, setData] = useState<ExportResp | null>(null);
  const [loading, setLoading] = useState(false);
  const [revealed, setRevealed] = useState(false);

  const reveal = async () => {
    setLoading(true);
    try {
      const r = await api<ExportResp>("/wallet/eth/export");
      setData(r);
      setRevealed(true);
    } catch (e) {
      console.log(e);
    } finally {
      setLoading(false);
    }
  };

  const copyPk = async () => {
    if (data?.private_key) await Share.share({ message: data.private_key });
  };

  return (
    <SafeAreaView style={s.root} edges={["top", "bottom"]}>
      <View style={s.header}>
        <Pressable testID="export-back" onPress={() => router.back()}><Ionicons name="chevron-back" size={26} color={colors.onSurface} /></Pressable>
        <Text style={s.title}>Export private key</Text>
        <View style={{ width: 26 }} />
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.xl }}>
        <View style={s.warnCard}>
          <Ionicons name="warning" size={28} color={colors.warning} />
          <Text style={s.warnTitle}>Your keys, your coins.</Text>
          <Text style={s.warnText}>
            Anyone who has this private key controls your wallet permanently. Never share it,
            screenshot it on a synced device, or paste it into a website. Save it somewhere
            offline (paper, password manager).
          </Text>
        </View>

        {!revealed ? (
          <>
            <Pressable
              testID="export-confirm-check"
              onPress={() => setConfirmed(!confirmed)}
              style={s.checkRow}
            >
              <View style={[s.checkbox, confirmed && s.checkboxOn]}>
                {confirmed && <Ionicons name="checkmark" size={14} color="#fff" />}
              </View>
              <Text style={s.checkText}>I understand and accept full responsibility.</Text>
            </Pressable>

            <Pressable
              testID="export-reveal"
              onPress={reveal}
              disabled={!confirmed || loading}
              style={({ pressed }) => [s.cta, (!confirmed || loading) && { opacity: 0.4 }, pressed && { opacity: 0.85 }]}
            >
              {loading ? <ActivityIndicator color="#fff" /> : <Text style={s.ctaText}>Reveal private key</Text>}
            </Pressable>
          </>
        ) : (
          <View style={s.keyCard}>
            <Text style={s.label}>Address</Text>
            <Text testID="export-address" style={s.mono} selectable>{data?.address}</Text>

            <Text style={[s.label, { marginTop: spacing.md }]}>Network</Text>
            <Text style={s.subtle}>{data?.network}</Text>

            <Text style={[s.label, { marginTop: spacing.md }]}>Private key</Text>
            <Text testID="export-pk" style={[s.mono, { color: colors.error }]} selectable>{data?.private_key}</Text>

            <Pressable testID="export-share" onPress={copyPk} style={s.shareBtn}>
              <Ionicons name="share-outline" size={16} color={colors.brand} />
              <Text style={s.shareText}>Share / copy</Text>
            </Pressable>

            <Pressable
              testID="export-explorer"
              onPress={() => Linking.openURL(`https://sepolia.etherscan.io/address/${data?.address}`)}
              style={s.shareBtn}
            >
              <Ionicons name="open-outline" size={16} color={colors.brand} />
              <Text style={s.shareText}>View on Sepolia Etherscan</Text>
            </Pressable>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.xl, paddingTop: spacing.sm, paddingBottom: spacing.md },
  title: { fontSize: 17, fontWeight: "700", color: colors.onSurface },
  warnCard: { padding: spacing.lg, borderRadius: radius.lg, backgroundColor: "#FFF6E0", gap: spacing.sm, alignItems: "flex-start" },
  warnTitle: { fontSize: 18, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.3 },
  warnText: { fontSize: 13, color: colors.onSurfaceSecondary, lineHeight: 19 },
  checkRow: { flexDirection: "row", alignItems: "center", gap: 10, marginTop: spacing.xl },
  checkbox: { width: 22, height: 22, borderRadius: 4, borderWidth: 2, borderColor: colors.borderStrong, alignItems: "center", justifyContent: "center" },
  checkboxOn: { backgroundColor: colors.brand, borderColor: colors.brand },
  checkText: { color: colors.onSurface, fontSize: 14, flex: 1 },
  cta: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: 16, alignItems: "center", marginTop: spacing.xl },
  ctaText: { color: "#fff", fontSize: 16, fontWeight: "600" },
  keyCard: { marginTop: spacing.lg, padding: spacing.lg, borderRadius: radius.lg, backgroundColor: colors.surfaceSecondary },
  label: { fontSize: 11, fontWeight: "600", color: colors.onSurfaceTertiary, textTransform: "uppercase", letterSpacing: 0.5 },
  subtle: { color: colors.onSurface, fontSize: 13, marginTop: 4 },
  mono: { color: colors.onSurface, fontSize: 12, marginTop: 4, fontFamily: "monospace" },
  shareBtn: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: spacing.md, alignSelf: "flex-start", padding: 6 },
  shareText: { color: colors.brand, fontSize: 13, fontWeight: "600" },
});
