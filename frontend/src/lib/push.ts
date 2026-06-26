// Vaulted push registration — relays device tokens to the backend so the
// Emergent push service can target this user. Web/no-hardware safe — no-ops
// gracefully on web. Implements the handle_permissions_contract: contextual
// ask (called only on login/app-resume), respects canAskAgain, and surfaces an
// "Open Settings" hint when denied. The actual UI prompt is up to the caller;
// this helper just returns the outcome.

import { Platform, Linking, Alert } from "react-native";

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || "";

type RegisterResult = {
  status: "registered" | "denied" | "blocked" | "skipped" | "error";
  message?: string;
};

let _registeredForUser: string | null = null;

export async function registerForPush(userId: string): Promise<RegisterResult> {
  if (Platform.OS === "web") return { status: "skipped", message: "Web preview — pushes are device-only." };
  if (_registeredForUser === userId) return { status: "registered" };

  try {
    // Lazy require so the module is never loaded on web.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const Notifications = require("expo-notifications") as typeof import("expo-notifications");
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const Device = require("expo-device") as typeof import("expo-device");

    if (!Device.isDevice) {
      return { status: "skipped", message: "Push works on physical devices only." };
    }

    let { status, canAskAgain } = await Notifications.getPermissionsAsync();
    if (status !== "granted") {
      if (!canAskAgain) {
        return {
          status: "blocked",
          message: "Notifications are off. Enable them in Settings to get chat & multi-sig alerts.",
        };
      }
      const req = await Notifications.requestPermissionsAsync();
      status = req.status;
      if (status !== "granted") return { status: "denied" };
    }

    const tokenResp = await Notifications.getDevicePushTokenAsync();
    const base = BACKEND ? `${BACKEND}/api` : "/api";
    const resp = await fetch(`${base}/register-push`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: userId,
        platform: Platform.OS,
        device_token: tokenResp.data,
      }),
    });
    if (!resp.ok) {
      return { status: "error", message: `Backend rejected token (${resp.status})` };
    }
    _registeredForUser = userId;
    return { status: "registered" };
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    return { status: "error", message: msg };
  }
}

export function openNotificationSettings() {
  if (Platform.OS === "web") return;
  Linking.openSettings().catch(() => {
    Alert.alert("Couldn't open Settings", "Please open Settings → Vaulted → Notifications manually.");
  });
}
