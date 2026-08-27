/**
 * PreviewBanner
 * =============
 * A thin persistent banner that reminds users the current build is in
 * preview / waitlist mode ahead of FCA authorization.
 *
 * Used on:
 *  - Screens where users might commit real value (send, remit, fiat
 *    deposit, vault-pro subscription).
 *  - The wallet home so it's visible on every launch.
 *
 * Purpose: keeps the disclosure top-of-mind without dominating the UI.
 * Tapping the banner opens the full risk disclosure.
 */
import { Linking, Pressable, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, radius, spacing } from "@/src/lib/theme";

type Variant = "warning" | "info";

const RISK_DISCLOSURE_URL = "https://phoenix-atlas.com/risk-disclosure.html";

type Props = {
  message?: string;
  variant?: Variant;
  testID?: string;
};

const DEFAULT_MESSAGE =
  "Preview mode - Vaulted is not yet FCA authorized. Transactions may not settle to a real recipient. Tap to learn more.";

export default function PreviewBanner({
  message = DEFAULT_MESSAGE,
  variant = "warning",
  testID = "preview-banner",
}: Props) {
  const styles = variant === "warning" ? warningStyles : infoStyles;
  const iconColor = variant === "warning" ? WARN_ICON_COLOR : INFO_ICON_COLOR;
  return (
    <Pressable
      testID={testID}
      onPress={() => Linking.openURL(RISK_DISCLOSURE_URL).catch(() => undefined)}
      accessibilityRole="link"
      accessibilityLabel="Preview mode disclosure - tap to read risk disclosure"
      style={({ pressed }) => [styles.wrap, pressed && { opacity: 0.85 }]}
    >
      <Ionicons
        name={variant === "warning" ? "warning-outline" : "information-circle-outline"}
        size={14}
        color={iconColor}
      />
      <Text style={styles.text} numberOfLines={2}>
        {message}
      </Text>
      <Ionicons name="chevron-forward" size={14} color={iconColor} />
    </Pressable>
  );
}

const commonBase = {
  flexDirection: "row" as const,
  alignItems: "center" as const,
  gap: spacing.sm,
  paddingHorizontal: spacing.md,
  paddingVertical: 8,
  borderRadius: radius.md,
  marginHorizontal: spacing.lg,
  marginTop: spacing.md,
};

// StyleSheet.create rejects non-style keys, so the icon-tint color lives
// outside the sheet.
const WARN_ICON_COLOR = "#C9962A";
const INFO_ICON_COLOR = colors.brand;

const warningStyles = StyleSheet.create({
  wrap: {
    ...commonBase,
    backgroundColor: "#FFF6E6",
    borderWidth: 1,
    borderColor: "#F1D793",
  },
  text: {
    flex: 1,
    color: "#7A5A1F",
    fontSize: 11,
    lineHeight: 15,
    fontWeight: "500" as const,
  },
});

const infoStyles = StyleSheet.create({
  wrap: {
    ...commonBase,
    backgroundColor: colors.brandTertiary,
    borderWidth: 1,
    borderColor: colors.border,
  },
  text: {
    flex: 1,
    color: colors.brandDeep,
    fontSize: 11,
    lineHeight: 15,
    fontWeight: "500" as const,
  },
});

/**
 * Sub-variant used inline near amounts (send screen, remit quote) to make
 * clear the figure shown is illustrative, not a live settlement quote.
 */
export function IllustrativeNote({
  message = "Preview mode - amount and rate shown are examples, not a live settlement quote.",
  testID = "illustrative-note",
}: { message?: string; testID?: string }) {
  return (
    <View style={illStyles.wrap} testID={testID}>
      <Ionicons name="information-circle-outline" size={12} color={colors.onSurfaceTertiary} />
      <Text style={illStyles.text}>{message}</Text>
    </View>
  );
}

const illStyles = StyleSheet.create({
  wrap: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 6,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  text: {
    flex: 1,
    color: colors.onSurfaceTertiary,
    fontSize: 11,
    lineHeight: 15,
    fontStyle: "italic",
  },
});
