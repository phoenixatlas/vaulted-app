# Vaulted — Production State (LIVE 🎉)

> Last updated: 2026-06-27 — Fully shipped with custom domain.
> ⚠️ This file is in `.gitignore` but Emergent's secret scanner blocks pushes
>    that have *any* live secrets in the workspace. So real values live in Render only.

## 🌐 Live URLs
- **Primary**: https://app.phoenix-atlas.com  (Vercel-hosted, Cloudflare DNS)
- **Backup**: https://vaulted-app-one.vercel.app
- **Backend API**: https://vaulted-app.onrender.com  (Render Starter)
- **Database**: MongoDB Atlas Free M0 cluster (cluster0.s9r8j83.mongodb.net)
- **GitHub repo**: https://github.com/phoenixatlas/vaulted-app

## 🔐 Render Env Vars (production)
Real values live ONLY in Render's Environment dashboard.
Format reference (NOT the actual values):

| Variable | Format | Where the real value lives |
|---|---|---|
| `MONGO_URL` | `mongodb+srv://USER:PASS@cluster0.s9r8j83.mongodb.net/...` | Render dashboard |
| `DB_NAME` | `vaulted` | Render dashboard |
| `JWT_SECRET` | 64-hex string | Render dashboard |
| `STRIPE_API_KEY` | `sk_live_...` (LIVE — Stripe Live Mode) | Render dashboard |
| `STRIPE_WEBHOOK_SECRET` | `whsec_...` | Render dashboard |
| `RESEND_API_KEY` | `re_...` | Render dashboard |
| `DAILY_API_KEY` | hex | Render dashboard |
| `CORS_ALLOW_ORIGINS` | `https://app.phoenix-atlas.com,https://vaulted-app-one.vercel.app` | Render dashboard |
| `APP_PUBLIC_URL` | `https://app.phoenix-atlas.com` | Render dashboard |

## 🌩️ Cloudflare DNS for phoenix-atlas.com
- `app` → CNAME → `cname.vercel-dns.com` (Proxy: **DNS only / grey cloud** — MUST stay grey)
- `send` → MX/TXT/CNAME → Resend (verified, sends as `noreply@phoenix-atlas.com`)
- MongoDB Atlas IP Allowlist: `0.0.0.0/0` (permanent)

## 👤 First Production Account
- Email: `oumarsanii@yahoo.co.uk` (Umar Muhammad Sani)
- ETH address: `0x57Fb8eEDef807bDFC5E943f3335d1...`

## 💳 Stripe Live Mode
- **Status**: Live mode active (account: PhoenixAtlas Technologies Ltd, GBP)
- **Webhook destination**: `we_1TmwA92Zkc1SL713jbr6pJWO`
- **Webhook endpoint**: `https://vaulted-app.onrender.com/api/stripe/webhook`
- **Webhook events**: `checkout.session.completed`, `customer.subscription.{created,updated,deleted}`, `invoice.payment_failed`
- **Pricing**: Vault Pro = £9.99/month (currency=`gbp` in `server.py`)

## ✅ Hardening Completed
- [x] CORS locked to specific Vercel + custom domain origins (not `*`)
- [x] Render Starter ($7/mo) — always-on, no cold starts
- [x] Custom branded domain `app.phoenix-atlas.com` with SSL
- [x] Backend uses certifi `tlsCAFile` for Atlas TLS
- [x] Stripe Live keys configured
- [x] Vault Pro priced in GBP £9.99/month

## 🔄 Deferred (do later)
- [ ] Rotate MongoDB Atlas password & tighten IP allowlist to Render egress range
- [ ] Marketing landing at `phoenix-atlas.com` (root) and `www.phoenix-atlas.com`
- [ ] Set Cloudflare SSL/TLS mode → "Full (strict)" (defense-in-depth)
- [ ] Optional `api.phoenix-atlas.com` subdomain for the backend
- [ ] Server.py refactor (2156 lines → `routers/` modules) — recommended after 2+ weeks of stability
