import { useCallback, useState } from "react";
import { View, Text, StyleSheet, FlatList, Pressable, Image, RefreshControl, ActivityIndicator } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { useI18n } from "@/src/lib/i18n";
import { colors, spacing, radius } from "@/src/lib/theme";

type Conv = { id: string; contact_name: string; contact_avatar: string; last_message: string; last_message_at: string; encrypted: boolean; unread: number };

export default function ChatList() {
  const { t } = useI18n();
  const router = useRouter();
  const [items, setItems] = useState<Conv[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    try { setItems(await api<Conv[]>("/chat/conversations")); } catch (e) { console.log(e); }
  };
  useFocusEffect(useCallback(() => { setLoading(true); load().finally(() => setLoading(false)); }, []));
  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  return (
    <SafeAreaView style={s.root} edges={["top"]}>
      <View style={s.header}>
        <Text style={s.title}>{t("chat")}</Text>
        <Pressable testID="open-video-call" onPress={() => router.push("/video-call")} style={s.callBtn}>
          <Ionicons name="videocam" size={20} color={colors.brand} />
        </Pressable>
      </View>
      {loading ? (
        <ActivityIndicator color={colors.brand} style={{ marginTop: 40 }} />
      ) : items.length === 0 ? (
        <View style={s.empty}>
          <View style={s.emptyIcon}><Ionicons name="chatbubbles-outline" size={32} color={colors.brand} /></View>
          <Text style={s.emptyText}>{t("no_chats")}</Text>
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(i) => i.id}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brand} />}
          renderItem={({ item }) => (
            <Pressable
              testID={`conv-${item.id}`}
              onPress={() => router.push(`/chat/${item.id}`)}
              style={({ pressed }) => [s.row, pressed && { backgroundColor: colors.surfaceSecondary }]}
            >
              <Image source={{ uri: item.contact_avatar }} style={s.avatar} />
              <View style={{ flex: 1 }}>
                <View style={s.nameRow}>
                  <Text style={s.name}>{item.contact_name}</Text>
                  {item.encrypted && <Ionicons name="lock-closed" size={11} color={colors.onSurfaceTertiary} />}
                </View>
                <Text style={s.preview} numberOfLines={1}>{item.last_message}</Text>
              </View>
              {item.unread > 0 && (
                <View style={s.badge}><Text style={s.badgeText}>{item.unread}</Text></View>
              )}
            </Pressable>
          )}
          ItemSeparatorComponent={() => <View style={s.sep} />}
        />
      )}
    </SafeAreaView>
  );
}
const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.xl, paddingTop: spacing.md, paddingBottom: spacing.lg },
  title: { fontSize: 26, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.6 },
  callBtn: { width: 40, height: 40, borderRadius: radius.pill, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingHorizontal: spacing.xl, paddingVertical: spacing.md },
  avatar: { width: 48, height: 48, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary },
  nameRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  name: { fontSize: 15, fontWeight: "600", color: colors.onSurface },
  preview: { fontSize: 13, color: colors.onSurfaceSecondary, marginTop: 2 },
  sep: { height: 1, backgroundColor: colors.divider, marginLeft: spacing.xl + 48 + spacing.md },
  badge: { backgroundColor: colors.brand, minWidth: 22, height: 22, borderRadius: 11, alignItems: "center", justifyContent: "center", paddingHorizontal: 6 },
  badgeText: { color: "#fff", fontSize: 11, fontWeight: "700" },
  empty: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.md },
  emptyIcon: { width: 72, height: 72, borderRadius: radius.pill, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  emptyText: { fontSize: 15, color: colors.onSurfaceSecondary },
});
