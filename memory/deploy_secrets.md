# Vaulted — Production State (LIVE 🎉)

> Last updated: 2026-06-27 — Fully shipped with custom domain.

## 🌐 Live URLs
- **Primary**: https://app.phoenix-atlas.com (Vercel-hosted, Cloudflare DNS)
- **Backup**: https://vaulted-app-one.vercel.app (still active, CORS-allowed)
- **Backend API**: https://vaulted-app.onrender.com (Render Starter, always-on)
- **Database**: MongoDB Atlas Free M0 — `cluster0.s9r8j83.mongodb.net`
- **GitHub repo**: https://github.com/phoenixatlas/vaulted-app

## 🔐 Render Env Vars (production)
- `MONGO_URL` = `mongodb+srv://oumarsanii_db_user:YW8sEKGSBeJPnQSj@cluster0.s9r8j83.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0`
- `DB_NAME` = `vaulted`
- `JWT_SECRET` = `1187f6ea010a0f6e59e2dc43a7397d1153f8bb148cfe44c00878e5c9dca73131`
- `CORS_ALLOW_ORIGINS` = `https://app.phoenix-atlas.com,https://vaulted-app-one.vercel.app`
- `APP_PUBLIC_URL` = `https://app.phoenix-atlas.com`
- `STRIPE_API_KEY` = test mode (`sk_test_...`)
- `RESEND_API_KEY`, `DAILY_API_KEY` = production
- `SEPOLIA_RPC_URL` = `https://ethereum-sepolia-rpc.publicnode.com`

## 🌩️ Cloudflare DNS for phoenix-atlas.com
- `app` → CNAME → `cname.vercel-dns.com` (Proxy: **DNS only** / grey cloud) ← MUST stay grey
- `send` → MX/TXT/CNAME → Resend (already verified, sends as `noreply@phoenix-atlas.com`)
- IP Allowlist for MongoDB Atlas: `0.0.0.0/0` (permanent)

## 👤 First Production Account
- Email: `oumarsanii@yahoo.co.uk` (Umar Muhammad Sani)
- ETH address: `0x57Fb8eEDef807bDFC5E943f3335d1...`

## ✅ Hardening Completed
- [x] CORS locked to specific Vercel + custom domain origins (not `*`)
- [x] Render Starter ($7/mo) — always-on, no cold starts
- [x] Custom branded domain `app.phoenix-atlas.com` with SSL
- [x] Backend uses certifi `tlsCAFile` for Atlas TLS

## 🔄 Deferred (do later)
- [ ] **Rotate** MongoDB Atlas password & tighten IP allowlist to Render egress range (optional security upgrade)
- [ ] **Stripe Live Mode** — when first paying customer appears; needs Stripe onboarding completion
- [ ] **Server.py refactor** — 2156 lines → `routers/` modules. Defer until production is proven stable.
- [ ] **Marketing landing** at `phoenix-atlas.com` (root) and `www.phoenix-atlas.com`
- [ ] **Cloudflare SSL/TLS mode** → set to "Full (strict)" if not already (defense-in-depth)
- [ ] **Optional `api.phoenix-atlas.com`** subdomain for the backend (currently uses Render URL directly)
