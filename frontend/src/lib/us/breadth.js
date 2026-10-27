// Market breadth from a single cross-sectional snapshot: advance/decline counts,
// up/down volume, and a participation-based thrust signal. Pure (no DOM) so the
// page and the cross-check test import the same function and cannot drift.

export function breadth(rows) {
  if (!Array.isArray(rows) || !rows.length) return null;
  const valid = rows.filter((r) => Number.isFinite(r.pct_change));
  if (!valid.length) return null;

  let advancing = 0,
    declining = 0,
    unchanged = 0,
    upVolume = 0,
    downVolume = 0;
  const pcts = [];
  let topGainer = null,
    topLoser = null;

  for (const r of valid) {
    const p = r.pct_change;
    pcts.push(p);
    const pct100 = p * 100;
    if (p > 0) {
      advancing++;
      upVolume += r.volume || 0;
    } else if (p < 0) {
      declining++;
      downVolume += r.volume || 0;
    } else {
      unchanged++;
    }
    if (!topGainer || pct100 > topGainer.pct) topGainer = { symbol: r.symbol, pct: pct100 };
    if (!topLoser || pct100 < topLoser.pct) topLoser = { symbol: r.symbol, pct: pct100 };
  }

  const total = valid.length;
  const totalVol = upVolume + downVolume;
  const upVolPct = totalVol > 0 ? upVolume / totalVol : 0.5;
  const advPct = advancing / total;
  const decPct = declining / total;
  const adRatio = declining > 0 ? advancing / declining : advancing > 0 ? Infinity : 0;

  // mean + median of the day's percent moves
  const meanPct = (pcts.reduce((s, v) => s + v, 0) / total) * 100;
  const sorted = pcts.slice().sort((a, b) => a - b);
  const mid = sorted.length >> 1;
  const medianPct =
    (sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2) * 100;

  // breadth thrust: broad participation (>70% of names) AND demand confirmed by
  // volume (>65% traded in advancing names) => bullish; mirror => bearish; else neutral.
  let signal = "neutral";
  if (advPct >= 0.7 && upVolPct >= 0.65) signal = "bull";
  else if (decPct >= 0.7 && upVolPct <= 0.35) signal = "bear";

  return {
    advancing,
    declining,
    unchanged,
    total,
    advPct,
    decPct,
    upVolume,
    downVolume,
    upVolPct,
    adRatio,
    meanPct,
    medianPct,
    signal,
    topGainer,
    topLoser,
  };
}
