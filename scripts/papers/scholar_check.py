"""Check: compare each seed author's Google Scholar list with what Semantic Scholar gave us.

Semantic Scholar is the pipeline's source, but it splits people across profiles and can miss papers outright. Google
Scholar profiles are curated by the people themselves, so a paper on Scholar in someone's year window that isn't in
raw.json is a gap to look into. Scholar pages are saved in papers-db/scholar/ (delete a file to refetch it).

Prints the misses per person; writes papers-db/scholar-missing.json.
    python3 scholar_check.py [slug ...]      seed authors (default: all), papers in their year windows
    python3 scholar_check.py --members       everyone else on scholar-ids.json, papers with 2+ Redwood people
"""
import html
import json
import os
import re
import sys
import time
from difflib import SequenceMatcher

import requests

from build import CAREER_DL, WINDOWS
from common import DB, PEOPLE, ROOT, load_json, name_key, norm_title, save_json

OUT = os.path.join(DB, "scholar")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def scholar_list(slug, uid):
    path = os.path.join(OUT, f"{slug}.json")
    if os.path.exists(path):
        return load_json(path)
    rows, start = [], 0
    while True:
        r = requests.get("https://scholar.google.com/citations", headers={"User-Agent": UA}, timeout=30, params={
            "hl": "en", "user": uid, "view_op": "list_works", "sortby": "pubdate", "cstart": start, "pagesize": 100})
        if r.status_code == 404:
            print(f"{slug}: Scholar profile {uid} not found; check scholar-ids.json")
            return []
        r.raise_for_status()
        page = re.findall(r'<tr class="gsc_a_tr">(.*?)</tr>', r.text, re.S)
        if not page and "gsc_a_tr" not in r.text and "gsc_prf_in" not in r.text:
            raise SystemExit(f"{slug}: Scholar returned no profile page (blocked?)")
        for row in page:
            title = re.search(r'class="gsc_a_at"[^>]*>(.*?)</a>', row, re.S)
            gray = [html.unescape(re.sub("<.*?>", "", g)) for g in re.findall(r'<div class="gs_gray">(.*?)</div>', row, re.S)]
            year = re.search(r'gsc_a_h gsc_a_hc gs_ibl">(\d*)<', row)
            href = re.search(r'class="gsc_a_at"[^>]*href="([^"]+)"', row) or re.search(r'href="([^"]+)"[^>]*class="gsc_a_at"', row)
            rows.append({"title": html.unescape(re.sub("<.*?>", "", title.group(1))) if title else "",
                         "scholar": "https://scholar.google.com" + html.unescape(href.group(1)) if href else None,
                         "authors": gray[0] if gray else "", "venue": gray[1] if len(gray) > 1 else "",
                         "year": int(year.group(1)) if year and year.group(1) else None})
        if len(page) < 100:
            break
        start += 100
        time.sleep(4)
    os.makedirs(OUT, exist_ok=True)
    save_json(path, rows)
    time.sleep(4)
    return rows


def main():
    ids = load_json(os.path.join(ROOT, "scripts", "data", "scholar-ids.json"))
    raw = load_json(os.path.join(DB, "raw.json"))
    ours = [norm_title(p["title"] or "") for person in raw.values() for p in person["papers"]]
    prefixes = {t[:40] for t in ours}

    def known(title):
        t = norm_title(title)
        return t[:40] in prefixes or any(SequenceMatcher(None, t, o).ratio() > 0.85 for o in ours if abs(len(o) - len(t)) < 25)

    # --members: everyone else with a Scholar profile. Their papers only count with 2+ Redwood people (the seed
    # authors' papers are fetched already), so only those are reported, from 2016 on.
    members = "--members" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    slugs = args or [s for s in ids if not s.startswith("_") and (s not in WINDOWS) == members]
    people = load_json(PEOPLE)
    redwood = {(name_key(p["name"])[1], name_key(p["name"])[0]) for p in people}  # (surname, first initial)

    def n_redwood(authors):
        out = set()
        for a in authors.split(","):
            parts = a.strip().split()
            if len(parts) >= 2 and (parts[-1].lower(), parts[0][0].lower()) in redwood:
                out.add(parts[-1].lower())
        return len(out)

    report = load_json(os.path.join(DB, "scholar-missing.json"), {})
    for slug in slugs:
        rows = scholar_list(slug, ids[slug]["id"])
        since = 2016 if members else WINDOWS[slug] if slug not in CAREER_DL else 0
        window = [r for r in rows if (r["year"] or 9999) >= since and (not members or n_redwood(r["authors"]) >= 2)]
        miss = [r for r in window if r["title"] and not known(r["title"])]
        report[slug] = miss
        print(f"\n{slug}: {len(rows)} on Scholar, {len(window)} from {since or 'any year'} on, {len(miss)} not in raw.json")
        for r in miss:
            print(f"  {r['year'] or '    '}  {r['title'][:80]}  |  {r['venue'][:45]}")
    save_json(os.path.join(DB, "scholar-missing.json"), report)


if __name__ == "__main__":
    main()
