"""Crawl redwood.berkeley.edu into archive/ (raw bytes at original paths).

Seeds: Yoast sitemaps (minus attachment stub pages) + every media library file
from the WP REST API. Then BFS over same-host links found in HTML and CSS.
Resumable: URLs already in archive/manifest.jsonl are skipped.

Usage: python3 scripts/crawl.py [--delay 0.4]
"""
import argparse
import json
import os
import re
import sys
import time
import warnings
from collections import deque
from urllib.parse import urljoin, urlsplit, urlunsplit, unquote

warnings.filterwarnings("ignore")
import requests
from bs4 import BeautifulSoup

HOST = "redwood.berkeley.edu"
BASE = f"https://{HOST}"
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "archive")
MANIFEST = os.path.join(ROOT, "manifest.jsonl")
UA = "RedwoodSiteArchiver/1.0 (Redwood Center site migration)"

EXCLUDE = re.compile(
    r"^/(wp-admin|wp-json|wp-login\.php|xmlrpc\.php|feed/|comments/feed)"
    r"|/feed/?$|/embed/?$|/trackback/?$"
)

session = requests.Session()
session.headers["User-Agent"] = UA


def normalize(url, keep_query=False):
    """Canonical form for dedup: https, our host, no fragment, no query (unless asked)."""
    p = urlsplit(url)
    if p.scheme not in ("http", "https", ""):
        return None
    host = (p.netloc or HOST).lower()
    if host.startswith("www."):
        host = host[4:]
    if host != HOST:
        return None
    path = p.path or "/"
    if EXCLUDE.search(path):
        return None
    return urlunsplit(("https", HOST, path, p.query if keep_query else "", ""))


def local_path(url, is_html):
    path = unquote(urlsplit(url).path)
    if is_html and not re.search(r"\.html?$", path):
        path = path.rstrip("/") + "/index.html"
    return os.path.normpath(os.path.join(ROOT, path.lstrip("/")))


def html_links(text, page_url):
    soup = BeautifulSoup(text, "html.parser")
    out = []
    for tag, attr in (("a", "href"), ("link", "href"), ("img", "src"), ("script", "src"),
                      ("source", "src"), ("video", "src"), ("video", "poster"),
                      ("iframe", "src"), ("embed", "src"), ("object", "data")):
        for el in soup.find_all(tag):
            v = el.get(attr)
            if v:
                out.append(urljoin(page_url, v.strip()))
    for el in soup.find_all(["img", "source"]):
        for attr in ("srcset", "data-srcset"):
            for part in (el.get(attr) or "").split(","):
                if part.strip():
                    out.append(urljoin(page_url, part.strip().split()[0]))
    for el in soup.find_all(attrs={"data-src": True}):
        out.append(urljoin(page_url, el["data-src"]))
    for m in re.finditer(r"url\(\s*['\"]?([^'\")]+)", text):  # inline styles
        out.append(urljoin(page_url, m.group(1)))
    return out


def css_links(text, css_url):
    refs = re.findall(r"url\(\s*['\"]?([^'\")]+)", text)
    refs += re.findall(r"@import\s+['\"]([^'\"]+)", text)
    return [urljoin(css_url, r) for r in refs if not r.startswith("data:")]


def seeds():
    """Returns (seed urls, attachment stub page urls to skip)."""
    urls, skip = [BASE + "/"], set()
    idx = session.get(BASE + "/sitemap_index.xml", timeout=60).text
    for sm in re.findall(r"<loc>([^<]+)</loc>", idx):
        locs = re.findall(r"<loc>([^<]+)</loc>", session.get(sm, timeout=60).text)
        if "attachment-sitemap" in sm:
            skip.update(normalize(u) for u in locs)
        else:
            urls += locs
    page = 1
    while True:
        r = session.get(f"{BASE}/wp-json/wp/v2/media",
                        params={"per_page": 100, "page": page, "_fields": "source_url"}, timeout=120)
        if r.status_code != 200 or not r.json():
            break
        urls += [m["source_url"] for m in r.json()]
        page += 1
        time.sleep(0.5)
    return urls, skip


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=0.4)
    args = ap.parse_args()
    os.makedirs(ROOT, exist_ok=True)

    done = set()
    if os.path.exists(MANIFEST):
        with open(MANIFEST) as f:
            for line in f:
                done.add(json.loads(line)["url"])

    seen, queue = set(done), deque()

    def enqueue(u):
        n = normalize(u)
        if n and n not in seen:
            seen.add(n)
            queue.append(n)

    seed_urls, skip = seeds()
    seen |= skip
    for u in seed_urls:
        enqueue(u)
    # On resume, re-scan saved HTML/CSS so links from already-fetched pages get queued.
    if done:
        with open(MANIFEST) as f:
            for line in f:
                rec = json.loads(line)
                if rec.get("file") and rec.get("kind") in ("html", "css"):
                    with open(rec["file"], encoding="utf-8", errors="replace") as fh:
                        t = fh.read()
                    for u in (html_links if rec["kind"] == "html" else css_links)(t, rec["final"]):
                        enqueue(u)
    print(f"{len(done)} already done, {len(queue)} queued", flush=True)

    mf = open(MANIFEST, "a")
    n = 0
    while queue:
        url = queue.popleft()
        rec = {"url": url}
        try:
            r = session.get(url, timeout=120, allow_redirects=True)
        except Exception as e:
            rec.update(status=None, error=str(e))
            mf.write(json.dumps(rec) + "\n"); mf.flush()
            continue
        final = r.url
        ctype = r.headers.get("content-type", "").split(";")[0].strip()
        kind = "html" if ctype == "text/html" else "css" if ctype == "text/css" else "other"
        rec.update(status=r.status_code, final=final, ctype=ctype, kind=kind, bytes=len(r.content))
        if normalize(final, keep_query=True) is None and urlsplit(final).netloc.lower() not in (HOST, "www." + HOST):
            rec["offsite"] = True
        elif r.status_code == 200:
            nf = normalize(final)
            if nf and nf != url:
                rec["redirect"] = nf
                seen.add(nf)
            path = local_path(nf or url, kind == "html")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(r.content)
            rec["file"] = path
            if kind == "html":
                for u in html_links(r.text, final):
                    enqueue(u)
            elif kind == "css":
                for u in css_links(r.text, final):
                    enqueue(u)
        mf.write(json.dumps(rec) + "\n"); mf.flush()
        n += 1
        if n % 50 == 0:
            print(f"{n} fetched, {len(queue)} queued — {url}", flush=True)
        time.sleep(args.delay)
    print(f"DONE. {n} fetched this run.", flush=True)


if __name__ == "__main__":
    main()
