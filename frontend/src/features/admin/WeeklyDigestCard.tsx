/**
 * WeeklyDigestCard — manages the Monday-morning operations email.
 * Lets operators toggle it on/off, maintain the recipient list, preview
 * the next send and fire a one-off dispatch for testing. Pairs with
 * `/api/admin/digest/*` on the backend.
 */
import { useCallback, useEffect, useState } from "react";
import {
  View, Text, Pressable, TextInput, ActivityIndicator, Platform,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { colors, spacing } from "@/src/lib/theme";
import { s } from "./styles";

type DigestConfig = {
  enabled: boolean;
  recipients: string[];
  send_weekday: number;
  send_hour_utc: number;
  last_sent_at?: string | null;
  last_error?: string | null;
  last_sent_summary?: {
    period_start: string;
    period_end: string;
    tx_settled: number;
    tx_pending: number;
    usd_equivalent: number;
    waitlist_new: number;
    waitlist_total: number;
    usecase_sends: number;
    usecase_opens: number;
    kotani_ready: boolean;
  } | null;
};

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function WeeklyDigestCard() {
  const [cfg, setCfg] = useState<DigestConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [sending, setSending] = useState(false);
  const [sendMsg, setSendMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [newRecipient, setNewRecipient] = useState("");

  const load = useCallback(async () => {
    try {
      const data = await api<DigestConfig>("/admin/digest/config");
      setCfg(data);
    } catch (e: any) {
      setSendMsg({ ok: false, text: e?.message || "Load failed" });
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const patch = useCallback(async (updates: Partial<DigestConfig>) => {
    setSaving(true);
    try {
      const data = await api<DigestConfig>("/admin/digest/config", { method: "POST", body: updates });
      setCfg(data);
    } catch (e: any) {
      setSendMsg({ ok: false, text: e?.message || "Save failed" });
    } finally {
      setSaving(false);
    }
  }, []);

  const addRecipient = useCallback(() => {
    const t = newRecipient.trim();
    if (!t.includes("@") || !cfg) return;
    const list = Array.from(new Set([...(cfg.recipients || []), t]));
    patch({ recipients: list });
    setNewRecipient("");
  }, [newRecipient, cfg, patch]);

  const removeRecipient = useCallback((email: string) => {
    if (!cfg) return;
    patch({ recipients: cfg.recipients.filter((r) => r !== email) });
  }, [cfg, patch]);

  const sendNow = useCallback(async () => {
    setSending(true);
    setSendMsg(null);
    try {
      const res = await api<{ ok: boolean; sent_to: string[]; errors: string[]; subject: string }>(
        "/admin/digest/send-now",
        { method: "POST", body: {} }
      );
      if (res.ok && res.sent_to.length > 0) {
        setSendMsg({ ok: true, text: `✓ Delivered to ${res.sent_to.length} recipient(s): ${res.sent_to.join(", ")}` });
        load();
      } else if (res.errors?.length) {
        setSendMsg({ ok: false, text: `✗ Failed for: ${res.errors.join(", ")}` });
      } else {
        setSendMsg({ ok: false, text: "No recipients configured — add at least one email first." });
      }
    } catch (e: any) {
      setSendMsg({ ok: false, text: `✗ ${e?.message || "Send failed"}` });
    } finally {
      setSending(false);
    }
  }, [load]);

  const openPreview = useCallback(() => {
    // The /admin/digest/preview endpoint returns JSON with an html string.
    // Easiest on web: open a data URL. On native: alert the subject only.
    (async () => {
      try {
        const res = await api<{ subject: string; html: string }>("/admin/digest/preview");
        if (Platform.OS === "web" && typeof window !== "undefined") {
          const w = window.open("", "_blank");
          if (w) {
            w.document.open();
            w.document.write(res.html);
            w.document.close();
          }
        } else {
          setSendMsg({ ok: true, text: `Preview subject: ${res.subject}` });
        }
      } catch (e: any) {
        setSendMsg({ ok: false, text: e?.message || "Preview failed" });
      }
    })();
  }, []);

  if (loading) {
    return (
      <View style={s.card}>
        <Text style={s.cardTitle}>Weekly digest</Text>
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
        <Text style={s.cardTitle}>Weekly digest</Text>
        <Text style={s.subtle}>Unavailable.</Text>
      </View>
    );
  }

  const nextSendLabel = `${WEEKDAYS[cfg.send_weekday]} · ${String(cfg.send_hour_utc).padStart(2, "0")}:00 UTC`;
  const lastSentLabel = cfg.last_sent_at
    ? new Date(cfg.last_sent_at).toLocaleString()
    : "Never";

  return (
    <View style={s.card}>
      <View style={s.cardHeaderRow}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Ionicons name="mail-unread-outline" size={18} color={colors.brand} />
          <Text style={s.cardTitle}>Weekly digest</Text>
        </View>
        <View style={[s.modePill, cfg.enabled ? s.modePillReady : s.modePillMock]}>
          <Text style={s.modePillText}>{cfg.enabled ? "ARMED" : "PAUSED"}</Text>
        </View>
      </View>
      <Text style={s.subtle}>
        Monday-morning operations summary — settlements, outstanding tx, Kotani
        health, waitlist delta and partner-use-case engagement delivered to your
        inbox so you start the week with the numbers already in hand.
      </Text>

      {/* Enabled toggle + schedule */}
      <View style={{ marginTop: spacing.md, gap: 8 }}>
        <Pressable
          onPress={() => patch({ enabled: !cfg.enabled })}
          disabled={saving}
          style={s.toolRow}
          hitSlop={6}
        >
          <Ionicons
            name={cfg.enabled ? "toggle" : "toggle-outline"}
            size={28}
            color={cfg.enabled ? colors.success : colors.onSurfaceTertiary}
          />
          <View style={{ flex: 1 }}>
            <Text style={s.toolTitle}>
              {cfg.enabled ? "Automatic weekly send is ON" : "Automatic weekly send is OFF"}
            </Text>
            <Text style={s.toolSub}>
              Next scheduled: {nextSendLabel} · Last sent: {lastSentLabel}
            </Text>
          </View>
        </Pressable>

        {/* Weekday picker */}
        <View>
          <Text style={s.inputLabel}>Send day</Text>
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

        {/* Hour picker */}
        <View>
          <Text style={s.inputLabel}>Send hour (UTC)</Text>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
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
            <Text style={s.subtle}>
              {`${String(cfg.send_hour_utc).padStart(2, "0")}:00 UTC`} ·
              roughly 08:00 BST / 10:00 Nairobi
            </Text>
          </View>
        </View>
      </View>

      {/* Recipients */}
      <Text style={[s.microLabel, { marginTop: spacing.md }]}>RECIPIENTS</Text>
      <View style={{ marginTop: 6, gap: 4 }}>
        {(cfg.recipients || []).length === 0 ? (
          <Text style={s.subtle}>
            No recipients yet. Add at least one email below.
          </Text>
        ) : (
          cfg.recipients.map((r) => (
            <View key={r} style={s.contactRow}>
              <Ionicons name="mail-outline" size={14} color={colors.brand} />
              <Text style={[s.contactName, { flex: 1 }]} numberOfLines={1}>{r}</Text>
              <Pressable
                onPress={() => removeRecipient(r)}
                hitSlop={6}
                disabled={saving}
              >
                <Ionicons name="close-circle" size={16} color={colors.onSurfaceTertiary} />
              </Pressable>
            </View>
          ))
        )}
      </View>
      <View style={{ flexDirection: "row", gap: 6, marginTop: 8 }}>
        <TextInput
          value={newRecipient}
          onChangeText={setNewRecipient}
          placeholder="ops@phoenix-atlas.com"
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

      {/* Preview + Send now actions */}
      <View style={{ flexDirection: "row", gap: 8, marginTop: 14 }}>
        <Pressable
          onPress={openPreview}
          disabled={sending}
          style={[s.downloadBtn, { flex: 1, justifyContent: "center" }]}
          hitSlop={6}
        >
          <Ionicons name="eye-outline" size={14} color={colors.brand} />
          <Text style={s.downloadBtnText}>Preview</Text>
        </Pressable>
        <Pressable
          onPress={sendNow}
          disabled={sending || cfg.recipients.length === 0}
          style={[s.sendBtn, { flex: 2, marginTop: 0 }, (sending || cfg.recipients.length === 0) && s.sendBtnDisabled]}
        >
          {sending ? (
            <ActivityIndicator size="small" color={colors.onBrand} />
          ) : (
            <>
              <Ionicons name="paper-plane" size={14} color={colors.onBrand} />
              <Text style={s.sendBtnText}>Send digest now</Text>
            </>
          )}
        </Pressable>
      </View>

      {sendMsg ? (
        <Text style={[s.sendResult, sendMsg.ok ? s.sendResultOk : s.sendResultErr]}>
          {sendMsg.text}
        </Text>
      ) : null}

      {/* Last-sent summary */}
      {cfg.last_sent_summary ? (
        <View style={{ marginTop: spacing.md, padding: 10, backgroundColor: colors.surfaceSecondary, borderRadius: 8 }}>
          <Text style={s.microLabel}>LAST SENT SNAPSHOT</Text>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10, marginTop: 6 }}>
            <SummaryStat label="Settled" value={cfg.last_sent_summary.tx_settled} />
            <SummaryStat label="Pending" value={cfg.last_sent_summary.tx_pending} warn={cfg.last_sent_summary.tx_pending > 0} />
            <SummaryStat label="USD eq" value={`$${cfg.last_sent_summary.usd_equivalent.toLocaleString(undefined, { maximumFractionDigits: 0 })}`} />
            <SummaryStat label="New signups" value={`+${cfg.last_sent_summary.waitlist_new}`} />
            <SummaryStat label="Use-case sent" value={cfg.last_sent_summary.usecase_sends} />
            <SummaryStat label="Opened" value={cfg.last_sent_summary.usecase_opens} />
          </View>
        </View>
      ) : null}

      {cfg.last_error ? (
        <Text style={[s.sendResult, s.sendResultErr]}>Last error: {cfg.last_error}</Text>
      ) : null}
    </View>
  );
}

function SummaryStat({ label, value, warn }: { label: string; value: string | number; warn?: boolean }) {
  return (
    <View style={{ minWidth: 70 }}>
      <Text style={{ fontSize: 10, color: colors.onSurfaceTertiary, letterSpacing: 0.4, textTransform: "uppercase" }}>{label}</Text>
      <Text style={{ fontSize: 15, fontWeight: "800", color: warn ? colors.warning : colors.onSurface, marginTop: 2 }}>
        {value}
      </Text>
    </View>
  );
}
