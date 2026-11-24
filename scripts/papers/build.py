"""Step 3: assemble the papers database.

- One record per Semantic Scholar paper, authors marked with Redwood people (current or alumni).
- Versions of the same paper (preprint vs. published, retitled) grouped; the latest is the primary, others point to it.
- Citation edges between papers in the database (mapped onto primaries).
- A first-pass category and a "candidate" flag (is this plausibly a Redwood paper?) with reasons, for human review.

Outputs: papers-db/papers.json (everything) and site/src/data/papers.json (what the Papers page needs).
"""
import os
import re
from difflib import SequenceMatcher

from common import DB, PEOPLE, ROOT, load_json, name_key, norm_title, save_json, words

# Years whose papers count, per seed author (Jamie, 2026-10-27). Older papers stay in the database but aren't flagged
# (so they don't appear on the map). Bouchard: on the Redwood people page by 2018 (earliest archived copy).
# Otero-Millan: first on the Redwood site mid-2025 (his page first archived 2025-06; on the people page by 2025-07;
# Berkeley faculty since 2020). Yates: 2023 on. Simon/Karkada: grad-school ML; see CAREER_DL.
WINDOWS = {"mike-deweese": 2016, "bruno-olshausen": 2016, "fritz-sommer": 2016, "kristofer-bouchard": 2018,
           "jacob-yates": 2023, "jorge-otero-millan": 2025, "james-simon": 2020, "dhruva-karkada": 2020,
           "daniel-kunin": 2025}
# Any year counts for these authors' science-of-deep-learning papers (Jamie, 2026-10-27: all of it is Redwood work).
CAREER_DL = {"james-simon", "dhruva-karkada"}
# Inclusion (Jamie, 2026-10-27): two or more Redwood people on a paper -> in, whatever the year. Otherwise more than
# BIG_PAPER authors with the one Redwood author neither first nor last -> out, except Jamie Simon's papers up to
# MEGA authors (BIG-bench-style collaborations stay out).
BIG_PAPER = 5
MEGA = 50

NICKNAMES = [{"mike", "michael"}, {"fritz", "friedrich"}, {"jamie", "james"}, {"chris", "christopher"},
             {"joey", "joseph", "joe"}, {"sam", "samuel"}, {"ed", "eduardo"}, {"jake", "jacob"}, {"dan", "daniel"},
             {"alex", "alexander"}, {"kris", "kristofer"}, {"pentti"}, {"tom", "thomas"}, {"bill", "william"}]

def read_categories():
    """{id: name} from categories.md (`## <id>: <Name>` headings), in file order."""
    text = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "categories.md")).read()
    return dict(re.findall(r"^## ([a-z-]+): (.+)$", text, re.M))


CATEGORIES = read_categories()
KEYWORDS = {
    "learning-mech": ["neural tangent kernel", "ntk", "kernel regression", "kernel ridge", "learning dynamics",
                   "training dynamics", "gradient flow", "gradient descent", "feature learning", "overparameteri",
                   "scaling law", "double descent", "infinite width", "wide neural", "loss landscape", "implicit bias",
                   "generalization", "eigenlearning", "learning curve", "rich regime", "lazy regime", "saddle",
                   "critical point", "hessian", "learning rate", "hyperparameter", "deep linear", "conservation law",
                   "mean-field", "word2vec", "solvable", "spectral bias", "eigenstructure", "muP", "optimizer"],
    "representation": ["sparse coding", "sparse code", "dictionary learning", "natural image", "natural scene",
                       "unsupervised", "representation learning", "manifold", "efficient coding", "color", "colour",
                       "equivariant", "invarian", "image statistics", "foveat", "self-supervised", "lie group",
                       "transformation", "perceptual", "generative model", "texture", "cone"],
    "neuromorphic": ["hyperdimensional", "vector symbolic", "vsa", "holographic reduced", "resonator", "binding",
                     "high-dimensional computing", "neuromorphic", "spiking", "residue number",
                     "sparse distributed memory", "phasor", "superposition", "cognitive"],
    "physical-computing": ["optical neural", "photonic", "optical", "analog computing", "in-memory computing", "memristor",
                 "emerging hardware", "hardware", "chip", "circuit", "superconducting", "accelerator", "fpga",
                 "device", "nanoscal", "ising machine", "oscillator", "energy-efficient"],
    "vision": ["saccad", "eye movement", "gaze", "fixation", "oculomotor", "nystagmus", "vestibular", "torsion",
               "visual cortex", "primary visual", " v1", "marmoset", "retina", "free viewing", "visual field",
               "psychophysic", "dizziness", "vertigo", "head impulse", "eye tracking", "binocular", "strabism",
               "visual perception", "pupil"],
    "neuro-theory": ["neuron", "neural coding", "cortex", "cortical", "hippocamp", "place cell", "grid cell", "spike",
              "synap", "ecog", "electrocorticograph", "brain", "auditory", "neural data", "recording",
              "calcium imaging", "decoding", "neural population", "theta", "entorhinal", "mouse", "mice",
              "songbird", "neuroscience", "dendrit", "motor cortex", "speech"],
    "physics": ["thermodynamic", "nonequilibrium", "non-equilibrium", "entropy production", "brownian",
                "fokker-planck", "carnot", "heat engine", "quantum", "qubit", "spin", "stochastic thermodynamics",
                "optimal protocol", "free energy", "maxwell", "information engine", "nanotube", "dissipation",
                "langevin", "physical review"],
}
VENUE_HINTS = [(r"physical review|j\. ?stat|journal of statistical|epl\b|new journal of physics", "physics", 3),
               (r"journal of vision|investigative ophthalmology|vision research|ophthalm|otolaryng|neurolog", "vision", 3),
               (r"neuron\b|j(ournal of)? ?neurosci|elife|plos computational|neural computation|cerebral cortex", "neuro-theory", 2),
               (r"optics|photonic|circuits and systems|electron devices|nature electronics", "physical-computing", 3)]

JUNK = re.compile(r"^(author response|decision letter|author correction|correction|erratum|retraction|reply|"
                  r"response to|comment on|supplementar|reviewer|publisher correction)|\breply\.?$", re.I)
ABSTRACT_VENUES = re.compile(r"bulletin of the american physical society|cosyne|society for neuroscience|"
                             r"abstracts?$|meeting abstracts|abstracts with programs|invited talks", re.I)
# Journal of Vision prints the Vision Sciences Society meeting abstracts as articles numbered in the hundreds or
# thousands (10.1167/jov.25.9.2734); regular articles have small numbers.
JOV_ABSTRACT = re.compile(r"^10\.1167/jov\.\d+\.\d+\.(\d+)$", re.I)


def first_name(name):
    parts = [p for p in re.split(r"[\s.]+", name) if p]
    return parts[0].lower() if parts else ""


def same_first(a, b):
    a, b = a.lower(), b.lower()
    if len(a) == 1 or len(b) == 1:
        return a[0] == b[0]
    return a == b or any(a in s and b in s for s in NICKNAMES)


def people_index():
    idx = {}
    for p in load_json(PEOPLE):
        k = name_key(p["name"])
        idx.setdefault(k[1], []).append((first_name(p["name"]), p["slug"], "alumni" if p["group"] == "Alumni" else "current", p["name"]))
    return idx


def redwood_of(author, seed_ids, idx):
    if author.get("authorId") in seed_ids:
        return seed_ids[author["authorId"]]
    k = name_key(author["name"] or "")
    for first, slug, status, _ in idx.get(k[1], []):
        if same_first(first_name(author["name"]), first):
            return slug
    return None


def venue_of(p):
    v = (p.get("publicationVenue") or {}).get("name") or p.get("venue") or ((p.get("journal") or {}).get("name"))
    ext = p.get("externalIds") or {}
    if not v or v.lower() in ("arxiv.org", "arxiv"):
        if (ext.get("DOI") or "").startswith("10.1101/"):
            return "bioRxiv"
        return "arXiv" if ext.get("ArXiv") else (v or "")
    return v


SHORT_WORDS = {"a", "an", "of", "in", "at", "to", "on", "by", "as", "is", "or", "we", "vs", "it", "be", "do", "no", "up"}


WORDS = None


def _words():
    global WORDS
    if WORDS is None:
        try:
            WORDS = {w.strip().lower() for w in open("/usr/share/dict/words")}
        except OSError:
            WORDS = set()
    return WORDS


GREEK = {"mu": "μ", "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "sigma": "σ",
         "lambda": "λ", "theta": "θ", "pi": "π", "ell": "ℓ", "infty": "∞"}
KEEP_UPPER_SHORT = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "is", "of", "on", "or", "the",
                    "to", "via", "vs", "with", "its", "can", "how", "why", "not", "new", "two", "one", "are", "do"}


def clean_title(t):
    """Tidy titles as scraped: glued quotes, spaced punctuation, trailing periods, LaTeX, ALL CAPS, lost ligatures."""
    t = " ".join((t or "").split())
    # Lost ligatures ("e � ciently" -> "efficiently"); a stray one at the start is just dropped.
    def lig(m):
        pre, post = m.group(1), m.group(2)
        for l in ("ffi", "fi", "fl", "ff", "ffl"):
            if (pre + l + post).lower() in _words():
                return pre + l + post
        return pre + post
    t = re.sub(r"(\w*)\s*\ufffd\s*(\w*)", lig, t)
    # LaTeX: $\mu$P -> μP
    t = re.sub(r"\$([^$]*)\$", lambda m: re.sub(r"\\([a-z]+)", lambda g: GREEK.get(g.group(1), g.group(1)),
                                                  m.group(1)).replace("{", "").replace("}", ""), t)
    # Quotes glued to words: A"feature ODE"describing -> A “feature ODE” describing
    t = re.sub(r'\s*"\s*([^"]+?)\s*"\s*', lambda m: f" “{m.group(1)}” ", t).strip()
    t = re.sub(r"(“[^”]*”)\s+([,.:;?!])", r"\1\2", t)
    # Spaced punctuation: "Shape , Motion" / "( UoI )"
    t = re.sub(r"\s+([,:;?!.)\]’])", r"\1", t)
    t = re.sub(r"([(\[‘])\s+", r"\1", t)
    t = re.sub(r"\s*-\s+(?=[A-Z]{2,})|(?<=[A-Z])\s+-\s*", "-", t) if t.isupper() else t
    # Broken capitals from PDF headers: "O SCILLATOR" -> "OSCILLATOR" (a lone A or I is a real word, so not those)
    t = re.sub(r"\b(?![AI]\b)([A-Z]) ([A-Z]{3,})\b", r"\1\2", t)
    # ALL CAPS -> sentence case, keeping short non-words (MT, V1) and acronyms with digits.
    letters = [c for c in t if c.isalpha()]
    if len(letters) > 12 and sum(c.isupper() for c in letters) / len(letters) > 0.85:
        out = []
        for k, w in enumerate(t.split(" ")):
            core = re.sub(r"[^A-Za-z0-9]", "", w)
            if any(ch.isdigit() for ch in core) or (len(core) <= 3 and core.lower() not in KEEP_UPPER_SHORT):
                out.append(w)
            else:
                out.append(w.lower() if k else w[:1].upper() + w[1:].lower())
        t = " ".join(out)
    t = re.sub(r"(?<![.])\.$", "", t)  # trailing period (not an ellipsis)
    return " ".join(t.split())


def garbled(title):
    """Titles scraped from PDFs and slides: "23.2 n&v 919 MH NEW2", "EASONING ABOUT S PATIAL R ELATIONSHIPS",
    "Are there principles ? “ God is a hacker ” –", "Challenge 2018-Parts-based ... Organizers :"."""
    toks = re.findall(r"[A-Za-z0-9]+", title)
    # Fragments: bare numbers and 1-2 letter pieces, not counting ordinary short words or labels like V1 and MT.
    odd = [t for t in toks if (t.isdigit() or len(t) <= 2) and t.lower() not in SHORT_WORDS
           and not re.fullmatch(r"[A-Z]+\d*|[A-Z]\d+", t)]
    if not toks or len(odd) / len(toks) > 0.3:
        return True
    t = title.strip()
    if re.search(r"\s[?:;,)’”`]|[(‘“`]\s|\b(?![AI]\b)[A-Z] [A-Z]{3,}|[–-]$", t):  # "S PATIAL", not "A Theory"/"A MOTION"
        return True
    if re.search(r"^extended abstract track$|organizers\s*:", t, re.I):
        return True
    return False


def kind_of(p, venue):
    t = p["title"] or ""
    if JUNK.search(t.strip()):
        return "erratum-or-reply"
    ext = p.get("externalIds") or {}
    if garbled(t) and not (ext.get("DOI") or ext.get("ArXiv") or venue):
        return "garbled-title"  # a mangled title with nothing behind it: a scraped slide or listing
    if ABSTRACT_VENUES.search(venue or "") or re.match(r"poster session|panel discussion", t, re.I):
        return "abstract"
    m = JOV_ABSTRACT.match((p.get("externalIds") or {}).get("DOI") or "")
    if m and int(m.group(1)) >= 100:
        return "abstract"
    if re.search(r"thesis|dissertation", venue or "", re.I) or "Thesis" in (p.get("publicationTypes") or []):
        return "thesis"
    if re.search(r"\bpatent\b", venue or "", re.I):
        return "patent"
    return "paper"


def categorize(title, abstract, venue):
    t, a, v = f" {title.lower()} ", f" {(abstract or '').lower()} ", (venue or "").lower()
    score = {c: 0 for c in KEYWORDS}
    for c, kws in KEYWORDS.items():
        for kw in kws:
            kw = kw.lower()
            score[c] += 3 * t.count(kw) + min(a.count(kw), 3)
    for pat, c, w in VENUE_HINTS:
        if re.search(pat, v):
            score[c] += w
    best = max(score, key=score.get)
    return best if score[best] > 0 else None


def shingles(text, n=3):
    w = words(text)
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


PREPRINT_SERVERS = ("bioRxiv", "medRxiv", "Research Square")


def link_list(group):
    """[label, url] links for a paper across its versions (newest first): the published version, arXiv, a PDF.
    Falls back to the Semantic Scholar page when there's nothing else."""
    out, seen = [], set()
    def add(label, url):
        if url and url not in seen and label not in {l for l, _ in out}:
            seen.add(url); out.append([label, url])
    for r in group:
        doi, page = r["links"]["doi"], r["links"]["page"]
        if doi and "10.48550" not in doi:
            add(r["venue"] if r["venue"] in PREPRINT_SERVERS else "Published version", doi)
        # A page that isn't a DOI, arXiv or Semantic Scholar link: a hand-entered paper's or a corrected venue's.
        if page and page not in (doi, r["links"]["arxiv"], r["links"]["s2"]) and "semanticscholar.org" not in page:
            add(r["venue"] if r["venue"] in PREPRINT_SERVERS else "Published version", page)
    for r in group:
        add("arXiv", r["links"]["arxiv"])
    for r in group:
        add("PDF", r["links"]["pdf"])
    out.sort(key=lambda l: l[0] != "Published version")
    if not out:
        add("Semantic Scholar", group[0]["links"]["s2"] or group[0]["links"]["page"])
    return out


def group_versions(recs, forced):
    """Union papers that are the same work: near-identical titles, or near-identical abstracts, with shared authors.
    `forced` adds hand-curated pairs (papers-db/merges.json) for retitled versions these rules can't catch."""
    parent = {r["id"]: r["id"] for r in recs}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    info = [(r, norm_title(r["title"]), shingles(r["abstract"] or ""), {name_key(a["name"])[1] for a in r["authors"]})
            for r in recs]
    for i in range(len(info)):
        r1, t1, s1, a1 = info[i]
        for j in range(i + 1, len(info)):
            r2, t2, s2, a2 = info[j]
            shared = len(a1 & a2)
            if shared < min(2, len(a1), len(a2)):
                continue
            same = t1 == t2 or (min(len(t1), len(t2)) > 20 and SequenceMatcher(None, t1, t2).ratio() > 0.9)
            if not same and len(s1) > 40 and len(s2) > 40:
                same = len(s1 & s2) / len(s1 | s2) > 0.45
            if same:
                parent[find(r1["id"])] = find(r2["id"])
    for a, b in forced:
        if a in parent and b in parent:
            parent[find(a)] = find(b)
    groups = {}
    for r in recs:
        groups.setdefault(find(r["id"]), []).append(r)
    return [g for g in groups.values()]


def propagate_labels(recs, labels):
    """Papers without a hand label take the majority label of their 5 most similar hand-labeled papers (SPECTER2
    embeddings); the keyword guess stays only for papers with no embedding."""
    import hashlib, json as _json
    import numpy as np
    from embed import load_cache
    cache = load_cache("specter2")
    vec = {}
    for r in recs:
        h = hashlib.sha1(_json.dumps({"title": r["title"], "abstract": r["abstract"] or ""}, sort_keys=True).encode()).hexdigest()
        if h in cache:
            v = cache[h]; vec[r["id"]] = v / np.linalg.norm(v)
    known = [pid for pid in labels if pid in vec]
    if not known:
        return
    K = np.stack([vec[pid] for pid in known])
    for r in recs:
        if r["id"] in labels or r["id"] not in vec:
            continue
        top = np.argsort(-(K @ vec[r["id"]]))[:5]
        votes = {}
        for t in top:
            votes[labels[known[t]]] = votes.get(labels[known[t]], 0) + 1
        r["category"] = max(votes, key=votes.get)


def display_name(author, names):
    """Redwood people by their People-page name ("James B. Simon" -> "Jamie Simon"); everyone else without middle
    initials ("Daniel A. Butts" -> "Daniel Butts"). Middle names that aren't initials stay."""
    if author["redwood"] and author["redwood"] in names:
        return names[author["redwood"]]
    parts = (author["name"] or "").split()
    if len(parts) <= 2:
        return author["name"]
    middle = [w for w in parts[1:-1] if not re.fullmatch(r"[A-Z]\.?(-[A-Z]\.?)?", w)]
    return " ".join([parts[0], *middle, parts[-1]])


def recency(r):
    """Which version of a paper to show: a clean title first, then a real venue over arXiv/bioRxiv/none, then the
    newest, then the most cited."""
    published = bool(r["venue"]) and not re.search(r"arxiv|biorxiv", r["venue"], re.I)
    return (not garbled(r["title"]), published, r["date"] or f"{r['year'] or 0}-00-00", r["citations"] or 0)


def main():
    raw = load_json(os.path.join(DB, "raw.json"))
    enrich = load_json(os.path.join(DB, "enrich.json"), {})
    idx = people_index()
    names = {p["slug"]: p["name"] for p in load_json(PEOPLE)}
    seed_ids = {aid: slug for slug, d in raw.items() for aid in d["s2_ids"]}

    papers = {}
    for d in raw.values():
        for p in d["papers"]:
            papers[p["paperId"]] = p

    recs = []
    flags = load_json(os.path.join(DB, "flags.json"), {})
    title_fixes = {k: v for k, v in load_json(os.path.join(DB, "title-fixes.json"), {}).items() if not k.startswith("_")}
    year_fixes = {k: v for k, v in load_json(os.path.join(DB, "year-fixes.json"), {}).items() if not k.startswith("_")}
    fixes = load_json(os.path.join(DB, "curation.json"), {}).get("fix", {})
    labels = {k: v for k, v in load_json(os.path.join(DB, "labels.json"), {}).items() if v in CATEGORIES}
    for pid, p in papers.items():
        e = enrich.get(pid, {})
        ext = {**(p.get("externalIds") or {}), **({"ArXiv": e["arxiv_found"]} if e.get("arxiv_found") else {})}
        venue = venue_of(p)
        authors = []
        for a in p.get("authors") or []:
            slug = redwood_of(a, seed_ids, idx)
            authors.append({"name": a["name"], "s2": a.get("authorId"), "redwood": slug})
        arxiv = ext.get("ArXiv")
        doi = ext.get("DOI")
        # Semantic Scholar keeps a preprint's date on a record merged with its journal version; the journal's year
        # wins when it's later (Pre-saccadic enhancements in marmoset MT: bioRxiv 2022, J Neurosci 2024).
        pub = e.get("published")
        journal_year = int(pub[:4]) if pub and int(pub[:4]) > (p.get("year") or 0) else None
        if journal_year and len(pub) < 10:
            pub = None  # year or month only: no exact date
        rec = {
            "id": pid, "title": title_fixes.get(pid) or clean_title(p["title"]), "raw_title": " ".join((p["title"] or "").split()),
            "abstract": e.get("abstract") or p.get("abstract"),
            # A hand-fixed year also overrides a wrong one (e.g. an old paper's late arXiv upload), and drops the date.
            "year": year_fixes.get(pid) or journal_year or p.get("year"),
            "date": None if pid in year_fixes else (pub if journal_year else p.get("publicationDate")),
            "venue": venue, "kind": kind_of(p, venue),
            "authors": authors, "citations": p.get("citationCount"),
            "ids": {k: v for k, v in ext.items() if k in ("DOI", "ArXiv", "PubMed", "DBLP", "CorpusId")},
            "links": {
                "page": f"https://doi.org/{doi}" if doi and not doi.startswith("10.48550") else
                        (f"https://arxiv.org/abs/{arxiv}" if arxiv else p.get("url")),
                "arxiv": f"https://arxiv.org/abs/{arxiv}" if arxiv else None,
                "doi": f"https://doi.org/{doi}" if doi else None,
                "pdf": ((p.get("openAccessPdf") or {}).get("url") or None) or (f"https://arxiv.org/pdf/{arxiv}" if arxiv else None),
                "s2": None if pid.startswith("manual-") else p.get("url"),  # hand-entered: url is the paper's own page
            },
        }
        # Hand corrections (curation.json "fix"), e.g. a published version Semantic Scholar doesn't know about.
        fix = fixes.get(pid, {})
        for k in ("title", "venue", "year", "date"):
            if k in fix:
                rec[k] = fix[k]
        if "link" in fix:
            rec["links"]["page"] = fix["link"]
        # Hand labels (labels.json, from reading each paper against categories.md) win over the keyword guess.
        rec["category"] = labels.get(pid) or categorize(rec["title"], rec["abstract"], venue)
        recs.append(rec)

    propagate_labels(recs, labels)

    # Versions of the same work: the most recent (published over preprint on ties) is shown.
    real = [r for r in recs if r["kind"] == "paper"]
    primary_of = {}
    merges = {k: v for k, v in load_json(os.path.join(DB, "merges.json"), {}).items() if not k.startswith("_")}
    for g in group_versions(real, merges.items()):
        g.sort(key=recency, reverse=True)
        # A hand-merged target is always the version shown.
        target = next((r for r in g if r["id"] in merges.values()), None)
        if target:
            g.remove(target); g.insert(0, target)
        head = g[0]
        # A hand label on any version applies to the version shown.
        if head["id"] not in labels:
            lab = next((labels[r["id"]] for r in g if r["id"] in labels), None)
            if lab:
                head["category"] = lab
        # The newest version (often a conference record) can lack the abstract an older version has.
        if not head["abstract"]:
            head["abstract"] = next((r["abstract"] for r in g[1:] if r["abstract"]), None)
        head["versions"] = [{"id": r["id"], "title": r["title"], "venue": r["venue"], "year": r["year"]} for r in g[1:]]
        head["link_list"] = link_list(g)
        for r in g:
            primary_of[r["id"]] = head["id"]
            if r is not head:
                r["dup_of"] = head["id"]
    for r in recs:
        primary_of.setdefault(r["id"], r["id"])

    # Citation edges inside the database, onto primaries.
    by_doi = {r["ids"]["DOI"].lower(): r["id"] for r in recs if r["ids"].get("DOI")}
    by_arxiv = {r["ids"]["ArXiv"]: r["id"] for r in recs if r["ids"].get("ArXiv")}
    by_title = {norm_title(r["title"]): r["id"] for r in recs if len(norm_title(r["title"])) >= 30}
    edges = set()
    for r in recs:
        e = enrich.get(r["id"], {})
        targets = [t for t in e.get("refs_s2", []) if t in papers]
        for ref in e.get("refs_text", []):
            hit = by_doi.get((ref.get("doi") or "").lower())
            text = ref.get("text") or ""
            if not hit:
                m = re.search(r"(\d{4}\.\d{4,5})", text)
                hit = by_arxiv.get(m.group(1)) if m else None
            if not hit:
                nt = norm_title(text)
                hit = next((pid for t, pid in by_title.items() if t in nt), None)
            if hit:
                targets.append(hit)
        for t in targets:
            a, b = primary_of[r["id"]], primary_of[t]
            if a != b:
                edges.add((a, b))
    cites, cited_by = {}, {}
    for a, b in edges:
        cites.setdefault(a, []).append(b)
        cited_by.setdefault(b, []).append(a)

    # Candidate flag with reasons.
    for r in recs:
        r["cites"], r["cited_by"] = sorted(cites.get(r["id"], [])), sorted(cited_by.get(r["id"], []))
        r["ref_source"] = enrich.get(r["id"], {}).get("ref_source")
        why, ok = [], False
        seeds = [(i, a["redwood"]) for i, a in enumerate(r["authors"]) if a["redwood"] in WINDOWS]
        qualifying = [s for i, s in seeds if (r["year"] or 0) >= WINDOWS[s]
                      or (s in CAREER_DL and r["category"] == "learning-mech")]
        n = len(r["authors"])
        team = list(dict.fromkeys(a["redwood"] for a in r["authors"] if a["redwood"]))
        edge_redwood = [a["redwood"] for a in (r["authors"][:1] + r["authors"][-1:]) if a["redwood"]]
        if r["kind"] != "paper":
            why.append(r["kind"])
        elif r.get("dup_of"):
            why.append("older version")
        elif not r["year"]:
            why.append("no publication year found")
        elif len(team) >= 2 and n <= MEGA:
            ok = True
            why.append("Redwood authors: " + ", ".join(names.get(t, t) for t in team))
        elif not qualifying:
            why.append("outside year window")
        elif n > BIG_PAPER and not edge_redwood and not (team == ["james-simon"] and n <= MEGA):
            why.append(f"{n} authors, Redwood author in the middle")
        elif qualifying == ["james-simon"] and r["category"] == "physics":
            why.append("Simon physics (pre-ML)")
        else:
            ok = True
            if edge_redwood:
                why.append("Redwood " + ("last" if r["authors"][-1]["redwood"] else "first") + " author")
            why.append("in window: " + ", ".join(sorted({names.get(q, q) for q in qualifying})))
        if ok:
            why += flags.get(r["id"], [])
            if garbled(r["raw_title"]):
                why.append("title looks scraped: check")
        r["candidate"], r["why"] = ok, why

    recs.sort(key=lambda r: (r["date"] or str(r["year"] or 0)), reverse=True)
    save_json(os.path.join(DB, "papers.json"), {"categories": CATEGORIES, "windows": WINDOWS, "papers": recs})

    # The site gets primaries of real papers only; older versions are folded into their primary.
    slim = [{
        "id": r["id"], "title": r["title"], "year": r["year"], "date": r["date"], "venue": r["venue"], "abstract": r["abstract"],
        "authors": [[display_name(a, names), a["redwood"]] for a in r["authors"]], "citations": r["citations"],
        "link": r["links"]["page"], "pdf": r["links"]["pdf"], "links": r.get("link_list") or link_list([r]),
        "category": r["category"],
        "candidate": r["candidate"], "why": r["why"], "versions": r.get("versions", []),
        "cites": r["cites"], "cited_by": r["cited_by"],
    } for r in recs if r["kind"] in ("paper", "garbled-title") and not r.get("dup_of")]
    people = {p["slug"]: {"name": p["name"], "current": p["group"] != "Alumni"} for p in load_json(PEOPLE)}
    save_json(os.path.join(ROOT, "site", "src", "data", "papers.json"),
              {"categories": CATEGORIES, "people": people, "seeds": list(WINDOWS), "papers": slim})

    n_c = sum(r["candidate"] for r in recs)
    print(f"{len(recs)} records; {len(slim)} on the page; {n_c} candidates; {len(edges)} citation edges; "
          f"{sum(1 for r in recs if r.get('dup_of'))} older versions folded")
    kinds = {}
    for r in recs:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    print("kinds:", kinds)
    cats = {}
    for r in slim:
        if r["candidate"]:
            cats[r["category"]] = cats.get(r["category"], 0) + 1
    print("candidate categories:", cats)


if __name__ == "__main__":
    main()
