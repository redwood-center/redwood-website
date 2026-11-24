"""Shared helpers for the papers pipeline: cached, rate-limited API access and text normalization."""
import hashlib
import json
import os
import random
import re
import sys
import time
import unicodedata
import warnings

warnings.filterwarnings("ignore")
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
DB = os.path.join(ROOT, "papers-db")
CACHE = os.path.join(DB, "cache")
PEOPLE = os.path.join(ROOT, "site", "src", "data", "people.json")
# Contact address for Crossref/OpenAlex's polite pool, kept out of the repo: papers-db/.mailto (one line).
_mailfile = os.path.join(DB, ".mailto")
MAILTO = open(_mailfile).read().strip() if os.path.exists(_mailfile) else "redwood-website@users.noreply.github.com"
UA = f"RedwoodPapersDB/1.0 (Redwood Center website; mailto:{MAILTO})"
S2 = "https://api.semanticscholar.org/graph/v1"
# Optional Semantic Scholar API key (dedicated 1 req/s instead of the congested shared pool): papers-db/.s2-key
_keyfile = os.path.join(DB, ".s2-key")
S2_KEY = os.environ.get("S2_API_KEY") or (open(_keyfile).read().strip() if os.path.exists(_keyfile) else None)

_last = {}


def _wait(host, gap):
    dt = time.time() - _last.get(host, 0)
    if dt < gap:
        time.sleep(gap - dt)
    _last[host] = time.time()


def fetch(url, params=None, body=None, gap=1.2, kind="json", tries=80, max_age_days=None):
    """GET (or POST when body is given) with an on-disk cache and polite pacing. Returns parsed JSON or text.
    max_age_days: refetch when the cached copy is older (for lists that grow, like an author's papers);
    None keeps cached copies forever (for things that don't change, like a paper's abstract)."""
    key = hashlib.sha1(json.dumps([url, params, body], sort_keys=True).encode()).hexdigest()
    path = os.path.join(CACHE, key[:2], key + (".json" if kind == "json" else ".txt"))
    fresh = max_age_days is None or (os.path.exists(path) and time.time() - os.path.getmtime(path) < max_age_days * 86400)
    if os.path.exists(path) and fresh:
        with open(path) as f:
            return json.load(f) if kind == "json" else f.read()
    host = url.split("/")[2]
    r = None
    for i in range(tries):
        _wait(host, gap)
        try:
            headers = {"User-Agent": UA}
            if S2_KEY and host == "api.semanticscholar.org":
                headers["x-api-key"] = S2_KEY
            r = (requests.post(url, params=params, json=body, headers=headers, timeout=90) if body is not None
                 else requests.get(url, params=params, headers=headers, timeout=90))
        except requests.RequestException:
            time.sleep(5 + 5 * i)
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            # S2's keyless pool is shared and refuses ~1 in 3 calls at random; short jittered retries work best.
            # Long refusal streaks happen; back off up to a minute rather than give up.
            print(f"    {r.status_code} on {url.split('/')[2]}, retry {i + 1}", file=sys.stderr, flush=True)
            time.sleep(2 + random.random() * 3 + min(55, 3 * max(0, i - 5)))
            continue
        break
    if r is None or r.status_code == 404:
        out = None
    elif not r.ok:
        raise RuntimeError(f"{r.status_code} {url} {r.text[:200]}")
    else:
        out = r.json() if kind == "json" else r.text
    if out is not None or (r is not None and r.status_code == 404):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(out, f) if kind == "json" else f.write(out or "")
    return out


def ascii_fold(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()


def norm_title(s):
    return re.sub(r"[^a-z0-9]", "", ascii_fold(s).lower())


def words(s):
    return re.findall(r"[a-z0-9]+", ascii_fold(s).lower())


def name_key(name):
    """(first initial, last name) with accents, punctuation and suffixes dropped."""
    parts = [p for p in re.split(r"[\s.]+", ascii_fold(name).replace("’", "'")) if p]
    parts = [p for p in parts if p.lower() not in ("jr", "sr", "ii", "iii", "phd")]
    if not parts:
        return ("", "")
    last = re.sub(r"[^a-z]", "", parts[-1].lower())
    return (parts[0][0].lower(), last)


def load_json(path, default=None):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
