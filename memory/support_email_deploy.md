# Support Email — Vaulted Deploy Eligibility

> Send to: **support@emergent.sh**
> Subject: Deploy clarification — blockchain libraries used as a pure HTTP client (job-attached)

---

Hi Emergent team,

I'd like to clarify the deployment eligibility of my app before either pursuing an exception or rehoming the project elsewhere.

**My app:** Vaulted — an Expo + FastAPI + MongoDB self-custody crypto wallet. Built end-to-end on Emergent over the last several iterations (auth, multi-sig email approvals, in-chat ETH sends, biometric lock, CSV/tax export, Stripe payments, Resend, Daily.co video, etc.).

**Job ID:** *(paste from the ℹ️ button, top-right of the workspace)*

**The blocker your `deployment_agent` returned:**
> severity: BLOCKER, category: BLOCKCHAIN
> file: backend/requirements.txt
> "Application uses Ethereum blockchain libraries (eth-account, eth-keys, etc.) ... Blockchain/web3 applications are not deployable on Emergent infrastructure."

**My request — please confirm whether the policy is strict given the following:**
The app does **not** run a blockchain node or any chain infrastructure. The `eth-account` family is used **purely as a local cryptographic library** for two things:

1. **Local key generation** at sign-up (`Account.create()`) — equivalent to generating an SSH key on your laptop.
2. **Local transaction signing** (`Account.sign_transaction(...)`) — produces a signed RLP-encoded byte string.

All actual chain traffic is plain HTTPS to a **public, third-party Sepolia RPC**: `https://ethereum-sepolia-rpc.publicnode.com`. From an infra standpoint, my backend is just a Python HTTP client — no daemon, no peer-to-peer networking, no validator, no consensus.

**Concrete questions:**
1. Is the "no blockchain apps" rule absolute, or is it intended to exclude *infrastructure-running* apps (full nodes, indexers, mining/validation workloads)?
2. If absolute — can you whitelist this project, given the constrained usage above?
3. If neither is possible — can you confirm so I can plan an alternative deploy target (e.g. Vercel + Railway) without further delay?

Thanks for the help. Happy to share a code walkthrough or the relevant `eth-account` import sites if useful.

— *(your name)*
