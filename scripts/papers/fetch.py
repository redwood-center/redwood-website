"""Step 1: collect every paper since 2016 (whole careers for ALL_YEARS) by the seed authors from Semantic Scholar (+ OpenAlex to fill gaps).

Semantic Scholar often splits one person across several author IDs (recent papers land on a new ID). We find the
main ID from anchor papers we know are theirs, then accept other same-name IDs only if they share co-authors.

Output: papers-db/raw.json  {slug: {"s2_ids": [...], "papers": [s2 paper, ...]}}
"""
import os
import sys

from common import DB, MAILTO, S2, fetch, load_json, name_key, norm_title, save_json

SINCE = 2016
# Whole careers for these (Jamie, 2026-10-27: their science-of-deep-learning work is all Redwood work).
ALL_YEARS = {"james-simon", "dhruva-karkada"}
FIELDS = ("paperId,title,abstract,year,publicationDate,venue,publicationVenue,journal,externalIds,authors,url,"
          "openAccessPdf,publicationTypes,citationCount")

# Author paper lists and author searches older than this are refetched, so a later run sees new papers.
MAX_AGE = float(os.environ.get("PAPERS_MAX_AGE_DAYS", 7))

# Hand curation (papers-db/curation.json): extra author profiles and papers Semantic Scholar lacks.
CURATION = load_json(os.path.join(DB, "curation.json"), {})

# slug -> name variants to search, plus anchor titles that are certainly theirs.
SEEDS = {
    "mike-deweese": (["Michael R. DeWeese", "Michael DeWeese", "M. DeWeese"],
                     ["The Eigenlearning Framework: A Conservation Law Perspective on Kernel Regression and Wide Neural Networks",
                      "Closed-Form Training Dynamics Reveal Learned Features and Linear Structure in Word2Vec-like Models",
                      "Optimal finite-time Brownian Carnot engine"]),
    "bruno-olshausen": (["Bruno A. Olshausen", "Bruno Olshausen", "B. Olshausen"],
                        ["Tent: Fully Test-time Adaptation by Entropy Minimization",
                         "The Sparse Manifold Transform"]),
    "fritz-sommer": (["Friedrich T. Sommer", "Fritz Sommer", "F. Sommer"],
                     ["Resonator Networks, 1: An Efficient Solution for Factoring High-Dimensional, Distributed Representations of Data Structures",
                      "Computing on Functions Using Randomized Vector Representations"]),
    "kristofer-bouchard": (["Kristofer E. Bouchard", "Kristofer Bouchard", "K. Bouchard"],
                           ["Union of Intersections (UoI) for Interpretable Data Driven Discovery and Prediction"]),
    "jacob-yates": (["Jacob L. Yates", "Jacob Yates", "J. Yates"],
                    ["Detailed characterization of neural selectivity in free viewing primates"]),
    "jorge-otero-millan": (["Jorge Otero-Millan", "J. Otero-Millan"],
                           ["Saccades and microsaccades during visual fixation, exploration, and search: foundations for a common saccadic generator"]),
    "james-simon": (["James B. Simon", "James Simon", "Jamie Simon", "J. B. Simon"],
                    ["The Eigenlearning Framework: A Conservation Law Perspective on Kernel Regression and Wide Neural Networks",
                     "On the Stepwise Nature of Self-Supervised Learning",
                     "Predicting kernel regression learning curves from only raw data statistics"]),
    "dhruva-karkada": (["Dhruva Karkada", "D. Karkada"],
                       ["Closed-Form Training Dynamics Reveal Learned Features and Linear Structure in Word2Vec-like Models",
                        "Predicting kernel regression learning curves from only raw data statistics"]),
    "daniel-kunin": (["Daniel Kunin", "D. Kunin"],
                     ["Get rich quick: exact solutions reveal how unbalanced initializations promote rapid feature learning",
                      "Neural Mechanics: Symmetry and Broken Conservation Laws in Deep Learning Dynamics"]),
}


def author_papers(aid):
    out, offset = [], 0
    while True:
        d = fetch(f"{S2}/author/{aid}/papers", {"fields": FIELDS, "limit": 500, "offset": offset}, max_age_days=MAX_AGE)
        if not d:
            break
        out += d.get("data", [])
        if d.get("next") is None:
            break
        offset = d["next"]
    return out


def anchor_ids(slug, titles):
    key = name_key(SEEDS[slug][0][0])
    ids = set()
    for t in titles:
        d = fetch(f"{S2}/paper/search/match", {"query": t, "fields": "title,authors"})
        hit = (d or {}).get("data", [None])[0]
        if not hit or norm_title(hit["title"])[:40] != norm_title(t)[:40]:
            print(f"  ! anchor not found: {t[:60]}")
            continue
        for a in hit["authors"]:
            if a["authorId"] and name_key(a["name"])[1] == key[1]:
                ids.add(a["authorId"])
    return ids


def person(slug):
    variants, anchors = SEEDS[slug]
    key = name_key(variants[0])
    main = anchor_ids(slug, anchors) | set(CURATION.get("profiles", {}).get(slug, {}))  # + hand-accepted profiles
    if not main:
        raise SystemExit(f"no anchor matched for {slug}")
    papers = {aid: author_papers(aid) for aid in main}
    coauthors = {a["authorId"] for ps in papers.values() for p in ps for a in p["authors"] if a["authorId"]} - main
    # Other IDs under the same name: keep those that share co-authors with the anchored IDs.
    cands = {}
    for v in variants:
        d = fetch(f"{S2}/author/search", {"query": v, "fields": "name,paperCount", "limit": 100}, max_age_days=MAX_AGE)
        for a in (d or {}).get("data", []):
            k = name_key(a["name"])
            if k[1] == key[1] and k[0] == key[0] and a["authorId"] not in main:
                cands[a["authorId"]] = a
    # Repeat until nothing changes: a profile accepted in one round brings its co-authors into the pool, which can
    # vouch for the next. (A single round missed Jake Yates's Berkeley-era profile: its co-authors, Vafaii and Galor,
    # are on another accepted profile but not on the anchor paper's, which holds his older work.) After the first
    # round only profiles that spell out the first name qualify: chaining through initials-only "F. Sommer" profiles
    # pulled in dozens of other F. Sommers.
    accepted, pending = [], {aid: a for aid, a in cands.items() if a["paperCount"] <= 2000}  # >2000: a merged bucket
    rejected = [a for a in cands.values() if a["paperCount"] > 2000]
    first_round, changed = True, True
    while changed:
        changed, pool = False, set(coauthors)  # each round tests against the pool as it stood when the round began
        for aid, a in list(pending.items()):
            if not first_round and len(a["name"].split()[0].rstrip(".")) < 2:
                continue
            ps = author_papers(aid)
            if {x["authorId"] for p in ps for x in p["authors"]} & pool:
                papers[aid] = ps
                accepted.append(pending.pop(aid))
                coauthors |= {x["authorId"] for p in ps for x in p["authors"] if x["authorId"]} - {aid}
                changed = True
        first_round = False
    rejected += pending.values()
    print(f"{slug}: main {sorted(main)}; +{len(accepted)} split IDs "
          f"({sum(a['paperCount'] for a in accepted)} papers); rejected {len(rejected)} other same-name IDs")
    seen, out = set(), []
    for aid, ps in papers.items():
        for p in ps:
            if p["paperId"] not in seen and (slug in ALL_YEARS or (p.get("year") or SINCE) >= SINCE):
                seen.add(p["paperId"])
                p["_via"] = aid
                out.append(p)
    out += [manual_paper(m) for m in CURATION.get("add", []) if m["person"] == slug]
    return {"s2_ids": sorted(papers), "papers": out}


def manual_paper(m):
    """A hand-entered paper (curation.json "add") in Semantic Scholar's shape, for papers S2 doesn't have."""
    return {"paperId": m["id"], "title": m["title"], "abstract": m.get("abstract"), "year": int(m["date"][:4]),
            "publicationDate": m["date"] if len(m["date"]) == 10 else None, "venue": m["venue"],
            "publicationVenue": None, "journal": None, "externalIds": m.get("ids", {}),
            "authors": [{"authorId": None, "name": n} for n in m["authors"]], "url": m["link"],
            "openAccessPdf": {"url": m["pdf"]} if m.get("pdf") else None, "publicationTypes": None,
            "citationCount": None, "_via": "curation.json"}


def main():
    # With slugs given, update just those people in raw.json; with none, rebuild it for everyone.
    slugs = sys.argv[1:] or list(SEEDS)
    raw = load_json(os.path.join(DB, "raw.json"), {}) if sys.argv[1:] else {}
    for slug in slugs:
        raw[slug] = person(slug)
        print(f"  {len(raw[slug]['papers'])} papers since {SINCE}")
    save_json(os.path.join(DB, "raw.json"), raw)


if __name__ == "__main__":
    main()
