// Markowitz efficient frontier (unconstrained / shorts allowed, closed form) for a
// set of assets. The frontier is a hyperbola in (vol, return): for any target
// return μ_t the minimum achievable variance is closed-form, needing only two
// linear solves of the covariance system (Σ·u = 1, Σ·v = μ) — no per-point
// optimization, no full matrix inverse. Pure on purpose so the page and its test
// share one implementation.
//
// All math is in DAILY units over the members' common (time-intersected) window;
// results are annualized (return ×252, vol ×√252) for display. Closed form (with
// shorts) is the textbook theoretical frontier — it DOMINATES every real long-only
// portfolio, which is exactly what the dominance check in the test asserts.

// Solve M·x = b via Gaussian elimination with partial pivoting. Returns null if
// (near-)singular. M is square (rows of equal-length arrays); b is a vector.
export function solve(M, b) {
  const n = M.length;
  if (n === 0 || M.some((r) => r.length !== n) || b.length !== n) return null;
  const A = M.map((r, i) => [...r, b[i]]); // augmented matrix (copy)
  for (let col = 0; col < n; col++) {
    let piv = col;
    for (let r = col + 1; r < n; r++) if (Math.abs(A[r][col]) > Math.abs(A[piv][col])) piv = r;
    if (Math.abs(A[piv][col]) < 1e-12) return null; // singular
    if (piv !== col) { const t = A[piv]; A[piv] = A[col]; A[col] = t; }
    for (let r = col + 1; r < n; r++) {
      const f = A[r][col] / A[col][col];
      for (let c = col; c <= n; c++) A[r][c] -= f * A[col][c];
    }
  }
  const x = new Array(n).fill(0);
  for (let r = n - 1; r >= 0; r--) {
    let s = A[r][n];
    for (let c = r + 1; c < n; c++) s -= A[r][c] * x[c];
    x[r] = s / A[r][r];
  }
  return x;
}

// Common (time-intersected) window daily-return matrix: R[k][i] = return of asset i
// at common bar k. Mirrors the alignment in portfolio.equalWeightPortfolio.
export function alignedRets(series) {
  const sets = series.map((s) => new Map((s.rets || []).map((p) => [p.time, p.r])));
  if (!sets.length) return { times: [], R: [] };
  let common = [...sets[0].keys()].sort((a, z) => a - z);
  for (let i = 1; i < sets.length; i++) common = common.filter((t) => sets[i].has(t));
  if (common.length < 2) return { times: common, R: [] };
  return { times: common, R: common.map((t) => sets.map((m) => m.get(t))) };
}

// mean returns (N) + sample covariance (N×N) over aligned rows R.
export function retStats(R, n) {
  const T = R.length;
  const mu = new Array(n).fill(0);
  for (const row of R) for (let i = 0; i < n; i++) mu[i] += row[i];
  for (let i = 0; i < n; i++) mu[i] /= T;
  const cov = Array.from({ length: n }, () => new Array(n).fill(0));
  for (const row of R) for (let i = 0; i < n; i++) {
    const di = row[i] - mu[i];
    for (let j = 0; j < n; j++) cov[i][j] += di * (row[j] - mu[j]);
  }
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) cov[i][j] /= (T - 1);
  return { mu, cov };
}

// Efficient frontier (annualized %). Returns null if covariance is singular or the
// common window is too short.
//   curve      : [{x: ann.vol %, y: ann.return %}] sorted by x, spanning members' return range
//   minVar     : {x, y, weights[]}   global minimum-variance portfolio (fully invested)
//   maxSharpe  : {x, y, weights[], sharpe}  tangency portfolio (rf=0); null if undefined
//   scalars    : {A,B,C,D}  frontier constants (exposed for the test)
export function efficientFrontier(series, nPts = 40) {
  const n = series.length;
  if (n < 2) return null;
  const { R } = alignedRets(series);
  if (R.length < n + 2) return null; // need T > N for a full-rank covariance
  const { mu, cov } = retStats(R, n);
  const ones = new Array(n).fill(1);
  const u = solve(cov, ones); // Σ⁻¹1
  const v = solve(cov, mu);   // Σ⁻¹μ
  if (!u || !v) return null;
  const A = u.reduce((s, x) => s + x, 0);    // 1ᵀΣ⁻¹1
  const B = v.reduce((s, x) => s + x, 0);    // 1ᵀΣ⁻¹μ
  const C = mu.reduce((s, m, i) => s + m * v[i], 0); // μᵀΣ⁻¹μ
  const D = A * C - B * B;
  if (!(D > 1e-18) || !(A > 0)) return null;
  const SQ = Math.sqrt(252);
  const varAt = (mt) => Math.max(0, (A * mt * mt - 2 * B * mt + C) / D); // daily variance at target return
  const lo = Math.min(...mu), hi = Math.max(...mu);
  const curve = [];
  for (let k = 0; k <= nPts; k++) {
    const mt = lo + ((hi - lo) * k) / nPts;
    curve.push({ x: Math.sqrt(varAt(mt)) * SQ * 100, y: mt * 252 * 100 });
  }
  curve.sort((p, q) => p.x - q.x);
  const mtMv = B / A;
  const minVar = { x: Math.sqrt(1 / A) * SQ * 100, y: mtMv * 252 * 100, weights: u.map((x) => x / A) };
  // tangency (max Sharpe, rf=0): μ_tg = C/B, only defined for B>0
  const maxSharpe = B > 0
    ? { x: (Math.sqrt(C) / B) * SQ * 100, y: (C / B) * 252 * 100, weights: v.map((x) => x / B), sharpe: Math.sqrt(C) * SQ }
    : null;
  return { curve, minVar, maxSharpe, scalars: { A, B, C, D } };
}
