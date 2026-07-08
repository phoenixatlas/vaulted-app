import { Stack, useRouter } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import * as Notifications from "expo-notifications";
import * as Linking from "expo-linking";
import { useEffect } from "react";
import { LogBox, Platform } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { GestureHandlerRootView } from "react-native-gesture-handler";

import { useIconFonts } from "@/src/hooks/use-icon-fonts";
import { AuthProvider } from "@/src/lib/auth";
import { I18nProvider } from "@/src/lib/i18n";
import { BiometricGate } from "@/src/components/BiometricGate";
import { captureRefCodeFromUrl } from "@/src/lib/refCode";

LogBox.ignoreAllLogs(true);
SplashScreen.preventAutoHideAsync();

// ---- PUSH NOTIFICATIONS (module scope, must run before any component) ------
if (Platform.OS !== "web") {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowAlert: true,
      shouldPlaySound: true,
      shouldSetBadge: false,
      shouldShowBanner: true,
      shouldShowList: true,
    }),
  });
}
if (Platform.OS === "android") {
  Notifications.setNotificationChannelAsync("default", {
    name: "Vaulted Alerts",
    importance: Notifications.AndroidImportance.MAX,
    sound: "default",
    vibrationPattern: [0, 250, 250, 250],
    lightColor: "#C9A35B",
  });
}

function navigateToUrl(router: ReturnType<typeof useRouter>, url: string) {
  if (url.startsWith("http")) Linking.openURL(url).catch(() => undefined);
  else router.push(url as never);
}

export default function RootLayout() {
  const [loaded, error] = useIconFonts();
  const router = useRouter();

  useEffect(() => {
    if (loaded || error) {
      SplashScreen.hideAsync();
    }
  }, [loaded, error]);

  // Capture ?ref=CODE from the initial URL (web) or deep-link (native) and
  // stash it in AsyncStorage so the register screen can pick it up.
  useEffect(() => {
    captureRefCodeFromUrl().catch(() => undefined);
  }, []);

  // Notification tap handlers — web-guarded
  useEffect(() => {
    if (Platform.OS === "web") return;

    const tapSub = Notifications.addNotificationResponseReceivedListener((response) => {
      const data = (response.notification.request.content.data || {}) as Record<string, unknown>;
      const url = (data.deeplink || data.action_url) as string | undefined;
      if (url) navigateToUrl(router, url);
    });

    Notifications.getLastNotificationResponseAsync().then((response) => {
      if (!response) return;
      const data = (response.notification.request.content.data || {}) as Record<string, unknown>;
      const url = (data.deeplink || data.action_url) as string | undefined;
      if (url) navigateToUrl(router, url);
    });

    return () => { tapSub.remove(); };
  }, [router]);

  if (!loaded && !error) return null;

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <I18nProvider>
          <AuthProvider>
            <BiometricGate>
              <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: "#FBF8F2" } }} />
            </BiometricGate>
          </AuthProvider>
        </I18nProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
