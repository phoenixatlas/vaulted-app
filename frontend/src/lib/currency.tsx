/**
 * Display-currency provider.
 *
 * The app's ledger is USD everywhere (wallet.fiat_value, tx.fiat_value,
 * price_usd, etc.). This provider lets the user pick ANY of the
 * supported display currencies and we convert on-the-fly in the UI only.
 *
 * Flow:
 *   1. On mount: read saved pref from AsyncStorage, hydrate rates
 *      cache from AsyncStorage, then kick off a background refresh
 *      from `/api/rates/fiat`.
 *   2. `format(usd)` converts USD→selected currency and returns a
 *      localised string with the right symbol + decimals.
 *   3. Rates refresh every 60 min (and whenever the app foregrounds).
 *
 * We never block the UI on the rate fetch — a stale snapshot is always
 * served, upgraded in-place once the live call returns.
 */
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  ReactNode,
} from "react";
import { AppState } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { api } from "@/src/lib/api";

export type CurrencyCode =
  | "USD" | "GBP" | "EUR"
  | "NGN" | "KES" | "GHS" | "UGX" | "TZS" | "ZMW" | "ZAR";

export type CurrencyMeta = {
  code: CurrencyCode;
  name: string;
  symbol: string;      // Prefix symbol shown next to amount
  flag: string;        // Emoji flag for pickers
  decimals: number;    // Display decimals (NGN/UGX/TZS/ZMW round to 0)
  locale: string;      // Hint for `Number.toLocaleString`
};

// Order matters — list that renders in the Settings picker. UK/EU first
// (our primary senders), then the live African corridors so Nigerian /
// Kenyan / Ghanaian users find theirs instantly.
export const CURRENCIES: CurrencyMeta[] = [
  { code: "USD", name: "US Dollar",       symbol: "$",   flag: "🇺🇸", decimals: 2, locale: "en-US"  },
  { code: "GBP", name: "British Pound",   symbol: "£",   flag: "🇬🇧", decimals: 2, locale: "en-GB"  },
  { code: "EUR", name: "Euro",            symbol: "€",   flag: "🇪🇺", decimals: 2, locale: "en-IE"  },
  { code: "NGN", name: "Nigerian Naira",  symbol: "₦",   flag: "🇳🇬", decimals: 0, locale: "en-NG"  },
  { code: "KES", name: "Kenyan Shilling", symbol: "KSh", flag: "🇰🇪", decimals: 0, locale: "en-KE"  },
  { code: "GHS", name: "Ghanaian Cedi",   symbol: "₵",   flag: "🇬🇭", decimals: 2, locale: "en-GH"  },
  { code: "UGX", name: "Ugandan Shilling",symbol: "USh", flag: "🇺🇬", decimals: 0, locale: "en-UG"  },
  { code: "TZS", name: "Tanzanian Shilling", symbol: "TSh", flag: "🇹🇿", decimals: 0, locale: "en-TZ" },
  { code: "ZMW", name: "Zambian Kwacha",  symbol: "ZK",  flag: "🇿🇲", decimals: 2, locale: "en-ZM"  },
  { code: "ZAR", name: "South African Rand", symbol: "R", flag: "🇿🇦", decimals: 2, locale: "en-ZA" },
];

const SUPPORTED: Set<CurrencyCode> = new Set(CURRENCIES.map((c) => c.code));

// Baked-in snapshot — never show "—" if the API is unreachable and the
// AsyncStorage cache is empty (brand new install, offline). Refreshed
// in-memory the moment the first live fetch returns.
const FALLBACK_RATES: Record<CurrencyCode, number> = {
  USD: 1,
  GBP: 0.787,
  EUR: 0.925,
  NGN: 1546,
  KES: 129,
  GHS: 15.6,
  UGX: 3745,
  TZS: 2612,
  ZMW: 27.1,
  ZAR: 18.4,
};

const STORAGE_CURRENCY_KEY = "vaulted_display_currency";
const STORAGE_RATES_KEY = "vaulted_fx_rates_v1";
const STORAGE_GEO_DETECTED_KEY = "vaulted_currency_geo_detected_v1";
const REFRESH_INTERVAL_MS = 60 * 60 * 1000; // 1h

type RatesCache = {
  rates: Record<string, number>;
  fetchedAt: number; // epoch ms
};

type CurrencyCtx = {
  currency: CurrencyCode;
  setCurrency: (c: CurrencyCode) => void;
  meta: CurrencyMeta;
  rates: Record<string, number>;
  format: (usdAmount: number, opts?: { withSymbol?: boolean; compact?: boolean }) => string;
  convert: (usdAmount: number) => number;
  /** Convert FROM the display currency BACK to USD. Needed by the fiat
   *  deposit flow: user types `100` in ₦, we charge Stripe in USD. */
  toUsd: (localAmount: number) => number;
  /** Epoch ms the rate table was last refreshed from the backend. 0 if
   *  we only ever used the static snapshot. */
  fetchedAt: number;
  loading: boolean;
  refresh: () => Promise<void>;
};

const metaFor = (code: CurrencyCode): CurrencyMeta =>
  CURRENCIES.find((c) => c.code === code) ?? CURRENCIES[0];

const CurrencyContext = createContext<CurrencyCtx>({
  currency: "USD",
  setCurrency: () => {},
  meta: metaFor("USD"),
  rates: FALLBACK_RATES,
  format: (v) => `$${(v ?? 0).toFixed(2)}`,
  convert: (v) => v,
  toUsd: (v) => v,
  fetchedAt: 0,
  loading: false,
  refresh: async () => {},
});

export function CurrencyProvider({ children }: { children: ReactNode }) {
  const [currency, setCurrencyState] = useState<CurrencyCode>("USD");
  const [rates, setRates] = useState<Record<string, number>>(FALLBACK_RATES);
  const [loading, setLoading] = useState<boolean>(false);
  const [fetchedAt, setFetchedAt] = useState<number>(0);
  const refreshingRef = useRef<boolean>(false);
  const lastFetchRef = useRef<number>(0);

  // --- Boot: hydrate persisted currency pref + cached rates ---------------
  useEffect(() => {
    (async () => {
      let userHasExplicitPref = false;
      try {
        const [savedCurrency, savedRates] = await Promise.all([
          AsyncStorage.getItem(STORAGE_CURRENCY_KEY),
          AsyncStorage.getItem(STORAGE_RATES_KEY),
        ]);
        if (savedCurrency && SUPPORTED.has(savedCurrency as CurrencyCode)) {
          setCurrencyState(savedCurrency as CurrencyCode);
          userHasExplicitPref = true;
        }
        if (savedRates) {
          try {
            const parsed: RatesCache = JSON.parse(savedRates);
            if (parsed && parsed.rates && typeof parsed.rates === "object") {
              setRates({ ...FALLBACK_RATES, ...parsed.rates });
              lastFetchRef.current = parsed.fetchedAt || 0;
              setFetchedAt(parsed.fetchedAt || 0);
            }
          } catch {
            /* ignore corrupt cache */
          }
        }
      } catch {
        /* ignore boot errors — fallback rates still work */
      }
      // Always kick off a live refresh after boot so stale caches heal
      // themselves on next launch. Fire-and-forget.
      refresh().catch(() => undefined);

      // Smart default: if the user has never picked a currency AND we've
      // never attempted detection on this install, ask the backend what
      // country they're in and preselect the local currency once.
      if (!userHasExplicitPref) {
        try {
          const geoAttempted = await AsyncStorage.getItem(STORAGE_GEO_DETECTED_KEY);
          if (!geoAttempted) {
            await AsyncStorage.setItem(STORAGE_GEO_DETECTED_KEY, "1");
            try {
              const geo = (await api("/geo")) as { suggested_currency?: string };
              const suggested = (geo?.suggested_currency || "").toUpperCase();
              if (suggested && SUPPORTED.has(suggested as CurrencyCode) && suggested !== "USD") {
                setCurrencyState(suggested as CurrencyCode);
                await AsyncStorage.setItem(STORAGE_CURRENCY_KEY, suggested);
              }
            } catch {
              /* geo detection is a nice-to-have; USD is a safe default */
            }
          }
        } catch {
          /* ignore storage errors */
        }
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- Refresh when app comes back to foreground --------------------------
  useEffect(() => {
    const sub = AppState.addEventListener("change", (state) => {
      if (state !== "active") return;
      // Only hit the network if the cache is older than REFRESH_INTERVAL_MS
      if (Date.now() - lastFetchRef.current < REFRESH_INTERVAL_MS) return;
      refresh().catch(() => undefined);
    });
    return () => sub.remove();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- Periodic background refresh ----------------------------------------
  useEffect(() => {
    const id = setInterval(() => {
      refresh().catch(() => undefined);
    }, REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refresh = useCallback(async () => {
    if (refreshingRef.current) return;
    refreshingRef.current = true;
    setLoading(true);
    try {
      const data = (await api("/rates/fiat")) as {
        rates: Record<string, number>;
        base: string;
        fetched_at?: string;
      };
      if (data && data.rates && typeof data.rates === "object") {
        const merged = { ...FALLBACK_RATES, ...data.rates };
        setRates(merged);
        const now = Date.now();
        lastFetchRef.current = now;
        setFetchedAt(now);
        try {
          await AsyncStorage.setItem(
            STORAGE_RATES_KEY,
            JSON.stringify({ rates: merged, fetchedAt: now } as RatesCache),
          );
        } catch {
          /* ignore storage errors */
        }
      }
    } catch {
      /* network/API failure — swallow; UI keeps using existing rates */
    } finally {
      refreshingRef.current = false;
      setLoading(false);
    }
  }, []);

  const setCurrency = useCallback((c: CurrencyCode) => {
    if (!SUPPORTED.has(c)) return;
    setCurrencyState(c);
    AsyncStorage.setItem(STORAGE_CURRENCY_KEY, c).catch(() => undefined);
  }, []);

  const meta = useMemo(() => metaFor(currency), [currency]);

  const convert = useCallback(
    (usdAmount: number): number => {
      const safe = Number(usdAmount);
      if (!isFinite(safe)) return 0;
      const rate = rates[currency];
      if (!rate || !isFinite(rate) || rate <= 0) return safe; // graceful: show USD-as-is
      return safe * rate;
    },
    [currency, rates],
  );

  const toUsd = useCallback(
    (localAmount: number): number => {
      const safe = Number(localAmount);
      if (!isFinite(safe)) return 0;
      const rate = rates[currency];
      if (!rate || !isFinite(rate) || rate <= 0) return safe;
      return safe / rate;
    },
    [currency, rates],
  );

  const format = useCallback(
    (
      usdAmount: number,
      opts: { withSymbol?: boolean; compact?: boolean } = {},
    ): string => {
      const { withSymbol = true, compact = false } = opts;
      const converted = convert(usdAmount);
      const sign = converted < 0 ? "-" : "";
      const abs = Math.abs(converted);

      let numberPart: string;
      if (compact && abs >= 10_000) {
        // 1.2k / 1.3M — stays legible on tight asset rows.
        if (abs >= 1_000_000) {
          numberPart = `${(abs / 1_000_000).toLocaleString(meta.locale, {
            maximumFractionDigits: 1,
            minimumFractionDigits: 0,
          })}M`;
        } else {
          numberPart = `${(abs / 1_000).toLocaleString(meta.locale, {
            maximumFractionDigits: 1,
            minimumFractionDigits: 0,
          })}k`;
        }
      } else {
        try {
          numberPart = abs.toLocaleString(meta.locale, {
            maximumFractionDigits: meta.decimals,
            minimumFractionDigits: meta.decimals,
          });
        } catch {
          numberPart = abs.toFixed(meta.decimals);
        }
      }

      if (!withSymbol) return `${sign}${numberPart}`;
      // KSh / USh / TSh / ZK read better with a space; single-glyph
      // symbols hug the number.
      const spacer = meta.symbol.length > 1 ? " " : "";
      return `${sign}${meta.symbol}${spacer}${numberPart}`;
    },
    [convert, meta],
  );

  const value = useMemo<CurrencyCtx>(
    () => ({ currency, setCurrency, meta, rates, format, convert, toUsd, fetchedAt, loading, refresh }),
    [currency, setCurrency, meta, rates, format, convert, toUsd, fetchedAt, loading, refresh],
  );

  return (
    <CurrencyContext.Provider value={value}>{children}</CurrencyContext.Provider>
  );
}

export const useCurrency = () => useContext(CurrencyContext);
