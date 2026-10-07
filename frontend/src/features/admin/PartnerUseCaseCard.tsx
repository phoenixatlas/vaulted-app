/**
 * PartnerUseCaseCard — one-click dispatcher + download panel for the PSB
 * use-case brief. Combines three capabilities in a single card:
 *   • Form to fill in recipient + optional cover note, then "Send via Resend"
 *   • Direct PDF / DOCX downloads if you want to review before sending
 *   • Sent-history list with delivery / open status (populated by Resend
 *     webhook → /api/admin/usecase/resend-webhook)
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { View, Text, Pressable, TextInput, ActivityIndicator, Linking, Platform } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { api, API_BASE } from "@/src/lib/api";
import { colors } from "@/src/lib/theme";
import { s } from "./styles";
import type { Contact, ContactsResp, UseCaseSendRow, UseCaseSendsResp } from "./types";

type Props = {
  sendsData: UseCaseSendsResp | null;
  loading: boolean;
  errorMsg?: string;
  onSent: () => void;
};

export function PartnerUseCaseCard({ sendsData, loading, errorMsg, onSent }: Props) {
  const [bankShort, setBankShort] = useState("9PSB");
  const [bankName, setBankName] = useState("9mobile 9Payment Service Bank Ltd");
  const [recipientEmail, setRecipientEmail] = useState("");
  const [recipientName, setRecipientName] = useState("");
  const [recipientTitle, setRecipientTitle] = useState("");
  const [coverNote, setCoverNote] = useState("");
  const [sending, setSending] = useState(false);
  const [sendResult, setSendResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  // Contact book — pulled lazily when the card mounts so we don't block
  // initial admin load on a secondary endpoint.
  const [contacts, setContacts] = useState<ContactsResp | null>(null);
  const [showContacts, setShowContacts] = useState(false);
  const [savingContact, setSavingContact] = useState(false);
  const reloadContacts = useCallback(async () => {
    try {
      const res = await api<ContactsResp>("/admin/contacts");
      setContacts(res);
    } catch {
      /* non-fatal — card still works without contacts */
    }
  }, []);
  useEffect(() => { reloadContacts(); }, [reloadContacts]);

  // When the user types a new bank_short, auto-pick its primary contact
  // from the contact book (no overwrite if they've already typed).
  useEffect(() => {
    if (!contacts || recipientEmail || recipientName) return;
    const bank = (bankShort || "").toUpperCase();
    const list = contacts.by_bank[bank];
    if (!list?.length) return;
    const primary = list.find((c) => c.is_primary) || list[0];
    if (primary) {
      setRecipientEmail(primary.email);
      setRecipientName(primary.name);
      if (primary.title) setRecipientTitle(primary.title);
      if (primary.bank_name && !bankName) setBankName(primary.bank_name);
    }
  }, [bankShort, contacts]); // eslint-disable-line react-hooks/exhaustive-deps -- auto-fill only runs when fields empty

  const applyContact = useCallback(async (c: Contact) => {
    setRecipientEmail(c.email);
    setRecipientName(c.name);
    setRecipientTitle(c.title || "");
    setBankShort(c.bank_short);
    if (c.bank_name) setBankName(c.bank_name);
    setShowContacts(false);
    // Fire-and-forget touch so this contact ranks higher next time.
    api(`/admin/contacts/${c.id}/touch`, { method: "POST", body: {} }).catch(() => undefined);
  }, []);

  const saveCurrentAsContact = useCallback(async () => {
    if (!recipientEmail.includes("@") || !recipientName.trim() || !bankShort.trim()) return;
    setSavingContact(true);
    try {
      await api("/admin/contacts", {
        method: "POST",
        body: {
          bank_short: bankShort.trim(),
          bank_name: bankName.trim() || undefined,
          name: recipientName.trim(),
          title: recipientTitle.trim() || undefined,
          email: recipientEmail.trim(),
        },
      });
      await reloadContacts();
    } catch {
      /* swallow — minor UX feature */
    } finally {
      setSavingContact(false);
    }
  }, [bankName, bankShort, recipientEmail, recipientName, recipientTitle, reloadContacts]);

  const canSend =
    recipientEmail.includes("@") && recipientEmail.includes(".") &&
    bankShort.trim().length > 0 && !sending;

  const currentContactSaved = useMemo(() => {
    if (!contacts || !recipientEmail) return false;
    return contacts.contacts.some((c) => c.email.toLowerCase() === recipientEmail.toLowerCase());
  }, [contacts, recipientEmail]);

  const onSend = async () => {
    if (!canSend) return;
    setSending(true);
    setSendResult(null);
    try {
      const res = await api<{ ok: boolean; send_id: string; status: string; error?: string }>(
        "/admin/usecase/send",
        {
          method: "POST",
          body: {
            recipient_email: recipientEmail.trim(),
            recipient_name: recipientName.trim(),
            recipient_title: recipientTitle.trim() || undefined,
            bank_short: bankShort.trim(),
            bank_name: bankName.trim() || undefined,
            cover_note: coverNote.trim() || undefined,
          },
        }
      );
      if (res.ok) {
        setSendResult({ ok: true, msg: `✓ Sent to ${recipientEmail}` });
        setCoverNote("");
        setTimeout(() => onSent(), 500);
      } else {
        setSendResult({ ok: false, msg: `✗ ${res.error || "Send failed"}` });
      }
    } catch (e: any) {
      setSendResult({ ok: false, msg: `✗ ${e?.message || "Network error"}` });
    } finally {
      setSending(false);
    }
  };

  const statusChip = (row: UseCaseSendRow): { label: string; color: string } => {
    if (row.opened_at) return { label: "OPENED", color: colors.success };
    if (row.clicked_at) return { label: "CLICKED", color: colors.success };
    if (row.delivered_at) return { label: "DELIVERED", color: colors.brand };
    if (row.status === "bounced") return { label: "BOUNCED", color: colors.error };
    if (row.status === "failed") return { label: "FAILED", color: colors.error };
    if (row.status === "sent") return { label: "SENT", color: colors.onSurfaceSecondary };
    return { label: row.status.toUpperCase(), color: colors.onSurfaceTertiary };
  };

  return (
    <View style={s.card}>
      <View style={s.cardHeaderRow}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Ionicons name="briefcase-outline" size={18} color={colors.brand} />
          <Text style={s.cardTitle}>Partner use case · {bankShort}</Text>
        </View>
        <View style={s.modePill}>
          <Text style={s.modePillText}>INFRA PITCH</Text>
        </View>
      </View>
      <Text style={s.subtle}>
        Fill in the recipient, add a personal note, hit send. Vaulted
        attaches the 2-page PDF and emails via Resend from your reply-to
        address — any reply lands back in your inbox.
      </Text>

      {/* Minimal form */}
      <View style={{ marginTop: 10, gap: 8 }}>
        <View style={{ flexDirection: "row", gap: 8 }}>
          <View style={{ flex: 1 }}>
            <Text style={s.inputLabel}>Bank short</Text>
            <TextInput
              value={bankShort}
              onChangeText={setBankShort}
              placeholder="9PSB"
              placeholderTextColor={colors.onSurfaceTertiary}
              style={s.input}
              autoCapitalize="characters"
            />
          </View>
          <View style={{ flex: 2 }}>
            <Text style={s.inputLabel}>Bank name</Text>
            <TextInput
              value={bankName}
              onChangeText={setBankName}
              placeholder="e.g. 9mobile 9PSB Ltd"
              placeholderTextColor={colors.onSurfaceTertiary}
              style={s.input}
            />
          </View>
        </View>
        <View>
          <Text style={s.inputLabel}>Recipient email *</Text>
          <TextInput
            value={recipientEmail}
            onChangeText={setRecipientEmail}
            placeholder="director@9psb.com.ng"
            placeholderTextColor={colors.onSurfaceTertiary}
            style={s.input}
            autoCapitalize="none"
            keyboardType="email-address"
          />
        </View>

        {/* Contact book picker + save-as-contact action */}
        {contacts && contacts.total > 0 ? (
          <View style={{ flexDirection: "row", alignItems: "center", gap: 10, marginTop: -2 }}>
            <Pressable onPress={() => setShowContacts((v) => !v)} hitSlop={6}>
              <Text style={s.disclosureBtn}>
                {showContacts ? "▾" : "▸"} {contacts.total} saved contact{contacts.total !== 1 ? "s" : ""}
              </Text>
            </Pressable>
            {recipientEmail && !currentContactSaved ? (
              <Pressable
                onPress={saveCurrentAsContact}
                disabled={savingContact}
                hitSlop={6}
                style={{ marginLeft: "auto" }}
              >
                <Text style={[s.disclosureBtn, { color: colors.success }]}>
                  {savingContact ? "Saving…" : "+ Save to contacts"}
                </Text>
              </Pressable>
            ) : null}
          </View>
        ) : null}
        {showContacts && contacts ? (
          <View style={{ gap: 4, marginTop: 2 }}>
            {Object.entries(contacts.by_bank).map(([bank, list]) => (
              <View key={bank}>
                <Text style={[s.inputLabel, { marginTop: 6, marginBottom: 4 }]}>{bank}</Text>
                {list.map((c) => (
                  <Pressable
                    key={c.id}
                    onPress={() => applyContact(c)}
                    style={s.contactRow}
                    hitSlop={4}
                  >
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <Text style={s.contactName} numberOfLines={1}>
                        {c.name}{" "}
                        {c.is_primary ? <Text style={s.contactPrimary}>· primary</Text> : null}
                      </Text>
                      <Text style={s.contactMeta} numberOfLines={1}>
                        {c.email}{c.title ? ` · ${c.title}` : ""}
                      </Text>
                    </View>
                    <Ionicons name="arrow-forward-circle-outline" size={16} color={colors.brand} />
                  </Pressable>
                ))}
              </View>
            ))}
          </View>
        ) : null}

        <View style={{ flexDirection: "row", gap: 8 }}>
          <View style={{ flex: 1 }}>
            <Text style={s.inputLabel}>Recipient name</Text>
            <TextInput
              value={recipientName}
              onChangeText={setRecipientName}
              placeholder="Dr. Branka Mracajac"
              placeholderTextColor={colors.onSurfaceTertiary}
              style={s.input}
            />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={s.inputLabel}>Title</Text>
            <TextInput
              value={recipientTitle}
              onChangeText={setRecipientTitle}
              placeholder="Managing Director"
              placeholderTextColor={colors.onSurfaceTertiary}
              style={s.input}
            />
          </View>
        </View>
        <Pressable onPress={() => setExpanded((v) => !v)} hitSlop={6}>
          <Text style={s.disclosureBtn}>
            {expanded ? "▾ Hide cover note" : "▸ Add a personal cover note (optional)"}
          </Text>
        </Pressable>
        {expanded ? (
          <TextInput
            value={coverNote}
            onChangeText={setCoverNote}
            placeholder="e.g. 'Following up on our call last week — attached is the detailed brief we discussed.'"
            placeholderTextColor={colors.onSurfaceTertiary}
            style={[s.input, { height: 80, textAlignVertical: "top", paddingVertical: 10 }]}
            multiline
          />
        ) : null}
      </View>

      {/* Send button + result */}
      <Pressable
        onPress={onSend}
        disabled={!canSend}
        style={[s.sendBtn, !canSend && s.sendBtnDisabled]}
      >
        {sending ? (
          <ActivityIndicator size="small" color={colors.onBrand} />
        ) : (
          <>
            <Ionicons name="paper-plane" size={16} color={colors.onBrand} />
            <Text style={s.sendBtnText}>Send use case to {bankShort}</Text>
          </>
        )}
      </Pressable>
      {sendResult ? (
        <Text style={[s.sendResult, sendResult.ok ? s.sendResultOk : s.sendResultErr]}>
          {sendResult.msg}
        </Text>
      ) : null}

      {/* Download / preview links */}
      <View style={s.downloadStrip}>
        <Pressable
          onPress={() => {
            const q = `?bank_short=${encodeURIComponent(bankShort)}&bank_name=${encodeURIComponent(bankName)}`;
            const url = `${API_BASE}/api/usecase/psb.pdf${q}`;
            if (Platform.OS === "web") window.open(url, "_blank");
            else Linking.openURL(url).catch(() => {});
          }}
          style={s.downloadBtn}
          hitSlop={6}
        >
          <Ionicons name="document-outline" size={13} color={colors.brand} />
          <Text style={s.downloadBtnText}>Preview PDF</Text>
        </Pressable>
        <Pressable
          onPress={() => {
            const q = `?bank_short=${encodeURIComponent(bankShort)}&bank_name=${encodeURIComponent(bankName)}`;
            const url = `${API_BASE}/api/usecase/psb.docx${q}`;
            if (Platform.OS === "web") window.open(url, "_blank");
            else Linking.openURL(url).catch(() => {});
          }}
          style={s.downloadBtn}
          hitSlop={6}
        >
          <Ionicons name="document-text-outline" size={13} color={colors.brand} />
          <Text style={s.downloadBtnText}>Edit DOCX</Text>
        </Pressable>
      </View>

      {/* Send history (collapsed by default) */}
      {sendsData && sendsData.total > 0 ? (
        <>
          <Pressable
            onPress={() => setShowHistory((v) => !v)}
            style={s.historyToggle}
            hitSlop={6}
          >
            <Text style={s.historyToggleText}>
              {showHistory ? "▾" : "▸"} Sent history ({sendsData.total})
            </Text>
            <View style={{ flexDirection: "row", gap: 10 }}>
              <Text style={s.historyStat}>
                📬 {sendsData.delivered_count} delivered
              </Text>
              <Text style={s.historyStat}>
                👀 {sendsData.opened_count} opened
              </Text>
            </View>
          </Pressable>
          {showHistory ? (
            <View style={{ gap: 6, marginTop: 6 }}>
              {sendsData.rows.slice(0, 10).map((row) => {
                const chip = statusChip(row);
                return (
                  <View key={row.send_id} style={s.historyRow}>
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <Text style={s.historyRecipient} numberOfLines={1}>
                        {row.recipient_name || row.recipient_email}
                        <Text style={{ color: colors.onSurfaceTertiary }}>
                          {"  ·  "}{row.bank_short}
                        </Text>
                      </Text>
                      <Text style={s.historyMeta} numberOfLines={1}>
                        {row.recipient_email} · {new Date(row.attempted_at || "").toLocaleString()}
                      </Text>
                    </View>
                    <View style={[s.historyChip, { borderColor: chip.color + "60", backgroundColor: chip.color + "20" }]}>
                      <Text style={[s.historyChipText, { color: chip.color }]}>{chip.label}</Text>
                    </View>
                  </View>
                );
              })}
            </View>
          ) : null}
        </>
      ) : null}

      {errorMsg && !sendsData ? (
        <Text style={[s.subtle, { color: colors.error, marginTop: 8, fontSize: 11 }]}>
          History unavailable: {errorMsg}
        </Text>
      ) : null}
    </View>
  );
}
