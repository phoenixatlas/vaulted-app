# Vaulted Deployment — Step-by-Step Checklist

Repo: https://github.com/phoenixatlas/-Vaulted.app

---

## ✅ Done
- [x] Code pushed to GitHub

## 🟡 Up next — in order

### Step 1: MongoDB Atlas (5 min) — get the database online
1. Sign up at https://www.mongodb.com/cloud/atlas
2. Click **"Build a Database"** → choose the **FREE M0 Shared** tier
3. Pick any cloud provider/region (AWS, us-east-1 is fine)
4. **Username + password**: pick something memorable, save it
5. **Network Access** tab → click **"Add IP Address"** → choose **"Allow Access from Anywhere" (0.0.0.0/0)** (we'll tighten this later)
6. **Database tab** → click **"Connect"** → choose **"Drivers"** → copy the SRV string (it looks like `mongodb+srv://USER:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority`)
7. Replace `<password>` with your actual password
8. ✋ **Send this string back to me** — I'll add it to Railway with you

---

### Step 2: Railway (backend, 10 min)
1. Sign up at https://railway.com (use the "Login with GitHub" button)
2. Click **"New Project"** → **"Deploy from GitHub repo"**
3. Pick **`-Vaulted.app`** from the list
4. Railway will ask for a **service root directory** → set it to `backend`
5. It will auto-detect the `Procfile` and start building

While it builds, click **"Variables"** in the service and paste these (copy values from `/app/backend/.env` in Emergent):

| Variable | Where to get it |
|---|---|
| `MONGO_URL` | The SRV string from Step 1 |
| `DB_NAME` | `vaulted` (just pick a name) |
| `JWT_SECRET` | Run in terminal: `openssl rand -hex 32` (or any 32+ random chars) |
| `STRIPE_API_KEY` | Copy from `/app/backend/.env` line `STRIPE_API_KEY=` |
| `STRIPE_WEBHOOK_SECRET` | Copy from `/app/backend/.env` |
| `RESEND_API_KEY` | Copy from `/app/backend/.env` |
| `DAILY_API_KEY` | Copy from `/app/backend/.env` |
| `DAILY_DOMAIN` | Copy from `/app/backend/.env` |
| `SEPOLIA_RPC_URL` | Optional — leave blank to use the public default |
| `APP_PUBLIC_URL` | **Set later** once Vercel gives us the frontend URL |
| `CORS_ALLOW_ORIGINS` | **Set later** once Vercel URL is known |
| `MULTISIG_THRESHOLD_ETH` | `0.05` (or whatever value is in `.env`) |
| `VAULT_PRO_PRICE_USD` | `9` (or whatever value is in `.env`) |

(Skip `EMERGENT_PUSH_KEY` — push notifications only work inside Emergent infra.)

5. After the deploy finishes, **click the public domain** Railway gives you (something like `vaulted-api-production.up.railway.app`)
6. Append `/api/health` to it — should see `{"status":"ok"}`
7. ✋ **Send me that Railway URL** — we'll plug it into Vercel next

---

### Step 3: Vercel (frontend web, 5 min)
1. Sign up at https://vercel.com with **"Continue with GitHub"**
2. Click **"Add New… → Project"**
3. Pick **`-Vaulted.app`** → click **"Import"**
4. **Root Directory** → click **"Edit"** → set to `frontend`
5. **Framework Preset** → leave on **"Other"** (Vercel will read our `vercel.json`)
6. Expand **"Environment Variables"** → add:
   - `EXPO_PUBLIC_BACKEND_URL` = your Railway URL from Step 2
7. Click **"Deploy"**
8. Once it finishes, you'll get a `*.vercel.app` URL
9. ✋ **Send me the Vercel URL**

---

### Step 4: Final wiring (I'll handle this with you)
- Go back to Railway → add the Vercel URL as `CORS_ALLOW_ORIGINS` and `APP_PUBLIC_URL`
- Smoke-test login with `smoketest@vaulted.app / test1234`
- Update Stripe webhook URL to the Railway endpoint
