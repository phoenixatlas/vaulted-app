"""Copy for the multi-page phoenix-atlas.com site (used by build_site.py).

Rules: keep every regulatory disclaimer; label amounts as illustrative; never
claim live customer service before FCA authorization.
"""

SITE = {
    "url": "https://www.phoenix-atlas.com",
    "summary": ("Vaulted is a fiat-first cross-border remittance app with a self-custody crypto wallet, built by "
                "Phoenix-Atlas Technologies Ltd (UK, Company No. 17432346). It is designed for UK/EU to Africa "
                "and Africa to UK/EU payments over regulated stablecoin rails. Vaulted is in waitlist / preview "
                "mode and is not yet authorized by the FCA; it is not open for customer transactions."),
    "facts": [
        "Company: Phoenix-Atlas Technologies Ltd, registered in England and Wales, Company No. 17432346.",
        "Product: Vaulted — cross-border remittance + self-custody wallet + end-to-end encrypted chat and video calls.",
        "Status: pre-launch, waitlist and preview app only; live money transfer launches upon applicable FCA authorizations.",
        "Directions: UK/EU to Africa (outbound) and Africa to UK/EU (reverse corridor, for school fees, medical bills and business payments).",
        "Rails: regulated stablecoins (USDC) and low-cost networks (Stellar XLM, XRP Ledger, Polygon, Base, Arbitrum); payout to mobile money (M-Pesa, MoMo) or bank.",
        "Planned pricing: Free tier with 3 cross-border sends per month at a 1.5% service fee (min £0.50, max £9.99); Vault Pro £9.99/month with 50% off fees.",
        "Security: keys generated on-device (BIP-39 12-word phrase), biometric authentication, multi-signature approvals, TweetNaCl end-to-end encryption.",
        "Contact: hello@phoenix-atlas.com · investors: invest@phoenix-atlas.com · support: support@phoenix-atlas.com.",
    ],
}

NAV = [
    ("Send money", "/send-money-to-africa"), ("Africa &rarr; UK", "/africa-to-uk"), ("Wallet", "/wallet"),
    ("Security", "/security"), ("Corridors", "/corridors"), ("Pricing", "/pricing"),
    ("Business", "/business"), ("Investors", "/investors"), ("Learn", "/learn"),
]

ILLUSTRATIVE = ('<p style="font-size:13px;color:var(--text-muted)">Vaulted is in build and not yet FCA-authorized. '
                'Everything described here is planned functionality; amounts, fees and timings are illustrative targets.</p>')

PAGES = [
    {
        "path": "/", "crumb": "Home",
        "title": "Vaulted — Send Money from the UK to Africa and Back | Self-Custody Remittance App",
        "desc": "Vaulted by Phoenix-Atlas is a UK fintech in build: fiat-first remittance between the UK/EU and Africa on stablecoin rails, with a self-custody wallet and encrypted chat. Join the waitlist.",
        "ld": [{"@context": "https://schema.org", "@type": "WebSite", "name": "Vaulted", "url": "https://www.phoenix-atlas.com/"},
               {"@context": "https://schema.org", "@type": "SoftwareApplication", "name": "Vaulted", "applicationCategory": "FinanceApplication",
                "operatingSystem": "iOS, Android, Web", "description": SITE["summary"],
                "offers": {"@type": "Offer", "price": "0", "priceCurrency": "GBP"},
                "publisher": {"@type": "Organization", "name": "Phoenix-Atlas Technologies Ltd"}}],
        "blocks": [
            ("hero",),
            ("cards", "<h2>Everything Vaulted does, one page each.</h2><p>Pick the part that matters to you.</p>", [
                {"title": "Send money to Africa", "body": "Pounds, euros or dollars in; M-Pesa, mobile money or bank payout out. No crypto knowledge needed.", "href": "/send-money-to-africa"},
                {"title": "Africa to the UK &amp; EU", "body": "The reverse corridor for school fees, medical bills and business payments into GBP and EUR.", "href": "/africa-to-uk"},
                {"title": "Self-custody wallet", "body": "Your keys stay on your device. Six networks, multi-signature approvals and encrypted chat.", "href": "/wallet"},
                {"title": "Security model", "body": "How we protect keys, messages and approvals &mdash; and what we deliberately cannot see.", "href": "/security"},
                {"title": "Planned corridors", "body": "Eleven planned destination countries, with live sandbox rates on the first African rails.", "href": "/corridors"},
                {"title": "Pricing &amp; comparison", "body": "Free tier, Vault Pro, and how planned fees compare with today&rsquo;s alternatives.", "href": "/pricing"},
            ]),
            ("legacy", "Three steps to sovereignty"),
            ("cards", "<h2>Who we&rsquo;re building for.</h2>", [
                {"title": "Families sending money home", "body": "Monthly support, emergencies and bills &mdash; fast and in local currency.", "href": "/send-money-to-africa#who-its-for", "cta": "See how"},
                {"title": "Businesses &amp; payment partners", "body": "Payment banks and PSPs exploring stablecoin settlement or a white-label corridor.", "href": "/business"},
                {"title": "Investors", "body": "Reverse-corridor unit economics, the 5-page deck and a 20-minute founder call.", "href": "/investors"},
                {"title": "Regulators &amp; due diligence", "body": "Our authorization status, launch stages and company details in one place.", "href": "/compliance"},
            ], True),
        ],
    },
    {
        "path": "/send-money-to-africa", "crumb": "Send money to Africa",
        "title": "Send Money from the UK to Africa — Kenya, Nigeria, Ghana & More | Vaulted",
        "desc": "How Vaulted plans to send money from the UK and EU to Kenya (M-Pesa), Nigeria, Ghana, Uganda, Tanzania and more in seconds, funded by card, Apple Pay or bank transfer.",
        "blocks": [
            ("hero", "UK/EU &rarr; Africa", "Send money home in <span class=\"gold-text\">seconds</span>, not days.",
             "Enter pounds, euros or dollars. Your recipient gets local currency to M-Pesa, mobile money or their bank account. Vaulted handles the stablecoin rail in the middle &mdash; you never have to touch crypto."),
            ("legacy", "features"),
            ("legacy", "Three steps to sovereignty"),
            ("legacy", "who-its-for"),
            ("prose", "<h2>What you&rsquo;ll need to send</h2><ul>"
                      "<li><strong>Kenya:</strong> the recipient&rsquo;s M-Pesa phone number.</li>"
                      "<li><strong>Nigeria:</strong> the 10-digit account number (NUBAN) and bank &mdash; Vaulted checks the account holder&rsquo;s name before you confirm.</li>"
                      "<li><strong>Ghana, Uganda, Tanzania:</strong> the recipient&rsquo;s mobile-money number.</li></ul>"
                      "<p>See every planned destination on the <a href=\"/corridors\">corridors page</a>, fees on <a href=\"/pricing\">pricing</a>, or read our guide on "
                      "<a href=\"/learn/send-money-uk-to-nigeria-kenya\">how to send money from the UK to Nigeria and Kenya</a>.</p>" + ILLUSTRATIVE),
        ],
    },
    {
        "path": "/africa-to-uk", "crumb": "Africa to UK &amp; EU",
        "title": "Send Money from Nigeria, Kenya, Ghana & South Africa to the UK and EU | Vaulted",
        "desc": "Vaulted's reverse corridor is designed for paying UK tuition, medical bills and suppliers from Africa into GBP or EUR over regulated stablecoin rails instead of SWIFT.",
        "blocks": [
            ("hero", "Africa &rarr; UK/EU &middot; Reverse corridor", "Pay UK school fees from Lagos in <span class=\"gold-text\">minutes</span>.",
             "Parents paying tuition, families covering treatment in London, businesses paying European suppliers &mdash; the reverse corridor moves money from Nigeria, Kenya, Ghana and South Africa into GBP or EUR."),
            ("legacy", "reverse"),
            ("cards", "<h2>Common reasons people send to the UK</h2>", [
                {"title": "University &amp; school fees", "body": "Tuition and accommodation payments to UK institutions."},
                {"title": "Medical treatment", "body": "Covering hospital or specialist bills for family members in the UK or EU."},
                {"title": "Business payments", "body": "Paying UK and Eurozone suppliers, subscriptions and contractors."},
                {"title": "Family &amp; property", "body": "Supporting relatives abroad, mortgages and rent."},
            ]),
            ("prose", "<h2>How the reverse rail works</h2><ol><li>Fund locally &mdash; bank transfer in Nigeria and South Africa, M-Pesa in Kenya, MoMo in Ghana.</li>"
                      "<li>Funds convert to a regulated USD stablecoin (USDC) and move on a low-cost network.</li>"
                      "<li>The UK or EU recipient is paid in GBP (Faster Payments) or EUR (SEPA Instant).</li></ol>"
                      "<p>GBP and EUR settlement requires our UK payment-service-provider integration (Phase 2). Today the reverse corridor offers rate quotes and a waitlist. "
                      "Learn more in <a href=\"/learn/stablecoins-vs-bank-transfers\">stablecoins vs bank transfers</a>.</p>" + ILLUSTRATIVE, True),
        ],
    },
    {
        "path": "/wallet", "crumb": "Self-custody wallet",
        "title": "Self-Custody Crypto Wallet — Your Keys, Six Networks, Multi-Sig | Vaulted",
        "desc": "Vaulted's self-custody wallet generates your keys on your device, supports BTC, ETH, USDC on Polygon, Base and Arbitrum, SOL, XLM and XRP, and adds multi-signature approvals.",
        "blocks": [
            ("hero", "Self-custody wallet", "Your keys. Your money. <span class=\"gold-text\">Your device</span>.",
             "Vaulted is non-custodial: your private keys are generated and stored on your phone, protected by your biometrics, and never sent to our servers."),
            ("cards", "<h2>What&rsquo;s in the wallet</h2>", [
                {"title": "On-device keys", "body": "A BIP-39 12-word recovery phrase is created on your phone. We never see it and cannot recover it."},
                {"title": "Six networks", "body": "Bitcoin, Ethereum, USDC (Ethereum, Polygon, Base, Arbitrum), Solana, Stellar (XLM) and the XRP Ledger. One 0x address covers every EVM chain."},
                {"title": "Multi-signature approvals", "body": "Require a trusted co-signer &mdash; a partner, accountant or your second device &mdash; to approve large transactions."},
                {"title": "Biometric unlock", "body": "Face ID, Touch ID or Android biometrics guard the app and every send."},
                {"title": "Encrypted chat &amp; video", "body": "Message and call your recipient end-to-end encrypted, and send crypto inside the chat."},
                {"title": "Fiat-first when you want it", "body": "Prefer pounds? Fund remittances with card or bank and never hold crypto at all."},
            ]),
            ("prose", "<h2>Self-custody means responsibility</h2><p>Because Vaulted cannot access your keys, nobody &mdash; including us &mdash; can reset them. "
                      "Write your recovery phrase down offline and never share it. Our guide <a href=\"/learn/self-custody-wallet-safety\">keeping a self-custody wallet safe</a> walks through the essentials, "
                      "and the <a href=\"/security\">security page</a> explains the full model.</p>" + ILLUSTRATIVE, True),
        ],
    },
    {
        "path": "/security", "crumb": "Security",
        "title": "Security Model — On-Device Keys, End-to-End Encryption, Multi-Sig | Vaulted",
        "desc": "How Vaulted is engineered so funds stay safe even if our servers are compromised: on-device keys, XChaCha20-Poly1305 encryption, biometrics, multi-signature approvals and no password-based key recovery.",
        "blocks": [
            ("hero", "Security", "Built assuming our servers could be <span class=\"gold-text\">breached tomorrow</span>.",
             "Defence in depth: the parts that control your money live on your device, and the parts on our servers are designed to be useless to an attacker."),
            ("legacy", "security"),
            ("prose", "<h2>The model, layer by layer</h2>"
                      "<h3>1. Keys</h3><p>Private keys are derived from a BIP-39 recovery phrase generated on your device and stored in the phone&rsquo;s secure storage. They are never uploaded.</p>"
                      "<h3>2. Messages</h3><p>Chat is encrypted on-device with TweetNaCl (XChaCha20-Poly1305). Our servers relay ciphertext only.</p>"
                      "<h3>3. Approvals</h3><p>Large transactions can require a second signature from a co-signer, verified by email, before they move.</p>"
                      "<h3>4. Access</h3><p>Biometric device-level authentication protects the app; there is deliberately no password-based key recovery.</p>"
                      "<h3>5. Safety controls</h3><p>Users can report and block contacts in chat, and reports are reviewed by our team.</p>"
                      "<h2>What we can&rsquo;t see</h2><ul><li>Your recovery phrase or private keys.</li><li>The content of your encrypted messages.</li></ul>"
                      "<p>Found a vulnerability? Email <a href=\"mailto:support@phoenix-atlas.com\">support@phoenix-atlas.com</a>. See also <a href=\"/compliance\">compliance</a> and <a href=\"/wallet\">the wallet</a>.</p>", True),
        ],
    },
    {
        "path": "/corridors", "crumb": "Corridors",
        "title": "Remittance Corridors — Kenya, Ghana, Nigeria, Uganda, Tanzania, India & More | Vaulted",
        "desc": "Vaulted's planned payment corridors from the UK/EU to Kenya, Ghana, Tanzania, Zambia, Uganda, Nigeria, Senegal, Côte d'Ivoire, India, the Philippines and Mexico, plus the Africa-to-UK reverse corridor.",
        "blocks": [
            ("hero", "Payment corridors", "Eleven planned countries. <span class=\"gold-text\">Both directions</span>.",
             "Where Vaulted plans to send money, how recipients get paid, and where each corridor is in its rollout."),
            ("legacy", "corridors"),
            ("prose", "<h2>How corridors launch</h2><div class=\"stage\"><b>Sandbox</b> &mdash; rates and payouts tested with our off-ramp partners using test money.</div>"
                      "<div class=\"stage\"><b>Licensing &amp; partner go-live</b> &mdash; local partner approval and the applicable UK authorizations.</div>"
                      "<div class=\"stage\"><b>Live</b> &mdash; opened to waitlist members corridor by corridor.</div>"
                      "<p>Sending the other way? See <a href=\"/africa-to-uk\">Africa to UK &amp; EU</a>. Track our status on the <a href=\"/compliance\">compliance page</a>.</p>", True),
        ],
    },
    {
        "path": "/pricing", "crumb": "Pricing",
        "title": "Pricing — Free Tier, Vault Pro & How Vaulted Compares to Wise and Remitly",
        "desc": "Vaulted's planned launch pricing: a free tier with 3 cross-border sends per month and Vault Pro at £9.99/month, compared with Wise, Remitly and the crypto-exchange route for a £50 send.",
        "blocks": [
            ("hero", "Pricing", "Simple. Honest. <span class=\"gold-text\">Planned</span> in the open.",
             "Our launch pricing, and how it compares with the ways people send money today."),
            ("legacy", "pricing"),
            ("legacy", "compare"),
        ],
    },
    {
        "path": "/business", "crumb": "Business &amp; partners",
        "title": "For Payment Banks, PSPs & Partners — Stablecoin Remittance Infrastructure | Vaulted",
        "desc": "Partner with Phoenix-Atlas: white-label reverse-corridor remittance for African payment banks, stablecoin settlement between Africa and the UK/EU, and off-ramp partnerships.",
        "blocks": [
            ("hero", "Business &amp; partnerships", "Remittance rails for <span class=\"gold-text\">partners</span>.",
             "We work with payment banks, PSPs, off-ramp providers and mobile-money operators to move money between Africa and the UK/EU faster and cheaper than correspondent banking.", False),
            ("cards", "<h2>Ways to work with us</h2>", [
                {"title": "White-label reverse corridor", "body": "Offer your customers Africa-to-UK/EU payments under your brand, settled over stablecoin rails."},
                {"title": "Off-ramp &amp; payout partners", "body": "Mobile-money and bank-payout providers in our planned corridors."},
                {"title": "UK payment partners", "body": "PSPs and EMIs for GBP and EUR settlement (Faster Payments, SEPA Instant)."},
                {"title": "Stablecoin liquidity", "body": "Issuers and liquidity providers for USDC on low-cost networks."},
            ]),
            ("prose", "<h2 id=\"enquire\">Partner enquiry</h2><p>Tell us who you are and which corridor you&rsquo;re interested in &mdash; the founder replies personally.</p>"
                      "<form id=\"partner-form\" class=\"partner-form\" onsubmit=\"return handlePartnerEnquiry(event)\">"
                      "<div class=\"pf-row\"><input id=\"pf-name\" required maxlength=\"120\" placeholder=\"Your name\" aria-label=\"Your name\">"
                      "<input id=\"pf-email\" type=\"email\" required placeholder=\"Work email\" aria-label=\"Work email\"></div>"
                      "<div class=\"pf-row\"><input id=\"pf-company\" required maxlength=\"160\" placeholder=\"Company\" aria-label=\"Company\">"
                      "<select id=\"pf-type\" aria-label=\"Partner type\"><option value=\"payment_bank\">Payment bank</option><option value=\"psp_emi\">PSP / EMI</option>"
                      "<option value=\"offramp\">Off-ramp / payout provider</option><option value=\"mobile_money\">Mobile-money operator</option>"
                      "<option value=\"liquidity\">Stablecoin liquidity</option><option value=\"other\" selected>Other</option></select></div>"
                      "<input id=\"pf-corridor\" required maxlength=\"120\" placeholder=\"Corridor of interest, e.g. UK &rarr; Nigeria\" aria-label=\"Corridor\">"
                      "<textarea id=\"pf-message\" rows=\"4\" maxlength=\"2000\" placeholder=\"Anything else? (optional)\" aria-label=\"Message\"></textarea>"
                      "<input id=\"pf-website\" tabindex=\"-1\" autocomplete=\"off\" class=\"pf-hp\" aria-hidden=\"true\">"
                      "<button id=\"pf-btn\" class=\"btn btn-primary btn-large\" type=\"submit\">Send enquiry &rarr;</button>"
                      "<p id=\"pf-msg\" role=\"status\" aria-live=\"polite\"></p></form>", False),
            ("prose", "<h2>Talk to the founder</h2><p>A 20-minute call covers a live sandbox demo, the rail architecture and the fee waterfall on a real &pound;1,000 send.</p>"
                      "<p><a class=\"btn btn-primary btn-large\" href=\"#\" onclick=\"openBookingModal('business'); return false;\">Book a 20-min call &rarr;</a></p>"
                      "<p>Or email <a href=\"mailto:hello@phoenix-atlas.com\">hello@phoenix-atlas.com</a>. Investors, see <a href=\"/investors\">investor information</a>.</p>", True),
        ],
    },
    {
        "path": "/investors", "crumb": "Investors",
        "title": "Investors — Reverse-Corridor Unit Economics, Pitch Deck & Founder Call | Vaulted",
        "desc": "Investor information for Vaulted by Phoenix-Atlas Technologies: download the reverse-corridor one-pager or 5-page pitch deck and book a 20-minute call with the founder.",
        "blocks": [
            ("hero", "Investors", "The reverse-corridor <span class=\"gold-text\">opportunity</span>.",
             "Download the one-pager or the 5-page deck, watch the 3-minute explainer, or book a call with the founder.", False),
            ("legacy", "invest"),
            ("prose", "<p>Building due diligence? Our regulatory status and launch stages are on the <a href=\"/compliance\">compliance page</a>; partner opportunities are on <a href=\"/business\">business</a>.</p>"),
        ],
    },
    {
        "path": "/compliance", "crumb": "Compliance &amp; launch stages",
        "title": "Compliance, Regulatory Status & Launch Stages | Vaulted by Phoenix-Atlas",
        "desc": "Vaulted's regulatory status: Phoenix-Atlas Technologies Ltd (Company No. 17432346) is not yet FCA-authorized. See our launch stages, how we handle KYC and data, and our risk disclosures.",
        "blocks": [
            ("hero", "Compliance", "Where we are, <span class=\"gold-text\">honestly</span>.",
             "Vaulted is in build. This page sets out our regulatory status, what is and isn&rsquo;t live, and how we plan to launch.", False),
            ("prose", "<h2>Regulatory status</h2><p>Phoenix-Atlas Technologies Ltd is registered in England and Wales (Company No. 17432346). Vaulted is <strong>not currently authorized</strong> by the Financial Conduct Authority. "
                      "Cross-border money remittance, cryptoasset custody and cryptoasset exchange services will only be offered upon receipt of applicable authorizations. Nothing on this site is an offer of regulated services or investment advice.</p>"
                      "<h2>Launch stages</h2>"
                      "<div class=\"stage\"><b>Now &mdash; waitlist &amp; preview.</b> A preview app and closed beta use test money only. No customer transactions.</div>"
                      "<div class=\"stage\"><b>Sandbox corridors.</b> Payout partners are integrated in sandbox / test mode to validate rates and delivery.</div>"
                      "<div class=\"stage\"><b>Authorization &amp; partner go-live.</b> Applicable UK authorizations and local partner approvals, corridor by corridor.</div>"
                      "<div class=\"stage\"><b>Phase 2 &mdash; reverse settlement.</b> GBP/EUR payouts for the Africa-to-UK/EU corridor via a UK payment-service-provider integration.</div>"
                      "<h2>Identity checks &amp; data</h2><p>Live services will require identity verification (KYC) before money moves. We collect only what is needed to provide the service; see our <a href=\"/privacy\">privacy policy</a>. Private keys and encrypted messages are never accessible to us (<a href=\"/security\">security model</a>).</p>"
                      "<h2>Risk warning</h2><p>Don&rsquo;t invest unless you&rsquo;re prepared to lose all the money you invest. This is a high-risk investment and you should not expect to be protected if something goes wrong. Read the full <a href=\"/risk-disclosure\">risk disclosure</a>.</p>"),
        ],
    },
    {
        "path": "/faq", "crumb": "FAQ",
        "title": "FAQ — Cross-Border Payments, Stablecoins & Self-Custody | Vaulted",
        "desc": "Answers to common questions about Vaulted: is it live, how stablecoin remittance works, do I need crypto, which countries, fees, self-custody and security.",
        "blocks": [
            ("hero", "FAQ", "Questions, <span class=\"gold-text\">answered</span>.", "The things people ask us most about Vaulted, cross-border payments and self-custody.", False),
            ("faq",),
        ],
    },
]

FAQ = [
    ("Is Vaulted live?", "Not yet. Vaulted is in waitlist and preview mode ahead of FCA authorization and is not open for customer transactions. A preview app and closed beta use test money only. See <a href=\"/compliance\">compliance &amp; launch stages</a>."),
    ("Who is behind Vaulted?", "Vaulted is built by Phoenix-Atlas Technologies Ltd, a company registered in England and Wales (Company No. 17432346)."),
    ("Do I need to own crypto to send money?", "No. Vaulted is designed to be fiat-first: fund with a card, Apple Pay, Google Pay or bank transfer and your recipient receives local currency. The stablecoin rail runs in the background."),
    ("How does stablecoin remittance work?", "Your pounds are converted to a regulated USD stablecoin (USDC), moved on a low-cost network such as Stellar, the XRP Ledger or a USDC layer-2, then converted to local currency and paid out to mobile money or a bank account. Read <a href=\"/learn/stablecoins-vs-bank-transfers\">stablecoins vs bank transfers</a>."),
    ("Which countries will Vaulted support?", "Planned destinations are Kenya, Ghana, Tanzania, Zambia, Uganda, Nigeria, Senegal, Côte d&rsquo;Ivoire, India, the Philippines and Mexico, plus a reverse corridor from Nigeria, Kenya, Ghana and South Africa to the UK and EU. See <a href=\"/corridors\">corridors</a>."),
    ("Can I send money from Africa to the UK?", "Yes, that is the reverse corridor &mdash; designed for school fees, medical bills and business payments into GBP or EUR. Rate quotes and a waitlist are available now; GBP/EUR settlement is planned for Phase 2. See <a href=\"/africa-to-uk\">Africa to UK &amp; EU</a>."),
    ("How much will it cost?", "Planned launch pricing is a free tier with 3 cross-border sends per month at a 1.5% service fee (minimum £0.50, maximum £9.99), or Vault Pro at £9.99/month with 50% off fees. See <a href=\"/pricing\">pricing</a>."),
    ("What does self-custody mean?", "Your private keys are generated and stored on your device, not by us. That means nobody else can move your funds &mdash; and nobody, including Vaulted, can recover your recovery phrase if you lose it. Read <a href=\"/learn/self-custody-wallet-safety\">keeping a self-custody wallet safe</a>."),
    ("Is my chat really private?", "Messages are encrypted on your device with TweetNaCl (XChaCha20-Poly1305); our servers only relay ciphertext."),
    ("How do I join?", "Use the waitlist form at the bottom of any page. We&rsquo;ll email you once authorized services open in your corridor."),
]

_REL = {
    "send": {"title": "Send money to Africa", "body": "How Vaulted plans to pay M-Pesa, mobile money and banks.", "href": "/send-money-to-africa"},
    "rev": {"title": "Africa to UK &amp; EU", "body": "The reverse corridor for tuition and medical bills.", "href": "/africa-to-uk"},
    "wallet": {"title": "Self-custody wallet", "body": "On-device keys, six networks, multi-sig.", "href": "/wallet"},
    "sec": {"title": "Security model", "body": "What we protect and what we can&rsquo;t see.", "href": "/security"},
    "faq": {"title": "FAQ", "body": "Quick answers about Vaulted.", "href": "/faq"},
}

GUIDES = [
    {
        "slug": "send-money-uk-to-nigeria-kenya", "short": "UK to Nigeria &amp; Kenya", "published": "2026-06-20",
        "title": "How to send money from the UK to Nigeria and Kenya",
        "seo_title": "How to Send Money from the UK to Nigeria and Kenya (2026 Guide) | Vaulted",
        "desc": "The main ways to send money from the UK to Nigeria and Kenya, what to compare (fees, exchange rate, speed, payout method) and the details your recipient needs.",
        "html": "<h2>Your main options</h2><ul>"
                "<li><strong>Bank wire (SWIFT).</strong> Widely available but often the slowest and most expensive route, with fees taken by intermediary banks and a marked-up exchange rate.</li>"
                "<li><strong>Money-transfer apps.</strong> Specialist providers usually beat banks on price and speed; costs vary by corridor and payout method.</li>"
                "<li><strong>Mobile money.</strong> In Kenya, M-Pesa is the most common way to receive money &mdash; funds land on the recipient&rsquo;s phone.</li>"
                "<li><strong>Stablecoin rails.</strong> Newer services convert pounds to a dollar stablecoin, move it on a blockchain network and pay out local currency. This is the approach Vaulted is building.</li></ul>"
                "<h2>What to compare before you send</h2><ol><li><strong>Total cost</strong> &mdash; the fee <em>and</em> the exchange-rate margin. Compare what the recipient actually receives.</li>"
                "<li><strong>Speed</strong> &mdash; seconds, minutes or days.</li><li><strong>Payout method</strong> &mdash; bank account, mobile money or cash pickup.</li>"
                "<li><strong>Regulation</strong> &mdash; check the provider is authorized to offer money transfers in the UK.</li></ol>"
                "<h2>Details your recipient needs to give you</h2><h3>Nigeria</h3><ul><li>Their 10-digit bank account number (NUBAN) and bank name.</li><li>Their full name exactly as on the account &mdash; good providers confirm it before you pay.</li></ul>"
                "<h3>Kenya</h3><ul><li>Their M-Pesa-registered phone number (format 2547XXXXXXXX), or bank details.</li><li>Their full name as registered with M-Pesa.</li></ul>"
                "<h2>Stay safe</h2><ul><li>Only send to people you know. Scammers often pose as relatives or romantic partners.</li><li>Double-check numbers &mdash; transfers are hard to reverse.</li><li>Keep the receipt and reference.</li></ul>"
                "<h2>Where Vaulted fits</h2><p>Vaulted is designed to take pounds by card or bank and pay Nigerian bank accounts and Kenyan M-Pesa wallets in seconds, with the account name checked first. It is not live yet &mdash; <a href=\"#waitlist\">join the waitlist</a>.</p>",
        "related": [_REL["send"], _REL["faq"], {"title": "Stablecoins vs bank transfers", "body": "How the new rails compare.", "href": "/learn/stablecoins-vs-bank-transfers"}],
    },
    {
        "slug": "stablecoins-vs-bank-transfers", "short": "Stablecoins vs banks", "published": "2026-06-20",
        "title": "Stablecoins vs bank transfers for cross-border payments",
        "seo_title": "Stablecoins vs Bank Transfers for International Payments, Explained | Vaulted",
        "desc": "What stablecoins are, how a stablecoin remittance rail works compared with SWIFT correspondent banking, and the benefits and risks to understand.",
        "html": "<h2>What is a stablecoin?</h2><p>A stablecoin is a digital token designed to hold a steady value, usually one US dollar. Regulated stablecoins such as USDC are issued by companies that hold reserves backing each token.</p>"
                "<h2>How a traditional international transfer works</h2><p>A bank wire typically travels through the SWIFT messaging network and one or more <strong>correspondent banks</strong>. Each hop can add fees and time, and transfers often only move during banking hours.</p>"
                "<h2>How a stablecoin rail works</h2><ol><li><strong>On-ramp:</strong> your pounds (or naira, shillings, cedis) are converted to a stablecoin.</li>"
                "<li><strong>Transfer:</strong> the stablecoin moves on a blockchain network, 24/7, typically settling in seconds to minutes.</li>"
                "<li><strong>Off-ramp:</strong> a local partner converts it to the recipient&rsquo;s currency and pays their bank or mobile-money wallet.</li></ol>"
                "<p>With a fiat-first app, the sender and recipient only ever see their own currencies.</p>"
                "<h2>Potential benefits</h2><ul><li>Faster settlement, including evenings and weekends.</li><li>Fewer intermediaries, which can mean lower costs.</li><li>Transparent, traceable movement on-chain.</li></ul>"
                "<h2>Risks to understand</h2><ul><li><strong>Stablecoin risk:</strong> a token can lose its peg if reserves or the issuer fail.</li><li><strong>Partner risk:</strong> on- and off-ramp partners must be reliable and licensed.</li>"
                "<li><strong>Regulation:</strong> rules for cryptoassets and payments are evolving; in the UK, cryptoasset promotions carry FCA risk warnings.</li><li>Cryptoassets held in your own wallet are generally not covered by deposit protection.</li></ul>"
                "<h2>How Vaulted uses stablecoins</h2><p>Vaulted plans to route payments over USDC and low-cost networks such as Stellar, the XRP Ledger, Polygon, Base and Arbitrum, choosing the cheapest route automatically. See <a href=\"/corridors\">corridors</a> and <a href=\"/africa-to-uk\">the reverse corridor</a>.</p>",
        "related": [_REL["rev"], _REL["send"], _REL["faq"]],
    },
    {
        "slug": "self-custody-wallet-safety", "short": "Self-custody safety", "published": "2026-06-20",
        "title": "Keeping a self-custody wallet safe: a practical checklist",
        "seo_title": "Self-Custody Crypto Wallet Safety Checklist — Recovery Phrases, Multi-Sig & Scams | Vaulted",
        "desc": "What self-custody means, how to protect your recovery phrase, when to use biometrics and multi-signature approvals, and how to spot common wallet scams.",
        "html": "<h2>What self-custody means</h2><p>In a self-custody (non-custodial) wallet, <strong>you</strong> hold the private keys. No company can freeze or move your funds &mdash; but no company can recover them for you either.</p>"
                "<h2>Your recovery phrase</h2><ul><li>Write the 12 (or 24) words on paper, in order, and store them somewhere safe and private. Consider a second copy in a different location.</li>"
                "<li>Never photograph it, store it in cloud notes or email, or type it into a website.</li><li>Anyone with the phrase controls the wallet. Nobody legitimate will ever ask for it &mdash; including Vaulted.</li></ul>"
                "<h2>Lock the device and the app</h2><ul><li>Use a strong device passcode and enable biometric unlock (Face ID, Touch ID or Android biometrics).</li><li>Keep your phone&rsquo;s operating system and the wallet app updated.</li></ul>"
                "<h2>Use multi-signature for large amounts</h2><p>Multi-signature (multi-sig) requires a second approval before a transaction moves &mdash; from a trusted person or your own second device. It protects against a single stolen phone or a rushed mistake.</p>"
                "<h2>Spot the common scams</h2><ul><li><strong>Fake support:</strong> &ldquo;support agents&rdquo; who message you first and ask for your phrase.</li><li><strong>Phishing links:</strong> lookalike websites and apps &mdash; download only from official stores.</li>"
                "<li><strong>Address swaps:</strong> always check the first and last characters of a pasted address.</li><li><strong>Too-good-to-be-true returns:</strong> guaranteed profits are a red flag.</li></ul>"
                "<h2>Checklist</h2><ol><li>Recovery phrase written down offline.</li><li>Device passcode + biometrics on.</li><li>Multi-sig for large balances.</li><li>Test with a small amount first.</li><li>Never share your phrase.</li></ol>"
                "<p>See how Vaulted applies these principles on the <a href=\"/security\">security page</a>.</p>",
        "related": [_REL["wallet"], _REL["sec"], _REL["faq"]],
    },
]
