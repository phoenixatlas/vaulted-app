/**
 * ShareReceiptButton — creates a private receipt link for a transfer and
 * opens the phone's share sheet (WhatsApp, email, Messages…). On web it uses
 * the browser share sheet when available, otherwise copies the link.
 */
import { useState } from "react";
import { Pressable, Text, ActivityIndicator, Share, Platform, StyleSheet } from "react-native";
import * as Clipboard from "expo-clipboard";
import { Ionicons } from "@expo/vector-icons";
import { api, API_BASE } from "@/src/lib/api";
import { colors, spacing, radius } from "@/src/lib/theme";

type Props = { txId: string; amountText: string; recipientName?: string | null };

export default function ShareReceiptButton({ txId, amountText, recipientName }: Props) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const share = async () => {
    setBusy(true);
    setNote(null);
    try {
      const { path } = await api<{ path: string }>(`/transactions/${txId}/share`, { method: "POST" });
      const url = `${API_BASE}${path}`;
      const who = recipientName ? recipientName.split(" ")[0] : "you";
      const message = `I've sent ${amountText} to ${who} with Vaulted. View the receipt: ${url}`;
      const nav: any = Platform.OS === "web" ? (globalThis as any).navigator : null;
      if (Platform.OS !== "web") {
        await Share.share({ message, title: "Vaulted receipt" });
      } else if (nav?.share) {
        await nav.share({ title: "Vaulted receipt", text: message, url });
      } else {
        await Clipboard.setStringAsync(message);
        setNote("Receipt link copied");
      }
    } catch (e: any) {
      if (e?.name !== "AbortError") setNote(e?.message || "Couldn't create the link");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Pressable testID="share-receipt" onPress={share} disabled={busy} style={st.btn}>
        {busy ? <ActivityIndicator color={colors.brandDeep} /> : (
          <>
            <Ionicons name="share-social-outline" size={18} color={colors.brandDeep} />
            <Text style={st.text}>Share receipt</Text>
          </>
        )}
      </Pressable>
      {!!note && <Text testID="share-receipt-note" style={st.note}>{note}</Text>}
    </>
  );
}

const st = StyleSheet.create({
  btn: {
    flexDirection: "row", gap: 8, alignItems: "center", justifyContent: "center", minHeight: 48, width: "100%",
    borderRadius: radius.md, borderWidth: 1, borderColor: colors.brand, marginTop: spacing.md,
  },
  text: { color: colors.brandDeep, fontSize: 15, fontWeight: "700" },
  note: { textAlign: "center", fontSize: 12, color: colors.onSurfaceSecondary, marginTop: spacing.xs },
});
