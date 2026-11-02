"""Build the multi-page phoenix-atlas.com marketing site.

Source of truth for the original one-page copy, CSS and form scripts:
    /app/landing/src/legacy.html
New page copy lives in /app/landing/scripts/site_content.py.

Run:  python /app/landing/scripts/build_site.py
Outputs: index.html + one .html per page, learn/*.html, assets/styles.css,
assets/site.js, sitemap.xml, robots.txt, llms.txt (Vercel cleanUrls serves
/wallet.html as /wallet).
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from site_content import FAQ, GUIDES, PAGES, SITE, NAV

ROOT = Path(__file__).resolve().parent.parent
LEGACY = (ROOT / "src" / "legacy.html").read_text()
TODAY = date.today().isoformat()

# ---------------------------------------------------------------- extraction
CSS = LEGACY[LEGACY.index("<style>") + 7: LEGACY.index("</style>")]
MODAL_CSS = re.search(r"<style>\s*@keyframes bookModalIn.*?</style>", LEGACY, re.S).group(0)
MODAL_HTML = LEGACY[LEGACY.index('<div id="book-modal"'): LEGACY.index(MODAL_CSS)].strip()
SCRIPTS = re.findall(r"<script>(.*?)</script>", LEGACY, re.S)
JS_WAITLIST = next(s for s in SCRIPTS if "var WAITLIST_API_BASE =" in s)
JS_INVESTOR = next(s for s in SCRIPTS if "handleInvestor" in s)
JS_MODAL = next(s for s in SCRIPTS if "VAULTED_BOOK_URL" in s)
_SECTIONS = re.findall(r"<section\b.*?</section>", LEGACY, re.S)

LINK_MAP = {
    "#corridors": "/corridors", "#reverse": "/africa-to-uk", "#features": "/send-money-to-africa#features",
    "#who-its-for": "/send-money-to-africa#who-its-for", "#compare": "/pricing#compare",
    "#pricing": "/pricing", "#security": "/security", "#invest": "/investors#invest",
}


def legacy_section(marker: str) -> str:
    """Return an original <section> (by id or by a phrase it contains), with
    old one-page anchors rewritten to the new page URLs."""
    sec = next((s for s in _SECTIONS if f'id="{marker}"' in s.split(">", 1)[0]), None) \
        or next(s for s in _SECTIONS if marker in s)
    for old, new in LINK_MAP.items():
        sec = sec.replace(f'href="{old}"', f'href="{new}"')
    return sec


EXTRA_CSS = """
/* ---- Multi-page additions (build_site.py) ---- */
.brand { display: flex; align-items: center; gap: 10px; text-decoration: none; }
.brand img { width: 36px; height: 36px; border-radius: 9px; }
.nav-links { gap: 20px; }
.nav-links a { font-size: 13px; white-space: nowrap; }
.wordmark-tag { white-space: nowrap; }
@media (max-width: 1280px) { .brand .wordmark-tag { display: none !important; } .nav-links { gap: 16px; } }
.nav-links a[aria-current="page"] { color: var(--gold-light); }
.menu-toggle { display: none; background: none; border: 1px solid var(--border); color: var(--gold-cream);
  border-radius: 10px; width: 44px; height: 44px; font-size: 20px; cursor: pointer; }
.mobile-menu { display: none; }
@media (max-width: 1180px) {
  .nav-links a:not(.btn) { display: none; }
  .menu-toggle { display: inline-flex; align-items: center; justify-content: center; }
  body.menu-open .mobile-menu { display: block; position: fixed; left: 0; right: 0; bottom: 0;
    z-index: 99; background: var(--bg); overflow-y: auto; padding: 16px 24px 40px; border-top: 1px solid var(--border); }
  .mobile-menu a { display: block; padding: 14px 4px; color: var(--text-primary); text-decoration: none;
    font-size: 17px; border-bottom: 1px solid var(--border); }
  .mobile-menu a[aria-current="page"] { color: var(--gold-light); }
  .mobile-menu .btn { margin-top: 20px; width: 100%; border-bottom: none; }
}
@media (max-width: 480px) { .nav-links .btn-launch { display: none; } }
.page-hero { padding: 120px 0 64px; }
.page-hero h1 { font-size: clamp(36px, 5.5vw, 60px); }
.crumbs { font-size: 12px; color: var(--text-muted); margin-bottom: 18px; position: relative; z-index: 1; }
.crumbs a { color: var(--text-secondary); text-decoration: none; }
.crumbs a:hover { color: var(--gold-light); }
.prose { max-width: 780px; margin: 0 auto; }
.prose h2 { font-family: 'Cormorant Garamond', serif; font-weight: 600; font-size: clamp(28px, 4vw, 40px);
  line-height: 1.15; margin: 48px 0 16px; color: var(--gold-cream); }
.prose h2:first-child { margin-top: 0; }
.prose h3 { font-size: 18px; margin: 28px 0 10px; color: var(--gold-light); }
.prose p, .prose li { color: var(--text-secondary); font-size: 16px; margin-bottom: 14px; }
.prose ul, .prose ol { padding-left: 22px; margin-bottom: 18px; }
.prose a { color: var(--gold-light); }
.prose strong { color: var(--text-primary); }
.card-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 18px; margin-top: 32px; }
.info-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 18px; padding: 24px;
  text-decoration: none; color: inherit; display: block; }
a.info-card:hover { border-color: rgba(201,163,91,0.5); }
.info-card h3 { font-size: 17px; color: var(--gold-cream); margin-bottom: 8px; }
.info-card p { font-size: 14px; color: var(--text-secondary); margin: 0; }
.info-card .more { display: inline-block; margin-top: 12px; color: var(--gold-light); font-size: 13px; font-weight: 600; }
.stage { border-left: 2px solid var(--gold); padding: 4px 0 4px 18px; margin: 18px 0; }
.stage b { color: var(--gold-light); }
.faq-item { border-bottom: 1px solid var(--border); padding: 18px 0; }
.faq-item summary { cursor: pointer; font-weight: 600; color: var(--text-primary); font-size: 16px; list-style: none; }
.faq-item summary::after { content: '+'; float: right; color: var(--gold); }
.faq-item[open] summary::after { content: '\\2212'; }
.faq-item p { margin-top: 10px; color: var(--text-secondary); }
.related { margin-top: 56px; }
.footer-grid { grid-template-columns: 1.6fr repeat(4, 1fr); }
@media (max-width: 900px) { .footer-grid { grid-template-columns: 1fr 1fr; } }
"""

JS_MENU = """
// Keep the fixed header + mobile menu exactly below the (wrapping) pre-auth banner.
function layoutChrome() {
  var b = document.querySelector('.preauth-banner'), h = document.querySelector('header'), m = document.getElementById('mobile-menu');
  if (!b || !h) return;
  var bh = b.offsetHeight;
  h.style.top = bh + 'px';
  document.body.style.paddingTop = bh + 'px';
  if (m) m.style.top = (bh + h.offsetHeight) + 'px';
}
window.addEventListener('resize', layoutChrome);
document.addEventListener('DOMContentLoaded', layoutChrome);
function toggleMenu(force) {
  layoutChrome();
  var open = typeof force === 'boolean' ? force : !document.body.classList.contains('menu-open');
  document.body.classList.toggle('menu-open', open);
  var b = document.getElementById('menu-toggle');
  if (b) { b.setAttribute('aria-expanded', String(open)); b.textContent = open ? '\\u2715' : '\\u2630'; }
}
document.addEventListener('keydown', function (e) { if (e.key === 'Escape') toggleMenu(false); });
// Old one-page anchors (phoenix-atlas.com/#pricing etc.) -> new pages.
(function () {
  var moved = {'#corridors': '/corridors', '#reverse': '/africa-to-uk', '#features': '/send-money-to-africa#features',
    '#who-its-for': '/send-money-to-africa#who-its-for', '#compare': '/pricing#compare', '#pricing': '/pricing',
    '#security': '/security', '#invest': '/investors#invest'};
  if ((location.pathname === '/' || location.pathname === '/index.html') && moved[location.hash]) location.replace(moved[location.hash]);
})();
"""

# ---------------------------------------------------------------- templates
ORG_LD = {
    "@context": "https://schema.org", "@type": "Organization", "name": "Phoenix-Atlas Technologies Ltd",
    "url": SITE["url"], "logo": SITE["url"] + "/logo.png", "email": "hello@phoenix-atlas.com",
    "identifier": "Companies House 17432346", "address": {"@type": "PostalAddress", "addressCountry": "GB"},
    "brand": {"@type": "Brand", "name": "Vaulted"},
    "sameAs": ["https://youtu.be/zrTFni4lfxU"],
}


def jsonld(obj) -> str:
    return f'<script type="application/ld+json">{json.dumps(obj, ensure_ascii=False)}</script>'


def breadcrumb_ld(trail):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, "item": SITE["url"] + p} for i, (n, p) in enumerate(trail)]}


def head(title, desc, path, extra_ld=()):
    url = SITE["url"] + (path if path != "/" else "/")
    lds = "\n  ".join(jsonld(x) for x in (ORG_LD, *extra_ld))
    return f"""<!DOCTYPE html>
<html lang="en-GB">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="theme-color" content="#0A0807">
  <title>{title}</title>
  <meta name="description" content="{desc}">
  <meta name="robots" content="index, follow">
  <link rel="canonical" href="{url}">
  <link rel="icon" type="image/png" href="/logo.png">
  <link rel="apple-touch-icon" href="/logo.png">
  <meta property="og:site_name" content="Vaulted">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{desc}">
  <meta property="og:url" content="{url}">
  <meta property="og:type" content="{'article' if path.startswith('/learn/') else 'website'}">
  <meta property="og:image" content="{SITE['url']}/og-image.png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:locale" content="en_GB">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{title}">
  <meta name="twitter:description" content="{desc}">
  <meta name="twitter:image" content="{SITE['url']}/og-image.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/assets/styles.css">
  {lds}
</head>
<body>
"""


def header(path):
    def link(label, href):
        cur = ' aria-current="page"' if href == path else ""
        return f'<a href="{href}"{cur}>{label}</a>'
    desk = "\n        ".join(link(l, h) for l, h in NAV)
    mob = "\n    ".join(link(l, h) for l, h in [("Home", "/")] + NAV + [("FAQ", "/faq"), ("Compliance", "/compliance")])
    return f"""
  <div class="preauth-banner" role="alert" aria-live="polite">
    <strong>Vaulted is a UK fintech in build.</strong>
    Live money-transfer services will launch upon receipt of applicable authorizations from the Financial Conduct Authority.
    Not currently open for customer transactions.
    <a href="/risk-disclosure">Read the risk disclosure &rarr;</a>
  </div>
  <header>
    <div class="container nav">
      <a class="brand" href="/" aria-label="Vaulted home">
        <img src="/logo.png" alt="" width="36" height="36">
        <span><span class="wordmark">Vaulted</span><span class="wordmark-tag" style="display:block">Self-Custody &middot; Encrypted &middot; Sovereign</span></span>
      </a>
      <nav class="nav-links" aria-label="Main">
        {desk}
        <a class="btn btn-launch" href="https://app.phoenix-atlas.com">Preview app &rarr;</a>
        <button id="menu-toggle" class="menu-toggle" type="button" aria-label="Menu" aria-expanded="false" aria-controls="mobile-menu" onclick="toggleMenu()">&#9776;</button>
      </nav>
    </div>
  </header>
  <nav id="mobile-menu" class="mobile-menu" aria-label="Mobile">
    {mob}
    <a class="btn btn-primary" href="#waitlist" onclick="toggleMenu(false)">Join the waitlist &rarr;</a>
  </nav>
"""


def page_hero(trail, eyebrow, h1, sub, ctas=True):
    crumbs = " / ".join(f'<a href="{p}">{n}</a>' for n, p in trail[:-1]) + f" / <span>{trail[-1][0]}</span>"
    cta = """
      <div class="hero-cta-row">
        <a class="btn btn-primary btn-large" href="#waitlist">Join the waitlist &rarr;</a>
        <a class="btn btn-ghost btn-large" href="https://app.phoenix-atlas.com">Preview the app</a>
      </div>""" if ctas else ""
    return f"""
  <section class="hero page-hero">
    <div class="container">
      <nav class="crumbs" aria-label="Breadcrumb">{crumbs}</nav>
      <div class="eyebrow">{eyebrow}</div>
      <h1>{h1}</h1>
      <p class="hero-sub">{sub}</p>{cta}
    </div>
  </section>
"""


def prose(html, bg=False):
    style = ' style="background: var(--bg-elevated);"' if bg else ""
    return f'\n  <section{style}><div class="container"><div class="prose">{html}</div></div></section>\n'


def cards(items):
    out = []
    for c in items:
        more = f'<span class="more">{c.get("cta", "Learn more")} &rarr;</span>' if c.get("href") else ""
        tag, attr = ("a", f' href="{c["href"]}"') if c.get("href") else ("div", "")
        out.append(f'<{tag} class="info-card"{attr}><h3>{c["title"]}</h3><p>{c["body"]}</p>{more}</{tag}>')
    return '<div class="card-grid">' + "".join(out) + "</div>"


FOOTER = """
  <footer>
    <div class="container">
      <div class="footer-grid">
        <div class="footer-brand">
          <div class="wordmark">Vaulted</div>
          <div class="wordmark-tag">Self-Custody &middot; Encrypted &middot; Sovereign</div>
          <p>Vaulted is a product built by <strong>Phoenix-Atlas Technologies Ltd</strong>, a UK-registered fintech (Company No. 17432346). Currently in waitlist mode ahead of authorization from the Financial Conduct Authority.</p>
        </div>
        <div class="footer-col"><h4>Product</h4><ul>
          <li><a href="/send-money-to-africa">Send money to Africa</a></li>
          <li><a href="/africa-to-uk">Africa to UK &amp; EU</a></li>
          <li><a href="/wallet">Self-custody wallet</a></li>
          <li><a href="/security">Security</a></li>
          <li><a href="/corridors">Corridors</a></li>
          <li><a href="/pricing">Pricing</a></li>
          <li><a href="https://app.phoenix-atlas.com">Preview app</a></li>
        </ul></div>
        <div class="footer-col"><h4>Company</h4><ul>
          <li><a href="/business">Business &amp; partners</a></li>
          <li><a href="/investors">Investors</a></li>
          <li><a href="/compliance">Compliance &amp; launch stages</a></li>
          <li><a href="mailto:hello@phoenix-atlas.com">Contact</a></li>
          <li><a href="mailto:support@phoenix-atlas.com">Support</a></li>
        </ul></div>
        <div class="footer-col"><h4>Learn</h4><ul>
          <li><a href="/learn">All guides</a></li>
          GUIDE_LINKS
          <li><a href="/faq">FAQ</a></li>
        </ul></div>
        <div class="footer-col"><h4>Legal</h4><ul>
          <li><a href="/risk-disclosure">Risk disclosure</a></li>
          <li><a href="/privacy">Privacy</a></li>
          <li><a href="/terms">Terms</a></li>
        </ul></div>
      </div>
      <div style="margin-top: 40px; padding-top: 28px; border-top: 1px solid var(--border); font-size: 12px; color: var(--text-muted); line-height: 1.7;">
        <p><strong>Phoenix-Atlas Technologies Ltd</strong> is a company registered in England and Wales, <strong>Company No. 17432346</strong>. Contact: <a href="mailto:hello@phoenix-atlas.com" style="color: var(--gold-light);">hello@phoenix-atlas.com</a>.</p>
        <p style="margin-top: 10px;">Vaulted is <strong>not currently authorized</strong> by the Financial Conduct Authority (FCA). Cross-border money remittance, cryptoasset custody, and cryptoasset exchange services shown on this site are in build and will only be offered upon receipt of applicable authorizations. Nothing on this site constitutes an offer to provide regulated services or investment advice.</p>
        <p style="margin-top: 10px;"><strong>Cryptoasset risk warning:</strong> Don&rsquo;t invest unless you&rsquo;re prepared to lose all the money you invest. This is a high-risk investment and you should not expect to be protected if something goes wrong. <a href="/risk-disclosure" style="color: var(--gold-light);">Learn more.</a></p>
      </div>
      <div class="footer-bottom">
        <p>&copy; 2026 Phoenix-Atlas Technologies Ltd &middot; Company No. 17432346. All rights reserved.</p>
        <span class="tag">Made with care &middot; UK</span>
      </div>
    </div>
  </footer>
"""


def render(path, title, desc, body, trail=None, extra_ld=()):
    lds = list(extra_ld)
    if trail:
        lds.append(breadcrumb_ld(trail))
    guide_links = "".join(f'<li><a href="/learn/{g["slug"]}">{g["short"]}</a></li>' for g in GUIDES)
    html = (head(title, desc, path, lds) + header(path) + "  <main>" + body
            + legacy_section("waitlist") + "\n  </main>\n" + FOOTER.replace("GUIDE_LINKS", guide_links)
            + "\n  " + MODAL_HTML + "\n  " + MODAL_CSS
            + '\n  <script src="/assets/site.js"></script>\n</body>\n</html>\n')
    out = ROOT / (("index" if path == "/" else path.strip("/")) + ".html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    return path


# ---------------------------------------------------------------- build
def build():
    (ROOT / "assets").mkdir(exist_ok=True)
    (ROOT / "assets" / "styles.css").write_text(CSS + EXTRA_CSS)
    (ROOT / "assets" / "site.js").write_text("\n".join([JS_WAITLIST, JS_INVESTOR, JS_MODAL, JS_MENU]))

    paths = []
    for p in PAGES:
        trail = [("Home", "/")] + ([(p["crumb"], p["path"])] if p["path"] != "/" else [])
        body = ""
        for block in p["blocks"]:
            kind = block[0]
            if kind == "hero":
                body += page_hero(trail, *block[1:]) if p["path"] != "/" else legacy_section('class="hero"')
            elif kind == "legacy":
                body += legacy_section(block[1])
            elif kind == "prose":
                body += prose(block[1], bg=len(block) > 2 and block[2])
            elif kind == "cards":
                body += prose(block[1] + cards(block[2]), bg=len(block) > 3 and block[3])
            elif kind == "faq":
                items = "".join(f'<details class="faq-item"><summary>{q}</summary><p>{a}</p></details>' for q, a in FAQ)
                body += prose(items)
        lds = list(p.get("ld", []))
        if p["path"] == "/faq":
            lds.append({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": re.sub("<[^>]+>", "", a)}}
                for q, a in FAQ]})
        paths.append(render(p["path"], p["title"], p["desc"], body, trail if p["path"] != "/" else None, lds))

    # Learn hub + guides
    learn_trail = [("Home", "/"), ("Learn", "/learn")]
    hub = page_hero(learn_trail, "Learn", "Guides to sending money home, <span class=\"gold-text\">safely</span>.",
                    "Plain-English explainers on cross-border remittance, stablecoin payment rails and keeping a self-custody wallet safe.", ctas=False)
    hub += prose(cards([{"title": g["title"], "body": g["desc"], "href": f"/learn/{g['slug']}", "cta": "Read the guide"} for g in GUIDES]))
    paths.append(render("/learn", "Learn — Remittance, Stablecoin & Wallet Guides | Vaulted",
                        "Plain-English guides on sending money from the UK to Africa, how stablecoin payment rails compare with banks, and how to keep a self-custody wallet safe.",
                        hub, learn_trail))
    for g in GUIDES:
        path = f"/learn/{g['slug']}"
        trail = learn_trail + [(g["short"], path)]
        body = page_hero(trail, "Guide", g["title"], g["desc"], ctas=False) + prose(
            g["html"] + f'<p style="margin-top:32px;font-size:13px;color:var(--text-muted)">Last reviewed {TODAY}. '
            'General information only &mdash; not financial, legal or tax advice.</p>'
            '<div class="related"><h3>Related</h3>' + cards(g["related"]) + "</div>")
        article = {"@context": "https://schema.org", "@type": "Article", "headline": re.sub("<[^>]+>", "", g["title"]),
                   "description": g["desc"], "dateModified": TODAY, "datePublished": g["published"],
                   "author": {"@type": "Organization", "name": "Phoenix-Atlas Technologies Ltd"},
                   "publisher": {"@type": "Organization", "name": "Phoenix-Atlas Technologies Ltd", "logo": {"@type": "ImageObject", "url": SITE["url"] + "/logo.png"}},
                   "mainEntityOfPage": SITE["url"] + path}
        paths.append(render(path, g["seo_title"], g["desc"], body, trail, [article]))

    # sitemap / robots / llms
    urls = paths + ["/risk-disclosure", "/privacy", "/terms"]
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{SITE['url']}{'' if u == '/' else u}{'/' if u == '/' else ''}</loc><lastmod>{TODAY}</lastmod></url>\n" for u in urls)
        + "</urlset>\n")
    (ROOT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE['url']}/sitemap.xml\n")
    llms = [f"# Vaulted by Phoenix-Atlas Technologies Ltd", "",
            "> " + SITE["summary"], ""]
    llms += ["## Pages"] + [f"- [{p['crumb']}]({SITE['url']}{p['path'] if p['path'] != '/' else ''}): {p['desc']}" for p in PAGES]
    llms += ["", "## Guides"] + [f"- [{g['short']}]({SITE['url']}/learn/{g['slug']}): {g['desc']}" for g in GUIDES]
    llms += ["", "## Key facts"] + [f"- {f}" for f in SITE["facts"]]
    (ROOT / "llms.txt").write_text("\n".join(llms) + "\n")
    print(f"built {len(paths)} pages")


if __name__ == "__main__":
    build()
