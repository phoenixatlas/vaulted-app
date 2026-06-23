# Vaulted — Secure Crypto Wallet (PRD)

## Vision
A self-custody crypto wallet mobile app that combines crypto storage, fiat on/off-ramps, end-to-end encrypted peer chat, and built-in video calls — all behind one trusted brand. iOS-Native Clean design (moss/sage palette).

## Implemented Features

### Iteration 1 (MVP)
1. **Auth (JWT + bcrypt)**: register, login, /me, logout, token in SecureStore / IndexedDB.
2. **Crypto wallet (simulated)**: BTC/ETH/USDC/SOL balances, hero card, send (debit + random tx_hash), receive (QR + address).
3. **Fiat transfers (simulated)**: deposit (card/bank/Apple Pay) credits USDC 1:1; withdraw debits USDC.
4. **Transactions / Activity**: unified history feed.
5. **Chat (polling)**: 3 seeded contacts, conversation thread, system auto-reply.
6. **Video call (mocked UI)**: full-bleed screen with timer + mic/cam/end controls.
7. **Language selection**: live EN / ES / FR / AR switcher.
8. **Security settings**: biometric + multi-sig toggles persisted.

### Iteration 2 (Integrations + Monetization)
9. **Real Stripe** (sandbox-ready): one-time deposit Checkout (payment mode), Vault Pro subscription Checkout (subscription mode), webhook handler with idempotency, /sync polling endpoint, /cancel subscription. Backend gracefully degrades with 503 when STRIPE_API_KEY isn't a real key.
10. **Real WebRTC video calls via Daily.co**: backend creates Daily rooms + meeting tokens via REST; frontend renders the Daily room in a `react-native-webview`. Falls back to mock UI when DAILY_API_KEY isn't set.
11. **Real E2E chat encryption** via TweetNaCl (`secretbox`): client generates a 32-byte symmetric key on first login, stores it in SecureStore, encrypts every outgoing message with a fresh nonce. Server stores only ciphertext + nonce. Decryption is client-side only.
12. **Vault Pro $9.99/month subscription**: dedicated screen + perks (multi-sig, lower fees, priority video support, Pro badge); non-Pro users tapping multi-sig switch are routed to upsell; settings shows live PRO badge when active.

## API Surface
| Endpoint | Method | Purpose |
|---|---|---|
| /api/auth/{register,login,me,language,security} | POST/PATCH/GET | Auth + profile |
| /api/wallet/{assets,send} | GET/POST | Crypto |
| /api/fiat/{deposit,withdraw} | POST | Simulated fiat |
| /api/transactions | GET | History |
| /api/chat/{conversations,messages/{id},messages} | GET/POST | Chat (now E2E) |
| /api/keys/{register, :id} | POST/GET | E2E public-key registry |
| /api/stripe/checkout/{deposit,subscription} | POST | Stripe Checkout |
| /api/stripe/{sync,webhook,cancel} | POST | Stripe lifecycle |
| /api/calls/room | POST | Daily.co room + token |

## Required Keys to fully activate Iter-2
- `STRIPE_API_KEY` — real `sk_test_...` from https://dashboard.stripe.com/apikeys (placeholder `sk_test_emergent` triggers 503).
- `STRIPE_WEBHOOK_SECRET` — from `stripe listen --forward-to .../api/stripe/webhook` or dashboard webhook.
- `DAILY_API_KEY` — from https://dashboard.daily.co/developers (free tier).
- `APP_PUBLIC_URL` — already set to preview URL; used as Stripe success/cancel base.

## Still simulated / not in scope
- On-chain crypto interactions (real blockchain RPC).
- Fiat withdrawals to real bank accounts (needs Stripe Connect / Treasury).
- Signal-grade chat (libsignal); TweetNaCl is symmetric per-device, demonstrably real E2E for messages-at-rest but not multi-device key exchange.
