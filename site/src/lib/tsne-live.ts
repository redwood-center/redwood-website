// A small exact t-SNE for the live paper map. Same optimizer as tsnejs (momentum, adaptive gains, early
// exaggeration), plus what tsnejs can't do:
// - extra dimensions that can be squeezed to zero ("start in 5-D, flatten to 2-D"), so clusters can pass through
//   each other early instead of locking in;
// - frozen points, which exert forces but don't move (newcomers settle against an existing layout without
//   disturbing it).
// Exact O(N^2) gradient: fine for the few hundred papers on the map.

export const DIMS = 5; // the map shows dims 0 and 1; dims 2..4 exist only until squeezed away

/** Row-normalized Gaussian affinities at the given perplexity, symmetrized (as in tsnejs's d2p). */
function affinities(D: Float64Array, n: number, perplexity: number) {
  const P = new Float64Array(n * n);
  const H = Math.log(perplexity);
  const row = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    let beta = 1, lo = -Infinity, hi = Infinity;
    for (let it = 0; it < 50; it++) {
      let sum = 0;
      for (let j = 0; j < n; j++) { row[j] = j === i ? 0 : Math.exp(-D[i * n + j] * beta); sum += row[j]; }
      sum = sum || 1e-12;
      let h = 0;
      for (let j = 0; j < n; j++) { const p = row[j] / sum; if (p > 1e-7) h -= p * Math.log(p); }
      if (Math.abs(h - H) < 1e-4) break;
      if (h > H) { lo = beta; beta = hi === Infinity ? beta * 2 : (beta + hi) / 2; }
      else { hi = beta; beta = lo === -Infinity ? beta / 2 : (beta + lo) / 2; }
    }
    let sum = 0;
    for (let j = 0; j < n; j++) sum += row[j];
    for (let j = 0; j < n; j++) P[i * n + j] = row[j] / (sum || 1e-12);
  }
  const out = new Float64Array(n * n);
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) out[i * n + j] = Math.max((P[i * n + j] + P[j * n + i]) / (2 * n), 1e-100);
  return out;
}

export class LiveTSNE {
  n: number;
  P: Float64Array;
  Y: Float64Array; // n x DIMS
  v: Float64Array; // momentum
  gains: Float64Array;
  private grad: Float64Array;
  private W: Float64Array; // pairwise Student-t weights, reused every step
  learningRate = 10;
  lrScale = 1; // the caller lowers this to bring motion to a gentle stop

  /** D: squared distances (n x n, row-major). */
  constructor(D: Float64Array, n: number, perplexity: number) {
    this.n = n;
    this.P = affinities(D, n, perplexity);
    this.Y = new Float64Array(n * DIMS);
    this.v = new Float64Array(n * DIMS);
    this.gains = new Float64Array(n * DIMS).fill(1);
    this.grad = new Float64Array(n * DIMS);
    this.W = new Float64Array(n * n);
  }

  /**
   * One gradient step. `exaggeration` multiplies P (early exaggeration); `momentum` as in tsnejs (0.5 early, 0.8
   * later); `frozen[i]` = 1 keeps point i fixed while it still pulls and pushes the others; `squeeze` in [0, 1]
   * shrinks dims 2.. by that fraction this step (1 = flatten now).
   */
  step(exaggeration: number, momentum: number, frozen: Uint8Array | null, squeeze: number) {
    const { n, P, Y, v, gains, grad, W } = this;
    grad.fill(0);
    let Z = 0;
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
      let d2 = 0;
      for (let k = 0; k < DIMS; k++) { const t = Y[i * DIMS + k] - Y[j * DIMS + k]; d2 += t * t; }
      const w = 1 / (1 + d2);
      W[i * n + j] = W[j * n + i] = w;
      Z += 2 * w;
    }
    for (let i = 0; i < n; i++) {
      if (frozen && frozen[i]) continue;
      for (let j = 0; j < n; j++) {
        if (j === i) continue;
        const w = W[i * n + j];
        const f = 4 * (exaggeration * P[i * n + j] - w / Z) * w;
        for (let k = 0; k < DIMS; k++) grad[i * DIMS + k] += f * (Y[i * DIMS + k] - Y[j * DIMS + k]);
      }
    }
    for (let i = 0; i < n; i++) {
      if (frozen && frozen[i]) continue;
      for (let k = 0; k < DIMS; k++) {
        const a = i * DIMS + k, g = grad[a];
        gains[a] = Math.sign(g) === Math.sign(v[a]) ? gains[a] * 0.8 : gains[a] + 0.2;
        if (gains[a] < 0.01) gains[a] = 0.01;
        v[a] = momentum * v[a] - this.learningRate * this.lrScale * gains[a] * g;
        Y[a] += v[a];
        if (k >= 2 && squeeze > 0) { Y[a] *= 1 - squeeze; v[a] *= 1 - squeeze; }
      }
    }
    // Keep the layout centered, unless some points are pinned (then the frame must not shift under them).
    if (!frozen) {
      for (let k = 0; k < DIMS; k++) {
        let m = 0;
        for (let i = 0; i < n; i++) m += Y[i * DIMS + k];
        m /= n;
        for (let i = 0; i < n; i++) Y[i * DIMS + k] -= m;
      }
    }
  }

  /** The t-SNE energy: KL(P || Q) for the current positions (no exaggeration). Lower is a better layout. */
  kl() {
    const { n, P, Y } = this;
    let Z = 0;
    const W = this.W;
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
      let d2 = 0;
      for (let k = 0; k < DIMS; k++) { const t = Y[i * DIMS + k] - Y[j * DIMS + k]; d2 += t * t; }
      const w = 1 / (1 + d2);
      W[i * n + j] = W[j * n + i] = w;
      Z += 2 * w;
    }
    let kl = 0;
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
      if (i === j) continue;
      const p = P[i * n + j];
      if (p > 1e-12) kl += p * Math.log(p / Math.max(W[i * n + j] / Z, 1e-300));
    }
    return kl;
  }

  x(i: number) { return this.Y[i * DIMS]; }
  y(i: number) { return this.Y[i * DIMS + 1]; }
}
