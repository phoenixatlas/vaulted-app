/**
 * AdminBiometricGate — second-factor biometric gate specifically for the
 * /admin screen. Independent of the wallet-level BiometricGate so admins
 * can disable one without affecting the other.
 *
 * Flow:
 *   1. On mount: look up `admin_biometric_enabled` in SecureStore.
 *   2. If disabled: render children + show one-time enroll nudge.
 *   3. If enabled + hardware available: fire Face ID / Touch ID prompt
 *      immediately. Children only mount after success.
 *   4. On web (no biometric API) or hardware unavailable: pass through.
 *
 * The gate is opt-in; new installs show a dismissable nudge, nothing is
 * forced. Can be disabled from the admin screen's ⚙ icon.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { View, Text, Pressable, StyleSheet, Platform, ActivityIndicator } from "react-native";
import * as LocalAuthentication from "expo-local-authentication";
import { Ionicons } from "@expo/vector-icons";
import { storage } from "@/src/utils/storage";
import { colors, spacing, radius } from "@/src/lib/theme";

const ENABLED_KEY = "admin_biometric_enabled";
const DISMISSED_KEY = "admin_biometric_dismissed";

type HardwareState = "checking" | "available" | "unavailable" | "web";

function useBiometricHardware(): HardwareState {
  const [state, setState] = useState<HardwareState>("checking");
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (Platform.OS === "web") {
        if (!cancelled) setState("web");
        return;
      }
      try {
        const hasHW = await LocalAuthentication.hasHardwareAsync();
        const enrolled = await LocalAuthentication.isEnrolledAsync();
        if (!cancelled) setState(hasHW && enrolled ? "available" : "unavailable");
      } catch {
        if (!cancelled) setState("unavailable");
      }
    })();
    return () => { cancelled = true; };
  }, []);
  return state;
}

export const adminBiometric = {
  isEnabled: async () => (await storage.secureGet<string>(ENABLED_KEY, "")) === "1",
  enable: () => storage.secureSet(ENABLED_KEY, "1"),
  disable: () => storage.secureRemove(ENABLED_KEY),
};

export function AdminBiometricGate({ children }: { children: React.ReactNode }) {
  const hw = useBiometricHardware();
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [unlocked, setUnlocked] = useState(false);
  const [prompting, setPrompting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const on = await adminBiometric.isEnabled();
      if (!cancelled) setEnabled(on);
    })();
    return () => { cancelled = true; };
  }, []);

  const prompt = useCallback(async () => {
    setErr(null);
    setPrompting(true);
    try {
      const res = await LocalAuthentication.authenticateAsync({
        promptMessage: "Unlock Vaulted admin",
        fallbackLabel: "Use device passcode",
        disableDeviceFallback: false,
      });
      if (res.success) {
        setUnlocked(true);
      } else if (res.error === "user_cancel" || res.error === "system_cancel") {
        setErr("Authentication cancelled.");
      } else {
        setErr("Authentication failed. Please try again.");
      }
    } catch (e: any) {
      setErr(e?.message || "Authentication error");
    } finally {
      setPrompting(false);
    }
  }, []);

  useEffect(() => {
    if (enabled && hw === "available" && !unlocked && !prompting) {
      prompt();
    }
  }, [enabled, hw, unlocked, prompt, prompting]);

  // Pass through on web / no hardware / disabled by user.
  if (hw === "web" || hw === "unavailable" || enabled === false) {
    return <>{children}</>;
  }
  if (enabled === null || hw === "checking") {
    return (
      <View style={s.wrap}>
        <ActivityIndicator color={colors.brand} />
      </View>
    );
  }
  if (unlocked) return <>{children}</>;

  return (
    <View style={s.wrap}>
      <View style={s.card}>
        <View style={s.icon}>
          <Ionicons name="finger-print" size={34} color={colors.brand} />
        </View>
        <Text style={s.title}>Verify to continue</Text>
        <Text style={s.body}>
          Admin tools are gated behind biometric verification on this device. Use Face ID or Touch ID to continue.
        </Text>
        <Pressable onPress={prompt} disabled={prompting} style={s.btn}>
          {prompting ? (
            <ActivityIndicator size="small" color={colors.onBrand} />
          ) : (
            <>
              <Ionicons name="finger-print" size={16} color={colors.onBrand} />
              <Text style={s.btnText}>Unlock with biometrics</Text>
            </>
          )}
        </Pressable>
        {err ? <Text style={s.err}>{err}</Text> : null}
      </View>
    </View>
  );
}

/** One-time enroll nudge — rendered inside the admin screen so new admins
 * see "Enable Face ID?" after their first JWT login. Dismisses forever
 * once the user picks either option. */
export function AdminBiometricNudge() {
  const hw = useBiometricHardware();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (hw !== "available") return;
      const already = await adminBiometric.isEnabled();
      const dismissed = await storage.secureGet<string>(DISMISSED_KEY, "");
      if (!cancelled && !already && !dismissed) setVisible(true);
    })();
    return () => { cancelled = true; };
  }, [hw]);

  if (!visible) return null;

  return (
    <View style={s.nudge}>
      <Ionicons name="finger-print" size={18} color={colors.brand} />
      <View style={{ flex: 1 }}>
        <Text style={s.nudgeTitle}>Enable Face ID / Touch ID for admin?</Text>
        <Text style={s.nudgeBody}>Faster access next time on this device.</Text>
      </View>
      <Pressable
        onPress={async () => {
          await storage.secureSet(DISMISSED_KEY, "1");
          setVisible(false);
        }}
        hitSlop={6}
        style={s.nudgeSkip}
      >
        <Text style={s.nudgeSkipText}>Not now</Text>
      </Pressable>
      <Pressable
        onPress={async () => {
          await adminBiometric.enable();
          setVisible(false);
        }}
        hitSlop={6}
        style={s.nudgeAccept}
      >
        <Text style={s.nudgeAcceptText}>Enable</Text>
      </Pressable>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: {
    flex: 1, alignItems: "center", justifyContent: "center",
    paddingHorizontal: 24, backgroundColor: colors.background,
  },
  card: {
    width: "100%", maxWidth: 420,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1, borderColor: colors.border,
    padding: 28, alignItems: "center",
  },
  icon: {
    width: 68, height: 68, borderRadius: 34,
    backgroundColor: colors.brand + "20",
    alignItems: "center", justifyContent: "center",
    marginBottom: 16,
  },
  title: { fontSize: 19, fontWeight: "800", color: colors.onSurface, marginBottom: 8 },
  body: {
    fontSize: 13, color: colors.onSurfaceSecondary,
    lineHeight: 19, textAlign: "center", marginBottom: 22,
  },
  btn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
    paddingVertical: 11, paddingHorizontal: 24,
    backgroundColor: colors.brand,
    borderRadius: radius.md,
    minWidth: 200, minHeight: 44,
  },
  btnText: { color: colors.onBrand, fontSize: 14, fontWeight: "700" },
  err: { fontSize: 12, color: colors.error, marginTop: 12, textAlign: "center" },

  nudge: {
    marginHorizontal: spacing.md, marginTop: spacing.sm,
    flexDirection: "row", alignItems: "center", gap: 8,
    paddingHorizontal: 12, paddingVertical: 10,
    backgroundColor: colors.brand + "15",
    borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.brand + "40",
  },
  nudgeTitle: { fontSize: 12, fontWeight: "700", color: colors.onSurface },
  nudgeBody: { fontSize: 10.5, color: colors.onSurfaceSecondary, marginTop: 2 },
  nudgeSkip: {
    paddingHorizontal: 10, paddingVertical: 5,
    borderRadius: radius.pill, backgroundColor: "transparent",
  },
  nudgeSkipText: { fontSize: 11, color: colors.onSurfaceSecondary, fontWeight: "600" },
  nudgeAccept: {
    paddingHorizontal: 10, paddingVertical: 5,
    borderRadius: radius.pill, backgroundColor: colors.brand,
  },
  nudgeAcceptText: { fontSize: 11, color: colors.onBrand, fontWeight: "700" },
});
