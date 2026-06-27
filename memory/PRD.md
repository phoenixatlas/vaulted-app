# Vaulted — Production State (FULLY OPERATIONAL 🏆)

> Last updated: 2026-06-27 — Live + accepting real payments.

## 🌐 Live URLs
- **Primary**: https://app.phoenix-atlas.com (Vercel, Cloudflare DNS)
- **Backup**: https://vaulted-app-one.vercel.app
- **Backend API**: https://vaulted-app.onrender.com (Render Starter)
- **Database**: MongoDB Atlas Free M0 (cluster0.s9r8j83.mongodb.net)
- **GitHub repo**: https://github.com/phoenixatlas/vaulted-app

## 🌩️ Infrastructure
- **Vercel** Hobby tier (auto-deploys from GitHub main)
- **Render** Starter $7/mo always-on
- **Cloudflare** DNS for phoenix-atlas.com
- **MongoDB Atlas** M0 Free (cluster0.s9r8j83 — 0.0.0.0/0 allowlist)
- **Resend** for transactional email (noreply@phoenix-atlas.com — verified)
- **Stripe Live** (PhoenixAtlas Technologies Ltd, GBP, flat-rate, "Pre-built checkout")
- **Daily.co** for WebRTC video calls

## ✅ End-to-End Verified
- [x] Account registration + JWT login on custom domain
- [x] Multi-chain wallet (BTC Testnet3, ETH Sepolia, USDC Sepolia, SOL Devnet)
- [x] BTC + SOL Send wired & tested
- [x] CORS locked to custom + Vercel origins
- [x] Always-on backend (Render Starter)
- [x] **Stripe Live mode — real £9.99 subscription confirmed** (Customer → checkout → webhook → DB update → "Pro activated" success page)
- [x] Webhook signing secret rotated post-test

## 🔐 Env Vars (live in Render dashboard, never committed)
MONGO_URL, DB_NAME=vaulted, JWT_SECRET, STRIPE_API_KEY (live, rotated), STRIPE_WEBHOOK_SECRET, RESEND_API_KEY, DAILY_API_KEY, CORS_ALLOW_ORIGINS, APP_PUBLIC_URL=https://app.phoenix-atlas.com, SEPOLIA_RPC_URL

## 💷 Stripe Live Mode
- Account: PhoenixAtlas Technologies Ltd (GBP)
- Webhook destination: `we_1TmwA92Zkc1SL713jbr6pJWO` → `https://vaulted-app.onrender.com/api/stripe/webhook`
- Vault Pro price: **£9.99/month recurring**
- Smoke test charge: confirmed live (refund after to recover funds minus Stripe fee)

## 🔄 Backlog (do later)
- [ ] Server.py refactor (2156 lines → routers/) — after 2+ weeks of stability
- [ ] Marketing landing at phoenix-atlas.com root + www
- [ ] Cloudflare SSL/TLS mode → "Full (strict)"
- [ ] Optional api.phoenix-atlas.com subdomain for backend
- [ ] Tighten Atlas IP allowlist to Render egress range
- [ ] Cancel + clean up test subscription in Stripe (Subscriptions → Cancel)
- [ ] Real WebRTC native module to replace Daily.co WebView (requires dev build)
