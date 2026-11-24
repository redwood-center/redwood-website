"""Runs ON A NODE (CPU is plenty): SPECTER2 embeddings for papers in a JSONL file.

    .venv/bin/python specter2_node.py in.jsonl out.npy     # each line: {"title": ..., "abstract": ...}

Uses allenai/specter2_base with the "proximity" adapter (allenai/specter2), the variant meant for finding related
papers, on title [SEP] abstract, CLS vector. Rows of out.npy follow the input lines.
"""
import json
import sys

import numpy as np
import torch
from adapters import AutoAdapterModel
from transformers import AutoTokenizer

src, dst = sys.argv[1], sys.argv[2]
rows = [json.loads(l) for l in open(src)]
tok = AutoTokenizer.from_pretrained("allenai/specter2_base")
model = AutoAdapterModel.from_pretrained("allenai/specter2_base")
model.load_adapter("allenai/specter2", source="hf", load_as="specter2", set_active=True)
# The load prints "none are activated" anyway; output matches S2's published specter_v2 vectors (median cosine 1.000).
model.set_active_adapters("specter2")
model.eval()
torch.set_num_threads(32)
out = []
with torch.no_grad():
    for i in range(0, len(rows), 16):
        batch = [r["title"] + tok.sep_token + (r.get("abstract") or "") for r in rows[i:i + 16]]
        enc = tok(batch, padding=True, truncation=True, max_length=512, return_tensors="pt", return_token_type_ids=False)
        out.append(model(**enc).last_hidden_state[:, 0, :].numpy())
np.save(dst, np.concatenate(out).astype(np.float32))
print(f"embedded {len(rows)} papers -> {dst}")
