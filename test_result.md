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
  Iteration goal: Multichain expansion Phase A — add XRP (Ripple), and fix stale-user
  XLM invisibility caused by DB backfill gap.

backend:
  - task: "XLM backfill for existing (pre-XLM) users"
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
