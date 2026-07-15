#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: |
  Cross-border remittance-focused crypto self-custody wallet (Vaulted / Phoenix Atlas).
  Iteration 22 goal: (1) Change login tagline to "Sending money should never be
  slower than sending a message." (2) Extend Send Money screen to let users fund
  a cross-border send with EITHER their crypto wallet OR fiat (Card / Apple Pay /
  Bank transfer via Stripe). (3) Add Forgot / Reset password flow via existing
  Resend integration.

backend:
  - task: "Forgot / Reset password endpoints (Resend email + single-use JWT)"
    implemented: true
    working: true
    file: "/app/backend/server.py + /app/backend/audit.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: |
          Added POST /api/auth/forgot-password (idempotent, rate-limited 3/hr,
          never reveals whether email exists) + POST /api/auth/reset-password
          (single-use JWT nonce, 30-min TTL, burns nonce on use + invalidates
          parallel outstanding tokens). Sends email via existing Resend
          integration to APP_PUBLIC_URL/reset-password?token=xxx. New audit
          events: AUTH_FORGOT_PASSWORD_REQUESTED, AUTH_PASSWORD_RESET_COMPLETED,
          AUTH_PASSWORD_RESET_INVALID_TOKEN.
      - working: true
        agent: "testing"
        comment: |
          Iteration 22 test: 11/12 passed. Verified idempotent 200 for both real
          and unknown emails, rate limit caps nonces to 3/hr, bogus tokens 400,
          happy path mint→reset→login, reused token 400 "already used".

  - task: "/api/remit/fund — fiat funding for cross-border sends"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: |
          New endpoint creates a Stripe Checkout session for a remittance
          funded by fiat. Enforces same gates as /remit/send (corridor block,
          free-tier limit, KYC tier). Extended _apply_checkout_session to
          handle flow="remit_fund": books a transaction with funding_method
          ="stripe", status="processing", and no on-chain settlement (rails
          hidden). Audits as REMIT_SEND_SUCCESS with funding_method="stripe".
      - working: false
        agent: "testing"
        comment: |
          payment_method=bank returned 502 because customer_balance requires
          funding_type. Card + apple_pay worked, corridor block worked,
          unauthenticated blocked correctly.
      - working: true
        agent: "main"
        comment: |
          Fixed by making the bank branch omit payment_method_types entirely
          so Stripe Checkout auto-shows every method enabled in the dashboard
          for that region (cards + BACS/SEPA/ACH + wallets). Re-verified all
          three payment_method values return valid checkout_urls.

  - task: "Kotani Pay off-ramp (USDC → M-Pesa KES) — MOCKED, auto-flips to LIVE"
    implemented: true
    working: true
    file: "/app/backend/kotani.py + /app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: |
          New module /app/backend/kotani.py: async client for Kotani Pay v3
          off-ramp API (https://documentation.kotanipay.com/v3). Runs in MOCK
          mode when KOTANI_API_KEY is empty or set to "MOCKED"; auto-flips to
          LIVE the moment a real key lands in /app/backend/.env. Every
          response mirrors the real {success, message, data} envelope so
          downstream code doesn't change on go-live.

          Endpoints wired into server.py:
          - POST /api/offramp/mpesa/quote (auth user; returns Kotani rate quote)
          - GET  /api/offramp/mpesa/status/{ref_id} (auth user; owner-scoped)
          - POST /api/offramp/callback (Kotani webhook receiver; HMAC-SHA256
            signature verification via X-Kotani-Signature when
            KOTANI_WEBHOOK_SECRET is configured)
          - GET  /api/offramp/health (admin-only diagnostic)

          Auto-integration into fiat-funded remit flow: when Stripe checkout
          completes and metadata.destination_code == "KE", the backend
          automatically calls kotani.create_offramp() to disburse KES to the
          recipient's M-Pesa. In MOCK mode this returns SUCCESS immediately
          and the tx flips to status="settled" for a delightful demo UX.

          Callback handling verified end-to-end (SUCCESS + FAILED terminal
          states, unmatched refs handled gracefully, single-use tx state
          updates atomically).

          Env vars added to /app/backend/.env:
          - KOTANI_API_KEY=MOCKED (replace with sandbox key when Kotani
            approves the integrator account)
          - KOTANI_BASE_URL=https://sandbox-api.kotanipay.io
          - KOTANI_WEBHOOK_SECRET= (blank in dev; set once sandbox is live)
          - KOTANI_MOCK= (force-mock override for tests)

          Audit event types added: OFFRAMP_MPESA_INITIATED,
          OFFRAMP_MPESA_SUCCESS, OFFRAMP_MPESA_FAILED, OFFRAMP_MPESA_REFUNDED,
          OFFRAMP_WEBHOOK_INVALID_SIGNATURE.

          Frontend receipt.tsx now shows an "M-Pesa receipt" row when
          Kotani has settled + hides all crypto rail language for fiat
          sends. remit.tsx passes kotani_json + kotani_reference_id +
          mpesa_receipt to the receipt route params.

  - task: "Original: XLM backfill for existing (pre-XLM) users"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: |
          User reported XLM missing on their wallet even after clearing Safari cache.
          Root cause: /wallet/assets only iterates over db.balances rows; users who
          registered before XLM was added had no XLM row so it never appeared.
          Fix: added an auto-backfill inside /wallet/assets that inserts any missing
          DEFAULT_ASSETS row for the current user (and strips the injected _id so
          FastAPI can serialize the response). Verified locally by deleting the XLM
          row for a fresh user and re-hitting the endpoint — XLM re-appears in DB
          + response.

  - task: "XRP (Ripple) full-stack implementation"
    implemented: true
    working: true
    file: "/app/backend/multichain.py + /app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: |
          - Added XRP to DEFAULT_ASSETS / SEED_BALANCES.
          - `derive_addresses` now returns xrp (BIP-44 path m/44'/144'/0'/0/0 via bip_utils).
          - `_xrp_wallet_from_mnemonic` maps the bip_utils secp256k1 key → xrpl-py Wallet
            (public_key hex + "00"-prefixed private_key hex).
          - `fetch_xrp_balance_drops` via XRPL account_info JSON-RPC.
          - `xrp_send` uses xrpl.asyncio.transaction.autofill_and_sign +
            submit_and_wait for a truly-async broadcast (avoids nested event-loop
            bug from mixing sync/async xrpl-py APIs).
          - Endpoints: GET /api/wallet/xrp/info (address, balance, network,
            explorer, faucet, min_reserve_xrp) and POST /api/wallet/xrp/send.
          - Reserve pre-flight check (1 XRP testnet / 10 XRP mainnet) before signing.
          - Verified end-to-end on live XRPL testnet: funded via
            https://faucet.altnet.rippletest.net/accounts (100 XRP), sent 5 XRP to
            rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh, real tx_hash 9867119F...86D9 mined
            successfully on testnet.
          - xrpl-py 5.0.0 added to requirements.txt (emergentintegrations and
            litellm re-introduced by pip freeze were manually stripped again since
            they break Render deployment).

frontend:
  - task: "XRP + XLM UI (send / receive / wallet chip)"
    implemented: true
    working: true
    file: "/app/frontend/app/send.tsx + receive.tsx + src/lib/theme.ts"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: |
          - ASSET_ICON_COLORS: added XLM (#08B5E5 Stellar electric blue) + XRP
            (#23292F Ripple charcoal) to give both chains proper brand pills
            (user reported the XLM logo was hard to see).
          - send.tsx: added isXrp branch (chain-aware placeholders, fee copy,
            memo field, faucet link, POST /wallet/xrp/send call).
          - receive.tsx: Asset type/labels/paths/badges extended for XRP;
            chip row converted to horizontal ScrollView so all 6 chains fit
            without overflow on small phones.
          - Confirmed via Playwright screenshot (login as smoketest, wallet
            renders BTC, ETH, USDC, SOL, XLM, XRP with distinct brand colors).

metadata:
  created_by: "main_agent"
  version: "1.3"
  test_sequence: 16
  run_ui: false

backend_new_endpoints_this_iteration:
  - task: "Remit — cross-border remittance quote + send (Phase B)"
    implemented: true
    working: true
    file: "/app/backend/remit.py + /app/backend/server.py"
    priority: "high"
    needs_retesting: true
    endpoints:
      - "GET /api/remit/corridors (public — no auth)"
      - "POST /api/remit/quote (auth) — {source_fiat, amount, destination_code}"
      - "POST /api/remit/send (auth) — {source_fiat, amount, destination_code, recipient_address, recipient_name?, memo?}"
    key_behaviours:
      - "Free tier gate: 3 remit sends/month/user, 4th → HTTP 402 with paywall CTA"
      - "Server-side re-quote on /send to prevent client-side rate/fee cheating"
      - "Chain selector picks cheapest chain user has liquidity on"
      - "Fresh users have 0 balance so quotes should show sufficient_balance=false with reason_if_no_chain populated"
      - "Persists a 'remit' object on the transactions record (source/dest ccy, amounts, fx_rate, receive_via, chain)"

  - task: "XRP (Ripple) chain — full-stack"
    implemented: true
    working: true
    file: "/app/backend/multichain.py + /app/backend/server.py"
    priority: "high"
    needs_retesting: true
    endpoints:
      - "GET /api/wallet/xrp/info (auth)"
      - "POST /api/wallet/xrp/send (auth) — {to_address (r...), amount, memo?}"
    key_behaviours:
      - "Address derivation: BIP-44 m/44'/144'/0'/0/0 → xrpl-py Wallet"
      - "Balance fetch via XRPL account_info JSON-RPC"
      - "Reserve pre-flight (1 XRP testnet / 10 XRP mainnet)"
      - "Verified end-to-end on live XRPL testnet: tx 9867119F...86D9 mined (main agent)"

  - task: "EVM L2 chains — Polygon / Base / Arbitrum for cheap USDC"
    implemented: true
    working: true
    file: "/app/backend/evm.py + /app/backend/server.py"
    priority: "high"
    needs_retesting: true
    endpoints:
      - "GET /api/wallet/evm/chains (auth) — returns all 4 L2s with usdc_balance + native_balance per chain"
      - "POST /api/wallet/evm/usdc/send (auth) — {chain: 'polygon'|'base'|'arbitrum'|'sepolia', to_address, amount_usdc}"
    key_behaviours:
      - "GET /wallet/assets now aggregates USDC across all EVM chains and exposes usdc_by_chain breakdown"
      - "Same 0x address holds USDC on every EVM chain (no new key derivation)"
      - "USDC contract per chain uses Circle's official Sepolia/Amoy/Base-Sep/Arb-Sep deployments"
      - "Remit chain selector considers USDC_POLYGON/USDC_BASE/USDC_ARBITRUM as first-class ~$0.01-gas routes"

  - task: "XLM backfill for existing (pre-XLM) users"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    priority: "high"
    needs_retesting: true
    key_behaviours:
      - "Any missing symbol from DEFAULT_ASSETS is auto-inserted into db.balances on next /wallet/assets fetch"
      - "Injected Mongo _id is stripped before response (prevents ObjectId serialization bug)"
      - "Now applies to XLM AND XRP for legacy accounts registered before those chains shipped"

test_plan:
  current_focus:
    - "Backend sweep — validate all new remit + XRP + EVM L2 endpoints end-to-end"
    - "Free-tier gate enforcement — verify 4th cross-border send returns 402 for non-Pro users"
    - "Legacy user backfill — simulate an old user (delete their XLM+XRP balance rows) and confirm /wallet/assets re-inserts them"
    - "USDC on L2 send happy path — Polygon Amoy funded via Circle faucet (or MOCKED if faucet is slow/unavailable)"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: |
      Please run a full backend sweep targeting the endpoints added in the
      last three iterations (Remit / XRP / EVM L2). Details in
      backend_new_endpoints_this_iteration above.

      Environment: local backend at http://localhost:8001 (Render production
      hasn't received the L2 commit yet — user still needs to click Push).

      Test creds (from /app/memory/test_credentials.md):
        smoketest@vaulted.app / test1234  (this account IS Pro — good for
        testing paywall bypass and 50% service-fee discount)

      To test the free-tier paywall you'll need to register a FRESH non-Pro
      account and do 4 remit sends in a row (the 4th must return 402).

      XRP + XLM real broadcasts are cheap on testnets — feel free to hit the
      faucets. USDC on L2 broadcasts likely need MOCKING (Circle's faucet
      requires manual clicks); it's fine to test /wallet/evm/usdc/send with
      "insufficient balance" 400s and validate the address / chain
      validation + error paths instead.


  - agent: "main"
    message: |
      BUG REPORT (iteration 17 — Stripe Identity error UX):
      User reported the raw Stripe error "Stripe Identity error: Request
      req_XXX: Your account is not set up to use Identity. Please have an
      account admin visit https://dashboard.stripe.com/identity/application
      to get started." was leaking through as scary red text on /kyc when
      they tapped "Verify identity" (screenshot in job context).

      Root cause: stripe.identity.VerificationSession.create() throws
      stripe.error.StripeError when the Identity product isn't activated on
      the Stripe account. Old handler served the raw error verbatim.

      Fix committed as e1d32f0:
       A. BACKEND /api/kyc/session — detects "not set up to use Identity"
          or "identity/application" substring in the Stripe error and
          raises HTTPException(status_code=503, detail={
              "error": "stripe_identity_not_activated",
              "message": "Identity verification is temporarily unavailable
                          — we're finalising our Stripe Identity onboarding.
                          Please try again shortly, or contact
                          support@phoenix-atlas.com for immediate help.",
          }) instead of leaking the raw message. Non-matching Stripe errors
          still 502 as before.
       B. FRONTEND /kyc — on catch, checks e.status===503 OR message
          includes 'stripe_identity_not_activated' / 'not set up to use
          Identity' → sets errKind='config' → renders the gold construction
          card (testID='kyc-config-error') instead of the raw red 's.err'
          Text. Generic errors still show as red text.

      Local backend restarted with the fix; production Render still has
      OLD code (commit not yet pushed).

      Please verify against LOCAL http://localhost:8001:
        1. Monkey-patch stripe.identity.VerificationSession.create to raise
           stripe.error.StripeError("Request req_TEST: Your account is not
           set up to use Identity. Please have an account admin visit
           https://dashboard.stripe.com/identity/application to get
           started.") → POST /api/kyc/session (auth: smoketest@vaulted.app /
           test1234) → assert status=503, detail.error=='stripe_identity_
           not_activated', detail.message contains 'temporarily
           unavailable' AND 'support@phoenix-atlas.com'.
        2. Monkey-patch same method to raise stripe.error.StripeError("Rate
           limit exceeded") → assert status=502 (generic bubble-up
           unchanged), detail contains "Stripe Identity error".
        3. FRONTEND regression (optional if time-boxed): with the local
           backend still monkey-patched from test 1, load /kyc, tap
           testID='kyc-start', wait ≤3s, assert data-testid='kyc-config-
           error' is visible AND that the raw phrase 'not set up to use
           Identity' is NOT anywhere in the rendered DOM.

      ALL OTHER KYC / remit endpoints already passed in iteration 16 —
      please DO NOT re-run them. Focus only on this error-handling fix.
      Report to /app/test_reports/iteration_17.json.


  - agent: "main"
    message: |
      ITERATION 18 — KYC "requires_input" UX overhaul + backend force_new
      escape hatch.

      Context: Production user reported "tried verification twice and returned
      with the same message" — screenshot showed our own /kyc-return screen
      rendering a generic "Stripe couldn't verify your document. Please try
      again with a clearer photo." message even after Stripe sent a specific
      last_error (e.g. document_expired, selfie_face_mismatch). Users were
      stuck retrying the same failed session with no context and no way to
      start over.

      Root causes:
       1. Backend stored kyc.identity_last_error on the requires_input
          webhook, and /api/kyc/status returned it, but kyc-return.tsx
          ignored the code entirely and always showed generic copy.
       2. Backend /api/kyc/session ALWAYS reused an existing requires_input
          session — no way to force a brand-new session with a fresh
          idempotency key when the old one was in a bad state.

      Fix committed:
       A. NEW /app/frontend/src/lib/kycErrors.ts — maps Stripe Identity
          last_error.code (~20 codes: document_expired,
          document_unverified_other, selfie_face_mismatch, id_number_mismatch,
          etc.) → {title, reason, tip, fatal?}. Fatal codes (age, country,
          document_type_not_supported, consent_declined) skip the retry CTA
          and only show start-over/support.
       B. BACKEND /api/kyc/session — now accepts optional body
          {"force_new": true}. When true: cancels the existing session on
          Stripe (best-effort), bumps session_attempt, mints a fresh session
          with new idempotency key, AND clears stale kyc.identity_last_error
          in the DB. Backward-compatible: empty body / no body still reuses.
       C. FRONTEND /kyc-return — reads identity_last_error, renders mapped
          {title, reason, tip} + a 5-item photo-capture checklist +
          three CTAs: "Try again" (reuses session), "Start over with a new
          session" (force_new), and "I'll try later" (back to wallet). Fatal
          errors hide "Try again". Adds inline support@phoenix-atlas.com
          escape hatch.
       D. FRONTEND /kyc — pre-verification screen now uses the same error
          mapping for the last_error banner and adds a secondary "Start over
          with a new session" button when in requires_input state.

      Backend tests (all passing, local http://localhost:8001):
        /app/backend/tests/test_iteration18_kyc_force_new.py — 4 tests
          - TestForceNewReuses (default reuses existing session)
          - TestForceNewCreatesFresh (force_new cancels + creates + clears
            stale error + increments idempotency counter)
          - TestForceNewToleratesCancelFailure (cancel error is swallowed)
          - TestBackwardCompat (empty body still works)
        + iteration 17 regressions all still pass.

      Please verify (backend + frontend against LOCAL):
        1. Backend: re-run iteration 17 + 18 tests to confirm nothing
           regressed. Report only failures.
        2. Frontend regression: on /kyc-return, simulate a requires_input
           status with identity_last_error.code='document_unverified_other'
           in the mocked /kyc/status response, verify:
             - testID='kyc-return-retry' visible
             - testID='kyc-return-start-over' visible
             - The specific "What to do next" tip block is rendered
             - The 5 photo tips are all rendered
           Then simulate a FATAL error (code='under_supported_age') and verify:
             - testID='kyc-return-retry' is NOT rendered
             - testID='kyc-return-start-over' still rendered
        3. On /kyc: with a mocked status returning
           identity_verification_status='requires_input' + last_error, verify
           the error card shows the MAPPED title (not the raw reason
           string), and the "Start over with a new session" secondary
           button (testID='kyc-start-over') is visible.

      Auth credentials: smoketest@vaulted.app / test1234
      Report to /app/test_reports/iteration_18.json.


  - agent: "main"
    message: |
      ITERATION 19 — OpenSanctions wiring (Path C+): safe fallback +
      audit-friendly degraded state + admin diagnostic endpoints +
      COMPLIANCE_STRICT_MODE gate + docs.

      Root causes addressed:
       1. compliance.py silently failed-open (matched=False) on 401/timeout,
          giving zero audit evidence that screening was attempted.
       2. No admin visibility — you couldn't tell from the app whether
          OpenSanctions is live without reading logs.
       3. No path to enforce fail-closed once FCA registration lands.
       4. Docs missing.

      Ships:
       A. compliance.py — screen_sanctions() returns {degraded, degraded_reason}
          uniformly. Short-circuits to degraded="no_api_key" when
          OPENSANCTIONS_API_KEY is empty (avoids 401). Emits structured audit
          log (event=sanctions_screen, name_hash, latency_ms, matched, degraded).
          Adds opensanctions_health() canary + opensanctions_config_status().
          Reads COMPLIANCE_STRICT_MODE env flag (default false).
       B. server.py:
          - New require_admin dependency + ADMIN_EMAILS env var (CSV).
          - GET /api/admin/compliance/health — canary ping + config snapshot.
          - POST /api/admin/compliance/screen — manual name/dob/country screen.
          - /kyc/status now surfaces sanctions_check.{degraded, degraded_reason}.
          - _apply_identity_verified now stores degraded/degraded_reason on user.
          - /api/remit/send strict-mode gate: 503 if degraded && STRICT_MODE.
       C. /app/docs/COMPLIANCE.md — architecture, env vars, three key
          acquisition paths (paid hosted, self-hosted Yente, corridor-only),
          admin endpoint reference, structured-log schema, strict-mode rollout.

      Backend tests (all 13 passing, plus 7 iter17/18 regression → 20 total):
        /app/backend/tests/test_iteration19_compliance_health.py

      Please verify:
        1. Re-run iter17 + iter18 + iter19 test suites and confirm no
           regression (20/20 should pass).
        2. Optional: smoke that /api/remit/quote and /api/remit/send are
           unchanged for users with no kyc.sanctions data (default state —
           strict mode is off).
        3. Do NOT re-test wallet/multichain/subscription — untouched.

      Credentials: smoketest@vaulted.app / test1234.
      Report to /app/test_reports/iteration_19.json.


  - agent: "main"
    message: |
      ITERATION 20 — FCA-compliant audit-log endpoint. Backend-only feature.

      Ships an immutable event trail for every KYC decision, sanctions screen,
      and remit attempt, powering the FCA money-transmission authorisation
      application.

      NEW MODULE /app/backend/audit.py:
       - EventType constants (12 canonical events)
       - write_event() fire-and-forget, never raises
       - query_events() cursor pagination + filters
       - summarize_user() per-user compliance file
       - PII pseudonymisation: user_email_hash = sha256[:12]

      HOOKS: all KYC state transitions, all remit send outcomes (success +
      5 block types), corridor blocks, admin manual screens.

      NEW ADMIN ENDPOINTS:
       - GET /api/admin/audit-log (paginated + filtered)
       - GET /api/admin/audit-log/event-types
       - GET /api/admin/audit-log/user/{user_id}

      Backend tests (14 new, 34 total across iter17-20): all passing.
      Live smoke verified: blocked-corridor attempt writes 2 events;
      /admin/audit-log locked (403) without ADMIN_EMAILS set.

      Please verify:
        1. Re-run iter17+18+19+20 (34 tests). No regression.
        2. Confirm /api/wallet/assets and /api/auth/login still 200 (no
           accidental breakage of unrelated flows).

      Credentials: smoketest@vaulted.app / test1234.
      Report to /app/test_reports/iteration_20.json.


  - agent: "main"
    message: |
      ITERATION 21 — Referral loop: invite links + £5 GBP credit ledger.

      Backend NEW module /app/backend/referrals.py:
       - generate_code() 8-char [A-Z0-9] secure random
       - register_referral_at_signup() creates pending referrals row
       - credit_referral_on_kyc() grants both sides £5 (idempotent). Skips flagged users.
       - spend_credit_for_fee() applies GBP credit to remit service fee
       - referral_summary() dashboard aggregate (masked emails)

      server.py hooks:
       - Register accepts referred_by_code; auto-assigns referral_code
       - _apply_identity_verified triggers credit_referral_on_kyc (post sanctions)
       - /remit/send: USD fee → GBP, applies credit, stores credit_applied_gbp on tx
       - public_user + /auth/me expose referral_code

      New endpoints: /referrals/me, /referrals/validate/{code} (public),
      /credit/balance, /credit/ledger.

      Audit: 4 new EventType constants (REFERRAL_SIGNUP, REFERRAL_CREDITED,
      CREDIT_GRANTED, CREDIT_SPENT).

      Frontend:
       - src/lib/refCode.ts (capture ?ref=CODE from URL, persist, apply at signup)
       - _layout.tsx calls captureRefCodeFromUrl() at mount
       - (auth)/register.tsx renders "Invited by …" banner, passes referred_by_code
       - app/referral.tsx: hero, balance, share link (native Share API), 3-step
         explainer, friends list with masked emails, pull-to-refresh
       - Settings row: "Invite friends · Earn £5 each"

      Backend tests: 19 new + 34 regression → 53 passing.

      Please verify:
        1. Re-run iter17-21 (53 tests). No regression.
        2. Confirm /auth/register still works without referred_by_code
           (backward compat).
        3. Confirm /referrals/me returns share_link + code for smoke user.
        4. Optional frontend: navigate to
           http://localhost:3000/(auth)/register?ref=<smoke_code> and confirm
           testID='reg-invite-banner' renders with masked referrer name.

      Credentials: smoketest@vaulted.app / test1234.
      Report to /app/test_reports/iteration_21.json.
