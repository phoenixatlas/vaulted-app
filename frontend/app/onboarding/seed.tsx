import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { colors, spacing, radius } from "@/src/lib/theme";

export default function SeedOnboarding() {
  const router = useRouter();
  const [words, setWords] = useState<string[]>([]);
  const [address, setAddress] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [revealed, setRevealed] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api<{ address: string; mnemonic: string }>("/wallet/eth/mnemonic")
      .then((d) => {
        setAddress(d.address);
        setWords(d.mnemonic.split(/\s+/));
      })
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }, []);

  const next = () => {
    router.push({ pathname: "/onboarding/verify", params: { words: words.join(" ") } });
  };

  return (
    <SafeAreaView style={s.root} edges={["top", "bottom"]}>
      <ScrollView contentContainerStyle={{ padding: spacing.xl, paddingBottom: spacing.xxxl }}>
        <View style={s.iconWrap}>
          <Ionicons name="key" size={28} color={colors.brand} />
        </View>
        <Text style={s.title}>Your recovery phrase</Text>
        <Text style={s.subtitle}>
          These 12 words are the only way to restore your wallet if you lose this device. Write them down on paper and store somewhere safe. Never share them.
        </Text>

        <View style={s.warnRow}>
          <Ionicons name="warning" size={16} color={colors.warning} />
          <Text style={s.warnText}>Anyone with these words owns your wallet.</Text>
        </View>

        {loading ? (
          <ActivityIndicator color={colors.brand} style={{ marginTop: 40 }} />
        ) : err ? (
          <Text style={s.error}>{err}</Text>
        ) : (
          <>
            {!revealed ? (
              <Pressable testID="seed-reveal" onPress={() => setRevealed(true)} style={s.revealHidden}>
                <Ionicons name="eye" size={22} color={colors.brand} />
                <Text style={s.revealText}>Tap to reveal</Text>
              </Pressable>
            ) : (
              <View testID="seed-words-grid" style={s.grid}>
                {words.map((w, i) => (
                  <View key={i} style={s.wordCell}>
                    <Text style={s.wordNum}>{i + 1}</Text>
                    <Text style={s.wordText} selectable>{w}</Text>
                  </View>
                ))}
              </View>
            )}

            <Text style={s.addrLabel}>Wallet address</Text>
            <Text style={s.addrText} selectable>{address}</Text>

            <Pressable
              testID="seed-continue"
              onPress={next}
              disabled={!revealed}
              style={({ pressed }) => [s.cta, !revealed && { opacity: 0.4 }, pressed && { opacity: 0.85 }]}
            >
              <Text style={s.ctaText}>I've saved them — verify</Text>
            </Pressable>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  iconWrap: { width: 52, height: 52, borderRadius: 26, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center", marginBottom: spacing.md },
  title: { fontSize: 26, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.5 },
  subtitle: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 20, marginTop: spacing.sm, marginBottom: spacing.lg },
  warnRow: { flexDirection: "row", alignItems: "center", gap: 8, padding: spacing.md, backgroundColor: "#FFF6E0", borderRadius: radius.md, marginBottom: spacing.lg },
  warnText: { color: colors.onSurfaceSecondary, fontSize: 12, flex: 1 },
  revealHidden: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, paddingVertical: 60, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg },
  revealText: { color: colors.brand, fontSize: 15, fontWeight: "600" },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 8, backgroundColor: colors.surfaceSecondary, padding: spacing.md, borderRadius: radius.lg },
  wordCell: { flexBasis: "31%", flexGrow: 1, flexDirection: "row", alignItems: "center", backgroundColor: colors.surface, paddingHorizontal: 10, paddingVertical: 10, borderRadius: radius.md, gap: 6 },
  wordNum: { color: colors.onSurfaceTertiary, fontSize: 11, fontWeight: "700", minWidth: 14 },
  wordText: { color: colors.onSurface, fontSize: 13, fontWeight: "600" },
  addrLabel: { fontSize: 11, fontWeight: "600", color: colors.onSurfaceTertiary, textTransform: "uppercase", letterSpacing: 0.5, marginTop: spacing.xl },
  addrText: { color: colors.onSurface, fontSize: 12, fontFamily: "monospace", marginTop: 4 },
  cta: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: 16, alignItems: "center", marginTop: spacing.xl },
  ctaText: { color: "#0F0B08", fontSize: 16, fontWeight: "600" },
  error: { color: colors.error, marginTop: spacing.lg },
});
