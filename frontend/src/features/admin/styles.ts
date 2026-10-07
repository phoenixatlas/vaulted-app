/**
 * Admin Dashboard — Shared StyleSheet
 * ====================================
 * One source of truth for every card style used across the admin screen.
 * Imported by individual card components in /src/features/admin/ as well
 * as the main orchestrator in /app/admin/index.tsx.
 *
 * Pulled verbatim from the original monolithic index.tsx so that the
 * refactor is purely organisational — zero visual changes.
 */
import { StyleSheet } from "react-native";
import { colors, spacing, radius } from "@/src/lib/theme";

export const s = StyleSheet.create({
  // Session-expired takeover
  expiredWrap: {
    flex: 1, alignItems: "center", justifyContent: "center",
    paddingHorizontal: 24, paddingBottom: 60,
  },
  expiredCard: {
    width: "100%", maxWidth: 420,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1, borderColor: colors.border,
    padding: 28, alignItems: "center",
  },
  expiredIcon: {
    width: 60, height: 60, borderRadius: 30,
    backgroundColor: colors.brand + "20",
    alignItems: "center", justifyContent: "center",
    marginBottom: 16,
  },
  expiredTitle: {
    fontSize: 20, fontWeight: "800", color: colors.onSurface,
    letterSpacing: -0.3, marginBottom: 10,
  },
  expiredBody: {
    fontSize: 13, color: colors.onSurfaceSecondary,
    lineHeight: 19, textAlign: "center", marginBottom: 22,
  },
  expiredBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
    paddingVertical: 11, paddingHorizontal: 24,
    backgroundColor: colors.brand,
    borderRadius: radius.md,
    minWidth: 180, minHeight: 44,
  },
  expiredBtnText: {
    color: colors.onBrand, fontSize: 14, fontWeight: "700", letterSpacing: 0.2,
  },
  expiredRetry: {
    fontSize: 12, color: colors.onSurfaceTertiary,
    textDecorationLine: "underline",
  },

  // PartnerUseCaseCard dispatcher
  inputLabel: {
    fontSize: 10, fontWeight: "700", color: colors.onSurfaceSecondary,
    letterSpacing: 0.4, textTransform: "uppercase", marginBottom: 4,
  },
  input: {
    paddingHorizontal: 10, paddingVertical: 8,
    borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.sm,
    backgroundColor: colors.surfaceSecondary,
    color: colors.onSurface,
    fontSize: 13,
  },
  disclosureBtn: {
    fontSize: 11.5, color: colors.brandDeep, fontWeight: "600",
    marginTop: 2, paddingVertical: 4,
  },
  sendBtn: {
    marginTop: 14,
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
    paddingVertical: 11, paddingHorizontal: 16,
    backgroundColor: colors.brand,
    borderRadius: radius.md,
    minHeight: 44,
  },
  sendBtnDisabled: {
    backgroundColor: colors.border,
    opacity: 0.7,
  },
  sendBtnText: {
    color: colors.onBrand, fontSize: 13.5, fontWeight: "700", letterSpacing: 0.2,
  },
  sendResult: { fontSize: 12, marginTop: 8, textAlign: "center" },
  sendResultOk: { color: colors.success, fontWeight: "600" },
  sendResultErr: { color: colors.error, fontWeight: "600" },
  downloadStrip: {
    flexDirection: "row", gap: 8, marginTop: 10, flexWrap: "wrap",
  },
  downloadBtn: {
    flexDirection: "row", alignItems: "center", gap: 5,
    paddingHorizontal: 10, paddingVertical: 6,
    borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary,
  },
  downloadBtnText: {
    fontSize: 11, color: colors.brand, fontWeight: "600", letterSpacing: 0.2,
  },
  historyToggle: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    paddingVertical: 8, paddingHorizontal: 2,
    marginTop: 10,
    borderTopWidth: 1, borderTopColor: colors.border,
  },
  historyToggleText: { fontSize: 12, fontWeight: "700", color: colors.onSurface },
  historyStat: { fontSize: 10.5, color: colors.onSurfaceSecondary },
  historyRow: {
    flexDirection: "row", alignItems: "center", gap: 10,
    paddingVertical: 7, paddingHorizontal: 10,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.sm,
  },
  historyRecipient: { fontSize: 12, fontWeight: "700", color: colors.onSurface },
  historyMeta: { fontSize: 10, color: colors.onSurfaceTertiary, marginTop: 2 },
  historyChip: {
    paddingHorizontal: 7, paddingVertical: 3,
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  historyChipText: { fontSize: 9.5, fontWeight: "800", letterSpacing: 0.3 },

  // Contact book
  contactRow: {
    flexDirection: "row", alignItems: "center", gap: 8,
    paddingVertical: 8, paddingHorizontal: 10,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.sm,
    marginTop: 4,
  },
  contactName: { fontSize: 12, fontWeight: "700", color: colors.onSurface },
  contactPrimary: { fontSize: 10, color: colors.brandDeep, fontWeight: "600" },
  contactMeta: { fontSize: 10.5, color: colors.onSurfaceTertiary, marginTop: 2 },

  // KotaniSmokeTestCard
  smokeCorridorRow: {
    flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 10,
  },
  corridorPill: {
    paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
    minWidth: 40, alignItems: "center",
  },
  corridorPillActive: {
    backgroundColor: colors.brand + "25",
    borderColor: colors.brand,
  },
  corridorPillText: { fontSize: 11, fontWeight: "700", color: colors.onSurfaceSecondary, letterSpacing: 0.5 },
  corridorPillTextActive: { color: colors.brandDeep },
  smokeStepRow: {
    flexDirection: "row", alignItems: "flex-start", gap: 10,
    paddingVertical: 8, paddingHorizontal: 10,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.sm,
    marginTop: 6,
  },
  smokeStepName: { fontSize: 12, fontWeight: "700", color: colors.onSurface },
  smokeStepCall: { fontSize: 10, color: colors.onSurfaceTertiary, fontFamily: "Menlo", marginTop: 1 },
  smokeStepDetail: { fontSize: 10.5, color: colors.onSurfaceSecondary, marginTop: 4, lineHeight: 14 },
  smokeStepError: { fontSize: 10.5, color: colors.error, marginTop: 4, lineHeight: 14 },
  smokeStepMs: { fontSize: 9.5, color: colors.onSurfaceTertiary, marginLeft: "auto" },
  smokeVerdictBox: {
    marginTop: 10, paddingHorizontal: 12, paddingVertical: 10,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  smokeVerdictGreen: {
    backgroundColor: colors.success + "15",
    borderColor: colors.success + "50",
  },
  smokeVerdictYellow: {
    backgroundColor: colors.warning + "15",
    borderColor: colors.warning + "50",
  },
  smokeVerdictRed: {
    backgroundColor: colors.error + "15",
    borderColor: colors.error + "50",
  },
  smokeVerdictTitle: { fontSize: 13, fontWeight: "800", color: colors.onSurface, letterSpacing: -0.2 },
  smokeVerdictText: { fontSize: 11.5, color: colors.onSurfaceSecondary, marginTop: 3, lineHeight: 16 },

  // KotaniSettlementsCard
  settleOverallGrid: {
    flexDirection: "row", flexWrap: "wrap", gap: 10, marginTop: 10,
  },
  settleStatBox: {
    flex: 1, minWidth: "47%",
    paddingHorizontal: 10, paddingVertical: 10,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.sm,
    borderWidth: 1, borderColor: colors.border,
  },
  settleStatLabel: { fontSize: 10, color: colors.onSurfaceTertiary, letterSpacing: 0.4, textTransform: "uppercase" },
  settleStatValue: { fontSize: 18, fontWeight: "800", color: colors.onSurface, marginTop: 3, letterSpacing: -0.3 },
  settleStatSub: { fontSize: 10, color: colors.onSurfaceSecondary, marginTop: 2 },
  settleRow: {
    paddingVertical: 10, paddingHorizontal: 10,
    borderTopWidth: 1, borderTopColor: colors.border,
  },
  settleDay: { fontSize: 11.5, fontWeight: "700", color: colors.onSurface },
  settleDaySub: { fontSize: 10.5, color: colors.onSurfaceSecondary, marginTop: 2 },
  settleReconRow: { flexDirection: "row", gap: 8, marginTop: 6, flexWrap: "wrap" },
  settleReconChip: {
    paddingHorizontal: 7, paddingVertical: 3,
    borderRadius: radius.sm,
    backgroundColor: colors.surface,
    borderWidth: 1, borderColor: colors.border,
  },
  settleReconChipText: { fontSize: 10, color: colors.onSurfaceSecondary, fontFamily: "Menlo" },
  settleReconChipWarn: { borderColor: colors.warning + "80", backgroundColor: colors.warning + "15" },

  container: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: "row", alignItems: "center", gap: 12,
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
    borderBottomWidth: 1, borderBottomColor: colors.divider,
  },
  backBtn: { padding: 4 },
  headerTitle: { fontSize: 20, fontWeight: "700", color: colors.onSurface },
  headerSub: { fontSize: 12, color: colors.onSurfaceSecondary, marginTop: 2 },

  scrollContent: { padding: spacing.lg, gap: spacing.md, paddingBottom: 48 },

  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
    borderWidth: 1, borderColor: colors.divider,
  },
  cardHeaderRow: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    marginBottom: spacing.sm,
  },
  cardTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface },

  modePill: {
    paddingHorizontal: 10, paddingVertical: 4,
    borderRadius: radius.pill,
  },
  modePillLive: { backgroundColor: colors.brand + "22", borderWidth: 1, borderColor: colors.brand },
  modePillMock: { backgroundColor: colors.onSurfaceTertiary + "22" },
  modePillReady: { backgroundColor: colors.success + "22", borderWidth: 1, borderColor: colors.success },
  modePillText: { fontSize: 10, fontWeight: "700", color: colors.onSurface, letterSpacing: 0.5 },

  loadingBox: { flexDirection: "row", alignItems: "center", gap: 8, padding: spacing.md },
  loadingText: { fontSize: 13, color: colors.onSurfaceSecondary },

  errorBox: {
    flexDirection: "row", alignItems: "center", gap: 8,
    padding: spacing.sm, backgroundColor: colors.error + "11",
    borderRadius: radius.sm, borderLeftWidth: 3, borderLeftColor: colors.error,
  },
  errorText: { fontSize: 12, color: colors.error, flex: 1 },

  diagRow: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    paddingVertical: 6, gap: 12,
  },
  diagLabel: { fontSize: 12, color: colors.onSurfaceSecondary },
  diagValue: { fontSize: 12, color: colors.onSurface, fontFamily: "Menlo", flex: 1, textAlign: "right" },
  diagValueOk: { color: colors.success },
  diagValueMissing: { color: colors.error },

  divider: { height: 1, backgroundColor: colors.divider, marginVertical: spacing.sm },
  probesHeader: {
    fontSize: 11, fontWeight: "700", color: colors.onSurfaceSecondary,
    letterSpacing: 0.5, marginBottom: 6, textTransform: "uppercase",
  },
  probeRow: {
    paddingVertical: 8,
    borderTopWidth: 1, borderTopColor: colors.divider + "80",
  },
  probeName: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  probeEndpoint: { fontSize: 10, color: colors.onSurfaceTertiary, fontFamily: "Menlo", marginLeft: 22 },
  probeDetail: { fontSize: 11, color: colors.onSurfaceSecondary, marginTop: 3, marginLeft: 22 },
  probeDetailFail: { color: colors.error },

  chip: {
    paddingHorizontal: 8, paddingVertical: 2,
    borderRadius: radius.pill,
    backgroundColor: colors.onSurfaceTertiary + "22",
  },
  chipBad: { backgroundColor: colors.error + "22" },
  chipText: { fontSize: 10, color: colors.onSurfaceSecondary, fontFamily: "Menlo" },
  chipTextBad: { color: colors.error },

  blockerBox: {
    backgroundColor: colors.brand + "10", borderRadius: radius.sm,
    padding: spacing.sm, marginTop: spacing.sm,
    borderLeftWidth: 3, borderLeftColor: colors.brand,
  },
  blockerText: { fontSize: 11.5, color: colors.brandDeep, flex: 1, lineHeight: 16 },
  mono: { fontFamily: "Menlo", fontSize: 11 },

  footerRow: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    marginTop: spacing.sm, paddingTop: spacing.sm,
    borderTopWidth: 1, borderTopColor: colors.divider,
  },
  footerText: { fontSize: 10, color: colors.onSurfaceTertiary },
  refreshBtn: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: 10, paddingVertical: 4,
    borderRadius: radius.pill,
    backgroundColor: colors.brand + "18",
  },
  refreshBtnText: { fontSize: 11, color: colors.brand, fontWeight: "600" },

  toolRow: {
    flexDirection: "row", alignItems: "center", gap: 10,
    paddingVertical: spacing.sm,
  },
  toolTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  toolSub: { fontSize: 11, color: colors.onSurfaceSecondary, marginTop: 2 },

  // Waitlist card
  totalPill: {
    paddingHorizontal: 10, paddingVertical: 4,
    borderRadius: radius.pill,
    backgroundColor: colors.brand + "18",
  },
  totalPillText: { fontSize: 11, color: colors.brand, fontWeight: "700", letterSpacing: 0.3 },
  emptyBox: {
    alignItems: "center", gap: 8, paddingVertical: spacing.md,
  },
  emptyText: { fontSize: 12, color: colors.onSurfaceSecondary, textAlign: "center" },

  corridorRow: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    marginBottom: 4, gap: 8,
  },
  corridorFlag: { fontSize: 14 },
  corridorName: { fontSize: 12.5, color: colors.onSurface, fontWeight: "600", flexShrink: 1 },
  corridorCode: {
    fontSize: 9.5, color: colors.onSurfaceTertiary,
    fontFamily: "Menlo", letterSpacing: 0.5,
  },
  corridorCount: { fontSize: 13, color: colors.onSurface, fontWeight: "700" },
  corridorPct: { fontSize: 10, color: colors.onSurfaceSecondary },
  barTrack: {
    height: 5, borderRadius: 3, overflow: "hidden",
    backgroundColor: colors.divider,
  },
  barFill: {
    height: "100%",
    backgroundColor: colors.brand,
    borderRadius: 3,
  },

  // InvestorLeadsCard extras
  pill: {
    paddingHorizontal: 10, paddingVertical: 4,
    borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
  },
  pillText: { fontSize: 10, fontWeight: "700", color: colors.onSurface, letterSpacing: 0.3 },
  subtle: { fontSize: 12, color: colors.onSurfaceSecondary, lineHeight: 16 },
  microLabel: {
    fontSize: 10, letterSpacing: 1.1,
    color: colors.onSurfaceTertiary, fontWeight: "700",
  },
  companyChip: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: 10, paddingVertical: 5,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    borderWidth: 1, borderColor: "rgba(201,163,91,0.35)",
  },
  companyChipName: { fontSize: 11, color: colors.onSurface, fontWeight: "600" },
  companyChipCount: { fontSize: 10, color: colors.brandDeep, fontWeight: "700" },
  leadRow: {
    flexDirection: "row", alignItems: "center", gap: 8,
    paddingVertical: 10,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.divider,
  },
  leadName: { fontSize: 13, color: colors.onSurface, fontWeight: "700" },
  leadRole: { color: colors.onSurfaceSecondary, fontWeight: "500", fontSize: 12 },
  leadEmail: { fontSize: 11, color: colors.onSurfaceSecondary, marginTop: 1 },
  leadNote: { fontSize: 11, color: colors.onSurfaceTertiary, marginTop: 4, fontStyle: "italic", lineHeight: 15 },
  leadBadge: {
    paddingHorizontal: 8, paddingVertical: 3,
    borderRadius: radius.pill,
    backgroundColor: colors.brand,
  },
  leadBadgeText: { fontSize: 10, fontWeight: "800", color: "#0F0B08" },

  // DailySignupsCard mini stats row
  miniStatsRow: {
    flexDirection: "row",
    gap: 12,
    marginTop: spacing.md,
    padding: 10,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border,
  },
  miniStat: { flex: 1, alignItems: "center" },
  miniStatNum: { fontSize: 18, fontWeight: "800", color: colors.onSurface, letterSpacing: -0.5 },
  miniStatLabel: { fontSize: 10, color: colors.onSurfaceSecondary, marginTop: 2, letterSpacing: 0.3, textAlign: "center" },

  // KotaniWebhookEchoCard
  webhookUrlBox: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.sm,
    padding: 10,
    borderWidth: 1, borderColor: colors.border,
  },
  webhookUrl: {
    flex: 1,
    fontSize: 11.5,
    fontFamily: "Menlo",
    color: colors.onSurface,
    lineHeight: 16,
  },
  copyBtn: {
    padding: 6,
    borderRadius: radius.sm,
    backgroundColor: colors.brand + "18",
  },
  checklistRow: { flexDirection: "row", alignItems: "center", gap: 8, paddingVertical: 3 },
  checklistText: { fontSize: 12, color: colors.onSurface, flex: 1 },
  eventChip: {
    paddingHorizontal: 8, paddingVertical: 4,
    borderRadius: radius.pill,
    backgroundColor: colors.brand + "15",
    borderWidth: 1, borderColor: colors.brand + "40",
  },
  eventChipText: { fontSize: 10, color: colors.brandDeep, fontFamily: "Menlo" },
  deliveryRow: {
    flexDirection: "row", alignItems: "center", gap: 8,
    paddingVertical: 6, paddingHorizontal: 8,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.sm,
  },
  deliveryEvent: { fontSize: 11.5, color: colors.onSurface, fontWeight: "600" },
  deliveryTime: { fontSize: 10, color: colors.onSurfaceTertiary, marginTop: 1 },

  // Host badge + warning
  hostBadge: {
    paddingHorizontal: 6, paddingVertical: 2,
    borderRadius: radius.pill,
    backgroundColor: colors.onSurfaceTertiary + "20",
    borderWidth: 1, borderColor: colors.border,
  },
  hostBadgeOk: {
    backgroundColor: colors.success + "20",
    borderColor: colors.success + "60",
  },
  hostBadgeWarn: {
    backgroundColor: colors.warning + "20",
    borderColor: colors.warning + "60",
  },
  hostBadgeErr: {
    backgroundColor: colors.error + "20",
    borderColor: colors.error + "60",
  },
  hostBadgeText: {
    fontSize: 9.5, fontWeight: "700", color: colors.onSurface, letterSpacing: 0.3,
  },
  hostWarnBox: {
    flexDirection: "row", gap: 6, alignItems: "flex-start",
    marginTop: 8, paddingHorizontal: 8, paddingVertical: 6,
    backgroundColor: colors.warning + "12",
    borderRadius: radius.sm,
    borderWidth: 1, borderColor: colors.warning + "35",
  },
  hostWarnText: { flex: 1, fontSize: 11, color: colors.onSurfaceSecondary, lineHeight: 15 },
});
