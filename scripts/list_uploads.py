"""Walk the Apache directory listing of /wp-content/uploads/ to inventory every uploaded file.

The REST API hides media attached to non-REST custom types (it returns ~263 of 1203),
so this is the only complete list. Writes archive/uploads-index.json:
[{"url", "path", "modified", "size", "is_thumb"}], where is_thumb marks WP-generated
resized variants (foo-300x200.jpg) whose original also exists.
"""
import json
import os
import re
import time
import warnings
from urllib.parse import urljoin, unquote

warnings.filterwarnings("ignore")
import requests

ROOT_URL = "https://redwood.berkeley.edu/wp-content/uploads/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "archive", "uploads-index.json")
UA = "RedwoodSiteArchiver/1.0 (Redwood Center site migration)"
ROW = re.compile(r'<a href="([^"?]+)">[^<]*</a>\s+(\d{4}-\d\d-\d\d \d\d:\d\d)\s+(\S+)')
THUMB = re.compile(r"^(.*)-\d+x\d+(\.\w+)$")


def get(url, tries=5):
    for i in range(tries):
        try:
            return requests.get(url, headers={"User-Agent": UA}, timeout=120).text
        except requests.RequestException:
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def walk(url, files):
    html = get(url)
    time.sleep(0.5)
    for href, modified, size in ROW.findall(html):
        if href.startswith("/"):
            continue  # parent directory link
        full = urljoin(url, href)
        if href.endswith("/"):
            walk(full, files)
        else:
            files.append({"url": full, "path": unquote(full[len(ROOT_URL):]),
                          "modified": modified, "size": size})
    print(f"{url}: {len(files)} files so far", flush=True)


def main():
    files = []
    walk(ROOT_URL, files)
    paths = {f["path"] for f in files}
    for f in files:
        m = THUMB.match(f["path"])
        f["is_thumb"] = bool(m) and any(
            p in paths for p in (m.group(1) + m.group(2), m.group(1) + "-scaled" + m.group(2)))
    with open(OUT, "w") as fh:
        json.dump(files, fh, indent=1)
    print(f"{len(files)} files, {sum(not f['is_thumb'] for f in files)} originals")


if __name__ == "__main__":
    main()
