"""Step 2: fill in missing abstracts and collect each paper's reference list.

References come from Semantic Scholar; for papers it has none for, we read the bibliography from arXiv's HTML
rendering, then fall back to Crossref's publisher-deposited references.

It also looks up when the journal version came out (PubMed, then Crossref): Semantic Scholar often merges a preprint
with its later journal version but keeps the preprint's date.

Output: papers-db/enrich.json  {paperId: {"abstract": str|None, "refs_s2": [ids], "refs_text": [{doi?, text}],
                                          "ref_source": str, "published": "YYYY[-MM[-DD]]"|None}}
"""
import os
import re
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

from common import DB, MAILTO, S2, fetch, load_json, norm_title, save_json


def all_papers():
    raw = load_json(os.path.join(DB, "raw.json"))
    out = {}
    for person in raw.values():
        for p in person["papers"]:
            out[p["paperId"]] = p
    return out


def s2_refs(ids):
    refs = {}
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        d = fetch(f"{S2}/paper/batch", {"fields": "references.paperId,references.externalIds"}, body={"ids": chunk},
                  max_age_days=90)  # reference lists fill in after publication
        for pid, p in zip(chunk, d or []):
            refs[pid] = [r for r in ((p or {}).get("references") or []) if r.get("paperId") or r.get("externalIds")]
    return refs


def arxiv_bib(arxiv_id):
    html = fetch(f"https://arxiv.org/html/{arxiv_id}", kind="text", gap=3)
    if not html:
        return []
    items = BeautifulSoup(html, "html.parser").select("li.ltx_bibitem")
    return [{"text": " ".join(li.get_text(" ").split())} for li in items]


def arxiv_id_for_title(title):
    """arXiv ID for an exact (normalized) title match, for conference versions that carry no arXiv ID."""
    words = [w for w in re.findall(r"[A-Za-z0-9]+", title) if len(w) > 3][:12]
    if len(words) < 3:
        return None
    xml = fetch("https://export.arxiv.org/api/query", {"search_query": " AND ".join(f"ti:{w}" for w in words),
                                                      "max_results": 5}, kind="text", gap=3)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for e in ET.fromstring(xml).findall("a:entry", ns):
        if norm_title(e.find("a:title", ns).text) == norm_title(title):
            return re.sub(r"v\d+$", "", e.find("a:id", ns).text.rsplit("/abs/", 1)[-1])
    return None


def crossref_refs(doi):
    d = fetch(f"https://api.crossref.org/works/{doi}", {"mailto": MAILTO}, gap=0.3)
    refs = ((d or {}).get("message") or {}).get("reference") or []
    return [{"doi": (r.get("DOI") or "").lower() or None,
             "text": " ".join(filter(None, [r.get("article-title"), r.get("unstructured"), r.get("journal-title")]))}
            for r in refs]


def arxiv_abstracts(ids):
    out = {}
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        xml = fetch("https://export.arxiv.org/api/query", {"id_list": ",".join(chunk), "max_results": 50}, kind="text", gap=3)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for e in ET.fromstring(xml).findall("a:entry", ns):
            aid = re.sub(r"v\d+$", "", e.find("a:id", ns).text.rsplit("/abs/", 1)[-1])
            s = e.find("a:summary", ns)
            if s is not None and s.text:
                out[aid] = " ".join(s.text.split())
    return out


def openalex_abstracts(dois):
    out = {}
    for i in range(0, len(dois), 40):
        chunk = dois[i:i + 40]
        d = fetch("https://api.openalex.org/works", {"filter": "doi:" + "|".join(chunk), "per_page": 50,
                                                     "select": "doi,abstract_inverted_index", "mailto": MAILTO}, gap=0.2)
        for w in (d or {}).get("results", []):
            inv = w.get("abstract_inverted_index")
            if inv and w.get("doi"):
                pos = sorted((i, word) for word, idx in inv.items() for i in idx)
                out[w["doi"].lower().replace("https://doi.org/", "")] = " ".join(word for _, word in pos)
    return out


def crossref_abstract(doi):
    d = fetch(f"https://api.crossref.org/works/{doi}", {"mailto": MAILTO}, gap=0.3)
    a = ((d or {}).get("message") or {}).get("abstract")
    if not a:
        return None
    text = " ".join(BeautifulSoup(a, "html.parser").get_text(" ").split())
    return re.sub(r"^abstract\s*", "", text, flags=re.I) or None


def pubmed_abstract(pmid):
    xml = fetch("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                {"db": "pubmed", "id": pmid, "retmode": "xml"}, kind="text", gap=0.4)
    if not xml:
        return None
    parts = [" ".join(e.itertext()) for e in ET.fromstring(xml).iter("AbstractText")]
    return " ".join(" ".join(parts).split()) or None


MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
PREPRINT_DOI = ("10.1101/", "10.48550/", "10.21203/", "10.20944/")  # bioRxiv/medRxiv, arXiv, Research Square, Preprints


def _pubmed_date(s):
    """'2024 Jan 24', '2023 Nov-Dec', '2024' -> '2024-01-24', '2023-11', '2024'."""
    m = re.match(r"(\d{4})(?:\s+([A-Za-z]{3}))?(?:\s+(\d{1,2}))?", s or "")
    if not m:
        return None
    y, mon, d = m.group(1), MONTHS.get((m.group(2) or "").lower()), m.group(3)
    return y + (f"-{mon:02d}" if mon else "") + (f"-{int(d):02d}" if mon and d else "")


def pubmed_dates(pmids):
    out = {}
    for i in range(0, len(pmids), 200):
        chunk = pmids[i:i + 200]
        d = fetch("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                  {"db": "pubmed", "id": ",".join(chunk), "retmode": "json"}, gap=0.4)
        for pmid in chunk:
            r = ((d or {}).get("result") or {}).get(pmid) or {}
            dates = [x for x in (_pubmed_date(r.get("epubdate")), _pubmed_date(r.get("pubdate"))) if x]
            if dates:
                out[pmid] = min(dates)
    return out


def crossref_date(doi):
    d = fetch(f"https://api.crossref.org/works/{doi}", {"mailto": MAILTO}, gap=0.3)
    parts = ((((d or {}).get("message") or {}).get("published") or {}).get("date-parts") or [[None]])[0]
    return "-".join(f"{x:02d}" if i else str(x) for i, x in enumerate(parts)) if parts and parts[0] else None


def arxiv_abstract_by_title(title):
    aid = arxiv_id_for_title(title)
    return arxiv_abstracts([aid]).get(aid) if aid else None


def main():
    papers = all_papers()
    ids = list(papers)
    print(f"{len(ids)} papers")
    refs = s2_refs([i for i in ids if not i.startswith("manual-")])  # hand-entered papers aren't on S2
    out = {}
    need_arxiv_abs, need_doi_abs = [], []
    for pid, p in papers.items():
        ext = p.get("externalIds") or {}
        e = {"abstract": p.get("abstract"), "refs_s2": [r["paperId"] for r in refs.get(pid, []) if r.get("paperId")],
             "refs_text": [], "ref_source": "s2"}
        if not e["refs_s2"]:
            if not ext.get("ArXiv") and p.get("title"):
                found = arxiv_id_for_title(p["title"])
                if found:
                    ext = {**ext, "ArXiv": found}
                    e["arxiv_found"] = found
            if ext.get("ArXiv"):
                e["refs_text"], e["ref_source"] = arxiv_bib(ext["ArXiv"]), "arxiv-html"
            if not e["refs_text"] and ext.get("DOI"):
                e["refs_text"], e["ref_source"] = crossref_refs(ext["DOI"]), "crossref"
            if not e["refs_text"]:
                e["ref_source"] = None
        if not e["abstract"]:
            if ext.get("ArXiv"):
                need_arxiv_abs.append(ext["ArXiv"])
            elif ext.get("DOI"):
                need_doi_abs.append(ext["DOI"].lower())
        out[pid] = e
    ax, oa = arxiv_abstracts(need_arxiv_abs), openalex_abstracts(need_doi_abs)
    for pid, p in papers.items():
        ext = {**(p.get("externalIds") or {}), **({"ArXiv": out[pid]["arxiv_found"]} if out[pid].get("arxiv_found") else {})}
        e = out[pid]
        if not e["abstract"]:
            e["abstract"] = ax.get(ext.get("ArXiv")) or oa.get((ext.get("DOI") or "").lower())
        # Still nothing: the publisher's record, PubMed, then an arXiv version found by exact title.
        doi = ext.get("DOI") if ext.get("DOI") and not ext["DOI"].startswith("10.48550") else None
        if not e["abstract"] and doi:
            e["abstract"] = crossref_abstract(doi)
        if not e["abstract"] and ext.get("PubMed"):
            e["abstract"] = pubmed_abstract(ext["PubMed"])
        if not e["abstract"] and ext.get("ArXiv"):
            e["abstract"] = arxiv_abstracts([ext["ArXiv"]]).get(ext["ArXiv"])
        if not e["abstract"] and p.get("title") and not ext.get("ArXiv"):
            e["abstract"] = arxiv_abstract_by_title(p["title"])
    # The journal version's date, when the paper has one (a PubMed record or a non-preprint DOI).
    pm = pubmed_dates(sorted({(p.get("externalIds") or {}).get("PubMed") for p in papers.values()} - {None}))
    for pid, p in papers.items():
        ext = p.get("externalIds") or {}
        doi = ext.get("DOI") or ""
        out[pid]["published"] = pm.get(ext.get("PubMed")) or (
            crossref_date(doi) if doi and not doi.lower().startswith(PREPRINT_DOI) else None)
    src = {}
    for e in out.values():
        src[e["ref_source"]] = src.get(e["ref_source"], 0) + 1
    print("reference sources:", src)
    print("abstracts:", sum(1 for e in out.values() if e["abstract"]), "/", len(out))
    save_json(os.path.join(DB, "enrich.json"), out)


if __name__ == "__main__":
    main()
