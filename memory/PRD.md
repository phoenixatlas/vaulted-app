# Vaulted — Secure Crypto Wallet (PRD)

## Vision
A self-custody crypto wallet mobile app combining crypto storage, fiat on/off-ramps, end-to-end encrypted peer chat, and built-in video calls. iOS-Native Clean design (moss/sage palette).

## Implemented Features

### Iter 1 — MVP
JWT+bcrypt auth · simulated BTC/ETH/USDC/SOL wallet · simulated fiat deposit/withdraw with VLT receipts · activity feed · polling chat w/ 3 seeded contacts · mocked video UI · EN/ES/FR/AR i18n · biometric/multi-sig settings toggles.

### Iter 2 — Live integrations
Real Stripe Checkout (deposit + Vault Pro subscription) + webhook + sync + cancel · Real Daily.co video rooms via WebView · Real E2E chat via TweetNaCl secretbox · Vault Pro $9.99/mo gating.

### Iter 3 — On-chain ETH + Pro perks
Real Ethereum keypair on Sepolia · `/wallet/eth/{info,send,export}` · `/wallet/assets` reads live chain balance · Pro 50% fee discount · Vault Support pinned + PRIORITY badge · Stripe Billing Portal · multi-sig gated behind subscription · Export private key flow.

### Iter 4 — Live prices + BIP-39 onboarding
- **CoinGecko live prices**: `/api/market/prices` with 300s server cache, falls back to stale cache then defaults; `/wallet/assets` now includes `change_24h_pct` and `sparkline_7d[]` per asset.
- **SVG sparklines** on every wallet row via `react-native-svg`, color-coded (green/red) by 24h move.
- **BIP-39 12-word recovery phrase** generated via `Account.create_with_mnemonic()` on registration. `/wallet/eth/mnemonic` reveals it. Address derived from mnemonic verified to match `eth_private_key`.
- **Onboarding flow** `/onboarding/seed` (reveal-tap + 12 numbered word cells) → `/onboarding/verify` (4-question word-position quiz with distractors) → `/auth/onboarding-complete` → wallet. Settings exposes both "Show recovery phrase" and "Export private key".

## Live integration keys (in /app/backend/.env)
- `STRIPE_API_KEY` — real `sk_test_51Tlaat...`
- `DAILY_API_KEY` — real (domain `phoenixatl.daily.co`)
- `SEPOLIA_RPC_URL` — `https://ethereum-sepolia-rpc.publicnode.com` (free public)
- `COINGECKO_API` — free tier, no key needed

## Still simulated / deferred
- BTC, USDC, SOL balances (MongoDB only)
- Fiat withdrawals (Stripe Connect not onboarded)
- Multi-sig 2-of-N signing (UI toggle only)
- Push notifications (deferred — requires native build, not Expo Go)

## Test status
- Iter 1: 32/32 · Iter 2: 41/41 · Iter 3: 30/31 · **Iter 4: 35/35** (21 backend pytest + 14 frontend UI)
