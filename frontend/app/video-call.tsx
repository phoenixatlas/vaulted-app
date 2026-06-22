import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, Image } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useI18n } from "@/src/lib/i18n";
import { colors, spacing, radius } from "@/src/lib/theme";

export default function VideoCall() {
  const { t } = useI18n();
  const router = useRouter();
  const [seconds, setSeconds] = useState(0);
  const [muted, setMuted] = useState(false);
  const [camOn, setCamOn] = useState(true);

  useEffect(() => {
    const it = setInterval(() => setSeconds((x) => x + 1), 1000);
    return () => clearInterval(it);
  }, []);

  const fmt = (n: number) => `${Math.floor(n / 60).toString().padStart(2, "0")}:${(n % 60).toString().padStart(2, "0")}`;

  return (
    <View style={s.root}>
      <Image
        source={{ uri: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?crop=entropy&cs=srgb&fm=jpg&w=900&q=70" }}
        style={s.bg}
      />
      <View style={s.scrim} />
      <SafeAreaView style={s.safe} edges={["top", "bottom"]}>
        <View style={s.topBar}>
          <View style={s.encPill}>
            <Ionicons name="lock-closed" size={11} color="#fff" />
            <Text style={s.encText}>{t("encrypted")}</Text>
          </View>
          <Text style={s.timer}>{fmt(seconds)}</Text>
        </View>

        <View style={s.pip}>
          <Ionicons name="person" size={36} color="#fff" />
        </View>

        <View style={s.bottomBar}>
          <Pressable testID="call-mute" onPress={() => setMuted(!muted)} style={[s.ctrl, muted && s.ctrlOn]}>
            <Ionicons name={muted ? "mic-off" : "mic"} size={22} color={muted ? colors.error : "#fff"} />
          </Pressable>
          <Pressable testID="call-cam" onPress={() => setCamOn(!camOn)} style={[s.ctrl, !camOn && s.ctrlOn]}>
            <Ionicons name={camOn ? "videocam" : "videocam-off"} size={22} color={!camOn ? colors.error : "#fff"} />
          </Pressable>
          <Pressable testID="call-end" onPress={() => router.back()} style={s.endBtn}>
            <Ionicons name="call" size={24} color="#fff" style={{ transform: [{ rotate: "135deg" }] }} />
          </Pressable>
        </View>
      </SafeAreaView>
    </View>
  );
}
const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#000" },
  bg: { ...StyleSheet.absoluteFillObject, width: "100%", height: "100%", resizeMode: "cover" },
  scrim: { ...StyleSheet.absoluteFillObject, backgroundColor: "rgba(0,0,0,0.3)" },
  safe: { flex: 1, justifyContent: "space-between" },
  topBar: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: spacing.xl, paddingTop: spacing.md },
  encPill: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 5, borderRadius: radius.pill, backgroundColor: "rgba(255,255,255,0.16)" },
  encText: { color: "#fff", fontSize: 11, fontWeight: "600" },
  timer: { color: "#fff", fontSize: 14, fontWeight: "600", backgroundColor: "rgba(0,0,0,0.4)", paddingHorizontal: 12, paddingVertical: 5, borderRadius: radius.pill },
  pip: { position: "absolute", top: 80, right: 20, width: 90, height: 120, borderRadius: radius.md, backgroundColor: "rgba(255,255,255,0.15)", alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: "rgba(255,255,255,0.3)" },
  bottomBar: { flexDirection: "row", justifyContent: "center", alignItems: "center", gap: spacing.lg, paddingBottom: spacing.xl, paddingHorizontal: spacing.xl },
  ctrl: { width: 56, height: 56, borderRadius: 28, backgroundColor: "rgba(255,255,255,0.18)", alignItems: "center", justifyContent: "center" },
  ctrlOn: { backgroundColor: "#fff" },
  endBtn: { width: 64, height: 64, borderRadius: 32, backgroundColor: colors.error, alignItems: "center", justifyContent: "center" },
});
