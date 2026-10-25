/**
 * TellRecipientButton — once money is delivered, the sender lets the
 * recipient know from their own phone: WhatsApp or SMS straight to the
 * recipient's mobile-money number, or the share sheet for bank payouts.
 * The message includes the private receipt link.
 */
import { useState } from "react";
import { View, Pressable, Text, Linking, Share, Platform, ActivityIndicator, StyleSheet } from "react-native";
import * as Clipboard from "expo-clipboard";
import { Ionicons } from "@expo/vector-icons";
import { api, API_BASE } from "@/src/lib/api";
import { colors, spacing, radius } from "@/src/lib/theme";

type Props = { txId: string; amountText: string; recipientName?: string | null; phone?: string | null };

export default function TellRecipientButton({ txId, amountText, recipientName, phone }: Props) {
  const [busy, setBusy] = useState<"wa" | "sms" | "share" | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const raw = (phone || "").trim();
  const digits = raw.replace(/[^\d]/g, "");
  // Accept "+254 712…" and local "0712…" style numbers; local ones get no country code so WhatsApp can't be used.
  const hasPhone = digits.length >= 9;
  const intl = raw.startsWith("+");
  const first = (recipientName || "").trim().split(" ")[0] || "";

  const buildMessage = async () => {
    const { path } = await api<{ path: string }>(`/transactions/${txId}/share`, { method: "POST" });
    return `Hi${first ? ` ${first}` : ""}, the ${amountText} I sent you with Vaulted has arrived. Receipt: ${API_BASE}${path}`;
  };

  const go = async (kind: "wa" | "sms" | "share") => {
    setBusy(kind);
    setNote(null);
    try {
      const msg = await buildMessage();
      const text = encodeURIComponent(msg);
      if (kind === "wa") {
        await Linking.openURL(`https://wa.me/${digits}?text=${text}`);
      } else if (kind === "sms") {
        const num = intl ? `+${digits}` : digits;
        if (Platform.OS === "web") { await Clipboard.setStringAsync(msg); setNote("Message copied — paste it into a text to your recipient"); return; }
        const sep = Platform.OS === "ios" ? "&" : "?";
        await Linking.openURL(`sms:${num}${sep}body=${text}`);
      } else if (Platform.OS !== "web") {
        await Share.share({ message: msg });
      } else {
        await Clipboard.setStringAsync(msg);
        setNote("Message copied — paste it to your recipient");
      }
    } catch (e: any) {
      setNote(e?.message || "Couldn't prepare the message");
    } finally {
      setBusy(null);
    }
  };

  return (
    <View testID="tell-recipient">
      <Text style={st.title}>Let {first || "them"} know it's arrived</Text>
      <View style={st.row}>
        {hasPhone ? (
          <>
            {intl && (
              <Pressable testID="tell-recipient-whatsapp" onPress={() => go("wa")} style={st.btn} disabled={!!busy}>
                {busy === "wa" ? <ActivityIndicator color={colors.brandDeep} /> : <><Ionicons name="logo-whatsapp" size={18} color={colors.brandDeep} /><Text style={st.text}>WhatsApp</Text></>}
              </Pressable>
            )}
            <Pressable testID="tell-recipient-sms" onPress={() => go("sms")} style={st.btn} disabled={!!busy}>
              {busy === "sms" ? <ActivityIndicator color={colors.brandDeep} /> : <><Ionicons name="chatbubble-outline" size={18} color={colors.brandDeep} /><Text style={st.text}>Text</Text></>}
            </Pressable>
          </>
        ) : (
          <Pressable testID="tell-recipient-share" onPress={() => go("share")} style={st.btn} disabled={!!busy}>
            {busy === "share" ? <ActivityIndicator color={colors.brandDeep} /> : <><Ionicons name="paper-plane-outline" size={18} color={colors.brandDeep} /><Text style={st.text}>Send a message</Text></>}
          </Pressable>
        )}
      </View>
      {!!note && <Text testID="tell-recipient-note" style={st.note}>{note}</Text>}
    </View>
  );
}

const st = StyleSheet.create({
  title: { fontSize: 13, fontWeight: "700", color: colors.onSurfaceSecondary, textTransform: "uppercase", letterSpacing: 0.8, marginTop: spacing.xl, marginBottom: spacing.sm },
  row: { flexDirection: "row", gap: spacing.sm },
  btn: {
    flex: 1, flexDirection: "row", gap: 8, alignItems: "center", justifyContent: "center", minHeight: 48,
    borderRadius: radius.md, backgroundColor: colors.brandTertiary,
  },
  text: { color: colors.brandDeep, fontSize: 15, fontWeight: "700" },
  note: { fontSize: 12, color: colors.onSurfaceSecondary, marginTop: spacing.xs, textAlign: "center" },
});
