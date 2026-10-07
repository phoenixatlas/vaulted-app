/**
 * LetterheadCard — reusable letterhead template downloads (DOCX + PDF).
 */
import { View, Text, Pressable, Linking, Platform } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { API_BASE } from "@/src/lib/api";
import { colors } from "@/src/lib/theme";
import { s } from "./styles";

export function LetterheadCard() {
  const open = (url: string) => {
    if (Platform.OS === "web") window.open(url, "_blank");
    else Linking.openURL(url).catch(() => {});
  };
  return (
    <View style={s.card}>
      <Text style={s.cardTitle}>Company letterhead</Text>
      <Text style={s.subtle}>
        Download your branded Phoenix-Atlas / Vaulted letterhead. The DOCX
        is editable in Word Online — drop it in OneDrive and the gold
        header + Companies House footer repeat on every page you add.
      </Text>
      <Pressable style={s.toolRow} onPress={() => open(`${API_BASE}/api/letterhead.docx`)}>
        <Ionicons name="document-text-outline" size={18} color={colors.brand} />
        <View style={{ flex: 1 }}>
          <Text style={s.toolTitle}>Editable Word template (.docx)</Text>
          <Text style={s.toolSub}>Save to OneDrive · type over the placeholders</Text>
        </View>
        <Ionicons name="download-outline" size={16} color={colors.onSurfaceTertiary} />
      </Pressable>
      <Pressable style={s.toolRow} onPress={() => open(`${API_BASE}/api/letterhead.pdf`)}>
        <Ionicons name="document-outline" size={18} color={colors.brand} />
        <View style={{ flex: 1 }}>
          <Text style={s.toolTitle}>Print-ready A4 PDF</Text>
          <Text style={s.toolSub}>Overlay in Pages/Word or print and sign</Text>
        </View>
        <Ionicons name="download-outline" size={16} color={colors.onSurfaceTertiary} />
      </Pressable>
    </View>
  );
}
