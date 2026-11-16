/** BillsReviewCard — approve / reject International Bill Payment requests. */
import { useEffect, useState } from "react";
import { View, Text, Pressable, ActivityIndicator, Linking } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { api, API_BASE, getToken } from "@/src/lib/api";
import { colors } from "@/src/lib/theme";
import { s } from "./styles";

type AdminBill = {
  id: string; reference: string; category: string; subtype: string; institution: string; beneficiary_name: string;
  user_email: string; status: string; created_at: string;
  quote: { payout_amount: number; payout_currency: string; total: number; payer_currency: string; provider: { label: string } };
  payee: { name: string; bank_name: string; account_number: string; routing?: string; swift?: string; reference: string };
};

export function BillsReviewCard() {
  const [rows, setRows] = useState<AdminBill[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = () => api<{ bills: AdminBill[] }>("/admin/bills").then((d) => setRows(d.bills)).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);

  const decide = async (id: string, approve: boolean) => {
    setBusy(id); setErr(null);
    try {
      await api(`/admin/bills/${id}/decision`, { method: "POST", body: { approve, note: approve ? "" : "Documentation could not be verified" } });
      await load();
    } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  };

  const openInvoice = async (id: string) => {
    // Web admin: open the invoice in a new tab with the auth token as a query-less fetch → blob URL.
    const token = await getToken();
    const r = await fetch(`${API_BASE}/api/admin/bills/${id}/invoice`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (!r.ok) { setErr("Could not open invoice"); return; }
    const blob = await r.blob();
    const url = (globalThis as any).URL?.createObjectURL?.(blob);
    if (url) Linking.openURL(url);
  };

  const pending = (rows || []).filter((r) => r.status === "under_review");
  return (
    <View style={s.card} testID="admin-bills-card">
      <View style={s.cardHeaderRow}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Ionicons name="document-text" size={18} color={colors.brand} />
          <Text style={s.cardTitle}>Bill payments · {pending.length} to review</Text>
        </View>
        {!rows && !err && <ActivityIndicator color={colors.brand} />}
      </View>
      {err && <Text style={{ color: colors.error, marginTop: 6 }}>{err}</Text>}
      {rows && rows.length === 0 && <Text style={{ color: colors.onSurfaceSecondary, marginTop: 8 }}>No requests yet.</Text>}
      {(rows || []).slice(0, 30).map((b) => (
        <View key={b.id} testID={`admin-bill-${b.id}`} style={{ borderTopWidth: 1, borderTopColor: colors.divider, paddingVertical: 10, marginTop: 8 }}>
          <Text style={{ fontSize: 15, fontWeight: "700", color: colors.onSurface }}>{b.institution} · {b.quote.payout_amount.toLocaleString()} {b.quote.payout_currency}</Text>
          <Text style={{ fontSize: 12, color: colors.onSurfaceSecondary, marginTop: 2 }}>
            {b.category} / {b.subtype} · {b.beneficiary_name} · {b.user_email} · {b.reference}
          </Text>
          <Text style={{ fontSize: 12, color: colors.onSurface, marginTop: 4 }}>
            Payee: {b.payee.name}, {b.payee.bank_name}, {b.payee.account_number} {b.payee.routing} {b.payee.swift} · Ref {b.payee.reference}
          </Text>
          <Text style={{ fontSize: 12, color: colors.onSurfaceSecondary, marginTop: 2 }}>
            Customer pays {b.quote.total.toLocaleString()} {b.quote.payer_currency} via {b.quote.provider.label} · {b.status}
          </Text>
          <View style={{ flexDirection: "row", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
            <Pressable testID={`admin-bill-invoice-${b.id}`} onPress={() => openInvoice(b.id)} style={btn(colors.border)}>
              <Text style={{ fontWeight: "700", color: colors.onSurface }}>View invoice</Text>
            </Pressable>
            {b.status === "under_review" && (
              <>
                <Pressable testID={`admin-bill-approve-${b.id}`} disabled={busy === b.id} onPress={() => decide(b.id, true)} style={btn(colors.success)}>
                  <Text style={{ fontWeight: "700", color: colors.success }}>Approve (test payout)</Text>
                </Pressable>
                <Pressable testID={`admin-bill-reject-${b.id}`} disabled={busy === b.id} onPress={() => decide(b.id, false)} style={btn(colors.error)}>
                  <Text style={{ fontWeight: "700", color: colors.error }}>Reject</Text>
                </Pressable>
              </>
            )}
            {busy === b.id && <ActivityIndicator color={colors.brand} />}
          </View>
        </View>
      ))}
    </View>
  );
}

const btn = (border: string) => ({ minHeight: 44, paddingHorizontal: 12, borderRadius: 10, borderWidth: 1, borderColor: border, justifyContent: "center" as const });
