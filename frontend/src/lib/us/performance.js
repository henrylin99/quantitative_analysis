/**
 * Risk-adjusted performance metrics derived from an equity curve.
 *
 * The backtest equity curve ([{ time, value }], starting at 1.0) spans every
 * bar of the window, so simple per-bar returns are well-defined. From those we
 * get annualized return (CAGR), annualized volatility, and the three classic
 * risk-adjusted ratios — Sharpe, Sortino, Calmar — exactly the column set a
 * TradingView strategy-test report shows. Risk-free rate is assumed 0 (sandbox).
 *
 * Annualization uses trading periods per year by timeframe: daily 252, weekly
 * 52; intraday scales the 6.5-hour US session (390 min/day × 252 days).
 */
const PERIODS_PER_YEAR = {
  daily: 252,
  weekly: 52,
  "60": 6.5 * 252,
  "30": 13 * 252,
  "15": 26 * 252,
  "5": 78 * 252,
};

/**
 * @param {Array<{time:number,value:number}>} equity  per-bar net value (≥ 2 pts)
 * @param {string} tf        timeframe key (daily/weekly/60/30/15/5)
 * @param {number} maxDrawdown  strategy max drawdown as a signed decimal (≤ 0)
 * @returns {{cagr:number,vol:number,sharpe:number|null,sortino:number|null,
 *           calmar:number|null,py:number}|null}
 */
export function perfMetrics(equity, tf, maxDrawdown) {
  if (!equity || equity.length < 2) return null;
  const py = PERIODS_PER_YEAR[tf] ?? 252;

  const rets = [];
  for (let i = 1; i < equity.length; i++) {
    const a = equity[i - 1].value;
    if (a > 0) rets.push(equity[i].value / a - 1);
  }
  const n = rets.length;
  if (!n) return null;

  const mean = rets.reduce((s, r) => s + r, 0) / n;
  const variance = rets.reduce((s, r) => s + (r - mean) ** 2, 0) / n;
  const std = Math.sqrt(variance);
  // downside deviation from a 0 target: square of negative returns averaged
  // over ALL observations (zeros for non-negative bars), the standard Sortino form.
  const downsideVar = rets.reduce((s, r) => s + (r < 0 ? r * r : 0), 0) / n;
  const ddStd = Math.sqrt(downsideVar);

  const v0 = equity[0].value;
  const vLast = equity[equity.length - 1].value;
  const cagr = v0 > 0 ? (vLast / v0) ** (py / n) - 1 : 0;
  const vol = std * Math.sqrt(py);
  const sharpe = std > 0 ? (mean / std) * Math.sqrt(py) : null;
  const sortino = ddStd > 0 ? (mean / ddStd) * Math.sqrt(py) : null;
  const calmar = maxDrawdown ? cagr / Math.abs(maxDrawdown) : null;

  return { cagr, vol, sharpe, sortino, calmar, py };
}

/**
 * Per-trade Maximum Adverse / Favourable Excursion. For each long trade, how far
 * price ran against the entry (MAE, ≤ 0) and in favour (MFE, ≥ 0) over the bars
 * from entry to exit. Excursion is trade quality independent of outcome: a win
 * with tiny MFE is partly luck; a loss with large MFE gave back gains (exited
 * too late); heavy MAE means the trade sat deep underwater before resolving.
 *
 * @param {Array<{time,low,high}>} bars   OHLC bars, time-ascending
 * @param {Array<{entry_time,exit_time,entry_price,win}>} trades
 */
export function maeMfe(bars, trades) {
  if (!bars || !trades || !trades.length) return null;
  const seg = (t) => {
    let lo = Infinity, hi = -Infinity;
    for (const b of bars) {
      if (b.time < t.entry_time) continue;
      if (b.time > t.exit_time) break; // bars are time-ascending
      if (b.low < lo) lo = b.low;
      if (b.high > hi) hi = b.high;
    }
    const ep = t.entry_price > 0 ? t.entry_price : 1;
    return { mae: (lo - t.entry_price) / ep, mfe: (hi - t.entry_price) / ep };
  };
  const enriched = trades.map((t) => ({ ...t, ...seg(t) }));
  const n = enriched.length;
  const avg = (f) => enriched.reduce((s, t) => s + f(t), 0) / n;
  const avgMae = avg((t) => t.mae), avgMfe = avg((t) => t.mfe);
  return {
    trades: enriched,
    avgMae,
    avgMfe,
    gaveBack: enriched.filter((t) => t.mfe > 0.03 && !t.win).length, // saw ≥3% gain, ended a loss
    deepWater: enriched.filter((t) => t.mae < -0.05).length,          // sat ≥5% underwater
    n,
  };
}
