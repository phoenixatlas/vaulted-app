/**
 * PartnerLeadsCard — enquiries from phoenix-atlas.com/business, with
 * New → Contacted → Closed status.
 */
import { useEffect, useState } from "react";
import { View, Text, Pressable, ActivityIndicator, Linking } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { colors } from "@/src/lib/theme";
import { s } from "./styles";

type Status = "new" | "contacted" | "closed";
type Lead = {
  id: string; name: string; email: string; company: string; partner_type: string;
  corridor: string; message?: string; status: Status; created_at: string;
};
const FILTERS: (Status | "all")[] = ["new", "contacted", "closed", "all"];
const LABEL: Record<Status, string> = { new: "New", contacted: "Contacted", closed: "Closed" };

export function PartnerLeadsCard() {
  const [rows, setRows] = useState<Lead[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState<Status | "all">("new");
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    api<{ enquiries: Lead[] }>("/admin/partners")
      .then((d) => setRows(d.enquiries))
      .catch((e) => setErr(e?.message || "Load failed"));
  }, []);

  const setStatus = async (id: string, status: Status) => {
    setBusyId(id);
    setErr(null);
    try {
      await api(`/admin/partners/${id}`, { method: "PATCH", body: { status } });
      setRows((prev) => prev?.map((r) => (r.id === id ? { ...r, status } : r)) ?? prev);
    } catch (e: any) {
      setErr(e?.message || "Update failed");
    } finally { setBusyId(null); }
  };

  const count = (f: Status | "all") => (rows || []).filter((r) => f === "all" || r.status === f).length;
  const shown = (rows || []).filter((r) => filter === "all" || r.status === filter);

  return (
    <View style={s.card} testID="admin-partner-leads-card">
      <View style={s.cardHeaderRow}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Ionicons name="briefcase" size={18} color={colors.brand} />
          <Text style={s.cardTitle}>Partner leads{rows ? ` · ${rows.length}` : ""}</Text>
        </View>
        {!rows && !err && <ActivityIndicator color={colors.brand} />}
      </View>
      {err && (
        <View style={s.errorBox}>
          <Ionicons name="alert-circle-outline" size={18} color={colors.error} />
          <Text style={s.errorText}>{err}</Text>
        </View>
      )}
      <View style={{ flexDirection: "row", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
        {FILTERS.map((f) => (
          <Pressable key={f} testID={`partner-filter-${f}`} onPress={() => setFilter(f)}
            style={{ minHeight: 44, paddingHorizontal: 14, borderRadius: 22, justifyContent: "center",
              backgroundColor: filter === f ? colors.brand : colors.brandTertiary }}>
            <Text style={{ fontSize: 12, fontWeight: "700", color: filter === f ? colors.onBrand : colors.brandDeep }}>
              {f === "all" ? "All" : LABEL[f]} · {count(f)}
            </Text>
          </Pressable>
        ))}
      </View>
      {rows && shown.length === 0 && (
        <Text style={{ color: colors.onSurfaceSecondary, marginTop: 10 }}>No {filter === "all" ? "" : LABEL[filter].toLowerCase() + " "}leads.</Text>
      )}
      {shown.map((r) => (
        <View key={r.id} testID={`partner-lead-${r.id}`} style={{ borderTopWidth: 1, borderTopColor: colors.divider, paddingVertical: 10, marginTop: 8 }}>
          <Text style={{ fontSize: 15, fontWeight: "700", color: colors.onSurface }}>{r.company}</Text>
          <Text style={{ fontSize: 13, color: colors.onSurfaceSecondary, marginTop: 2 }}>
            {r.corridor} · {r.partner_type.replace(/_/g, " ")}
          </Text>
          <Pressable testID={`partner-mailto-${r.id}`} style={{ minHeight: 44, justifyContent: "center" }}
            onPress={() => Linking.openURL(`mailto:${r.email}?subject=${encodeURIComponent("Vaulted partnership — " + r.company)}`)}>
            <Text style={{ fontSize: 13, color: colors.brandDeep, marginTop: 2 }}>{r.name} · {r.email}</Text>
          </Pressable>
          {!!r.message && <Text style={{ fontSize: 13, color: colors.onSurface, marginTop: 6 }}>{r.message}</Text>}
          <Text style={{ fontSize: 11, color: colors.onSurfaceTertiary, marginTop: 4 }}>{new Date(r.created_at).toLocaleString()}</Text>
          <View style={{ flexDirection: "row", gap: 8, marginTop: 8 }}>
            {(["new", "contacted", "closed"] as Status[]).map((st) => (
              <Pressable key={st} testID={`partner-status-${r.id}-${st}`} disabled={busyId === r.id || r.status === st}
                onPress={() => setStatus(r.id, st)}
                style={{ minHeight: 44, paddingHorizontal: 12, borderRadius: 10, justifyContent: "center", borderWidth: 1,
                  borderColor: r.status === st ? colors.brand : colors.border,
                  backgroundColor: r.status === st ? colors.brandTertiary : "transparent" }}>
                <Text style={{ fontSize: 12, fontWeight: "700", color: r.status === st ? colors.brandDeep : colors.onSurfaceSecondary }}>
                  {LABEL[st]}
                </Text>
              </Pressable>
            ))}
            {busyId === r.id && <ActivityIndicator color={colors.brand} />}
          </View>
        </View>
      ))}
    </View>
  );
}
