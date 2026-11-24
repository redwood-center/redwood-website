"""Dump the WP REST API's core types to archive/api/*.json.

Only pages/posts/media/taxonomies/users are exposed; the custom types
(people, seminars, news, courses) are not, so those come from crawl.py.
"""
import json
import os
import time
import warnings

warnings.filterwarnings("ignore")
import requests

API = "https://redwood.berkeley.edu/wp-json/wp/v2"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "archive", "api")
UA = "RedwoodSiteArchiver/1.0 (Redwood Center site migration)"


def fetch_all(endpoint):
    items, page = [], 1
    while True:
        r = requests.get(f"{API}/{endpoint}", params={"per_page": 100, "page": page},
                         headers={"User-Agent": UA}, timeout=120)
        if r.status_code != 200 or not r.json():
            break
        items += r.json()
        if page >= int(r.headers.get("X-WP-TotalPages", 1)):
            break
        page += 1
        time.sleep(0.5)
    return items


def main():
    os.makedirs(OUT, exist_ok=True)
    for ep in ("pages", "posts", "media", "categories", "tags", "users"):
        items = fetch_all(ep)
        with open(os.path.join(OUT, f"{ep}.json"), "w") as f:
            json.dump(items, f, indent=1, ensure_ascii=False)
        print(f"{ep}: {len(items)}")


if __name__ == "__main__":
    main()
