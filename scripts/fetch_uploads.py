"""Download every original upload (per archive/uploads-index.json) not already in archive/.

Skips WP-generated thumbnails; crawl.py already fetched the ones pages actually use.
"""
import json
import os
import time
import warnings

warnings.filterwarnings("ignore")
import requests

ARCHIVE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "archive")
UA = "RedwoodSiteArchiver/1.0 (Redwood Center site migration)"


def main():
    files = json.load(open(os.path.join(ARCHIVE, "uploads-index.json")))
    todo = [f for f in files if not f["is_thumb"] and not os.path.exists(
        os.path.join(ARCHIVE, "wp-content", "uploads", f["path"]))]
    print(f"{len(todo)} to download", flush=True)
    s = requests.Session()
    s.headers["User-Agent"] = UA
    failed = []
    for i, f in enumerate(todo, 1):
        dest = os.path.join(ARCHIVE, "wp-content", "uploads", f["path"])
        for attempt in range(4):
            try:
                r = s.get(f["url"], timeout=300)
                r.raise_for_status()
                break
            except requests.RequestException as e:
                r = None
                time.sleep(5 * (attempt + 1))
        if r is None:
            failed.append(f["url"])
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest + ".part", "wb") as fh:
            fh.write(r.content)
        os.replace(dest + ".part", dest)
        if i % 50 == 0:
            print(f"{i}/{len(todo)}", flush=True)
        time.sleep(0.3)
    print(f"DONE. {len(failed)} failed:", *failed, sep="\n", flush=True)


if __name__ == "__main__":
    main()
