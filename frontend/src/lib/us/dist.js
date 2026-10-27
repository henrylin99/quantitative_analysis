/**
 * Market return-distribution histogram + shape stats. Pure: takes an array of
 * percent values (e.g. pct_change × 100) and returns fixed-width bins plus the
 * moments that describe the distribution's shape (σ, skew, excess kurtosis).
 * HeatmapPage and its regression test share this one implementation.
 *
 * Bins: uniform 1%-wide buckets from -6% to +6% (12 inner) with two open-ended
 * tails (<-6%, ≥+6%) = 14 bins. Fixed edges keep the chart comparable day to day.
 */

// default edges → bins: (-∞,-6) [-6,-5) … [5,6) [6,+∞)
export const DEFAULT_EDGES = [-6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6];

const mean = (xs) => xs.reduce((s, x) => s + x, 0) / xs.length;

export function distribution(values, edges = DEFAULT_EDGES) {
  const vs = (values || []).filter((v) => typeof v === "number" && Number.isFinite(v));
  const n = vs.length;
  if (!n) return { bins: [], n: 0, mean: null, median: null, std: null, skew: null, kurt: null, maxCount: 0 };

  // central moments for shape stats
  const mu = mean(vs);
  const m2 = mean(vs.map((x) => (x - mu) ** 2));
  const m3 = mean(vs.map((x) => (x - mu) ** 3));
  const m4 = mean(vs.map((x) => (x - mu) ** 4));
  const std = Math.sqrt(m2);
  const skew = m2 > 0 ? m3 / m2 ** 1.5 : 0;            // Fisher–Pearson: + right tail, − left tail
  const kurt = m2 > 0 ? m4 / (m2 * m2) - 3 : 0;          // excess: >0 fat-tailed vs normal

  // median
  const sorted = [...vs].sort((a, b) => a - b);
  const median = n % 2 ? sorted[(n - 1) >> 1] : (sorted[n / 2 - 1] + sorted[n / 2]) / 2;

  // bins: counts per [edges[i], edges[i+1]); tails are open-ended at each end
  const bins = [];
  for (let i = 0; i <= edges.length; i++) {
    const lo = i === 0 ? -Infinity : edges[i - 1];
    const hi = i === edges.length ? Infinity : edges[i];
    const count = vs.reduce((s, v) => s + (v >= lo && v < hi ? 1 : 0), 0);
    bins.push({
      lo,
      hi,
      mid: Number.isFinite(lo) && Number.isFinite(hi) ? (lo + hi) / 2 : Number.isFinite(lo) ? lo + 0.5 : hi - 0.5,
      count,
      share: count / n,
    });
  }
  const maxCount = Math.max(...bins.map((b) => b.count));
  return { bins, n, mean: mu, median, std, skew, kurt, maxCount };
}
