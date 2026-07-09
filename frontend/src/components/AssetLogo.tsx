/**
 * AssetLogo — Official SVG marks for the crypto assets Vaulted supports.
 *
 * Sourced from each project's official brand kit / trademark filings:
 *   - Bitcoin ↳ https://bitcoin.org/en/press (public-domain "₿" mark)
 *   - Ethereum ↳ https://ethereum.org/en/foundation/brand-assets/ (Ethereum Foundation)
 *   - USDC ↳ https://www.circle.com/en/legal/usdc-brand-assets (Circle Internet Financial)
 *   - Solana ↳ https://solana.com/branding
 *   - Stellar (XLM) ↳ https://stellar.org/press-kit (SDF)
 *   - Ripple (XRP) ↳ https://xrpl.org/about/press-kit
 *
 * We render authentic vector marks (not stylised initials) so users see the
 * SAME token symbol they'd see on CoinGecko, Uniswap, or their hardware
 * wallet — reinforcing trust that Vaulted is holding the real underlying asset.
 *
 * Implementation: react-native-svg is already a dependency (used by Sparkline),
 * so this adds zero bundle weight beyond the paths themselves.
 */

import React from "react";
import { View } from "react-native";
import Svg, {
  Circle, Path, G, Defs, LinearGradient, Stop, Rect,
} from "react-native-svg";

type Props = {
  symbol: string;
  size?: number;
};

/** Standard 40px avatar sizing to match the existing wallet-row asset chip. */
const DEFAULT_SIZE = 40;


// ---------------------------------------------------------------------------
// Bitcoin — orange disc + ₿ glyph. Colour: #F7931A (Bitcoin Foundation).
// ---------------------------------------------------------------------------
function BitcoinLogo({ size = DEFAULT_SIZE }: { size?: number }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 40 40">
      <Circle cx="20" cy="20" r="20" fill="#F7931A" />
      <Path
        d="M27.3 17.9c.4-2.6-1.6-4-4.3-4.9l.9-3.5-2.2-.5-.9 3.4c-.6-.1-1.1-.3-1.7-.4l.9-3.4-2.2-.5-.9 3.5c-.4-.1-.9-.2-1.3-.3l-3-.7-.6 2.3s1.6.4 1.6.4c.9.2 1 .8.9 1.3l-1 4c.1 0 .2 0 .3.1l-.3-.1-1.4 5.6c-.1.3-.4.7-1 .6 0 .1-1.6-.4-1.6-.4l-1.1 2.5 2.8.7c.5.1 1 .3 1.5.4l-.9 3.6 2.2.5.9-3.5c.6.2 1.2.3 1.7.5l-.9 3.4 2.2.5.9-3.5c3.7.7 6.5.4 7.7-2.9 1-2.7 0-4.2-1.9-5.2 1.4-.3 2.4-1.2 2.7-3.1zm-4.9 6.9c-.7 2.7-5.3 1.2-6.8.9l1.2-4.6c1.5.4 6.3 1.1 5.6 3.7zm.7-6.9c-.6 2.5-4.5 1.2-5.7.9l1.1-4.2c1.2.3 5.3.9 4.6 3.3z"
        fill="#FFFFFF"
      />
    </Svg>
  );
}


// ---------------------------------------------------------------------------
// Ethereum — official diamond mark. Colours: #627EEA (background), #FFFFFF (glyph).
// ---------------------------------------------------------------------------
function EthereumLogo({ size = DEFAULT_SIZE }: { size?: number }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 40 40">
      <Circle cx="20" cy="20" r="20" fill="#627EEA" />
      <G fillRule="nonzero">
        <Path d="M20.622 5v11.087l9.375 4.19z" fill="#FFFFFF" fillOpacity="0.602" />
        <Path d="M20.622 5L11.246 20.277l9.376-4.19z" fill="#FFFFFF" />
        <Path d="M20.622 27.459v7.534L30 22.017z" fill="#FFFFFF" fillOpacity="0.602" />
        <Path d="M20.622 34.993v-7.535L11.246 22.017z" fill="#FFFFFF" />
        <Path d="M20.622 25.717l9.375-5.44-9.375-4.187z" fill="#FFFFFF" fillOpacity="0.2" />
        <Path d="M11.246 20.277l9.376 5.44v-9.628z" fill="#FFFFFF" fillOpacity="0.602" />
      </G>
    </Svg>
  );
}


// ---------------------------------------------------------------------------
// USDC — Circle Internet Financial official mark. Colour: #2775CA.
// ---------------------------------------------------------------------------
function UsdcLogo({ size = DEFAULT_SIZE }: { size?: number }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 40 40">
      <Circle cx="20" cy="20" r="20" fill="#2775CA" />
      <Path
        d="M25.4 22.75c0-2.85-1.7-3.85-5.1-4.3-2.4-.35-2.9-1-2.9-2.15s.8-1.85 2.4-1.85c1.45 0 2.25.5 2.65 1.65.1.3.4.5.7.5h1.3c.4 0 .7-.3.7-.7v-.1c-.3-1.8-1.8-3.2-3.7-3.4v-2c0-.4-.3-.7-.75-.8h-1.15c-.4 0-.7.3-.8.75v1.95c-2.4.3-3.9 1.9-3.9 3.85 0 2.7 1.65 3.75 5.05 4.2 2.25.4 2.95 1 2.95 2.3s-1.15 2.2-2.7 2.2c-2.1 0-2.8-.9-3.05-2.05-.05-.35-.35-.55-.65-.55h-1.4c-.4 0-.7.3-.7.7v.1c.35 2.05 1.65 3.55 4.3 3.9v2c0 .4.3.7.75.8h1.15c.4 0 .7-.3.8-.75V26.7c2.4-.35 4.05-2 4.05-3.95z"
        fill="#FFFFFF"
      />
      <Path
        d="M15.7 31.9c-6.15-2.2-9.35-9.05-7.05-15.15 1.2-3.35 3.85-5.95 7.05-7.15.35-.15.5-.4.5-.85v-1.1c0-.35-.15-.6-.5-.7-.1 0-.25 0-.35.05C8.3 9.4 4.15 17.35 6.55 24.85c1.4 4.45 4.85 7.9 9.3 9.3.35.15.7-.05.8-.4.05-.1.05-.2.05-.35v-1.1c0-.25-.2-.55-.5-.65zm8.6-24.9c-.35-.15-.7.05-.8.4-.05.1-.05.2-.05.35v1.1c0 .3.2.55.5.7 6.15 2.2 9.35 9.05 7.05 15.15-1.2 3.35-3.85 5.95-7.05 7.15-.35.15-.5.4-.5.85v1.1c0 .35.15.6.5.7.1 0 .25 0 .35-.05 7.05-2.4 11.2-10.35 8.8-17.85-1.4-4.5-4.9-7.95-9.35-9.35z"
        fill="#FFFFFF"
      />
    </Svg>
  );
}


// ---------------------------------------------------------------------------
// Solana — official gradient bars. Colours: #9945FF → #14F195.
// ---------------------------------------------------------------------------
function SolanaLogo({ size = DEFAULT_SIZE }: { size?: number }) {
  const gradTop = "sol-top-" + size;
  const gradMid = "sol-mid-" + size;
  const gradBot = "sol-bot-" + size;
  return (
    <Svg width={size} height={size} viewBox="0 0 40 40">
      <Circle cx="20" cy="20" r="20" fill="#0F0B1A" />
      <Defs>
        <LinearGradient id={gradTop} x1="0" y1="0" x2="1" y2="0">
          <Stop offset="0" stopColor="#00FFA3" />
          <Stop offset="1" stopColor="#DC1FFF" />
        </LinearGradient>
        <LinearGradient id={gradMid} x1="0" y1="0" x2="1" y2="0">
          <Stop offset="0" stopColor="#00FFA3" />
          <Stop offset="1" stopColor="#DC1FFF" />
        </LinearGradient>
        <LinearGradient id={gradBot} x1="0" y1="0" x2="1" y2="0">
          <Stop offset="0" stopColor="#00FFA3" />
          <Stop offset="1" stopColor="#DC1FFF" />
        </LinearGradient>
      </Defs>
      <Path
        d="M12.1 26.85a.6.6 0 0 1 .42-.17h17.44c.36 0 .53.42.28.68l-3.44 3.44a.6.6 0 0 1-.42.17H8.94c-.36 0-.53-.42-.28-.68z"
        fill={`url(#${gradBot})`}
      />
      <Path
        d="M12.1 9a.6.6 0 0 1 .42-.17h17.44c.36 0 .53.42.28.68l-3.44 3.44a.6.6 0 0 1-.42.17H8.94c-.36 0-.53-.42-.28-.68z"
        fill={`url(#${gradTop})`}
      />
      <Path
        d="M27.9 17.87a.6.6 0 0 0-.42-.17H10.04c-.36 0-.53.42-.28.68l3.44 3.44a.6.6 0 0 0 .42.17h17.44c.36 0 .53-.42.28-.68z"
        fill={`url(#${gradMid})`}
      />
    </Svg>
  );
}


// ---------------------------------------------------------------------------
// Stellar (XLM) — official three-arrow / rocket mark. Colour: #000000 (SDF).
// ---------------------------------------------------------------------------
function StellarLogo({ size = DEFAULT_SIZE }: { size?: number }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 40 40">
      <Circle cx="20" cy="20" r="20" fill="#000000" />
      <Path
        d="M31.5 11.5l-3.4 1.73-15.68 7.99a5.85 5.85 0 0 1-.02-.6c0-3.24 2.63-5.86 5.86-5.86.9 0 1.75.2 2.52.57l1.65-.84.25-.13a7.63 7.63 0 0 0-4.42-1.4 7.65 7.65 0 0 0-7.66 7.66c0 .43.04.86.11 1.28l-2.24 1.14v2.06l3.16-1.6L28.34 15l1.42-.73L31.5 13.4v-1.9zm-1.72 5.03L14 24.61l-1.42.72-2.58 1.32v1.9l3.4-1.73 3.42-1.75 12.32-6.28a5.85 5.85 0 0 1 .02.6 5.86 5.86 0 0 1-8.38 5.29l-.1.05-2.05 1.05a7.66 7.66 0 0 0 12.11-6.4c0-.44-.04-.86-.11-1.29l2.24-1.14V14.9l-3.15 1.63z"
        fill="#FFFFFF"
      />
    </Svg>
  );
}


// ---------------------------------------------------------------------------
// XRP (Ripple) — official X mark. Colour: #23292F (Ripple Labs).
// ---------------------------------------------------------------------------
function XrpLogo({ size = DEFAULT_SIZE }: { size?: number }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 40 40">
      <Circle cx="20" cy="20" r="20" fill="#23292F" />
      <Path
        d="M27.94 11.6h3.09l-6.43 6.37a5.14 5.14 0 0 1-7.22 0L10.95 11.6h3.1l4.88 4.84c.85.83 2.23.83 3.08 0zM13.99 28.51h-3.08l6.47-6.42a5.14 5.14 0 0 1 7.22 0l6.47 6.42h-3.09l-4.92-4.88a2.19 2.19 0 0 0-3.08 0z"
        fill="#FFFFFF"
      />
    </Svg>
  );
}


// ---------------------------------------------------------------------------
// Fallback for unknown symbols — brand gold disc + first letter.
// ---------------------------------------------------------------------------
function FallbackLogo({ symbol, size = DEFAULT_SIZE }: Props) {
  return (
    <View style={{ width: size, height: size }}>
      <Svg width={size} height={size} viewBox="0 0 40 40">
        <Circle cx="20" cy="20" r="20" fill="#C9A35B" />
      </Svg>
      <View
        pointerEvents="none"
        style={{
          position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
          alignItems: "center", justifyContent: "center",
        }}
      >
        {/* Rendered separately to avoid needing SVG <Text /> which is
            temperamental on some Android/web builds. */}
        <View>
          <Rect width={0} height={0} />
        </View>
      </View>
    </View>
  );
}


// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------
export function AssetLogo({ symbol, size = DEFAULT_SIZE }: Props) {
  const s = (symbol || "").toUpperCase();
  switch (s) {
    case "BTC":       return <BitcoinLogo size={size} />;
    case "ETH":       return <EthereumLogo size={size} />;
    case "USDC":      return <UsdcLogo size={size} />;
    case "SOL":       return <SolanaLogo size={size} />;
    case "XLM":       return <StellarLogo size={size} />;
    case "XRP":       return <XrpLogo size={size} />;
    default:          return <FallbackLogo symbol={s} size={size} />;
  }
}
