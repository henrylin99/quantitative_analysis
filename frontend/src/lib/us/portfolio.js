/**
 * Portfolio / multi-symbol analytics: aligned returns, pairwise correlation,
 * and rebased performance. Pure functions so the page and its test share one
 * implementation (the established cross-check pattern).
 *
 * Daily simple returns are aligned by timestamp (intersection of the two
 * series) before any pairwise math, so symbols with different histories are
 * compared only over the bars they share.
 */

/** Per-bar simple returns: [{ time, r }], skipping a non-positive prior close. */
export function returns(bars) {
  const out = [];
  for (let i = 1; i < bars.length; i++) {
    const a = bars[i - 1].close;
    if (a > 0) out.push({ time: bars[i].time, r: bars[i].close / a - 1 });
  }
  return out;
}

/**
 * Pearson correlation between two return series, aligned by time. Returns null
 * when fewer than 2 shared bars or zero variance — the same guard the screener's
 * factor matrix uses.
 */
export function pearson(a, b) {
  const m = new Map(a.map((p) => [p.time, p.r]));
  const pairs = [];
  for (const p of b) if (m.has(p.time)) pairs.push([m.get(p.time), p.r]);
  const n = pairs.length;
  if (n < 2) return null;
  const mx = pairs.reduce((s, p) => s + p[0], 0) / n;
  const my = pairs.reduce((s, p) => s + p[1], 0) / n;
  let num = 0, dx = 0, dy = 0;
  for (const [x, y] of pairs) {
    num += (x - mx) * (y - my);
    dx += (x - mx) ** 2;
    dy += (y - my) ** 2;
  }
  return dx > 0 && dy > 0 ? num / Math.sqrt(dx * dy) : null;
}

/**
 * Rolling-window Pearson correlation between two return series over time — the
 * correlation REGIME, not just the single all-history number. At each bar the
 * correlation is computed over the trailing `win` shared returns, so the line
 * shows when two assets start/stop moving together (correlations famously spike
 * in sell-offs, exactly when diversification is needed most).
 */
export function rollingCorr(a, b, win) {
  const m = new Map(a.map((p) => [p.time, p.r]));
  const pts = [];
  for (const p of b) if (m.has(p.time)) pts.push({ t: p.time, x: m.get(p.time), y: p.r });
  const out = [];
  for (let i = win - 1; i < pts.length; i++) {
    let mx = 0, my = 0;
    for (let k = i - win + 1; k <= i; k++) { mx += pts[k].x; my += pts[k].y; }
    mx /= win; my /= win;
    let num = 0, dx = 0, dy = 0;
    for (let k = i - win + 1; k <= i; k++) {
      const xa = pts[k].x - mx, ya = pts[k].y - my;
      num += xa * ya; dx += xa * xa; dy += ya * ya;
    }
    if (dx > 0 && dy > 0) out.push({ time: pts[i].t, value: num / Math.sqrt(dx * dy) });
  }
  return out;
}

/**
 * Average pairwise rolling correlation of a basket — one line summarising how
 * internally correlated the whole portfolio is at each point in time. A spike
 * means the holdings are all moving together (diversification failing); a dip
 * means they're dispersing. Pairs are aligned by time then averaged per bar.
 */
export function avgRollingCorr(series, win) {
  const pairs = [];
  for (let i = 0; i < series.length; i++)
    for (let j = i + 1; j < series.length; j++) pairs.push([series[i].rets, series[j].rets]);
  if (!pairs.length) return [];
  const rolls = pairs.map(([a, b]) => {
    const map = new Map();
    for (const p of rollingCorr(a, b, win)) if (Number.isFinite(p.value)) map.set(p.time, p.value);
    return map;
  });
  const times = new Set();
  for (const map of rolls) for (const t of map.keys()) times.add(t);
  const out = [];
  for (const t of [...times].sort((x, y) => x - y)) {
    let sum = 0, cnt = 0;
    for (const map of rolls) if (map.has(t)) { sum += map.get(t); cnt++; }
    if (cnt) out.push({ time: t, value: sum / cnt });
  }
  return out;
}

/**
 * Full N×N correlation matrix from `series` ([{ symbol, rets }]). Symmetric with
 * 1 on the diagonal; off-diagonals are the time-aligned Pearson r (or null when
 * not computable). Also returns the mean of the upper triangle as a single
 * diversification number (≈1 = everything moves together, ≈0 = diversified).
 */
export function corrMatrix(series) {
  const n = series.length;
  const m = Array.from({ length: n }, () => Array(n).fill(null));
  let sum = 0, count = 0;
  for (let i = 0; i < n; i++) {
    m[i][i] = 1;
    for (let j = i + 1; j < n; j++) {
      const r = pearson(series[i].rets, series[j].rets);
      m[i][j] = r;
      m[j][i] = r;
      if (r != null) { sum += r; count++; }
    }
  }
  return { matrix: m, mean: count ? sum / count : null };
}

/** Rebase a bar series to start at `base` (default 100) — comparable performance lines. */
export function rebased(bars, base = 100) {
  if (!bars.length) return [];
  const b0 = bars[0].close;
  return bars.map((p) => ({ time: p.time, value: b0 > 0 ? (p.close / b0) * base : base }));
}

/**
 * Rebase from a specific anchor date instead of the first bar: finds the first
 * bar at/after `fromTime`, then scales that tail to `base`. Used to put every
 * portfolio member on the same starting line (100 at the shared start date) so
 * the relative-performance panel and the equal-weight line are directly
 * comparable. fromTime = -Infinity → whole series (== rebased).
 */
export function rebasedAt(bars, fromTime, base = 100) {
  if (!bars.length) return [];
  const idx = bars.findIndex((b) => b.time >= fromTime);
  if (idx < 0 || !bars[idx] || bars[idx].close <= 0) return [];
  const b0 = bars[idx].close;
  return bars.slice(idx).map((p) => ({ time: p.time, value: (p.close / b0) * base }));
}

/**
 * Underwater (drawdown) curve of an equity/index series: at each point, how far
 * below its running peak it sits, as a fraction (always ≤ 0; 0 at a new high).
 * The "path" of drawdown the single max-drawdown number hides — shows WHEN the
 * portfolio was underwater, how deep, and how long it stayed there (recovery).
 * Takes any [{ time, value }] curve (a rebased price line or the equal-weight
 * portfolio equity). Robust to non-positive peaks (emits 0 rather than ±Inf).
 */
export function drawdownSeries(eq) {
  const out = [];
  let peak = -Infinity;
  for (const p of eq) {
    if (p.value > peak) peak = p.value;
    out.push({ time: p.time, value: peak > 0 ? p.value / peak - 1 : 0 });
  }
  return out;
}

/**
 * Equal-weight (daily-rebalanced) portfolio equity curve over the date range
 * EVERY member shares (intersection of return dates). Each bar's portfolio
 * return is the plain mean of the members' returns that day; the curve is the
 * cumulative product from 1.0. Feeding this to perfMetrics yields the basket's
 * annualised return / volatility / Sharpe — the payoff of the diversification
 * the correlation matrix revealed.
 */
export function equalWeightPortfolio(series) {
  if (!series.length) return [];
  const sets = series.map((s) => new Map(s.rets.map((p) => [p.time, p.r])));
  let common = [...sets[0].keys()].sort((a, b) => a - b);
  for (let i = 1; i < sets.length; i++) {
    const si = sets[i];
    common = common.filter((t) => si.has(t));
  }
  if (common.length < 2) return [];
  let eq = 1;
  const out = [{ time: common[0], value: eq }];
  for (let k = 1; k < common.length; k++) {
    let sum = 0;
    for (const s of sets) sum += s.get(common[k]);
    eq *= 1 + sum / sets.length;
    out.push({ time: common[k], value: eq });
  }
  return out;
}

/**
 * Daily returns of the equal-weight basket over the shared window — the same
 * intersection equalWeightPortfolio uses, but emitting the per-bar mean return
 * instead of the cumulative curve. Serves as the in-house "market" proxy for beta.
 */
export function basketReturns(series) {
  if (!series.length) return [];
  const sets = series.map((s) => new Map(s.rets.map((p) => [p.time, p.r])));
  let common = [...sets[0].keys()].sort((a, b) => a - b);
  for (let i = 1; i < sets.length; i++) common = common.filter((t) => sets[i].has(t));
  return common.map((t) => {
    let sum = 0;
    for (const s of sets) sum += s.get(t);
    return { time: t, r: sum / sets.length };
  });
}

/**
 * Beta of a member's returns vs the market (basket) returns over shared dates:
 * cov(member, market) / var(market). >1 = amplifies the basket (bigger risk
 * contribution), <1 = stabilises/diversifies. null when not computable. The
 * basket's own beta vs itself is exactly 1 (var/var).
 */
export function betaOf(memberRets, marketRets) {
  const m = new Map(marketRets.map((p) => [p.time, p.r]));
  const pts = [];
  for (const p of memberRets) if (m.has(p.time)) pts.push([p.r, m.get(p.time)]);
  const n = pts.length;
  if (n < 2) return null;
  let mm = 0, mk = 0;
  for (const [x, y] of pts) { mm += x; mk += y; }
  mm /= n; mk /= n;
  let cov = 0, varM = 0;
  for (const [x, y] of pts) { cov += (x - mm) * (y - mk); varM += (y - mk) ** 2; }
  return varM > 0 ? cov / varM : null;
}

/**
 * Rolling beta of a member vs the market (basket) over a trailing window:
 * cov(member, market)/var(market) per window on time-aligned returns. Shows how
 * a member's systematic-risk contribution evolves. [{time,value}]. (Note: for an
 * equal-weight basket the member betas sum to n, so their MEAN is always 1 — the
 * per-member lines are what carry information.)
 */
export function rollingBeta(memberRets, marketRets, win) {
  const m = new Map(marketRets.map((p) => [p.time, p.r]));
  const pts = [];
  for (const p of memberRets) if (m.has(p.time)) pts.push({ t: p.time, x: p.r, y: m.get(p.time) });
  const out = [];
  for (let i = win - 1; i < pts.length; i++) {
    let mx = 0, my = 0;
    for (let k = i - win + 1; k <= i; k++) { mx += pts[k].x; my += pts[k].y; }
    mx /= win; my /= win;
    let cov = 0, varM = 0;
    for (let k = i - win + 1; k <= i; k++) { cov += (pts[k].x - mx) * (pts[k].y - my); varM += (pts[k].y - my) ** 2; }
    if (varM > 0) out.push({ time: pts[i].t, value: cov / varM });
  }
  return out;
}
