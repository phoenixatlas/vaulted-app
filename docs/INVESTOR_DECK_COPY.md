# Vaulted — 12-Slide Investor Deck · Slide-by-Slide Copy

Complete production copy for the pitch deck. Every slide has:
- **Headline** — the 3-second glance value
- **Body copy** — the 11-second scan value
- **Visual brief** — exactly what image / chart / screenshot to include
- **Speaker notes** — what you say verbally when presenting

Total deck length target: **12 slides, no more.** VCs share decks that
are too long by forwarding just the first 8. Own the whole story arc.

---

## 🎨 DECK-LEVEL DESIGN SYSTEM (set once, apply to every slide)

| Property | Value | Rationale |
|---|---|---|
| **Aspect ratio** | 16:9 (1920×1080) | Standard for Notion, Loom, most projectors |
| **Background** | `#0A0807` (matches landing site + app) | Consistent brand across all touchpoints |
| **Primary type** | Inter (headers 40–60pt, body 18–24pt) | Modern, screen-optimised, free from Google Fonts |
| **Serif accent** | Cormorant / Playfair Display (for pull-quotes only) | Adds gravitas on hero slides — use sparingly |
| **Primary gold** | `#C9A35B` | Matches brand |
| **Gold-light** | `#E6C879` | Emphasis / headlines |
| **Gold-cream** | `#F5E9C9` | Body text on dark background |
| **Text-secondary** | `#B8AFA1` | Sub-headlines, captions |
| **Accent-danger** | `#D64545` | For the "fee tax" bar in slide 2 |
| **Chart accents** | `#7AB8B0` (teal), `#C9A35B` (gold), `#D64545` (red) | High-contrast, colour-blind-safe trio |

**Tool recommendation:** Figma (free tier is enough). Alternatives in
descending order of quality: Pitch, Notion Slides, Google Slides.
Avoid PowerPoint — the export handling on Mac is broken in 2026.

**Slide numbering:** small, bottom-right, in `#B8AFA1`. NEVER slide 1 —
title slide is un-numbered.

**Footer on every slide except title & closing:**
- Bottom-left: `Vaulted · Confidential · [MONTH YEAR]`
- Bottom-right: slide number, e.g. `04 / 12`

---

# 🎬 SLIDE 1 · TITLE

**Layout:** Large centred logo mark. Wordmark below. Tagline in serif
italic below that. Founder name + month/year at bottom.

**Copy on slide:**

```
                     [VAULTED LOGO MARK]

                        V A U L T E D

              Instant, sovereign cross-border remittance.

                    ────────────────────

           [Founder Full Name]  ·  July 2026
             Seed Round — Confidential Draft
```

**Visual brief:**
- Logo mark centred, ~180px tall
- Wordmark in Inter Regular, 56pt, letter-spacing 8pt
- Tagline in Cormorant Italic 28pt, `#F5E9C9`
- Small horizontal gold divider between tagline and name block
- Background: pure `#0A0807` — no image, no clutter

**Speaker notes:**
> [Open with silence for 2 seconds while you settle. Then, warm and
> direct:]
>
> "Good morning [Name]. Thanks for the time. I'm [Founder], I'm the
> founder of Vaulted — self-custody cross-border remittance for the
> UK diaspora. I've prepped for exactly the twenty minutes you gave
> me. Are we still on for that or should I compress?"
>
> [This last sentence is scripted deliberately — it signals respect
> for time AND makes them explicitly reaffirm the meeting length. VCs
> appreciate founders who protect their calendar.]

---

# 🚨 SLIDE 2 · THE PROBLEM

**Layout:** One big number in the centre. Bar chart below. Human-anchor
caption at bottom.

**Copy on slide:**

```
          UK diaspora paid

               £980m

     in remittance fees last year alone.

      ────────────────────────────────

      Average fee on the UK's biggest corridors:

      UK → Ghana        ████████████████ 9.1%
      UK → Nigeria      ███████████████  8.7%
      UK → Senegal      ███████████████  8.9%
      UK → Kenya        ██████████████   7.4%
                                              ← SDG 10.c target: 3%

      A Kenyan NHS nurse sending £300/mo home loses
      £266 a year — a term of school fees.
```

**Visual brief:**
- Huge `£980m` in gold gradient, 120pt, dead-centre top-third
- Horizontal bar chart with corridors labelled left, %s labelled right
- Bars filled in red (`#D64545`); a dotted vertical line at 3% labelled "SDG 10.c target"
- Caption at the bottom in Inter Italic 20pt

**Source line (tiny, bottom-right):** `Source: World Bank RPW Q4 2025, £200 benchmark send`

**Speaker notes:**
> "The world sends 908 billion dollars home a year. It should cost
> 3% under the UN's SDG target. On the UK's most important corridors
> to Africa, it still costs 7 to 9 percent. Sarah, a Kenyan nurse
> in Peckham, sends £300 home every month. She loses £266 a year to
> a wire-transfer fee. That's a term of school fees for her nephew.
> This is the tax we're removing."
>
> [30 seconds. Do not rush the number 980. It has to land.]

---

# ⏰ SLIDE 3 · WHY NOW

**Layout:** 2×2 grid, each quadrant a punchy claim + one supporting stat.

**Copy on slide:**

```
                      Why now?

┌─────────────────────────────┬─────────────────────────────┐
│  Regulatory clarity          │  Rails are ready             │
│                              │                              │
│  UK Treasury opened          │  USDC on Base:               │
│  stablecoin consultation     │  £0.0008 gas per transfer    │
│  Q1 2026. FCA MTL is a       │  4× cheaper than 2024.       │
│  known-path licence.         │  1000× cheaper than SWIFT.   │
├─────────────────────────────┼─────────────────────────────┤
│  Diaspora density            │  Trust vacuum                │
│                              │                              │
│  3.2m sub-Saharan            │  Wise closed 4,000+          │
│  African-heritage residents  │  Nigerian accounts in 2024.  │
│  in the UK. Concentrated in  │  Users are asking: why not   │
│  London / Manchester / Bham. │  self-custody?               │
└─────────────────────────────┴─────────────────────────────┘
```

**Visual brief:**
- Each quadrant: bold headline (Inter 28pt gold), one supporting stat
  in body (Inter 20pt cream), no bullet points
- Thin gold dividers between quadrants
- Optional icon in top-left of each quadrant (regulatory: shield;
  rails: lightning; diaspora: globe; trust: broken chain)

**Speaker notes:**
> "Four things aligned in the last eighteen months. First, the UK
> Treasury opened its stablecoin consultation — the regulatory path
> is clear. Second, gas on the L2s we route through is running at
> under a penny; the rails are literally cheaper than SWIFT by a
> factor of a thousand. Third, the UK has 3.2 million sub-Saharan
> African residents concentrated in London, Manchester and Birmingham
> — the density that makes referral marketing work. And fourth, Wise
> closed four thousand Nigerian accounts in 2024, and the diaspora
> is asking the question we're answering."
>
> [45 seconds. Slow down on the fourth point — it's the emotional
> catalyst.]

---

# 📱 SLIDE 4 · SOLUTION (Live Demo)

**Layout:** Three phone-frame mockups side-by-side, each showing a stage
of the send flow.

**Copy on slide:**

```
      Type pounds. Tap a flag. Done.

  ┌────────────┐    ┌────────────┐    ┌────────────┐
  │            │    │            │    │            │
  │  Send £50  │    │  £50 GBP → │    │     ✅     │
  │            │    │  8,732 KES │    │            │
  │ [flag] 🇰🇪 │ →  │  fees £0.62│ →  │   Sent to  │
  │            │    │  ~5 seconds│    │   +254...  │
  │ [Send btn] │    │  [Confirm] │    │            │
  └────────────┘    └────────────┘    └────────────┘

  1. Enter amount     2. Live quote      3. Arrived (5s later)
     Pick country        Biometric auth     Recipient buzzes

               → Live product · 60-second demo Loom
                    [ QR code to Loom link ]
```

**Visual brief:**
- Three device-frame screenshots at 320×640 each, arranged left→right with arrow separators
- Actual screenshots from the app — retake if UI has changed since
- Below the frames: a small QR code linking to the 60s Loom
- Caption below QR: "Point your phone at this code to watch the send happen live"

**Speaker notes:**
> "This is what Sarah sees. She types 50 in the amount field. She taps
> the Kenyan flag. The app quotes 8,732 shillings, fees 62 pence,
> arriving in about five seconds. Face ID. Done. In the third frame
> the money's already there — her mum's phone has already buzzed.
>
> I have this on my phone. If you want to see it live at the end of
> this deck I'll happily send you a fiver."
>
> [30 seconds. The offer to send them £5 is a power move — most VCs
> will decline but the offer itself proves confidence and lands the
> memory of the demo.]

---

# ⚙️ SLIDE 5 · HOW IT ACTUALLY WORKS

**Layout:** Horizontal flow diagram with 3 boxes + 2 arrows. Below,
a caption in italic.

**Copy on slide:**

```
              What the user sees:

     [phone] Type £50 → tap 🇰🇪 → tap Send

              What actually happens:

  ┌───────────┐     ┌───────────┐     ┌───────────┐
  │  User key │  →  │  Chain    │  →  │  Local    │
  │  signs on │     │  Router   │     │  off-ramp │
  │  device   │     │  picks    │     │  (mobile  │
  │           │     │  cheapest │     │  money /  │
  │  BIP-39,  │     │  chain in │     │  P2P /    │
  │  Secure   │     │  real     │     │  wallet)  │
  │  Enclave  │     │  time     │     │           │
  └───────────┘     └───────────┘     └───────────┘

           Self-custody         6 chains: BTC · ETH ·      8 corridors, 5s
           throughout           USDC (Poly/Base/Arb)       settlement
                                · SOL · XLM · XRP

     ─────────────────────────────────────────────────

  "We are the first remittance app whose fee floor is chain gas —
             not correspondent-bank fees."
```

**Visual brief:**
- Three boxes in horizontal flow, connected by thick gold arrows
- Icon in each box (fingerprint, router, phone-with-KES)
- Small captions beneath each box in `#B8AFA1`
- Pull-quote at bottom in Cormorant Italic 22pt gold — the memorable line

**Speaker notes:**
> "Three things happen. One, her key never leaves her phone. Two, our
> chain router looks at fees, FX, and settlement time across six
> chains and picks the winner — for a UK→Kenya send that's usually
> Stellar or USDC on Polygon. Three, the settlement lands via a local
> off-ramp — for Kenya that's Kotani Pay's M-Pesa bridge.
>
> This is the sentence I want you to remember: we're the first
> remittance app whose fee floor is chain gas, not correspondent-bank
> fees. That's a structural cost advantage the incumbents cannot
> match without cannibalising their own revenue base."
>
> [45 seconds. Pause after the pull-quote.]

---

# 📦 SLIDE 6 · WHAT'S SHIPPED

**Layout:** 3×2 grid of app screenshots, each with a small caption.
Bold header "**All of this is live in production today.**"

**Copy on slide:**

```
              All of this is live in production today.

  ┌──────────┐  ┌──────────┐  ┌──────────┐
  │  Wallet  │  │   Send   │  │   KYC    │
  │          │  │  Money   │  │  Stripe  │
  │ [screen] │  │ [screen] │  │ [screen] │
  │          │  │          │  │          │
  │ 6 chains │  │ 8        │  │ Live     │
  │  live    │  │ corridors│  │ mode     │
  └──────────┘  └──────────┘  └──────────┘

  ┌──────────┐  ┌──────────┐  ┌──────────┐
  │Referrals │  │   Chat   │  │  Audit   │
  │          │  │   +      │  │   Log    │
  │ [screen] │  │  Video   │  │ [screen] │
  │          │  │ [screen] │  │          │
  │ £5 credit│  │  E2E     │  │ MLR 2017 │
  │ both     │  │encrypted │  │compliant │
  │ sides    │  │          │  │          │
  └──────────┘  └──────────┘  └──────────┘

              53 automated tests · deployed on Render + Vercel
```

**Visual brief:**
- Six actual screenshots from the app (phone-frame optional but recommended)
- Consistent scale — same crop ratio for all six
- Small caption below each: feature name + status badge

**Speaker notes:**
> "I want to spend one slide on evidence. Everything you see here is
> shipped, in production, hittable at phoenix-atlas.com right now.
> The wallet is self-custody across six chains. Send Money is live
> for eight corridors. KYC uses Stripe Identity in Live mode — not
> test mode. Referrals give both sides £5 credit on verification.
> Chat is end-to-end encrypted with TweetNaCl. Video calls run
> through Daily.co. And the audit log is built to MLR 2017 standard
> with immutable event trails for FCA record-keeping.
>
> 53 automated tests, deploy on merge. This isn't a mockup."
>
> [40 seconds. Keep pace up — this slide's job is to close the "is
> it real?" question.]

---

# 🌍 SLIDE 7 · MARKET

**Layout:** Three concentric circles or a funnel showing TAM / SAM /
SOM. Right-hand column: world map with UK-outbound corridors highlighted.

**Copy on slide:**

```
                       Market

    ┌─────────────────────────────────────────────┐
    │  TAM   Global remittance flows to LMICs     │
    │        $908bn / yr (World Bank, 2025)       │
    │                                              │
    │  ┌──────────────────────────────────────┐   │
    │  │  SAM  UK-outbound to our corridors   │   │
    │  │       £12.1bn / yr                   │   │
    │  │                                       │   │
    │  │  ┌──────────────────────────────┐    │   │
    │  │  │  SOM  1.5% share in 3 yrs    │    │   │
    │  │  │       £145m / yr volume       │    │   │
    │  │  │       £1.74m / yr revenue     │    │   │
    │  │  └──────────────────────────────┘    │   │
    │  └──────────────────────────────────────┘   │
    └─────────────────────────────────────────────┘

    Wedge: UK → sub-Saharan Africa
    · 3.2m diaspora residents in UK
    · £4.7bn annual outbound flow
    · 7.4–9.1% current avg fee
    · High density = viral referral loop
```

**Visual brief:**
- Three concentric circles/rectangles, TAM outermost, SOM innermost
- Each shell in a slightly darker shade of the same gold; SOM in
  brightest gold
- Sub-column on the right with a small world map showing UK as origin
  and 8 destination pins
- Sources footnote bottom-right

**Speaker notes:**
> "TAM is the World Bank number — 908 billion dollars globally. Our
> SAM is UK-outbound to the eight corridors we serve — 12.1 billion
> pounds a year. Our SOM at 1.5% share in three years is 145 million
> in transaction volume, 1.74 million in revenue.
>
> But the number that matters most is our wedge: the UK → sub-Saharan
> African corridor is 4.7 billion pounds a year, currently paying 7
> to 9 percent, and the diaspora is dense enough in London and
> Manchester that community-driven growth compounds. That's where
> the first 25,000 users come from."
>
> [45 seconds.]

---

# ⚔️ SLIDE 8 · COMPETITION

**Layout:** A table. Highlight Vaulted's row with a gold band. Highlight
Vaulted's cost cell with a bright pop.

**Copy on slide:**

```
                    UK → Nigeria, £100 send

  ┌──────────────┬─────────┬────────┬──────────┬───────────────┐
  │  Provider    │  Fee    │  Speed │  Custody │  Weakness     │
  ├──────────────┼─────────┼────────┼──────────┼───────────────┤
  │  Vaulted     │  £0.62  │   5s   │  User    │  Awareness    │  ← US
  ├──────────────┼─────────┼────────┼──────────┼───────────────┤
  │  Wise        │  £2.85  │  20m–  │  Wise    │  Frozen acct  │
  │              │         │  24h   │          │  risk         │
  │  Remitly     │  £3.99  │  15m–  │  Remitly │  Cash pickup  │
  │              │         │  hours │          │  friction     │
  │  WorldRemit  │  £3.49  │  Hours │  WR      │  Fee creep    │
  │  Western U.  │  £8.90  │  Var.  │  WU      │  Legacy costs │
  │  Coinbase    │  Free*  │  Mins  │  Exchange│  User must    │
  │  (*+swap)    │         │        │          │  know crypto  │
  │  MetaMask    │  Free   │  Secs  │  User    │  12-word seed │
  │              │  (gas)  │        │          │  gauntlet     │
  └──────────────┴─────────┴────────┴──────────┴───────────────┘

      "We are Wise's UX + Coinbase's rails,
       delivered as one app, self-custody by default."
```

**Visual brief:**
- Table with monospace or condensed sans (Inter Regular 18pt works)
- Vaulted row: background `#C9A35B` at 15% opacity, gold border top+bottom
- Vaulted's fee cell: dark chip with `£0.62` in gold — this is the number that stays in their heads
- Pull-quote at the bottom in Cormorant Italic 22pt

**Speaker notes:**
> "This is the slide you'll remember when you leave. On a £100 send
> to Nigeria: Wise charges £2.85, Remitly £3.99, Western Union
> £8.90. We charge 62 pence. Coinbase is technically cheaper but
> the user has to know what a chain is. MetaMask is technically
> equivalent but the user has to survive a 12-word-seed onboarding.
>
> We are Wise's UX plus Coinbase's rails, delivered as one app, self-
> custody by default. That's the sentence."
>
> [30 seconds. Say the pull-quote slowly at the end.]

---

# 💰 SLIDE 9 · BUSINESS MODEL

**Layout:** Left column: three revenue-stream boxes stacked. Right column:
unit-economics block with big numbers.

**Copy on slide:**

```
                      Business Model

  ┌────────────────────────┐  ┌─────────────────────────────┐
  │  1. Send fee            │  │  Unit economics (month 12)  │
  │     £0.50–1.20 / send   │  │                              │
  │                         │  │      3.4      Sends / user   │
  │  2. FX spread           │  │       £185    Avg send size  │
  │     0.35% baked in      │  │                              │
  │     (Wise is 0.42%)     │  │      £2.24    Rev per send    │
  │                         │  │      £7.62    Rev / user / mo │
  │  3. Vault Pro           │  │                              │
  │     £4.99 / mo          │  │      £3.20    CAC             │
  │     50% off fees        │  │      13 days  Payback         │
  │     + priority support  │  │                              │
  │                         │  │        83%    Gross margin    │
  │  4. B2B API (2027)      │  └─────────────────────────────┘
  │  5. USDC yield (2027)   │
  └────────────────────────┘

      Structural moat: chain gas trends ↓, correspondent-bank
      fees trend →.  Time compounds in our favour.
```

**Visual brief:**
- Left column: five numbered boxes for revenue streams; first three
  bold in gold, last two in `#B8AFA1` marked "Phase 2 · 2027"
- Right column: 8 stat rows, big number in gold 36pt, label in cream 16pt
- Bottom-of-slide pull-quote in Cormorant Italic

**Speaker notes:**
> "Five revenue streams, three of them live today: flat send fee,
> a 0.35% FX spread which is below Wise, and Vault Pro subscription.
> Two more we haven't turned on yet: a B2B API for community
> organisations and stablecoin yield on our reserve float — both
> for 2027.
>
> Unit economics at month twelve: the average user sends 3.4 times,
> gross revenue per user is 7 pounds 62, payback on a 3.20 CAC is
> thirteen days, gross margin is 83 percent.
>
> The moat is on the last line. Our fee floor is chain gas — it
> trends down. Their fee floor is correspondent-bank fees — flat at
> best. Time is on our side."
>
> [50 seconds.]

---

# 📈 SLIDE 10 · TRACTION & ROADMAP

**Layout:** A horizontal timeline. Left of "TODAY" marker: shipped
milestones. Right: 6/12/18-month targets.

**Copy on slide:**

```
                Traction & Roadmap

  ── SHIPPED ─────────────────  T   ── TARGETS ─────────────
                                O
   6 chains live                D    Month 6   →  2,400 MAU
   8 corridors live             A                £480k / mo volume
   Stripe Live (subs + KYC)     Y                
   Sanctions screen             |    Month 12  →  9,800 MAU
   MLR audit log                |                £2.1M / mo volume
   Referral loop                |                £52k / mo revenue
   E2E chat + video             |                
   53 automated tests           |    Month 18  →  25,000 MAU
   Production deployment        |                £8M / mo volume
                                |                £150k / mo revenue
                                |                FCA MTL granted
                                |                
                                |                ─── Series A opens ───
```

**Visual brief:**
- Full-width horizontal timeline, gold line down the centre-vertical
  midpoint labelled "TODAY"
- Left side: ticked checkmarks against each shipped milestone
- Right side: forward arrows against each future milestone
- Each target block sized to reflect scale (month 18 block visibly larger than month 6)

**Speaker notes:**
> "Left side is shipped, right side is next. In the last twelve months
> we shipped six chains, eight corridors, Stripe in Live mode with
> both subscriptions and Identity KYC, sanctions screening, an FCA-
> track audit log, referral flywheel, encrypted chat, video calls,
> and 53 automated tests.
>
> In the next eighteen months: 25,000 monthly active users, 8 million
> pounds in monthly transaction volume, 150,000 in monthly revenue,
> FCA money-transmission licence granted or in final review. Base
> case break-even is month 17. Series A conversation opens at month
> 15."
>
> [45 seconds.]

---

# 👥 SLIDE 11 · TEAM

**Layout:** Two big headshots at top (founders). Below: advisors row
with smaller circle photos. Below that: open-roles row.

**Copy on slide:**

```
                        Team

  ┌─────────────┐              ┌─────────────┐
  │   [Photo]   │              │   [Photo]   │
  │  Founder /  │              │    CTO      │
  │    CEO      │              │             │
  │             │              │             │
  │ [Name]      │              │ [Name]      │
  │ Prior: [1-  │              │ Prior: [1-  │
  │ line credi- │              │ line credi- │
  │ bility]     │              │ bility]     │
  └─────────────┘              └─────────────┘

              ─────── Advisors ───────

     [O]           [O]           [O]           [O]
   [Name]        [Name]        [Name]        [Name]
   [1-line]      [1-line]      [1-line]      [1-line]

              ─── Hiring post-close ───

   Senior Engineer  ·  MLRO (compliance)  ·  Head of Growth
```

**Visual brief:**
- Founder headshots: 200×200 circular crop, warm lighting, direct
  eye contact (NOT candids)
- Advisor row: 80×80 circular crops, name below in Inter 14pt
- If you have logos of prior companies (Wise, Monzo, PwC, etc.), place
  as small greyscale icons under each founder's name-block
- Open-roles row at the bottom in `#B8AFA1`

**⚠️ You must fill this slide in with real names + real photos. Do not
present a deck with a placeholder team slide.** If you don't have
formal advisors, list any prior founders / operators who have taken
your call once. VCs know the difference between "advisor with equity"
and "supportive contact" — being clear about which is which earns credibility.

**Speaker notes:**
> "[Name] and I have been building together for [X] months. [One
> paragraph on how you two met and why the pairing works — this is
> the personal moment, don't script it too tightly.]
>
> Our advisors are [name] — [what they bring] — and [name] — [what
> they bring].
>
> Post-close we hire in this order: a senior backend engineer to
> finish the router refactor and integrate Kotani Pay, an MLRO to
> own the FCA application, and a head of growth to run community-
> partnership marketing."
>
> [60 seconds. This is the most personal slide. Slow down.]

---

# 🎯 SLIDE 12 · THE ASK

**Layout:** One big number at top. Pie chart of use-of-funds. Timeline
at the bottom. Contact block below timeline.

**Copy on slide:**

```
                        The Ask

                    £1.2m seed
             on a £6m pre-money SAFE
                (16.7% dilution)

  ┌───────────────────────────────────────────────┐
  │       Use of funds (18-month runway):          │
  │                                                 │
  │   40% ██████████  Compliance + FCA MTL         │
  │   30% ████████    Engineering (2 senior hires) │
  │   20% █████       Community + paid growth      │
  │   10% ███         Ops runway                    │
  └───────────────────────────────────────────────┘

  Close by Q3 2026  →  Milestones by Q1 2028  →  Series A open

  ─────────────────────────────────────────────────

              [Founder Name]
              founder@phoenix-atlas.com
              [Phone / Calendly link]

              phoenix-atlas.com
```

**Visual brief:**
- Big `£1.2m seed` in gold gradient, 96pt, top-third centred
- Use-of-funds as horizontal bar chart OR pie chart (bar chart reads faster in a meeting)
- Bottom: contact block on a gold-tinted panel with founder headshot next to it
- QR code to your Calendly bottom-right

**Speaker notes:**
> "1.2 million pound seed on a 6 million pre-money SAFE. Sixteen point
> seven percent dilution. Forty percent goes into the FCA
> money-transmission licence and compliance hires. Thirty into two
> senior engineers. Twenty into community marketing. Ten into runway.
>
> We're closing by the end of Q3. If LocalGlobe leads this round,
> Vaulted becomes a portfolio company that repeats the TransferWise
> pattern — but the fee floor is chain gas, not correspondent banks.
> This is the same thesis you backed in 2011. Fifteen years later,
> and with lower structural costs.
>
> I'd love to work with you. What questions can I answer?"
>
> [45 seconds. End on the question, not on a period. Hold eye contact.
> Then be silent for as long as it takes for them to speak.]

---

# 📋 DECK PRODUCTION CHECKLIST

Before your first send:

**Design pass**
- [ ] Every slide uses the same background colour (`#0A0807`)
- [ ] Every headline is 40pt+ (readable on a phone preview)
- [ ] Every slide has ≤ 30 words of body copy
- [ ] Footer (bottom-left brand · bottom-right slide number) on every slide 2–11
- [ ] Sources cited on slides 2 and 7 in a tiny footnote
- [ ] Team slide has real photos and real names — no placeholders

**Content pass**
- [ ] Every stat traceable to a source you can defend in Q&A
- [ ] All screenshots current with the shipped UI
- [ ] Founder name filled in on slides 1 and 12
- [ ] Calendly / phone / email on slide 12 tested (does the link work?)
- [ ] QR code on slide 4 links to the actual Loom (test in a QR scanner)

**Distribution pass**
- [ ] Exported to PDF at 1080p (Figma → Export → PDF, ONE page per slide)
- [ ] File name: `Vaulted_Deck_v1_2026-07.pdf` (semver + date; VCs collect these)
- [ ] Cover-thumbnail: the title slide (not a random middle slide)
- [ ] Deck is under 8MB (compress screenshots if not)
- [ ] Password-protected? NO. Never. It kills forward rate.
- [ ] DocSend or Attio tracking on? Optional. Fine either way.

**Deck-to-email pass**
- [ ] Deck link is a public Google Drive / Notion / Docsend URL that
      requires NO account to open
- [ ] Test in an incognito browser — you'd be amazed how often the
      permissions are wrong
- [ ] The email that includes the deck link ALSO includes the Loom link
      (belt and braces — different VCs prefer different formats)

---

# 🧠 WHAT MAKES THIS DECK DIFFERENT

Most seed decks fail one of three ways: too long (20+ slides), too
vague (talks about "the market" not the users), or too polished
(reads like a marketing agency built it).

This deck is 12 slides. Every slide has a specific human moment
(Sarah in Peckham, Julia's Wise investment, the £0.62 fee number).
It's rough enough at the edges that Julia will read it and think
"this founder built this, not their brand agency" — which is exactly
what you want her to think.

**One last note on order.** If Julia asks a question on slide 6, do NOT
say "great question, I'll cover that on slide 9." Answer immediately.
The deck is a scaffold, not a script. The best pitches wander.

Now go build it. 🚀
