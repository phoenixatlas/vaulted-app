/**
 * KotaniWebhookEchoCard — surfaces the raw deliveries that landed on
 * /api/offramp/callback plus a step-by-step setup checklist. First
 * stop for diagnosing "my Kotani dashboard says no webhooks are
 * firing" — answers (1) did Kotani even POST anything? (2) is the
 * signature verifying? (3) are the right event types subscribed?
 */
import { useCallback } from "react";
import { View, Text, Pressable, ActivityIndicator, Platform } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, spacing } from "@/src/lib/theme";
import { s } from "./styles";
import type { KotaniWebhookEchoResp } from "./types";

type Props = {
  data: KotaniWebhookEchoResp | null;
  loading: boolean;
  errorMsg?: string;
  onReplay: () => void;
  replayStatus?: string | null;
};

export function KotaniWebhookEchoCard({
  data, loading, errorMsg, onReplay, replayStatus,
}: Props) {
  const copyUrl = useCallback(() => {
    if (!data?.expected_webhook_url) return;
    if (Platform.OS === "web" && typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(data.expected_webhook_url).catch(() => {});
    }
  }, [data]);

  if (loading && !data) {
    return (
      <View style={s.card}>
        <Text style={s.cardTitle}>Kotani webhooks</Text>
        <View style={s.loadingBox}>
          <ActivityIndicator color={colors.brand} />
          <Text style={s.loadingText}>Checking deliveries…</Text>
        </View>
      </View>
    );
  }
  if (!data) {
    return (
      <View style={s.card}>
        <Text style={s.cardTitle}>Kotani webhooks</Text>
        <Text style={s.subtle}>
          Unavailable. {errorMsg ? `(${errorMsg})` : "Endpoint returned an error."}
        </Text>
      </View>
    );
  }

  const { config_checklist: cc, deliveries, expected_webhook_url } = data;
  const noneYet = data.total_received === 0;

  const ChecklistRow = ({ ok, label }: { ok: boolean; label: string }) => (
    <View style={s.checklistRow}>
      <Ionicons
        name={ok ? "checkmark-circle" : "ellipse-outline"}
        size={16}
        color={ok ? colors.success : colors.onSurfaceTertiary}
      />
      <Text style={[s.checklistText, !ok && { color: colors.onSurfaceSecondary }]}>
        {label}
      </Text>
    </View>
  );

  return (
    <View style={s.card}>
      <View style={s.cardHeaderRow}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Ionicons name="radio-outline" size={18} color={colors.brand} />
          <Text style={s.cardTitle}>Kotani webhooks</Text>
        </View>
        <View style={[
          s.modePill,
          noneYet ? s.modePillMock : (cc.signature_invalid_count > 0 ? s.modePillLive : s.modePillReady),
        ]}>
          <Text style={s.modePillText}>
            {noneYet ? "AWAITING" : cc.signature_invalid_count > 0 ? "SIG ERRORS" : "RECEIVING"}
          </Text>
        </View>
      </View>

      {/* Expected URL block — the thing to paste into Kotani dashboard */}
      <View style={s.webhookUrlBox}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <Text style={s.microLabel}>WEBHOOK URL · PASTE INTO KOTANI DASHBOARD</Text>
          <View style={[
            s.hostBadge,
            data.host_type === "render" && s.hostBadgeOk,
            data.host_type === "preview" && s.hostBadgeWarn,
            (data.host_type === "unset" || data.host_type === "localhost") && s.hostBadgeErr,
          ]}>
            <Text style={s.hostBadgeText}>{data.host_label}</Text>
          </View>
        </View>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginTop: 4 }}>
          <Text selectable style={s.webhookUrl} numberOfLines={2}>
            {expected_webhook_url || "⚠ APP_PUBLIC_URL env var not set"}
          </Text>
          {expected_webhook_url && Platform.OS === "web" ? (
            <Pressable onPress={copyUrl} hitSlop={8} style={s.copyBtn}>
              <Ionicons name="copy-outline" size={14} color={colors.brand} />
            </Pressable>
          ) : null}
        </View>
        {data.host_warning ? (
          <View style={s.hostWarnBox}>
            <Ionicons name="warning-outline" size={13} color={colors.warning} />
            <Text style={s.hostWarnText}>{data.host_warning}</Text>
          </View>
        ) : null}
      </View>

      {/* Setup checklist */}
      <Text style={[s.microLabel, { marginTop: spacing.md }]}>SETUP CHECKLIST</Text>
      <View style={{ marginTop: 6, gap: 4 }}>
        <ChecklistRow ok={cc.api_key_configured} label="API key configured in backend .env" />
        <ChecklistRow ok={cc.webhook_secret_configured} label="Webhook signing secret in backend .env" />
        <ChecklistRow ok={cc.webhook_url_registered} label={
          cc.webhook_url_registered
            ? `${data.total_received} delivery(ies) received`
            : "Kotani is not posting to this URL yet"
        } />
        <ChecklistRow
          ok={cc.signature_invalid_count === 0 && cc.webhook_url_registered}
          label={
            cc.signature_invalid_count > 0
              ? `${cc.signature_invalid_count} delivery(ies) failed signature verification`
              : "Signatures verifying cleanly"
          }
        />
      </View>

      {/* Recommended events to subscribe */}
      <Text style={[s.microLabel, { marginTop: spacing.md }]}>SUBSCRIBE TO THESE EVENTS</Text>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
        {data.recommended_events.map((e) => (
          <View key={e} style={s.eventChip}>
            <Text style={s.eventChipText}>{e}</Text>
          </View>
        ))}
      </View>

      {/* Deliveries list */}
      <Text style={[s.microLabel, { marginTop: spacing.md }]}>LATEST DELIVERIES</Text>
      {noneYet ? (
        <View style={[s.emptyBox, { paddingVertical: spacing.md }]}>
          <Ionicons name="hourglass-outline" size={20} color={colors.onSurfaceTertiary} />
          <Text style={s.emptyText}>
            No webhooks received yet. Configure the URL above in Kotani → Settings, then hit &ldquo;Fire test delivery&rdquo;.
          </Text>
        </View>
      ) : (
        <View style={{ gap: 6, marginTop: 6 }}>
          {deliveries.slice(0, 6).map((d, i) => (
            <View key={i} style={s.deliveryRow}>
              <Ionicons
                name={d.signature_valid ? "checkmark-circle" : "close-circle"}
                size={14}
                color={d.signature_valid ? colors.success : colors.error}
              />
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={s.deliveryEvent} numberOfLines={1}>
                  {d.event_header || "(no event header — direct callback)"}
                </Text>
                <Text style={s.deliveryTime}>
                  {new Date(d.received_at).toLocaleString()}
                </Text>
              </View>
            </View>
          ))}
        </View>
      )}

      {/* Replay button — fire a synthetic webhook end-to-end */}
      <View style={s.footerRow}>
        <Text style={s.footerText} numberOfLines={1}>
          {replayStatus || "Verify dispatcher end-to-end:"}
        </Text>
        <Pressable onPress={onReplay} style={s.refreshBtn} hitSlop={8}>
          <Ionicons name="flash" size={14} color={colors.brand} />
          <Text style={s.refreshBtnText}>Fire test delivery</Text>
        </Pressable>
      </View>
    </View>
  );
}
