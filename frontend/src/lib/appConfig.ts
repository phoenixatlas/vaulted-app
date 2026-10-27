import { useEffect, useState } from "react";
import { api } from "@/src/lib/api";

export type AppConfig = {
  beta_test_mode: boolean;
  payout_provider: "flutterwave" | "kotani" | "yellowcard";
  payout_provider_label: string;
  stripe_mode: "test" | "live" | "off";
};

// Module-level cache so every screen shares one fetch per app session.
let cached: AppConfig | null = null;
let inflight: Promise<AppConfig | null> | null = null;

function load(): Promise<AppConfig | null> {
  if (!inflight) {
    inflight = api<AppConfig>("/app/config")
      .then((c) => { cached = c; return c; })
      .catch(() => { inflight = null; return null; });
  }
  return inflight;
}

export function useAppConfig(): AppConfig | null {
  const [cfg, setCfg] = useState<AppConfig | null>(cached);
  useEffect(() => {
    if (!cached) load().then((c) => c && setCfg(c));
  }, []);
  return cfg;
}
