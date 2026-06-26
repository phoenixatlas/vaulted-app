# Vaulted — Secure Crypto Wallet (PRD)

## Iterations
- **Iter 1** — JWT auth, simulated wallet, simulated fiat, polling chat, mocked video, i18n.
- **Iter 2** — Live Stripe + Daily.co + TweetNaCl E2E chat + Vault Pro $9.99/mo.
- **Iter 3** — Real Sepolia ETH (key, send, export); Pro perks (50% fee, pinned support, billing portal); multi-sig gating.
- **Iter 4** — Live CoinGecko prices + sparklines; BIP-39 12-word recovery + verify quiz.
- **Iter 5** — **Real 2-of-2 ETH multi-sig with Resend email approvals.**
  - `RESEND_API_KEY` configured.
  - Threshold: `0.01 ETH` (configurable via env).
  - Approval TTL: 24h.
  - `POST /api/cosigners` (Pro only) → sends a welcome email + persists.
  - `POST /api/wallet/eth/send` gates ≥ threshold behind `approval_required:true` and emails the co-signer one-click Approve/Reject links pointing to `<APP_URL>/approve?token=...`.
  - `POST /api/approvals/decide` is the **public** decision endpoint (no auth — the token IS the credential). Approve attempts a real Sepolia broadcast. Idempotent; expired returns 410.
  - Frontend: `/cosigners`, `/approvals`, `/approve` screens; Settings → Security routes both into Pro-gated UX.
- **Iter 8** — **Resend auto-poller + in-chat crypto sends.**
  - **Resend poller**: backend startup task polls Resend every 5 min and *automatically* re-triggers verification for `phoenix-atlas.com`. The moment the domain flips to `verified`, the sender is promoted to `Vaulted <noreply@phoenix-atlas.com>` in-memory — no env-file rewriting, no restart, no manual script. New env vars: `RESEND_TARGET_DOMAIN`, `RESEND_TARGET_FROM`, `RESEND_POLL_INTERVAL_SEC`. Helper script `/app/scripts/check_resend_domain.sh` still works for manual flips.
  - **In-chat crypto sends**: new endpoint `POST /api/chat/send_crypto` performs a real Sepolia broadcast to the conversation counter-party (recipient ETH address is deterministically derived from the seeded contact's email — stored once on first send), then inserts a structured `kind:"tx_card"` message into the conversation. Capped under `MULTISIG_THRESHOLD_ETH` (0.01) so in-chat sends never block on multi-sig email approval.
  - **Chat UI**: composer now has a gold cash icon next to the message input → opens a bottom sheet ("Send ETH to <name>") with amount input, 3 quick-pill amounts (0.0001 / 0.001 / 0.005), and a brand-gold "Send now" CTA. Biometric scan required before broadcast if the user has biometric lock on. Errors (insufficient balance, cap) surface inline.
  - **tx_card bubble**: rich gold-bordered receipt card showing amount, network, masked recipient, status pill, and an "VIEW ON ETHERSCAN" deep-link button. Renders inline in the chat thread.
  - i18n keys extended (send_eth_to, send_now, cancel, sent_eth_label, network, to, view_on_etherscan, sepolia_testnet_note).
  - Wordmark + phoenix-mark imported from logo, processed (`brand-wordmark.png`, `brand-icon.png`, `brand-adaptive.png`) and wired into theme via `BRAND_IMAGES`.
  - New palette in `theme.ts`: warm metallic gold `#C9A35B` brand, deep warm-black `#0F0B08` inverse, cream-tinted light surfaces. Hybrid theme — gold-on-black chrome on auth/hero/CTAs; light cream surfaces for forms & lists for readability.
  - All 13 primary CTAs flipped from white-on-gold (poor contrast) to deep-black-on-gold (premium 7:1).
  - Login screen full dark-luxe; wallet hero with phoenix watermark + gold border; `app.json` splash + icons set to phoenix mark on deep-warm-black.
  - **Polish sweep**: chat "me" bubbles now use deep-black text on gold (was white); send-arrow icon in deep-black; tab-bar inactive icons keep warm tone + gold-tinted top border; video-call overlay fully rebranded — gold-tinted encrypted pill, gold-bordered timer, deep-warm-black backdrop (replaced stock unsplash photo), warm cream demo-mode notice; receipt ticket has gold-accent border, gold success-circle ring, deep-gold uppercase row labels.
  - App name kept as "Vaulted" per user direction.

## Live integration keys (in /app/backend/.env)
- `STRIPE_API_KEY` — real `sk_test_51Tlaat...`
- `DAILY_API_KEY` — real (`phoenixatl.daily.co`)
- `SEPOLIA_RPC_URL` — public node
- `RESEND_API_KEY` — real, **testing mode**: currently only delivers to `oumarsanii@yahoo.co.uk` (Resend free-tier requires verified domain to send to arbitrary recipients).

## Test status
- Iter 5: **19/19 backend pytest + full frontend UI verified** ✅
- All previous iterations regression-tested green.

## Open follow-ups
1. **Resend domain verification** — verify a domain at resend.com/domains and replace `onboarding@resend.dev` in `server.py:583,626` to deliver to real cosigners outside your own email.
2. Push notifications, real multi-sig 2-of-N beyond 2-of-2, CSV tax export — still deferred.
3. Optional: pin bcrypt==4.0.1, lengthen JWT_SECRET to 32 bytes, split server.py routers, fix deprecated `pointerEvents`/`resizeMode` warnings.
