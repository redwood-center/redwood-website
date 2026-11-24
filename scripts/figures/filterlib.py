"""Shared helpers for choosing receptive-field / filter images for the homepage hero.

- spectral_score: how Gabor-like a grayscale patch is (one dominant orientation + frequency).
- write_picker: writes a self-contained click-to-select HTML page from filter-picker.template.html.
- write_site_data: writes the chosen filters, in order, to site/src/data/ for the hero grids.
"""
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
SITE_DATA = os.path.join(HERE, "..", "..", "site", "src", "data")


def normalize(g):
    g = g - g.mean()
    return g / (np.abs(g).max() + 1e-12)


def spectral_score(gray, pad=44):
    """Fraction of spectral power near the single strongest (orientation, frequency) peak,
    down-weighted when that peak is near DC (blobs) or Nyquist (checkerboards)."""
    g = gray - gray.mean()
    P = np.abs(np.fft.fftshift(np.fft.fft2(g, s=(pad, pad)))) ** 2
    yy, xx = np.mgrid[:pad, :pad] - pad // 2
    r = np.hypot(xx, yy)
    py, px = np.unravel_index(np.argmax(P), P.shape)
    dy, dx = py - pad // 2, px - pad // 2
    near = (np.hypot(yy - dy, xx - dx) <= 4) | (np.hypot(yy + dy, xx + dx) <= 4)
    concentration = float(P[near].sum() / (P.sum() + 1e-12))
    peak_r = float(r[py, px])
    band = 1.0 if 5 <= peak_r <= 20 else 0.3  # Nyquist is at r = pad/2 = 22
    return concentration * band, {"concentration": round(concentration, 3), "peak_r": round(peak_r, 1)}


def write_picker(name, title, blurb, size, candidates, preselected, target=48):
    """candidates: list of {"id", "score", "gray"} sorted best-first; gray is a flat size*size list."""
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(HERE, "filter-picker.template.html")) as fh:
        page = fh.read()
    data = {"title": title, "blurb": blurb, "size": size, "target": target, "preselected": preselected,
            "candidates": [{k: c[k] for k in ("id", "score", "gray")} for c in candidates]}
    page = page.replace("/*__DATA__*/null", json.dumps(data))
    path = os.path.join(OUT, f"{name}-picker.html")
    with open(path, "w") as fh:
        fh.write(page)
    return path


def write_site_data(name, size, source, candidates, ids):
    by_id = {c["id"]: c for c in candidates}
    missing = [i for i in ids if i not in by_id]
    if missing:
        raise SystemExit(f"unknown ids: {' '.join(missing)}")
    path = os.path.join(SITE_DATA, f"filters-{name}.json")
    data = {"size": size, "source": source, "ids": ids, "filters": [by_id[i]["gray"] for i in ids]}
    if all("rgb" in by_id[i] for i in ids):
        data["colors"] = [by_id[i]["rgb"] for i in ids]  # HWC, each normalized to [-1, 1]
    with open(path, "w") as fh:
        json.dump(data, fh)
    return path
