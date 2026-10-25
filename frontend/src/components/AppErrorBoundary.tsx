/**
 * Root crash screen — expo-router renders this when any screen throws,
 * instead of closing the app (Apple 2.1 stability).
 */
import { View, Text, Pressable, StyleSheet } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { colors, spacing, radius } from "@/src/lib/theme";

type Props = { error: Error; retry: () => Promise<void> };

export default function AppErrorBoundary({ error, retry }: Props) {
  console.log("[ErrorBoundary]", error?.message);
  return (
    <SafeAreaView style={s.root}>
      <View style={s.body} testID="app-error-boundary">
        <Text style={s.title}>Something went wrong</Text>
        <Text style={s.sub}>Your wallet and funds are safe. Please try again.</Text>
        <Pressable testID="app-error-retry" onPress={retry} style={s.cta}>
          <Text style={s.ctaText}>Try again</Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  body: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.md },
  title: { fontSize: 22, fontWeight: "700", color: colors.onSurface },
  sub: { fontSize: 14, color: colors.onSurfaceSecondary, textAlign: "center" },
  cta: { marginTop: spacing.md, backgroundColor: colors.brand, borderRadius: radius.pill, paddingHorizontal: spacing.xl, minHeight: 48, justifyContent: "center" },
  ctaText: { color: "#0F0B08", fontWeight: "700", fontSize: 15 },
});
