# Production Deployment — LIVE 🎉

> Deployed: 2026-06-27 — Vaulted is live on public infrastructure.

## 🌐 Live URLs
- **Frontend** (Vercel): https://vaulted-app-one.vercel.app
- **Backend** (Render): https://vaulted-app.onrender.com
- **Database** (MongoDB Atlas): cluster0.s9r8j83.mongodb.net (free M0)
- **GitHub repo**: https://github.com/phoenixatlas/vaulted-app

## 🔐 MongoDB Atlas
- **MONGO_URL** = `mongodb+srv://oumarsanii_db_user:YW8sEKGSBeJPnQSj@cluster0.s9r8j83.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0`
- **DB_NAME** = `vaulted`
- **IP Allowlist**: `0.0.0.0/0` (permanent, added 2026-06-27)
- **TODO (post-launch)**: Rotate password & tighten IP allowlist to Render egress range

## 👤 Production Account
- **First user**: oumarsanii@yahoo.co.uk (Umar Muhammad Sani)
- **ETH address**: 0x57Fb8eEDef807bDFC5E943f3335d1...

## 🛠️ Key Deploy Fixes Applied
1. Renamed GitHub repo (`-Vaulted.app` → `vaulted-app`) to fix leading-dash CLI issue
2. Switched backend from Railway → Render (better mobile UX)
3. Removed private Emergent deps from requirements.txt (`emergentintegrations`, `litellm`)
4. Fixed Render Start Command (iOS Smart Punctuation `--` → `—` issue)
5. Hardcoded fallback BACKEND_URL in `api.ts` with auto-https:// prefix
6. Added certifi `tlsCAFile` to MongoDB connection (PyMongo + Atlas best practice)
7. Added `0.0.0.0/0` to Atlas Network Access (Render IPs aren't fixed)

## ⚠️ Free-Tier Caveats
- **Render**: spins down after 15 min inactivity → ~30s cold start on next request
- **Atlas M0**: 512 MB storage, shared resources, fine for early production
- **Vercel hobby**: 100 GB bandwidth/month, plenty for early users
