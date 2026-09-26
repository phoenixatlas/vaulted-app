# Vaulted — Production State (FULLY OPERATIONAL 🏆)

> Last updated: 2026-06-27 — Book-a-call scheduler wired into hero, investor section, post-download modal, investor emails and PDFs. Attribution surfaced in /admin.

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
- [x] Multi-chain wallet (BTC Testnet3, ETH Sepolia, USDC Sepolia, SOL Devnet, **XLM Testnet**)
- [x] BTC + SOL Send wired & tested
- [x] **XLM Send + Receive + Balance** (Stellar Testnet via Horizon; Mainnet-ready via env flag)
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
- [ ] Backend refactor continuation — extract `remit_router.py` (~600 lines), `wallet_router.py` (~1500 lines), `multichain_router.py` from server.py (still ~2058 lines)
- [ ] Bi-directional Phase 2 — UK/EU GBP + EUR payout via PSP (Modulr / ClearBank / Stripe Treasury)
- [ ] Marketing landing at phoenix-atlas.com root + www
- [ ] Cloudflare SSL/TLS mode → "Full (strict)"
- [ ] Optional api.phoenix-atlas.com subdomain for backend
- [ ] Tighten Atlas IP allowlist to Render egress range
- [ ] Cancel + clean up test subscription in Stripe (Subscriptions → Cancel)
- [ ] Real WebRTC native module to replace Daily.co WebView (requires dev build)

## 🔧 Backend Refactor Progress (P2)
- ✅ `routers/admin.py` · `routers/referrals.py` · `routers/offramp.py` · `routers/calls.py` · `routers/keys.py` · `routers/chat.py` · `routers/multisig.py` · `routers/waitlist.py` · `routers/auth.py` · `routers/kyc.py` · `routers/reverse_remit.py` · `routers/investor.py` · **`routers/stripe_router.py`** (new — 6 endpoints, ~370 lines extracted)
- ⏳ Pending: `routers/remit_router.py` (~600 lines including /remit/quote, /remit/send, /remit/fund)
- ⏳ Pending: `routers/wallet_router.py` + `routers/multichain_router.py` (~1500 lines combined)
- Current server.py size: **2058 lines** (down from initial ~4500)

## 🔁 Bi-directional Corridors (Phase 1 shipped — Q3 2026)
- **Reverse quote engine**: `/api/remit/reverse/quote` — live Kotani onramp rate + open.er-api FX cache → GBP/EUR estimate
- **Corridors live**: 🇳🇬 NG · 🇰🇪 KE · 🇬🇭 GH · 🇿🇦 ZA → 🇬🇧 GBP / 🇪🇺 EUR
- **Live Kotani sandbox rates**: KE ✓ · ZA ✓ · NG (estimated — Kotani onramp NG enablement pending) · GH (estimated)
- **Waitlist**: Segmented by direction (inbound/outbound) → separate Resend Audiences per corridor+direction
- **UI**: `/remit` direction toggle · `<ReverseRemitPanel />` · landing page `#reverse` section

## 📄 Investor One-Pager + Deck (Q3 2026)
- **One-pager**: `/app/backend/onepager.py` (single A4, 6.3KB, live waitlist metrics)
- **Deck**: `/app/backend/deck.py` (5-page A4, 12KB, auto-generated; admin can upload real PDF via `POST /admin/investor/deck/upload` to override)
- **Endpoints**: `POST /investor/onepager/request` · `POST /investor/deck/request` · `GET /investor/{onepager,deck}/download?token=` · `GET /admin/investor/leads` · `POST/DELETE/GET /admin/investor/deck/{upload,status}`
- **Landing**: `#invest` section with dual CTAs (one-pager + deck link) + hero teaser
- **Resend**: Auto-creates "Vaulted Investor Leads" audience; follow-up email includes founder signature block + optional demo video CTA (env-configurable)

## 🚀 Growth Boosters (Q3 2026)
- **Referral queue-jump**: Every 3 referrals moves referrer up 25 spots. 5+ refs unlocks "Founding Member" badge (lifetime 50% off).
- **Landing referral banner**: `?ref=CODE` → validates + shows "You've been referred by o***@example.com" banner
- **Post-signup card**: Shows "YOUR SPOT #N of Total" + one-tap copy referral link + share buttons
- **Confirmation email**: Big position card + referral link + Twitter/WhatsApp share buttons

## 📊 Admin Analytics (Q3 2026)
- **Daily signups chart**: 30-day dense series with total + inbound overlay (SVG line chart via react-native-svg)
- **Corridor matrix heatmap**: Outbound × inbound × 7 corridors, brand-gold intensity = demand
- **Referral leaderboard**: Top 10 referrers (redacted emails) + founding members count
- **Investor leads card**: Total + repeat visitors + top companies + 5 most recent
