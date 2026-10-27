// Tail-risk measures for a return series: Value at Risk (VaR) and Conditional
// VaR (expected shortfall). Pure on purpose so the page and its one-off test
// share one implementation.
//
// Conventions:
//   - All inputs are DAILY simple-return series (e.g. portfolio.returns() /
//     basketReturns() output values, i.e. the `.r` of each point). Pass the
//     numeric array; this lib takes plain numbers, not {time,r} points.
//   - Every function returns a LOSS as a NON-NEGATIVE fraction (0.02 = a 2%
//     one-day loss threshold). null when the series is too short.
//   - alpha = the tail probability (0.05 → "95% VaR": the loss not exceeded on
//     95% of days; the worst 5% are deeper). Smaller alpha → deeper tail.

// Inverse standard-normal CDF (Acklam's rational approximation), ~1e-9 in the
// central region. Needed for the parametric (mean-σ) VaR. Public so the test
// can sanity-check it against known z-values (Φ⁻¹(0.05)≈-1.6449, etc.).
export function invPhi(p) {
  if (p <= 0 || p >= 1) return p <= 0 ? -Infinity : Infinity;
  const a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00];
  const b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01];
  const c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00];
  const d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00];
  const plow = 0.02425, phigh = 1 - plow;
  if (p < plow) {
    const q = Math.sqrt(-2 * Math.log(p));
    return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
  }
  if (p <= phigh) {
    const q = p - 0.5, r = q * q;
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
  }
  const q = Math.sqrt(-2 * Math.log(1 - p));
  return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
}

// Linear-interpolation quantile (numpy/Excel "type 7" / inclusive default) of a
// numeric series at probability q∈[0,1]. Does NOT mutate the input. null if empty.
export function quantile(vals, q) {
  const s = [...vals].sort((x, y) => x - y);
  const n = s.length;
  if (!n) return null;
  if (n === 1) return s[0];
  const pos = (n - 1) * Math.max(0, Math.min(1, q));
  const lo = Math.floor(pos), hi = Math.ceil(pos);
  if (lo === hi) return s[lo];
  const frac = pos - lo;
  return s[lo] * (1 - frac) + s[hi] * frac;
}

// Historical (empirical) VaR: the loss at the alpha tail of the realized
// returns. alpha=0.05 → the 5th-percentile daily return expressed as a loss.
export function historicalVaR(rets, alpha = 0.05) {
  if (!rets || !rets.length) return null;
  return -quantile(rets, alpha);
}

// Parametric (variance-covariance) VaR: assumes returns ~ N(μ,σ²), so the
// alpha-quantile is μ + Φ⁻¹(α)·σ. Uses the sample standard deviation (n-1).
export function parametricVaR(rets, alpha = 0.05) {
  const n = rets && rets.length;
  if (!n || n < 2) return null;
  let mu = 0;
  for (const r of rets) mu += r;
  mu /= n;
  let ss = 0;
  for (const r of rets) ss += (r - mu) ** 2;
  const sigma = Math.sqrt(ss / (n - 1));
  return -(mu + invPhi(alpha) * sigma);
}

// Historical Conditional VaR (expected shortfall): the AVERAGE loss on days in
// the alpha tail (mean of all returns ≤ the alpha-quantile). By definition
// CVaR ≥ VaR — the average of the worst tail is at least as bad as its edge.
export function cvarHistorical(rets, alpha = 0.05) {
  if (!rets || !rets.length) return null;
  const q = quantile(rets, alpha);
  const tail = rets.filter((r) => r <= q);
  if (!tail.length) return null;
  return -tail.reduce((s, r) => s + r, 0) / tail.length;
}
