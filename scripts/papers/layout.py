"""Step 5: compact embeddings for the live paper map, plus two quick quality checks per model.

The page runs t-SNE itself (tsnejs, like jamiesimon.io/t-sne), so it needs each paper's embedding. Full vectors are
3072/768 floats; we ship a 64-dim PCA of the unit-normalized vectors, quantized to int8 (~40 KB for 600 papers).
Vectors are centered first (removes the direction every paper shares); the compact vectors' cosine similarities
track the full centered ones closely (printed below).

Checks (higher is better):
- category agreement: share of each paper's 10 nearest neighbours (in the embedding) with the same category.
- citation closeness: for each Redwood paper that cites another, the percentile of the cited paper's similarity
  among all papers (100 = the nearest).

Output: site/src/data/papers-map.json  {"dims": 64, "models": {name: {"ids": [...], "vecs": base64 int8 rows}}}
"""
import base64
import hashlib
import json
import os

import numpy as np

from common import DB, ROOT, load_json, save_json
from embed import load_cache

MODELS = ["specter2"]  # Jamie picked SPECTER2 over OpenAI text-embedding-3-large (2026-10-27)
SEEDS = {"mike-deweese": "DeWeese", "bruno-olshausen": "Olshausen", "fritz-sommer": "Sommer",
         "kristofer-bouchard": "Bouchard", "jacob-yates": "Yates", "jorge-otero-millan": "Otero-Millan",
         "james-simon": "Simon", "dhruva-karkada": "Karkada", "daniel-kunin": "Kunin"}


def authorship_flags(ids, X, site):
    """Papers whose topic is far from everything else by that author: often a same-name stranger's paper.
    Score = mean similarity to the author's 5 most similar other papers; flag the low tail (z < -2)."""
    authors = {p["id"]: {a[1] for a in p["authors"] if a[1] in SEEDS} for p in site["papers"]}
    pos = {pid: i for i, pid in enumerate(ids)}
    S = X @ X.T
    flags = {}
    for slug, name in SEEDS.items():
        mine = [pos[pid] for pid in ids if slug in authors.get(pid, ())]
        if len(mine) < 8:
            continue
        sub = S[np.ix_(mine, mine)].copy()
        np.fill_diagonal(sub, -np.inf)
        score = np.sort(sub, axis=1)[:, -5:].mean(1)
        z = (score - score.mean()) / (score.std() + 1e-9)
        for k, zi in zip(mine, z):
            if zi < -2:
                flags.setdefault(ids[k], []).append(f"unusual topic for {name}: check authorship")
    return flags
DIMS = 64


def main():
    site = load_json(os.path.join(ROOT, "site", "src", "data", "papers.json"))
    full = {r["id"]: r for r in load_json(os.path.join(DB, "papers.json"))["papers"]}
    review = load_json(os.path.join(DB, "review.json"), {})
    out = {"dims": DIMS, "models": {}}
    for name in MODELS:
        cache = load_cache(name)
        ids, X = [], []
        for p in site["papers"]:
            r = full[p["id"]]
            t = {"title": r["title"], "abstract": r["abstract"] or ""}
            h = hashlib.sha1(json.dumps(t, sort_keys=True).encode()).hexdigest()
            if h in cache:
                ids.append(p["id"]); X.append(cache[h])
        if len(ids) < 5:
            continue
        X = np.stack(X).astype(np.float64)
        X /= np.linalg.norm(X, axis=1, keepdims=True)
        S = X @ X.T

        cat = {p["id"]: (review.get(p["id"], {}).get("category") or p["category"]) for p in site["papers"]}
        nn = np.argsort(-S, axis=1)[:, 1:11]
        agree = np.mean([np.mean([cat[ids[j]] == cat[ids[i]] for j in row]) for i, row in enumerate(nn) if cat[ids[i]]])
        pos = {pid: i for i, pid in enumerate(ids)}
        pct = []
        for p in site["papers"]:
            for q in p["cites"]:
                if p["id"] in pos and q in pos:
                    row = np.delete(S[pos[p["id"]]], pos[p["id"]])
                    pct.append(100 * np.mean(row < S[pos[p["id"]], pos[q]]))

        # PCA to DIMS (centered), re-normalized, int8.
        k = min(DIMS, len(ids) - 1)
        Xc = X - X.mean(0)
        U, sv, Vt = np.linalg.svd(Xc, full_matrices=False)
        Z = Xc @ Vt[:k].T
        Z /= np.linalg.norm(Z, axis=1, keepdims=True)
        if k < DIMS:
            Z = np.pad(Z, ((0, 0), (0, DIMS - k)))
        q = np.clip(np.round(Z * 127 / np.abs(Z).max()), -127, 127).astype(np.int8)
        Zq = q.astype(np.float64); Zq /= np.linalg.norm(Zq, axis=1, keepdims=True) + 1e-12
        # Fidelity vs the full vectors after the same centering (centering is deliberate: it removes the direction
        # every paper shares, which otherwise squeezes all similarities toward 1).
        Xn = Xc / np.linalg.norm(Xc, axis=1, keepdims=True)
        iu = np.triu_indices(len(ids), 1)
        corr = np.corrcoef((Xn @ Xn.T)[iu], (Zq @ Zq.T)[iu])[0, 1]
        print(f"{name}: {len(ids)} papers; category agreement {agree:.2f}; citation closeness "
              f"{np.median(pct) if pct else float('nan'):.0f}th pct over {len(pct)} citations; "
              f"compact vs full (centered) similarity r = {corr:.3f}")
        out["models"][name] = {"ids": ids, "vecs": base64.b64encode(q.tobytes()).decode()}
        if name == "specter2":
            flags = authorship_flags(ids, X, site)
            save_json(os.path.join(DB, "flags.json"), flags)
            print(f"  authorship flags: {len(flags)}")
    save_json(os.path.join(ROOT, "site", "src", "data", "papers-map.json"), out)


if __name__ == "__main__":
    main()
