import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ActivityIndicator, Image } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { WebView } from "react-native-webview";
import { api } from "@/src/lib/api";
import { useI18n } from "@/src/lib/i18n";
import { colors, spacing, radius } from "@/src/lib/theme";

type RoomResp = { configured: boolean; room_url: string | null; token: string | null; message?: string };

export default function VideoCall() {
  const { t } = useI18n();
  const router = useRouter();
  const [room, setRoom] = useState<RoomResp | null>(null);
  const [loading, setLoading] = useState(true);
  const [seconds, setSeconds] = useState(0);
  const [muted, setMuted] = useState(false);
  const [camOn, setCamOn] = useState(true);

  useEffect(() => {
    api<RoomResp>("/calls/room", { method: "POST", body: {} })
      .then(setRoom)
      .catch((e) => setRoom({ configured: false, room_url: null, token: null, message: e?.message }))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const it = setInterval(() => setSeconds((x) => x + 1), 1000);
    return () => clearInterval(it);
  }, []);

  const fmt = (n: number) =>
    `${Math.floor(n / 60).toString().padStart(2, "0")}:${(n % 60).toString().padStart(2, "0")}`;

  // Build full Daily URL with token & pre-set audio/video. Daily Prebuilt loads via room_url.
  const dailyUrl = room?.configured && room.room_url
    ? `${room.room_url}?t=${room.token ?? ""}`
    : null;

  if (loading) {
    return (
      <SafeAreaView style={s.loading} edges={["top", "bottom"]}>
        <ActivityIndicator color="#fff" size="large" />
        <Text style={s.connectingText}>Connecting…</Text>
      </SafeAreaView>
    );
  }

  if (dailyUrl) {
    return (
      <View style={s.root}>
        <WebView
          testID="daily-webview"
          source={{ uri: dailyUrl }}
          style={s.web}
          allowsInlineMediaPlayback
          mediaPlaybackRequiresUserAction={false}
          javaScriptEnabled
          domStorageEnabled
        />
        <SafeAreaView style={s.overlay} pointerEvents="box-none" edges={["top", "bottom"]}>
          <View style={s.topBar}>
            <View style={s.encPill}>
              <Ionicons name="lock-closed" size={11} color="#fff" />
              <Text style={s.encText}>{t("encrypted")} · Daily.co</Text>
            </View>
            <Text style={s.timer}>{fmt(seconds)}</Text>
          </View>
          <View style={s.bottomBar}>
            <Pressable testID="call-end" onPress={() => router.back()} style={s.endBtn}>
              <Ionicons name="call" size={24} color="#fff" style={{ transform: [{ rotate: "135deg" }] }} />
            </Pressable>
          </View>
        </SafeAreaView>
      </View>
    );
  }

  // Daily not configured → show mock call screen with notice
  return (
    <View style={s.root}>
      <Image
        source={{
          uri: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?crop=entropy&cs=srgb&fm=jpg&w=900&q=70",
        }}
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

        <View style={s.notice} testID="daily-notice">
          <Ionicons name="alert-circle" size={16} color="#fff" />
          <Text style={s.noticeText}>
            DAILY_API_KEY not set — showing demo UI. Add the key in /app/backend/.env to enable real calls.
          </Text>
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
  loading: { flex: 1, backgroundColor: "#000", alignItems: "center", justifyContent: "center", gap: 12 },
  connectingText: { color: "#fff", fontSize: 14 },
  web: { ...StyleSheet.absoluteFillObject },
  overlay: { ...StyleSheet.absoluteFillObject, justifyContent: "space-between" },
  bg: { ...StyleSheet.absoluteFillObject, width: "100%", height: "100%", resizeMode: "cover" },
  scrim: { ...StyleSheet.absoluteFillObject, backgroundColor: "rgba(0,0,0,0.3)" },
  safe: { flex: 1, justifyContent: "space-between" },
  topBar: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: spacing.xl, paddingTop: spacing.md },
  encPill: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 5, borderRadius: radius.pill, backgroundColor: "rgba(255,255,255,0.16)" },
  encText: { color: "#fff", fontSize: 11, fontWeight: "600" },
  timer: { color: "#fff", fontSize: 14, fontWeight: "600", backgroundColor: "rgba(0,0,0,0.4)", paddingHorizontal: 12, paddingVertical: 5, borderRadius: radius.pill },
  notice: { flexDirection: "row", gap: 8, alignItems: "flex-start", margin: spacing.xl, padding: spacing.md, backgroundColor: "rgba(184,142,20,0.85)", borderRadius: radius.md },
  noticeText: { color: "#fff", fontSize: 12, flex: 1, lineHeight: 16 },
  pip: { position: "absolute", top: 100, right: 20, width: 90, height: 120, borderRadius: radius.md, backgroundColor: "rgba(255,255,255,0.15)", alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: "rgba(255,255,255,0.3)" },
  bottomBar: { flexDirection: "row", justifyContent: "center", alignItems: "center", gap: spacing.lg, paddingBottom: spacing.xl, paddingHorizontal: spacing.xl },
  ctrl: { width: 56, height: 56, borderRadius: 28, backgroundColor: "rgba(255,255,255,0.18)", alignItems: "center", justifyContent: "center" },
  ctrlOn: { backgroundColor: "#fff" },
  endBtn: { width: 64, height: 64, borderRadius: 32, backgroundColor: colors.error, alignItems: "center", justifyContent: "center" },
});
