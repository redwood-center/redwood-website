"""Copy extracted content + images into the Astro site (site/src/data, site/public/media).

Images come from archive/ when present, else are fetched from the live site.
Rewrites image URLs in the data to site-relative paths under media/.
"""
import json
import os
import re
import time
import warnings
from datetime import date

warnings.filterwarnings("ignore")
import requests
from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
ARCHIVE = os.path.join(ROOT, "archive")
CONTENT = os.path.join(ROOT, "content")
DATA = os.path.join(ROOT, "site", "src", "data")
MEDIA = os.path.join(ROOT, "site", "public", "media")
BASE = "https://redwood.berkeley.edu"
UA = "RedwoodSiteArchiver/1.0 (Redwood Center site migration)"


def media(url, subdir):
    """Ensure the image at url is in public/media/<subdir>/; return its site-relative path."""
    if not url:
        return None
    path = url.split("redwood.berkeley.edu", 1)[-1]
    name = os.path.basename(path)
    dest = os.path.join(MEDIA, subdir, name)
    if not os.path.exists(dest):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        src = os.path.join(ARCHIVE, path.lstrip("/"))
        if os.path.exists(src):
            with open(src, "rb") as f:
                blob = f.read()
        else:
            r = requests.get(BASE + path, headers={"User-Agent": UA}, timeout=120)
            r.raise_for_status()
            blob = r.content
            time.sleep(0.3)
        with open(dest, "wb") as f:
            f.write(blob)
    return f"media/{subdir}/{name}"


def load(name):
    with open(os.path.join(CONTENT, f"{name}.json")) as f:
        return json.load(f)


def strip_tags(html):
    text = re.sub(r"\s+", " ", BeautifulSoup(html or "", "html.parser").get_text(" ")).strip()
    return re.sub(r"\s+([.,;:!?)])", r"\1", text)  # get_text(" ") leaves "link ." gaps


def excerpt(text, limit):
    """Up to `limit` chars: whole sentences if they fit, else cut at a word with an ellipsis."""
    if len(text) <= limit:
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text)
    out = ""
    for s in sentences:
        if len(out) + len(s) + 1 > limit:
            break
        out = f"{out} {s}".strip()
    if out:
        return out
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def people():
    # The listing page has uniform 300x350 crops; prefer those over the bio-page originals.
    soup = BeautifulSoup(open(os.path.join(ARCHIVE, "people", "index.html")).read(), "html.parser")
    card_photo, order = {}, {}
    for i, a in enumerate(soup.select("a.item")):
        slug = a["href"].rstrip("/").rsplit("/", 1)[-1]
        order.setdefault(slug, i)
        if a.find("img"):
            card_photo[slug] = a.find("img")["src"]
    out = []
    for p in load("people"):
        group = p["groups"][0] if p["groups"] else "Alumni"
        rec = {"slug": p["slug"], "name": p["name"], "group": group, "order": order.get(p["slug"], 999)}
        if p["kind"] == "member":
            rec.update(title=p["title"], affiliation=p["affiliation"], labs=p["labs"],
                       website=p["website"],  # no email: the site doesn't show it, and the repo is public
                       photo=media(card_photo.get(p["slug"]) or p["photo"], "people"))
        else:
            rec.update(current_affiliation=p.get("current_affiliation"))
        rec.update(PEOPLE_OVERRIDES.get(p["slug"], {}))
        if rec["group"] == "Research Staff and Students":
            rec["group"] = "Students" if "Student" in (rec.get("title") or "") else "Postdocs and research staff"
        if p["slug"] in PEOPLE_LINKS:
            rec["website"] = PEOPLE_LINKS[p["slug"]]
        if p["slug"] in FACULTY_ORDER:
            rec["order"] = FACULTY_ORDER.index(p["slug"])
        out.append(rec)
    out += [{"group": "Students" if "Student" in r["title"] or r["title"] == "Undergraduate"
             else "Postdocs and research staff", "order": 999, "affiliation": None,
             **r} for r in NEW_PEOPLE]
    return sorted(out, key=lambda r: (r["order"], r["name"]))


# Corrections to the old site's data (user, 2026-10-26). `role` renders as its own line under the title.
PEOPLE_OVERRIDES = {
    "jacob-yates": {"title": "Assistant Professor", "role": "Co-Director"},
    "mike-deweese": {"title": "Professor", "role": "Co-Director"},
    "jorge-otero-millan": {"title": "Assistant Professor"},
    "james-simon": {"name": "Jamie Simon", "title": "Postdoc", "photo": "media/people/jamie-simon.jpg"},
    "pentti-kanerva": {"title": "Research Scientist"},
    "jeff-teeters": {"group": "Staff", "labs": []},
    # No longer at the Center.
    "adrianne-zhong": {"group": "Alumni"},
    "hadi-vafaii": {"group": "Alumni"},
    "yasemin-ersoy": {"group": "Alumni"},
    "connor-bybee": {"group": "Alumni"},
}
# Members who joined after the old site was last updated (user, 2026-10-26). Photos were cropped
# to 300x350 by hand and live in site/public/media/people/; Joey's site has none.
NEW_PEOPLE = [
    {"slug": "raymond-fan", "name": "Raymond Fan", "title": "Postdoc", "labs": [],
     "website": "https://rfangit.github.io/", "photo": "media/people/raymond-fan.jpg"},
    {"slug": "joey-turnbull", "name": "Joey Turnbull", "title": "PhD Student", "labs": ["DeWeese Lab"],
     "website": "https://joeyturn.github.io/", "photo": None},
    {"slug": "samyak-jain", "name": "Samyak Jain", "title": "PhD Student", "labs": [],
     "website": "https://samyakjain0112.github.io/", "photo": "media/people/samyak-jain.jpg"},
    {"slug": "thelonious-cooper", "name": "Thelonious Cooper", "title": "PhD Student", "labs": [],
     "website": "https://theloniouscoop.dev/", "photo": "media/people/thelonious-cooper.jpg"},
    {"slug": "sultan-daniels", "name": "Sultan Daniels", "title": "PhD Student", "labs": [],
     "website": None, "photo": "media/people/sultan-daniels.jpg"},
    {"slug": "mark-rhee", "name": "Mark Rhee", "title": "Undergraduate", "labs": ["DeWeese Lab"],
     "website": "https://mrkdh16.github.io/", "photo": "media/people/mark-rhee.jpg"},
]
# Personal pages found for people (mostly alumni) whose old-site entry had none. Curated by hand;
# no LinkedIn. {slug: url}
with open(os.path.join(HERE, "data", "people-links.json")) as _f:
    PEOPLE_LINKS = json.load(_f)
FACULTY_ORDER = ["jacob-yates", "mike-deweese", "bruno-olshausen", "fritz-sommer",
                 "kristofer-bouchard", "jorge-otero-millan"]


def seminars():
    out = []
    for s in load("seminars"):
        loc = re.sub(r"\s*\(see note below[^)]*\)", "", s["location"] or "").strip() or None
        out.append({"slug": s["slug"], "title": s["title"], "speaker": s["speaker"],
                    "affiliation": s["affiliation"], "date": s["date"], "time": s["time"],
                    "location": loc, "recording_url": s["recording_url"],
                    "summary": excerpt(strip_tags(s["abstract_html"]), 400)})
    return out


def news():
    return [{"slug": n["slug"], "title": n["title"], "date": n["date"],
             "summary": excerpt(strip_tags(n["body_html"]), 240)} for n in load("news")]


def funders():
    soup = BeautifulSoup(open(os.path.join(ARCHIVE, "index.html")).read(), "html.parser")
    h3 = soup.find("h3", string=re.compile("Research Grant Support"))
    box = next(p for p in h3.parents if p.find("img"))
    out = []
    for a in box.find_all("a"):
        img = a.find("img")
        if img and "redwood.berkeley.edu" not in a["href"]:
            host = re.sub(r"^www\.", "", a["href"].split("//")[-1].split("/")[0])
            out.append({"name": FUNDER_NAMES.get(host, host), "href": HREF_FIXES.get(host, a["href"]),
                        "logo": media(img["src"], "funders")})
    return out


FUNDER_NAMES = {
    "nsf.gov": "National Science Foundation", "nih.gov": "National Institutes of Health",
    "src.org": "Semiconductor Research Corporation", "darpa.mil": "DARPA", "intel.com": "Intel",
    "apple.com": "Apple", "gatesfoundation.org": "Gates Foundation",
    "kavlifoundation.org": "Kavli Foundation", "theschwartzfoundation.org": "Swartz Foundation",
    "weillneurohub.org": "Weill Neurohub", "afrl.af.mil": "Air Force Office of Scientific Research",
}
# The old site misspells the Swartz Foundation's domain.
HREF_FIXES = {"theschwartzfoundation.org": "https://www.theswartzfoundation.org"}


def main():
    os.makedirs(DATA, exist_ok=True)
    data = {"people": people(), "seminars": seminars(), "news": news(), "funders": funders()}
    media(f"{BASE}/wp-content/uploads/2025/06/redwood_group_photo_2022_crop-1536x869.jpg", "site")
    for name, recs in data.items():
        with open(os.path.join(DATA, f"{name}.json"), "w") as f:
            json.dump(recs, f, indent=1, ensure_ascii=False)
        print(f"{name}: {len(recs)}")


if __name__ == "__main__":
    main()
