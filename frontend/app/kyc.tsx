import { useEffect, useState } from "react";
import {
  View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator, Linking, Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { colors, spacing, radius } from "@/src/lib/theme";

type KycStatus = {
  tier: string;
  tier_label: string;
  limits: { per_send_gbp: number; monthly_gbp: number };
  usage: { this_month_gbp: number; monthly_remaining_gbp: number; monthly_used_pct: number };
  next_tier?: string | null;
  next_tier_details?: {
    label: string;
    per_send_gbp: number;
    monthly_gbp: number;
    requires: string;
    why: string;
  } | null;
  identity_verification_status: "not_started" | "requires_input" | "processing" | "verified" | "canceled";
  identity_last_error?: { code?: string; reason?: string } | null;
  sanctions_check: { matched: boolean; checked_at: string | null };
};

const STATUS_LABEL: Record<string, string> = {
  not_started: "Not started",
  requires_input: "Action needed",
  processing: "Verifying…",
  verified: "Verified",
  canceled: "Canceled",
};
const STATUS_COLOR = (s: string) => (s === "verified" ? colors.success : s === "requires_input" ? colors.error : colors.brand);

export default function Kyc() {
  const router = useRouter();
  const params = useLocalSearchParams<{ reason?: string }>();
  const [status, setStatus] = useState<KycStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const d = await api<KycStatus>("/kyc/status");
      setStatus(d);
    } catch (e: any) {
      setErr(e?.message || "Failed to load KYC status");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const startVerification = async () => {
    setStarting(true);
    setErr(null);
    try {
      const { url } = await api<{ url: string; session_id: string }>("/kyc/session", { method: "POST" });
      // Stripe Identity is a hosted flow — redirect the user to Stripe's page,
      // then they come back via the return_url. On web this is a same-tab
      // navigation; on native this opens the system browser.
      if (Platform.OS === "web") {
        window.location.href = url;
      } else {
        await Linking.openURL(url);
      }
    } catch (e: any) {
      setErr(e?.message || "Could not start verification");
    } finally {
      setStarting(false);
    }
  };

  const tier = status?.tier ?? "unverified";
  const isVerified = tier === "kyc_lite" || tier === "kyc_full";
  const isFlagged = tier === "flagged";
  const nextDetails = status?.next_tier_details;
  const verifStatus = status?.identity_verification_status ?? "not_started";
  const showReason = params?.reason === "over_limit";

  return (
    <SafeAreaView style={s.root} edges={["top", "bottom"]}>
      <View style={s.header}>
        <Pressable testID="kyc-back" onPress={() => router.back()}>
          <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
        </Pressable>
        <Text style={s.title}>Identity</Text>
        <View style={{ width: 26 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.xl, paddingBottom: 120 }}>
        {loading ? (
          <ActivityIndicator color={colors.brand} style={{ marginTop: spacing.xl }} />
        ) : status ? (
          <>
            {showReason && !isVerified && (
              <View style={s.reasonBanner}>
                <Ionicons name="alert-circle" size={18} color={colors.brandDeep} />
                <Text style={s.reasonText}>
                  Your send exceeds your current tier&apos;s limit. Verify your identity to send up to £{nextDetails?.per_send_gbp?.toLocaleString()} per transfer.
                </Text>
              </View>
            )}

            <View style={s.tierCard}>
              <Text style={s.tierEyebrow}>Current tier</Text>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 10, marginTop: 4 }}>
                <Text style={s.tierLabel}>{status.tier_label}</Text>
                {isVerified && <Ionicons name="shield-checkmark" size={20} color={colors.success} />}
                {isFlagged && <Ionicons name="warning" size={20} color={colors.error} />}
              </View>
              <View style={s.limitGrid}>
                <View style={s.limitCell}>
                  <Text style={s.limitLabel}>Per send</Text>
                  <Text style={s.limitValue}>£{status.limits.per_send_gbp.toLocaleString()}</Text>
                </View>
                <View style={s.limitCell}>
                  <Text style={s.limitLabel}>Monthly</Text>
                  <Text style={s.limitValue}>£{status.limits.monthly_gbp.toLocaleString()}</Text>
                </View>
                <View style={s.limitCell}>
                  <Text style={s.limitLabel}>Used this month</Text>
                  <Text style={s.limitValue}>£{status.usage.this_month_gbp.toLocaleString()}</Text>
                </View>
              </View>
              <View style={s.progressBar}>
                <View style={[s.progressFill, { width: `${Math.min(100, status.usage.monthly_used_pct)}%` }]} />
              </View>
              <Text style={s.progressText}>
                £{status.usage.monthly_remaining_gbp.toLocaleString()} of monthly limit remaining
              </Text>
            </View>

            {/* Verification status */}
            <View style={s.statusRow}>
              <Text style={s.statusLabel}>Verification status</Text>
              <View style={[s.statusPill, { borderColor: STATUS_COLOR(verifStatus), backgroundColor: `${STATUS_COLOR(verifStatus)}15` }]}>
                <View style={[s.statusDot, { backgroundColor: STATUS_COLOR(verifStatus) }]} />
                <Text style={[s.statusPillText, { color: STATUS_COLOR(verifStatus) }]}>
                  {STATUS_LABEL[verifStatus] ?? verifStatus}
                </Text>
              </View>
            </View>

            {status.identity_last_error?.reason && verifStatus === "requires_input" && (
              <View style={s.errorBox}>
                <Ionicons name="information-circle" size={16} color={colors.error} />
                <Text style={s.errorBoxText}>
                  Last check failed: {status.identity_last_error.reason}. Please try again with a clearer photo.
                </Text>
              </View>
            )}

            {/* Upgrade card */}
            {!isVerified && nextDetails && (
              <View style={s.upgradeCard}>
                <View style={s.upgradeHeader}>
                  <Ionicons name="arrow-up-circle" size={22} color={colors.brand} />
                  <Text style={s.upgradeTitle}>Upgrade to {nextDetails.label}</Text>
                </View>
                <Text style={s.upgradeWhy}>{nextDetails.why}</Text>
                <View style={s.upgradeBenefits}>
                  <View style={s.upgradeBenefit}>
                    <Ionicons name="checkmark-circle" size={14} color={colors.success} />
                    <Text style={s.upgradeBenefitText}>Send up to £{nextDetails.per_send_gbp.toLocaleString()} per transfer</Text>
                  </View>
                  <View style={s.upgradeBenefit}>
                    <Ionicons name="checkmark-circle" size={14} color={colors.success} />
                    <Text style={s.upgradeBenefitText}>£{nextDetails.monthly_gbp.toLocaleString()} monthly limit</Text>
                  </View>
                  <View style={s.upgradeBenefit}>
                    <Ionicons name="checkmark-circle" size={14} color={colors.success} />
                    <Text style={s.upgradeBenefitText}>Unlock Phase C fiat off-ramps (bank / M-Pesa / MoMo) as they launch</Text>
                  </View>
                </View>
                <Text style={s.upgradeReq}>
                  Requires: {nextDetails.requires}
                </Text>
                <Pressable
                  testID="kyc-start"
                  disabled={starting}
                  onPress={startVerification}
                  style={({ pressed }) => [s.cta, pressed && { opacity: 0.9 }]}
                >
                  {starting ? (
                    <ActivityIndicator color="#0F0B08" />
                  ) : (
                    <Text style={s.ctaText}>{verifStatus === "requires_input" ? "Retry verification" : "Verify identity"}</Text>
                  )}
                </Pressable>
                <Text style={s.upgradeSecure}>
                  <Ionicons name="lock-closed" size={11} color={colors.onSurfaceTertiary} /> Powered by Stripe Identity · Your document never touches Vaulted servers
                </Text>
              </View>
            )}

            {isVerified && (
              <View style={s.verifiedCard} testID="kyc-verified">
                <Ionicons name="shield-checkmark" size={32} color={colors.success} />
                <Text style={s.verifiedTitle}>You&apos;re verified</Text>
                <Text style={s.verifiedSub}>
                  Your identity has been confirmed. You can send up to £{status.limits.per_send_gbp.toLocaleString()} per transfer, £{status.limits.monthly_gbp.toLocaleString()} per month.
                </Text>
              </View>
            )}

            {isFlagged && (
              <View style={s.flaggedCard}>
                <Ionicons name="warning" size={26} color={colors.error} />
                <Text style={s.flaggedTitle}>Account under review</Text>
                <Text style={s.flaggedSub}>
                  Your identity check matched a sanctions list entry. We&apos;ve paused your account pending manual review — contact support@phoenix-atlas.com.
                </Text>
              </View>
            )}

            {err && <Text style={s.err}>{err}</Text>}

            {/* Compliance footer — user education */}
            <View style={s.legal}>
              <Text style={s.legalTitle}>Why do we ask this?</Text>
              <Text style={s.legalBody}>
                Vaulted is a UK-registered money transmission service, subject to the Money Laundering Regulations 2017 and the FATF Travel Rule. Identity verification is required by law above certain send limits. Verified data is stored encrypted, never sold, and never shared beyond regulatory compliance.
              </Text>
            </View>
          </>
        ) : (
          <Text style={s.err}>{err ?? "No data"}</Text>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.xl, paddingTop: spacing.sm, paddingBottom: spacing.md },
  title: { fontSize: 17, fontWeight: "700", color: colors.onSurface },

  reasonBanner: { flexDirection: "row", alignItems: "center", gap: 10, padding: spacing.md, backgroundColor: colors.brandTertiary, borderRadius: radius.md, borderWidth: 1, borderColor: "rgba(201,163,91,0.40)", marginBottom: spacing.lg },
  reasonText: { flex: 1, color: colors.brandDeep, fontSize: 12, lineHeight: 16 },

  tierCard: { padding: spacing.lg, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border },
  tierEyebrow: { fontSize: 11, letterSpacing: 1.5, textTransform: "uppercase", color: colors.onSurfaceTertiary },
  tierLabel: { fontSize: 22, fontWeight: "800", color: colors.onSurface, letterSpacing: -0.4 },
  limitGrid: { flexDirection: "row", gap: spacing.md, marginTop: spacing.lg, flexWrap: "wrap" },
  limitCell: { flex: 1, minWidth: 90 },
  limitLabel: { fontSize: 11, color: colors.onSurfaceTertiary, marginBottom: 2 },
  limitValue: { fontSize: 15, fontWeight: "700", color: colors.onSurface },
  progressBar: { height: 4, backgroundColor: colors.border, borderRadius: 2, marginTop: spacing.lg, overflow: "hidden" },
  progressFill: { height: 4, backgroundColor: colors.brand },
  progressText: { fontSize: 11, color: colors.onSurfaceTertiary, marginTop: 6 },

  statusRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: spacing.xl, paddingHorizontal: 4 },
  statusLabel: { fontSize: 13, color: colors.onSurfaceSecondary, fontWeight: "500" },
  statusPill: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 10, paddingVertical: 5, borderRadius: radius.pill, borderWidth: 1 },
  statusDot: { width: 6, height: 6, borderRadius: 3 },
  statusPillText: { fontSize: 11, fontWeight: "700", letterSpacing: 0.4 },

  errorBox: { flexDirection: "row", gap: 8, alignItems: "flex-start", padding: spacing.sm, backgroundColor: "rgba(200,60,60,0.10)", borderRadius: radius.md, borderWidth: 1, borderColor: "rgba(200,60,60,0.35)", marginTop: spacing.sm },
  errorBoxText: { flex: 1, color: colors.error, fontSize: 12, lineHeight: 16 },

  upgradeCard: { padding: spacing.lg, backgroundColor: colors.brandTertiary, borderRadius: radius.lg, borderWidth: 1, borderColor: "rgba(201,163,91,0.40)", marginTop: spacing.xl },
  upgradeHeader: { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: spacing.sm },
  upgradeTitle: { fontSize: 16, fontWeight: "700", color: colors.brandDeep, letterSpacing: -0.2 },
  upgradeWhy: { fontSize: 12, color: colors.onSurfaceSecondary, lineHeight: 17, marginBottom: spacing.md },
  upgradeBenefits: { gap: 8, marginBottom: spacing.md },
  upgradeBenefit: { flexDirection: "row", alignItems: "center", gap: 8 },
  upgradeBenefitText: { flex: 1, color: colors.onSurface, fontSize: 12 },
  upgradeReq: { fontSize: 11, color: colors.onSurfaceTertiary, marginBottom: spacing.md },
  upgradeSecure: { fontSize: 10, color: colors.onSurfaceTertiary, marginTop: spacing.md, textAlign: "center" },

  cta: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: 14, alignItems: "center" },
  ctaText: { color: "#0F0B08", fontSize: 15, fontWeight: "700" },

  verifiedCard: { alignItems: "center", padding: spacing.xl, marginTop: spacing.xl, backgroundColor: "rgba(60,180,90,0.08)", borderRadius: radius.lg, borderWidth: 1, borderColor: "rgba(60,180,90,0.40)" },
  verifiedTitle: { fontSize: 18, fontWeight: "700", color: colors.onSurface, marginTop: spacing.sm },
  verifiedSub: { fontSize: 12, color: colors.onSurfaceSecondary, textAlign: "center", marginTop: 6, lineHeight: 17 },

  flaggedCard: { alignItems: "center", padding: spacing.xl, marginTop: spacing.xl, backgroundColor: "rgba(200,60,60,0.08)", borderRadius: radius.lg, borderWidth: 1, borderColor: "rgba(200,60,60,0.40)" },
  flaggedTitle: { fontSize: 16, fontWeight: "700", color: colors.error, marginTop: spacing.sm },
  flaggedSub: { fontSize: 12, color: colors.onSurfaceSecondary, textAlign: "center", marginTop: 6, lineHeight: 17 },

  err: { color: colors.error, fontSize: 13, textAlign: "center", marginTop: spacing.md },

  legal: { marginTop: spacing.xl, padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  legalTitle: { fontSize: 12, fontWeight: "700", color: colors.onSurface, marginBottom: 4 },
  legalBody: { fontSize: 11, color: colors.onSurfaceTertiary, lineHeight: 16 },
});
