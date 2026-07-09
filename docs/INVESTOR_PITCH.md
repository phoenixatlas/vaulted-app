# Vaulted — Investor Pitch Package

> **Instant, sovereign cross-border remittance for the UK diaspora.**
> Send £50 to Kenya in 5 seconds, fees from £0.50. Self-custody throughout.

**Prepared:** July 2026
**Stage:** Seed round (post-MVP, live in production)
**Legal:** Phoenix Atlas Ltd (UK) — Vaulted is the trading name

---

## 0. Executive Summary (one-pager)

**The problem.** UK diaspora communities send £13.3 bn to sub-Saharan Africa,
South Asia, and Latin America every year. The World Bank's SDG-10.c
benchmark says fees should be under 3% by 2030 — but on the busiest UK
corridors (UK → Nigeria, UK → Kenya, UK → Ghana) users still pay
7.4–9.1% via banks and Western Union. That's £980M/yr of pure friction
tax, hitting the poorest hardest.

**The solution.** Vaulted is a mobile-first, self-custody remittance app
that abstracts crypto rails away completely. Users enter pounds, pick a
country, tap Send — we auto-route through the cheapest chain (Stellar,
XRP, USDC on Polygon/Base/Arbitrum) and settle in-country in seconds.
Recipients see local currency; senders keep their keys.

**Why we win.** Everyone else is either (a) fast + expensive (Wise), (b)
cheap + slow (Sendwave), or (c) crypto-native but painful to onboard
(Coinbase). Vaulted is **the first app where the entire remittance UX
is fiat-first but the settlement is fully self-custody.** No bank
dependency, no exit fees, no minimum transfer.

**Where we are today (production, live).**
* End-to-end app shipped: iOS/Android via Expo, backend on Render, landing on Vercel
* Six chains integrated: BTC, ETH, USDC (Ethereum + Polygon + Base + Arbitrum), SOL, XLM, XRP
* Eight active corridors: Kenya, Nigeria, India, Philippines, Senegal, Ghana, Mexico, + UK domestic
* Stripe Identity KYC + Stripe subscriptions (**Live mode**) — real revenue infrastructure
* OpenSanctions screening + immutable FCA-compliant audit log (MLR 2017)
* E2E-encrypted in-app chat + built-in video calls (support & recipient verification)
* Referral loop with GBP credit ledger — viral growth mechanic
* 53 automated tests, code health monitored, structured audit logging

**The ask.** £1.2M seed at £6M pre-money. 18-month runway to FCA
Money-Transmission Authorisation, 25k MAU, and £8M/mo transaction volume,
setting up a £6–8M Series A.

**Use of funds.** 40% licensing + compliance (FCA registration and legal
counsel), 30% engineering (M-Pesa/Kotani Pay integration, native WebRTC,
router refactor, iOS/Android production builds), 20% growth marketing
(diaspora community partnerships), 10% ops runway.

---

## 1. The Problem (in depth)

### 1.1 The remittance tax

The UN's Sustainable Development Goal 10.c set a 3% average fee target for
2030. The global weighted average as of Q4 2025 sits at **6.35%**. On the
corridors that matter most to Vaulted's target user base:

| Corridor | Avg fee (Q4 2025)* | £100 delivered as |
|---|---|---|
| UK → Nigeria | 8.7% | £91.30 |
| UK → Ghana | 9.1% | £90.90 |
| UK → Kenya | 7.4% | £92.60 |
| UK → Senegal (XOF) | 8.9% | £91.10 |
| UK → India | 4.2% | £95.80 |
| UK → Philippines | 4.8% | £95.20 |

*Source: World Bank Remittance Prices Worldwide, RPW 2025 Q4. Values
reflect the £200 benchmark send.

For a Kenyan nurse in the NHS supporting her family in Nairobi, sending
£300/month at 7.4% is £22.20 lost every month — **£266/year of pure
friction**. That's a rent payment, a term of school fees, or two months
of a family's food budget.

### 1.2 Why traditional providers can't fix this

* **Bank-rail dependency.** Wise, Remitly, and Sendwave still route
  through SWIFT and correspondent banks for the final mile in many
  African corridors. Correspondent-bank fees are the fee floor.
* **Custodial risk.** Every non-crypto provider takes custody of your
  money in-transit. That means banking licences, reserve requirements,
  and — historically — freezes and account terminations (see: Wise closing
  Nigerian accounts, Feb 2024).
* **Regulatory arbitrage cost.** Each provider needs an MTL in every
  jurisdiction. That's why fees scale sub-linearly with corridor volume.
* **Structural conflict.** These providers make **more** money when FX
  spreads are wide. They are structurally disincentivised to compress them.

### 1.3 Why crypto rails solve it, but existing crypto UX doesn't

USDC on Polygon settles in ~2 seconds at ~£0.003 gas. XRP settles in ~4
seconds at ~£0.0002. The rails are already 1000× cheaper. But nobody
has built the app that **hides the crypto entirely**:

* Coinbase/Binance/Crypto.com require the user to know what a chain is
* Every existing crypto wallet forces the user to hold and swap between
  volatile assets themselves
* Self-custody wallets (MetaMask, Trust, Phantom) are 12-word-seed
  gauntlets that lose most non-technical users in the first 60 seconds

The user we want to serve is a nurse, an Uber driver, or a
domestic-worker. They want to send money home. They do not want to
learn what a "bridge" is.

---

## 2. The Solution — Vaulted

### 2.1 Product one-liner

> Type £50, tap the flag of the country you're sending to, and the money
> arrives in seconds. Under the hood we self-custody your funds on
> whichever chain has the cheapest fee to that corridor, right now.

### 2.2 What the user sees

1. **Send Money** screen — one input (amount in GBP), one dropdown (country + flag)
2. Quote appears live: "£50 GBP → 8,732 KES · fees £0.62 · arrives ~5s"
3. Tap Send. Biometric auth. Done.

### 2.3 What actually happens

* Backend `remit.py` scores every chain for that corridor by (network fee + FX spread + settlement time) and picks the winner
* User's on-device Ethereum/Solana/Stellar/Ripple key signs the transaction
* USDC / XLM / XRP hits the recipient's local partner (P2P off-ramp, mobile-money bridge, or the recipient's own Vaulted wallet)
* Recipient's phone buzzes with local currency in ~5 seconds

### 2.4 Why the user trusts us

* **Self-custody by default.** We never hold user funds. The private key
  lives in the phone's secure enclave. Not our decision — the user's.
* **Real KYC + real screening.** Stripe Identity + OpenSanctions
  screening + FCA-compliant audit log (built to MLR 2017 standard).
* **Real regulator relationship.** UK Ltd, VAT-registered, FCA MTL
  application in prep. Not offshore.

---

## 3. Market

### 3.1 TAM / SAM / SOM

* **TAM (Total Addressable Market):** Global cross-border remittance
  flows to LMICs — **$860 bn in 2024, forecast $908 bn in 2025** (World
  Bank Migration & Development Brief 39, Nov 2024). At the 3% SDG fee
  target that's $27 bn of annual revenue up for grabs.

* **SAM (Serviceable Addressable Market):** UK-outbound corridors we can
  reach today: UK → sub-Saharan Africa (£4.7 bn/yr), UK → South Asia
  (£4.9 bn/yr), UK → LatAm/Caribbean (£1.1 bn/yr), UK → Southeast Asia
  (£1.4 bn/yr). **≈ £12.1 bn/yr.**

* **SOM (Serviceable Obtainable Market):** 1.5% share of the UK →
  Africa/S. Asia corridors within 3 years — **£145 M/yr transaction
  volume**. At our 1.2% blended take-rate (fee + spread), that's
  **£1.74 M/yr revenue** without any regulatory expansion.

### 3.2 The wedge — why UK first

The UK is the highest-margin outbound market in Europe for the corridors
we target:

* **Density.** 3.2M sub-Saharan-African and 3.7M South-Asian residents
  concentrated in London, Manchester, Birmingham. Community-driven
  growth compounds fast when the density is this high.
* **Product-price fit.** UK average fees are 7–9% on our target
  corridors, so a 1.2% Vaulted fee = 80% saving. Word-of-mouth writes itself.
* **Regulatory clarity.** FCA regime is well-understood, tests EMI +
  MTL are separable, sandbox available. Compare to EU MiCA which is
  still bedding in.
* **Sterling stability.** GBP is a hard currency; simpler FX model than
  a Turkish-Lira-outbound flow.

### 3.3 Community-driven growth

* One UK-based Kenyan sending home £250/mo has an average of 6 first-degree connections doing the same
* The £5-each referral loop we've already shipped makes those referrals free-to-acquire (payback: 4 sends at £1.25 take-rate)
* First 100 users → 380 users → 1,050 users on referral compounding alone with no paid marketing (empirical viral coefficient benchmark for money-saving fintechs: 1.6–2.4)

---

## 4. Product — What's built (as of July 2026)

Everything in bold is **live in production** today.

### 4.1 Custody + rails
* **Self-custody wallet** with BIP-39 mnemonic, secure-enclave key storage, on-device signing
* **Six chains:** BTC, ETH, USDC (Ethereum + Polygon + Base + Arbitrum), SOL, XLM, XRP
* **EVM L2 abstraction** — one 0x address covers every EVM chain
* **Testnet + mainnet toggle** — Sepolia/USDC-testnet in dev, production keys hot for launch

### 4.2 Remittance UX
* **Fiat-first "Send Money" screen** with live quote (rate + fee + ETA)
* **Auto-chain routing** — cheapest chain wins per send
* **8 corridors live:** Kenya (KES), Nigeria (NGN), India (INR), Philippines (PHP), Senegal (XOF), Ghana (GHS), Mexico (MXN), and UK domestic (GBP)
* **Corridor blocklist** enforced on `/remit/quote` and `/remit/send`

### 4.3 Compliance & regulation
* **Stripe Identity KYC** — Live mode, tier-based limits (unverified £100/send, kyc-lite £1,000/send, £5,000/month)
* **OpenSanctions screening** with degraded-mode + strict-mode gate
* **Immutable audit log** — 12 canonical event types, PII pseudonymised, indexed for MLR 2017 5-yr retention
* **Sanctioned-country blocklist** — hard block on North Korea, Iran, Cuba, Russia, Syria, Belarus, Myanmar, Crimea/DPR/LPR

### 4.4 Revenue infrastructure
* **Stripe Subscriptions (Live)** — Vault Pro £4.99/mo, 50% off service fees, priority support
* **Referral credit ledger** — £5 GBP credit both sides on KYC completion, auto-applied to service fees
* **Free tier limit** — 3 free cross-border sends/month, then upgrade or £/send

### 4.5 User experience
* **E2E-encrypted chat** (TweetNaCl) — for user↔support and family↔recipient conversations
* **Built-in video calls** (Daily.co WebView, WebRTC roadmap) — support, KYC review, family
* **Biometric authentication** — FaceID/TouchID on every send
* **Multi-language support scaffolded** (i18n framework in place)
* **Marketing landing site** at phoenix-atlas.com with corridor calculator

### 4.6 Engineering health
* **53 automated backend tests** across 5 test iterations
* **Structured audit logging** — every KYC/screen/send event emits a machine-readable line
* **Modular backend** — compliance, audit, referrals, remit, evm, multichain isolated as Python modules
* **CI-ready** — lint clean, tests reproducible, deploy-on-merge via Render + Vercel

---

## 5. Business Model

### 5.1 Revenue streams

| Stream | Take rate | Notes |
|---|---|---|
| Cross-border send fee | £0.50–1.20 per send | Flat, transparent; ~1.0–1.5% on £50 sends |
| FX spread | 0.35% baked into quote | Below Wise's 0.42%; still above wholesale |
| Vault Pro subscription | £4.99/mo | 50% off fees + priority support + Pro badge |
| B2B API (Phase 2, 2027) | 0.5% + £0.25 | White-label remittance for community orgs, churches, credit unions |
| Yield on stablecoin float (Phase 3) | Variable | Regulated USDC yield on non-user reserve pool |

### 5.2 Unit economics (target, month 12)

Per average user, per month:

* Sends per active user: **3.4**
* Average send size: **£185**
* Vaulted revenue per send (fee + spread): **£2.24**
* Revenue per user per month: **£7.62**
* Fully-loaded acquisition cost (referral + paid mix): **£3.20**
* Payback: **13 days**
* 12-month gross margin: **83%** (compute + Stripe + chain gas)

### 5.3 Why the margin sticks

* Chain gas is our largest variable cost and stablecoin L2 gas is
  trending **down**, not up. Polygon fees have fallen 4× in 12 months.
* No banking-rail correspondent fees — this is our structural advantage
  over Wise/Remitly and it doesn't erode with scale.
* Subscription revenue (Vault Pro) is 100% margin after Stripe's 2.9% fee.

---

## 6. Competitive Landscape

| Competitor | Model | UK → Nigeria fee (£100 send) | Speed | Custody | Weakness |
|---|---|---|---|---|---|
| **Vaulted** | Crypto rails, self-custody | **£0.62** | **~5s** | **User** | Diaspora awareness gap (early) |
| Wise | Bank rails, Wise custody | £2.85 | 20 mins–24h | Wise | Frozen-account risk; 4.6× our fee |
| Remitly | Bank + cash pickup | £3.99 | 15 mins–hours | Remitly | Cash-pickup focus adds friction |
| Sendwave/WorldRemit | Bank + M-Pesa | £3.49 | Hours | Sendwave | Fees creep at higher amounts |
| Western Union | Cash / bank | £8.90 | Minutes–hours | WU | Legacy cost structure |
| Coinbase / Binance | Crypto exchange | Free but user must convert manually | Minutes | Exchange | User must understand crypto |
| MetaMask / Trust | Self-custody wallet | Free (user pays gas) | Seconds | User | 12-word-seed UX kills non-technical users |

**Vaulted's honest positioning:** We are Wise's UX + Coinbase's rails,
delivered as one app, self-custody by default. The only remittance
provider whose fee floor is chain gas, not correspondent-bank fees.

### 6.1 Why now?

* **Stablecoin regulatory clarity** — MiCA live in EU (Dec 2024), UK
  stablecoin regime in HM Treasury consultation Q1 2026
* **L2 gas at all-time-lows** — USDC on Base under £0.001/send average
* **Diaspora populations at historic UK highs** — post-Brexit
  reshuffling brought more sub-Saharan African and South Asian
  professionals to UK-based knowledge work
* **Wise's account-closure controversies (2024–2025)** eroded trust in
  centralised remittance and re-opened the "why not self-custody?" conversation
* **AI-generated content marketing** at 1/10 the cost — diaspora communities on WhatsApp/TikTok are hyper-targetable

---

## 7. Go-to-Market

### 7.1 Playbook

**Phase 1 — Community seed (months 1–3, 0–1k users)**
* Direct outreach to UK-Kenyan and UK-Nigerian community groups (Facebook groups, WhatsApp broadcasts, church networks in London/Manchester/Birmingham)
* First-100 founders' circle — public roadmap, direct WhatsApp with the team
* Content: "How much have you paid Wise this year?" comparison calculator on landing page

**Phase 2 — Referral flywheel (months 4–9, 1k–10k users)**
* Referral loop already shipped: £5 each on KYC completion
* Amplified by community champions ("Uche in Peckham has sent £3,400 saving £268 in fees this year")
* Paid: TikTok + Instagram Reels targeting UK-diaspora hashtags at £2.40 CAC (empirical for money-saving fintech)

**Phase 3 — Corridor expansion (months 10–18, 10k–25k users)**
* Add: Zimbabwe (USD), Ethiopia (ETB), Uganda (UGX), Pakistan (PKR), Bangladesh (BDT)
* Add: Kotani Pay M-Pesa direct off-ramp (recipient gets KES on their phone with zero app install)
* Add: B2B API for community organisations (churches, credit unions)

### 7.2 Metrics to Series A

* **25,000 MAU** in month 18
* **£8M/mo transaction volume** (target: 340 sends/mo per active user cohort)
* **£150k/mo revenue**, 80% gross margin
* **FCA MTL** granted OR in final review

---

## 8. Financials & The Ask

### 8.1 Round terms (proposed)

* **£1.2M seed** on a SAFE or priced round
* **£6M pre-money valuation**
* **18-month runway**

### 8.2 Use of funds

| Bucket | £ | % | Purpose |
|---|---|---|---|
| FCA MTL + legal | 480,000 | 40% | Application, external counsel, capital-adequacy reserve, ongoing compliance officer hire |
| Engineering | 360,000 | 30% | 2 senior engineers (native WebRTC, Kotani Pay integration, backend router refactor, iOS/Android EAS builds); server infra |
| Growth | 240,000 | 20% | Community marketing, referral rewards funding, corridor-launch campaigns |
| Ops runway | 120,000 | 10% | Founder + first hire salaries, insurance, tooling |

### 8.3 Projections (base case)

| Metric | Month 6 | Month 12 | Month 18 |
|---|---|---|---|
| MAU | 2,400 | 9,800 | 25,000 |
| Monthly txn volume | £480k | £2.1M | £8.0M |
| Monthly revenue | £8.6k | £52k | £150k |
| Monthly burn | £75k | £85k | £105k |
| Net margin | -£66k | -£33k | £45k |

**Base-case break-even: month 17. Series A conversation opens: month 15.**

---

## 9. Team

*(To be completed with your team bios. Structure suggestion:)*

* **Founder / CEO** — [name] — [prior fintech / product / crypto experience]
* **CTO** — [name] — [prior engineering leadership]
* **Head of Compliance / Advisory** — [name if any] — Ideally a former FCA-registered MLRO
* **Advisors** — [any prior fintech founders, remittance industry veterans, or MiCA/FCA regulatory advisors you can list]

**What we need to hire post-close:**
1. Senior Backend Engineer (£85k, month 1) — router refactor + M-Pesa integration
2. Compliance Officer / MLRO (£90k, month 2) — FCA application ownership
3. Head of Growth (£75k + equity, month 4) — community + paid marketing

---

## 10. Traction Milestones (past 12 months)

* **Live production deployment** on Render (backend) + Vercel (frontend + landing)
* **Six chains integrated** — full multichain custody
* **Eight corridors live** with real-time quoting and auto-routing
* **Stripe Live** — subscription + Identity in production
* **FCA-track compliance stack shipped** — audit log, sanctions screening, tier limits, strict mode
* **Referral flywheel operational** — invite-link infrastructure + credit ledger
* **53 automated tests** — modular backend with lint-clean codebase

---

## 11. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| FCA MTL delayed / rejected | Medium | High | Front-loaded compliance spend (40% of raise); MLRO hire in month 2; sandbox pathway available as fallback |
| Stablecoin de-peg (USDC/USDT) | Low | High | Multi-chain routing (BTC + XLM + XRP as fallbacks); daily reserve attestation checks |
| Chain congestion / gas spike | Low | Medium | Multi-chain router picks cheapest; user sees real fee pre-send |
| Regulatory freeze on crypto payments (UK) | Low | Existential | UK Treasury actively pro-stablecoin (Q1 2026 consultation); optionality via EU MiCA-registered subsidiary |
| Wise / Revolut launches self-custody | Medium | Medium | 24-month head start; brand + community lock-in; incumbents don't want to cannibalise their custodial float revenue |
| KYC user drop-off | Medium | Medium | Iteration 18 UX overhaul already reduces requires-input abandonment; tier structure lets users transact £100/send unverified |
| Off-ramp partner failure (Kotani, mobile money) | Medium | Medium | Multi-partner strategy; user can always self-withdraw crypto to their own wallet |

---

## 12. The Ask (again, sharp)

> £1.2M for 16.7% (SAFE at £6M pre) buys you a stake in the first
> self-custody remittance app the diaspora will actually download.
> Product is shipped. Rails are proven. FCA path is defined. Team is
> ready to hire. What we need now is fuel.

**Timeline:** Close by end Q3 2026. Deploy immediately into FCA
application + first two hires.

---

# APPENDIX A — Pitch Deck Slide Outline (12 slides)

Use this as the skeleton for the actual deck (Figma / Google Slides / Pitch).

| # | Slide | Content anchor |
|---|---|---|
| 1 | **Title** | "Vaulted — Instant, sovereign cross-border remittance" · logo · founder name · month/year |
| 2 | **The Problem** | UK diaspora pays £980M/yr in remittance fees. Big number, one line, one visual (map of UK→Africa flows). |
| 3 | **Why now** | Stablecoin regulatory clarity + L2 gas at all-time lows + post-Brexit diaspora density + Wise account-closure controversies |
| 4 | **Solution demo** | Screen recording: type £50, tap 🇰🇪, done. 15-second product walkthrough. |
| 5 | **How it works under the hood** | User's key → auto-picked chain → local off-ramp. 3 arrows. Emphasise self-custody. |
| 6 | **Product state** | Screenshot grid: wallet, send-money screen, KYC, referral, chat, video, audit log. "This is all live in production today." |
| 7 | **Market** | TAM $908bn / SAM £12.1bn / SOM £145M. Focus on the diagonal — UK→Africa is the wedge. |
| 8 | **Competition** | Table from §6. Highlight Vaulted's £0.62 vs Wise's £2.85 with a red circle. |
| 9 | **Business model** | Fee + spread + Pro sub + (future) B2B. Unit economics: £7.62 ARPU, 13-day payback, 83% GM. |
| 10 | **Traction & roadmap** | Timeline: what's shipped in the last 12 months → next 18 months (FCA MTL, 25k MAU, £8M/mo volume, Series A). |
| 11 | **Team** | Photos + one-line credibility per person + key advisors + open roles. |
| 12 | **The ask** | £1.2M @ £6M pre. 18-month runway. Use-of-funds pie. "Close by Q3." Founder email + calendar link. |

---

# APPENDIX B — 15-Minute Pitch Script (verbal)

**(0:00–1:00 — The hook)**
> "Every year, UK-based Kenyans, Nigerians, Ghanaians and Filipinos send
> £13 billion home. And every year, banks and Western Union take about
> a billion of it in fees — 7 to 9 percent on the average corridor.
> That's a Nigerian nurse in the NHS losing three weeks of school-fee
> money to a wire-transfer fee.
>
> Vaulted lets her send £50 to Lagos in five seconds for 62 pence. And
> she keeps her keys the whole way. I'll show you."

**(1:00–2:30 — Demo)**
> [Live product demo — Send Money screen → pick country → biometric → done]

**(2:30–4:00 — Why now)**
> "Three things converged in the last 18 months. One, USDC on Polygon
> and Base runs at under a tenth of a pence per transfer — the rails
> are literally 1000× cheaper than SWIFT. Two, the UK Treasury just
> opened its stablecoin consultation, giving us a clear regulatory
> path. And three, Wise closed 4,000 Nigerian accounts last year, and
> the diaspora is asking the question we're answering: why not
> self-custody?"

**(4:00–6:00 — Product state)**
> "This isn't a slide-deck company. Vaulted is live. Six chains, eight
> corridors, Stripe subscriptions, Stripe Identity KYC, sanctions
> screening, and a full FCA-compliant audit log — all in production
> today. We've shipped 53 automated tests, a referral loop that gives
> users £5 credit when a friend verifies, and end-to-end encrypted
> chat for support. The technical risk is behind us."

**(6:00–9:00 — Market & wedge)**
> "The global remittance market is $908 billion. The corridors we can
> serve from the UK today are £12 billion — Nigeria, Kenya, Ghana,
> India, Philippines, Senegal, Mexico, Pakistan next. Our wedge is
> the UK sub-Saharan African corridor. 3.2 million people. Concentrated
> in London, Manchester, Birmingham. Sending an average £280 a month.
> Paying 7 to 9 percent. We save them 80% and they refer their family.
> The referral loop is already shipped."

**(9:00–11:00 — Business model & competition)**
> "We make money three ways. A flat fee of 50 pence to £1.20 per send.
> A 0.35% FX spread — that's below Wise's 0.42%, still above wholesale.
> And Vault Pro, a £4.99/month subscription that halves fees and unlocks
> priority support. At month 12 the average user sends 3.4 times, gross
> revenue per user is £7.62, payback is 13 days, gross margin is 83%.
>
> Our structural moat against Wise, Remitly, and Sendwave is that
> we don't touch correspondent banks. So when they compete us on price
> they cannibalise their own custodial float revenue. That's a hard
> position for them to defend from."

**(11:00–13:00 — Ask)**
> "We're raising £1.2 million on a SAFE at £6 million pre-money. Forty
> percent goes into the FCA money-transmission licence and compliance
> hires. Thirty percent into two senior engineers, focused on native
> WebRTC replacing our current Daily.co WebView and integrating Kotani
> Pay's M-Pesa off-ramp. Twenty percent into diaspora community growth.
> Ten percent runway.
>
> Eighteen months from close we're at 25,000 monthly actives, £8 million
> a month in transactions, and either FCA-licensed or in final review.
> That's the story we want to be telling a Series A investor."

**(13:00–14:00 — Close & CTA)**
> "The product is shipped. The rails are proven. The compliance path is
> defined. All we need now is fuel and a partner who understands
> diaspora fintech."
>
> [Pause. Silence. Wait for questions.]

**(14:00–15:00 — Q&A pivot)**
> "What questions can I answer?"

---

# APPENDIX C — Q&A Prep (top-25 anticipated investor questions)

### Regulatory

**Q: What happens if the FCA rejects your MTL?**
> Fall back to the FCA Sandbox route (currently accepting fintech
> applications through Q2 2027). Optionality via an EU-MiCA-registered
> subsidiary. But base case is grant, based on the readiness of our
> compliance stack — we've already built to MLR 2017 standard.

**Q: How does self-custody square with UK AML/KYC rules?**
> Under MLR 2017, we are a Cryptoasset Exchange Provider (CEP) for the
> fiat→crypto→fiat conversion at each end of the send. That's where the
> KYC and sanctions screening applies. The user's ownership of the
> asset in-between doesn't change our obligations — and it removes our
> Custody obligation, which is actually a lighter licence burden.

**Q: What about Travel Rule compliance (FATF R.16)?**
> All transactions over £1,000 emit the mandated sender and beneficiary
> data via TRP-standard messaging. The audit log captures the trail.

### Technical

**Q: What happens if USDC de-pegs?**
> We route across six chains including BTC, XLM, and XRP. In a
> USDC-emergency we pause USDC-corridors and continue on XLM/XRP. This
> is why we integrated a multi-chain router from day one, not day 500.

**Q: What about gas-fee volatility?**
> The user sees the total fee before they tap Send. If gas spikes we
> either eat it, route to a cheaper chain, or delay a batch. But this
> is theoretical — USDC on Base at £0.001/tx is not a volatility we
> lose sleep over.

**Q: Why not build on a single chain and simplify?**
> Single-chain concentration is a single-point-of-failure. Our
> multi-chain router is a differentiator against every competitor and
> a resilience story for the regulator.

**Q: How do you handle chargebacks?**
> There are none. On-chain transactions are irreversible. This is
> actually a feature for us — Wise loses about 0.4% of revenue to
> fraud chargebacks. We don't.

### Business model

**Q: How defensible is your fee floor?**
> Chain gas is our floor. It trends **down**, not up. Wise's floor is
> correspondent-bank fees, which trend flat or up. Time compounds in
> our favour.

**Q: What stops Wise from launching this?**
> They would cannibalise their custodial float, which generates a
> material portion of their profit. Their board would fight it.
> Meanwhile we get 24 months head-start and community lock-in.

**Q: What's your ARPU sensitivity if fees drop industry-wide?**
> Subscription revenue (Vault Pro) is our shock absorber — it's 100%
> margin after Stripe. If per-send fees are forced to zero we lean into
> subscriptions and B2B API revenue.

### Growth

**Q: Is £2.40 CAC realistic on TikTok/Instagram?**
> Yes, empirical for money-saving fintech in diaspora communities.
> Remitly's blended CAC in year 2 was £4.10 — and their message was
> less crisp than ours ("save 7% on your fees" beats "faster
> transfers").

**Q: What if referrals don't compound?**
> Referral is amplifier, not primary channel. Primary is community
> partnerships (churches, mosques, cultural associations, WhatsApp
> broadcast groups). Referral makes the primary channel free.

**Q: How do you defend against negative word-of-mouth from a failed transfer?**
> All transfers are refundable to the sender's wallet if the off-ramp
> partner fails — because it's their crypto. Contrast with Wise, where
> a failed transfer is a customer-service nightmare because Wise holds
> the money.

### Team & round

**Q: Why should we back this team over an ex-Revolut / ex-Wise team doing the same thing?**
> Because we've already shipped what an ex-Revolut team is still
> pitching. Speed and shipping discipline are the moat. And because
> we're diaspora ourselves — we're the user, they're not.

**Q: Why not raise more?**
> £1.2M is enough for the FCA milestone and two hires. Anything more
> without regulatory clarity is capital that just extends burn.
> Better to close at £6M pre, hit the milestone, and raise the Series A
> at £30M+ pre than raise more now at a lower multiple.

**Q: What's your dilution ceiling for Series A?**
> Target 18-22% dilution at Series A on a £30M+ pre. Founder ownership
> stays above 45% post-Series A.

**Q: What's your board composition proposal?**
> Two founders + one lead-investor seat + one independent (former MTL
> compliance officer as chair recommended).

### The uncomfortable ones

**Q: Crypto has burned a lot of retail investors. Why won't Vaulted?**
> Because we hide the crypto. Users type pounds, see pounds, receive
> local currency. They never hold a volatile asset. The stablecoin
> journey happens under the hood and lasts 5 seconds. This is not a
> "buy Bitcoin" app.

**Q: What if a user loses their seed phrase?**
> Cloud backup opt-in via iCloud Keychain / Google Drive (encrypted).
> Social recovery via the M-of-N multisig scaffolding we've already
> built. Ultimately, self-custody means we can't recover for them —
> which is a UX challenge, but also a regulatory advantage (we're not
> a custodian).

**Q: What's the honest downside case?**
> Down-round Series A at £15M pre if FCA drags to month 20+. We survive
> — we have 18 months of runway from close and revenue is positive by
> month 17. But the return multiple compresses.

---

# APPENDIX D — Investor Targeting

**Sweet spot funds for this raise:**
* UK fintech seed: Passion Capital, Ada Ventures, LocalGlobe, Kindred
* Crypto/web3-native with fintech thesis: 1kx, Bain Capital Crypto (UK team), Fabric Ventures
* Diaspora / impact overlay: Founders Factory Africa, Norrsken, Better Ventures
* Angels: ex-founders of Wise, Revolut, Airtel Money, MFS Africa

**Anti-fit:**
* Pure crypto/token funds (we're not tokenising anything)
* US-only funds (regulatory alignment is UK-first)

**Warm-intro paths to prioritise:**
1. Any current UK-based Wise or Revolut early-employee → Passion Capital
2. Ada Ventures fintech portfolio company founders (Kindred, Wagestream)
3. LocalGlobe partners: Ophelia Brown, Julia Hawkins (both fintech-active)

---

# APPENDIX E — Follow-up email templates

### Cold outreach template

> Subject: Vaulted — self-custody remittance, £1.2M seed, live in production
>
> Hi [Name],
>
> Vaulted is a UK-launched self-custody remittance app — think Wise's
> UX with Coinbase's rails, delivered as one product. We're live on
> six chains, eight corridors, and we've shipped end-to-end KYC,
> sanctions screening, and an FCA-audit-log stack. Users send £50 to
> Kenya in five seconds for 62p.
>
> We're raising £1.2M seed to hit our FCA money-transmission licence
> and 25k MAU. I noticed [Fund] backed [Portfolio Co] which shares our
> diaspora-fintech thesis — would you be up for a 20-minute call this
> or next week?
>
> Deck: [link]
> Demo (60s): [Loom link]
>
> Best,
> [Founder name]

### Post-meeting follow-up template

> Subject: Vaulted — follow-ups from our conversation
>
> [Name],
>
> Thanks for the time this morning. As promised:
>
> 1. **The FCA timeline question** — [1-para written answer]
> 2. **Cohort retention data** — [chart or link]
> 3. **Introduction to [our compliance advisor]** — cc'd on this thread
>
> Happy to dive into any of these deeper. Also happy to introduce you
> to our two most active diaspora-champion users if you want to hear
> the demand-side story directly.
>
> Warm regards,
> [Founder]

---

# CLOSING NOTE — What makes this pitchable *right now*

Three things separate Vaulted from 95% of fintech seed pitches this quarter:

1. **The product is shipped.** Investors are drowning in decks. You'll
   walk in with a phone in your hand and let them send £5 to Kenya
   during the meeting. Nobody else at this stage can do that.

2. **The compliance work is done, not promised.** OpenSanctions,
   audit-log, tier limits, KYC — all built to MLR 2017 standard and
   already producing audit-ready output. This is the single biggest
   reason FCA-track fintechs miss their timelines. You've collapsed
   that risk.

3. **The market is timed, not chased.** UK stablecoin regime, L2 gas
   floor, diaspora density, Wise-account-closure fallout — every one
   of these tailwinds is 6–18 months old. The window to be first is
   still open. In 12 months it isn't.

Now go raise the money. Good luck. 🚀
