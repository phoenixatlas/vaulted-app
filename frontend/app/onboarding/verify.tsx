import { useEffect, useMemo, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { useAuth } from "@/src/lib/auth";
import { colors, spacing, radius } from "@/src/lib/theme";

const CHECK_POSITIONS = [3, 6, 9, 11]; // verify these 4 indices (0-based)

function shuffle<T>(arr: T[]): T[] {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

export default function SeedVerify() {
  const { words: wordsParam } = useLocalSearchParams<{ words: string }>();
  const router = useRouter();
  const { refresh } = useAuth();
  const words = useMemo(() => (wordsParam ? wordsParam.split(/\s+/) : []), [wordsParam]);
  const [picks, setPicks] = useState<Record<number, string | null>>({});
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const options = useMemo(() => {
    if (words.length !== 12) return {} as Record<number, string[]>;
    const out: Record<number, string[]> = {};
    for (const idx of CHECK_POSITIONS) {
      const distractors = shuffle(words.filter((_, i) => i !== idx)).slice(0, 3);
      out[idx] = shuffle([words[idx], ...distractors]);
    }
    return out;
  }, [words]);

  const allCorrect =
    CHECK_POSITIONS.every((idx) => picks[idx] === words[idx]) &&
    CHECK_POSITIONS.length === Object.values(picks).filter(Boolean).length;

  const submit = async () => {
    setErr(null);
    if (!allCorrect) {
      setErr("Some answers don't match. Please try again.");
      return;
    }
    setSubmitting(true);
    try {
      await api("/auth/onboarding-complete", { method: "POST" });
      await refresh();
      router.replace("/(tabs)/wallet");
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={s.root} edges={["top", "bottom"]}>
      <ScrollView contentContainerStyle={{ padding: spacing.xl, paddingBottom: spacing.xxxl }}>
        <Pressable testID="verify-back" onPress={() => router.back()} style={{ marginBottom: spacing.md, alignSelf: "flex-start" }}>
          <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
        </Pressable>
        <Text style={s.title}>Verify your phrase</Text>
        <Text style={s.subtitle}>Confirm a few words to make sure you saved them correctly.</Text>

        {CHECK_POSITIONS.map((idx) => (
          <View key={idx} style={s.q}>
            <Text style={s.qLabel}>Word #{idx + 1}</Text>
            <View style={s.optionsRow}>
              {(options[idx] ?? []).map((w) => {
                const selected = picks[idx] === w;
                return (
                  <Pressable
                    key={w}
                    testID={`verify-pick-${idx}-${w}`}
                    onPress={() => setPicks({ ...picks, [idx]: w })}
                    style={[s.optionChip, selected && s.optionChipActive]}
                  >
                    <Text style={[s.optionText, selected && { color: "#fff" }]}>{w}</Text>
                  </Pressable>
                );
              })}
            </View>
          </View>
        ))}

        {err && <Text testID="verify-error" style={s.error}>{err}</Text>}

        <Pressable
          testID="verify-submit"
          disabled={submitting}
          onPress={submit}
          style={({ pressed }) => [s.cta, !allCorrect && { opacity: 0.6 }, pressed && { opacity: 0.85 }]}
        >
          {submitting ? <ActivityIndicator color="#fff" /> : <Text style={s.ctaText}>Finish setup</Text>}
        </Pressable>

        <Pressable testID="verify-back-to-seed" onPress={() => router.back()} style={s.linkBtn}>
          <Text style={s.linkText}>I need to see my words again</Text>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  title: { fontSize: 26, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.5 },
  subtitle: { fontSize: 14, color: colors.onSurfaceSecondary, marginTop: spacing.sm, marginBottom: spacing.lg },
  q: { marginBottom: spacing.lg },
  qLabel: { fontSize: 13, fontWeight: "600", color: colors.onSurfaceSecondary, marginBottom: spacing.sm },
  optionsRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  optionChip: { paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  optionChipActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  optionText: { color: colors.onSurface, fontSize: 14, fontWeight: "600" },
  cta: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: 16, alignItems: "center", marginTop: spacing.xl },
  ctaText: { color: "#fff", fontSize: 16, fontWeight: "600" },
  linkBtn: { alignItems: "center", marginTop: spacing.md, padding: spacing.sm },
  linkText: { color: colors.brand, fontSize: 13, fontWeight: "500" },
  error: { color: colors.error, marginTop: spacing.md, fontSize: 14, textAlign: "center" },
});
