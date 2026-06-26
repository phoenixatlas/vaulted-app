import { useEffect, useState } from "react";
import {
  View, Text, StyleSheet, TextInput, Pressable, FlatList, Image, ActivityIndicator,
  KeyboardAvoidingView, Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { useI18n } from "@/src/lib/i18n";
import { colors, spacing, radius } from "@/src/lib/theme";

type Contact = { id: string; name: string; email: string; avatar?: string };

export default function NewGroup() {
  const { t } = useI18n();
  const router = useRouter();
  const [name, setName] = useState("");
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setContacts(await api<Contact[]>("/chat/contacts"));
      } catch (e: any) { setErr(e?.message ?? "Failed to load contacts"); }
      finally { setLoading(false); }
    })();
  }, []);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const submit = async () => {
    setErr(null);
    if (!name.trim()) { setErr(t("group_name_required")); return; }
    if (selected.size === 0) { setErr(t("pick_at_least_one")); return; }
    setCreating(true);
    try {
      const conv = await api<{ id: string }>("/chat/groups", {
        method: "POST",
        body: { name: name.trim(), contact_ids: Array.from(selected) },
      });
      router.replace(`/chat/${conv.id}`);
    } catch (e: any) {
      setErr(e?.message ?? "Failed to create group");
    } finally { setCreating(false); }
  };

  return (
    <SafeAreaView style={s.root} edges={["top", "bottom"]}>
      <View style={s.header}>
        <Pressable testID="newgroup-back" onPress={() => router.back()}>
          <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
        </Pressable>
        <Text style={s.title}>{t("new_group")}</Text>
        <View style={{ width: 26 }} />
      </View>

      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1 }}>
        <View style={s.field}>
          <Text style={s.label}>{t("group_name")}</Text>
          <TextInput
            testID="group-name-input"
            value={name}
            onChangeText={setName}
            placeholder={t("group_name_placeholder")}
            placeholderTextColor={colors.onSurfaceTertiary}
            style={s.input}
            maxLength={60}
          />
        </View>

        <View style={s.pickerHeader}>
          <Text style={s.pickerTitle}>{t("members")}</Text>
          <Text style={s.pickerCount}>{selected.size} {t("selected")}</Text>
        </View>

        {loading ? (
          <ActivityIndicator color={colors.brand} style={{ marginTop: 40 }} />
        ) : (
          <FlatList
            data={contacts}
            keyExtractor={(c) => c.id}
            contentContainerStyle={{ paddingBottom: spacing.xxl }}
            renderItem={({ item }) => {
              const isOn = selected.has(item.id);
              return (
                <Pressable
                  testID={`pick-contact-${item.id}`}
                  onPress={() => toggle(item.id)}
                  style={({ pressed }) => [s.row, pressed && { backgroundColor: colors.surfaceSecondary }]}
                >
                  {item.avatar
                    ? <Image source={{ uri: item.avatar }} style={s.avatar} />
                    : <View style={[s.avatar, s.avatarFallback]}>
                        <Text style={s.avatarInitials}>{(item.name || "?").slice(0, 1).toUpperCase()}</Text>
                      </View>
                  }
                  <View style={{ flex: 1 }}>
                    <Text style={s.name}>{item.name}</Text>
                    <Text style={s.email} numberOfLines={1}>{item.email}</Text>
                  </View>
                  <View style={[s.checkbox, isOn && s.checkboxOn]}>
                    {isOn && <Ionicons name="checkmark" size={16} color="#0F0B08" />}
                  </View>
                </Pressable>
              );
            }}
            ItemSeparatorComponent={() => <View style={s.sep} />}
          />
        )}

        {err ? <Text style={s.err}>{err}</Text> : null}
        <Pressable
          testID="create-group-btn"
          onPress={submit}
          disabled={creating}
          style={[s.cta, creating && { opacity: 0.6 }]}
        >
          {creating
            ? <ActivityIndicator color="#0F0B08" />
            : <Text style={s.ctaText}>{t("create_group")}</Text>}
        </Pressable>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.xl, paddingTop: spacing.sm, paddingBottom: spacing.md },
  title: { fontSize: 17, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.3 },
  field: { paddingHorizontal: spacing.xl, marginBottom: spacing.md },
  label: { fontSize: 12, color: colors.brandDeep, fontWeight: "700", letterSpacing: 0.5, textTransform: "uppercase", marginBottom: 6 },
  input: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.lg, paddingVertical: 14, fontSize: 16, color: colors.onSurface, backgroundColor: colors.surfaceSecondary },
  pickerHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: spacing.xl, paddingTop: spacing.sm, paddingBottom: spacing.xs },
  pickerTitle: { fontSize: 12, color: colors.brandDeep, fontWeight: "700", letterSpacing: 0.5, textTransform: "uppercase" },
  pickerCount: { fontSize: 12, color: colors.onSurfaceSecondary, fontWeight: "600" },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingHorizontal: spacing.xl, paddingVertical: spacing.md },
  avatar: { width: 40, height: 40, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary },
  avatarFallback: { alignItems: "center", justifyContent: "center", backgroundColor: colors.brandTertiary },
  avatarInitials: { color: colors.brandDeep, fontWeight: "700", fontSize: 16 },
  name: { fontSize: 15, fontWeight: "600", color: colors.onSurface },
  email: { fontSize: 12, color: colors.onSurfaceSecondary, marginTop: 2 },
  sep: { height: 1, backgroundColor: colors.divider, marginLeft: spacing.xl + 40 + spacing.md },
  checkbox: { width: 24, height: 24, borderRadius: 12, borderWidth: 1.5, borderColor: colors.borderStrong, alignItems: "center", justifyContent: "center" },
  checkboxOn: { backgroundColor: colors.brand, borderColor: colors.brand },
  err: { color: colors.error, fontSize: 13, paddingHorizontal: spacing.xl, paddingTop: spacing.sm },
  cta: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: 16, alignItems: "center", marginHorizontal: spacing.xl, marginVertical: spacing.lg, shadowColor: colors.brand, shadowOpacity: 0.3, shadowRadius: 12, shadowOffset: { width: 0, height: 4 } },
  ctaText: { color: "#0F0B08", fontSize: 16, fontWeight: "700", letterSpacing: 0.3 },
});
