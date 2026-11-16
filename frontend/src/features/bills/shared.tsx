/** Shared bits for International Bill Payments screens. */
import { ReactNode } from "react";
import { View, Text, Pressable, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
import { colors, spacing, radius } from "@/src/lib/theme";

export type BillCategory = { id: string; label: string; tagline: string; subtypes: string[]; fields: { key: string; label: string }[] };
export type BillConfig = {
  categories: BillCategory[];
  payer_countries: { code: string; name: string; currency: string }[];
  payout_currencies: { code: string; country: string; rail: string; routing_label: string }[];
};
export type BillQuote = {
  id: string;
  payer_currency: string; payout_currency: string; payout_amount: number; mid_market_rate: number; rate: number;
  fx_margin_pct: number; principal: number; fee: number; total: number;
  provider: { label: string; mode: string; settlement: string }; rail: string; expires_at: string;
};
export type Bill = {
  id: string; reference: string; category: string; subtype: string; institution: string; beneficiary_name: string;
  status: string; created_at: string; quote: BillQuote; payee: { name: string; bank_name: string; reference: string };
  timeline: { at: string; label: string; status: string }[]; decision_note?: string;
};

export const CATEGORY_ICON: Record<string, keyof typeof Ionicons.glyphMap> = {
  education: "school-outline", healthcare: "medkit-outline", business: "briefcase-outline",
};
export const STATUS_LABEL: Record<string, string> = {
  under_review: "Under review", approved: "Approved", paid: "Paid (test)", rejected: "Rejected",
};

export const money = (n: number, cur: string) =>
  `${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${cur}`;

export function BillHeader({ title }: { title: string }) {
  return (
    <View style={bs.header}>
      <Pressable testID="bills-back" onPress={() => (router.canGoBack() ? router.back() : router.replace("/(tabs)/wallet"))} style={bs.back} hitSlop={8}>
        <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
      </Pressable>
      <Text style={bs.headerTitle}>{title}</Text>
    </View>
  );
}

export function TestModeBanner() {
  return (
    <View style={bs.banner} testID="bills-test-banner">
      <Ionicons name="flask-outline" size={16} color={colors.brandDeep} />
      <Text style={bs.bannerText}>Beta test mode — requests are reviewed and paid with test money only. No real funds move.</Text>
    </View>
  );
}

export function Chip({ label, active, onPress, testID }: { label: string; active: boolean; onPress: () => void; testID?: string }) {
  return (
    <Pressable testID={testID} onPress={onPress} style={[bs.chip, active && bs.chipActive]}>
      <Text style={[bs.chipText, active && bs.chipTextActive]}>{label}</Text>
    </Pressable>
  );
}

export function QuoteRow({ label, value, strong }: { label: string; value: ReactNode; strong?: boolean }) {
  return (
    <View style={bs.qRow}>
      <Text style={bs.qLabel}>{label}</Text>
      <Text style={[bs.qValue, strong && { fontWeight: "800", fontSize: 16 }]}>{value}</Text>
    </View>
  );
}

export const bs = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  back: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontSize: 20, fontWeight: "700", color: colors.onSurface },
  banner: { flexDirection: "row", gap: 8, backgroundColor: colors.brandTertiary, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.lg },
  bannerText: { flex: 1, fontSize: 12, color: colors.brandDeep },
  chip: { minHeight: 44, paddingHorizontal: 14, borderRadius: 22, borderWidth: 1, borderColor: colors.border, justifyContent: "center", backgroundColor: colors.surface },
  chipActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  chipText: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  chipTextActive: { color: "#0F0B08" },
  qRow: { flexDirection: "row", justifyContent: "space-between", gap: 12, paddingVertical: 6 },
  qLabel: { fontSize: 13, color: colors.onSurfaceSecondary, flexShrink: 1 },
  qValue: { fontSize: 14, color: colors.onSurface, fontWeight: "600", textAlign: "right", flexShrink: 1 },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, borderWidth: 1, borderColor: colors.border },
  section: { fontSize: 13, fontWeight: "700", color: colors.onSurfaceSecondary, textTransform: "uppercase", letterSpacing: 0.6, marginTop: spacing.xl, marginBottom: spacing.sm },
  input: { minHeight: 48, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, fontSize: 15, color: colors.onSurface, backgroundColor: colors.surface, marginBottom: spacing.sm },
  cta: { minHeight: 52, borderRadius: 26, backgroundColor: colors.brand, alignItems: "center", justifyContent: "center", marginTop: spacing.lg },
  ctaText: { color: "#0F0B08", fontWeight: "800", fontSize: 16 },
  err: { color: colors.error, fontSize: 13, marginTop: spacing.sm },
});
