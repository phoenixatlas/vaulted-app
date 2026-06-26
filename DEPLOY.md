# Vaulted — Deploying to Vercel (web frontend) + Railway (backend) + MongoDB Atlas

This guide assumes you've already pushed `/app` to a GitHub repo.

---

## 1. MongoDB Atlas (free shared cluster)
1. Create a free cluster at https://www.mongodb.com/cloud/atlas
2. Add a database user + password.
3. In **Network Access** allow `0.0.0.0/0` (or just Railway's egress IPs).
4. Copy the **SRV connection string** — looks like:
   `mongodb+srv://USER:PASS@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority&appName=Vaulted`
5. Keep this for the Railway env vars.

## 2. Backend on Railway
1. Sign up at https://railway.com and click **New Project → Deploy from GitHub repo**.
2. Pick this repo. When asked for the service root, choose `/backend` (or set `RAILWAY_SERVICE_ROOT_DIR=backend` in the service settings).
3. Railway auto-detects `Procfile` / `nixpacks.toml`.
4. Add the following environment variables in **Service → Variables**:

   | Variable | Value |
   |---|---|
   | `MONGO_URL` | Atlas SRV connection string |
   | `DB_NAME` | `vaulted` (or anything you want) |
   | `JWT_SECRET` | 32+ random bytes — `openssl rand -hex 32` |
   | `CORS_ALLOW_ORIGINS` | `https://YOUR-VERCEL-DOMAIN.vercel.app` (no trailing slash) |
   | `STRIPE_SECRET_KEY` | copy from existing `/app/backend/.env` |
   | `RESEND_API_KEY` | copy from `.env` |
   | `RESEND_TARGET_DOMAIN` | `phoenix-atlas.com` |
   | `RESEND_TARGET_FROM` | `Vaulted <noreply@phoenix-atlas.com>` |
   | `DAILY_API_KEY` | copy from `.env` |
   | `EMERGENT_PUSH_KEY` | placeholder (real value supplied by Emergent CI on their infra; on Railway leave it empty if push isn't needed) |
   | `APP_URL` | Your Vercel URL — used in multi-sig approval emails |

5. Click **Deploy**. Railway will run `pip install -r requirements.txt` then `uvicorn server:app`.
6. Once it's live, copy the public URL (e.g. `https://vaulted-api.up.railway.app`). You'll need this for step 3.

### Health check
There's no `/api/health` route yet — Railway's default TCP health check on `$PORT` is fine. If you want a real check, add this near `app = FastAPI(...)`:
```python
@app.get("/api/health")
async def health():
    return {"status": "ok"}
```
Then set `healthcheckPath: /api/health` in `railway.json` (already there).

## 3. Frontend on Vercel (Expo web export)
1. Sign up at https://vercel.com and **Import** the GitHub repo.
2. Set **Root Directory** to `frontend`.
3. **Framework Preset**: `Other`. (Vercel will pick up `vercel.json`.)
4. Add the env var:

   | Variable | Value |
   |---|---|
   | `EXPO_PUBLIC_BACKEND_URL` | the Railway URL from step 2 (e.g. `https://vaulted-api.up.railway.app`) |

5. Deploy. Vercel will run `yarn expo export --platform web --output-dir dist`.
6. Once live, grab the Vercel URL and **paste it back into Railway as `CORS_ALLOW_ORIGINS`** so the API will accept calls from it.
7. Also update `APP_URL` on Railway to the same Vercel URL so multi-sig approval emails contain the correct deep links.

## 4. Native (iOS / Android) builds
Web is on Vercel; native iOS/Android need an EAS build (separate from Vercel).
```bash
cd frontend
npx eas build --platform ios
npx eas build --platform android
```
Make sure `EXPO_PUBLIC_BACKEND_URL` is set the same way in your `eas.json`'s build profile env block, pointing at the Railway URL.

## 5. Stripe webhooks
If you turn off Stripe's test mode, update the Stripe **Dashboard → Webhooks** endpoint to:
```
https://YOUR-RAILWAY-URL/api/stripe/webhook
```
and store the new webhook signing secret in Railway as `STRIPE_WEBHOOK_SECRET`.

## 6. Push notifications
Emergent push requires the deploy-time-supplied `EMERGENT_PUSH_KEY`, which is *not* available outside Emergent's infrastructure. Two options:
- **Disable pushes for the Railway/Vercel deploy** — the backend gracefully no-ops; the app keeps working.
- **Swap to Expo Push** — replace `https://integrations.emergentagent.com/api/v1/push/trigger` calls in `server.py` with `https://exp.host/--/api/v2/push/send` (open API, no key required) and store device tokens in MongoDB.

## 7. Smoke-test after deploy
```bash
BASE=https://YOUR-RAILWAY-URL
curl $BASE/api/auth/login -H 'content-type: application/json' \
  -d '{"email":"smoketest@vaulted.app","password":"test1234"}'
```
Should return a JSON `{ "access_token": "..." }`. Then load the Vercel URL in a browser — login should work end-to-end.

---

### Notes / common pitfalls
- **Browser & credentials**: We set `allow_credentials=True` only when `CORS_ALLOW_ORIGINS` is a real domain list. Wildcard (`*`) + credentials is rejected by browsers, so wildcard automatically falls back to credentials-off.
- **Mongo IP allowlist**: If Railway IPs change, you may need to re-allowlist or use `0.0.0.0/0` for simplicity.
- **Daily.co + WebView**: Native iOS/Android needs a real device build to test video. The WebView fallback works on web.
- **Sepolia RPC**: Uses the public `https://ethereum-sepolia-rpc.publicnode.com` — no key required.
