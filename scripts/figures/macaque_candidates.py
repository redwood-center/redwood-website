"""Receptive fields measured from real neurons, for a third hero grid next to the model filters.

Sources (figure files in research-data/receptive-fields/):
- M: macaque V1 simple cells, raw reverse-correlation maps (Ringach 2002 data), as shown in Zylberberg, Murphy &
  DeWeese 2011, PLoS Comput Biol 7:e1002250, Fig. 3A (98 cells; CC BY). Each cell is shown at its own scale.
- G: the same macaque data as Gabor fits, scale-corrected for eccentricity, from Rehn & Sommer 2007,
  J Comput Neurosci 22:135, Fig. 5 (128 cells; author's preprint, www.rctn.org/fsommer/papers/).
Each cell is cut out of the figure, background-subtracted, and resampled to 11x11 to match the other two grids:
"M" zooms to a window around the cell's energy, "Mfull" keeps the whole frame. IDs are M<n> / G<n>, numbered
row-major in the source figure.

    python3 scripts/figures/macaque_candidates.py                  # candidates JSON for the comparison page
    python3 scripts/figures/macaque_candidates.py --select auto    # write site/src/data/filters-macaque.json
"""
import argparse
import json
import os

import numpy as np
from PIL import Image

from filterlib import HERE, normalize, spectral_score, write_site_data

SRC = os.path.join(HERE, "..", "..", "research-data", "receptive-fields")
K = 11
HI_RES = (22, 44)  # the source cells are ~70 px across, so the raw maps can also be shown sharper

# Cell boundaries in the source figures (pixels), found from the grid lines.
ZYL_COLS = [(14, 91), (91, 168), (168, 246), (278, 356), (356, 433), (433, 511), (511, 588)]
ZYL_ROWS = [118, 189, 261, 333, 406, 478, 550, 621, 693, 765, 837, 909, 980, 1052, 1125]
RS_COLS = [166, 185, 204, 222, 241, 260, 278, 297, 316]
RS_ROWS = [23, 42, 61, 79, 98, 117, 135, 154, 173, 192, 211, 229, 248, 267, 285, 304, 323]


def resample(a, size):
    return np.asarray(Image.fromarray(a.astype(np.float32)).resize((size, size), Image.BOX))


def to_patch(cell, zoom=None, size=K):
    """Background-subtract a cell and resample it to size x size. With zoom, first crop a square window around the
    cell's energy, zoom times the energy's spread wide, so small fields aren't lost in a big frame."""
    border = np.concatenate([cell[0], cell[-1], cell[:, 0], cell[:, -1]])
    f = cell - np.median(border)
    if zoom:
        e = f ** 2
        h, w = f.shape
        yy, xx = np.mgrid[:h, :w]
        cy, cx = (e * yy).sum() / e.sum(), (e * xx).sum() / e.sum()
        sd = np.sqrt((e * ((yy - cy) ** 2 + (xx - cx) ** 2)).sum() / e.sum())
        side = int(np.clip(round(zoom * sd), K, min(h, w)))
        y0 = int(np.clip(round(cy - side / 2), 0, h - side))
        x0 = int(np.clip(round(cx - side / 2), 0, w - side))
        f = f[y0:y0 + side, x0:x0 + side]
    return normalize(resample(f, size))


def cells(path, cols, rows, inset):
    im = np.asarray(Image.open(path).convert("L")).astype(float)
    for r0, r1 in zip(rows, rows[1:]):
        for c0, c1 in cols:
            yield im[r0 + inset:r1 - inset, c0 + inset:c1 - inset]


def candidates():
    out = {"M": [], "Mfull": [], "G": []}
    zyl = os.path.join(SRC, "zylberberg2011-fig3.tif")
    for i, c in enumerate(cells(zyl, ZYL_COLS, ZYL_ROWS, 3)):
        for key, zoom in (("M", 3.5), ("Mfull", None)):
            p = to_patch(c, zoom)
            s, _ = spectral_score(p)
            hi = {f"gray{n}": np.round(to_patch(c, zoom, n), 3).reshape(-1).tolist() for n in HI_RES}
            out[key].append({"id": f"M{i}", "score": round(s, 4), "gray": np.round(p, 3).reshape(-1).tolist(), **hi})
    rs = os.path.join(SRC, "rehn-sommer2007-fig5.jpeg")
    rs_cols = list(zip(RS_COLS, RS_COLS[1:]))
    for i, c in enumerate(cells(rs, rs_cols, RS_ROWS, 2)):
        p = to_patch(c, zoom=3.0)
        s, _ = spectral_score(p)
        out["G"].append({"id": f"G{i}", "score": round(s, 4), "gray": np.round(p, 3).reshape(-1).tolist()})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--select", help='IDs from set M, in display order, to write to the site ("auto": the '
                                     "comparison page's automatic pick)")
    ap.add_argument("--size", type=int, default=44, choices=(K, *HI_RES))
    args = ap.parse_args()

    data = candidates()
    if args.select:
        from rf_compare import pick
        ids = pick(data["M"]) if args.select == "auto" else args.select.split()
        key = "gray" if args.size == K else f"gray{args.size}"
        cands = [{"id": c["id"], "gray": c[key]} for c in data["M"]]
        print(write_site_data("macaque", args.size, "Macaque V1 simple cells (Ringach 2002 data) from Zylberberg et "
                              f"al. 2011 Fig. 3A, cropped around each field, {args.size}x{args.size}", cands, ids))
        return
    path = os.path.join(HERE, "out", "macaque-candidates.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(data, fh)
    print({k: len(v) for k, v in data.items()}, "->", path)


if __name__ == "__main__":
    main()
