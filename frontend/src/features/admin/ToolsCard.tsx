/**
 * ToolsCard — quick links to secondary admin screens + biometric toggle.
 */
import { View, Text, Pressable } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { adminBiometric } from "@/src/components/AdminBiometricGate";
import { colors } from "@/src/lib/theme";
import { s } from "./styles";

export function ToolsCard() {
  const router = useRouter();
  return (
    <View style={s.card}>
      <Text style={s.cardTitle}>Tools</Text>
      <Pressable
        style={s.toolRow}
        onPress={() => router.push("/admin/kyc-override")}
      >
        <Ionicons name="shield-checkmark-outline" size={18} color={colors.brand} />
        <View style={{ flex: 1 }}>
          <Text style={s.toolTitle}>Manual EDD approval</Text>
          <Text style={s.toolSub}>Upgrade a user{"\u2019"}s KYC tier with documented evidence</Text>
        </View>
        <Ionicons name="chevron-forward" size={16} color={colors.onSurfaceTertiary} />
      </Pressable>
      <Pressable
        style={s.toolRow}
        onPress={async () => {
          const on = await adminBiometric.isEnabled();
          if (on) await adminBiometric.disable();
          else await adminBiometric.enable();
          router.replace("/admin" as any);
        }}
      >
        <Ionicons name="finger-print" size={18} color={colors.brand} />
        <View style={{ flex: 1 }}>
          <Text style={s.toolTitle}>Biometric lock</Text>
          <Text style={s.toolSub}>
            Toggle Face ID / Touch ID gate for this device (web unaffected).
          </Text>
        </View>
        <Ionicons name="chevron-forward" size={16} color={colors.onSurfaceTertiary} />
      </Pressable>
    </View>
  );
}
