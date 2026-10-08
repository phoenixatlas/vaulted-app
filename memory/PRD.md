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

## 🔗 Kotani Pay v3 Webhook Hardening (Iter 44, 2026-10)
- **Signature verification**: Rewrote `kotani.verify_webhook_signature` to handle Kotani v3's `sha256=<hex>` header format over canonical `JSON.stringify({event, data})`. Keeps raw-body fallback for direct-callback mode.
- **Status enum**: Added `TERMINAL_SUCCESS/FAILURE/REFUND` constants + `classify_status()` helper so `SUCCESSFUL` (Kotani v3) and `SUCCESS` (legacy mock) both map to `settled`.
- **Receipt extraction**: `extract_mpesa_receipt()` reads `telcoId` (offramp/withdrawal camelCase), `telco_id` (deposit snake_case), and legacy `receipt.mpesaReceipt`.
- **Event dispatcher**: `/api/offramp/callback` now routes `transaction.{offramp,onramp,deposit,withdrawal}.status.updated`, `refund.{completed,failed}`, and settlement/kyc events to dedicated handlers.
- **Onramp booking**: Added `kotani.create_onramp()` + `kotani.onramp_status()` to complete inbound-remit flow once Kotani enables the service.
- **Admin webhook-echo**: `GET /api/admin/kotani/webhook-echo` surfaces last 20 raw deliveries, config checklist, and expected webhook URL. `POST /api/admin/kotani/webhook-echo/replay` fires a synthetic signed envelope end-to-end for QA.
- **UI**: New `KotaniWebhookEchoCard` in `/admin` shows checklist (API key, secret, URL registered, signatures valid), subscribed events, latest deliveries, and a "Fire test delivery" button.
- **Tests**: `tests/test_kotani_webhook_v3.py` — 29 unit tests covering canonical/raw signature paths, status enum, snake/camel field picker, receipt extraction.

## 🧪 Kotani Pay — Smoke Test, Receipts, Settlements (Iter 45, 2026-10)
- **Smoke test** (`POST /api/admin/kotani/smoke-test?corridor=KE`): runs health → rate → customer → booking → dispatcher as 5 independent steps; surfaces Kotani error payloads (e.g. "Service mobile_money_customers is not enabled for your account") verbatim so operators can forward to Kotani support.
- **Settlement receipts** (`POST /offramp/callback` → `_handle_offramp_event`): on `bucket == "settled"`, auto-generates a branded A4 PDF (`backend/receipt.py`) and emails it as a Resend attachment via `send_offramp_receipt_email`. Idempotency flag `receipt_emailed_at` prevents double-sending on Kotani retry.
- **User-facing re-download**: `GET /api/transactions/{tx_id}/receipt.pdf` — gated to tx owner + settled status.
- **Live settlement rollup** (`GET /api/admin/kotani/settlements?days=30`): daily aggregation of settled offramps with per-currency reconciliation (quoted vs settled fiat delta). `delta_pct > 0.5%` auto-highlighted as warning in UI.
- **UI**: Three new cards on `/admin` — `KotaniSmokeTestCard` (6-corridor pills + stepper + verdict banner), `KotaniSettlementsCard` (4-stat grid + 7-day breakdown with reconciliation chips).

## 📄 Partner Use Case Generator — 9PSB (Iter 46, 2026-10)
- **New module** `backend/usecase.py`: parameterised 2-page PSB brief with `UseCaseContent` dataclass.
- **Positioning**: Vaulted framed as **infrastructure/rail**, not consumer wallet. Opening and strategic-fit sections lead with "developer-grade API, SDK, settlement engine" and "deliberately invisible to end user".
- **Content sections**: Opportunity (4 stat tiles) · Strategic fit (4 bullets) · Technical integration model (Rail API, Compliance stack, Settlement engine, White-label SDK) · Commercial options (Per-tx fee / Exclusive corridor licence / Strategic equity) · Roadmap (60d integration · 90d pilot · 12m exclusive rail) · Next steps.
- **Routes** (`routers/usecase_router.py`): `GET /api/usecase/psb.pdf` and `.docx`. Both accept `bank_name`, `bank_short`, `recipient_*` as query params so Umar can regenerate for MoMo / SmartCash / Hope PSB from the same codebase.
- **Admin UI**: new "Partner use case · 9PSB" card on `/admin` with DOCX + PDF download buttons and inline tip for per-bank customisation.

## 📬 One-Click PSB Use Case Dispatcher (Iter 47, 2026-10)
- **Backend**: 3 new routes
  - `POST /api/admin/usecase/send` — composes branded cover email + attaches PDF + sends via Resend. Returns `send_id` and `resend_id`. Idempotent on `send_id`.
  - `GET /api/admin/usecase/sends` — paginated history with status counters (sent / delivered / opened).
  - `POST /api/admin/usecase/resend-webhook` — public endpoint that correlates Resend `email.delivered/opened/clicked/bounced` events to `usecase_sends` rows via `send_id` tag.
- **Cover email**: `usecase.build_usecase_cover_html` — dark gold-on-ink Vaulted-branded body with optional per-recipient `cover_note` override + optional "Book a working session" CTA.
- **Reply tracking**: Resend tags carry `send_id`; webhook writes `delivered_at`, `opened_at`, `clicked_at` back on the send row. Replies land directly in `umar.sani@phoenix-atlas.com` via `reply_to`.
- **DB**: new `usecase_sends` collection.
- **Admin UI**: `PartnerUseCaseCard` replaces previous download-only card. Inline form (bank_short, bank_name, recipient_email/name/title, optional cover note) + Send button + Preview/Edit links + collapsible send history with per-row status chips (SENT / DELIVERED / OPENED / BOUNCED / FAILED).
- **Resend webhook config**: In Resend dashboard, add webhook URL `https://vaulted-app.onrender.com/api/admin/usecase/resend-webhook` subscribed to `email.*` events for full reply tracking.

## 🔒 Session Expiry UX + Re-probe Fix (Iter 48, 2026-10)
- **`api.ts`**: New `ApiError` class exposing HTTP status; module-level 401 handler registry so any 401 from any screen triggers a global sign-out + "session expired" state. Auto-clears stale JWT so subsequent cold starts land on `/sign-in` cleanly.
- **`admin/index.tsx`**: Full-screen "Session expired" takeover (lock icon + explanation + "Sign in again" + retry link) replaces the previous nine "Not authenticated" error cards.
- **`app/(auth)/login.tsx`**: Reads `?returnTo=/admin` query param (same-origin only, defends against open-redirect) so operators land back on `/admin` after re-authentication instead of being bounced to the wallet.
- **Re-probe fix**: `load()` now sets `setLoading(true)` at the start — previously the fetch fired silently with no visual feedback. "Re-probe" button shows spinner + "Probing…" label and is disabled during the request.
- **PDF signoff**: 9PSB use-case PDF sign-off block is now anchored 58mm from the page bottom so "Yours sincerely / Umar Sani / Founder & CE / email" never collides with the Phoenix-Atlas footer, regardless of body length above it.

## 🔐 Session Refresh + Biometric Gate + Contact Book (Iter 49, 2026-10)

### Feature 1 — Refresh Tokens
- **Backend**: `auth_tokens.py` module (SHA-256 hashed-at-rest refresh tokens, 30d TTL, rotation on every use, reuse detection → family revocation, TTL index). Three new routes: `POST /auth/refresh`, `POST /auth/logout`, plus `/auth/login` + `/auth/register` now return `refresh_token` + `expires_in`.
- **Frontend**: `api.ts` extended with `getRefreshToken`/`saveSession`/`refreshAccessToken`. Single-flight refresh lock prevents concurrent 401s from rotating the same token. On 401, api() silently refreshes once and retries the original request transparently.
- **Env**: `ACCESS_TOKEN_MINUTES=60`, `REFRESH_TOKEN_DAYS=30` added (backwards-compat with legacy 7-day access tokens if env unset).
- **Live-tested**: login→rotate→replay→family-revoke→logout flow all pass.

### Feature 2 — Admin Biometric Gate
- **New component**: `src/components/AdminBiometricGate.tsx` wraps `/admin` behind Face ID / Touch ID / device PIN using `expo-local-authentication`.
- **Opt-in**: `AdminBiometricNudge` shows a one-time "Enable Face ID?" prompt after first successful admin visit. Preference stored in SecureStore (`admin_biometric_enabled`), independent of the wallet-level biometric.
- **Graceful fallbacks**: pass-through on web, no-hardware, or no-enrolment devices. Toggleable from Tools card.

### Feature 3 — Partner Contact Book
- **Backend**: `routers/contacts_router.py` with full CRUD on `partner_contacts` collection. `POST /admin/contacts/{id}/touch` for recency ranking. First contact per bank auto-promoted to primary.
- **Frontend**: Dispatcher card now auto-fills recipient fields from the primary contact when `bank_short` changes. "N saved contacts" expander shows grouped list for one-tap application. "+ Save to contacts" button on new recipients.


## 🛠️ Vercel Build Hotfix (Iter 50, 2026-10)
- **Issue**: Production deploy on commit `9bee927` failed with `yarn expo export --platform web --output-dir dist` exit 1.
- **Root cause**: `src/components/AdminBiometricGate.tsx` imported `Ionicons` from `@react-native-vector-icons/ionicons`, a package not installed in `package.json` (rest of the app uses `@expo/vector-icons`).
- **Fix**: Switched import to `@expo/vector-icons`. Local `yarn expo export --platform web` now completes cleanly (3.17 MB bundle).
- **Action for user**: Push to `main` (or hit **Redeploy** on Vercel) to get production back on the latest commit.

## 🧹 Admin Dashboard Refactor + Weekly Digest (Iter 51, 2026-10)

### Admin split
- `/app/frontend/app/admin/index.tsx`: 2539 → 329 lines. Now a thin orchestrator owning data-fetch, 401 session takeover and per-card error routing.
- New folder `/app/frontend/src/features/admin/`:
  - `types.ts` (shared Mongo/API types + CORRIDOR_FLAGS)
  - `styles.ts` (single StyleSheet — pulled verbatim; zero visual change)
  - `common.tsx` (ProbeRow + Chip)
  - `index.ts` (barrel export)
  - One file per card: `KotaniHealthCard`, `WaitlistCard`, `DailySignupsCard`,
    `CorridorMatrixCard`, `ReferralLeaderboardCard`, `InvestorLeadsCard`,
    `BookClicksCard`, `KotaniWebhookEchoCard`, `KotaniSmokeTestCard`,
    `KotaniSettlementsCard`, `PartnerUseCaseCard`, `LetterheadCard`,
    `ToolsCard`, `WeeklyDigestCard`.
- Local `yarn expo export --platform web` passes clean. ESLint clean on all admin files.

### Weekly Settlement Digest (new feature)
- **Backend `digest.py`**: data collector + HTML renderer + Mongo-persisted
  config + scheduler tick. Pulls settlements, outstanding tx, waitlist
  delta, use-case opens and Kotani readiness. Resend-sent via existing
  `send_email_via_resend`.
- **Router `routers/digest_router.py`**: `GET/POST /admin/digest/config`,
  `GET /admin/digest/preview`, `POST /admin/digest/send-now`,
  `POST /admin/digest/cron` (header-authed via `DIGEST_CRON_SECRET`),
  `GET /admin/digest/log`.
- **Scheduler**: in-process 15-min ticker in `server.py` startup fires the
  digest on the configured weekday (default Monday) + hour (default 07:00 UTC)
  and gates on `last_sent_at` so a restart during the window never
  double-sends. External cron providers can hit `/api/admin/digest/cron`
  for belt-and-braces.
- **Mongo collections**: `digest_config` (singleton `_id="weekly_digest"`),
  `digest_log` (one row per send).
- **Admin UI `WeeklyDigestCard`**: toggle, weekday + hour pickers, recipient
  CRUD, "Send now" button, inline web-only preview pane, last-sent snapshot
  stats and error surfacing.
- **Env vars (optional)**: `DIGEST_WEEKDAY`, `DIGEST_HOUR_UTC`,
  `DIGEST_DEFAULT_RECIPIENTS`, `DIGEST_CRON_SECRET`, `DIGEST_SUBJECT_PREFIX`.
  All defaults work out-of-the-box without any env changes.

## 🔄 Waitlist Resend Reconciliation (Iter 52, 2026-10)
- **Issue**: Production admin dashboard showed 0 waitlist signups while
  Resend audiences contained real contacts captured via phoenix-atlas.com.
  Likely root cause: Mongo data loss between signup time and view time
  (Render free-tier reset, redeploy with different `MONGO_URL`, etc.).
- **Fix**: Added Resend-as-source-of-truth reconciliation.
  - `GET /api/admin/waitlist/audit` — compares Mongo count vs live Resend
    audience contact counts, lists missing emails and per-audience gaps.
  - `POST /api/admin/waitlist/sync-from-resend` — idempotent import that
    upserts every Resend contact into `db.waitlist`, decoding corridor /
    direction / source from the `last_name` tag we stash at write time.
  - New `WaitlistSyncCard` on `/admin` showing side-by-side counts, gap,
    sample missing emails, per-audience breakdown and a one-click
    "Import N from Resend" action.
  - On successful sync, parent `admin/index.tsx` refetches so Waitlist +
    Daily signups + Corridor matrix cards update immediately.

## 🌙 Nightly Resend → Mongo Auto-Sync (Iter 53, 2026-10)
- Extended Iter 52 reconciliation with a scheduled job so missing
  signups never require a manual tap again.
- **Backend**: refactored sync helpers to module scope in
  `routers/waitlist.py` and exposed `run_resend_sync()`,
  `run_resend_audit()`, `waitlist_sync_scheduler_tick()`,
  `get_sync_config()`, `set_sync_config()`.
- **Scheduler**: in-process 15-min ticker added to `server.py` startup.
  Fires inside the configured hour window (default 02:00 UTC) and gates
  on `last_run_at < 20h` so restarts never cause double runs.
- **Endpoints**: `GET/POST /api/admin/waitlist/sync-config` for toggle +
  hour; `GET /api/admin/waitlist/audit`,
  `POST /api/admin/waitlist/sync-from-resend` already shipped.
- **Mongo collections**: `waitlist_sync_config` (singleton), `waitlist_sync_log` (history).
- **UI**: `WaitlistSyncCard` now shows nightly config (ARMED / PAUSED pill,
  toggle, UTC hour input + BST/Nairobi preview), last-run timestamp +
  5-row recent history disclosure.
- **Env vars**: `WAITLIST_SYNC_ENABLED` (default true), `WAITLIST_SYNC_HOUR_UTC` (default 2).

## ✉️ Multi-Recipient Partner Use-Case Send (Iter 54, 2026-10)
- **Issue**: Pasting a comma-separated list of PSB emails into
  "Recipient email" triggered a Pydantic `EmailStr` validation error.
- **Fix**:
  - Backend `UseCaseSendIn` now accepts a plain string with a custom
    validator that splits on `,;` or whitespace and validates each
    segment — same forgiveness as Gmail's To field. Rejects a single
    malformed address with the offending email in the error message.
  - Endpoint fans out one send per recipient (unique `send_id` per
    person for per-recipient open/click tracking) and returns a batch
    result when more than one address was supplied; single-recipient
    callers get the legacy response shape so existing integrations keep
    working.
  - Frontend `PartnerUseCaseCard` parses the input live, hints
    "Separate multiple with commas", expands the field into a 2-line
    textarea when >1 recipient is detected, updates the button copy to
    `Send to N recipients at 9PSB`, surfaces per-recipient success /
    failure in the result message, and translates Pydantic
    `not a valid email` errors into a clearer hint.
  - "+ Save to contacts" is retained — it saves the first parsed
    address only so operators can still bank one new contact per
    multi-recipient send without creating duplicates.

## 📝 Draft Editor + CC + Grouped History + Signup Alerts + Mongo Backup (Iter 55, 2026-10)

### Full-fat draft editor for the use-case dispatcher
- New Mongo collection `usecase_drafts` with CRUD + preview + direct-send
  endpoints under `/api/admin/usecase/drafts/*`.
- `UseCaseSendIn` extended with `body_text`, `greeting_override`,
  `cta_text` and `draft_id`. Blank-line-separated paragraphs become
  `<p>` tags; HTML is escaped so operators cannot accidentally break
  the brand template.
- Rewrote `PartnerUseCaseCard` as a true compose/edit/preview/send
  surface: Subject, Greeting, Body (big multiline), CTA, Booking URL,
  Draft label — every field is editable and autosaved on Send.
- Draft drawer at the top of the card lists all unsent drafts plus a
  "Recently sent" section with one-tap duplicate-to-new-draft.
- "Save*" button flips to "Saved" after a clean write; Send auto-saves
  so the archived draft matches what was actually dispatched.

### CC field
- New `cc` input on the card parses commas/newlines, dedupes, and
  stashes recipients separately from the primary To list.
- Backend validator accepts both an array OR comma-strings per entry
  so pasting from Outlook/Gmail works verbatim.

### Reply-All aware Sent history
- `usecase_sends` rows now always carry `batch_id` (equal to the
  base send_id for singles, shared across fan-outs for groups).
- `SendHistoryGroup` component collapses batches into one row with a
  per-recipient disclosure. One 3-person 9PSB blast reads as a single
  entry showing e.g. "3 opened · 9PSB".

### Signup alert email
- `_add_and_confirm` fires a branded Resend email on every new
  waitlist signup — includes corridor flag, direction arrow, position,
  referral code, and a jump-to-admin CTA.
- `/api/admin/waitlist/alert-config` endpoints + `SignupAlertCard` on
  the admin dashboard for toggle + recipient CRUD.
- Env var fallback `WAITLIST_ALERT_RECIPIENTS` for zero-UI setup.

### Weekly Mongo backup snapshot
- New `backup.py` module + `routers/backup_router.py`.
- `/api/admin/backup/config` for toggle, weekday, hour and collections list.
- `/api/admin/backup/run-now` for manual trigger.
- Dumps 13 critical collections into gzip'd JSON (~10-20x compression)
  and emails via Resend with filename `vaulted-backup-YYYYMMDD-HHMM.json.gz`.
- In-process scheduler ticks every 15 min; fires once a week on the
  configured weekday (default Sunday) + hour (default 03:00 UTC) and
  gates on `last_sent_at < 6 days` for idempotency.
- `BackupCard` on admin dashboard shows last-run doc count + size +
  delivered-to list + manual-trigger button.
- Env vars: `BACKUP_WEEKDAY`, `BACKUP_HOUR_UTC`, `BACKUP_RECIPIENTS`, `BACKUP_COLLECTIONS`.
