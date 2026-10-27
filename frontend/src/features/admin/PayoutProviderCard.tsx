/**
 * PayoutProviderCard
 * ==================
 * Switch the active payout partner (Kotani Pay ↔ Yellow Card), toggle Beta
 * test-money mode, and see whether each partner currently accepts our key.
 */
import { useCallback, useEffect, useState } from "react";
import { View, Text, Pressable, ActivityIndicator, Switch } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { colors } from "@/src/lib/theme";
import { s } from "./styles";

type Provider = "flutterwave" | "kotani" | "yellowcard";
type ProviderInfo = {
  label: string;
  config: { mode: string; base_url: string; api_key_configured: boolean };
  probe: { ok: boolean; detail: string };
  countries: string[];
};
type Data = {
  settings: { provider: Provider; beta_test_mode: boolean };
  stripe_mode: "test" | "live" | "off";
  providers: Record<Provider, ProviderInfo>;
};

export function PayoutProviderCard() {
  const [data, setData] = useState<Data | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setErr(null);
    try { setData(await api<Data>("/admin/payouts")); }
    catch (e: any) { setErr(e?.message || "Load failed"); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const save = async (patch: Partial<Data["settings"]>) => {
    setSaving(true);
    try {
      await api("/admin/payouts", { method: "PUT", body: patch });
      await load();
    } catch (e: any) { setErr(e?.message || "Save failed"); }
    finally { setSaving(false); }
  };

  return (
    <View style={s.card} testID="payout-provider-card">
      <View style={s.cardHeaderRow}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Ionicons name="swap-horizontal" size={18} color={colors.brand} />
          <Text style={s.cardTitle}>Payout partner</Text>
        </View>
        {(saving || (!data && !err)) && <ActivityIndicator color={colors.brand} />}
      </View>

      {err && (
        <View style={s.errorBox}>
          <Ionicons name="alert-circle-outline" size={18} color={colors.error} />
          <Text style={s.errorText}>{err}</Text>
        </View>
      )}

      {data && (
        <>
          {(Object.keys(data.providers) as Provider[]).map((p) => {
            const info = data.providers[p];
            const active = data.settings.provider === p;
            return (
              <Pressable
                key={p}
                testID={`payout-provider-${p}`}
                disabled={saving || active}
                onPress={() => save({ provider: p })}
                style={{
                  borderWidth: 1.5, borderRadius: 12, padding: 12, marginTop: 10,
                  borderColor: active ? colors.brand : colors.border,
                  backgroundColor: active ? colors.brandTertiary : "transparent",
                }}
              >
                <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
                  <Text style={{ fontSize: 15, fontWeight: "700", color: colors.onSurface }}>{info.label}</Text>
                  <Text style={{ fontSize: 11, fontWeight: "800", color: active ? colors.brandDeep : colors.onSurfaceTertiary }}>
                    {active ? "ACTIVE" : "TAP TO USE"}
                  </Text>
                </View>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginTop: 6 }}>
                  <Ionicons
                    name={info.probe.ok ? "checkmark-circle" : "close-circle"}
                    size={14}
                    color={info.probe.ok ? colors.success : colors.error}
                  />
                  <Text style={{ flex: 1, fontSize: 12, color: colors.onSurfaceSecondary }} numberOfLines={2}>
                    {info.probe.ok ? `Connected — ${info.probe.detail}` : info.probe.detail}
                  </Text>
                </View>
                <Text style={{ fontSize: 11, color: colors.onSurfaceTertiary, marginTop: 4 }}>
                  Pays out to: {info.countries.join(", ")} · {info.config.api_key_configured ? "key saved" : "no key yet"}
                </Text>
              </Pressable>
            );
          })}

          <View style={s.divider} />
          <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 14, fontWeight: "700", color: colors.onSurface }}>Beta test-money mode</Text>
              <Text style={{ fontSize: 12, color: colors.onSurfaceSecondary, marginTop: 2 }}>
                No real money moves. Blocked partners fall back to a labelled test payout.
              </Text>
            </View>
            <Switch
              testID="beta-test-mode-switch"
              value={data.settings.beta_test_mode}
              disabled={saving}
              onValueChange={(v) => save({ beta_test_mode: v })}
              trackColor={{ true: colors.brand, false: colors.border }}
            />
          </View>
          <View style={s.diagRow}>
            <Text style={s.diagLabel}>Card payments (Stripe)</Text>
            <Text style={[s.diagValue, data.stripe_mode === "live" ? s.diagValueMissing : s.diagValueOk]}>
              {data.stripe_mode === "live"
                ? data.settings.beta_test_mode ? "live key — paused for beta" : "LIVE"
                : data.stripe_mode}
            </Text>
          </View>
        </>
      )}
    </View>
  );
}
