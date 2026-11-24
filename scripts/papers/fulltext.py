"""Download PDFs for papers in the database, for later full-text work. Not part of the regular build.

    python3 fulltext.py                 # every paper marked "in" on the review page
    python3 fulltext.py --all           # every candidate
    python3 fulltext.py <paperId> ...   # specific papers

PDFs land in papers-db/pdf/<paperId>.pdf. Only open-access links (arXiv, publisher OA) are tried.
"""
import os
import sys
import time

import requests

from common import DB, UA, load_json

PDF = os.path.join(DB, "pdf")


def main():
    db = {p["id"]: p for p in load_json(os.path.join(DB, "papers.json"))["papers"]}
    review = load_json(os.path.join(DB, "review.json"), {})
    args = sys.argv[1:]
    if args == ["--all"]:
        ids = [i for i, p in db.items() if p["candidate"]]
    elif args:
        ids = args
    else:
        ids = [i for i, d in review.items() if d.get("status") == "in"]
    os.makedirs(PDF, exist_ok=True)
    got = missing = 0
    for pid in ids:
        url = (db.get(pid) or {}).get("links", {}).get("pdf")
        dest = os.path.join(PDF, f"{pid}.pdf")
        if not url or os.path.exists(dest):
            missing += not url
            continue
        r = requests.get(url, headers={"User-Agent": UA}, timeout=120)
        if r.ok and r.content[:4] == b"%PDF":
            with open(dest, "wb") as f:
                f.write(r.content)
            got += 1
        else:
            missing += 1
        time.sleep(3 if "arxiv.org" in url else 1)
    print(f"downloaded {got}; no open PDF for {missing}; folder: {PDF}")


if __name__ == "__main__":
    main()
