/**
 * PreviewAcknowledgementGate
 * ==========================
 * A one-time launch modal that requires the user to acknowledge Vaulted's
 * current "preview / waitlist" status BEFORE they can create an account,
 * deposit funds, or send anything.
 *
 * Legal rationale (July 2026):
 *  - Vaulted is not yet FCA-authorized. Everything in the app that looks
 *    like a live money-transfer service is engineering-preview only.
 *  - By making the user tick "I understand this is a preview build and
 *    real funds may be lost / not settled to a recipient" we create a
 *    documented, dated consent event that reduces our exposure under
 *    misleading-communications and financial-promotions rules.
 *  - The acknowledgement is stored in AsyncStorage keyed by a version
 *    string so we can force a re-ack any time the disclosures materially
 *    change (e.g. once we go live, or if we add new corridors).
 *
 * Behaviour:
 *  - On first launch (or after a version bump) the gate renders a
 *    full-screen modal that blocks the underlying navigator until the
 *    user taps "I understand — continue".
 *  - The FCA cryptoasset warning (Oct 2023 exact wording) is included
 *    verbatim, plus a link to the full risk disclosure.
 *  - The modal cannot be dismissed by tapping the backdrop, swiping down,
 *    or Android back button (uses onRequestClose no-op) - the only way
 *    forward is explicit acknowledgement.
 */
import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Linking,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Ionicons } from "@expo/vector-icons";
import { colors, radius, spacing } from "@/src/lib/theme";

// Bump this string any time the disclosure text materially changes; every
// user will be shown the fresh modal on next launch until they re-ack.
const ACK_VERSION = "2026-07-preview-v1";
const ACK_STORAGE_KEY = "vaulted.preview.ack.version";
const RISK_DISCLOSURE_URL = "https://phoenix-atlas.com/risk-disclosure.html";

type Props = { children: React.ReactNode };

export default function PreviewAcknowledgementGate({ children }: Props) {
  // undefined = still loading from AsyncStorage
  // false = user hasn't acknowledged this version -> show modal
  // true = user has acknowledged -> render children
  const [acked, setAcked] = useState<boolean | undefined>(undefined);
  const [saving, setSaving] = useState(false);

  // Load the persisted acknowledgement on mount.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const raw = await AsyncStorage.getItem(ACK_STORAGE_KEY);
        if (cancelled) return;
        setAcked(raw === ACK_VERSION);
      } catch {
        // If AsyncStorage is unavailable (rare), default to showing the
        // modal - safer to over-disclose than under-disclose.
        if (!cancelled) setAcked(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleAcknowledge = useCallback(async () => {
    setSaving(true);
    try {
      await AsyncStorage.setItem(ACK_STORAGE_KEY, ACK_VERSION);
      setAcked(true);
    } catch {
      // Even if persistence fails, dismiss the modal so the user isn't
      // trapped - they'll just see it again on next launch.
      setAcked(true);
    } finally {
      setSaving(false);
    }
  }, []);

  const handleReadFullDisclosure = useCallback(() => {
    Linking.openURL(RISK_DISCLOSURE_URL).catch(() => undefined);
  }, []);

  // While loading, render children as-is (no flash). Once resolved, the
  // Modal below is rendered on top if the user hasn't ack'd.
  return (
    <View style={{ flex: 1 }}>
      {children}
      <Modal
        visible={acked === false}
        animationType={Platform.OS === "web" ? "fade" : "slide"}
        transparent={false}
        onRequestClose={() => {
          /* explicitly non-dismissible: force explicit acknowledgement */
        }}
        statusBarTranslucent
      >
        <View style={s.container} testID="preview-ack-gate">
          <ScrollView
            contentContainerStyle={s.scroll}
            showsVerticalScrollIndicator={false}
          >
            <View style={s.iconWrap}>
              <Ionicons name="shield-outline" size={32} color={colors.brand} />
            </View>
            <Text style={s.eyebrow}>UK fintech in build</Text>
            <Text style={s.title}>Welcome to Vaulted.{"\n"}Before you continue.</Text>

            <View style={s.warningCard}>
              <Text style={s.warningLabel}>Cryptoasset risk warning</Text>
              <Text style={s.warningBody}>
                Don&rsquo;t invest unless you&rsquo;re prepared to lose all the money
                you invest. This is a high-risk investment and you should not
                expect to be protected if something goes wrong.
              </Text>
            </View>

            <Text style={s.sectionTitle}>What Vaulted is right now</Text>
            <View style={s.bullet}>
              <Ionicons name="ellipse" size={6} color={colors.brand} style={s.bulletDot} />
              <Text style={s.bulletText}>
                A <Text style={s.strong}>preview build</Text> of a UK cross-border
                remittance and self-custody crypto app.
              </Text>
            </View>
            <View style={s.bullet}>
              <Ionicons name="ellipse" size={6} color={colors.brand} style={s.bulletDot} />
              <Text style={s.bulletText}>
                <Text style={s.strong}>Not currently authorized</Text> by the
                Financial Conduct Authority (FCA). Live money-transfer services
                will begin only once applicable permissions are in place.
              </Text>
            </View>
            <View style={s.bullet}>
              <Ionicons name="ellipse" size={6} color={colors.brand} style={s.bulletDot} />
              <Text style={s.bulletText}>
                Transfers you initiate in preview mode <Text style={s.strong}>may
                not settle to a real recipient</Text>. Off-ramp partners
                (M-Pesa, mobile-money, bank rails) are in integration.
              </Text>
            </View>
            <View style={s.bullet}>
              <Ionicons name="ellipse" size={6} color={colors.brand} style={s.bulletDot} />
              <Text style={s.bulletText}>
                <Text style={s.strong}>Your keys, your risk.</Text> Vaulted is a
                self-custody wallet. If you lose your recovery phrase, your funds
                are lost permanently.
              </Text>
            </View>
            <View style={s.bullet}>
              <Ionicons name="ellipse" size={6} color={colors.brand} style={s.bulletDot} />
              <Text style={s.bulletText}>
                <Text style={s.strong}>Do not deposit funds you cannot afford to lose.</Text>
              </Text>
            </View>

            <Pressable
              testID="preview-ack-read-more"
              onPress={handleReadFullDisclosure}
              style={s.linkRow}
              accessibilityRole="link"
            >
              <Ionicons name="document-text-outline" size={16} color={colors.brand} />
              <Text style={s.linkText}>Read the full risk disclosure</Text>
              <Ionicons name="open-outline" size={14} color={colors.brand} />
            </Pressable>

            <View style={s.buttonRow}>
              <Pressable
                testID="preview-ack-continue"
                onPress={handleAcknowledge}
                disabled={saving}
                style={({ pressed }) => [
                  s.primaryBtn,
                  pressed && s.primaryBtnPressed,
                  saving && s.primaryBtnDisabled,
                ]}
                accessibilityRole="button"
              >
                {saving ? (
                  <ActivityIndicator color={colors.surface} />
                ) : (
                  <Text style={s.primaryBtnText}>I understand &mdash; continue</Text>
                )}
              </Pressable>
            </View>

            <Text style={s.footnote}>
              By continuing you confirm you&rsquo;ve read and understand the risk
              disclosure and Vaulted&rsquo;s current regulatory status.
            </Text>
          </ScrollView>
        </View>
      </Modal>
    </View>
  );
}

const s = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.surfaceInverse,
  },
  scroll: {
    padding: spacing.xl,
    paddingTop: spacing.xxxl + spacing.md,
    paddingBottom: spacing.xxxl,
  },
  iconWrap: {
    width: 56,
    height: 56,
    borderRadius: radius.pill,
    backgroundColor: "rgba(201, 163, 91, 0.12)",
    borderWidth: 1,
    borderColor: "rgba(201, 163, 91, 0.35)",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.lg,
  },
  eyebrow: {
    color: colors.brandSecondary,
    fontSize: 11,
    letterSpacing: 2,
    textTransform: "uppercase",
    fontWeight: "600",
    marginBottom: spacing.sm,
  },
  title: {
    color: colors.onSurfaceInverse,
    fontSize: 28,
    lineHeight: 34,
    fontWeight: "700",
    marginBottom: spacing.xl,
    letterSpacing: -0.5,
  },
  warningCard: {
    backgroundColor: "#2a1e0a",
    borderWidth: 1,
    borderColor: "rgba(255, 184, 77, 0.35)",
    borderRadius: radius.md,
    padding: spacing.lg,
    marginBottom: spacing.xl,
  },
  warningLabel: {
    color: "#FFB84D",
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 2,
    textTransform: "uppercase",
    marginBottom: spacing.sm,
  },
  warningBody: {
    color: colors.onSurfaceInverse,
    fontSize: 14,
    lineHeight: 21,
  },
  sectionTitle: {
    color: colors.brandSecondary,
    fontSize: 13,
    fontWeight: "600",
    letterSpacing: 0.3,
    marginBottom: spacing.md,
    marginTop: spacing.sm,
  },
  bullet: {
    flexDirection: "row",
    alignItems: "flex-start",
    marginBottom: spacing.md,
    paddingRight: spacing.sm,
  },
  bulletDot: {
    marginTop: 8,
    marginRight: spacing.md,
  },
  bulletText: {
    flex: 1,
    color: colors.onSurfaceInverse,
    fontSize: 14,
    lineHeight: 21,
  },
  strong: {
    fontWeight: "700",
    color: colors.brandTertiary,
  },
  linkRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    marginTop: spacing.lg,
    marginBottom: spacing.xl,
  },
  linkText: {
    color: colors.brand,
    fontSize: 13,
    fontWeight: "600",
    textDecorationLine: "underline",
  },
  buttonRow: {
    marginTop: spacing.sm,
  },
  primaryBtn: {
    backgroundColor: colors.brand,
    paddingVertical: 16,
    borderRadius: radius.pill,
    alignItems: "center",
    justifyContent: "center",
  },
  primaryBtnPressed: {
    backgroundColor: colors.brandHover,
  },
  primaryBtnDisabled: {
    opacity: 0.7,
  },
  primaryBtnText: {
    color: colors.onSurface,
    fontSize: 15,
    fontWeight: "700",
    letterSpacing: 0.2,
  },
  footnote: {
    color: colors.onSurfaceTertiary,
    fontSize: 11,
    lineHeight: 16,
    textAlign: "center",
    marginTop: spacing.lg,
    paddingHorizontal: spacing.md,
  },
});
