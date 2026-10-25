/**
 * InviteCodeCard — view/change the shared beta invite code and switch the
 * sign-up gate on or off. Existing accounts are never affected.
 */
import { useEffect, useState } from "react";
import { View, Text, TextInput, Pressable, Switch, ActivityIndicator } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { colors } from "@/src/lib/theme";
import { s } from "./styles";

type Cfg = { enabled: boolean; code: string; signups_with_code: number };

export function InviteCodeCard() {
  const [cfg, setCfg] = useState<Cfg | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    api<Cfg>("/admin/invite").then((c) => { setCfg(c); setDraft(c.code); }).catch((e) => setMsg(e?.message || "Load failed"));
  }, []);

  const save = async (patch: Partial<Cfg>) => {
    setBusy(true);
    setMsg(null);
    try {
      const c = await api<Cfg>("/admin/invite", { method: "PUT", body: patch });
      setCfg(c);
      setDraft(c.code);
      if (patch.code) setMsg("Code updated");
    } catch (e: any) { setMsg(e?.message || "Save failed"); }
    finally { setBusy(false); }
  };

  const valid = /^[A-Za-z0-9-]{4,40}$/.test(draft.trim());

  return (
    <View style={s.card} testID="invite-code-card">
      <View style={s.cardHeaderRow}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Ionicons name="key-outline" size={18} color={colors.brand} />
          <Text style={s.cardTitle}>Beta invite code</Text>
        </View>
        {(busy || !cfg) && !msg && <ActivityIndicator color={colors.brand} />}
      </View>
      {cfg && (
        <>
          <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 8 }}>
            <Text style={{ flex: 1, fontSize: 13, color: colors.onSurfaceSecondary }}>
              Require a code for new sign-ups · {cfg.signups_with_code} joined with a code
            </Text>
            <Switch testID="invite-enabled-switch" value={cfg.enabled} disabled={busy}
              onValueChange={(v) => save({ enabled: v })} trackColor={{ true: colors.brand, false: colors.border }} />
          </View>
          <View style={{ flexDirection: "row", gap: 8, marginTop: 10 }}>
            <TextInput
              testID="invite-code-input"
              value={draft}
              onChangeText={(v) => setDraft(v.toUpperCase())}
              autoCapitalize="characters"
              autoCorrect={false}
              style={{ flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingHorizontal: 12, minHeight: 44, color: colors.onSurface, fontSize: 15, fontWeight: "700", letterSpacing: 1 }}
            />
            <Pressable
              testID="invite-code-save"
              onPress={() => save({ code: draft.trim() })}
              disabled={busy || !valid || draft.trim() === cfg.code}
              style={{ minWidth: 72, minHeight: 44, borderRadius: 10, alignItems: "center", justifyContent: "center", backgroundColor: colors.brand, opacity: busy || !valid || draft.trim() === cfg.code ? 0.5 : 1 }}
            >
              <Text style={{ color: colors.onBrand, fontWeight: "700" }}>Save</Text>
            </Pressable>
          </View>
          <Text style={{ fontSize: 11, color: colors.onSurfaceTertiary, marginTop: 6 }}>
            Letters, numbers and dashes, 4–40 characters. Not case-sensitive for testers.
          </Text>
        </>
      )}
      {!!msg && <Text style={{ fontSize: 12, color: msg === "Code updated" ? colors.success : colors.error, marginTop: 6 }}>{msg}</Text>}
    </View>
  );
}
