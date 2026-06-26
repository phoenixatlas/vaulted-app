import { View, Text, StyleSheet, Pressable, Share, Platform } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "@/src/lib/auth";
import { useI18n } from "@/src/lib/i18n";
import { colors, spacing, radius } from "@/src/lib/theme";

export default function Receive() {
  const { user } = useAuth();
  const { t } = useI18n();
  const router = useRouter();

  const share = async () => {
    if (user?.wallet_address) await Share.share({ message: user.wallet_address });
  };

  return (
    <SafeAreaView style={s.root} edges={["top", "bottom"]}>
      <View style={s.header}>
        <Pressable testID="receive-back" onPress={() => router.back()}><Ionicons name="chevron-back" size={26} color={colors.onSurface} /></Pressable>
        <Text style={s.title}>{t("receive_crypto")}</Text>
        <View style={{ width: 26 }} />
      </View>
      <View style={s.body}>
        <View style={s.qrBox}>
          <Ionicons name="qr-code" size={180} color={colors.onSurface} />
        </View>
        <Text style={s.label}>{t("your_address")}</Text>
        <View style={s.addrBox}>
          <Text testID="receive-address" style={s.addrText} selectable>{user?.wallet_address}</Text>
        </View>
        <Pressable testID="share-address" onPress={share} style={s.cta}><Text style={s.ctaText}>Share address</Text></Pressable>
      </View>
    </SafeAreaView>
  );
}
const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.xl, paddingTop: spacing.sm, paddingBottom: spacing.md },
  title: { fontSize: 17, fontWeight: "700", color: colors.onSurface },
  body: { padding: spacing.xl, alignItems: "center", gap: spacing.lg },
  qrBox: { width: 240, height: 240, borderRadius: radius.lg, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", marginTop: spacing.xl },
  label: { fontSize: 13, color: colors.onSurfaceSecondary, marginTop: spacing.lg },
  addrBox: { backgroundColor: colors.surfaceSecondary, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: radius.md },
  addrText: { color: colors.onSurface, fontSize: 13, fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace" },
  cta: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: 14, paddingHorizontal: spacing.xxl, marginTop: spacing.md },
  ctaText: { color: "#0F0B08", fontSize: 15, fontWeight: "600" },
});
