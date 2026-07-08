// PhoenixAtlas brand palette — warm gold + deep warm-black.
// Hybrid theme: light surfaces for forms/lists (readability), gold-on-black
// for headers, CTAs, brand chrome and premium surfaces.

export const colors = {
  // Light surfaces (forms, scrollable lists)
  surface: "#FBF8F2",            // warm off-white with a hint of cream
  onSurface: "#1A1310",          // deep warm near-black
  surfaceSecondary: "#F1EBDD",   // warm beige
  onSurfaceSecondary: "#5A4E3A",
  surfaceTertiary: "#E7DEC9",
  onSurfaceTertiary: "#8B7B5E",

  // Inverse / brand chrome (deep gold-on-black)
  surfaceInverse: "#0F0B08",     // near-black with warm undertone (logo bg)
  onSurfaceInverse: "#F5E9C9",   // warm light gold-cream
  surfaceInverseSecondary: "#1A1310",
  surfaceInverseTertiary: "#241B14",

  // Brand — warm metallic gold (from the logo)
  brand: "#C9A35B",
  brandHover: "#B58F47",
  brandSecondary: "#E6C879",     // lighter gold for highlights/badges
  onBrandSecondary: "#3A2A0E",
  brandTertiary: "#F5E9C9",      // gold tint backdrop on light surfaces
  onBrandTertiary: "#8B6A1F",
  brandDeep: "#7A5A20",          // dark gold for text on gold backgrounds

  // Semantic
  success: "#4F7B3A",
  warning: "#C9962A",
  error: "#B23C2F",

  // Borders & dividers
  border: "#E2D9C0",
  borderStrong: "#C9BD9C",
  borderInverse: "#2C2118",
  divider: "#EDE5CF",
};

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, xxxl: 48 };
export const radius = { sm: 6, md: 12, lg: 20, pill: 999 };

export const ASSET_ICON_COLORS: Record<string, string> = {
  BTC: "#F7931A",
  ETH: "#C9A35B", // tint ETH with brand gold for consistency
  USDC: "#2775CA",
  SOL: "#14F195",
  XLM: "#08B5E5", // Stellar electric blue (official brand)
  XRP: "#23292F", // Ripple charcoal (official brand)
};

// Brand image paths (for <Image source={require(...)} />)
export const BRAND_IMAGES = {
  wordmark: require("../../assets/images/brand-wordmark.png"),
  mark: require("../../assets/images/brand-icon.png"),
};
