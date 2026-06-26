import { useEffect, useRef, useState } from "react";
import {
  View, Text, StyleSheet, TextInput, Pressable, FlatList,
  KeyboardAvoidingView, Platform, ActivityIndicator, Image, Modal, Linking, Alert,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { useAuth } from "@/src/lib/auth";
import { useI18n } from "@/src/lib/i18n";
import { encryptText, decryptText, ensureSecretKey, getPublicFingerprint } from "@/src/lib/crypto";
import { authenticate } from "@/src/lib/biometric";
import { colors, spacing, radius } from "@/src/lib/theme";

type Msg = {
  id: string;
  sender: "me" | "contact";
  text: string;
  kind?: "text" | "tx_card";
  nonce?: string | null;
  encrypted?: boolean;
  created_at: string;
  // tx_card fields
  tx_hash?: string;
  explorer_url?: string;
  amount_eth?: number;
  asset?: string;
  to_address?: string;
  tx_status?: string;
  _plain?: string;
};
type Conv = {
  id: string;
  contact_name: string;
  contact_avatar?: string;
  is_group?: boolean;
  group_name?: string;
  members?: Array<{ contact_id: string; name: string; avatar?: string }>;
};

export default function Conversation() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { t } = useI18n();
  const router = useRouter();
  const { user } = useAuth();
  const [conv, setConv] = useState<Conv | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [fp, setFp] = useState<string>("");
  const [showCryptoSheet, setShowCryptoSheet] = useState(false);
  const [cryptoAmount, setCryptoAmount] = useState("");
  const [cryptoSending, setCryptoSending] = useState(false);
  const [cryptoErr, setCryptoErr] = useState<string | null>(null);
  const [recipientId, setRecipientId] = useState<string | null>(null);
  const listRef = useRef<FlatList>(null);

  const decorate = async (rows: Msg[]): Promise<Msg[]> => {
    const out: Msg[] = [];
    for (const m of rows) {
      if (m.encrypted && m.nonce) {
        const plain = await decryptText(m.text, m.nonce);
        out.push({ ...m, _plain: plain ?? "(unable to decrypt)" });
      } else {
        out.push({ ...m, _plain: m.text });
      }
    }
    return out;
  };

  const load = async () => {
    try {
      const d = await api<{ conversation: Conv; messages: Msg[] }>(`/chat/messages/${id}`);
      setConv(d.conversation);
      setMsgs(await decorate(d.messages));
    } catch (e) {
      console.log(e);
    }
  };

  useEffect(() => {
    (async () => {
      await ensureSecretKey();
      setFp(await getPublicFingerprint());
      await load();
      setLoading(false);
    })();
  }, [id]);

  const send = async () => {
    if (!text.trim() || sending) return;
    setSending(true);
    const txt = text.trim();
    setText("");
    try {
      const { ciphertext, nonce } = await encryptText(txt);
      await api("/chat/messages", {
        method: "POST",
        body: { conversation_id: id, text: ciphertext, nonce, encrypted: true },
      });
      await load();
      setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 100);
    } catch (e) {
      console.log(e);
    } finally {
      setSending(false);
    }
  };

  const openCryptoSheet = () => {
    setCryptoAmount("");
    setCryptoErr(null);
    // For groups, default-select the first member; user can change with chips
    if (conv?.is_group && conv.members?.length) {
      setRecipientId(conv.members[0].contact_id);
    } else {
      setRecipientId(null);
    }
    setShowCryptoSheet(true);
  };

  const sendCrypto = async () => {
    setCryptoErr(null);
    const amt = parseFloat(cryptoAmount);
    if (!amt || amt <= 0) { setCryptoErr("Enter a valid amount"); return; }
    if (amt >= 0.01) { setCryptoErr("In-chat sends are capped under 0.01 ETH. Use the Send screen for larger amounts."); return; }
    if (conv?.is_group && !recipientId) { setCryptoErr("Pick a recipient from the group"); return; }
    if (user?.biometric_enabled) {
      const ok = await authenticate({ reason: `Send ${amt} ETH from this chat?` });
      if (!ok.success) { setCryptoErr("Biometric authentication failed"); return; }
    }
    setCryptoSending(true);
    try {
      const body: Record<string, unknown> = { conversation_id: id, amount_eth: amt };
      if (recipientId) body.to_contact_id = recipientId;
      await api("/chat/send_crypto", { method: "POST", body });
      setShowCryptoSheet(false);
      await load();
      setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 100);
    } catch (e: any) {
      setCryptoErr(e?.message ?? "Send failed");
    } finally {
      setCryptoSending(false);
    }
  };

  return (
    <SafeAreaView style={s.root} edges={["top"]}>
      <View style={s.header}>
        <Pressable testID="chat-back" onPress={() => router.back()}>
          <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
        </Pressable>
        {conv?.is_group ? (
          <View style={[s.avatar, s.groupAvatar]}>
            <Ionicons name="people" size={18} color={colors.brand} />
          </View>
        ) : conv ? (
          <Image source={{ uri: conv.contact_avatar }} style={s.avatar} />
        ) : null}
        <View style={{ flex: 1 }}>
          <Text style={s.name}>{conv?.group_name ?? conv?.contact_name ?? "…"}</Text>
          <View style={s.encRow}>
            <Ionicons name="lock-closed" size={10} color={colors.success} />
            <Text style={s.enc}>
              {conv?.is_group
                ? `${conv.members?.length ?? 0} ${t("members_label")} · ${t("encrypted")}`
                : `${t("encrypted")} · key ${fp || "…"}`}
            </Text>
          </View>
        </View>
        <Pressable testID="chat-call" onPress={() => router.push("/video-call")}>
          <Ionicons name="videocam" size={22} color={colors.brand} />
        </Pressable>
      </View>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1 }}>
        {loading ? (
          <ActivityIndicator color={colors.brand} style={{ marginTop: 40 }} />
        ) : (
          <FlatList
            ref={listRef}
            data={msgs}
            keyExtractor={(m) => m.id}
            contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm }}
            onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: false })}
            renderItem={({ item }) => {
              if (item.kind === "tx_card") {
                return (
                  <View style={[s.bubbleWrap, { alignItems: item.sender === "me" ? "flex-end" : "flex-start" }]}>
                    <View testID={`tx-card-${item.id}`} style={s.txCard}>
                      <View style={s.txTopRow}>
                        <View style={s.txIconWrap}>
                          <Ionicons name="arrow-up" size={14} color={colors.brand} />
                        </View>
                        <View style={{ flex: 1 }}>
                          <Text style={s.txLabel}>{t("sent_eth_label")}</Text>
                          <Text style={s.txAmount}>{item.amount_eth} {item.asset ?? "ETH"}</Text>
                        </View>
                        <Text style={s.txStatus}>{(item.tx_status ?? "pending").toUpperCase()}</Text>
                      </View>
                      <View style={s.txDivider} />
                      <View style={s.txMetaRow}>
                        <Text style={s.txMetaKey}>{t("network")}</Text>
                        <Text style={s.txMetaVal}>Sepolia</Text>
                      </View>
                      {item.to_address ? (
                        <View style={s.txMetaRow}>
                          <Text style={s.txMetaKey}>{t("to")}</Text>
                          <Text style={s.txMetaVal} numberOfLines={1}>{item.to_address.slice(0, 8)}…{item.to_address.slice(-6)}</Text>
                        </View>
                      ) : null}
                      {item.explorer_url ? (
                        <Pressable
                          onPress={() => Linking.openURL(item.explorer_url as string)}
                          style={s.txExplorerBtn}
                        >
                          <Ionicons name="open-outline" size={13} color={colors.brandDeep} />
                          <Text style={s.txExplorerText}>{t("view_on_etherscan")}</Text>
                        </Pressable>
                      ) : null}
                    </View>
                  </View>
                );
              }
              const showLock = !!item.encrypted;
              return (
                <View style={[s.bubbleWrap, { alignItems: item.sender === "me" ? "flex-end" : "flex-start" }]}>
                  <View style={[s.bubble, item.sender === "me" ? s.bubbleMe : s.bubbleThem]}>
                    <Text style={[s.bubbleText, item.sender === "me" && { color: "#0F0B08" }]}>
                      {item._plain ?? item.text}
                    </Text>
                  </View>
                  {showLock && (
                    <View style={s.lockTag}>
                      <Ionicons name="lock-closed" size={9} color={colors.onSurfaceTertiary} />
                      <Text style={s.lockText}>encrypted</Text>
                    </View>
                  )}
                </View>
              );
            }}
          />
        )}
        <View style={s.composer}>
          <Pressable
            testID="chat-attach-crypto"
            onPress={openCryptoSheet}
            style={s.attachBtn}
          >
            <Ionicons name="cash-outline" size={20} color={colors.brand} />
          </Pressable>
          <TextInput
            testID="chat-input"
            value={text}
            onChangeText={setText}
            placeholder={t("new_message")}
            placeholderTextColor={colors.onSurfaceTertiary}
            style={s.input}
            multiline
          />
          <Pressable
            testID="chat-send"
            onPress={send}
            disabled={sending || !text.trim()}
            style={[s.sendBtn, (!text.trim() || sending) && { opacity: 0.5 }]}
          >
            <Ionicons name="arrow-up" size={20} color="#0F0B08" />
          </Pressable>
        </View>
      </KeyboardAvoidingView>

      <Modal
        visible={showCryptoSheet}
        transparent
        animationType="slide"
        onRequestClose={() => setShowCryptoSheet(false)}
      >
        <Pressable style={s.sheetBackdrop} onPress={() => !cryptoSending && setShowCryptoSheet(false)} />
        <View style={s.sheet} testID="chat-crypto-sheet">
          <View style={s.sheetHandle} />
          <Text style={s.sheetTitle}>
            {conv?.is_group
              ? `${t("send_eth_to_member")}`
              : `${t("send_eth_to")} ${conv?.contact_name ?? ""}`}
          </Text>
          <Text style={s.sheetHint}>{t("sepolia_testnet_note")}</Text>

          {conv?.is_group && conv.members?.length ? (
            <>
              <Text style={s.sheetLabel}>{t("recipient")}</Text>
              <View style={s.memberChips}>
                {conv.members.map((m) => {
                  const active = recipientId === m.contact_id;
                  return (
                    <Pressable
                      key={m.contact_id}
                      testID={`pick-member-${m.contact_id}`}
                      onPress={() => setRecipientId(m.contact_id)}
                      style={[s.memberChip, active && s.memberChipActive]}
                    >
                      <Text style={[s.memberChipText, active && { color: "#0F0B08" }]} numberOfLines={1}>
                        @{(m.name ?? "").split(" ")[0]}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>
            </>
          ) : null}

          <Text style={s.sheetLabel}>{t("amount")} (ETH)</Text>
          <TextInput
            testID="chat-crypto-amount"
            value={cryptoAmount}
            onChangeText={setCryptoAmount}
            placeholder="0.0001"
            keyboardType="decimal-pad"
            placeholderTextColor={colors.onSurfaceTertiary}
            style={s.sheetInput}
            autoFocus
          />
          <View style={s.quickRow}>
            {["0.0001", "0.001", "0.005"].map((q) => (
              <Pressable
                key={q}
                testID={`quick-${q}`}
                onPress={() => setCryptoAmount(q)}
                style={[s.quickPill, cryptoAmount === q && s.quickPillActive]}
              >
                <Text style={[s.quickText, cryptoAmount === q && { color: "#0F0B08" }]}>{q} ETH</Text>
              </Pressable>
            ))}
          </View>
          {cryptoErr ? <Text style={s.sheetErr}>{cryptoErr}</Text> : null}
          <Pressable
            testID="chat-crypto-confirm"
            onPress={sendCrypto}
            disabled={cryptoSending}
            style={[s.cta, cryptoSending && { opacity: 0.6 }]}
          >
            {cryptoSending
              ? <ActivityIndicator color="#0F0B08" />
              : <Text style={s.ctaText}>{t("send_now")}</Text>}
          </Pressable>
          <Pressable
            testID="chat-crypto-cancel"
            onPress={() => !cryptoSending && setShowCryptoSheet(false)}
            style={s.cancelBtn}
          >
            <Text style={s.cancelText}>{t("cancel")}</Text>
          </Pressable>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    paddingHorizontal: spacing.lg, paddingVertical: spacing.sm,
    borderBottomWidth: 1, borderBottomColor: colors.divider,
  },
  avatar: { width: 36, height: 36, borderRadius: radius.pill },
  groupAvatar: { backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "rgba(201,163,91,0.40)" },
  name: { color: colors.onSurface, fontWeight: "700", fontSize: 15 },
  encRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 2 },
  enc: { color: colors.onSurfaceTertiary, fontSize: 11 },
  bubbleWrap: { width: "100%" },
  bubble: { maxWidth: "78%", paddingHorizontal: 14, paddingVertical: 10, borderRadius: 18 },
  bubbleMe: { backgroundColor: colors.brand, borderBottomRightRadius: 4 },
  bubbleThem: { backgroundColor: colors.surfaceSecondary, borderBottomLeftRadius: 4 },
  bubbleText: { color: colors.onSurface, fontSize: 15 },
  lockTag: { flexDirection: "row", alignItems: "center", gap: 3, marginTop: 2, paddingHorizontal: 6 },
  lockText: { color: colors.onSurfaceTertiary, fontSize: 9 },
  composer: {
    flexDirection: "row", alignItems: "flex-end", gap: spacing.sm,
    paddingHorizontal: spacing.lg, paddingVertical: spacing.sm,
    borderTopWidth: 1, borderTopColor: colors.divider, backgroundColor: colors.surface,
  },
  input: {
    flex: 1, minHeight: 40, maxHeight: 120, borderRadius: radius.lg,
    borderWidth: 1, borderColor: colors.border, paddingHorizontal: 14, paddingVertical: 10,
    fontSize: 15, color: colors.onSurface, backgroundColor: colors.surfaceSecondary,
  },
  sendBtn: {
    width: 40, height: 40, borderRadius: radius.pill, backgroundColor: colors.brand,
    alignItems: "center", justifyContent: "center",
  },
  attachBtn: {
    width: 40, height: 40, borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: "rgba(201,163,91,0.35)",
  },
  // ---- tx_card ----
  txCard: {
    maxWidth: "82%",
    backgroundColor: colors.brandTertiary,
    borderWidth: 1,
    borderColor: "rgba(201,163,91,0.45)",
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.xs,
    shadowColor: colors.brand,
    shadowOpacity: 0.15,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
  },
  txTopRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  txIconWrap: {
    width: 28, height: 28, borderRadius: 14,
    backgroundColor: "rgba(201,163,91,0.20)",
    alignItems: "center", justifyContent: "center",
  },
  txLabel: { fontSize: 10, color: colors.brandDeep, fontWeight: "700", letterSpacing: 1, textTransform: "uppercase" },
  txAmount: { fontSize: 18, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.3, marginTop: 1 },
  txStatus: { fontSize: 9, color: colors.brandDeep, fontWeight: "800", letterSpacing: 1, backgroundColor: "rgba(201,163,91,0.20)", paddingHorizontal: 6, paddingVertical: 3, borderRadius: 4 },
  txDivider: { borderBottomWidth: 1, borderBottomColor: "rgba(201,163,91,0.30)", borderStyle: "dashed", marginVertical: spacing.xs },
  txMetaRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 2 },
  txMetaKey: { fontSize: 11, color: colors.brandDeep, fontWeight: "600", letterSpacing: 0.5, textTransform: "uppercase" },
  txMetaVal: { fontSize: 12, color: colors.onSurface, fontWeight: "600", maxWidth: "65%" },
  txExplorerBtn: {
    marginTop: spacing.xs, alignSelf: "flex-start",
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: 10, paddingVertical: 6,
    backgroundColor: "rgba(201,163,91,0.15)",
    borderRadius: radius.sm,
  },
  txExplorerText: { fontSize: 11, color: colors.brandDeep, fontWeight: "700", letterSpacing: 0.3 },
  // ---- crypto sheet ----
  sheetBackdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: "rgba(15,11,8,0.55)" },
  sheet: {
    position: "absolute", left: 0, right: 0, bottom: 0,
    backgroundColor: colors.surface,
    borderTopLeftRadius: 24, borderTopRightRadius: 24,
    padding: spacing.xl, paddingBottom: Platform.OS === "ios" ? spacing.xxl + 8 : spacing.xl,
    borderTopWidth: 1, borderTopColor: "rgba(201,163,91,0.30)",
  },
  sheetHandle: { width: 40, height: 4, borderRadius: 2, backgroundColor: colors.borderStrong, alignSelf: "center", marginBottom: spacing.md },
  sheetTitle: { fontSize: 18, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.3 },
  sheetHint: { fontSize: 12, color: colors.onSurfaceSecondary, marginTop: 4, marginBottom: spacing.lg },
  sheetLabel: { fontSize: 12, color: colors.brandDeep, fontWeight: "700", letterSpacing: 0.5, textTransform: "uppercase", marginBottom: 6 },
  sheetInput: {
    borderWidth: 1, borderColor: colors.borderStrong, backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, paddingHorizontal: spacing.lg, paddingVertical: 14,
    fontSize: 22, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.5,
  },
  quickRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md, marginBottom: spacing.md },
  quickPill: {
    paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary, borderWidth: 1, borderColor: "rgba(201,163,91,0.40)",
  },
  quickPillActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  quickText: { fontSize: 12, color: colors.brandDeep, fontWeight: "700" },
  memberChips: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginBottom: spacing.md },
  memberChip: {
    paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary, borderWidth: 1, borderColor: "rgba(201,163,91,0.40)",
    maxWidth: 140,
  },
  memberChipActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  memberChipText: { fontSize: 12, color: colors.brandDeep, fontWeight: "700" },
  sheetErr: { color: colors.error, fontSize: 13, marginBottom: spacing.sm, marginTop: 2 },
  cta: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: 14, alignItems: "center", marginTop: spacing.sm, shadowColor: colors.brand, shadowOpacity: 0.3, shadowRadius: 12, shadowOffset: { width: 0, height: 4 } },
  ctaText: { color: "#0F0B08", fontSize: 16, fontWeight: "700", letterSpacing: 0.3 },
  cancelBtn: { paddingVertical: spacing.md, alignItems: "center", marginTop: 4 },
  cancelText: { color: colors.onSurfaceSecondary, fontSize: 14, fontWeight: "500" },
});
