import { View, Text, StyleSheet, Pressable, ScrollView, Switch } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "@/src/lib/auth";
import { useI18n, LANGUAGES } from "@/src/lib/i18n";
import { api } from "@/src/lib/api";
import { colors, spacing, radius } from "@/src/lib/theme";

export default function Settings() {
  const { user, setUser, logout } = useAuth();
  const { t, lang, setLang } = useI18n();
  const router = useRouter();

  const toggleSecurity = async (key: "biometric_enabled" | "multisig_enabled", val: boolean) => {
    try {
      const updated = await api("/auth/security", { method: "PATCH", body: { [key]: val } });
      setUser(updated as any);
    } catch (e) { console.log(e); }
  };

  const Row = ({ icon, label, onPress, right, testID }: any) => (
    <Pressable testID={testID} onPress={onPress} style={({ pressed }) => [s.row, pressed && { backgroundColor: colors.surfaceSecondary }]}>
      <View style={s.rowIcon}><Ionicons name={icon} size={18} color={colors.brand} /></View>
      <Text style={s.rowLabel}>{label}</Text>
      <View style={{ flex: 1 }} />
      {right ?? <Ionicons name="chevron-forward" size={18} color={colors.onSurfaceTertiary} />}
    </Pressable>
  );

  return (
    <SafeAreaView style={s.root} edges={["top"]}>
      <ScrollView contentContainerStyle={{ paddingBottom: spacing.xxxl }}>
        <View style={s.header}><Text style={s.title}>{t("settings")}</Text></View>

        <View style={s.profile}>
          <View style={s.avatar}><Ionicons name="person" size={28} color={colors.brand} /></View>
          <Text style={s.name}>{user?.name}</Text>
          <Text style={s.email}>{user?.email}</Text>
        </View>

        <Text style={s.section}>Subscription</Text>
        <View style={s.card}>
          <Pressable
            testID="open-vaultpro"
            onPress={() => router.push("/vault-pro")}
            style={({ pressed }) => [s.row, pressed && { backgroundColor: colors.surfaceSecondary }]}
          >
            <View style={[s.rowIcon, { backgroundColor: user?.is_pro ? colors.brand : colors.brandTertiary }]}>
              <Ionicons name="star" size={18} color={user?.is_pro ? "#fff" : colors.brand} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={s.rowLabel}>Vault Pro</Text>
              <Text style={[s.rowLabel, { fontSize: 11, color: colors.onSurfaceTertiary, marginTop: 2 }]}>
                {user?.is_pro ? `Active · ${user?.subscription?.status}` : "Unlock multi-sig, lower fees & priority"}
              </Text>
            </View>
            {user?.is_pro && (
              <View style={s.proBadge}><Text style={s.proBadgeText}>PRO</Text></View>
            )}
            <Ionicons name="chevron-forward" size={18} color={colors.onSurfaceTertiary} />
          </Pressable>
        </View>

        <Text style={s.section}>{t("language")}</Text>
        <View style={s.card}>
          {LANGUAGES.map((l, idx) => (
            <Pressable
              key={l.code}
              testID={`lang-${l.code}`}
              onPress={() => setLang(l.code)}
              style={({ pressed }) => [s.row, pressed && { backgroundColor: colors.surfaceSecondary }]}
            >
              <View style={s.rowIcon}><Ionicons name="globe-outline" size={18} color={colors.brand} /></View>
              <Text style={s.rowLabel}>{l.label}</Text>
              <View style={{ flex: 1 }} />
              {lang === l.code && <Ionicons name="checkmark" size={20} color={colors.brand} />}
            </Pressable>
          ))}
        </View>

        <Text style={s.section}>{t("security")}</Text>
        <View style={s.card}>
          <Row
            icon="finger-print"
            label={t("biometric")}
            testID="toggle-biometric"
            right={
              <Switch
                testID="biometric-switch"
                value={!!user?.biometric_enabled}
                onValueChange={(v) => toggleSecurity("biometric_enabled", v)}
                trackColor={{ true: colors.brand, false: colors.borderStrong }}
              />
            }
          />
          <View style={s.sep} />
          <Row
            icon="key"
            label={t("multisig")}
            testID="toggle-multisig"
            right={
              <Switch
                testID="multisig-switch"
                value={!!user?.multisig_enabled}
                onValueChange={(v) => {
                  if (!user?.is_pro && v) {
                    router.push("/vault-pro");
                    return;
                  }
                  toggleSecurity("multisig_enabled", v);
                }}
                trackColor={{ true: colors.brand, false: colors.borderStrong }}
              />
            }
          />
          <View style={s.sep} />
          <Row
            icon="people"
            label="Co-signers"
            testID="open-cosigners"
            onPress={() => router.push("/cosigners")}
          />
          <View style={s.sep} />
          <Row
            icon="time"
            label="Pending approvals"
            testID="open-approvals"
            onPress={() => router.push("/approvals")}
          />
          <View style={s.sep} />
          <Row
            icon="reader"
            label="Show recovery phrase"
            testID="open-seed-phrase"
            onPress={() => router.push("/onboarding/seed")}
          />
          <View style={s.sep} />
          <Row
            icon="document-text"
            label="Export private key"
            testID="open-export-key"
            onPress={() => router.push("/export-key")}
          />
        </View>

        <Pressable testID="logout-button" onPress={async () => { await logout(); router.replace("/(auth)/login"); }} style={s.logout}>
          <Ionicons name="log-out-outline" size={18} color={colors.error} />
          <Text style={s.logoutText}>{t("logout")}</Text>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}
const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.xl, paddingTop: spacing.md, paddingBottom: spacing.md },
  title: { fontSize: 26, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.6 },
  profile: { alignItems: "center", paddingVertical: spacing.lg },
  avatar: { width: 72, height: 72, borderRadius: radius.pill, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center", marginBottom: spacing.md },
  name: { fontSize: 18, fontWeight: "700", color: colors.onSurface },
  email: { fontSize: 13, color: colors.onSurfaceSecondary, marginTop: 2 },
  section: { fontSize: 12, fontWeight: "600", color: colors.onSurfaceTertiary, textTransform: "uppercase", marginTop: spacing.xl, marginBottom: spacing.sm, paddingHorizontal: spacing.xl, letterSpacing: 0.5 },
  card: { marginHorizontal: spacing.xl, borderRadius: radius.lg, backgroundColor: colors.surfaceSecondary, overflow: "hidden" },
  row: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, paddingVertical: spacing.md, gap: spacing.md },
  rowIcon: { width: 32, height: 32, borderRadius: radius.pill, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  rowLabel: { color: colors.onSurface, fontSize: 15, fontWeight: "500" },
  sep: { height: 1, backgroundColor: colors.divider, marginLeft: spacing.lg + 32 + spacing.md },
  logout: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, marginTop: spacing.xl, marginHorizontal: spacing.xl, paddingVertical: spacing.lg, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  logoutText: { color: colors.error, fontWeight: "600", fontSize: 15 },
  proBadge: { backgroundColor: colors.brand, paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.pill, marginRight: 8 },
  proBadgeText: { color: "#fff", fontSize: 10, fontWeight: "800", letterSpacing: 0.5 },
});
