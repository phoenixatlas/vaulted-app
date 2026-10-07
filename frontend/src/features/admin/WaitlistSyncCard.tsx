/**
 * WaitlistSyncCard — reconciliation between Resend and Mongo.
 * ============================================================
 * Shipped when the admin dashboard was showing 0 waitlist signups while
 * Resend audiences actually contained several — classic ESP vs DB drift
 * from a mid-request restart or free-tier Mongo wipe.
 *
 * Capabilities:
 *   1. On mount, fetch /admin/waitlist/audit + /admin/waitlist/sync-config
 *      to show Mongo vs Resend counts, the gap and the nightly scheduler
 *      status.
 *   2. If a gap is detected, prominent "Import N missing signups" button
 *      that calls /admin/waitlist/sync-from-resend.
 *   3. Toggle + hour picker for the nightly auto-sync so operators never
 *      have to tap "Import" manually again.
 *   4. Shows last-run timestamp + recent run history (5 rows).
 */
import { useCallback, useEffect, useState } from "react";
import { View, Text, Pressable, TextInput, ActivityIndicator } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { colors, spacing } from "@/src/lib/theme";
import { s } from "./styles";

type AuditResp = {
  mongo_total: number;
  resend_total_unique: number;
  gap: number;
  missing_from_mongo_count: number;
  missing_from_mongo_sample: string[];
  missing_from_resend_count: number;
  resend_api_configured: boolean;
  audiences: {
    audience_id: string;
    audience_name: string;
    contacts_count: number;
    missing_from_mongo_count: number;
    sample_missing: string[];
  }[];
  audiences_count: number;
  checked_at: string;
};

type SyncResp = {
  ok: boolean;
  imported_count: number;
  skipped_count: number;
  new_mongo_total: number;
  audiences: { audience_id: string; audience_name: string; imported: number; contacts_total: number }[];
  sample_imported: { email: string; audience: string; corridor: string; direction: string }[];
};

type SyncConfig = {
  enabled: boolean;
  send_hour_utc: number;
  last_run_at: string | null;
  last_run_reason: string | null;
  last_imported_count: number | null;
  last_new_mongo_total: number | null;
  recent_runs: {
    ran_at: string;
    reason: string;
    imported_count: number;
    skipped_count: number;
    new_mongo_total: number;
  }[];
};

type Props = { onSynced?: () => void };

export function WaitlistSyncCard({ onSynced }: Props) {
  const [audit, setAudit] = useState<AuditResp | null>(null);
  const [config, setConfig] = useState<SyncConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [savingConfig, setSavingConfig] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [syncResult, setSyncResult] = useState<SyncResp | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const [a, c] = await Promise.all([
        api<AuditResp>("/admin/waitlist/audit"),
        api<SyncConfig>("/admin/waitlist/sync-config").catch(() => null),
      ]);
      setAudit(a);
      if (c) setConfig(c);
    } catch (e: any) {
      setErrorMsg(e?.message || "Audit failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const patchConfig = useCallback(async (updates: Partial<SyncConfig>) => {
    setSavingConfig(true);
    try {
      const next = await api<SyncConfig>("/admin/waitlist/sync-config", {
        method: "POST", body: updates,
      });
      setConfig(next);
    } catch (e: any) {
      setErrorMsg(e?.message || "Config save failed");
    } finally {
      setSavingConfig(false);
    }
  }, []);

  const runSync = useCallback(async () => {
    setSyncing(true);
    setErrorMsg(null);
    setSyncResult(null);
    try {
      const res = await api<SyncResp>("/admin/waitlist/sync-from-resend", {
        method: "POST", body: {},
      });
      setSyncResult(res);
      await loadAll();
      onSynced?.();
    } catch (e: any) {
      setErrorMsg(e?.message || "Sync failed");
    } finally {
      setSyncing(false);
    }
  }, [loadAll, onSynced]);

  if (loading && !audit) {
    return (
      <View style={s.card}>
        <View style={s.cardHeaderRow}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <Ionicons name="sync-outline" size={18} color={colors.brand} />
            <Text style={s.cardTitle}>Resend reconciliation</Text>
          </View>
        </View>
        <View style={s.loadingBox}>
          <ActivityIndicator color={colors.brand} />
          <Text style={s.loadingText}>Comparing Mongo vs Resend…</Text>
        </View>
      </View>
    );
  }

  if (!audit) {
    return (
      <View style={s.card}>
        <View style={s.cardHeaderRow}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <Ionicons name="sync-outline" size={18} color={colors.brand} />
            <Text style={s.cardTitle}>Resend reconciliation</Text>
          </View>
        </View>
        <Text style={s.subtle}>Unavailable. {errorMsg ? `(${errorMsg})` : ""}</Text>
      </View>
    );
  }

  const inSync = audit.gap === 0 && audit.missing_from_mongo_count === 0;
  const gap = audit.missing_from_mongo_count;
  const autoEnabled = config?.enabled ?? false;

  return (
    <View style={s.card}>
      <View style={s.cardHeaderRow}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Ionicons
            name={inSync ? "checkmark-circle" : "warning-outline"}
            size={18}
            color={inSync ? colors.success : colors.warning}
          />
          <Text style={s.cardTitle}>Resend reconciliation</Text>
        </View>
        <View style={[s.modePill, inSync ? s.modePillReady : s.modePillMock]}>
          <Text style={s.modePillText}>{inSync ? "IN SYNC" : "DRIFT"}</Text>
        </View>
      </View>

      {!audit.resend_api_configured ? (
        <Text style={s.subtle}>
          RESEND_API_KEY is not configured on this backend — cannot compare with Resend.
          Set it in Render env vars and redeploy.
        </Text>
      ) : (
        <>
          <Text style={s.subtle}>
            {inSync
              ? "Every Resend contact has a corresponding row in your Mongo waitlist. Dashboard counts are accurate."
              : `${gap} signup${gap !== 1 ? "s" : ""} present in Resend but missing from Mongo. ` +
                (autoEnabled
                  ? "The nightly auto-sync will pick these up — or import now."
                  : "The dashboard is under-counting until you import them.")}
          </Text>

          {/* Side-by-side counts */}
          <View style={s.miniStatsRow}>
            <View style={s.miniStat}>
              <Text style={s.miniStatNum}>{audit.mongo_total}</Text>
              <Text style={s.miniStatLabel}>Mongo</Text>
            </View>
            <View style={s.miniStat}>
              <Text style={s.miniStatNum}>{audit.resend_total_unique}</Text>
              <Text style={s.miniStatLabel}>Resend</Text>
            </View>
            <View style={s.miniStat}>
              <Text style={[s.miniStatNum, { color: gap > 0 ? colors.warning : colors.success }]}>
                {gap > 0 ? `+${gap}` : "0"}
              </Text>
              <Text style={s.miniStatLabel}>Missing</Text>
            </View>
          </View>

          {/* Sample of missing emails */}
          {audit.missing_from_mongo_sample.length > 0 ? (
            <>
              <Pressable
                onPress={() => setExpanded((v) => !v)}
                style={s.historyToggle}
                hitSlop={6}
              >
                <Text style={s.historyToggleText}>
                  {expanded ? "▾" : "▸"} First {audit.missing_from_mongo_sample.length} missing email
                  {audit.missing_from_mongo_sample.length !== 1 ? "s" : ""}
                </Text>
              </Pressable>
              {expanded ? (
                <View style={{ gap: 4, marginTop: 4 }}>
                  {audit.missing_from_mongo_sample.map((em) => (
                    <View key={em} style={s.contactRow}>
                      <Ionicons name="mail-outline" size={13} color={colors.onSurfaceTertiary} />
                      <Text style={[s.contactName, { flex: 1, fontWeight: "500" }]} numberOfLines={1}>{em}</Text>
                    </View>
                  ))}
                </View>
              ) : null}
            </>
          ) : null}

          {/* Audience-by-audience breakdown */}
          {audit.audiences.length > 0 ? (
            <View style={{ marginTop: spacing.md }}>
              <Text style={s.microLabel}>AUDIENCES</Text>
              <View style={{ gap: 4, marginTop: 6 }}>
                {audit.audiences.map((a) => (
                  <View key={a.audience_id} style={s.contactRow}>
                    <Ionicons name="people-outline" size={13} color={colors.brand} />
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <Text style={s.contactName} numberOfLines={1}>{a.audience_name}</Text>
                      <Text style={s.contactMeta}>
                        {a.contacts_count} contact{a.contacts_count !== 1 ? "s" : ""}
                        {a.missing_from_mongo_count > 0 ? ` · ${a.missing_from_mongo_count} missing` : " · all synced"}
                      </Text>
                    </View>
                  </View>
                ))}
              </View>
            </View>
          ) : (
            <Text style={[s.subtle, { marginTop: spacing.sm, fontSize: 11 }]}>
              No Resend audiences found. If you expect contacts to be there, check your RESEND_API_KEY matches the account hosting the audiences.
            </Text>
          )}

          {/* Nightly auto-sync config */}
          {config ? (
            <View style={{ marginTop: spacing.md, padding: 10, backgroundColor: colors.surfaceSecondary, borderRadius: 8 }}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                <Text style={s.microLabel}>NIGHTLY AUTO-SYNC</Text>
                <View style={[s.modePill, autoEnabled ? s.modePillReady : s.modePillMock]}>
                  <Text style={s.modePillText}>{autoEnabled ? "ARMED" : "PAUSED"}</Text>
                </View>
              </View>

              <Pressable
                onPress={() => patchConfig({ enabled: !autoEnabled })}
                disabled={savingConfig}
                style={{ flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 6, marginTop: 4 }}
                hitSlop={4}
              >
                <Ionicons
                  name={autoEnabled ? "toggle" : "toggle-outline"}
                  size={26}
                  color={autoEnabled ? colors.success : colors.onSurfaceTertiary}
                />
                <View style={{ flex: 1 }}>
                  <Text style={s.toolTitle}>
                    {autoEnabled ? "Running every night" : "Automatic sync is off"}
                  </Text>
                  <Text style={s.toolSub}>
                    {autoEnabled
                      ? `Imports any Resend contacts missing from Mongo at ${String(config.send_hour_utc).padStart(2, "0")}:00 UTC`
                      : "Enable to auto-import new Resend contacts every night"}
                  </Text>
                </View>
              </Pressable>

              <View style={{ flexDirection: "row", alignItems: "center", gap: 10, marginTop: 6 }}>
                <Text style={s.inputLabel}>Hour (UTC)</Text>
                <TextInput
                  value={String(config.send_hour_utc)}
                  onChangeText={(v) => {
                    const n = parseInt(v, 10);
                    if (!Number.isNaN(n) && n >= 0 && n <= 23) {
                      patchConfig({ send_hour_utc: n });
                    }
                  }}
                  keyboardType="numeric"
                  style={[s.input, { width: 60 }]}
                  editable={!savingConfig}
                />
                <Text style={[s.subtle, { fontSize: 11 }]}>
                  {`${String(config.send_hour_utc).padStart(2, "0")}:00 UTC`} ·
                  ~{String((config.send_hour_utc + 1) % 24).padStart(2, "0")}:00 BST ·
                  ~{String((config.send_hour_utc + 3) % 24).padStart(2, "0")}:00 Nairobi
                </Text>
              </View>

              {config.last_run_at ? (
                <Text style={[s.footerText, { marginTop: 8 }]}>
                  Last run · {new Date(config.last_run_at).toLocaleString()} ·
                  reason: {config.last_run_reason} ·
                  imported {config.last_imported_count ?? 0}
                </Text>
              ) : (
                <Text style={[s.footerText, { marginTop: 8 }]}>
                  Scheduler has not run yet — will fire at the next {String(config.send_hour_utc).padStart(2, "0")}:00 UTC window.
                </Text>
              )}

              {config.recent_runs.length > 0 ? (
                <>
                  <Pressable
                    onPress={() => setHistoryOpen((v) => !v)}
                    style={{ paddingVertical: 6, marginTop: 4 }}
                    hitSlop={4}
                  >
                    <Text style={s.disclosureBtn}>
                      {historyOpen ? "▾ Hide" : "▸ Show"} recent runs ({config.recent_runs.length})
                    </Text>
                  </Pressable>
                  {historyOpen ? (
                    <View style={{ gap: 4, marginTop: 2 }}>
                      {config.recent_runs.map((r, i) => (
                        <View key={i} style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                          <Ionicons
                            name="checkmark-circle-outline"
                            size={12}
                            color={colors.success}
                          />
                          <Text style={[s.footerText, { flex: 1 }]} numberOfLines={1}>
                            {new Date(r.ran_at).toLocaleString()} · {r.reason} ·
                            {" "}+{r.imported_count} new · total {r.new_mongo_total}
                          </Text>
                        </View>
                      ))}
                    </View>
                  ) : null}
                </>
              ) : null}
            </View>
          ) : null}

          {/* Action buttons */}
          <View style={{ flexDirection: "row", gap: 8, marginTop: spacing.md }}>
            <Pressable
              onPress={loadAll}
              disabled={loading || syncing}
              style={[s.downloadBtn, { flex: 1, justifyContent: "center" }, (loading || syncing) && { opacity: 0.5 }]}
              hitSlop={6}
            >
              <Ionicons name="refresh" size={14} color={colors.brand} />
              <Text style={s.downloadBtnText}>Re-check</Text>
            </Pressable>
            {gap > 0 ? (
              <Pressable
                onPress={runSync}
                disabled={syncing}
                style={[s.sendBtn, { flex: 2, marginTop: 0 }, syncing && s.sendBtnDisabled]}
              >
                {syncing ? (
                  <ActivityIndicator size="small" color={colors.onBrand} />
                ) : (
                  <>
                    <Ionicons name="cloud-download" size={14} color={colors.onBrand} />
                    <Text style={s.sendBtnText}>Import {gap} from Resend</Text>
                  </>
                )}
              </Pressable>
            ) : null}
          </View>

          {syncResult ? (
            <Text style={[s.sendResult, syncResult.ok ? s.sendResultOk : s.sendResultErr]}>
              ✓ Imported {syncResult.imported_count} new signup{syncResult.imported_count !== 1 ? "s" : ""}.
              Waitlist total is now {syncResult.new_mongo_total}.
            </Text>
          ) : null}
          {errorMsg ? (
            <Text style={[s.sendResult, s.sendResultErr]}>✗ {errorMsg}</Text>
          ) : null}

          <Text style={[s.footerText, { marginTop: spacing.sm, textAlign: "right" }]}>
            Last checked · {new Date(audit.checked_at).toLocaleString()}
          </Text>
        </>
      )}
    </View>
  );
}
