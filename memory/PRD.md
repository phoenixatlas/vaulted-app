# Vaulted — Secure Crypto Wallet (PRD)

## Vision
A self-custody crypto wallet mobile app that combines crypto storage, fiat on/off-ramps, end-to-end encrypted peer chat, and built-in video calls. iOS-Native Clean design (moss/sage palette).

## Implemented Features

### Iteration 1 (MVP)
1. Auth (JWT + bcrypt)
2. Simulated crypto wallet (BTC/ETH/USDC/SOL)
3. Simulated fiat deposit/withdraw with VLT receipts
4. Transactions / Activity feed
5. Polling-based chat with 3 seeded contacts
6. Mocked video call UI
7. Live EN/ES/FR/AR i18n
8. Biometric + multi-sig settings toggles

### Iteration 2 (Live integrations)
9. **Real Stripe** Checkout (deposit + Vault Pro subscription) + webhook + sync + cancel
10. **Real Daily.co** video rooms with meeting tokens, rendered in WebView
11. **Real E2E chat** via TweetNaCl secretbox (client-side encrypt/decrypt)
12. Vault Pro $9.99/mo gating

### Iteration 3 (Real on-chain ETH + Pro perks)
13. **Real Ethereum self-custody on Sepolia testnet**
    - eth-account generates a true keypair on registration
    - `/wallet/eth/info` returns live chain ID, gas price, balance
    - `/wallet/eth/send` signs and broadcasts via JSON-RPC; returns Etherscan-linked tx hash
    - `/wallet/eth/export` reveals the 0x-prefixed private key (after explicit confirm)
    - `/wallet/assets` ETH row marked `on_chain: true, network: "Sepolia"`
    - Faucet links in the UI (sepoliafaucet.com)
14. **Vault Pro perks now deliver real value**
    - Send screen: 50% off Vaulted service fee (with strike-through original), strike + PRO -50% badge
    - Conversations: Vault Support pinned to top for Pro users (regardless of message recency)
    - PRIORITY badge in chat list (Pro users only)
    - Stripe Billing Portal: "Manage billing" launches `billing_portal.sessions.create`
    - Multi-sig switch gates behind subscription (redirects non-Pro to upsell)
    - Settings → Security: Export private key flow with warning + Etherscan link

## API Surface (additions in iter-3)
| Endpoint | Method | Purpose |
|---|---|---|
| /api/wallet/eth/info | GET | Live Sepolia info (balance, gas, links) |
| /api/wallet/eth/send | POST | Sign + broadcast on-chain tx |
| /api/wallet/eth/export | GET | Reveal private key |
| /api/stripe/portal | POST | Stripe Billing Portal URL |

## Live integrations (keys in /app/backend/.env)
- `STRIPE_API_KEY` — real `sk_test_51Tlaat...`
- `DAILY_API_KEY` — real key, domain `phoenixatl.daily.co`
- `SEPOLIA_RPC_URL` — `https://ethereum-sepolia-rpc.publicnode.com` (free public)

## Still simulated
- BTC, USDC, SOL balances (MongoDB only)
- Fiat withdrawals (Stripe Connect not onboarded)
- Multi-sig 2-of-N signing (currently just a Pro-gated UI toggle)

## Test status
- Iteration 1: 32/32 pass
- Iteration 2: 33+8 pass
- Iteration 3: 17 backend pytest + 13/14 frontend UI pass, 2 follow-up bugs fixed and verified
