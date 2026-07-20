/**
 * Admin — Manual EDD (Enhanced Due Diligence) Approval
 * =====================================================
 * Route: /admin/kyc-override
 *
 * Only accessible to users whose email is in the backend's `ADMIN_EMAILS`
 * env var. Backend enforces the auth check — this screen is just the UI.
 *
 * Used when Stripe Identity's automated face-match / document-check fails
 * on a legitimate user (algorithm ceiling, common with older ID photos or
 * demographic edge cases). MLR 2017 Reg 33 allows manual EDD provided we
 * record who reviewed, what docs, and why.
 *
 * Design intentionally form-heavy to force the admin to think about
 * evidence — an accidentally-clicked "approve" button is a compliance
 * disaster.
 */
import { useEffect, useState } from "react";
import {
  View, Text, TextInput, Pressable, StyleSheet, ScrollView,
  ActivityIndicator, KeyboardAvoidingView, Platform, Alert,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { useAuth } from "@/src/lib/auth";
import { colors, spacing, radius } from "@/src/lib/theme";

type Tier = "basic" | "kyc_verified" | "enhanced";
type DocOption = { id: string; label: string };
const DOC_OPTIONS: DocOption[] = [
  { id: "passport", label: "Passport" },
  { id: "driving_licence", label: "Driving licence" },
  { id: "national_id", label: "National ID card" },
  { id: "brp", label: "UK BRP" },
  { id: "utility_bill", label: "Utility bill < 3 months" },
  { id: "bank_statement", label: "Bank statement < 3 months" },
  { id: "council_tax", label: "Council tax bill" },
  { id: "selfie_with_id", label: "Selfie holding ID" },
];

export default function AdminKycOverride() {
  const router = useRouter();
  const { user } = useAuth();
  const [targetEmail, setTargetEmail] = useState<string>(user?.email || "");
  const [tier, setTier] = useState<Tier>("kyc_verified");
  const [reference, setReference] = useState("");
  const [reason, setReason] = useState("");
  const [selectedDocs, setSelectedDocs] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Pre-populate `reference` with an auto-generated ticket for convenience —
  // admin can overwrite if they have a real ticket ref.
  useEffect(() => {
    if (!reference) {
      const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, "");
      setReference(`EDD-${stamp}-${Math.random().toString(36).slice(2, 8).toUpperCase()}`);
    }
  }, [reference]);

  const toggleDoc = (id: string) => {
    setSelectedDocs((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const submit = () => {
    setErr(null);
    const email = targetEmail.trim().toLowerCase();
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setErr("Enter a valid email address for the target user");
      return;
    }
    if (reference.trim().length < 6) {
      setErr("EDD reference must be at least 6 characters (auto-populated at page load)");
      return;
    }
    if (reason.trim().length < 8) {
      setErr("Add a substantive reason (min 8 chars) — this is the FCA audit evidence");
      return;
    }
    if (selectedDocs.size === 0) {
      setErr("Tick at least one document you reviewed");
      return;
    }

    Alert.alert(
      "Confirm manual EDD approval",
      `Mark ${email} as ${tier.replace("_", " ")} verified?\n\nThis is a regulated action. The approval will be logged to the immutable audit trail with your admin email hash. Continue only if you have physically verified the customer's documents.`,
      [
        { text: "Cancel", style: "cancel" },
        { text: "Approve", style: "destructive", onPress: doSubmit },
      ],
    );
  };

  const doSubmit = async () => {
    setSubmitting(true);
    setErr(null);
    try {
      const r = await api<{ ok: boolean; user: any }>(
        "/admin/kyc/manual-edd-approve",
        {
          method: "POST",
          body: {
            user_email: targetEmail.trim().toLowerCase(),
            target_tier: tier,
            edd_reference: reference.trim(),
            edd_reason: reason.trim(),
            documents_verified: Array.from(selectedDocs),
          },
        },
      );
      setSuccess(
        `${r.user.email} is now ${r.user.kyc?.tier ?? tier}. Refresh their app to see the new limits.`,
      );
    } catch (e: any) {
      const msg = e?.message || "Approval failed";
      // Friendly copy for the common auth mismatch scenario.
      if (msg.toLowerCase().includes("admin") || msg.toLowerCase().includes("403")) {
        setErr("Your account is not in ADMIN_EMAILS on Render. Add your email there, then sign out and sign back in.");
      } else {
        setErr(msg);
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={s.root} edges={["top", "bottom"]}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1 }}>
        <View style={s.header}>
          <Pressable testID="admin-edd-back" onPress={() => router.back()} hitSlop={10}>
            <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
          </Pressable>
          <Text style={s.title}>Manual EDD Approval</Text>
          <View style={{ width: 26 }} />
        </View>

        <ScrollView contentContainerStyle={s.body} keyboardShouldPersistTaps="handled">
          <View style={s.warningCard}>
            <Ionicons name="shield-checkmark" size={22} color={colors.brand} />
            <View style={{ flex: 1 }}>
              <Text style={s.warningTitle}>Regulated action — MLR 2017 Reg 33</Text>
              <Text style={s.warningBody}>
                {"Only use this when Stripe Identity's automated flow has failed for a customer whose documents you have physically verified. Every approval is written to the immutable audit log with your admin email hash. Include enough detail in the \"reason\" field that another compliance reviewer could reconstruct why manual EDD was warranted."}
              </Text>
            </View>
          </View>

          <Text style={s.label}>Target user email</Text>
          <TextInput
            testID="edd-target-email"
            value={targetEmail}
            onChangeText={setTargetEmail}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="email-address"
            placeholder="user@example.com"
            placeholderTextColor={colors.onSurfaceTertiary}
            style={s.input}
          />
          <Text style={s.help}>The customer you are approving. Pre-filled with your own email — change if approving someone else.</Text>

          <Text style={s.label}>Target tier</Text>
          <View style={s.tierRow}>
            {(["basic", "kyc_verified", "enhanced"] as Tier[]).map((tt) => (
              <Pressable
                key={tt}
                testID={`edd-tier-${tt}`}
                onPress={() => setTier(tt)}
                style={[s.tierChip, tier === tt && s.tierChipActive]}
              >
                <Text style={[s.tierChipText, tier === tt && s.tierChipTextActive]}>
                  {tt === "basic" ? "Basic (£100/tx)" : tt === "kyc_verified" ? "Verified (£1k/tx · £5k/mo)" : "Enhanced (£15k+)"}
                </Text>
              </Pressable>
            ))}
          </View>

          <Text style={s.label}>EDD reference</Text>
          <TextInput
            testID="edd-reference"
            value={reference}
            onChangeText={setReference}
            placeholder="EDD-YYYYMMDD-XXXXXX"
            placeholderTextColor={colors.onSurfaceTertiary}
            style={s.input}
          />
          <Text style={s.help}>Auto-generated. Overwrite with your compliance ticket ref if you have one.</Text>

          <Text style={s.label}>Reason for manual approval</Text>
          <TextInput
            testID="edd-reason"
            value={reason}
            onChangeText={setReason}
            placeholder="e.g. Stripe Identity face-match failed 11 attempts across passport + licence. Customer's ID photo is 8 years old; algorithm confidence too low. Reviewed docs in person on 2026-07-17; face + ID match confirmed."
            placeholderTextColor={colors.onSurfaceTertiary}
            multiline
            numberOfLines={4}
            style={[s.input, s.multiline]}
          />
          <Text style={s.help}>Be specific — this is the FCA audit evidence. Minimum 8 chars.</Text>

          <Text style={s.label}>Documents reviewed</Text>
          <View style={s.docGrid}>
            {DOC_OPTIONS.map((opt) => {
              const selected = selectedDocs.has(opt.id);
              return (
                <Pressable
                  key={opt.id}
                  testID={`edd-doc-${opt.id}`}
                  onPress={() => toggleDoc(opt.id)}
                  style={[s.docChip, selected && s.docChipActive]}
                >
                  <Ionicons
                    name={selected ? "checkbox" : "square-outline"}
                    size={16}
                    color={selected ? colors.brand : colors.onSurfaceTertiary}
                  />
                  <Text style={[s.docChipText, selected && s.docChipTextActive]}>{opt.label}</Text>
                </Pressable>
              );
            })}
          </View>

          {err && (
            <View style={s.errorBox}>
              <Ionicons name="alert-circle" size={16} color={colors.error} />
              <Text style={s.errorText}>{err}</Text>
            </View>
          )}
          {success && (
            <View style={s.successBox}>
              <Ionicons name="checkmark-circle" size={16} color={colors.success} />
              <Text style={s.successText}>{success}</Text>
            </View>
          )}

          <Pressable
            testID="edd-submit"
            onPress={submit}
            disabled={submitting}
            style={({ pressed }) => [s.cta, (pressed || submitting) && { opacity: 0.75 }]}
          >
            {submitting ? (
              <ActivityIndicator color="#0F0B08" />
            ) : (
              <>
                <Ionicons name="shield-checkmark" size={18} color="#0F0B08" />
                <Text style={s.ctaText}>Approve manual EDD</Text>
              </>
            )}
          </Pressable>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: spacing.xl, paddingVertical: spacing.md,
    borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  title: { fontSize: 17, fontWeight: "700", color: colors.onSurface },
  body: { padding: spacing.xl, paddingBottom: 60, gap: spacing.md },
  warningCard: {
    flexDirection: "row", gap: spacing.md, alignItems: "flex-start",
    padding: spacing.md, borderRadius: radius.md,
    backgroundColor: "rgba(201,163,91,0.10)",
    borderWidth: 1, borderColor: "rgba(201,163,91,0.30)",
    marginBottom: spacing.md,
  },
  warningTitle: { fontSize: 13, fontWeight: "700", color: colors.brandDeep, marginBottom: 4 },
  warningBody: { fontSize: 12, color: colors.onSurfaceSecondary, lineHeight: 17 },
  label: { fontSize: 13, fontWeight: "600", color: colors.onSurface, marginTop: spacing.sm },
  input: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.md, paddingVertical: 12, fontSize: 15,
    color: colors.onSurface, backgroundColor: colors.surfaceSecondary,
  },
  multiline: { minHeight: 96, textAlignVertical: "top" },
  help: { fontSize: 11, color: colors.onSurfaceTertiary, marginTop: 4, lineHeight: 15 },
  tierRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  tierChip: {
    paddingHorizontal: 12, paddingVertical: 8, borderRadius: 999,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
  },
  tierChipActive: { backgroundColor: colors.brandTertiary, borderColor: colors.brand },
  tierChipText: { fontSize: 12, color: colors.onSurfaceSecondary, fontWeight: "600" },
  tierChipTextActive: { color: colors.onSurface },
  docGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  docChip: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: 10, paddingVertical: 8, borderRadius: 999,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
  },
  docChipActive: { backgroundColor: colors.brandTertiary, borderColor: colors.brand },
  docChipText: { fontSize: 12, color: colors.onSurfaceSecondary },
  docChipTextActive: { color: colors.onSurface, fontWeight: "600" },
  errorBox: {
    flexDirection: "row", alignItems: "flex-start", gap: 8,
    padding: spacing.sm, borderRadius: radius.md,
    backgroundColor: "rgba(200,60,60,0.08)", borderWidth: 1, borderColor: "rgba(200,60,60,0.30)",
  },
  errorText: { flex: 1, color: colors.error, fontSize: 13, lineHeight: 18 },
  successBox: {
    flexDirection: "row", alignItems: "flex-start", gap: 8,
    padding: spacing.sm, borderRadius: radius.md,
    backgroundColor: "rgba(60,180,90,0.10)", borderWidth: 1, borderColor: "rgba(60,180,90,0.35)",
  },
  successText: { flex: 1, color: colors.success, fontSize: 13, lineHeight: 18, fontWeight: "600" },
  cta: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
    backgroundColor: colors.brand, borderRadius: radius.md,
    paddingVertical: 15, marginTop: spacing.lg,
  },
  ctaText: { color: "#0F0B08", fontSize: 15, fontWeight: "700", letterSpacing: 0.3 },
});
