"""Receptive fields of mouse V1 neurons, estimated from two-photon recordings of responses to natural images.

Data: Stringer, Pachitariu et al. 2019, "High-dimensional geometry of population responses in visual cortex",
Nature 571:361; figshare 10.25378/janelia.6845348 (CC BY-NC 4.0). One session (natimg2800_M160825_MP027,
11,449 neurons, 2,800 images shown twice) and the image set, in research-data/receptive-fields/stringer2019/.

Each neuron's receptive field is the ridge-regression map from image pixels (downsampled 2x to 34x135) to its
response, averaged over the two repeats, after removing the top 32 dimensions of spontaneous activity (as the
paper does). The 400 most reliable neurons (repeat-to-repeat correlation) are kept; each map is cropped to a
22x22 window around its peak and resampled to 11x11. IDs are S<neuron index>.

    python3 scripts/figures/mouse_candidates.py      # writes out/mouse-candidates.json
"""
import json
import os
import warnings

import numpy as np
import scipy.io as sio
from PIL import Image
from scipy.ndimage import gaussian_filter

from filterlib import HERE, normalize, spectral_score

DATA = os.path.join(HERE, "..", "..", "research-data", "receptive-fields", "stringer2019")
SESSION = "natimg2800_M160825_MP027_2016-12-14.mat"
LAMBDA, N_KEEP, SIDE, K = 1e6, 400, 22, 11


def receptive_fields():
    imgs = sio.loadmat(os.path.join(DATA, "images_natimg2800_all.mat"))["imgs"].astype(np.float64)  # 68x270x2800
    stim = sio.loadmat(os.path.join(DATA, SESSION), squeeze_me=True, struct_as_record=False)["stim"]
    resp, istim, spont = stim.resp.astype(np.float64), stim.istim.astype(int) - 1, stim.spont.astype(np.float64)
    keep = istim < 2800  # the last stimulus index is a blank screen
    resp, istim = resp[keep], istim[keep]
    mu, sd = spont.mean(0), spont.std(0) + 1e-6
    resp = (resp - mu) / sd
    pcs = np.linalg.svd((spont - mu) / sd, full_matrices=False)[2][:32]
    resp -= (resp @ pcs.T) @ pcs

    # reliability: correlation between the first and second showing of each image
    rep = np.zeros(len(istim), int)
    seen = {}
    for i, s in enumerate(istim):
        rep[i] = seen.get(s, 0)
        seen[s] = rep[i] + 1
    a = np.full((2800, resp.shape[1]), np.nan)
    b = a.copy()
    a[istim[rep == 0]], b[istim[rep == 1]] = resp[rep == 0], resp[rep == 1]
    ok = ~np.isnan(b[:, 0])
    rel = np.array([np.corrcoef(a[ok, j], b[ok, j])[0, 1] for j in range(resp.shape[1])])
    top = np.argsort(-np.nan_to_num(rel))[:N_KEEP]

    Y = np.zeros((2800, resp.shape[1]))
    cnt = np.zeros(2800)
    np.add.at(Y, istim, resp)
    np.add.at(cnt, istim, 1)
    Y = Y[:, top] / np.maximum(cnt, 1)[:, None]
    X = imgs.reshape(34, 2, 135, 2, 2800).mean((1, 3)).reshape(-1, 2800).T
    X = (X - X.mean(0)) / (X.std(0) + 1e-6)
    U, S, Vt = np.linalg.svd(X, full_matrices=False)
    W = Vt.T @ ((S / (S ** 2 + LAMBDA))[:, None] * (U.T @ (Y - Y.mean(0))))
    return top, W.T.reshape(-1, 34, 135)


def candidates():
    out = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # spurious matmul overflow warnings from macOS Accelerate
        ids, rfs = receptive_fields()
    for j, m in zip(ids, rfs):
        e = gaussian_filter(m ** 2, 3)
        py, px = np.unravel_index(np.argmax(e), e.shape)
        snr = e.max() / np.median(e)
        y0 = int(np.clip(py - SIDE // 2, 0, m.shape[0] - SIDE))
        x0 = int(np.clip(px - SIDE // 2, 0, m.shape[1] - SIDE))
        crop = (m - np.median(m))[y0:y0 + SIDE, x0:x0 + SIDE].astype(np.float32)
        p = normalize(np.asarray(Image.fromarray(crop).resize((K, K), Image.BOX)))
        s, _ = spectral_score(p)
        out.append({"id": f"S{j}", "score": round(s * min(snr, 30) / 30, 4), "gray": np.round(p, 3).reshape(-1).tolist()})
    return sorted(out, key=lambda c: -c["score"])


if __name__ == "__main__":
    path = os.path.join(HERE, "out", "mouse-candidates.json")
    data = candidates()
    with open(path, "w") as fh:
        json.dump({"S": data}, fh)
    print(len(data), "->", path)
