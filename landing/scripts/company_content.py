"""Company-level pages for phoenix-atlas.com (Phoenix-Atlas Technologies Ltd).

Vaulted product pages live in site_content.py. Each block is rendered by build_site.py:
  ("hero", eyebrow, h1, sub, ctas)  ctas = [(label, href, primary?)] or False
  ("prose", html[, bg])  ("cards", intro_html, [card...][, bg])  ("form", kind)
"""

TAGLINE = "Building Technology. Connecting Possibilities. Creating Impact."

COMPANY_NAV = [
    ("About", "/about"), ("What we do", "/what-we-do"), ("Products", "/products"),
    ("Our approach", "/approach"), ("Investors", "/investors"), ("Contact", "/contact"),
]

VAULTED_NAV = [
    ("Overview", "/vaulted"), ("Send money", "/send-money-to-africa"), ("Africa &rarr; UK", "/africa-to-uk"),
    ("Wallet", "/wallet"), ("Security", "/security"), ("Corridors", "/corridors"), ("Pricing", "/pricing"),
    ("Business", "/business"), ("Learn", "/learn"), ("FAQ", "/faq"),
]

SERVICES = [
    {"id": "software", "title": "Software Development &amp; Digital Solutions",
     "short": "Software-led solutions designed around practical business requirements and real-world user needs.",
     "html": "<p>We develop software-led solutions designed around practical business requirements and real-world user needs.</p>"
             "<p>Our approach encompasses the conception, design, development and evolution of digital products, applications and platforms. "
             "We place particular emphasis on usability, functionality, scalability, security and the ability of technology to deliver measurable value.</p>"
             "<p>From initial concepts to production-ready applications, we believe successful software development begins with understanding "
             "the problem before determining the technology required to solve it.</p>"},
    {"id": "product-innovation", "title": "Digital Product Innovation",
     "short": "Identifying where technology can challenge conventional approaches and deliver better outcomes.",
     "html": "<p>We identify opportunities where technology can challenge conventional approaches and deliver better outcomes.</p>"
             "<p>Through research, product strategy, development and continuous improvement, we work towards building digital products "
             "that combine practical functionality with accessible user experiences.</p>"
             "<p>Our product development philosophy is centred on solving problems rather than simply creating technology for its own sake.</p>"},
    {"id": "fintech", "title": "Financial Technology &amp; Digital Financial Services",
     "short": "Using emerging technology and new payment infrastructure to widen access and reduce cross-border friction.",
     "html": "<p>Financial technology is an important area of our innovation strategy.</p>"
             "<p>We are particularly interested in how emerging technologies, digital payment infrastructure and new financial models can "
             "improve access to financial services, reduce friction in cross-border transactions and create more efficient ways for people "
             "to move and manage value.</p>"
             "<p>Our work in this area explores opportunities to make financial services more inclusive, transparent and accessible, "
             "particularly across international markets.</p>"},
    {"id": "connected", "title": "Connected Digital Experiences",
     "short": "Bringing capabilities together in coherent digital environments that reduce fragmentation.",
     "html": "<p>We recognise that the future of digital services is increasingly interconnected.</p>"
             "<p>We are interested in developing solutions that bring together different capabilities within coherent digital environments, "
             "reducing fragmentation and creating more seamless experiences for users.</p>"
             "<p>This includes exploring the convergence of financial services, communication technologies, digital identity and other "
             "emerging applications.</p>"},
]

PRINCIPLES = [
    ("Innovation with Purpose", "We pursue innovation that addresses identifiable challenges and creates practical value. We are less "
     "interested in technology for its own sake than in what technology makes possible."),
    ("User-Centred Design", "Technology should be intuitive and accessible. We place the user experience at the centre of product thinking, "
     "ensuring that complexity behind the scenes does not translate into unnecessary complexity for the user."),
    ("Security and Trust", "Trust is fundamental to the adoption of digital technology. We recognise the importance of security, privacy, "
     "responsible data practices and robust technology architecture in developing products that people can depend on."),
    ("Scalability and Sustainability", "We seek to build solutions with the flexibility to evolve, adapt and scale as user requirements, "
     "markets and technologies change."),
    ("Continuous Improvement", "Technology never stands still. We embrace continuous learning, development and refinement, recognising that "
     "meaningful innovation is an ongoing process rather than a single achievement."),
]

PRODUCTS = [
    {"title": "Vaulted &mdash; Reimagining Cross-Border Payments", "href": "/vaulted", "cta": "Explore Vaulted",
     "body": "Making international money transfers simpler, more accessible and more cost-effective &mdash; a fiat-first remittance "
             "experience built on self-custody digital asset infrastructure."},
    {"title": "CareFlow &mdash; Turning Financial Support into Meaningful Outcomes", "href": "/careflow", "cta": "Discover CareFlow",
     "body": "An outcome-based payment and family-support platform, starting with healthcare. Don&rsquo;t just send money. Send the help."},
]

STATUS_NOTE = ('<p style="font-size:13px;color:var(--text-muted)">Vaulted and CareFlow are currently at different stages of product '
               'development and are not yet publicly available. Further information will be published as their respective development progresses.</p>')

CLOSING = ("prose", f'<div style="text-align:center"><h2>Great ideas deserve the right technology to bring them to life.</h2>'
                    f'<p>Whether you are a partner, investor or simply curious about what we are building, we&rsquo;d like to hear from you.</p>'
                    f'<p style="margin-top:24px"><a class="btn btn-primary btn-large" href="/contact">Get in touch &rarr;</a></p></div>', True)


def _principle_cards(link=False):
    return [{"title": t, "body": b, **({"href": "/approach", "cta": "Our approach"} if link else {})} for t, b in PRINCIPLES]


COMPANY_PAGES = [
    {
        "path": "/", "crumb": "Home",
        "title": "Phoenix-Atlas Technologies — Software, Digital Products &amp; Fintech Innovation",
        "desc": "Phoenix-Atlas Technologies Ltd is a UK technology and software innovation company designing intelligent digital solutions, "
                "including Vaulted (cross-border payments) and CareFlow (outcome-based family support).",
        "ld": [{"@context": "https://schema.org", "@type": "WebSite", "name": "Phoenix-Atlas Technologies", "url": "https://www.phoenix-atlas.com/"}],
        "blocks": [
            ("hero", "Phoenix-Atlas Technologies Ltd",
             'Building Technology. <span class="gold-text">Connecting Possibilities.</span> Creating Impact.',
             "A technology and software innovation company designing, developing and delivering intelligent digital solutions that "
             "address real-world challenges and create meaningful value.",
             [("Explore our products", "/products", True), ("Get in touch", "/contact", False)]),
            ("prose", "<h2>Who we are</h2><p>We believe technology should do more than make processes faster or more convenient. It should "
                      "remove barriers, connect people, simplify complex experiences and create opportunities that were previously difficult to access.</p>"
                      "<p>At Phoenix-Atlas, we bring together software development, digital innovation, product strategy and an understanding of "
                      "emerging technologies to transform ideas into practical digital solutions &mdash; with a global outlook and an innovation-led mindset.</p>"
                      '<p><a href="/about">More about us &rarr;</a></p>'),
            ("cards", "<h2>What we do</h2><p>Our activities centre on technology development, digital product innovation and software-driven solutions.</p>",
             [{"title": s["title"], "body": s["short"], "href": f"/what-we-do#{s['id']}"} for s in SERVICES], True),
            ("cards", "<h2>Our products</h2><p>Each product is conceived around a specific challenge &mdash; an opportunity to rethink how an existing service is delivered.</p>",
             PRODUCTS),
            ("cards", "<h2>How we approach technology</h2><p>Good technology is built on a clear understanding of people, problems and possibilities.</p>",
             _principle_cards(link=True), True),
            CLOSING,
        ],
    },
    {
        "path": "/about", "crumb": "About us",
        "title": "About Phoenix-Atlas Technologies Ltd — Who We Are, Vision &amp; Mission",
        "desc": "Who Phoenix-Atlas Technologies is, our vision to become a globally recognised technology company, and our mission to solve meaningful problems with software.",
        "blocks": [
            ("hero", "About us", f'Building Technology. <span class="gold-text">Connecting Possibilities.</span> Creating Impact.',
             "A technology and software innovation company with a global outlook and a commitment to products that solve meaningful problems.", False),
            ("prose", "<h2>Who we are</h2>"
                      "<p>Phoenix-Atlas Technologies Ltd is a technology and software innovation company focused on designing, developing and "
                      "delivering intelligent digital solutions that address real-world challenges and create meaningful value.</p>"
                      "<p>We believe technology should do more than make processes faster or more convenient. It should remove barriers, connect "
                      "people, simplify complex experiences and create opportunities that were previously difficult to access.</p>"
                      "<p>Our work is driven by the belief that some of the world&rsquo;s most persistent challenges require more than incremental "
                      "improvements. They require fresh thinking, purposeful innovation and technology designed around the needs of the people who use it.</p>"
                      "<p>At Phoenix-Atlas, we bring together software development, digital innovation, product strategy and an understanding of "
                      "emerging technologies to explore new possibilities and transform ideas into practical digital solutions.</p>"
                      "<p>We are building a technology business with a global outlook, an innovation-led mindset and a commitment to developing "
                      "products that solve meaningful problems.</p>"),
            ("prose", "<h2>Our vision</h2>"
                      "<p>To become a globally recognised technology company, developing innovative digital solutions that make everyday experiences "
                      "more accessible, connected, efficient and impactful.</p>"
                      "<p>We aspire to build technology that not only responds to today&rsquo;s challenges but also anticipates the opportunities of tomorrow.</p>"
                      "<h2>Our mission</h2>"
                      "<p>Our mission is to harness software, technology and innovation to solve meaningful problems, simplify complex processes and "
                      "create accessible digital experiences. We aim to achieve this by:</p><ul>"
                      "<li>Developing technology-driven products that address genuine market and societal needs.</li>"
                      "<li>Making complex technologies simpler, more accessible and intuitive.</li>"
                      "<li>Building secure, scalable and user-focused digital platforms.</li>"
                      "<li>Exploring emerging technologies and new business models to unlock opportunities.</li>"
                      "<li>Creating solutions that connect people, businesses and services across geographical and digital boundaries.</li></ul>", True),
            ("prose", "<h2>Looking ahead</h2>"
                      "<p>Phoenix-Atlas Technologies Ltd is an evolving technology business with ambitions that extend beyond individual products.</p>"
                      "<p>As we continue to develop our software capabilities and product portfolio, our focus remains on creating solutions that "
                      "combine innovation, accessibility, security and practical value.</p>"
                      "<p>We are committed to exploring new opportunities, embracing emerging technologies and building products that can contribute "
                      "to a more connected and digitally enabled world.</p>"
                      "<p><strong>We believe great ideas deserve the right technology to bring them to life.</strong></p>"),
            ("cards", "<h2>Explore further</h2>", [
                {"title": "What we do", "body": "Our four areas of technology development and innovation.", "href": "/what-we-do"},
                {"title": "Our products", "body": "Vaulted and CareFlow &mdash; the challenges each one sets out to solve.", "href": "/products"},
                {"title": "Our approach", "body": "The five principles that guide how we build.", "href": "/approach"},
            ], True),
        ],
    },
    {
        "path": "/what-we-do", "crumb": "What we do",
        "title": "What We Do — Software Development, Product Innovation &amp; Fintech | Phoenix-Atlas",
        "desc": "Phoenix-Atlas works across software development and digital solutions, digital product innovation, financial technology and connected digital experiences.",
        "blocks": [
            ("hero", "What we do", 'Technology development with a <span class="gold-text">purpose</span>.',
             "Our activities centre on technology development, digital product innovation and the creation of software-driven solutions.", False),
            *[("prose", f'<h2 id="{s["id"]}">{i + 1}. {s["title"]}</h2>{s["html"]}', i % 2 == 1) for i, s in enumerate(SERVICES)],
            ("cards", "<h2>See it in practice</h2><p>Our product portfolio puts these capabilities to work.</p>", PRODUCTS, True),
        ],
    },
    {
        "path": "/products", "crumb": "Products",
        "title": "Our Products — Vaulted &amp; CareFlow | Phoenix-Atlas Technologies",
        "desc": "The Phoenix-Atlas product portfolio: Vaulted, reimagining cross-border payments, and CareFlow, outcome-based payments for family healthcare support.",
        "blocks": [
            ("hero", "Our product portfolio", 'Products built around <span class="gold-text">real challenges</span>.',
             "Our products are conceived and developed around specific challenges, with each product representing an opportunity to rethink "
             "how existing services are delivered.", False),
            ("prose", '<h2 id="vaulted">Vaulted &mdash; Reimagining Cross-Border Payments</h2>'
                      "<p>Vaulted is a fintech product initiative focused on making international money transfers simpler, more accessible and more cost-effective.</p>"
                      "<p>Its vision is to transform self-custody digital asset infrastructure into a familiar, fiat-first remittance experience, allowing "
                      "users to send money internationally without needing to navigate the underlying complexity of cryptocurrency.</p>"
                      "<p>By bringing together self-custody, digital asset infrastructure, cross-border payments and encrypted communication, Vaulted "
                      "seeks to create a more integrated approach to international financial connectivity.</p>"
                      "<p>Our ambition is to make the benefits of modern financial technology accessible without requiring users to become experts in the "
                      "technology powering it.</p>"
                      '<p style="margin-top:24px"><a class="btn btn-primary" href="/vaulted">Explore Vaulted &rarr;</a></p>'),
            ("prose", '<h2 id="careflow">CareFlow &mdash; Turning Financial Support into Meaningful Outcomes</h2>'
                      "<p>CareFlow is an emerging outcome-based payment and family-support platform being developed to address a different dimension "
                      "of international money transfers.</p>"
                      "<p>Its initial focus is on healthcare-related payments, particularly enabling people living abroad to support the healthcare needs "
                      "of family members back home.</p>"
                      "<p>Rather than focusing exclusively on transferring money, CareFlow explores a more outcome-oriented approach to financial support: "
                      "connecting the sender&rsquo;s intention with the actual service or assistance the recipient needs.</p>"
                      '<p style="font-family:\'Cormorant Garamond\',serif;font-size:26px;color:var(--gold-cream)">Don&rsquo;t just send money. Send the help.</p>'
                      '<p style="margin-top:24px"><a class="btn btn-primary" href="/careflow">Discover CareFlow &rarr;</a></p>' + STATUS_NOTE, True),
        ],
    },
    {
        "path": "/careflow", "crumb": "CareFlow",
        "title": "CareFlow — Don’t Just Send Money. Send the Help. | Phoenix-Atlas",
        "desc": "CareFlow is an emerging outcome-based payment and family-support platform helping people abroad pay for the healthcare needs of family back home. Register early interest.",
        "parent": ("Products", "/products"),
        "blocks": [
            ("hero", "CareFlow &middot; In development", 'Don&rsquo;t just send money. <span class="gold-text">Send the help.</span>',
             "An outcome-based payment and family-support platform, starting with healthcare &mdash; connecting what a sender intends with the "
             "care their family actually receives.", [("Register early interest", "#careflow-interest", True), ("All products", "/products", False)]),
            ("prose", "<h2>Turning financial support into meaningful outcomes</h2>"
                      "<p>CareFlow is being developed to address a different dimension of international money transfers. Its initial focus is on "
                      "healthcare-related payments, particularly enabling people living abroad to support the healthcare needs of family members back home.</p>"
                      "<p>Rather than focusing exclusively on transferring money, CareFlow explores a more outcome-oriented approach to financial support: "
                      "connecting the sender&rsquo;s intention with the actual service or assistance the recipient needs.</p>"
                      "<p>Through this approach, CareFlow aims to explore how technology can bring greater transparency, accountability and purpose to "
                      "international family support.</p>"),
            ("cards", "<h2>What CareFlow sets out to bring</h2>", [
                {"title": "Transparency", "body": "Senders can see where their support goes &mdash; to the clinic, the pharmacy or the treatment itself."},
                {"title": "Accountability", "body": "Support tied to a real service or outcome, rather than cash with no visibility."},
                {"title": "Purpose", "body": "Intention and outcome connected, so help arrives as the help it was meant to be."},
            ], True),
            ("form", "careflow"),
        ],
    },
    {
        "path": "/approach", "crumb": "Our approach",
        "title": "Our Approach to Technology — Principles &amp; Perspective | Phoenix-Atlas",
        "desc": "The five principles behind Phoenix-Atlas: innovation with purpose, user-centred design, security and trust, scalability and sustainability, and continuous improvement.",
        "blocks": [
            ("hero", "How we approach technology", 'People, problems <span class="gold-text">and possibilities</span>.',
             "At Phoenix-Atlas, we believe good technology is built on a clear understanding of people, problems and possibilities. "
             "Our development philosophy is guided by five principles.", False),
            ("cards", "<h2>Our five principles</h2>", _principle_cards()),
            ("prose", "<h2>Our perspective</h2>"
                      "<p>We see a world where technology increasingly removes the boundaries between people, services and opportunities.</p>"
                      "<p>Yet many everyday processes remain unnecessarily complicated, fragmented or inaccessible. Whether in financial services, "
                      "international payments, healthcare support or digital communication, there are opportunities to rethink how things work.</p>"
                      "<p>We believe the next generation of impactful technology companies will be those that combine technical capability with a "
                      "genuine understanding of human needs.</p>"
                      "<p><strong>That is the thinking behind Phoenix-Atlas.</strong></p>"
                      "<p>We are building with a long-term perspective: identifying meaningful problems, developing purposeful technology and creating "
                      "digital solutions with the potential to make a difference across markets and communities.</p>", True),
            CLOSING,
        ],
    },
    {
        "path": "/contact", "crumb": "Contact",
        "title": "Contact Phoenix-Atlas Technologies Ltd",
        "desc": "Get in touch with Phoenix-Atlas Technologies Ltd about partnerships, investment, Vaulted, CareFlow or general enquiries.",
        "blocks": [
            ("hero", "Contact", 'Let&rsquo;s <span class="gold-text">talk</span>.',
             "Partnerships, investment, press or a question about Vaulted or CareFlow &mdash; send us a message and we&rsquo;ll reply within 2 working days.", False),
            ("form", "contact"),
            ("prose", "<h2>Other ways to reach us</h2><ul>"
                      '<li>General: <a href="mailto:hello@phoenix-atlas.com">hello@phoenix-atlas.com</a></li>'
                      '<li>Investors: <a href="mailto:invest@phoenix-atlas.com">invest@phoenix-atlas.com</a></li>'
                      '<li>Vaulted app support: <a href="mailto:support@phoenix-atlas.com">support@phoenix-atlas.com</a></li>'
                      '<li>Payment partners: <a href="/business">Vaulted business &amp; partners</a></li></ul>'
                      "<p>Phoenix-Atlas Technologies Ltd is registered in England and Wales, Company No. 17432346.</p>", True),
        ],
    },
]
