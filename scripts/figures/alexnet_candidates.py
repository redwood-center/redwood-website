"""Rank AlexNet first-layer filters by how Gabor-like they are; build a picker; write the chosen set.

Sources (both 11x11, ImageNet-trained):
  B<n>: BVLC AlexNet (Caffe reproduction of Krizhevsky et al. 2012), 96 filters, from the ONNX
        model zoo file research-data/bvlc-alexnet/bvlcalexnet-12.onnx
  T<n>: torchvision AlexNet (IMAGENET1K_V1), 64 filters

Each filter is converted to grayscale by summing its color channels (its response to a gray image).

    python3 scripts/figures/alexnet_candidates.py                  # picker: out/alexnet-picker.html
    python3 scripts/figures/alexnet_candidates.py --select "B90 ..." # write site/src/data/filters-alexnet.json
"""
import argparse
import os

import numpy as np
import onnx
import torchvision
from onnx import numpy_helper

from filterlib import normalize, spectral_score, write_picker, write_site_data

ONNX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "research-data", "bvlc-alexnet",
                    "bvlcalexnet-12.onnx")

# Scored well but look blurry or noisy by eye; skipped when preselecting (still shown in the picker).
LOOKS_WEAK = {"B87", "B93", "B82", "T43", "T33", "T63"}


def load_filters():
    m = onnx.load(ONNX)
    bvlc = next(numpy_helper.to_array(t) for t in m.graph.initializer if t.name == "conv1_w_0")
    tv = torchvision.models.alexnet(weights=torchvision.models.AlexNet_Weights.IMAGENET1K_V1)
    tv = tv.features[0].weight.detach().numpy()
    return [(f"B{i}", f) for i, f in enumerate(bvlc)] + [(f"T{i}", f) for i, f in enumerate(tv)]


def candidates():
    out = []
    for cid, f in load_filters():  # f: (3, 11, 11)
        mean_c = f.mean(axis=0, keepdims=True)
        achrom = min(float(3 * (mean_c ** 2).sum() / ((f - f.mean()) ** 2).sum()), 1.0)
        gray = f.sum(axis=0)
        s, _ = spectral_score(gray)
        rgb = f[::-1] if cid.startswith("B") else f  # Caffe stores BGR
        out.append({"id": cid, "score": round(s * np.sqrt(achrom), 4),
                    "gray": np.round(normalize(gray), 3).reshape(-1).tolist(),
                    "rgb": np.round(normalize(rgb.transpose(1, 2, 0)), 3).reshape(-1).tolist()})  # HWC
    return sorted(out, key=lambda c: -c["score"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--select", help="space-separated IDs, in display order, to write to the site")
    args = ap.parse_args()

    cands = candidates()
    if args.select:
        print(write_site_data("alexnet", 11, "AlexNet conv1 (B = BVLC/Caffe, T = torchvision), grayscale",
                              cands, args.select.split()))
        return
    pre = [c["id"] for c in cands if c["id"] not in LOOKS_WEAK][:48]
    print(write_picker("alexnet", "AlexNet first-layer filters, ranked by how Gabor-like they look",
                       "Grayscale versions of the 11×11 filters from two ImageNet-trained AlexNets "
                       "(B = BVLC/Caffe, T = torchvision).", 11, cands, pre))


if __name__ == "__main__":
    main()
