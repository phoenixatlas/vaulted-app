/**
 * SavedRecipients — tap-to-fill chips of people the user has paid before
 * in the selected corridor. Long-press a chip to remove it.
 */
import { useCallback, useEffect, useState } from "react";
import { View, Text, Pressable, ScrollView, Alert, StyleSheet, Platform } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { colors, spacing, radius } from "@/src/lib/theme";

export type SavedRecipient = {
  id: string; name: string; country_code: string; currency: string; account: string;
  rail: "momo" | "bank" | "wallet"; bank_id?: string | null; bank_name?: string | null; verified?: boolean;
};

type Props = { country: string; rails: SavedRecipient["rail"][]; selectedId?: string | null; onSelect: (r: SavedRecipient) => void };

export default function SavedRecipients({ country, rails, selectedId, onSelect }: Props) {
  const [all, setAll] = useState<SavedRecipient[]>([]);
  const items = all.filter((r) => rails.includes(r.rail));

  const load = useCallback(() => {
    api<{ recipients: SavedRecipient[] }>(`/recipients?country=${country}`)
      .then((d) => setAll(d.recipients))
      .catch(() => setAll([]));
  }, [country]);

  useEffect(() => { load(); }, [load]);

  const remove = (r: SavedRecipient) => {
    const go = () => api(`/recipients/${r.id}`, { method: "DELETE" }).then(load).catch(() => undefined);
    if (Platform.OS === "web") { go(); return; }
    Alert.alert("Remove recipient?", `${r.name} will be removed from your saved list.`, [
      { text: "Cancel", style: "cancel" },
      { text: "Remove", style: "destructive", onPress: go },
    ]);
  };

  if (!items.length) return null;

  const mask = (a: string) => (a.length > 6 ? `•••${a.slice(-4)}` : a);

  return (
    <View testID="saved-recipients">
      <Text style={st.label}>Saved recipients</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm, paddingBottom: spacing.sm }}>
        {items.map((r) => {
          const active = r.id === selectedId;
          return (
            <Pressable
              key={r.id}
              testID={`saved-recipient-${r.id}`}
              onPress={() => onSelect(r)}
              onLongPress={() => remove(r)}
              style={[st.chip, active && st.chipActive]}
            >
              <View style={st.avatar}><Text style={st.avatarText}>{r.name.slice(0, 1).toUpperCase()}</Text></View>
              <View>
                <Text style={st.name} numberOfLines={1}>{r.name}</Text>
                <Text style={st.sub} numberOfLines={1}>{r.bank_name ? `${r.bank_name} · ` : ""}{mask(r.account)}</Text>
              </View>
              {r.verified && <Ionicons name="checkmark-circle" size={14} color={colors.success} />}
            </Pressable>
          );
        })}
      </ScrollView>
    </View>
  );
}

const st = StyleSheet.create({
  label: { fontSize: 13, fontWeight: "600", color: colors.onSurfaceSecondary, marginTop: spacing.lg, marginBottom: spacing.sm },
  chip: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 8, paddingHorizontal: 12,
    borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, maxWidth: 220, minHeight: 48,
  },
  chipActive: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  avatar: { width: 30, height: 30, borderRadius: 15, backgroundColor: colors.brand, alignItems: "center", justifyContent: "center" },
  avatarText: { color: colors.onBrand, fontWeight: "700" },
  name: { fontSize: 13, fontWeight: "700", color: colors.onSurface, maxWidth: 140 },
  sub: { fontSize: 11, color: colors.onSurfaceSecondary, maxWidth: 140 },
});
