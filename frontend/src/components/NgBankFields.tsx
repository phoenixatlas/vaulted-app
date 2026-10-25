/**
 * NgBankFields — Nigeria bank payout details: pick a bank, enter the
 * 10-digit account number, and the account holder's name is looked up
 * automatically (Yellow Card; clearly marked test name until keys are set).
 */
import { useEffect, useMemo, useState } from "react";
import { View, Text, TextInput, Pressable, Modal, FlatList, ActivityIndicator, StyleSheet } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { colors, spacing, radius } from "@/src/lib/theme";

export type NgBank = { id: string; name: string; code?: string };
export type NgResolved = { name: string; test: boolean } | null;

// Extra search words so "Guaranty" finds GTBank, "United" finds UBA, etc.
const ALIASES: Record<string, string> = {
  "058": "guaranty trust", "033": "united bank for africa", "214": "first city monument",
  "221": "stanbic", "011": "firstbank", "50515": "moniepoint mfb", "999992": "paycom",
};

type Props = {
  bank: NgBank | null;
  account: string;
  onBank: (b: NgBank) => void;
  onAccount: (a: string) => void;
  onResolved: (r: NgResolved) => void;
};

export default function NgBankFields({ bank, account, onBank, onAccount, onResolved }: Props) {
  const [banks, setBanks] = useState<NgBank[]>([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<NgResolved>(null);
  const [lookupErr, setLookupErr] = useState("");

  useEffect(() => {
    api<{ banks: NgBank[] }>("/payouts/banks?country=NG").then((d) => setBanks(d.banks)).catch(() => setBanks([]));
  }, []);

  // Auto-check the account name once we have a bank + 10 digits.
  useEffect(() => {
    setResult(null);
    setLookupErr("");
    onResolved(null);
    if (!bank || account.length !== 10) return;
    let cancelled = false;
    setChecking(true);
    api<{ account_name: string; mode: string }>("/payouts/resolve-account", {
      method: "POST", body: { account_number: account, bank_id: bank.id },
    })
      .then((r) => {
        if (cancelled) return;
        const res = { name: r.account_name, test: r.mode !== "live" };
        setResult(res);
        onResolved(res);
      })
      .catch((e) => { if (!cancelled) setLookupErr(e?.status === 404 ? "We couldn't find this account. Check the number and bank." : "Name check unavailable right now — try again."); })
      .finally(() => { if (!cancelled) setChecking(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bank?.id, account]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return banks.filter((b) => (b.name + " " + (ALIASES[b.code || ""] || "")).toLowerCase().includes(q));
  }, [banks, search]);

  return (
    <View>
      <Text style={st.label}>Recipient's bank <Text style={{ color: colors.error }}>*</Text></Text>
      <Pressable testID="ng-bank-picker" onPress={() => setPickerOpen(true)} style={st.select}>
        <Text style={[st.selectText, !bank && { color: colors.onSurfaceTertiary }]}>{bank?.name || "Choose bank"}</Text>
        <Ionicons name="chevron-down" size={18} color={colors.onSurfaceSecondary} />
      </Pressable>

      <Text style={st.label}>Account number <Text style={{ color: colors.error }}>*</Text></Text>
      <TextInput
        testID="ng-account-number"
        value={account}
        onChangeText={(v) => onAccount(v.replace(/\D/g, "").slice(0, 10))}
        keyboardType="number-pad"
        placeholder="10-digit account number"
        placeholderTextColor={colors.onSurfaceTertiary}
        style={st.input}
      />

      {checking ? (
        <View style={st.resultRow}><ActivityIndicator size="small" color={colors.brand} /><Text style={st.muted}>Checking account name…</Text></View>
      ) : result ? (
        <View style={[st.resultRow, st.resultOk]} testID="ng-account-name">
          <Ionicons name="checkmark-circle" size={18} color={colors.success} />
          <View style={{ flex: 1 }}>
            <Text style={st.resolvedName}>{result.name}</Text>
            {result.test && <Text style={st.muted}>Test name — real names show once the payout partner is connected.</Text>}
          </View>
        </View>
      ) : lookupErr ? (
        <View style={st.resultRow}><Ionicons name="alert-circle" size={18} color={colors.error} /><Text style={[st.muted, { color: colors.error, flex: 1 }]}>{lookupErr}</Text></View>
      ) : null}

      <Modal visible={pickerOpen} animationType="slide" onRequestClose={() => setPickerOpen(false)}>
        <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top", "bottom"]}>
          <View style={st.modalHeader}>
            <Text style={st.modalTitle}>Choose bank</Text>
            <Pressable testID="ng-bank-close" onPress={() => setPickerOpen(false)} hitSlop={10}><Ionicons name="close" size={26} color={colors.onSurface} /></Pressable>
          </View>
          <TextInput
            testID="ng-bank-search"
            value={search}
            onChangeText={setSearch}
            placeholder="Search banks"
            placeholderTextColor={colors.onSurfaceTertiary}
            style={[st.input, { marginHorizontal: spacing.xl }]}
          />
          <FlatList
            data={filtered}
            keyExtractor={(b) => b.id}
            keyboardShouldPersistTaps="handled"
            ListEmptyComponent={<Text style={[st.muted, { padding: spacing.xl }]}>No banks match &quot;{search}&quot;.</Text>}
            renderItem={({ item }) => (
              <Pressable
                testID={`ng-bank-${item.id}`}
                onPress={() => { onBank(item); setPickerOpen(false); setSearch(""); }}
                style={st.bankRow}
              >
                <Text style={st.bankName}>{item.name}</Text>
                {bank?.id === item.id && <Ionicons name="checkmark" size={18} color={colors.brand} />}
              </Pressable>
            )}
          />
        </SafeAreaView>
      </Modal>
    </View>
  );
}

const st = StyleSheet.create({
  label: { fontSize: 13, fontWeight: "600", color: colors.onSurfaceSecondary, marginTop: spacing.lg, marginBottom: spacing.sm },
  select: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between", minHeight: 50,
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.lg, backgroundColor: colors.surfaceSecondary,
  },
  selectText: { fontSize: 15, color: colors.onSurface, fontWeight: "500" },
  input: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.lg, paddingVertical: 14,
    fontSize: 15, color: colors.onSurface, backgroundColor: colors.surfaceSecondary,
  },
  resultRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.sm, padding: spacing.md, borderRadius: radius.md },
  resultOk: { backgroundColor: colors.brandTertiary },
  resolvedName: { fontSize: 15, fontWeight: "700", color: colors.onSurface },
  muted: { fontSize: 12, color: colors.onSurfaceSecondary },
  modalHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", padding: spacing.xl },
  modalTitle: { fontSize: 20, fontWeight: "700", color: colors.onSurface },
  bankRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: spacing.xl, minHeight: 52, borderBottomWidth: 1, borderBottomColor: colors.divider },
  bankName: { fontSize: 15, color: colors.onSurface },
});
