"""Step 4: embed every paper (title + abstract) with two models, for the paper map.

- OpenAI text-embedding-3-large (API; OPENAI_API_KEY, which lives in ~/.zshrc).
- SPECTER2 (Allen AI's scientific-paper model), run on a node so its ~0.5 GB of weights stay off the laptop:
  the texts go to node-003, scripts/papers/specter2_node.py embeds them on CPU, the vectors come back.

Embeddings are cached by text hash in papers-db/emb/<model>.npz, so reruns only embed new or changed papers.
    python3 embed.py [openai|specter2 ...]
"""
import hashlib
import json
import os
import subprocess
import sys

import numpy as np

from common import DB, HERE, load_json

EMB = os.path.join(DB, "emb")
NODE = "node-003"
RSSH = os.path.expanduser("~/Projects/research-infra/scripts/rssh")
REMOTE = "redwood-papers-embed"


def texts():
    """Primaries of real papers: the set the map can show."""
    out = []
    for r in load_json(os.path.join(DB, "papers.json"))["papers"]:
        if r["kind"] == "paper" and not r.get("dup_of"):
            t = {"title": r["title"], "abstract": r["abstract"] or ""}
            t["hash"] = hashlib.sha1(json.dumps(t, sort_keys=True).encode()).hexdigest()
            out.append(t)
    return out


def load_cache(name):
    path = os.path.join(EMB, f"{name}.npz")
    if not os.path.exists(path):
        return {}
    z = np.load(path)
    return dict(zip(z["hashes"].tolist(), z["vectors"]))


def save_cache(name, cache):
    os.makedirs(EMB, exist_ok=True)
    hs = sorted(cache)
    np.savez(os.path.join(EMB, f"{name}.npz"), hashes=np.array(hs), vectors=np.stack([cache[h] for h in hs]))


def embed_openai(todo):
    from openai import OpenAI
    client = OpenAI()
    vecs = []
    for i in range(0, len(todo), 256):
        batch = [f"{t['title']}\n\n{t['abstract']}".strip()[:24000] for t in todo[i:i + 256]]
        resp = client.embeddings.create(model="text-embedding-3-large", input=batch)
        vecs += [np.array(d.embedding, dtype=np.float32) for d in resp.data]
    return vecs


def embed_specter2(todo):
    tmp = os.path.join(EMB, "specter2-todo.jsonl")
    with open(tmp, "w") as f:
        for t in todo:
            f.write(json.dumps({"title": t["title"], "abstract": t["abstract"]}) + "\n")
    host = f"host@{NODE}"
    subprocess.run(["scp", "-q", tmp, os.path.join(HERE, "specter2_node.py"), f"{host}:{REMOTE}/"], check=True)
    subprocess.run([RSSH, "-t", "1800", f"22:{NODE}",
                    f"cd {REMOTE} && .venv/bin/python specter2_node.py specter2-todo.jsonl specter2-out.npy"], check=True)
    out = os.path.join(EMB, "specter2-out.npy")
    subprocess.run(["scp", "-q", f"{host}:{REMOTE}/specter2-out.npy", out], check=True)
    return list(np.load(out))


def main():
    models = sys.argv[1:] or ["specter2"]  # "openai" still works if asked for
    ts = texts()
    for name in models:
        cache = load_cache(name)
        todo = [t for t in ts if t["hash"] not in cache]
        if todo:
            vecs = (embed_openai if name == "openai" else embed_specter2)(todo)
            for t, v in zip(todo, vecs):
                cache[t["hash"]] = v
            save_cache(name, cache)
        print(f"{name}: {len(ts)} papers, {len(todo)} newly embedded")


if __name__ == "__main__":
    main()
