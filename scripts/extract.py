"""Turn the raw crawl in archive/ into structured content in content/.

Offline: reads only archive/ (from crawl.py and fetch_api.py). Bodies are kept as
cleaned HTML (class/style/id stripped); Markdown conversion can come later.

Outputs content/{people,seminars,news,courses,publications,pages,internal}.json
and content/publications.bib.
"""
import json
import os
import re
from datetime import datetime

from bs4 import BeautifulSoup, Comment

HERE = os.path.dirname(os.path.abspath(__file__))
ARCHIVE = os.path.join(HERE, "..", "archive")
OUT = os.path.join(HERE, "..", "content")
BASE = "https://redwood.berkeley.edu"
KEEP_ATTRS = {"href", "src", "alt", "title", "colspan", "rowspan"}


def load(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return BeautifulSoup(f.read(), "html.parser")


def page(path):
    """Soup for a site path like /people/foo/, or None if not archived."""
    p = os.path.join(ARCHIVE, path.strip("/"), "index.html")
    return load(p) if os.path.exists(p) else None


def slugs(section):
    d = os.path.join(ARCHIVE, section)
    if not os.path.isdir(d):
        return []
    return sorted(s for s in os.listdir(d)
                  if s != "page" and os.path.exists(os.path.join(d, s, "index.html")))


def text(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip() if el else None


def clean_html(el):
    """Inner HTML of el with presentational attributes, comments and scripts removed."""
    if el is None:
        return None
    el = BeautifulSoup(str(el), "html.parser").find()
    for t in el.find_all(["script", "style", "noscript", "form"]):
        t.decompose()
    for c in el.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    for t in el.find_all(True):
        t.attrs = {k: v for k, v in t.attrs.items() if k in KEEP_ATTRS}
        if t.name == "span" and not t.attrs:
            t.unwrap()
    html = "".join(str(c) for c in el.contents).strip()
    return re.sub(r"\n\s*\n+", "\n", html) or None


def unscramble(soup, var):
    """Undo the theme's scramble.js obfuscation: out[orig_inds[k]] = shuffled_str[k]."""
    m = re.search(var + r"\s*=\s*(\{.*?\});", str(soup))
    if not m:
        return None
    d = json.loads(m.group(1))
    out = [""] * len(d["orig_inds"])
    for ch, i in zip(d["shuffled_str"], d["orig_inds"]):
        out[i] = ch
    return "".join(out).strip() or None


def img_src(el):
    img = el.find("img") if el else None
    return img.get("src") if img else None


# ---------------------------------------------------------------- people

def people():
    # Group membership comes from the listing pages, not the person pages.
    groups = {}
    listings = [page("/people/")] + [page(f"/people-category/{s}/") for s in slugs("people-category")]
    for soup in filter(None, listings):
        for g in soup.select(".peopleBox .group"):
            name = text(g.find("h2"))
            for a in g.select("a.item"):
                slug = a["href"].rstrip("/").rsplit("/", 1)[-1]
                groups.setdefault(slug, [])
                if name and name not in groups[slug]:
                    groups[slug].append(name)

    out = []
    for slug in slugs("people"):
        soup = page(f"/people/{slug}/")
        bio = soup.select_one(".blueBox.bio")
        rec = {"slug": slug, "url": f"{BASE}/people/{slug}/", "groups": groups.get(slug, [])}
        right = bio.select_one(".right") if bio else None
        if right:
            left = bio.select_one(".left")
            website = left.select_one("a.button") if left else None
            desc = right.select_one(".description")
            if desc and desc.find("h4"):
                desc.find("h4").decompose()
            rec.update(
                kind="member",
                name=text(right.find("h2")),
                title=text(right.find("h3", recursive=False)),
                affiliation=text(right.find("h4", recursive=False)),
                labs=[text(b) for b in right.select(".bioTag .but")],
                photo=img_src(left),
                website=website.get("href") if website else None,
                email=unscramble(soup, "json_email"),
                phone=unscramble(soup, "json_phone"),
                research_html=clean_html(desc),
            )
        else:
            # Alumni / rotation students: "<Name> is an alumnus of the Redwood Center. ... <b>Affil</b>"
            h3 = bio.find("h3") if bio else None
            line = text(h3) or ""
            m = re.match(r"(.+?) (?:is|was) an? ([\w\s]+?) (?:of|in|with) the Redwood", line)
            rec.update(kind="stub", name=m.group(1) if m else None,
                       status=m.group(2) if m else None,
                       current_affiliation=text(h3.find("b")).rstrip(".") if h3 and h3.find("b") else None,
                       stub_text=line)
        bg = soup.select_one(".bioBackground .text")
        rec["background_html"] = clean_html(bg)
        out.append(rec)
    return out


# ---------------------------------------------------------------- seminars

def parse_when(s):
    if not s:
        return None, None
    m = re.search(r"(\w+ \d{1,2}, \d{4})(?:\s+at\s+(.+))?", s)
    if not m:
        return None, None
    try:
        d = datetime.strptime(m.group(1), "%B %d, %Y").date().isoformat()
    except ValueError:
        d = None
    return d, (m.group(2) or "").strip() or None


def seminars():
    out = []
    for slug in slugs("seminars"):
        soup = page(f"/seminars/{slug}/")
        box = soup.select_one(".seminar-single")
        if not box:
            continue
        h6s = [text(h) for h in box.find_all("h6", recursive=False)]
        date, time_ = parse_when(h6s[0] if h6s else None)
        rec_btn = box.select_one(".seminar_recording_button a")
        out.append({
            "slug": slug, "url": f"{BASE}/seminars/{slug}/",
            "title": text(box.find("h3")), "speaker": text(box.find("h4")),
            "affiliation": text(box.find("h5")),
            "when_raw": h6s[0] if h6s else None, "date": date, "time": time_,
            "location": h6s[1] if len(h6s) > 1 else None,
            "abstract_html": clean_html(box.select_one(".text")),
            "recording_url": rec_btn.get("href") if rec_btn else None,
        })
    return sorted(out, key=lambda r: r["date"] or "", reverse=True)


# ---------------------------------------------------------------- news / courses / internal

def news():
    out = []
    for slug in slugs("news"):
        box = page(f"/news/{slug}/").select_one(".news-single")
        if not box:
            continue
        h5 = text(box.find("h5"))
        try:
            date = datetime.strptime(h5, "%B %d, %Y").date().isoformat()
        except (TypeError, ValueError):
            date = None
        out.append({"slug": slug, "url": f"{BASE}/news/{slug}/", "title": text(box.find("h3")),
                    "date": date, "date_raw": h5, "body_html": clean_html(box.select_one(".text"))})
    return sorted(out, key=lambda r: r["date"] or "", reverse=True)


def generic(section, body_sel):
    out = []
    for slug in slugs(section):
        soup = page(f"/{section}/{slug}/")
        head = soup.select_one("div.blue .container") or soup
        out.append({"slug": slug, "url": f"{BASE}/{section}/{slug}/",
                    "title": text(head.find("h3")) or text(soup.find("title")),
                    "body_html": clean_html(soup.select_one(body_sel))})
    return out


# ---------------------------------------------------------------- publications

def publications():
    soup = page("/publications/")
    out = []
    if soup is None:
        return out
    for item in soup.select(".publicationsBox .items .post"):
        info = item.select_one(".info")
        pre = info.find("pre")
        bib = pre.get_text().strip() if pre else None
        year = re.search(r"year\s*=\s*[{\"]?(\d{4})", bib or "")
        links = [{"label": text(a), "href": a.get("href")}
                 for a in info.select("a.more") if a.get("href") and not a["href"].startswith("#")]
        out.append({
            "title": text(info.find("h4")), "authors": text(info.find("h5")),
            "venue": text(info.find("h6")),
            "year": int(year.group(1)) if year else None,
            "tags": [text(a) for a in info.select(".tags a")],
            "links": links, "image": img_src(item.find("figure")), "bibtex": bib,
        })
    return out


# ---------------------------------------------------------------- core pages (REST API dump)

def pages():
    out = []
    for kind in ("pages", "posts"):
        p = os.path.join(ARCHIVE, "api", f"{kind}.json")
        if not os.path.exists(p):
            continue
        for it in json.load(open(p)):
            out.append({"type": kind[:-1], "id": it["id"], "slug": it["slug"], "url": it["link"],
                        "title": BeautifulSoup(it["title"]["rendered"], "html.parser").get_text(),
                        "date": it["date"], "modified": it["modified"], "parent": it.get("parent"),
                        "body_html": clean_html(BeautifulSoup(
                            f"<div>{it['content']['rendered']}</div>", "html.parser").div)})
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    results = {
        "people": people(), "seminars": seminars(), "news": news(),
        "courses": generic("courses", ".single-courses"),
        "internal": generic("internal-resources", "section.content .container"),
        "publications": publications(), "pages": pages(),
    }
    for name, recs in results.items():
        with open(os.path.join(OUT, f"{name}.json"), "w") as f:
            json.dump(recs, f, indent=1, ensure_ascii=False)
        print(f"{name}: {len(recs)}")
    with open(os.path.join(OUT, "publications.bib"), "w") as f:
        f.write("\n\n".join(p["bibtex"] for p in results["publications"] if p["bibtex"]) + "\n")


if __name__ == "__main__":
    main()
