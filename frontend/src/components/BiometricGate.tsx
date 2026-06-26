// Locks the app behind a biometric prompt whenever a logged-in user has
// `biometric_enabled` and (a) the app first mounts, or (b) the app returns
// from the background. Lightweight, no extra deps.

import React, { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, AppState, AppStateStatus, Platform, Pressable, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "@/src/lib/auth";
import { authenticate, getCapabilities, labelFor, BiometricCapabilities } from "@/src/lib/biometric";
import { colors, radius, spacing } from "@/src/lib/theme";

const BACKGROUND_LOCK_MS = 30_000; // re-lock after 30s in background

export function BiometricGate({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const [locked, setLocked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [caps, setCaps] = useState<BiometricCapabilities | null>(null);
  const lastBgAt = useRef<number | null>(null);
  const initLockedFor = useRef<string | null>(null); // user id we've already gated on mount

  // Load capabilities once (cheap, native-only)
  useEffect(() => { getCapabilities().then(setCaps); }, []);

  const shouldGate = !!user?.biometric_enabled && !!caps?.available;

  // Initial lock when user first becomes available
  useEffect(() => {
    if (loading) return;
    if (!user) { setLocked(false); initLockedFor.current = null; return; }
    if (shouldGate && initLockedFor.current !== user.id) {
      initLockedFor.current = user.id;
      setLocked(true);
    }
  }, [user, loading, shouldGate]);

  // Lock when returning from background after threshold
  useEffect(() => {
    if (!shouldGate) return;
    const sub = AppState.addEventListener("change", (next: AppStateStatus) => {
      if (next === "background" || next === "inactive") {
        lastBgAt.current = Date.now();
      } else if (next === "active") {
        const elapsed = lastBgAt.current ? Date.now() - lastBgAt.current : 0;
        if (elapsed >= BACKGROUND_LOCK_MS) setLocked(true);
        lastBgAt.current = null;
      }
    });
    return () => sub.remove();
  }, [shouldGate]);

  const unlock = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    try {
      const res = await authenticate({ reason: "Unlock Vaulted" });
      if (res.success) setLocked(false);
    } finally {
      setBusy(false);
    }
  }, [busy]);

  // Auto-prompt the moment the lock appears
  useEffect(() => { if (locked) unlock(); }, [locked, unlock]);

  if (!locked) return <>{children}</>;

  const kind = caps?.primary ?? "generic";
  const icon: any = kind === "face" ? "scan-outline" : kind === "fingerprint" ? "finger-print" : "lock-closed";
  const label = labelFor(kind, Platform);

  return (
    <>
      {children}
      <View style={[s.overlay, { pointerEvents: "auto" } as any]}>
        <View style={s.card}>
          <View style={s.iconWrap}>
            <Ionicons name={icon} size={42} color={colors.brand} />
          </View>
          <Text style={s.title}>Vaulted is locked</Text>
          <Text style={s.subtitle}>Use {label} to continue</Text>
          <Pressable
            testID="biometric-unlock-cta"
            disabled={busy}
            onPress={unlock}
            style={({ pressed }) => [s.cta, pressed && { opacity: 0.85 }]}
          >
            {busy
              ? <ActivityIndicator color="#fff" />
              : <Text style={s.ctaText}>Unlock with {label}</Text>}
          </Pressable>
          <Pressable
            testID="biometric-logout"
            onPress={async () => { setLocked(false); await logout(); }}
            style={s.altBtn}
          >
            <Text style={s.altText}>Sign out</Text>
          </Pressable>
        </View>
      </View>
    </>
  );
}

const s = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(17,20,18,0.96)",
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.xl,
    zIndex: 9999,
  },
  card: {
    width: "100%",
    maxWidth: 360,
    alignItems: "center",
    backgroundColor: colors.surface,
    paddingVertical: spacing.xxl,
    paddingHorizontal: spacing.xl,
    borderRadius: radius.lg,
  },
  iconWrap: {
    width: 84, height: 84, borderRadius: 42,
    backgroundColor: colors.brandTertiary,
    alignItems: "center", justifyContent: "center",
    marginBottom: spacing.lg,
  },
  title: { fontSize: 20, fontWeight: "700", color: colors.onSurface, marginBottom: 6, letterSpacing: -0.3 },
  subtitle: { fontSize: 14, color: colors.onSurfaceSecondary, marginBottom: spacing.xl },
  cta: {
    width: "100%",
    backgroundColor: colors.brand,
    borderRadius: radius.md,
    paddingVertical: 14,
    alignItems: "center",
    marginBottom: spacing.sm,
  },
  ctaText: { color: "#0F0B08", fontSize: 15, fontWeight: "600" },
  altBtn: { paddingVertical: spacing.sm, paddingHorizontal: spacing.md },
  altText: { color: colors.onSurfaceTertiary, fontSize: 13, fontWeight: "500" },
});
