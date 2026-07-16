/**
 * KycStatusBanner
 * =================
 * A contextual banner surfaced on Wallet / Send Money / Activity that
 * lets users track their identity-verification progress without having
 * to navigate to /kyc every time.
 *
 * Behaviour:
 *  - `not_started` / `verified`  → nothing rendered
 *  - `processing`                → 🟡 spinner + "We're reviewing your
 *    documents… usually 1-3 minutes", auto-polls every 12s and
 *    dismisses automatically when Stripe returns a terminal state.
 *  - `requires_input`            → 🟠 "Action needed" card, one-tap
 *    to /kyc where the user can restart the flow via `force_new`.
 *
 * Design decisions:
 *  - Auto-polls only when mounted AND status is processing — no wasted
 *    calls when the user is verified.
 *  - Silently swallows load errors so a transient /kyc/status failure
 *    never breaks the parent screen.
 *  - Renders a compact, low-noise footprint (56px tall max) that fits
 *    above the existing headers on Wallet / Send Money / Activity.
 *  - Fully honours the app's brand-gold + inverse-surface palette.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { View, Text, Pressable, StyleSheet, ActivityIndicator, Platform } from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { colors, spacing, radius } from "@/src/lib/theme";

type KycStatus =
  | "not_started"
  | "requires_input"
  | "processing"
  | "verified"
  | "canceled";

type KycStatusResp = {
  identity_verification_status: KycStatus;
  tier?: string;
  identity_last_error?: { code?: string; reason?: string } | null;
};

// Poll interval while status === "processing". Chose 12s because Stripe
// Identity verdicts typically settle within 30-90s — three polls covers
// the p95 case without hammering the API.
const PROCESSING_POLL_MS = 12_000;

// Minimum time between manual refreshes / focus events to avoid a
// storm when the user tab-switches quickly.
const MIN_REFRESH_INTERVAL_MS = 5_000;

export default function KycStatusBanner({ testID = "kyc-status-banner" }: { testID?: string }) {
  const router = useRouter();
  const [status, setStatus] = useState<KycStatus | null>(null);
  const [lastError, setLastError] = useState<{ code?: string; reason?: string } | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const lastLoadedAt = useRef<number>(0);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    // Debounce — don't refetch if we just did.
    const now = Date.now();
    if (now - lastLoadedAt.current < MIN_REFRESH_INTERVAL_MS) return;
    lastLoadedAt.current = now;
    try {
      const s = await api<KycStatusResp>("/kyc/status");
      setStatus(s.identity_verification_status);
      setLastError(s.identity_last_error || null);
    } catch {
      // Silent — a KYC-status fetch failure should not break the parent
      // screen. The banner just stays hidden until the next mount.
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Auto-poll while processing so the banner dismisses itself the
  // moment Stripe returns a verdict.
  useEffect(() => {
    if (pollTimer.current) {
      clearInterval(pollTimer.current);
      pollTimer.current = null;
    }
    if (status === "processing") {
      pollTimer.current = setInterval(() => {
        lastLoadedAt.current = 0; // bypass debounce during active poll
        load();
      }, PROCESSING_POLL_MS);
    }
    return () => {
      if (pollTimer.current) {
        clearInterval(pollTimer.current);
        pollTimer.current = null;
      }
    };
  }, [status, load]);

  // Nothing to show for non-actionable states.
  if (dismissed) return null;
  if (!status || status === "not_started" || status === "verified" || status === "canceled") {
    return null;
  }

  const isProcessing = status === "processing";
  const isRequiresInput = status === "requires_input";
  const iconName = isProcessing ? "hourglass-outline" : "warning-outline";
  const iconColor = isProcessing ? colors.brand : "#E0735F";
  const bg = isProcessing ? "rgba(201,163,91,0.10)" : "rgba(224,115,95,0.10)";
  const border = isProcessing ? "rgba(201,163,91,0.35)" : "rgba(224,115,95,0.45)";
  const title = isProcessing ? "Verifying your ID" : "Action needed to complete verification";
  const subtitle = isProcessing
    ? "We're reviewing your documents. Usually takes 1–3 minutes."
    : (lastError?.reason
        ? `${humanizeError(lastError)} Tap to retry.`
        : "Your documents couldn't be verified. Tap to retry.");
  const cta = isProcessing ? undefined : "Fix now";

  return (
    <Pressable
      testID={testID}
      onPress={isRequiresInput ? () => router.push({ pathname: "/kyc", params: { reason: "requires_input" } }) : undefined}
      // Only make the whole card pressable when there's an action.
      style={({ pressed }) => [
        s.wrap,
        { backgroundColor: bg, borderColor: border },
        pressed && isRequiresInput && { opacity: 0.85 },
      ]}
      accessibilityRole={isRequiresInput ? "button" : undefined}
      accessibilityLabel={`${title}. ${subtitle}`}
    >
      <View style={s.iconWrap}>
        {isProcessing ? (
          <ActivityIndicator color={iconColor} size="small" />
        ) : (
          <Ionicons name={iconName as any} size={22} color={iconColor} />
        )}
      </View>
      <View style={s.body}>
        <Text style={[s.title, { color: iconColor }]} numberOfLines={1}>{title}</Text>
        <Text style={s.subtitle} numberOfLines={2}>{subtitle}</Text>
      </View>
      {cta && (
        <View style={s.ctaChip}>
          <Text style={s.ctaText}>{cta}</Text>
          <Ionicons name="chevron-forward" size={14} color={iconColor} />
        </View>
      )}
      {/* Dismiss X only while processing — requires_input must stay sticky */}
      {isProcessing && (
        <Pressable
          testID={`${testID}-dismiss`}
          onPress={() => setDismissed(true)}
          hitSlop={10}
          style={s.dismiss}
        >
          <Ionicons name="close" size={16} color={colors.onSurfaceTertiary} />
        </Pressable>
      )}
    </Pressable>
  );
}

// Turn Stripe's verbose reason codes into a one-line human sentence.
function humanizeError(err: { code?: string; reason?: string }): string {
  const code = (err.code || "").toLowerCase();
  const reason = err.reason || "";
  if (code.includes("document_expired")) return "Your ID document has expired.";
  if (code.includes("document_unverified_other") || code.includes("document_type_not_supported")) {
    return "Try a different form of ID.";
  }
  if (code.includes("selfie") || code.includes("face")) return "Selfie didn't match your ID.";
  if (code.includes("document_photo") || code.includes("image_quality")) return "Your photo was too blurry.";
  if (code.includes("consent")) return "Verification consent was cancelled.";
  return reason.length > 80 ? reason.slice(0, 78) + "…" : reason;
}

const s = StyleSheet.create({
  wrap: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    marginHorizontal: spacing.xl,
    marginTop: spacing.sm,
    marginBottom: spacing.xs,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    minHeight: 56,
    // Subtle elevation on Android; iOS gets a hairline shadow via border.
    ...Platform.select({
      android: { elevation: 1 },
      default: {},
    }),
  },
  iconWrap: {
    width: 28, height: 28,
    alignItems: "center", justifyContent: "center",
  },
  body: { flex: 1 },
  title: { fontSize: 13, fontWeight: "700", letterSpacing: 0.2 },
  subtitle: { fontSize: 12, color: colors.onSurfaceSecondary, marginTop: 2, lineHeight: 16 },
  ctaChip: {
    flexDirection: "row", alignItems: "center", gap: 2,
    paddingHorizontal: 10, paddingVertical: 5,
    borderRadius: 999,
    backgroundColor: "rgba(224,115,95,0.14)",
  },
  ctaText: { fontSize: 11, fontWeight: "700", color: "#E0735F", letterSpacing: 0.3 },
  dismiss: {
    padding: 4, marginLeft: 4,
  },
});
