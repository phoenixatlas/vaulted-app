# Iteration 38: static-site corridor landing pages audit (/app/landing)
import json
import os
import re
import sys
from html.parser import HTMLParser

ROOT = "/app/landing"
SLUGS = ["kenya", "nigeria", "ghana", "uganda", "tanzania", "zambia", "senegal", "cote-divoire",
         "india", "philippines", "mexico"]
fails = []


class P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""; self._t = False; self.desc = None; self.canon = None
        self.h1 = 0; self.ld = []; self._ld = False; self.hrefs = []; self.srcs = []

    def handle_starttag(self, tag, a):
        a = dict(a)
        if tag == "title": self._t = True
        if tag == "meta" and a.get("name") == "description": self.desc = a.get("content")
        if tag == "link" and a.get("rel") == "canonical": self.canon = a.get("href")
        if tag == "h1": self.h1 += 1
        if tag == "script" and a.get("type") == "application/ld+json": self._ld = True; self.ld.append("")
        if tag == "a" and a.get("href"): self.hrefs.append(a["href"])
        if tag in ("img", "script") and a.get("src"): self.srcs.append(a["src"])
        if tag == "link" and a.get("href") and a.get("rel") in ("stylesheet", "icon"): self.srcs.append(a["href"])

    def handle_endtag(self, tag):
        if tag == "title": self._t = False
        if tag == "script": self._ld = False

    def handle_data(self, d):
        if self._t: self.title += d
        if self._ld: self.ld[-1] += d


def parse(path):
    p = P(); p.feed(open(path, encoding="utf-8").read()); return p


def resolve(href, base_dir):
    h = href.split("#")[0].split("?")[0]
    if not h or h.startswith(("http", "mailto:", "tel:", "javascript:", "data:")):
        if h.startswith("https://www.phoenix-atlas.com"):
            h = h[len("https://www.phoenix-atlas.com"):] or "/"
        else:
            return True
    p = os.path.join(ROOT, h.lstrip("/")) if h.startswith("/") else os.path.normpath(os.path.join(base_dir, h))
    if h in ("/", ""): return os.path.exists(os.path.join(ROOT, "index.html"))
    return any(os.path.exists(x) for x in (p, p + ".html", os.path.join(p, "index.html")))


titles, descs = {}, {}
for s in SLUGS:
    f = f"{ROOT}/send-money-to-{s}.html"
    if not os.path.exists(f):
        fails.append(f"missing {f}"); continue
    p = parse(f)
    titles.setdefault(p.title.strip(), []).append(s); descs.setdefault(p.desc, []).append(s)
    if not p.desc: fails.append(f"{s}: no meta description")
    exp = f"https://www.phoenix-atlas.com/send-money-to-{s}"
    if p.canon != exp: fails.append(f"{s}: canonical {p.canon} != {exp}")
    if p.h1 != 1: fails.append(f"{s}: h1 count {p.h1}")
    types = []
    for blob in p.ld:
        try:
            j = json.loads(blob)
            for it in (j if isinstance(j, list) else j.get("@graph", [j])):
                types.append(it.get("@type"))
        except Exception as e:
            fails.append(f"{s}: invalid JSON-LD {e}")
    for t in ("FAQPage", "BreadcrumbList"):
        if t not in types: fails.append(f"{s}: missing {t} (have {types})")
    print(f"{s}: title={p.title.strip()!r} desc_len={len(p.desc or '')} h1={p.h1} ld={types}")

for t, v in titles.items():
    if len(v) > 1: fails.append(f"duplicate title {t} for {v}")
for t, v in descs.items():
    if len(v) > 1: fails.append(f"duplicate desc for {v}")

for hub in ("corridors.html", "send-money-to-africa.html"):
    hrefs = set(parse(f"{ROOT}/{hub}").hrefs)
    for s in SLUGS:
        if f"send-money-to-{s}" == hub[:-5]: continue
        if not any(re.search(rf"send-money-to-{s}(\.html)?$", h.split('#')[0]) for h in hrefs):
            fails.append(f"{hub} does not link to {s}")

sm = open(f"{ROOT}/sitemap.xml").read()
for s in SLUGS:
    if f"https://www.phoenix-atlas.com/send-money-to-{s}<" not in sm:
        fails.append(f"sitemap missing {s}")

# broken internal links across all html pages
broken = set()
for dp, _, fs in os.walk(ROOT):
    if "/scripts" in dp or "/src" in dp or "node_modules" in dp: continue
    for fn in fs:
        if not fn.endswith(".html"): continue
        fp = os.path.join(dp, fn); p = parse(fp)
        for h in p.hrefs + p.srcs:
            if not resolve(h, dp): broken.add(f"{os.path.relpath(fp, ROOT)} -> {h}")
for b in sorted(broken): fails.append(f"broken link: {b}")

print("\nFAILS:" if fails else "\nALL CHECKS PASSED")
for f in fails: print(" -", f)
sys.exit(1 if fails else 0)
