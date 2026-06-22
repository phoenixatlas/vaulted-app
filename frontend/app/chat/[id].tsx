import { useEffect, useRef, useState } from "react";
import {
  View, Text, StyleSheet, TextInput, Pressable, FlatList,
  KeyboardAvoidingView, Platform, ActivityIndicator, Image,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { useI18n } from "@/src/lib/i18n";
import { colors, spacing, radius } from "@/src/lib/theme";

type Msg = { id: string; sender: "me" | "contact"; text: string; created_at: string };
type Conv = { id: string; contact_name: string; contact_avatar: string };

export default function Conversation() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { t } = useI18n();
  const router = useRouter();
  const [conv, setConv] = useState<Conv | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const listRef = useRef<FlatList>(null);

  const load = async () => {
    try {
      const d = await api<{ conversation: Conv; messages: Msg[] }>(`/chat/messages/${id}`);
      setConv(d.conversation);
      setMsgs(d.messages);
    } catch (e) { console.log(e); }
  };

  useEffect(() => { load().finally(() => setLoading(false)); }, [id]);

  const send = async () => {
    if (!text.trim() || sending) return;
    setSending(true);
    const txt = text.trim();
    setText("");
    try {
      await api("/chat/messages", { method: "POST", body: { conversation_id: id, text: txt } });
      await load();
      setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 100);
    } catch (e) { console.log(e); } finally { setSending(false); }
  };

  return (
    <SafeAreaView style={s.root} edges={["top"]}>
      <View style={s.header}>
        <Pressable testID="chat-back" onPress={() => router.back()}><Ionicons name="chevron-back" size={26} color={colors.onSurface} /></Pressable>
        {conv && <Image source={{ uri: conv.contact_avatar }} style={s.avatar} />}
        <View style={{ flex: 1 }}>
          <Text style={s.name}>{conv?.contact_name ?? "…"}</Text>
          <View style={s.encRow}>
            <Ionicons name="lock-closed" size={10} color={colors.success} />
            <Text style={s.enc}>{t("encrypted")}</Text>
          </View>
        </View>
        <Pressable testID="chat-call" onPress={() => router.push("/video-call")}><Ionicons name="videocam" size={22} color={colors.brand} /></Pressable>
      </View>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1 }} keyboardVerticalOffset={Platform.OS === "ios" ? 0 : 0}>
        {loading ? (
          <ActivityIndicator color={colors.brand} style={{ marginTop: 40 }} />
        ) : (
          <FlatList
            ref={listRef}
            data={msgs}
            keyExtractor={(m) => m.id}
            contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm }}
            onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: false })}
            renderItem={({ item }) => (
              <View style={[s.bubbleWrap, { alignItems: item.sender === "me" ? "flex-end" : "flex-start" }]}>
                <View style={[s.bubble, item.sender === "me" ? s.bubbleMe : s.bubbleThem]}>
                  <Text style={[s.bubbleText, item.sender === "me" && { color: "#fff" }]}>{item.text}</Text>
                </View>
              </View>
            )}
          />
        )}
        <View style={s.composer}>
          <TextInput
            testID="chat-input"
            value={text}
            onChangeText={setText}
            placeholder={t("new_message")}
            placeholderTextColor={colors.onSurfaceTertiary}
            style={s.input}
            multiline
          />
          <Pressable testID="chat-send" onPress={send} disabled={sending || !text.trim()} style={[s.sendBtn, (!text.trim() || sending) && { opacity: 0.5 }]}>
            <Ionicons name="arrow-up" size={20} color="#fff" />
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider },
  avatar: { width: 36, height: 36, borderRadius: radius.pill },
  name: { color: colors.onSurface, fontWeight: "700", fontSize: 15 },
  encRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 2 },
  enc: { color: colors.onSurfaceTertiary, fontSize: 11 },
  bubbleWrap: { width: "100%" },
  bubble: { maxWidth: "78%", paddingHorizontal: 14, paddingVertical: 10, borderRadius: 18 },
  bubbleMe: { backgroundColor: colors.brand, borderBottomRightRadius: 4 },
  bubbleThem: { backgroundColor: colors.surfaceSecondary, borderBottomLeftRadius: 4 },
  bubbleText: { color: colors.onSurface, fontSize: 15 },
  composer: { flexDirection: "row", alignItems: "flex-end", gap: spacing.sm, paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, borderTopWidth: 1, borderTopColor: colors.divider, backgroundColor: colors.surface },
  input: { flex: 1, minHeight: 40, maxHeight: 120, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 14, paddingVertical: 10, fontSize: 15, color: colors.onSurface, backgroundColor: colors.surfaceSecondary },
  sendBtn: { width: 40, height: 40, borderRadius: radius.pill, backgroundColor: colors.brand, alignItems: "center", justifyContent: "center" },
});
