/**
 * KotaniSmokeTestCard — one-tap end-to-end validator for the offramp rail.
 * Fires rate-quote → customer-create → booking → dispatcher through the
 * *real* Kotani sandbox so operators can see exactly where things break.
 * Especially useful while we're waiting on Kotani support to flip
 * `integratorEnabled` — this card shows the per-service error payload so
 * you can forward it verbatim in the support ticket.
 */
import { View, Text, Pressable, ActivityIndicator } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, spacing } from "@/src/lib/theme";
import { s } from "./styles";
import type { SmokeStep, SmokeTestResp } from "./types";

type Props = {
  result: SmokeTestResp | null;
  running: boolean;
  corridor: string;
  onRun: (corridor: string) => void;
};

export function KotaniSmokeTestCard({ result, running, corridor, onRun }: Props) {
  const CORRIDORS = ["KE", "NG", "GH", "UG", "TZ", "ZA"];

  const verdictColor =
    result?.verdict === "all_green" ? s.smokeVerdictGreen
    : result?.verdict === "partial" ? s.smokeVerdictYellow
    : result?.verdict === "all_failed" ? s.smokeVerdictRed
    : null;

  const verdictText =
    result?.verdict === "all_green"
      ? "All stages passed. The offramp rail is fully live for this corridor."
      : result?.verdict === "partial"
      ? "Some stages blocked — check the step details below and forward any Kotani error payloads to their support team."
      : result?.verdict === "all_failed"
      ? "Nothing passed. Check your API key, webhook secret, and Render deploy status."
      : "";

  const detailPreview = (step: SmokeStep): string | null => {
    if (!step.detail) return null;
    const d = step.detail;
    if (d.kotani_error) return `Kotani: ${d.kotani_error}`;
    if (d.status_code) return `HTTP ${d.status_code}`;
    if (d.rate_id) return `rateId · ${String(d.rate_id).slice(0, 10)}… · ${d.fiat_amount ?? "—"} ${d.currency ?? ""}`;
    if (d.customer_key) return `customerKey · ${String(d.customer_key).slice(0, 14)}…`;
    if (d.reference_id) return `ref · ${String(d.reference_id).slice(0, 18)}… · ${d.status || "created"}`;
    if (d.status) return String(d.status);
    return null;
  };

  return (
    <View style={s.card}>
      <View style={s.cardHeaderRow}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Ionicons name="flash-outline" size={18} color={colors.brand} />
          <Text style={s.cardTitle}>Offramp smoke test</Text>
        </View>
        {running ? (
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            <ActivityIndicator size="small" color={colors.brand} />
            <Text style={s.subtle}>Running…</Text>
          </View>
        ) : null}
      </View>

      <Text style={s.subtle}>
        Dry-run the full crypto → M-Pesa pipeline against the Kotani sandbox. No real USDC moves.
      </Text>

      {/* Corridor picker */}
      <View style={s.smokeCorridorRow}>
        {CORRIDORS.map((c) => {
          const active = c === corridor;
          return (
            <Pressable
              key={c}
              onPress={() => !running && onRun(c)}
              disabled={running}
              style={[s.corridorPill, active && s.corridorPillActive]}
              hitSlop={6}
            >
              <Text style={[s.corridorPillText, active && s.corridorPillTextActive]}>{c}</Text>
            </Pressable>
          );
        })}
      </View>

      {/* Verdict banner */}
      {result && verdictColor ? (
        <View style={[s.smokeVerdictBox, verdictColor]}>
          <Text style={s.smokeVerdictTitle}>
            {result.verdict === "all_green" ? "🎉 All green" :
             result.verdict === "partial" ? `⚠ ${result.passed} / ${result.total} passed` :
             "✗ All stages failed"}
            {" · "}
            <Text style={{ fontSize: 11, color: colors.onSurfaceSecondary, fontWeight: "500" }}>
              {result.corridor} · {result.elapsed_ms}ms
            </Text>
          </Text>
          <Text style={s.smokeVerdictText}>{verdictText}</Text>
        </View>
      ) : null}

      {/* Step details */}
      {result?.steps.map((step, i) => (
        <View key={i} style={s.smokeStepRow}>
          <Ionicons
            name={step.ok ? "checkmark-circle" : "close-circle"}
            size={18}
            color={step.ok ? colors.success : colors.error}
            style={{ marginTop: 1 }}
          />
          <View style={{ flex: 1, minWidth: 0 }}>
            <View style={{ flexDirection: "row", alignItems: "center" }}>
              <Text style={s.smokeStepName}>{step.name}</Text>
              <Text style={s.smokeStepMs}>{step.ms}ms</Text>
            </View>
            <Text style={s.smokeStepCall}>{step.call}</Text>
            {step.ok ? (
              detailPreview(step) ? <Text style={s.smokeStepDetail}>{detailPreview(step)}</Text> : null
            ) : (
              <Text style={s.smokeStepError}>
                {step.error || detailPreview(step) || "Failed"}
              </Text>
            )}
          </View>
        </View>
      ))}

      {!result && !running ? (
        <View style={[s.emptyBox, { paddingVertical: spacing.md, marginTop: 10 }]}>
          <Ionicons name="flash-outline" size={20} color={colors.onSurfaceTertiary} />
          <Text style={s.emptyText}>
            Tap a corridor above to run a fresh end-to-end test. Takes ~5s.
          </Text>
        </View>
      ) : null}
    </View>
  );
}
