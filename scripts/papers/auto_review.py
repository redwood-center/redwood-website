"""Step 6: decide what can be decided without Jamie, so the review page only asks about real judgment calls.

Rules (Jamie, 2026-10-27), applied to flagged papers Jamie hasn't already decided:
- two or more Redwood people on the paper -> In (the >50-author cap is already applied when flagging);
- conference abstracts and talk summaries -> Out (not papers);
- otherwise one Redwood person: Claude's judgment, listed below by title; anything not listed -> In.
Papers listed under ASK get no decision and stay in "To review".

Output: papers-db/auto-review.json {paperId: {"status": "in"|"out", "why": str}}. Jamie's own choices
(papers-db/review.json) always win over these.
"""
import os
import re

from common import DB, load_json, save_json

# Claude's calls on single-Redwood-author papers (2026-10-27). Matched by title prefix.
OUT = {
    "Avalon: A Benchmark for RL Generalization": "not a Redwood paper (Jamie)",
    "Tune As You Scale": "not a Redwood paper (Jamie)",
    "Homophilic relations in a formal organization": "a different Daniel Kunin",
    "Spatiotemporal integration in area MT": "conference abstract; the record's abstract is another paper's",
    "Yeti: A compact protein structure tokenizer": "Bouchard's LBNL work outside Redwood's science",
    "AutoCT: Automated CT registration": "Bouchard's LBNL work outside Redwood's science",
    "DL-TODA: A Deep Learning Tool for Omics": "Bouchard's LBNL work outside Redwood's science",
    "The Artificial Intelligence Ontology": "Bouchard's LBNL work outside Redwood's science",
    "Time-series ML-regression on Graphcore": "Bouchard's LBNL work outside Redwood's science",
    "Tent: Fully Test-Time Adaptation": "Darrell-group paper, not Redwood's (Jamie)",
    "Dynamic Scale Inference by Entropy Minimization": "Darrell-group paper, not Redwood's (Jamie)",
    "Neural Computations for Active Perception": "a lecture, not a paper (Jamie)",
    "Retinal Oscillations Carry Visual Information to Cortex": "published 2009, before the 10-year window",
    "A new method for parameter estimation in probabilistic models": "2011 PRL paper (arXiv copy posted 2020), before the window",
}
ASK = {}  # none left (Jamie decided Tent, Dynamic Scale Inference and the lecture, 2026-10-27)
NOT_A_PAPER = re.compile(r"annual meeting$|^ismrm", re.I)


def main():
    db = load_json(os.path.join(DB, "papers.json"))["papers"]
    review = load_json(os.path.join(DB, "review.json"), {})
    out, counts = {}, {}

    def decide(r, status, why):
        out[r["id"]] = {"status": status, "why": why}
        counts[why if status == "out" else status] = counts.get(why if status == "out" else status, 0) + 1

    for r in db:
        if not r["candidate"] or review.get(r["id"], {}).get("status"):
            continue
        title = r["title"]
        team = list(dict.fromkeys(a["redwood"] for a in r["authors"] if a["redwood"]))
        hit = lambda table: next((why for pre, why in table.items() if title.startswith(pre)), None)
        if hit(OUT):
            decide(r, "out", hit(OUT))
        elif NOT_A_PAPER.search(r["venue"] or "") or (r["abstract"] or "").startswith("Summary form only given"):
            decide(r, "out", "conference abstract or talk summary")
        elif len(team) >= 2:
            decide(r, "in", "2+ Redwood authors")
        elif hit(ASK):
            counts["left for Jamie"] = counts.get("left for Jamie", 0) + 1
        else:
            decide(r, "in", "Claude's call")
    save_json(os.path.join(DB, "auto-review.json"), out)
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"{v:4}  {k}")


if __name__ == "__main__":
    main()
