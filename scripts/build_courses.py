"""One-off migration of the old site's Courses section into the Astro site.

Reads archive/courses/index.html (terms, titles, one-line descriptions) and content/courses.json (each course
page), and writes:
  site/src/data/courses.json        one record per offering (a course taught in a term)
  site/src/data/courses/<slug>.html the offering's page content, cleaned to plain semantic HTML
  site/public/media/courses/        the few images the pages show

Lecture files (PDFs, zips: ~1.2 GB) stay on the old server and are linked there. Personal email addresses are
removed (the site shows none); mailing lists stay. The output is edited by hand afterwards, so don't rerun this
over it.
"""
import json
import os
import re
import shutil
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup, Comment, NavigableString

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
ARCHIVE = os.path.join(ROOT, "archive")
DATA = os.path.join(ROOT, "site", "src", "data")
MEDIA = os.path.join(ROOT, "site", "public", "media", "courses")
OLD = "https://redwood.berkeley.edu"

NC = ("neural-computation", "VS265", "Neural Computation", ["Bruno Olshausen"])
# Old page slug -> (course, code, title, instructors), from each page's own Instructor(s) line.
OFFERINGS = {
    "neu-290": ("science-of-intelligence", "NEU 290", "The Science of Intelligence", []),  # the page names none
    "vs265": NC, "vs265-2022": NC, "vs265-2020": NC, "vs265-fall-2018": NC,
    "nw_vs265-fall2014": NC, "nw_vs265-fall2012": NC, "nw_vs265-fall2010": NC,
    "vs298-fall2008": (NC[0], "VS298", NC[2], NC[3]), "vs298-fall2006": (NC[0], "VS298", NC[2], NC[3]),
    "computing-with-high-dimensional-vectors": (
        "computing-with-high-dimensional-vectors", "Neuroscience 299", "Computing with High-Dimensional Vectors",
        ["Denis Kleyko", "Bruno Olshausen", "Fritz Sommer", "Pentti Kanerva"]),
    "art-of-modeling": ("art-of-modeling", None, "The Art of Modeling", ["Gautam Agarwal"]),
    "vs298-2015": ("visual-perception", "VS298", "Visual Perception and its Neural Substrates", ["Karl Zipser"]),
    "vs298-fall2014": ("unsolved-problems-in-vision", "VS298", "Unsolved Problems in Vision",
                       ["Stan Klein", "Jerry Feldman", "Bruno Olshausen", "Karl Zipser"]),
    "vs198-2014": ("natural-scene-statistics", "VS298", "Natural Scene Statistics", ["Bruno Olshausen"]),
    "vs298-2012": ("animal-eyes", "VS298", "Animal Eyes", ["Bruno Olshausen"]),
}
# The CRCNS summer course has no page of its own; the old index links each year to crcns.org/course, which
# names the 2018 organizers.
CRCNS = {"Summer 2018": "crcns-summer-course-summer-2018", "Summer 2017": "crcns-summer-course-summer-2017",
         "Summer 2015": "crcns-summer2015", "Summer 2011": "crcns-summer2011"}
CRCNS_ORGANIZERS = {"Summer 2018": ["Fritz Sommer", "Bruno Olshausen", "Jeff Teeters"]}
# The old index repeats the Natural Scene Statistics blurb for these; use the course's own (Fall 2014).
SUMMARY_FROM = {"nw_vs265-fall2012": "nw_vs265-fall2014", "nw_vs265-fall2010": "nw_vs265-fall2014",
                "vs298-fall2008": "nw_vs265-fall2014", "vs298-fall2006": "nw_vs265-fall2014"}
SEMINAR_FIXES = {"jeff-hawkings-nov-2026": "jeff-hawkins-nov-2026"}

KEEP = {"p", "br", "h2", "h3", "ul", "ol", "li", "table", "thead", "tbody", "tr", "th", "td", "a", "strong", "em",
        "sup", "sub", "img", "blockquote", "hr", "code", "pre"}
RENAME = {"b": "strong", "i": "em", "h1": "h2", "h4": "h3", "h5": "h3", "h6": "h3"}
ATTRS = {"a": {"href"}, "img": {"src", "alt"}, "td": {"colspan", "rowspan"}, "th": {"colspan", "rowspan"}}
BLOCK = "p|ul|ol|li|h2|h3|table|thead|tbody|tr|th|td|blockquote|hr|pre"

EMAIL = re.compile(r"[\w.%+-]+@(?!lists\.)[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}", re.I)
EMAIL_SPELLED = re.compile(r"(?:[\w.]+,\s*)*[\w.]+(?:\s*\(respectively\))?\s+at\s+berkeley\s+dot\s+edu", re.I)


def index():
    """[(term, href, heading, description)] in the old index's order."""
    soup = BeautifulSoup(open(os.path.join(ARCHIVE, "courses", "index.html")).read(), "html.parser")
    out, term = [], None
    for el in soup.select_one(".coursesBox").children:
        if el.name == "h3":
            term = el.get_text(" ", strip=True)
        elif el.name == "div":
            for post in el.select(".post"):
                a = post.select_one("h4 a")
                out.append((term, a["href"], re.sub(r"\s+", " ", a.get_text(" ", strip=True)),
                            post.select_one("p").get_text(" ", strip=True)))
    return out


def load_people_sites():
    people = json.load(open(os.path.join(DATA, "people.json")))
    return {p["slug"]: p.get("website") for p in people}


def link(href, seminars, people):
    """Map an old link to its new home: internal pages to the new site (as /path, prefixed with the base at build
    time), uploads and everything else of the old server's to absolute URLs there."""
    href = href.strip()
    if href.startswith("//"):
        href = "https:" + href
    if href.startswith("/"):
        href = OLD + href
    u = urlparse(href)
    if u.netloc not in ("redwood.berkeley.edu", "www.redwood.berkeley.edu"):
        return href
    parts = [p for p in u.path.split("/") if p]
    if len(parts) == 2 and parts[0] == "courses":
        return f"/courses/{parts[1]}/"
    if len(parts) == 2 and parts[0] == "seminars":
        slug = SEMINAR_FIXES.get(parts[1], parts[1])
        return f"/seminars/{slug}/" if slug in seminars else href
    if len(parts) == 2 and parts[0] == "people":
        return people.get(parts[1]) or "/people/"
    return OLD + u.path + (f"?{u.query}" if u.query else "") + (f"#{u.fragment}" if u.fragment else "")


def copy_image(src):
    path = unquote(urlparse(src if not src.startswith("//") else "https:" + src).path)
    name = os.path.basename(path)
    os.makedirs(MEDIA, exist_ok=True)
    shutil.copyfile(os.path.join(ARCHIVE, path.lstrip("/")), os.path.join(MEDIA, name))
    return f"/media/courses/{name}"


INLINE = {"a", "strong", "em", "br", "sup", "sub", "code", "img"}


def wrap_loose_text(section):
    """Text and inline elements sitting directly in the page (from unwrapped divs) go into paragraphs."""
    run = []

    def flush():
        if any(str(n).strip() for n in run if n.name != "br"):
            p = BeautifulSoup("<p></p>", "html.parser").p
            run[0].insert_before(p)
            for n in run:
                p.append(n.extract())
        run.clear()

    for node in list(section.contents):
        if isinstance(node, NavigableString) or node.name in INLINE:
            run.append(node)
        else:
            flush()
    flush()


def fix_tables(section):
    """Drop empty rows; a one-row table followed by another table (a header split off by the old editor) joins
    it; then a first row of labels becomes the header."""
    for tr in section.find_all("tr"):
        if not tr.get_text(strip=True) and not tr.find("img"):
            tr.decompose()
    for table in section.find_all("table"):
        rows = table.find_all("tr")
        after = table.find_next_sibling()
        if len(rows) == 1 and after is not None and after.name == "table" and after.find("tr"):
            after.find("tr").insert_before(rows[0].extract())
            table.decompose()
    for table in section.find_all("table"):
        if not table.find_all("tr"):
            table.decompose()
        else:
            header_row(table)


def header_row(table):
    """A first row whose every filled cell is one italic or bold label becomes the table's header."""
    rows = table.find_all("tr")
    if len(rows) < 2:
        return
    cells = rows[0].find_all(["td", "th"], recursive=False)
    filled = [c for c in cells if c.get_text(strip=True)]
    if not filled or not all(
        len([k for k in c.contents if str(k).strip()]) == 1 and getattr(c.find(True), "name", None) in ("em", "strong")
        and c.find(True).get_text(strip=True) == c.get_text(strip=True) for c in filled):
        return
    for c in cells:
        c.name = "th"
        if c.find(True):
            c.find(True).unwrap()
    thead = BeautifulSoup("<thead></thead>", "html.parser").thead
    table.insert(0, thead)
    thead.append(rows[0].extract())


def clean(section, title, seminars, people):
    for c in section.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    for t in section.find_all(["script", "style", "noscript", "iframe", "form", "input", "button"]):
        t.decompose()
    for a in section.find_all("a"):
        href = a.get("href", "")
        if "mailhide" in href or (href.startswith("mailto:") and EMAIL.search(href)):
            text = a.get_text(" ", strip=True)
            if EMAIL.search(text) or text.lower() in ("", "link", "email", "e-mail"):
                a.decompose()  # the address itself, or a stand-in for it
            else:
                a.unwrap()  # a name linked to its address: keep the name
    for t in section.find_all(True):
        t.name = RENAME.get(t.name, t.name)
        if t.name not in KEEP:
            t.unwrap()
            continue
        t.attrs = {k: v for k, v in t.attrs.items() if k in ATTRS.get(t.name, set())}
        if t.name == "a":
            if not t.get("href") or t["href"].startswith("#"):
                t.unwrap()
                continue
            t["href"] = link(t["href"], seminars, people)
        if t.name == "img":
            t["src"] = copy_image(t["src"])
            t["alt"] = t.get("alt", "")
    for s in section.find_all(string=True):
        text = EMAIL_SPELLED.sub("", EMAIL.sub("", str(s))).replace("\xa0", " ")
        if text != str(s):
            s.replace_with(NavigableString(text))
    wrap_loose_text(section)
    fix_tables(section)

    html = "".join(str(c) for c in section.contents)
    html = re.sub(r"\s+", " ", html)
    html = re.sub(r"<br/?>", "<br>", html)
    # Remnants of removed addresses: an "Email:" label with nothing after it, empty brackets, doubled commas.
    html = re.sub(r"(?:<strong>)?\s*E-?mail\s*:?\s*(?:</strong>)?\s*:?\s*(?=<br>|</p>|</li>|</td>)", "", html, flags=re.I)
    html = re.sub(r"\(\s*\)", "", html)
    html = re.sub(r",(\s*,)+", ",", html)
    html = re.sub(r"\s*,\s*(?=<br>|</p>|</li>|</td>|<strong>)", " ", html)
    html = re.sub(r" +([.,;:)])", r"\1", html)
    for _ in range(3):  # empty elements and stray line breaks, innermost first
        html = re.sub(r"<(p|li|strong|em|h2|h3)>\s*</\1>", "", html)
        html = re.sub(r"<(ul|ol)>\s*</\1>", "", html)
        html = re.sub(r"(?:<br>\s*){2,}", "<br>", html)
        html = re.sub(r"(<(p|li|td|th)>)\s*(?:<br>\s*)+", r"\1", html)
        html = re.sub(r"(?:\s*<br>)+\s*(</(p|li|td|th)>)", r"\1", html)
        html = re.sub(r"(<(p|li|td|th)>)\s+", r"\1", html)
    # One block per line: a newline before each block's start, and before the end of containers.
    html = re.sub(rf"\s*(<(?:{BLOCK})[ >]|</(?:ul|ol|table|thead|tbody|tr|blockquote)>)", r"\n\1", html)
    html = re.sub(rf"\s+(</(?:{BLOCK})>)", r"\1", html)
    lines = [ln.strip() for ln in html.split("\n") if ln.strip()]
    # Two pages open with their own title as a heading.
    if lines and re.sub(r"<[^>]+>", "", lines[0]).strip() == title:
        lines = lines[1:]
    return "\n".join(lines) + "\n"


def main():
    pages = {c["slug"]: c for c in json.load(open(os.path.join(ROOT, "content", "courses.json")))}
    seminars = {s["slug"] for s in json.load(open(os.path.join(DATA, "seminars.json")))}
    people = load_people_sites()
    items = index()
    blurbs = {href.rstrip("/").rsplit("/", 1)[-1]: desc for _, href, _, desc in items}
    os.makedirs(os.path.join(DATA, "courses"), exist_ok=True)
    out = []
    for term, href, heading, desc in items:
        if "crcns.org" in href:
            out.append({"slug": CRCNS[term], "course": "crcns-summer-course", "code": None, "title": heading,
                        "term": term, "instructors": CRCNS_ORGANIZERS.get(term, []), "url": href, "summary": desc})
            continue
        slug = href.rstrip("/").rsplit("/", 1)[-1]
        course, code, title, instructors = OFFERINGS[slug]
        section = BeautifulSoup(pages[slug]["body_html"], "html.parser").find("section")
        full_title = f"{code}: {title}" if code else title
        body = clean(section, full_title, seminars, people)
        with open(os.path.join(DATA, "courses", f"{slug}.html"), "w") as f:
            f.write(body)
        out.append({"slug": slug, "course": course, "code": code, "title": title, "term": term,
                    "instructors": instructors, "url": None, "summary": blurbs[SUMMARY_FROM.get(slug, slug)]})
    with open(os.path.join(DATA, "courses.json"), "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(f"{len(out)} offerings, {len({o['course'] for o in out})} courses")


if __name__ == "__main__":
    main()
