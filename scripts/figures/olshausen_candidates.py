"""Rank sparse-coding basis functions by how Gabor-like they are; build a picker; write the chosen set.

Source: the Olshausen sparse-coding dictionary shipped with the Redwood Center's library
(github.com/rctn/sparsecoding, sparsecoding/data/dictionaries/olshausen/olshausen-1.5x_overcomplete.p):
384 basis functions, 16x16, learned from natural images. Each is cropped to an 11x11 window
centered on its energy so it matches the AlexNet filters' size. IDs are O<n>.

    python3 scripts/figures/olshausen_candidates.py                   # picker: out/olshausen-picker.html
    python3 scripts/figures/olshausen_candidates.py --select "O12 ..." # write site/src/data/filters-olshausen.json
"""
import argparse
import os
import pickle

import numpy as np

from filterlib import normalize, spectral_score, write_picker, write_site_data

DICT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "research-data", "rctn-sparsecoding",
                    "sparsecoding", "data", "dictionaries", "olshausen", "olshausen-1.5x_overcomplete.p")
CROP = 11


class NumpyOnlyUnpickler(pickle.Unpickler):
    """The file is a pickled ndarray; refuse anything else a pickle could reference."""
    ALLOWED = {("numpy.core.multiarray", "_reconstruct"), ("numpy._core.multiarray", "_reconstruct"),
               ("numpy", "ndarray"), ("numpy", "dtype")}

    def find_class(self, module, name):
        if (module, name) not in self.ALLOWED:
            raise pickle.UnpicklingError(f"blocked {module}.{name}")
        return super().find_class(module, name)


def crop(f, k=CROP):
    """k x k window centered on the basis function's energy; returns (crop, energy fraction kept)."""
    e = f ** 2
    n = f.shape[0]
    yy, xx = np.mgrid[:n, :n]
    cy, cx = (e * yy).sum() / e.sum(), (e * xx).sum() / e.sum()
    y0 = int(np.clip(round(cy - (k - 1) / 2), 0, n - k))
    x0 = int(np.clip(round(cx - (k - 1) / 2), 0, n - k))
    c = f[y0:y0 + k, x0:x0 + k]
    return c, float((c ** 2).sum() / e.sum())


def candidates():
    with open(DICT, "rb") as fh:
        D = NumpyOnlyUnpickler(fh).load()  # (256, 384)
    n = int(round(np.sqrt(D.shape[0])))
    out = []
    for j in range(D.shape[1]):
        c, kept = crop(D[:, j].reshape(n, n))
        s, _ = spectral_score(c)
        out.append({"id": f"O{j}", "score": round(s * kept, 4),
                    "gray": np.round(normalize(c), 3).reshape(-1).tolist()})
    return sorted(out, key=lambda c: -c["score"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--select", help="space-separated IDs, in display order, to write to the site")
    args = ap.parse_args()

    cands = candidates()
    if args.select:
        print(write_site_data("olshausen", CROP, "Olshausen sparse-coding dictionary (rctn/sparsecoding), 11x11 crops",
                              cands, args.select.split()))
        return
    pre = [c["id"] for c in cands[:48]]
    print(write_picker("olshausen", "Sparse-coding basis functions, ranked by how Gabor-like they look",
                       "The Olshausen dictionary from the Redwood Center's sparsecoding library: 384 basis "
                       "functions learned from natural images, cropped to 11×11 around each one's center.",
                       CROP, cands, pre))
    print("preselected:", " ".join(pre))


if __name__ == "__main__":
    main()
