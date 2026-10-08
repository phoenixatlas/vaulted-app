/**
 * SignupAlertCard — toggle operator notifications when someone joins
 * the waitlist. Minimal UI: enable/disable + recipient list.
 */
import { useCallback, useEffect, useState } from "react";
import { View, Text, Pressable, TextInput, ActivityIndicator } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { colors, spacing } from "@/src/lib/theme";
import { s } from "./styles";

type AlertConfig = {
  enabled: boolean;
  recipients: string[];
  has_env_default: boolean;
};

export function SignupAlertCard() {
  const [cfg, setCfg] = useState<AlertConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [newRecipient, setNewRecipient] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setCfg(await api<AlertConfig>("/admin/waitlist/alert-config"));
    } catch (e: any) {
      setErr(e?.message || "Load failed");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const patch = useCallback(async (updates: Partial<AlertConfig>) => {
    setSaving(true);
    try {
      setCfg(await api<AlertConfig>("/admin/waitlist/alert-config", { method: "POST", body: updates }));
      setErr(null);
    } catch (e: any) {
      setErr(e?.message || "Save failed");
    } finally {
      setSaving(false);
    }
  }, []);

  const add = () => {
    const e = newRecipient.trim();
    if (!e.includes("@") || !cfg) return;
    const list = Array.from(new Set([...(cfg.recipients || []), e]));
    patch({ recipients: list });
    setNewRecipient("");
  };
  const remove = (email: string) => {
    if (!cfg) return;
    patch({ recipients: cfg.recipients.filter((r) => r !== email) });
  };

  if (loading) {
    return (
      <View style={s.card}>
        <Text style={s.cardTitle}>Signup alerts</Text>
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
        <Text style={s.cardTitle}>Signup alerts</Text>
        <Text style={s.subtle}>{err || "Unavailable."}</Text>
      </View>
    );
  }

  return (
    <View style={s.card}>
      <View style={s.cardHeaderRow}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Ionicons name="notifications-outline" size={18} color={colors.brand} />
          <Text style={s.cardTitle}>Signup alerts</Text>
        </View>
        <View style={[s.modePill, cfg.enabled && cfg.recipients.length > 0 ? s.modePillReady : s.modePillMock]}>
          <Text style={s.modePillText}>
            {cfg.enabled && cfg.recipients.length > 0 ? "ARMED" : "OFF"}
          </Text>
        </View>
      </View>
      <Text style={s.subtle}>
        Receive an email the moment someone joins the waitlist — includes their corridor,
        direction, position, and referral code.
      </Text>

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
            {cfg.enabled ? "Alerts are ON" : "Alerts are OFF"}
          </Text>
          <Text style={s.toolSub}>
            {cfg.recipients.length > 0
              ? `Delivers to ${cfg.recipients.length} recipient${cfg.recipients.length !== 1 ? "s" : ""}`
              : "Add a recipient below to arm notifications"}
          </Text>
        </View>
      </Pressable>

      <Text style={[s.microLabel, { marginTop: spacing.sm }]}>RECIPIENTS</Text>
      <View style={{ gap: 4, marginTop: 6 }}>
        {cfg.recipients.length === 0 ? (
          <Text style={[s.subtle, { fontSize: 11 }]}>
            None yet. Add an email below.
          </Text>
        ) : null}
        {cfg.recipients.map((r) => (
          <View key={r} style={s.contactRow}>
            <Ionicons name="mail-outline" size={13} color={colors.brand} />
            <Text style={[s.contactName, { flex: 1 }]} numberOfLines={1}>{r}</Text>
            <Pressable onPress={() => remove(r)} hitSlop={6} disabled={saving}>
              <Ionicons name="close-circle" size={16} color={colors.onSurfaceTertiary} />
            </Pressable>
          </View>
        ))}
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
          onSubmitEditing={add}
        />
        <Pressable
          onPress={add}
          disabled={saving || !newRecipient.includes("@")}
          style={[s.downloadBtn, (!newRecipient.includes("@") || saving) && { opacity: 0.5 }]}
          hitSlop={6}
        >
          <Ionicons name="add" size={14} color={colors.brand} />
          <Text style={s.downloadBtnText}>Add</Text>
        </Pressable>
      </View>

      {err ? <Text style={[s.sendResult, s.sendResultErr]}>{err}</Text> : null}
    </View>
  );
}
