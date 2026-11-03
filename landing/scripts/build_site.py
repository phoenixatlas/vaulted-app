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

from site_content import COUNTRIES, FAQ, GUIDES, PAGES, SITE, NAV

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
/* Never fall back to the browser's default blue / visited-purple link colour. */
:where(a), :where(a:visited) { color: var(--gold-light); }
.brand { display: flex; align-items: center; gap: 10px; text-decoration: none; }
.brand img { width: 40px; height: 40px; border-radius: 9px; }
.brand, .brand:visited, .brand:hover { color: var(--gold-light); }
.brand-by { font-family: 'Cormorant Garamond', serif; font-weight: 600; font-size: 17px; color: var(--gold-light) !important; white-space: nowrap; }
@media (max-width: 420px) { .brand-by { font-size: 14px; } }
.rate-widget { background: var(--bg-card); border: 1px solid rgba(201,163,91,0.35); border-radius: 20px; padding: 24px; margin: 0 0 40px; }
.rate-widget .rw-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.rate-widget label { font-size: 13px; color: var(--text-secondary); width: 100%; }
.rate-widget input { background: var(--bg); border: 1px solid var(--border); border-radius: 12px; color: var(--text-primary);
  font: inherit; font-size: 22px; font-weight: 600; padding: 10px 14px; width: 160px; min-height: 52px; }
.rate-widget input:focus { outline: none; border-color: var(--gold); }
.rate-widget .rw-gets { font-family: 'Cormorant Garamond', serif; font-size: clamp(28px, 5vw, 40px); color: var(--gold-light); font-weight: 600; margin: 14px 0 6px; }
.rate-widget .rw-meta { font-size: 13px; color: var(--text-muted); margin: 0; }
.rate-widget .rw-compare { font-size: 15px; font-weight: 600; color: #7FC77F; margin: 0 0 10px; min-height: 1px; }
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
/* Buttons inside text sections keep the standard dark label (beats .prose a). */
.prose a.btn-primary, .prose a.btn-primary:visited, .prose a.btn-primary:hover,
.partner-form .btn-primary { color: #0F0B08; }
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
footer { overflow-x: hidden; }
.footer-grid > * { min-width: 0; overflow-wrap: anywhere; }
.partner-form { display: grid; gap: 12px; margin-top: 20px; }
.pf-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 600px) { .pf-row { grid-template-columns: 1fr; } }
.partner-form input, .partner-form select, .partner-form textarea { width: 100%; background: var(--bg-card);
  border: 1px solid var(--border); border-radius: 12px; color: var(--text-primary); padding: 14px 16px;
  font: inherit; font-size: 15px; min-height: 48px; }
.partner-form input:focus, .partner-form select:focus, .partner-form textarea:focus { outline: none; border-color: var(--gold); }
.partner-form .btn { justify-self: start; border: none; cursor: pointer; }
.pf-hp { position: absolute; left: -9999px; width: 1px; height: 1px; opacity: 0; }
#pf-msg { font-size: 14px; min-height: 20px; margin: 0; }
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
// Corridor rate widget: indicative recipient amount from live mid-market FX
// (/api/rates/fiat, USD base) minus the planned free-tier fee (1.5%, min £0.50, max £9.99).
async function initRateWidgets() {
  var BANK_FEE_GBP = 25, BANK_FX_MARGIN = 0.03;
  var boxes = document.querySelectorAll('.rate-widget');
  if (!boxes.length) return;
  var data;
  try {
    var r = await fetch(WAITLIST_API_BASE + '/api/rates/fiat');
    data = await r.json();
  } catch (err) { data = null; }
  boxes.forEach(function (box) {
    var cur = box.getAttribute('data-currency'), input = box.querySelector('input');
    var gets = box.querySelector('.rw-gets'), meta = box.querySelector('.rw-meta');
    var rates = data && data.rates;
    if (!rates || !rates[cur] || !rates.GBP) {
      gets.textContent = 'Live rate unavailable right now';
      meta.textContent = 'Please try again later.';
      return;
    }
    var perGbp = rates[cur] / rates.GBP;
    var fmt = function (n, d) { return n.toLocaleString('en-GB', {maximumFractionDigits: d, minimumFractionDigits: d}); };
    var update = function () {
      var amt = Math.min(Math.max(parseFloat(input.value) || 0, 0), 10000);
      var fee = amt > 0 ? Math.min(Math.max(amt * 0.015, 0.5), 9.99) : 0;
      var out = Math.max(amt - fee, 0) * perGbp;
      gets.textContent = 'Recipient gets \\u2248 ' + fmt(out, perGbp > 100 ? 0 : 2) + ' ' + cur;
      // Illustrative typical UK bank transfer: £25 fee + 3% exchange-rate margin.
      var bank = Math.max(amt - BANK_FEE_GBP, 0) * perGbp * (1 - BANK_FX_MARGIN);
      var diff = out - bank, cmp = box.querySelector('.rw-compare');
      if (cmp) {
        cmp.textContent = diff > 0 && amt > BANK_FEE_GBP
          ? '\\u2248 ' + fmt(diff, perGbp > 100 ? 0 : 2) + ' ' + cur + ' more than a typical bank transfer*'
          : '';
      }
      var when = data.fetched_at ? new Date(data.fetched_at).toLocaleString('en-GB', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'}) : '';
      meta.textContent = '\\u00a31 = ' + fmt(perGbp, perGbp > 100 ? 2 : 4) + ' ' + cur + ' mid-market' + (when ? ' (updated ' + when + ')' : '')
        + ' \\u00b7 planned fee \\u00a3' + fmt(fee, 2) + '. Indicative only \\u2014 not an offer; Vaulted is not yet live.'
        + ' *Bank comparison assumes an illustrative \\u00a3' + BANK_FEE_GBP + ' transfer fee and a ' + (BANK_FX_MARGIN * 100)
        + '% exchange-rate margin; actual bank costs vary and may include intermediary charges.';
    };
    input.addEventListener('input', update);
    update();
  });
}
document.addEventListener('DOMContentLoaded', initRateWidgets);
async function handlePartnerEnquiry(e) {
  e.preventDefault();
  var v = function (id) { return (document.getElementById(id).value || '').trim(); };
  var btn = document.getElementById('pf-btn'), msg = document.getElementById('pf-msg');
  btn.disabled = true; btn.textContent = 'Sending\\u2026'; msg.textContent = '';
  try {
    var res = await fetch(WAITLIST_API_BASE + '/api/partners/enquiry', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name: v('pf-name'), email: v('pf-email'), company: v('pf-company'), partner_type: v('pf-type'),
        corridor: v('pf-corridor'), message: v('pf-message'), website: v('pf-website')})
    });
    var data = await res.json().catch(function () { return {}; });
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Please check the form and try again.');
    document.getElementById('partner-form').reset();
    msg.style.color = 'var(--gold-light)';
    msg.textContent = 'Thanks \\u2014 we\\u2019ve received your enquiry and will reply within 2 working days.';
  } catch (err) {
    msg.style.color = '#ff8a80';
    msg.textContent = (err && err.message) || 'Something went wrong. Email hello@phoenix-atlas.com instead.';
  } finally { btn.disabled = false; btn.textContent = 'Send enquiry \\u2192'; }
  return false;
}
// Old one-page anchors (phoenix-atlas.com/#pricing etc.) -> new pages.
(function () {
  var moved = {'#corridors': '/corridors', '#reverse': '/africa-to-uk', '#features': '/send-money-to-africa#features',
    '#who-its-for': '/send-money-to-africa#who-its-for', '#compare': '/pricing#compare', '#pricing': '/pricing',
    '#security': '/security', '#invest': '/investors#invest'};
  if ((location.pathname === '/' || location.pathname === '/index.html') && moved[location.hash]) location.replace(moved[location.hash]);
})();
"""

# ---------------------------------------------------------------- templates
import hashlib  # noqa: E402

# Cache-buster so phones never keep an old stylesheet after a deploy.
ASSET_VER = hashlib.sha1((CSS + EXTRA_CSS + JS_MENU).encode()).hexdigest()[:8]
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
  <link rel="stylesheet" href="/assets/styles.css?v={ASSET_VER}">
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
        <span class="brand-by" style="color:#E6C879">by Phoenix-Atlas Technologies Ltd</span>
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
            + f'\n  <script src="/assets/site.js?v={ASSET_VER}"></script>\n</body>\n</html>\n')
    out = ROOT / (("index" if path == "/" else path.strip("/")) + ".html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    return path


# ---------------------------------------------------------------- build
def _plain(s: str) -> str:
    return re.sub("<[^>]+>", "", s).replace("&rsquo;", "'").replace("&mdash;", "—").replace("&amp;", "&")


def _cap(name: str) -> str:
    return name[0].upper() + name[1:]


def country_cards():
    return cards([{"title": f"Send money to {_cap(c['name'])}", "body": f"{c['currency']} &middot; {c['status']}",
                   "href": f"/send-money-to-{c['slug']}", "cta": "See corridor"} for c in COUNTRIES])


def rate_widget(c) -> str:
    """Live sample-rate calculator (filled in by initRateWidgets in site.js)."""
    return (f'<div class="rate-widget" data-currency="{c["cur"]}" data-country="{_plain(c["name"])}">'
            f'<div class="rw-row"><label for="rw-amount">You send (GBP)</label>'
            f'<input id="rw-amount" type="number" inputmode="decimal" min="1" max="10000" step="1" value="100" aria-label="Amount in pounds"></div>'
            f'<p class="rw-gets" aria-live="polite">Loading today&rsquo;s rate&hellip;</p>'
            f'<p class="rw-compare" aria-live="polite"></p>'
            f'<p class="rw-meta">Loading&hellip;</p></div>')


def build_country(c):
    path = f"/send-money-to-{c['slug']}"
    name, cap = c["name"], _cap(c["name"])
    trail = [("Home", "/"), ("Corridors", "/corridors"), (f"Send money to {cap}", path)]
    sandbox = c["status"].startswith("Sandbox")
    partner = c["status"].startswith("Supported")
    title = f"Send Money to {_plain(cap)} from the UK | Vaulted"
    desc = (f"Vaulted's planned UK/EU to {_plain(name)} corridor: payout to "
            f"{_plain(c['payout'][0]).split(',')[0].lower()}, recipient details, fees and launch status.")
    li = lambda xs: "<ul>" + "".join(f"<li>{x}</li>" for x in xs) + "</ul>"  # noqa: E731
    others = [x for x in COUNTRIES if x["slug"] != c["slug"]][:4]
    body = page_hero(trail, f"UK/EU &rarr; {cap}", f"Send money to <span class=\"gold-text\">{cap}</span>.",
                     f"Pay in pounds or euros; your recipient receives {c['currency']}. {c['why']}")
    body += prose(
        rate_widget(c) +
        f"<h2>How it works</h2><ol><li>Enter the amount in GBP or EUR and fund by card, Apple Pay, Google Pay or bank transfer.</li>"
        f"<li>Vaulted converts to a regulated USD stablecoin and moves it on the cheapest low-cost network.</li>"
        f"<li>Our local payout partner pays your recipient in {c['currency']}.</li></ol>"
        f"<h2>How your recipient gets paid</h2>{li(c['payout'])}"
        f"<h2>What you&rsquo;ll need</h2>{li(c['needs'])}"
        f"<h2>Planned fees</h2><p>Free tier: 3 cross-border sends a month at a 1.5% service fee (minimum &pound;0.50, maximum &pound;9.99). "
        f"Vault Pro (&pound;9.99/month) halves the fee. See <a href=\"/pricing\">pricing</a>.</p>"
        f"<h2>Corridor status</h2><div class=\"stage\"><b>{c['status']}.</b> "
        + ("Rates and payouts have been tested end-to-end in our partner&rsquo;s sandbox. " if sandbox else
           "Our payout partner supports this destination in test mode; end-to-end tests are next. " if partner else
           "This destination is on our roadmap and will open after earlier corridors. ")
        + "Live transfers open corridor by corridor once applicable FCA authorizations are in place &mdash; "
          "<a href=\"/compliance\">see our launch stages</a>.</div>"
        + '<p style="font-size:13px;color:var(--text-muted)">Vaulted is not yet FCA-authorized and is not open for customer transactions. Fees and timings are illustrative targets.</p>'
        + '<div class="related"><h3>Other corridors</h3>' + cards(
            [{"title": f"Send money to {_cap(o['name'])}", "body": o["currency"], "href": f"/send-money-to-{o['slug']}"} for o in others]
            + [{"title": "All corridors", "body": "Every planned destination and the reverse corridor.", "href": "/corridors"}]) + "</div>")
    faq = [(f"Can I send money from the UK to {_plain(name)} with Vaulted today?",
            "Not yet. Vaulted is in waitlist and preview mode ahead of FCA authorization and is not open for customer transactions."),
           (f"How will my recipient in {_plain(name)} receive the money?", _plain(" or ".join(c["payout"])) + "."),
           ("Do I need crypto?", "No. You pay in pounds or euros and your recipient receives local currency; the stablecoin rail runs in the background.")]
    ld = [{"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}]
    return render(path, title, desc, body, trail, ld)


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
            elif kind == "countries":
                body += prose("<h2>Send money by country</h2>" + country_cards(), bg=True)
            elif kind == "faq":
                items = "".join(f'<details class="faq-item"><summary>{q}</summary><p>{a}</p></details>' for q, a in FAQ)
                body += prose(items)
        lds = list(p.get("ld", []))
        if p["path"] == "/faq":
            lds.append({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": re.sub("<[^>]+>", "", a)}}
                for q, a in FAQ]})
        paths.append(render(p["path"], p["title"], p["desc"], body, trail if p["path"] != "/" else None, lds))

    # Per-country corridor pages
    for c in COUNTRIES:
        paths.append(build_country(c))

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
    llms += ["", "## Corridors"] + [f"- [Send money to {_plain(c['name'])}]({SITE['url']}/send-money-to-{c['slug']}): "
                                    f"{_plain(c['currency'])}; {c['status']}" for c in COUNTRIES]
    llms += ["", "## Key facts"] + [f"- {f}" for f in SITE["facts"]]
    (ROOT / "llms.txt").write_text("\n".join(llms) + "\n")
    print(f"built {len(paths)} pages")


if __name__ == "__main__":
    build()
