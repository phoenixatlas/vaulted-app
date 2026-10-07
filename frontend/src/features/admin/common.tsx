/**
 * Admin Dashboard — Common tiny components
 * ==========================================
 * ProbeRow and Chip are reused by the Kotani health card and the
 * webhook echo card. Hoisted here so every card consumer imports
 * from one place.
 */
import { View, Text } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors } from "@/src/lib/theme";
import { s } from "./styles";
import type { Probe } from "./types";

export function ProbeRow({
  name, endpoint, probe, showsIntegratorFlag,
}: {
  name: string;
  endpoint: string;
  probe: Probe;
  showsIntegratorFlag?: boolean;
}) {
  return (
    <View style={s.probeRow}>
      <View style={{ flex: 1 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 2 }}>
          <Ionicons
            name={probe.ok ? "checkmark-circle" : "close-circle"}
            size={14}
            color={probe.ok ? colors.success : colors.error}
          />
          <Text style={s.probeName}>{name}</Text>
        </View>
        <Text style={s.probeEndpoint}>{endpoint}</Text>
        <Text style={[s.probeDetail, !probe.ok && s.probeDetailFail]} numberOfLines={3}>
          {probe.detail || (probe.ok ? "ok" : "failed")}
        </Text>
        {showsIntegratorFlag && !probe.ok && probe.error_code === 403 && (
          <View style={{ flexDirection: "row", gap: 6, marginTop: 4, flexWrap: "wrap" }}>
            <Chip label={`service: ${probe.service}`} />
            <Chip label={`integratorEnabled: ${probe.integrator_enabled ? "true" : "false"}`} bad={!probe.integrator_enabled} />
          </View>
        )}
      </View>
    </View>
  );
}

export function Chip({ label, bad }: { label: string; bad?: boolean }) {
  return (
    <View style={[s.chip, bad && s.chipBad]}>
      <Text style={[s.chipText, bad && s.chipTextBad]}>{label}</Text>
    </View>
  );
}
