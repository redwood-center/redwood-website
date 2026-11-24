"""Click-through comparison of candidate sets for the third hero grid (receptive fields of real neurons).

Shows each set as it would sit on the homepage, next to the two existing grids. For each set the page starts
from 48 high-scoring fields with a spread of orientations; "Edit" shows the whole pool, where clicking a field
adds or removes it, and the chosen IDs can be copied for --select. Sets with higher-resolution versions
(gray22, gray44) can be shown at those sizes too.

    python3 scripts/figures/rf_compare.py      # writes out/rf-compare.html
"""
import json
import os

import numpy as np

from filterlib import HERE, OUT, SITE_DATA

SETS = [
    ("M", "macaque-candidates.json", "Macaque V1, measured (zoomed in)",
     "Simple cells in macaque V1, mapped by reverse correlation (Ringach 2002 data), as shown in Zylberberg, "
     "Murphy &amp; DeWeese 2011, Fig. 3A (CC BY): 48 of the 98 cells shown there, each cropped around the field."),
    ("Mfull", "macaque-candidates.json", "Macaque V1, measured (whole frame)",
     "The same macaque cells as set 1 (48 of the 98 in the figure), each shown in its whole original frame."),
    ("G", "macaque-candidates.json", "Macaque V1, Gabor fits",
     "Gabor fits to Ringach's macaque cells, corrected for eccentricity, from Rehn &amp; Sommer 2007, Fig. 5 "
     "(48 of the 128 shown there)."),
    ("S", "mouse-candidates.json", "Mouse V1, natural images",
     "48 mouse V1 neurons, recorded with two-photon imaging while the mouse viewed 2,800 natural images "
     "(Stringer, Pachitariu et al. 2019; CC BY-NC); fields estimated by ridge regression."),
]


def orientation(gray, pad=32):
    g = np.array(gray).reshape(11, 11)
    P = np.abs(np.fft.fftshift(np.fft.fft2(g - g.mean(), s=(pad, pad)))) ** 2
    py, px = np.unravel_index(np.argmax(P), P.shape)
    return np.degrees(np.arctan2(py - pad // 2, px - pad // 2)) % 180


def pick(cands, n=48, bins=8):
    """Best-scoring first, at most n/bins + 2 per orientation bin, so the grid isn't all one angle."""
    cap, counts, out = n // bins + 2, {}, []
    for c in sorted(cands, key=lambda c: -c["score"]):
        b = int(orientation(c["gray"]) // (180 / bins))
        if counts.get(b, 0) < cap:
            out.append(c["id"])
            counts[b] = counts.get(b, 0) + 1
        if len(out) == n:
            break
    rng = np.random.default_rng(0)
    return [out[i] for i in rng.permutation(len(out))]


def main():
    sets, starts = [], {}
    for key, fname, title, blurb in SETS:
        with open(os.path.join(OUT, fname)) as fh:
            cands = json.load(fh)[key]
        # Mfull is the same cells as M in their whole frames, so it starts from M's pick.
        starts[key] = starts["M"] if key == "Mfull" else pick(cands)
        sets.append({"key": key, "title": title, "blurb": blurb, "start": starts[key],
                     "pool": [{k: v for k, v in c.items() if k in ("id", "score") or k.startswith("gray")}
                              for c in sorted(cands, key=lambda c: -c["score"])]})
    fixed = {}
    for name in ("olshausen", "alexnet"):
        with open(os.path.join(SITE_DATA, f"filters-{name}.json")) as fh:
            fixed[name] = json.load(fh)["filters"]
    with open(os.path.join(HERE, "rf-compare.template.html")) as fh:
        page = fh.read().replace("/*__DATA__*/null", json.dumps({"sets": sets, "fixed": fixed}))
    path = os.path.join(OUT, "rf-compare.html")
    with open(path, "w") as fh:
        fh.write(page)
    print(path)


if __name__ == "__main__":
    main()
