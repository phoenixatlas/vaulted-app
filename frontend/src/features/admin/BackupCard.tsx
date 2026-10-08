/**
 * BackupCard — weekly Mongo snapshot config + manual trigger.
 * Mirrors the Weekly Digest card UX for consistency.
 */
import { useCallback, useEffect, useState } from "react";
import { View, Text, Pressable, TextInput, ActivityIndicator } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { colors, spacing } from "@/src/lib/theme";
import { s } from "./styles";

type BackupConfig = {
  enabled: boolean;
  recipients: string[];
  send_weekday: number;
  send_hour_utc: number;
  collections: string[];
  last_sent_at?: string | null;
  last_total_docs?: number | null;
  last_size_bytes?: number | null;
  last_sent_recipients?: string[];
  last_error?: string | null;
};

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function formatBytes(n: number): string {
  if (!n) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export function BackupCard() {
  const [cfg, setCfg] = useState<BackupConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [newRecipient, setNewRecipient] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const load = useCallback(async () => {
    try {
      setCfg(await api<BackupConfig>("/admin/backup/config"));
    } catch (e: any) {
      setMsg({ ok: false, text: e?.message || "Load failed" });
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const patch = useCallback(async (updates: Partial<BackupConfig>) => {
    setSaving(true);
    try {
      setCfg(await api<BackupConfig>("/admin/backup/config", { method: "POST", body: updates }));
    } catch (e: any) {
      setMsg({ ok: false, text: e?.message || "Save failed" });
    } finally {
      setSaving(false);
    }
  }, []);

  const addRecipient = () => {
    const e = newRecipient.trim();
    if (!e.includes("@") || !cfg) return;
    patch({ recipients: Array.from(new Set([...(cfg.recipients || []), e])) });
    setNewRecipient("");
  };
  const removeRecipient = (email: string) => {
    if (!cfg) return;
    patch({ recipients: cfg.recipients.filter((r) => r !== email) });
  };

  const runNow = useCallback(async () => {
    setRunning(true);
    setMsg(null);
    try {
      const r = await api<{ ok: boolean; total_docs: number; size_human: string; sent_to: string[]; errors: string[] }>(
        "/admin/backup/run-now",
        { method: "POST", body: {} }
      );
      if (r.ok) {
        setMsg({ ok: true, text: `✓ Backup emailed to ${r.sent_to.length} · ${r.total_docs.toLocaleString()} docs · ${r.size_human}` });
      } else {
        setMsg({ ok: false, text: `✗ ${r.errors?.join(", ") || "Backup failed"}` });
      }
      load();
    } catch (e: any) {
      setMsg({ ok: false, text: `✗ ${e?.message || "Backup failed"}` });
    } finally {
      setRunning(false);
    }
  }, [load]);

  if (loading) {
    return (
      <View style={s.card}>
        <Text style={s.cardTitle}>Weekly backup</Text>
        <View style={s.loadingBox}>
          <ActivityIndicator color={colors.brand} />
          <Text style={s.loadingText}>Loading…</Text>
        </View>
      </View>
    );
  }
  if (!cfg) {
    return (
      <View style={s.card}>
        <Text style={s.cardTitle}>Weekly backup</Text>
        <Text style={s.subtle}>Unavailable.</Text>
      </View>
    );
  }

  const nextSendLabel = `${WEEKDAYS[cfg.send_weekday]} · ${String(cfg.send_hour_utc).padStart(2, "0")}:00 UTC`;

  return (
    <View style={s.card}>
      <View style={s.cardHeaderRow}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Ionicons name="archive-outline" size={18} color={colors.brand} />
          <Text style={s.cardTitle}>Weekly backup</Text>
        </View>
        <View style={[s.modePill, cfg.enabled && cfg.recipients.length > 0 ? s.modePillReady : s.modePillMock]}>
          <Text style={s.modePillText}>
            {cfg.enabled && cfg.recipients.length > 0 ? "ARMED" : "OFF"}
          </Text>
        </View>
      </View>
      <Text style={s.subtle}>
        Gzipped JSON snapshot of {cfg.collections.length} collections emailed every week.
        One restore away from recovering if Mongo ever resets again.
      </Text>

      <Pressable onPress={() => patch({ enabled: !cfg.enabled })} disabled={saving} style={s.toolRow} hitSlop={6}>
        <Ionicons
          name={cfg.enabled ? "toggle" : "toggle-outline"}
          size={28}
          color={cfg.enabled ? colors.success : colors.onSurfaceTertiary}
        />
        <View style={{ flex: 1 }}>
          <Text style={s.toolTitle}>
            {cfg.enabled ? "Automatic backup is ON" : "Automatic backup is OFF"}
          </Text>
          <Text style={s.toolSub}>
            Next scheduled: {nextSendLabel}
            {cfg.last_sent_at ? ` · Last ${new Date(cfg.last_sent_at).toLocaleString()}` : " · Never run"}
          </Text>
        </View>
      </Pressable>

      {/* Weekday + hour */}
      <View>
        <Text style={s.inputLabel}>Day of week</Text>
        <View style={s.smokeCorridorRow}>
          {WEEKDAYS.map((d, i) => {
            const active = i === cfg.send_weekday;
            return (
              <Pressable
                key={d}
                onPress={() => !saving && patch({ send_weekday: i })}
                disabled={saving}
                style={[s.corridorPill, active && s.corridorPillActive]}
                hitSlop={4}
              >
                <Text style={[s.corridorPillText, active && s.corridorPillTextActive]}>{d}</Text>
              </Pressable>
            );
          })}
        </View>
      </View>
      <View style={{ marginTop: 6 }}>
        <Text style={s.inputLabel}>Hour (UTC)</Text>
        <TextInput
          value={String(cfg.send_hour_utc)}
          onChangeText={(v) => {
            const n = parseInt(v, 10);
            if (!Number.isNaN(n) && n >= 0 && n <= 23) {
              patch({ send_hour_utc: n });
            }
          }}
          keyboardType="numeric"
          style={[s.input, { width: 70 }]}
          editable={!saving}
        />
      </View>

      {/* Recipients */}
      <Text style={[s.microLabel, { marginTop: spacing.md }]}>RECIPIENTS</Text>
      <View style={{ gap: 4, marginTop: 6 }}>
        {cfg.recipients.length === 0 ? (
          <Text style={[s.subtle, { fontSize: 11 }]}>
            Add at least one email — backups are heavy, so keep this list tight.
          </Text>
        ) : null}
        {cfg.recipients.map((r) => (
          <View key={r} style={s.contactRow}>
            <Ionicons name="mail-outline" size={13} color={colors.brand} />
            <Text style={[s.contactName, { flex: 1 }]} numberOfLines={1}>{r}</Text>
            <Pressable onPress={() => removeRecipient(r)} hitSlop={6} disabled={saving}>
              <Ionicons name="close-circle" size={16} color={colors.onSurfaceTertiary} />
            </Pressable>
          </View>
        ))}
      </View>
      <View style={{ flexDirection: "row", gap: 6, marginTop: 8 }}>
        <TextInput
          value={newRecipient}
          onChangeText={setNewRecipient}
          placeholder="umar.sani@phoenix-atlas.com"
          placeholderTextColor={colors.onSurfaceTertiary}
          style={[s.input, { flex: 1 }]}
          autoCapitalize="none"
          keyboardType="email-address"
          onSubmitEditing={addRecipient}
        />
        <Pressable
          onPress={addRecipient}
          disabled={saving || !newRecipient.includes("@")}
          style={[s.downloadBtn, (!newRecipient.includes("@") || saving) && { opacity: 0.5 }]}
          hitSlop={6}
        >
          <Ionicons name="add" size={14} color={colors.brand} />
          <Text style={s.downloadBtnText}>Add</Text>
        </Pressable>
      </View>

      <Pressable
        onPress={runNow}
        disabled={running || cfg.recipients.length === 0}
        style={[s.sendBtn, (running || cfg.recipients.length === 0) && s.sendBtnDisabled]}
      >
        {running ? (
          <ActivityIndicator size="small" color={colors.onBrand} />
        ) : (
          <>
            <Ionicons name="cloud-upload" size={14} color={colors.onBrand} />
            <Text style={s.sendBtnText}>Run backup now</Text>
          </>
        )}
      </Pressable>
      {msg ? (
        <Text style={[s.sendResult, msg.ok ? s.sendResultOk : s.sendResultErr]}>{msg.text}</Text>
      ) : null}

      {/* Last-run summary */}
      {cfg.last_sent_at ? (
        <View style={{ marginTop: spacing.md, padding: 10, backgroundColor: colors.surfaceSecondary, borderRadius: 8 }}>
          <Text style={s.microLabel}>LAST RUN</Text>
          <View style={{ flexDirection: "row", gap: 14, marginTop: 6, flexWrap: "wrap" }}>
            <View><Text style={s.footerText}>Docs</Text><Text style={{ fontWeight: "700", color: colors.onSurface }}>{(cfg.last_total_docs ?? 0).toLocaleString()}</Text></View>
            <View><Text style={s.footerText}>Size</Text><Text style={{ fontWeight: "700", color: colors.onSurface }}>{formatBytes(cfg.last_size_bytes || 0)}</Text></View>
            <View><Text style={s.footerText}>Delivered</Text><Text style={{ fontWeight: "700", color: colors.onSurface }}>{cfg.last_sent_recipients?.length ?? 0}</Text></View>
          </View>
          {cfg.last_error ? (
            <Text style={[s.sendResult, s.sendResultErr, { marginTop: 6 }]}>{cfg.last_error}</Text>
          ) : null}
        </View>
      ) : null}

      {/* Collections list — hidden by default; shown via inline toggle to keep card small */}
      <Text style={[s.footerText, { marginTop: spacing.sm }]}>
        Includes: {cfg.collections.slice(0, 5).join(", ")}
        {cfg.collections.length > 5 ? ` +${cfg.collections.length - 5} more` : ""}
      </Text>
    </View>
  );
}
