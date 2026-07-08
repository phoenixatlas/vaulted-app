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
  version: "1.1"
  test_sequence: 15
  run_ui: false

test_plan:
  current_focus:
    - "XRP send/receive end-to-end on production Render (post-push)"
    - "Verify XLM finally shows up for the pre-XLM user (after backfill deploy)"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: |
      Ready to push these backend + frontend changes to GitHub → Render + Vercel
      will auto-deploy. Once live:
        1. The user's original account should immediately start showing XLM
           (backfill triggers on next /wallet/assets fetch).
        2. XRP will appear as the 6th asset — sends work on testnet;
           funded via the XRPL faucet link inside Send screen.
      Both flows verified locally; no need to burn an extra testing_agent call
      before user validates in production.
