import { useCallback, useState } from "react";
import {
  View, Text, StyleSheet, Pressable, ScrollView, TextInput,
  ActivityIndicator, KeyboardAvoidingView, Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { useAuth } from "@/src/lib/auth";
import { colors, spacing, radius } from "@/src/lib/theme";

type Cosigner = { id: string; email: string; label: string; status: string; added_at: string };

export default function CosignersScreen() {
  const router = useRouter();
  const { user } = useAuth();
  const [items, setItems] = useState<Cosigner[]>([]);
  const [email, setEmail] = useState("");
  const [label, setLabel] = useState("");
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = async () => {
    try { setItems(await api<Cosigner[]>("/cosigners")); } catch (e) { console.log(e); }
  };
  useFocusEffect(useCallback(() => { setLoading(true); load().finally(() => setLoading(false)); }, []));

  const add = async () => {
    setErr(null);
    if (!email.includes("@")) { setErr("Enter a valid email"); return; }
    setAdding(true);
    try {
      await api("/cosigners", { method: "POST", body: { email: email.trim(), label: label.trim() || null } });
      setEmail(""); setLabel("");
      await load();
    } catch (e: any) { setErr(e.message); } finally { setAdding(false); }
  };

  const remove = async (id: string) => {
    try { await api(`/cosigners/${id}`, { method: "DELETE" }); await load(); } catch (e) { console.log(e); }
  };

  return (
    <SafeAreaView style={s.root} edges={["top", "bottom"]}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1 }}>
        <View style={s.header}>
          <Pressable testID="cosigners-back" onPress={() => router.back()}><Ionicons name="chevron-back" size={26} color={colors.onSurface} /></Pressable>
          <Text style={s.title}>Co-signers</Text>
          <View style={{ width: 26 }} />
        </View>
        <ScrollView contentContainerStyle={{ padding: spacing.xl }} keyboardShouldPersistTaps="handled">
          <Text style={s.subtitle}>
            Adding a co-signer turns on 2-of-2 approvals for any ETH send ≥ 0.01 on Sepolia. They get an email with Approve / Reject buttons. {!user?.is_pro && "Vault Pro required."}
          </Text>

          {loading ? <ActivityIndicator color={colors.brand} style={{ marginTop: 24 }} /> :
            items.length === 0 ? (
              <View style={s.empty}>
                <Ionicons name="people-outline" size={28} color={colors.onSurfaceTertiary} />
                <Text style={s.emptyText}>No co-signers yet</Text>
              </View>
            ) : (
              <View style={s.listCard}>
                {items.map((c, i) => (
                  <View key={c.id}>
                    <View style={s.row} testID={`cosigner-${c.id}`}>
                      <View style={s.rowIcon}><Ionicons name="person" size={18} color={colors.brand} /></View>
                      <View style={{ flex: 1 }}>
                        <Text style={s.rowName}>{c.label}</Text>
                        <Text style={s.rowEmail}>{c.email}</Text>
                      </View>
                      <Pressable testID={`remove-${c.id}`} onPress={() => remove(c.id)}>
                        <Ionicons name="trash-outline" size={18} color={colors.error} />
                      </Pressable>
                    </View>
                    {i < items.length - 1 && <View style={s.sep} />}
                  </View>
                ))}
              </View>
            )
          }

          <Text style={s.section}>Add a co-signer</Text>
          <Text style={s.label}>Email</Text>
          <TextInput testID="cosigner-email" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" placeholder="co-signer@example.com" placeholderTextColor={colors.onSurfaceTertiary} style={s.input} />
          <Text style={s.label}>Label (optional)</Text>
          <TextInput testID="cosigner-label" value={label} onChangeText={setLabel} placeholder="e.g. My phone, Spouse" placeholderTextColor={colors.onSurfaceTertiary} style={s.input} />

          {err && <Text testID="cosigner-error" style={s.error}>{err}</Text>}

          <Pressable testID="cosigner-add-btn" disabled={adding} onPress={add} style={({ pressed }) => [s.cta, pressed && { opacity: 0.85 }, !user?.is_pro && { opacity: 0.5 }]}>
            {adding ? <ActivityIndicator color="#fff" /> : <Text style={s.ctaText}>{user?.is_pro ? "Send invite email" : "Vault Pro required"}</Text>}
          </Pressable>

          {!user?.is_pro && (
            <Pressable testID="cosigner-upsell" onPress={() => router.push("/vault-pro")} style={s.upsell}>
              <Text style={s.upsellText}>Unlock with Vault Pro →</Text>
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
  subtitle: { fontSize: 13, color: colors.onSurfaceSecondary, lineHeight: 18, marginBottom: spacing.lg },
  empty: { alignItems: "center", gap: 6, padding: spacing.xl },
  emptyText: { color: colors.onSurfaceSecondary, fontSize: 14 },
  listCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, overflow: "hidden" },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.lg },
  rowIcon: { width: 36, height: 36, borderRadius: radius.pill, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  rowName: { color: colors.onSurface, fontWeight: "600", fontSize: 14 },
  rowEmail: { color: colors.onSurfaceTertiary, fontSize: 12, marginTop: 2 },
  sep: { height: 1, backgroundColor: colors.divider, marginLeft: spacing.lg + 36 + spacing.md },
  section: { fontSize: 12, fontWeight: "600", color: colors.onSurfaceTertiary, textTransform: "uppercase", letterSpacing: 0.5, marginTop: spacing.xl, marginBottom: spacing.sm },
  label: { fontSize: 13, color: colors.onSurfaceSecondary, marginBottom: spacing.xs, marginTop: spacing.md, fontWeight: "500" },
  input: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.lg, paddingVertical: 14, fontSize: 15, color: colors.onSurface, backgroundColor: colors.surface },
  cta: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: 16, alignItems: "center", marginTop: spacing.xl },
  ctaText: { color: "#fff", fontSize: 16, fontWeight: "600" },
  upsell: { alignItems: "center", padding: spacing.md, marginTop: 4 },
  upsellText: { color: colors.brand, fontSize: 13, fontWeight: "600" },
  error: { color: colors.error, marginTop: spacing.md, fontSize: 14 },
});
