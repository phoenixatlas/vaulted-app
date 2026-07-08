import { useCallback, useEffect, useState } from "react";
import {
  View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator,
  Share, RefreshControl, Alert,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Clipboard from "expo-clipboard";
import { api } from "@/src/lib/api";
import { colors, spacing, radius } from "@/src/lib/theme";

type ReferralSummary = {
  referral_code: string;
  share_link: string;
  share_message: string;
  credit_balance_gbp: number;
  reward_per_side_gbp: number;
  signup_bonus_gbp: number;
  total_referred: number;
  credited_count: number;
  pending_count: number;
  referrals: {
    id: string;
    status: "pending" | "credited" | "rejected";
    created_at: string;
    credited_at: string | null;
    friend_email_masked: string;
    friend_kyc_status: string;
  }[];
};

export default function ReferralScreen() {
  const router = useRouter();
  const [data, setData] = useState<ReferralSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    try {
      const d = await api<ReferralSummary>("/referrals/me");
      setData(d);
      setErr(null);
    } catch (e: any) {
      setErr(e?.message || "Failed to load referrals");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const onCopy = async () => {
    if (!data) return;
    try {
      await Clipboard.setStringAsync(data.share_link);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      Alert.alert("Couldn't copy", "Please long-press the link to copy it manually.");
    }
  };

  const onShare = async () => {
    if (!data) return;
    try {
      await Share.share({
        message: `${data.share_message}\n\n${data.share_link}`,
        url: data.share_link,   // iOS picks this up; Android uses message
        title: "Send money home for less on Vaulted",
      });
    } catch {
      // Silently ignore user-cancelled shares
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={s.root} edges={["top", "bottom"]}>
        <View style={s.headerBar}>
          <Pressable testID="referral-back" onPress={() => router.back()} hitSlop={12}>
            <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
          </Pressable>
          <Text style={s.headerTitle}>Invite friends</Text>
          <View style={{ width: 26 }} />
        </View>
        <View style={s.centered}>
          <ActivityIndicator color={colors.brand} size="large" />
        </View>
      </SafeAreaView>
    );
  }

  if (err || !data) {
    return (
      <SafeAreaView style={s.root} edges={["top", "bottom"]}>
        <View style={s.centered}>
          <Text style={s.errText}>{err ?? "No data"}</Text>
          <Pressable testID="referral-retry" onPress={load} style={s.ctaSecondary}>
            <Text style={s.ctaSecondaryText}>Try again</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.root} edges={["top", "bottom"]}>
      <View style={s.headerBar}>
        <Pressable testID="referral-back" onPress={() => router.back()} hitSlop={12}>
          <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
        </Pressable>
        <Text style={s.headerTitle}>Invite friends</Text>
        <View style={{ width: 26 }} />
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.xl, paddingBottom: 120 }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} />}
      >
        {/* Hero — big pitch */}
        <View style={s.heroCard}>
          <Ionicons name="gift" size={36} color={colors.brandDeep} />
          <Text style={s.heroTitle}>
            Give £{data.signup_bonus_gbp.toFixed(0)}, get £{data.reward_per_side_gbp.toFixed(0)}
          </Text>
          <Text style={s.heroBody}>
            Share your link. When a friend signs up and verifies their identity, you both
            get £{data.reward_per_side_gbp.toFixed(0)} credit toward transfer fees.
          </Text>
        </View>

        {/* Credit balance */}
        <View style={s.balanceRow}>
          <View style={s.balanceCell}>
            <Text style={s.balanceLabel}>Credit balance</Text>
            <Text style={s.balanceValue} testID="referral-balance">
              £{data.credit_balance_gbp.toFixed(2)}
            </Text>
          </View>
          <View style={s.balanceDivider} />
          <View style={s.balanceCell}>
            <Text style={s.balanceLabel}>Friends verified</Text>
            <Text style={s.balanceValue} testID="referral-credited-count">
              {data.credited_count}
            </Text>
          </View>
          {data.pending_count > 0 && (
            <>
              <View style={s.balanceDivider} />
              <View style={s.balanceCell}>
                <Text style={s.balanceLabel}>Pending</Text>
                <Text style={s.balanceValue} testID="referral-pending-count">
                  {data.pending_count}
                </Text>
              </View>
            </>
          )}
        </View>

        {/* Share link block */}
        <View style={s.linkCard}>
          <Text style={s.linkLabel}>Your invite link</Text>
          <View style={s.linkRow}>
            <Text style={s.linkText} numberOfLines={1} testID="referral-share-link">
              {data.share_link}
            </Text>
            <Pressable testID="referral-copy" onPress={onCopy} hitSlop={8} style={s.copyBtn}>
              <Ionicons name={copied ? "checkmark" : "copy-outline"} size={18} color={colors.brandDeep} />
            </Pressable>
          </View>
          <View style={s.codeRow}>
            <Text style={s.codeLabel}>OR SHARE YOUR CODE</Text>
            <Text style={s.codeText} testID="referral-code">{data.referral_code}</Text>
          </View>
        </View>

        {/* Share CTA */}
        <Pressable
          testID="referral-share"
          onPress={onShare}
          style={({ pressed }) => [s.cta, pressed && { opacity: 0.9 }]}
        >
          <Ionicons name="share-social" size={18} color="#0F0B08" />
          <Text style={s.ctaText}>Share invite</Text>
        </Pressable>

        {/* How it works */}
        <View style={s.stepsCard}>
          <Text style={s.stepsTitle}>How it works</Text>
          <Step n={1} title="You share your link" body="WhatsApp, iMessage, email — anywhere." />
          <Step n={2} title="A friend signs up" body="They tap your link, register and complete Stripe Identity KYC." />
          <Step
            n={3}
            title={`You both get £${data.reward_per_side_gbp.toFixed(0)} credit`}
            body="Applied automatically to service fees on your next transfers. No expiry."
          />
        </View>

        {/* Friend list */}
        <Text style={s.sectionTitle}>Your invites</Text>
        {data.referrals.length === 0 ? (
          <View style={s.emptyCard}>
            <Ionicons name="mail-outline" size={22} color={colors.onSurfaceTertiary} />
            <Text style={s.emptyText}>
              No invites yet. Share your link above to get started.
            </Text>
          </View>
        ) : (
          data.referrals.map((r) => (
            <View key={r.id} style={s.friendRow} testID={`referral-friend-${r.id}`}>
              <View style={s.friendIcon}>
                <Ionicons
                  name={r.status === "credited" ? "checkmark-circle" : "time-outline"}
                  size={20}
                  color={r.status === "credited" ? colors.success : colors.onSurfaceTertiary}
                />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={s.friendEmail}>{r.friend_email_masked}</Text>
                <Text style={s.friendStatus}>
                  {r.status === "credited"
                    ? `Verified · +£${data.reward_per_side_gbp.toFixed(0)} credit`
                    : r.friend_kyc_status === "verified"
                      ? "Processing…"
                      : "Waiting on identity verification"}
                </Text>
              </View>
            </View>
          ))
        )}

        <Text style={s.footerNote}>
          Rewards apply once your friend completes identity verification. Credits are
          GBP-denominated and offset service fees on cross-border transfers automatically.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

function Step({ n, title, body }: { n: number; title: string; body: string }) {
  return (
    <View style={s.stepRow}>
      <View style={s.stepBubble}><Text style={s.stepNum}>{n}</Text></View>
      <View style={{ flex: 1 }}>
        <Text style={s.stepTitle}>{title}</Text>
        <Text style={s.stepBody}>{body}</Text>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  centered: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.md },
  errText: { color: colors.error, fontSize: 14 },

  headerBar: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: spacing.xl, paddingTop: spacing.sm, paddingBottom: spacing.md,
  },
  headerTitle: { fontSize: 17, fontWeight: "700", color: colors.onSurface },

  heroCard: {
    padding: spacing.lg,
    borderRadius: radius.lg,
    backgroundColor: colors.brandTertiary,
    borderWidth: 1,
    borderColor: "rgba(201,163,91,0.40)",
    alignItems: "center",
    gap: spacing.sm,
    marginBottom: spacing.lg,
  },
  heroTitle: { fontSize: 22, fontWeight: "800", color: colors.brandDeep, letterSpacing: -0.4, textAlign: "center" },
  heroBody: { fontSize: 13, color: colors.onSurfaceSecondary, textAlign: "center", lineHeight: 18, maxWidth: 340 },

  balanceRow: {
    flexDirection: "row",
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    marginBottom: spacing.lg,
    alignItems: "center",
  },
  balanceCell: { flex: 1, alignItems: "center" },
  balanceLabel: { fontSize: 11, color: colors.onSurfaceTertiary, letterSpacing: 0.4, textTransform: "uppercase", marginBottom: 4 },
  balanceValue: { fontSize: 22, fontWeight: "800", color: colors.onSurface, letterSpacing: -0.4 },
  balanceDivider: { width: 1, height: 30, backgroundColor: colors.border },

  linkCard: {
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    marginBottom: spacing.md,
  },
  linkLabel: { fontSize: 11, color: colors.onSurfaceTertiary, letterSpacing: 0.6, textTransform: "uppercase", marginBottom: spacing.sm },
  linkRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  linkText: { flex: 1, fontSize: 13, color: colors.onSurface, fontFamily: undefined },
  copyBtn: { padding: 6, borderRadius: 6, backgroundColor: colors.brandTertiary },
  codeRow: {
    marginTop: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    alignItems: "center",
  },
  codeLabel: { fontSize: 10, color: colors.onSurfaceTertiary, letterSpacing: 1, marginBottom: 4 },
  codeText: { fontSize: 24, fontWeight: "800", color: colors.brandDeep, letterSpacing: 4 },

  cta: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm,
    backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: 14,
    marginBottom: spacing.xl,
  },
  ctaText: { color: "#0F0B08", fontSize: 15, fontWeight: "700" },
  ctaSecondary: { borderRadius: radius.md, paddingHorizontal: 24, paddingVertical: 12, borderWidth: 1, borderColor: colors.border },
  ctaSecondaryText: { color: colors.onSurface, fontSize: 14, fontWeight: "600" },

  stepsCard: {
    padding: spacing.lg,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.xl,
    gap: spacing.md,
  },
  stepsTitle: { fontSize: 13, fontWeight: "700", color: colors.onSurface, marginBottom: 4 },
  stepRow: { flexDirection: "row", gap: spacing.md, alignItems: "flex-start" },
  stepBubble: { width: 26, height: 26, borderRadius: 13, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  stepNum: { color: colors.brandDeep, fontSize: 13, fontWeight: "800" },
  stepTitle: { color: colors.onSurface, fontSize: 13, fontWeight: "600" },
  stepBody: { color: colors.onSurfaceSecondary, fontSize: 12, lineHeight: 16, marginTop: 2 },

  sectionTitle: { fontSize: 13, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm, marginTop: spacing.sm },
  emptyCard: {
    padding: spacing.lg,
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: "dashed",
    borderColor: colors.border,
    alignItems: "center",
    gap: spacing.sm,
  },
  emptyText: { color: colors.onSurfaceSecondary, fontSize: 12, textAlign: "center", lineHeight: 17 },

  friendRow: {
    flexDirection: "row",
    gap: spacing.md,
    alignItems: "center",
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  friendIcon: { width: 32, alignItems: "center" },
  friendEmail: { color: colors.onSurface, fontSize: 13, fontWeight: "500" },
  friendStatus: { color: colors.onSurfaceTertiary, fontSize: 11, marginTop: 2 },

  footerNote: {
    color: colors.onSurfaceTertiary,
    fontSize: 10,
    textAlign: "center",
    marginTop: spacing.xl,
    lineHeight: 14,
  },
});
