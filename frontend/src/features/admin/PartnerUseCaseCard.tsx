/**
 * PartnerUseCaseCard — compose, edit drafts, and dispatch the PSB
 * use-case brief as a tracked Resend email.
 *
 * Capabilities
 * ============
 *   • Draft list (saved + sent) with one-tap resume editing
 *   • Editable Subject / Body / Greeting / CTA / Booking URL — the
 *     entire email surface except brand chrome is now operator-authored
 *   • Multi-recipient support (comma / semicolon / newline separated)
 *     with CC field for internal stakeholders
 *   • Full HTML preview (web: new tab, native: subject preview)
 *   • Save / Send / Delete / Duplicate draft affordances
 *   • Collapsed Sent history grouped by `batch_id` — one 3-person
 *     blast reads as one row with per-recipient status chips
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  View, Text, Pressable, TextInput, ActivityIndicator, Linking, Platform,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { api, API_BASE } from "@/src/lib/api";
import { colors, spacing } from "@/src/lib/theme";
import { s } from "./styles";
import type { Contact, ContactsResp, UseCaseSendRow, UseCaseSendsResp } from "./types";

type Draft = {
  id: string;
  bank_short: string;
  bank_name?: string;
  recipient_email: string;
  recipient_name?: string;
  recipient_title?: string;
  subject: string;
  body_text: string;
  greeting_override?: string;
  cta_text?: string;
  cover_note?: string;
  cc?: string[];
  booking_url?: string;
  label?: string;
  status: "draft" | "sent";
  created_at?: string;
  updated_at?: string;
  sent_at?: string;
};
type DraftsResp = { drafts: Draft[]; sent_drafts: Draft[]; total: number };

type Props = {
  sendsData: UseCaseSendsResp | null;
  loading: boolean;
  errorMsg?: string;
  onSent: () => void;
};

const EMPTY_DRAFT: Draft = {
  id: "",
  bank_short: "9PSB",
  bank_name: "9mobile 9Payment Service Bank Ltd",
  recipient_email: "",
  recipient_name: "",
  recipient_title: "",
  subject: "",
  body_text: "",
  greeting_override: "",
  cta_text: "",
  cover_note: "",
  cc: [],
  booking_url: "",
  label: "",
  status: "draft",
};

export function PartnerUseCaseCard({ sendsData, loading, errorMsg, onSent }: Props) {
  // Active editor state. Lives at the top so Save / Send / Preview all
  // see the same payload. We mirror into `active` so unsaved changes
  // never get clobbered by a background refetch.
  const [active, setActive] = useState<Draft>({ ...EMPTY_DRAFT });
  const [drafts, setDrafts] = useState<DraftsResp | null>(null);
  const [draftsOpen, setDraftsOpen] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [sending, setSending] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);
  const [sendResult, setSendResult] = useState<{ ok: boolean; msg: string } | null>(null);

  // Signals when the active draft has been touched since last save, so
  // the Save button can show "Unsaved changes" rather than looking inert.
  const [isDirty, setIsDirty] = useState(false);
  const initialising = useRef(true);

  // Contacts for recipient autofill
  const [contacts, setContacts] = useState<ContactsResp | null>(null);
  const [showContacts, setShowContacts] = useState(false);
  const [savingContact, setSavingContact] = useState(false);
  const [ccString, setCcString] = useState("");

  // --- API wrappers --------------------------------------------------
  const loadDrafts = useCallback(async () => {
    try {
      const d = await api<DraftsResp>("/admin/usecase/drafts");
      setDrafts(d);
    } catch {
      /* non-fatal */
    }
  }, []);

  const loadContacts = useCallback(async () => {
    try {
      setContacts(await api<ContactsResp>("/admin/contacts"));
    } catch {
      /* non-fatal */
    }
  }, []);

  const scaffoldNewDraft = useCallback(async (bankShort = "9PSB") => {
    try {
      const seed = await api<Draft>(`/admin/usecase/drafts/new?bank_short=${encodeURIComponent(bankShort)}`);
      initialising.current = true;
      setActive({ ...EMPTY_DRAFT, ...seed, status: "draft" });
      setCcString("");
      setIsDirty(false);
      setSendResult(null);
      setTimeout(() => { initialising.current = false; }, 50);
    } catch (e: any) {
      setSendResult({ ok: false, msg: `Could not load defaults: ${e?.message || "error"}` });
    }
  }, []);

  useEffect(() => {
    loadDrafts();
    loadContacts();
    scaffoldNewDraft();
  }, [loadDrafts, loadContacts, scaffoldNewDraft]);

  // --- Dirty tracking ------------------------------------------------
  useEffect(() => {
    if (initialising.current) return;
    setIsDirty(true);
  }, [
    active.bank_short, active.bank_name, active.recipient_email,
    active.recipient_name, active.recipient_title, active.subject,
    active.body_text, active.greeting_override, active.cta_text,
    active.booking_url, active.label, ccString,
  ]);

  // --- Parsed helpers ------------------------------------------------
  const parsedRecipients = useMemo(() => parseEmails(active.recipient_email), [active.recipient_email]);
  const parsedCc = useMemo(() => parseEmails(ccString), [ccString]);

  // --- Load draft from the list --------------------------------------
  const openDraft = useCallback((d: Draft) => {
    initialising.current = true;
    setActive({ ...EMPTY_DRAFT, ...d });
    setCcString((d.cc || []).join(", "));
    setIsDirty(false);
    setSendResult(null);
    setDraftsOpen(false);
    setTimeout(() => { initialising.current = false; }, 50);
  }, []);

  // Autofill from primary contact when operator types a new bank_short
  useEffect(() => {
    if (!contacts || active.recipient_email || active.recipient_name) return;
    const list = contacts.by_bank[(active.bank_short || "").toUpperCase()];
    if (!list?.length) return;
    const primary = list.find((c) => c.is_primary) || list[0];
    initialising.current = true;
    setActive((a) => ({
      ...a,
      recipient_email: primary.email,
      recipient_name: primary.name,
      recipient_title: primary.title || "",
      bank_name: primary.bank_name || a.bank_name,
    }));
    setTimeout(() => { initialising.current = false; }, 50);
  }, [active.bank_short, contacts]); // eslint-disable-line react-hooks/exhaustive-deps

  const applyContact = useCallback((c: Contact) => {
    initialising.current = true;
    setActive((a) => ({
      ...a,
      recipient_email: c.email,
      recipient_name: c.name,
      recipient_title: c.title || "",
      bank_short: c.bank_short,
      bank_name: c.bank_name || a.bank_name,
    }));
    setShowContacts(false);
    api(`/admin/contacts/${c.id}/touch`, { method: "POST", body: {} }).catch(() => undefined);
    setTimeout(() => { initialising.current = false; }, 50);
  }, []);

  const saveCurrentAsContact = useCallback(async () => {
    const firstEmail = parsedRecipients[0] || "";
    if (!firstEmail || !(active.recipient_name || "").trim()) return;
    setSavingContact(true);
    try {
      await api("/admin/contacts", {
        method: "POST",
        body: {
          bank_short: active.bank_short,
          bank_name: active.bank_name || undefined,
          name: active.recipient_name,
          title: active.recipient_title || undefined,
          email: firstEmail,
        },
      });
      await loadContacts();
    } catch { /* ignore */ } finally { setSavingContact(false); }
  }, [parsedRecipients, active, loadContacts]);

  const currentContactSaved = useMemo(() => {
    if (!contacts || parsedRecipients.length === 0) return false;
    const email = parsedRecipients[0].toLowerCase();
    return contacts.contacts.some((c) => c.email.toLowerCase() === email);
  }, [contacts, parsedRecipients]);

  // --- Save draft ----------------------------------------------------
  const saveDraft = useCallback(async (): Promise<Draft | null> => {
    setSavingDraft(true);
    try {
      const payload = {
        id: active.id || undefined,
        bank_short: active.bank_short,
        bank_name: active.bank_name,
        recipient_email: active.recipient_email,
        recipient_name: active.recipient_name,
        recipient_title: active.recipient_title,
        subject: active.subject,
        body_text: active.body_text,
        greeting_override: active.greeting_override,
        cta_text: active.cta_text,
        booking_url: active.booking_url,
        cc: parsedCc,
        label: active.label,
      };
      const saved = await api<Draft>("/admin/usecase/drafts", { method: "POST", body: payload });
      initialising.current = true;
      setActive({ ...EMPTY_DRAFT, ...saved });
      setCcString((saved.cc || []).join(", "));
      setIsDirty(false);
      setSendResult({ ok: true, msg: "✓ Draft saved" });
      await loadDrafts();
      setTimeout(() => { initialising.current = false; }, 50);
      return saved;
    } catch (e: any) {
      setSendResult({ ok: false, msg: `✗ Save failed: ${e?.message || "error"}` });
      return null;
    } finally {
      setSavingDraft(false);
    }
  }, [active, parsedCc, loadDrafts]);

  // --- Delete / duplicate --------------------------------------------
  const deleteDraft = useCallback(async (id: string) => {
    if (!id) return;
    try {
      await api(`/admin/usecase/drafts/${id}`, { method: "DELETE" });
      await loadDrafts();
      if (id === active.id) scaffoldNewDraft(active.bank_short);
    } catch (e: any) {
      setSendResult({ ok: false, msg: `✗ Delete failed: ${e?.message || "error"}` });
    }
  }, [loadDrafts, active.id, active.bank_short, scaffoldNewDraft]);

  // --- Preview -------------------------------------------------------
  const openPreview = useCallback(async () => {
    try {
      const res = await api<{ subject: string; html: string }>(
        "/admin/usecase/drafts/preview",
        {
          method: "POST",
          body: {
            bank_short: active.bank_short,
            bank_name: active.bank_name,
            recipient_name: active.recipient_name,
            subject: active.subject,
            body_text: active.body_text,
            greeting_override: active.greeting_override,
            cta_text: active.cta_text,
            booking_url: active.booking_url,
          },
        }
      );
      if (Platform.OS === "web" && typeof window !== "undefined") {
        const w = window.open("", "_blank");
        if (w) {
          w.document.open();
          w.document.write(res.html);
          w.document.close();
          w.document.title = res.subject;
        }
      } else {
        setSendResult({ ok: true, msg: `Preview subject: ${res.subject}` });
      }
    } catch (e: any) {
      setSendResult({ ok: false, msg: `✗ Preview failed: ${e?.message || "error"}` });
    }
  }, [active]);

  // --- Send ----------------------------------------------------------
  const sendNow = useCallback(async () => {
    if (parsedRecipients.length === 0) {
      setSendResult({ ok: false, msg: "✗ Add at least one recipient" });
      return;
    }
    // Autosave latest edits so the sent email matches what's on screen.
    if (isDirty) {
      const saved = await saveDraft();
      if (!saved) return;
    }
    setSending(true);
    setSendResult(null);
    try {
      const res = await api<any>("/admin/usecase/send", {
        method: "POST",
        body: {
          recipient_email: active.recipient_email,
          recipient_name: active.recipient_name,
          recipient_title: active.recipient_title || undefined,
          bank_short: active.bank_short,
          bank_name: active.bank_name || undefined,
          subject_override: active.subject || undefined,
          body_text: active.body_text || undefined,
          greeting_override: active.greeting_override || undefined,
          cta_text: active.cta_text || undefined,
          booking_url: active.booking_url || undefined,
          cc: parsedCc.length ? parsedCc : undefined,
          draft_id: active.id || undefined,
        },
      });
      if (Array.isArray(res?.results)) {
        const sent = res.sent_count ?? 0;
        const failed = res.failed_count ?? 0;
        if (res.ok) {
          setSendResult({ ok: true, msg: `✓ Sent to all ${sent} recipient${sent !== 1 ? "s" : ""}` });
        } else if (sent > 0) {
          const bad = res.results.filter((r: any) => !r.ok).map((r: any) => r.recipient).join(", ");
          setSendResult({ ok: false, msg: `⚠ ${sent} sent · ${failed} failed (${bad})` });
        } else {
          setSendResult({ ok: false, msg: `✗ All ${failed} failed · ${res.results[0]?.error || "Send failed"}` });
        }
      } else if (res?.ok) {
        setSendResult({ ok: true, msg: `✓ Sent to ${parsedRecipients[0]}` });
      } else {
        setSendResult({ ok: false, msg: `✗ ${res?.error || "Send failed"}` });
      }
      await loadDrafts();
      onSent();
      // After a successful send, scaffold a fresh draft so operators
      // can shoot off the next one immediately. The sent draft remains
      // in the Sent list.
      if (res?.ok || (res?.sent_count ?? 0) > 0) {
        setTimeout(() => scaffoldNewDraft(active.bank_short), 400);
      }
    } catch (e: any) {
      const msg = e?.message || "Network error";
      const nicer = /not a valid email/i.test(msg)
        ? "✗ One of the emails is malformed. Separate multiple recipients with a comma or newline."
        : `✗ ${msg}`;
      setSendResult({ ok: false, msg: nicer });
    } finally {
      setSending(false);
    }
  }, [active, parsedRecipients, parsedCc, isDirty, saveDraft, loadDrafts, onSent, scaffoldNewDraft]);

  // --- Batch grouping for Sent history -------------------------------
  const groupedHistory = useMemo(() => groupRowsByBatch(sendsData?.rows || []), [sendsData]);

  const canSend = parsedRecipients.length > 0 && (active.bank_short || "").trim().length > 0 && !sending;

  return (
    <View style={s.card}>
      <View style={s.cardHeaderRow}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Ionicons name="briefcase-outline" size={18} color={colors.brand} />
          <Text style={s.cardTitle}>Partner use case · {active.bank_short || "—"}</Text>
        </View>
        <View style={s.modePill}>
          <Text style={s.modePillText}>INFRA PITCH</Text>
        </View>
      </View>
      <Text style={s.subtle}>
        Compose, edit, preview and dispatch the two-page infrastructure brief
        — every field below is editable and persists as a draft until you send.
      </Text>

      {/* Draft drawer */}
      <View style={{ flexDirection: "row", gap: 6, marginTop: spacing.sm, flexWrap: "wrap" }}>
        <Pressable
          onPress={() => scaffoldNewDraft(active.bank_short)}
          style={[s.downloadBtn, { flex: 1, minWidth: 120, justifyContent: "center" }]}
          hitSlop={6}
        >
          <Ionicons name="add-circle-outline" size={14} color={colors.brand} />
          <Text style={s.downloadBtnText}>New draft</Text>
        </Pressable>
        <Pressable
          onPress={() => setDraftsOpen((v) => !v)}
          style={[s.downloadBtn, { flex: 1, minWidth: 120, justifyContent: "center" }]}
          hitSlop={6}
        >
          <Ionicons name={draftsOpen ? "folder-open" : "folder-outline"} size={14} color={colors.brand} />
          <Text style={s.downloadBtnText}>
            Drafts ({drafts?.drafts.length ?? 0}
            {(drafts?.sent_drafts.length ?? 0) > 0 ? ` · ${drafts?.sent_drafts.length} sent` : ""})
          </Text>
        </Pressable>
      </View>
      {draftsOpen && drafts ? (
        <View style={{ marginTop: 6, gap: 4 }}>
          {drafts.drafts.length === 0 && drafts.sent_drafts.length === 0 ? (
            <Text style={[s.subtle, { fontSize: 11 }]}>
              No drafts yet. Start typing below — unsaved changes autosave when you hit Save or Send.
            </Text>
          ) : null}
          {drafts.drafts.map((d) => (
            <View key={d.id} style={s.contactRow}>
              <Ionicons name="document-text-outline" size={13} color={colors.brand} />
              <Pressable onPress={() => openDraft(d)} style={{ flex: 1, minWidth: 0 }} hitSlop={4}>
                <Text style={s.contactName} numberOfLines={1}>
                  {d.label || d.subject || "(no subject)"}
                </Text>
                <Text style={s.contactMeta} numberOfLines={1}>
                  {d.recipient_email || "no recipient"} · {d.bank_short} ·
                  updated {new Date(d.updated_at || "").toLocaleString()}
                </Text>
              </Pressable>
              <Pressable onPress={() => deleteDraft(d.id)} hitSlop={6}>
                <Ionicons name="trash-outline" size={14} color={colors.onSurfaceTertiary} />
              </Pressable>
            </View>
          ))}
          {drafts.sent_drafts.length > 0 ? (
            <View style={{ marginTop: 6 }}>
              <Text style={[s.microLabel, { marginTop: 4 }]}>RECENTLY SENT</Text>
              {drafts.sent_drafts.map((d) => (
                <Pressable
                  key={d.id}
                  onPress={() => openDraft({ ...d, status: "draft", id: "" })}
                  style={s.contactRow}
                  hitSlop={4}
                >
                  <Ionicons name="checkmark-circle-outline" size={13} color={colors.success} />
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={s.contactName} numberOfLines={1}>{d.label || d.subject}</Text>
                    <Text style={s.contactMeta} numberOfLines={1}>
                      {d.recipient_email} · sent {new Date(d.sent_at || d.updated_at || "").toLocaleString()}
                    </Text>
                  </View>
                  <Ionicons name="copy-outline" size={13} color={colors.onSurfaceTertiary} />
                </Pressable>
              ))}
            </View>
          ) : null}
        </View>
      ) : null}

      {/* Editor fields --------------------------------------------- */}
      <View style={{ marginTop: spacing.md, gap: 8 }}>
        {/* Bank */}
        <View style={{ flexDirection: "row", gap: 8 }}>
          <View style={{ flex: 1 }}>
            <Text style={s.inputLabel}>Bank short</Text>
            <TextInput
              value={active.bank_short}
              onChangeText={(v) => setActive((a) => ({ ...a, bank_short: v }))}
              placeholder="9PSB"
              placeholderTextColor={colors.onSurfaceTertiary}
              style={s.input}
              autoCapitalize="characters"
            />
          </View>
          <View style={{ flex: 2 }}>
            <Text style={s.inputLabel}>Bank name</Text>
            <TextInput
              value={active.bank_name || ""}
              onChangeText={(v) => setActive((a) => ({ ...a, bank_name: v }))}
              placeholder="e.g. 9mobile 9PSB Ltd"
              placeholderTextColor={colors.onSurfaceTertiary}
              style={s.input}
            />
          </View>
        </View>

        {/* Recipients */}
        <View>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-end" }}>
            <Text style={s.inputLabel}>Recipients *</Text>
            <Text style={[s.inputLabel, { fontWeight: "500", textTransform: "none", letterSpacing: 0, color: colors.onSurfaceTertiary }]}>
              Separate multiple with commas
            </Text>
          </View>
          <TextInput
            value={active.recipient_email}
            onChangeText={(v) => setActive((a) => ({ ...a, recipient_email: v }))}
            placeholder="director@9psb.com.ng, md@9psb.com.ng"
            placeholderTextColor={colors.onSurfaceTertiary}
            style={[s.input, parsedRecipients.length > 1 && { height: 60, textAlignVertical: "top", paddingVertical: 8 }]}
            autoCapitalize="none"
            keyboardType="email-address"
            autoCorrect={false}
            multiline={parsedRecipients.length > 1}
          />
          {parsedRecipients.length > 1 ? (
            <Text style={[s.subtle, { fontSize: 11, marginTop: 3 }]}>
              Fans out to {parsedRecipients.length} recipients — each gets their own personalised send & tracking.
            </Text>
          ) : null}
        </View>

        {/* Contact book disclosure + save-to-contacts */}
        {contacts && contacts.total > 0 ? (
          <View style={{ flexDirection: "row", alignItems: "center", gap: 10, marginTop: -2 }}>
            <Pressable onPress={() => setShowContacts((v) => !v)} hitSlop={6}>
              <Text style={s.disclosureBtn}>
                {showContacts ? "▾" : "▸"} {contacts.total} saved contact{contacts.total !== 1 ? "s" : ""}
              </Text>
            </Pressable>
            {active.recipient_email && !currentContactSaved ? (
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
          <View style={{ gap: 4 }}>
            {Object.entries(contacts.by_bank).map(([bank, list]) => (
              <View key={bank}>
                <Text style={[s.inputLabel, { marginTop: 6, marginBottom: 4 }]}>{bank}</Text>
                {list.map((c) => (
                  <Pressable key={c.id} onPress={() => applyContact(c)} style={s.contactRow} hitSlop={4}>
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <Text style={s.contactName} numberOfLines={1}>
                        {c.name}{c.is_primary ? <Text style={s.contactPrimary}>  · primary</Text> : null}
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

        {/* Recipient name / title */}
        <View style={{ flexDirection: "row", gap: 8 }}>
          <View style={{ flex: 1 }}>
            <Text style={s.inputLabel}>Primary name</Text>
            <TextInput
              value={active.recipient_name || ""}
              onChangeText={(v) => setActive((a) => ({ ...a, recipient_name: v }))}
              placeholder="Dr. Branka Mracajac"
              placeholderTextColor={colors.onSurfaceTertiary}
              style={s.input}
            />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={s.inputLabel}>Title</Text>
            <TextInput
              value={active.recipient_title || ""}
              onChangeText={(v) => setActive((a) => ({ ...a, recipient_title: v }))}
              placeholder="Managing Director"
              placeholderTextColor={colors.onSurfaceTertiary}
              style={s.input}
            />
          </View>
        </View>

        {/* CC */}
        <View>
          <Text style={s.inputLabel}>CC (optional)</Text>
          <TextInput
            value={ccString}
            onChangeText={setCcString}
            placeholder="umar.sani@phoenix-atlas.com, board@phoenix-atlas.com"
            placeholderTextColor={colors.onSurfaceTertiary}
            style={s.input}
            autoCapitalize="none"
            keyboardType="email-address"
            autoCorrect={false}
          />
          {parsedCc.length > 0 ? (
            <Text style={[s.subtle, { fontSize: 11, marginTop: 3 }]}>
              Will CC {parsedCc.length}: {parsedCc.join(", ")}
            </Text>
          ) : null}
        </View>

        {/* Subject */}
        <View>
          <Text style={s.inputLabel}>Subject</Text>
          <TextInput
            value={active.subject}
            onChangeText={(v) => setActive((a) => ({ ...a, subject: v }))}
            placeholder="Vaulted — Strategic Use Case for 9PSB"
            placeholderTextColor={colors.onSurfaceTertiary}
            style={s.input}
          />
        </View>

        {/* Greeting */}
        <View>
          <Text style={s.inputLabel}>Greeting (optional override)</Text>
          <TextInput
            value={active.greeting_override || ""}
            onChangeText={(v) => setActive((a) => ({ ...a, greeting_override: v }))}
            placeholder="Dear Nafiu — defaults to the primary name's last name"
            placeholderTextColor={colors.onSurfaceTertiary}
            style={s.input}
          />
        </View>

        {/* Body */}
        <View>
          <Text style={s.inputLabel}>Body *</Text>
          <TextInput
            value={active.body_text}
            onChangeText={(v) => setActive((a) => ({ ...a, body_text: v }))}
            placeholder="Write the full body of the email. Blank lines become paragraph breaks."
            placeholderTextColor={colors.onSurfaceTertiary}
            style={[s.input, { height: 180, textAlignVertical: "top", paddingVertical: 10, fontSize: 13, lineHeight: 19 }]}
            multiline
          />
          <Text style={[s.subtle, { fontSize: 11, marginTop: 3 }]}>
            Plain text — paragraphs are HTML-wrapped automatically. The brand chrome, PDF
            attachment pitch and signature are added by the template.
          </Text>
        </View>

        {/* CTA */}
        <View>
          <Text style={s.inputLabel}>Closing / CTA copy (optional)</Text>
          <TextInput
            value={active.cta_text || ""}
            onChangeText={(v) => setActive((a) => ({ ...a, cta_text: v }))}
            placeholder="e.g. 'Happy to jump on a 20-min call this week — my calendar is open.'"
            placeholderTextColor={colors.onSurfaceTertiary}
            style={[s.input, { height: 60, textAlignVertical: "top", paddingVertical: 8 }]}
            multiline
          />
        </View>

        {/* Booking URL */}
        <View>
          <Text style={s.inputLabel}>Booking URL (optional)</Text>
          <TextInput
            value={active.booking_url || ""}
            onChangeText={(v) => setActive((a) => ({ ...a, booking_url: v }))}
            placeholder="https://cal.com/umar-sani/20min"
            placeholderTextColor={colors.onSurfaceTertiary}
            style={s.input}
            autoCapitalize="none"
            autoCorrect={false}
          />
          <Text style={[s.subtle, { fontSize: 11, marginTop: 3 }]}>
            When set, renders a gold &ldquo;Book a 45-min working session&rdquo; button beneath the body.
          </Text>
        </View>

        {/* Label (for drafts drawer) */}
        <View>
          <Text style={s.inputLabel}>Draft label (optional)</Text>
          <TextInput
            value={active.label || ""}
            onChangeText={(v) => setActive((a) => ({ ...a, label: v }))}
            placeholder="e.g. '9PSB — exec outreach v2'"
            placeholderTextColor={colors.onSurfaceTertiary}
            style={s.input}
          />
        </View>
      </View>

      {/* Action buttons */}
      <View style={{ flexDirection: "row", gap: 8, marginTop: spacing.md, flexWrap: "wrap" }}>
        <Pressable
          onPress={openPreview}
          style={[s.downloadBtn, { flex: 1, minWidth: 100, justifyContent: "center" }]}
          hitSlop={6}
        >
          <Ionicons name="eye-outline" size={14} color={colors.brand} />
          <Text style={s.downloadBtnText}>Preview</Text>
        </Pressable>
        <Pressable
          onPress={saveDraft}
          disabled={savingDraft}
          style={[s.downloadBtn, { flex: 1, minWidth: 100, justifyContent: "center" }, savingDraft && { opacity: 0.5 }]}
          hitSlop={6}
        >
          {savingDraft ? <ActivityIndicator size="small" color={colors.brand} /> : (
            <Ionicons name="save-outline" size={14} color={isDirty ? colors.warning : colors.brand} />
          )}
          <Text style={s.downloadBtnText}>{isDirty ? "Save*" : "Saved"}</Text>
        </Pressable>
      </View>
      <Pressable
        onPress={sendNow}
        disabled={!canSend}
        style={[s.sendBtn, !canSend && s.sendBtnDisabled]}
      >
        {sending ? (
          <ActivityIndicator size="small" color={colors.onBrand} />
        ) : (
          <>
            <Ionicons name="paper-plane" size={16} color={colors.onBrand} />
            <Text style={s.sendBtnText}>
              {parsedRecipients.length > 1
                ? `Send to ${parsedRecipients.length} recipients at ${active.bank_short}`
                : `Send use case to ${active.bank_short}`}
            </Text>
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
            const q = `?bank_short=${encodeURIComponent(active.bank_short)}&bank_name=${encodeURIComponent(active.bank_name || "")}`;
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
            const q = `?bank_short=${encodeURIComponent(active.bank_short)}&bank_name=${encodeURIComponent(active.bank_name || "")}`;
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

      {/* Sent history grouped by batch_id */}
      {sendsData && sendsData.total > 0 ? (
        <>
          <Pressable
            onPress={() => setShowHistory((v) => !v)}
            style={s.historyToggle}
            hitSlop={6}
          >
            <Text style={s.historyToggleText}>
              {showHistory ? "▾" : "▸"} Sent history ({groupedHistory.length})
            </Text>
            <View style={{ flexDirection: "row", gap: 10 }}>
              <Text style={s.historyStat}>📬 {sendsData.delivered_count} delivered</Text>
              <Text style={s.historyStat}>👀 {sendsData.opened_count} opened</Text>
            </View>
          </Pressable>
          {showHistory ? (
            <View style={{ gap: 6, marginTop: 6 }}>
              {groupedHistory.slice(0, 10).map((grp) => (
                <SendHistoryGroup key={grp.key} group={grp} />
              ))}
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

// ---------- helpers ---------------------------------------------------
function parseEmails(raw: string): string[] {
  const parts = (raw || "").split(/[,;\s]+/).map((p) => p.trim()).filter(Boolean);
  const seen = new Set<string>();
  const out: string[] = [];
  for (const p of parts) {
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(p)) continue;
    const low = p.toLowerCase();
    if (!seen.has(low)) {
      seen.add(low);
      out.push(p);
    }
  }
  return out;
}

type Group = {
  key: string;
  bank_short: string;
  subject: string;
  attempted_at?: string;
  recipients: UseCaseSendRow[];
  summary: { sent: number; delivered: number; opened: number; failed: number };
};
function groupRowsByBatch(rows: UseCaseSendRow[]): Group[] {
  const byKey = new Map<string, Group>();
  for (const r of rows) {
    // Use batch_id if present, else send_id — rows with no batch_id
    // (older records before Iter 54) group one-per-entry via send_id.
    const key = (r as any).batch_id || r.send_id;
    if (!byKey.has(key)) {
      byKey.set(key, {
        key,
        bank_short: r.bank_short,
        subject: r.subject,
        attempted_at: r.attempted_at,
        recipients: [],
        summary: { sent: 0, delivered: 0, opened: 0, failed: 0 },
      });
    }
    const g = byKey.get(key)!;
    g.recipients.push(r);
    if (r.opened_at) g.summary.opened++;
    if (r.delivered_at) g.summary.delivered++;
    if (r.status === "sent" || r.status === "delivered") g.summary.sent++;
    if (r.status === "failed" || r.status === "bounced") g.summary.failed++;
    if (!g.attempted_at || (r.attempted_at && r.attempted_at > g.attempted_at)) {
      g.attempted_at = r.attempted_at;
    }
  }
  // Order groups by latest attempt
  return Array.from(byKey.values()).sort((a, b) => (b.attempted_at || "").localeCompare(a.attempted_at || ""));
}

function SendHistoryGroup({ group }: { group: Group }) {
  const [open, setOpen] = useState(false);
  const isBatch = group.recipients.length > 1;
  const headline = isBatch ? `${group.recipients.length} recipients` : group.recipients[0]?.recipient_email;
  const summaryBits: string[] = [];
  if (group.summary.opened) summaryBits.push(`${group.summary.opened} opened`);
  else if (group.summary.delivered) summaryBits.push(`${group.summary.delivered} delivered`);
  else if (group.summary.sent) summaryBits.push(`${group.summary.sent} sent`);
  if (group.summary.failed) summaryBits.push(`${group.summary.failed} failed`);
  return (
    <View>
      <Pressable onPress={() => setOpen((v) => !v)} style={s.historyRow} hitSlop={4}>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={s.historyRecipient} numberOfLines={1}>
            {headline}
            <Text style={{ color: colors.onSurfaceTertiary }}>  ·  {group.bank_short}</Text>
          </Text>
          <Text style={s.historyMeta} numberOfLines={1}>
            {group.subject || "(no subject)"} · {new Date(group.attempted_at || "").toLocaleString()}
          </Text>
        </View>
        <View style={[s.historyChip, {
          borderColor: group.summary.failed ? colors.error + "60" : colors.success + "60",
          backgroundColor: group.summary.failed ? colors.error + "20" : colors.success + "20",
        }]}>
          <Text style={[s.historyChipText, {
            color: group.summary.failed ? colors.error : colors.success,
          }]}>
            {summaryBits.join(" · ") || group.recipients[0]?.status?.toUpperCase() || "SENT"}
          </Text>
        </View>
      </Pressable>
      {open && isBatch ? (
        <View style={{ gap: 3, marginTop: 4, paddingLeft: 12 }}>
          {group.recipients.map((r) => (
            <View key={r.send_id} style={[s.historyRow, { backgroundColor: colors.surface }]}>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={s.historyMeta} numberOfLines={1}>
                  {r.recipient_email}
                  {r.recipient_name ? ` · ${r.recipient_name}` : ""}
                </Text>
              </View>
              <Text style={[s.historyChipText, {
                color: r.opened_at ? colors.success
                  : r.delivered_at ? colors.brand
                  : r.status === "failed" ? colors.error
                  : colors.onSurfaceSecondary,
              }]}>
                {r.opened_at ? "OPENED" : r.delivered_at ? "DELIVERED" : (r.status || "").toUpperCase()}
              </Text>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}
