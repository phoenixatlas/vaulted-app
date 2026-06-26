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
