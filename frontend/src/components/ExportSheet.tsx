// Bottom-sheet UI for tax-ready CSV export.
// Talks to GET /api/transactions/export and saves the file via expo-file-system,
// then opens the native share sheet (works on iOS, Android, and falls back to
// a browser download on web).
import { useEffect, useState } from "react";
import {
  View, Text, StyleSheet, Pressable, ActivityIndicator, Modal, Platform,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import * as FileSystem from "expo-file-system/legacy";
import * as Sharing from "expo-sharing";
import { colors, spacing, radius } from "@/src/lib/theme";
import { useI18n } from "@/src/lib/i18n";
import { getToken } from "@/src/lib/api";

type Preset = "30d" | "this_year" | "last_year" | "all";
const ASSETS = ["BTC", "ETH", "USDC", "SOL"] as const;
const TYPES = ["send", "receive", "deposit", "withdraw"] as const;

function fmtISODate(d: Date) {
  return d.toISOString().slice(0, 10);
}
function rangeFor(preset: Preset): { from?: string; to?: string } {
  const now = new Date();
  if (preset === "30d") {
    const from = new Date(now); from.setDate(now.getDate() - 30);
    return { from: fmtISODate(from), to: fmtISODate(now) };
  }
  if (preset === "this_year") {
    return { from: `${now.getUTCFullYear()}-01-01`, to: fmtISODate(now) };
  }
  if (preset === "last_year") {
    const y = now.getUTCFullYear() - 1;
    return { from: `${y}-01-01`, to: `${y}-12-31` };
  }
  return {}; // all-time
}

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || "";

export function ExportSheet({
  visible, onClose,
}: { visible: boolean; onClose: () => void }) {
  const { t } = useI18n();
  const [preset, setPreset] = useState<Preset>("this_year");
  const [assets, setAssets] = useState<Set<string>>(new Set());
  const [types, setTypes] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [doneMsg, setDoneMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!visible) { setDoneMsg(null); setErr(null); }
  }, [visible]);

  const toggle = (set: Set<string>, value: string, setter: (s: Set<string>) => void) => {
    const next = new Set(set);
    if (next.has(value)) next.delete(value); else next.add(value);
    setter(next);
  };

  const exportNow = async () => {
    setErr(null); setDoneMsg(null); setBusy(true);
    try {
      const { from, to } = rangeFor(preset);
      const params = new URLSearchParams();
      if (from) params.set("date_from", from);
      if (to) params.set("date_to", to);
      if (assets.size > 0) params.set("assets", Array.from(assets).join(","));
      if (types.size > 0) params.set("types", Array.from(types).join(","));

      // Build URL — works both for relative (web preview) and absolute backend URL
      const base = BACKEND ? `${BACKEND}/api` : "/api";
      const url = `${base}/transactions/export?${params.toString()}`;

      // Auth header — same place auth.tsx stores the JWT
      const token = await getToken();
      const resp = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      if (!resp.ok) throw new Error(`Export failed (${resp.status})`);
      const text = await resp.text();
      const name = `vaulted-${preset}-${Date.now()}.csv`;

      if (Platform.OS === "web") {
        // Browser download path
        const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
        const dl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = dl; a.download = name; a.click();
        URL.revokeObjectURL(dl);
        setDoneMsg(t("export_downloaded"));
      } else {
        const fileUri = `${FileSystem.documentDirectory}${name}`;
        await FileSystem.writeAsStringAsync(fileUri, text, { encoding: FileSystem.EncodingType.UTF8 });
        const canShare = await Sharing.isAvailableAsync();
        if (canShare) {
          await Sharing.shareAsync(fileUri, {
            mimeType: "text/csv",
            dialogTitle: t("share_csv_dialog"),
            UTI: "public.comma-separated-values-text",
          });
          setDoneMsg(t("export_saved"));
        } else {
          setDoneMsg(`${t("export_saved")} ${fileUri}`);
        }
      }
    } catch (e: any) {
      setErr(e?.message ?? "Failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={s.backdrop} onPress={() => !busy && onClose()} />
      <View style={s.sheet} testID="export-sheet">
        <View style={s.handle} />
        <Text style={s.title}>{t("export_csv")}</Text>
        <Text style={s.hint}>{t("export_hint")}</Text>

        <Text style={s.label}>{t("date_range")}</Text>
        <View style={s.row}>
          {(["30d", "this_year", "last_year", "all"] as Preset[]).map((p) => (
            <Pressable
              key={p}
              testID={`preset-${p}`}
              onPress={() => setPreset(p)}
              style={[s.pill, preset === p && s.pillActive]}
            >
              <Text style={[s.pillText, preset === p && { color: "#0F0B08" }]}>{t(`range_${p}`)}</Text>
            </Pressable>
          ))}
        </View>

        <Text style={s.label}>{t("assets")} <Text style={s.optional}>({t("optional")})</Text></Text>
        <View style={s.row}>
          {ASSETS.map((a) => (
            <Pressable
              key={a}
              testID={`asset-${a}`}
              onPress={() => toggle(assets, a, setAssets)}
              style={[s.pill, assets.has(a) && s.pillActive]}
            >
              <Text style={[s.pillText, assets.has(a) && { color: "#0F0B08" }]}>{a}</Text>
            </Pressable>
          ))}
        </View>

        <Text style={s.label}>{t("type")} <Text style={s.optional}>({t("optional")})</Text></Text>
        <View style={s.row}>
          {TYPES.map((tp) => (
            <Pressable
              key={tp}
              testID={`type-${tp}`}
              onPress={() => toggle(types, tp, setTypes)}
              style={[s.pill, types.has(tp) && s.pillActive]}
            >
              <Text style={[s.pillText, types.has(tp) && { color: "#0F0B08" }]}>{t(`type_${tp}`)}</Text>
            </Pressable>
          ))}
        </View>

        {err ? <Text style={s.err}>{err}</Text> : null}
        {doneMsg ? <Text style={s.ok}><Ionicons name="checkmark-circle" size={13} color={colors.success} /> {doneMsg}</Text> : null}

        <Pressable
          testID="export-cta"
          onPress={exportNow}
          disabled={busy}
          style={[s.cta, busy && { opacity: 0.6 }]}
        >
          {busy
            ? <ActivityIndicator color="#0F0B08" />
            : (
              <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                <Ionicons name="download" size={18} color="#0F0B08" />
                <Text style={s.ctaText}>{t("export_csv")}</Text>
              </View>
            )}
        </Pressable>
        <Pressable onPress={() => !busy && onClose()} style={s.cancel}>
          <Text style={s.cancelText}>{t("cancel")}</Text>
        </Pressable>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: "rgba(15,11,8,0.55)" },
  sheet: {
    position: "absolute", left: 0, right: 0, bottom: 0,
    backgroundColor: colors.surface,
    borderTopLeftRadius: 24, borderTopRightRadius: 24,
    padding: spacing.xl, paddingBottom: Platform.OS === "ios" ? spacing.xxl + 8 : spacing.xl,
    borderTopWidth: 1, borderTopColor: "rgba(201,163,91,0.30)",
  },
  handle: { width: 40, height: 4, borderRadius: 2, backgroundColor: colors.borderStrong, alignSelf: "center", marginBottom: spacing.md },
  title: { fontSize: 20, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.3 },
  hint: { fontSize: 12, color: colors.onSurfaceSecondary, marginTop: 4, marginBottom: spacing.lg },
  label: { fontSize: 11, color: colors.brandDeep, fontWeight: "700", letterSpacing: 0.5, textTransform: "uppercase", marginTop: spacing.md, marginBottom: 6 },
  optional: { color: colors.onSurfaceTertiary, fontWeight: "500", fontSize: 10 },
  row: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  pill: {
    paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary, borderWidth: 1, borderColor: "rgba(201,163,91,0.40)",
  },
  pillActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  pillText: { fontSize: 12, color: colors.brandDeep, fontWeight: "700", letterSpacing: 0.2 },
  err: { color: colors.error, fontSize: 12, marginTop: spacing.md },
  ok: { color: colors.success, fontSize: 12, marginTop: spacing.md, flexDirection: "row", alignItems: "center" },
  cta: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: 14, alignItems: "center", marginTop: spacing.lg, shadowColor: colors.brand, shadowOpacity: 0.3, shadowRadius: 12, shadowOffset: { width: 0, height: 4 } },
  ctaText: { color: "#0F0B08", fontSize: 15, fontWeight: "700", letterSpacing: 0.3 },
  cancel: { paddingVertical: spacing.md, alignItems: "center", marginTop: 4 },
  cancelText: { color: colors.onSurfaceSecondary, fontSize: 14, fontWeight: "500" },
});
