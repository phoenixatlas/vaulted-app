// Thin, web-safe wrapper around expo-local-authentication.
// On web (or when biometrics aren't available), capability checks return false
// and authenticate() resolves to { success: true } so flows aren't dead-ended.
import { Platform } from "react-native";

type Module = typeof import("expo-local-authentication");

let _mod: Module | null = null;
function mod(): Module | null {
  if (Platform.OS === "web") return null;
  if (_mod) return _mod;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    _mod = require("expo-local-authentication") as Module;
    return _mod;
  } catch {
    return null;
  }
}

export type BiometricKind = "face" | "fingerprint" | "iris" | "generic";

export type BiometricCapabilities = {
  available: boolean;       // device has hardware AND has enrolled biometrics
  hasHardware: boolean;
  isEnrolled: boolean;
  kinds: BiometricKind[];   // best label to show in UI (Face ID / Touch ID / Fingerprint)
  primary: BiometricKind;
};

export async function getCapabilities(): Promise<BiometricCapabilities> {
  const m = mod();
  if (!m) {
    return { available: false, hasHardware: false, isEnrolled: false, kinds: [], primary: "generic" };
  }
  const [hasHardware, isEnrolled, types] = await Promise.all([
    m.hasHardwareAsync(),
    m.isEnrolledAsync(),
    m.supportedAuthenticationTypesAsync(),
  ]);
  const kinds: BiometricKind[] = types.map((t) => {
    switch (t) {
      case m.AuthenticationType.FACIAL_RECOGNITION: return "face";
      case m.AuthenticationType.FINGERPRINT: return "fingerprint";
      case m.AuthenticationType.IRIS: return "iris";
      default: return "generic";
    }
  });
  const primary: BiometricKind = kinds.includes("face")
    ? "face"
    : kinds.includes("fingerprint")
      ? "fingerprint"
      : kinds[0] ?? "generic";
  return { available: hasHardware && isEnrolled, hasHardware, isEnrolled, kinds, primary };
}

export function labelFor(kind: BiometricKind, platform: typeof Platform = Platform): string {
  if (kind === "face") return platform.OS === "ios" ? "Face ID" : "Face Unlock";
  if (kind === "fingerprint") return platform.OS === "ios" ? "Touch ID" : "Fingerprint";
  if (kind === "iris") return "Iris";
  return "Biometrics";
}

export async function authenticate(opts?: {
  reason?: string;
  fallbackLabel?: string;
  cancelLabel?: string;
}): Promise<{ success: boolean; error?: string }> {
  const m = mod();
  if (!m) {
    // Web / unsupported: skip biometrics, treat as already authenticated.
    return { success: true };
  }
  try {
    const res = await m.authenticateAsync({
      promptMessage: opts?.reason ?? "Unlock Vaulted",
      fallbackLabel: opts?.fallbackLabel ?? "Use passcode",
      cancelLabel: opts?.cancelLabel ?? "Cancel",
      disableDeviceFallback: false,
    });
    if (res.success) return { success: true };
    return { success: false, error: (res as any).error ?? "auth_failed" };
  } catch (e: any) {
    return { success: false, error: e?.message ?? "auth_failed" };
  }
}
