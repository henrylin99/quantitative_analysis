/**
 * Client-side technical indicators computed from OHLC bars.
 *
 * Mirrors common Pine Script built-ins (ta.sma / ta.ema / ta.bb / ta.macd /
 * ta.stoch / ta.rsi). Every function takes the bar array straight from
 * /api/bars and returns points [{ time, value }] aligned to those bars,
 * omitting the leading warm-up period. Histogram points additionally carry
 * a per-bar `color`.
 *
 * Computing these in the browser (rather than asking the backend per toggle)
 * is exactly how Pine Script overlays work in TradingView: the raw series is
 * the only thing streamed, and indicators derive from it locally.
 */

/** Simple moving average over `key` (default close). */
export function sma(bars, period, key = "close") {
  const out = [];
  let sum = 0;
  for (let i = 0; i < bars.length; i++) {
    sum += bars[i][key];
    if (i >= period) sum -= bars[i - period][key];
    if (i >= period - 1) out.push({ time: bars[i].time, value: sum / period });
  }
  return out;
}

/** Exponential moving average, seeded with an SMA of the first `period`. */
export function ema(bars, period, key = "close") {
  if (bars.length < period) return [];
  const k = 2 / (period + 1);
  let prev = 0;
  for (let i = 0; i < period; i++) prev += bars[i][key];
  prev /= period;
  const out = [{ time: bars[period - 1].time, value: prev }];
  for (let i = period; i < bars.length; i++) {
    prev = bars[i][key] * k + prev * (1 - k);
    out.push({ time: bars[i].time, value: prev });
  }
  return out;
}

/** Wilder ATR (Average True Range): true range smoothed with Wilder's method. */
export function atr(bars, period = 14) {
  const out = [];
  if (bars.length <= period) return out;
  const tr = new Array(bars.length);
  tr[0] = bars[0].high - bars[0].low;
  for (let i = 1; i < bars.length; i++) {
    tr[i] = Math.max(
      bars[i].high - bars[i].low,
      Math.abs(bars[i].high - bars[i - 1].close),
      Math.abs(bars[i].low - bars[i - 1].close)
    );
  }
  let a = 0;
  for (let i = 1; i <= period; i++) a += tr[i];
  a /= period;
  out.push({ time: bars[period].time, value: a });
  for (let i = period + 1; i < bars.length; i++) {
    a = (a * (period - 1) + tr[i]) / period;
    out.push({ time: bars[i].time, value: a });
  }
  return out;
}

/**
 * Wilder's Directional Movement Index (ADX / DMI) — the trend-STRENGTH system.
 *
 * Three aligned series: +DI and −DI (who is winning, bulls or bears, each scaled
 * 0–100) and ADX (the strength of whichever direction dominates, 0–100; >~25 is
 * conventionally "trending"). Unlike RSI (momentum) or MACD (trend/momentum), ADX
 * says nothing about direction — only whether a trend is strong enough to trade.
 * TR, +DM, −DM, and DX are each smoothed with Wilder's RMA (α = 1/period), seeded
 * with an SMA of the first `period` values over indices 1..period — the same seed
 * convention the codebase's own `atr` uses. +DM/−DM use Wilder's comparison (up
 * move beats down move, or vice‑versa, both floored at 0). ADX lags DI because it
 * is an RMA of DX, so it only starts emitting at index ~2·period; +DI/−DI start at
 * index `period`. Returns { plusDI, minusDI, adx }, each [{ time, value }].
 */
export function adx(bars, period = 14) {
  const n = bars.length;
  if (n <= period) return { plusDI: [], minusDI: [], adx: [] };
  const tr = new Array(n);
  const plusDM = new Array(n).fill(0);
  const minusDM = new Array(n).fill(0);
  tr[0] = bars[0].high - bars[0].low;
  for (let i = 1; i < n; i++) {
    const up = bars[i].high - bars[i - 1].high;   // up-move
    const dn = bars[i - 1].low - bars[i].low;     // down-move
    plusDM[i] = up > dn && up > 0 ? up : 0;
    minusDM[i] = dn > up && dn > 0 ? dn : 0;
    tr[i] = Math.max(
      bars[i].high - bars[i].low,
      Math.abs(bars[i].high - bars[i - 1].close),
      Math.abs(bars[i].low - bars[i - 1].close)
    );
  }
  // Wilder RMA: seed = mean of arr[1..period], then rma = (prev·(period−1) + cur)/period.
  const rma = (arr) => {
    const out = new Array(n).fill(NaN);
    let s = 0;
    for (let i = 1; i <= period; i++) s += arr[i];
    let prev = s / period;
    out[period] = prev;
    for (let i = period + 1; i < n; i++) {
      prev = (prev * (period - 1) + arr[i]) / period;
      out[i] = prev;
    }
    return out;
  };
  const trS = rma(tr), pS = rma(plusDM), mS = rma(minusDM);
  const plusDI = [], minusDI = [], dxArr = new Array(n).fill(NaN);
  for (let i = period; i < n; i++) {
    if (trS[i] > 0) {
      const pdi = (100 * pS[i]) / trS[i];
      const mdi = (100 * mS[i]) / trS[i];
      plusDI.push({ time: bars[i].time, value: pdi });
      minusDI.push({ time: bars[i].time, value: mdi });
      const sum = pdi + mdi;
      dxArr[i] = sum > 0 ? (100 * Math.abs(pdi - mdi)) / sum : 0;
    }
  }
  // ADX = RMA of DX with the same period. DX is first defined at index `period`,
  // so its RMA seeds over DX[period..2·period−1] and first emits at index 2·period−1.
  const adxOut = [];
  let s = 0, cnt = 0;
  for (let i = period; i < n; i++) {
    if (Number.isNaN(dxArr[i])) continue;
    s += dxArr[i];
    if (++cnt === period) {
      let prev = s / period;
      adxOut.push({ time: bars[i].time, value: prev });
      for (let k = i + 1; k < n; k++) {
        if (Number.isNaN(dxArr[k])) continue;
        prev = (prev * (period - 1) + dxArr[k]) / period;
        adxOut.push({ time: bars[k].time, value: prev });
      }
      break;
    }
  }
  return { plusDI, minusDI, adx: adxOut };
}

/** Bollinger Bands: middle = SMA(period), ±mult·population stdev. */
export function bollinger(bars, period = 20, mult = 2) {
  const upper = [], middle = [], lower = [];
  for (let i = period - 1; i < bars.length; i++) {
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) sum += bars[j].close;
    const mean = sum / period;
    let varSum = 0;
    for (let j = i - period + 1; j <= i; j++) varSum += (bars[j].close - mean) ** 2;
    const std = Math.sqrt(varSum / period);
    const t = bars[i].time;
    middle.push({ time: t, value: mean });
    upper.push({ time: t, value: mean + mult * std });
    lower.push({ time: t, value: mean - mult * std });
  }
  return { upper, middle, lower };
}

/** MACD: macd = EMA(fast) − EMA(slow); signal = EMA(macd, signal); hist = diff. */
export function macd(bars, fast = 12, slow = 26, signal = 9) {
  const ef = ema(bars, fast);
  const slowMap = new Map(ema(bars, slow).map((p) => [p.time, p.value]));
  const macdLine = ef
    .filter((p) => slowMap.has(p.time))
    .map((p) => ({ time: p.time, value: p.value - slowMap.get(p.time) }));
  const signalLine = ema(macdLine, signal, "value");
  const sigMap = new Map(signalLine.map((p) => [p.time, p.value]));
  const hist = macdLine
    .filter((p) => sigMap.has(p.time))
    .map((p) => {
      const h = p.value - sigMap.get(p.time);
      return { time: p.time, value: h, color: h >= 0 ? "rgba(38,166,154,0.6)" : "rgba(239,83,80,0.6)" };
    });
  return { macd: macdLine, signal: signalLine, hist };
}

/** Stochastic oscillator: %K from kPeriod high/low range, %D = SMA(%K, dPeriod). */
export function stochastic(bars, kPeriod = 14, dPeriod = 3) {
  const k = [];
  for (let i = kPeriod - 1; i < bars.length; i++) {
    let hh = -Infinity, ll = Infinity;
    for (let j = i - kPeriod + 1; j <= i; j++) {
      if (bars[j].high > hh) hh = bars[j].high;
      if (bars[j].low < ll) ll = bars[j].low;
    }
    const denom = hh - ll;
    k.push({ time: bars[i].time, value: denom === 0 ? 50 : ((bars[i].close - ll) / denom) * 100 });
  }
  return { k, d: sma(k, dPeriod, "value") };
}

/**
 * Fibonacci retracement grid over the bar range.
 *
 * Takes the period high/low and returns the standard retracement ratios
 * (measured down from the high: 0% at the high, 100% at the low) as horizontal
 * price-line descriptors. 50% and 61.8% — the most-watched levels — are drawn
 * brighter. Like `pivotLevels` these are annotations, not a time series.
 */
export function fibLevels(bars, ratios = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]) {
  if (!bars.length) return [];
  let hi = -Infinity, lo = Infinity;
  for (const b of bars) { if (b.high > hi) hi = b.high; if (b.low < lo) lo = b.low; }
  const span = hi - lo;
  return ratios.map((r) => ({
    price: hi - span * r,
    color: r === 0.5 || r === 0.618 ? "rgba(171,71,188,0.9)" : "rgba(171,71,188,0.4)",
    title: `${(r * 100).toFixed(1)}%`,
  }));
}

/**
 * Fibonacci extension: measured-move profit TARGETS projected beyond the range
 * high (the conventional "where to take profit on a long" levels). Each ratio is
 * a multiple of the high−low span measured up from the low, so 1.618× lands at
 * low + 1.618·span (above the high). Amber to distinguish from the retracement.
 * Like `fibLevels` these are price-line annotations, not a time series.
 */
export function fibExtension(bars, ratios = [1.272, 1.618, 2.618]) {
  if (!bars.length) return [];
  let hi = -Infinity, lo = Infinity;
  for (const b of bars) { if (b.high > hi) hi = b.high; if (b.low < lo) lo = b.low; }
  const span = hi - lo;
  return ratios.map((e) => ({
    price: lo + span * e,
    color: "rgba(255,193,7,0.6)",
    title: `↑${e}×`,
  }));
}

/**
 * Swing pivots: a bar is a pivot high when its high is the strict maximum of a
 * `left`/`right`-bar window, and a pivot low when its low is the strict minimum
 * (the same rule `pivotLevels` clusters). Returns { highs, lows }, each a
 * time-ordered list of { time, index, price }. Pivots only confirm `right`
 * bars after they form, so the last `right` bars can never hold one.
 */
export function pivots(bars, left = 5, right = 5) {
  if (bars.length < left + right + 1) return { highs: [], lows: [] };
  const highs = [], lows = [];
  for (let i = left; i < bars.length - right; i++) {
    let isHigh = true, isLow = true;
    const hi = bars[i].high, lo = bars[i].low;
    for (let j = i - left; j <= i + right; j++) {
      if (j === i) continue;
      if (bars[j].high >= hi) isHigh = false;
      if (bars[j].low <= lo) isLow = false;
    }
    if (isHigh) highs.push({ time: bars[i].time, index: i, price: hi });
    if (isLow) lows.push({ time: bars[i].time, index: i, price: lo });
  }
  return { highs, lows };
}

/**
 * Regular price↔oscillator divergence between consecutive like swings.
 *
 * Bullish (bottom) divergence: price prints a lower low while the oscillator
 * prints a higher low — downside momentum fading even as price falls. Bearish
 * (top) divergence: price prints a higher high while the oscillator prints a
 * lower high — upside momentum fading. Swings come from `pivots`; the
 * oscillator is RSI (`osc: "rsi"`, default) or the MACD histogram
 * (`osc: "macd"`), sampled at each pivot's bar. Each event joins the two
 * pivots of the pair and is anchored at the second (confirmation) pivot, so a
 * marker / connector line drawn there sits where the divergence becomes
 * actionable. Events are returned oldest-first.
 */
export function divergence(bars, { left = 5, right = 5, osc = "rsi", rsiPeriod = 14 } = {}) {
  const { highs, lows } = pivots(bars, left, right);
  const pts = osc === "macd" ? macd(bars).hist : rsi(bars, rsiPeriod);
  const val = new Map(pts.map((p) => [p.time, p.value]));
  const at = (p) => (p && val.has(p.time) ? val.get(p.time) : null);
  const events = [];
  for (let i = 1; i < highs.length; i++) {
    const a = highs[i - 1], b = highs[i];
    const oa = at(a), ob = at(b);
    if (oa == null || ob == null) continue;
    if (b.price > a.price && ob < oa) { // price higher high, oscillator lower high
      events.push({ type: "bear", aTime: a.time, aPrice: a.price, aOsc: oa, bTime: b.time, bPrice: b.price, bOsc: ob });
    }
  }
  for (let i = 1; i < lows.length; i++) {
    const a = lows[i - 1], b = lows[i];
    const oa = at(a), ob = at(b);
    if (oa == null || ob == null) continue;
    if (b.price < a.price && ob > oa) { // price lower low, oscillator higher low
      events.push({ type: "bull", aTime: a.time, aPrice: a.price, aOsc: oa, bTime: b.time, bPrice: b.price, bOsc: ob });
    }
  }
  return events.sort((x, y) => x.bTime - y.bTime);
}

/**
 * Most recent close-based cross of a `price` level — the engine behind price
 * alerts. "up" (上穿) fires when a bar closes at/above the level after the prior
 * bar closed below it; "down" (下穿) is the mirror. Returns the timestamp of the
 * latest crossing bar, or null if the level was never crossed in `bars` — so a
 * caller can show 监控中 vs 已触发(date). Close-based (not intraday touch) so the
 * trigger is unambiguous and deterministic.
 */
export function priceCross(bars, price, dir = "up") {
  let last = null;
  for (let i = 1; i < bars.length; i++) {
    const a = bars[i - 1].close, b = bars[i].close;
    const cross = dir === "down" ? a > price && b <= price : a < price && b >= price;
    if (cross) last = bars[i].time;
  }
  return last;
}

/**
 * Classic single/two-bar candlestick reversal patterns, detected locally from
 * OHLC (Pine-style — the chart ships raw candles, patterns derive in-browser).
 * Returns four time-ordered lists of `{ time, price }` (price anchored at the
 * pattern's visual tip — low for bullish, high for bearish):
 *   - hammer:        long lower shadow (≥ 2× body), tiny upper shadow → bullish
 *   - shootingStar:  long upper shadow (≥ 2× body), tiny lower shadow → bearish
 *   - bullEngulf:    prev down bar fully engulfed by a current up bar
 *   - bearEngulf:    prev up bar fully engulfed by a current down bar
 * Body ≈ 0 (doji-ish) bars are skipped for the shadow patterns to stay well-defined.
 */
export function candlePatterns(bars) {
  const out = { hammer: [], shootingStar: [], bullEngulf: [], bearEngulf: [], doji: [], marubozu: [], threeSoldiers: [], threeCrows: [] };
  const body = (b) => Math.abs(b.close - b.open);
  const up = (b) => b.close >= b.open;
  for (let i = 0; i < bars.length; i++) {
    const b = bars[i];
    const rng = b.high - b.low;
    const bod = body(b);
    if (rng > 0 && bod > 0) {
      const upper = b.high - Math.max(b.open, b.close);
      const lower = Math.min(b.open, b.close) - b.low;
      if (lower >= 2 * bod && upper <= bod) out.hammer.push({ time: b.time, price: b.low });
      if (upper >= 2 * bod && lower <= bod) out.shootingStar.push({ time: b.time, price: b.high });
    }
    // single-bar indecision / momentum: doji (open≈close) and marubozu (body fills the range)
    if (rng > 0) {
      if (bod / rng <= 0.1) out.doji.push({ time: b.time, price: (b.high + b.low) / 2 });
      if (bod / rng >= 0.9) out.marubozu.push({ time: b.time, price: b.close, dir: up(b) ? 1 : -1 });
    }
    if (i > 0) {
      const p = bars[i - 1];
      if (!up(p) && up(b) && b.open <= p.close && b.close >= p.open) out.bullEngulf.push({ time: b.time, price: b.low });
      if (up(p) && !up(b) && b.close <= p.open && b.open >= p.close) out.bearEngulf.push({ time: b.time, price: b.high });
    }
    // three-bar reversals: three white soldiers / three black crows — each bar opens
    // within the prior body and closes further in the trend direction.
    if (i >= 2) {
      const p1 = bars[i - 2], p2 = bars[i - 1];
      if (up(p1) && up(p2) && up(b) && p2.close > p1.close && b.close > p2.close &&
          p2.open >= p1.open && p2.open <= p1.close && b.open >= p2.open && b.open <= p2.close)
        out.threeSoldiers.push({ time: b.time, price: b.low });
      if (!up(p1) && !up(p2) && !up(b) && p2.close < p1.close && b.close < p2.close &&
          p2.open <= p1.open && p2.open >= p1.close && b.open <= p2.open && b.open >= p2.close)
        out.threeCrows.push({ time: b.time, price: b.high });
    }
  }
  return out;
}

/**
 * Pivot-based support / resistance levels.
 *
 * Reuses `pivots` for swing detection, then clusters nearby pivots (within
 * `tol` of the running cluster mean) and ranks by number of touches; the top
 * `n` of each side are returned as horizontal price-line descriptors (red
 * resistance / green support), not time series. S/R levels are the classic
 * manual annotation a trader draws — here derived automatically, Pine-style.
 */
export function pivotLevels(bars, left = 5, right = 5, n = 3, tol = 0.008) {
  const { highs, lows } = pivots(bars, left, right);
  if (!highs.length && !lows.length) return [];
  const cluster = (arr) => {
    arr.sort((a, b) => a - b);
    const groups = [];
    for (const p of arr) {
      const last = groups[groups.length - 1];
      if (last && Math.abs(p - last.mean) / last.mean < tol) {
        last.mean = (last.mean * last.count + p) / (last.count + 1);
        last.count++;
      } else {
        groups.push({ mean: p, count: 1 });
      }
    }
    return groups.sort((a, b) => b.count - a.count).slice(0, n);
  };
  const resist = cluster(highs.map((p) => p.price)).map((l) => ({ price: l.mean, color: "rgba(239,83,80,0.55)", title: `R ${l.mean.toFixed(2)} ×${l.count}` }));
  const support = cluster(lows.map((p) => p.price)).map((l) => ({ price: l.mean, color: "rgba(38,166,154,0.55)", title: `S ${l.mean.toFixed(2)} ×${l.count}` }));
  return [...resist, ...support];
}

/**
 * Parabolic SAR (Wilder's stop-and-reverse).
 *
 * Tracks an accelerating trailing stop: in an uptrend the SAR sits below price
 * and rises by af·(ep − sar) each bar (clamped to the prior two lows); when price
 * prints a low beneath it the trend flips and the SAR jumps to the old extreme.
 * `afStep`/`afMax` are the acceleration-factor step and cap, raised each time a
 * new extreme is made. Returns two aligned point sets — `up` (dots under price in
 * an uptrend) and `down` (dots over price in a downtrend) — so they plot as two
 * marker-only series rather than one colour-shifting line.
 */
export function psar(bars, afStep = 0.02, afMax = 0.2) {
  const n = bars.length;
  if (n < 2) return { up: [], down: [] };
  const up = [], down = [];
  let bull = bars[1].close >= bars[0].close;
  let af = afStep;
  let ep = bull ? bars[0].high : bars[0].low;
  let sar = bull ? bars[0].low : bars[0].high;
  const push = (i) => (bull ? up : down).push({ time: bars[i].time, value: sar });
  push(0);
  for (let i = 1; i < n; i++) {
    sar = sar + af * (ep - sar);
    if (bull) {
      const lo1 = bars[i - 1].low;
      const lo2 = i >= 2 ? bars[i - 2].low : lo1;
      if (lo2 < sar) sar = lo2; // SAR may not sit above the prior two lows
      if (lo1 < sar) sar = lo1;
      if (bars[i].low < sar) { bull = false; sar = ep; ep = bars[i].low; af = afStep; } // reversal
      else if (bars[i].high > ep) { ep = bars[i].high; af = Math.min(af + afStep, afMax); }
    } else {
      const hi1 = bars[i - 1].high;
      const hi2 = i >= 2 ? bars[i - 2].high : hi1;
      if (hi2 > sar) sar = hi2; // SAR may not sit below the prior two highs
      if (hi1 > sar) sar = hi1;
      if (bars[i].high > sar) { bull = true; sar = ep; ep = bars[i].high; af = afStep; } // reversal
      else if (bars[i].low < ep) { ep = bars[i].low; af = Math.min(af + afStep, afMax); }
    }
    push(i);
  }
  return { up, down };
}

/** RSI with Wilder smoothing. */
export function rsi(bars, period = 14) {
  if (bars.length <= period) return [];
  let gain = 0, loss = 0;
  for (let i = 1; i <= period; i++) {
    const ch = bars[i].close - bars[i - 1].close;
    if (ch >= 0) gain += ch; else loss -= ch;
  }
  let avgGain = gain / period, avgLoss = loss / period;
  const val = (ag, al) => (al === 0 ? 100 : 100 - 100 / (1 + ag / al));
  const out = [{ time: bars[period].time, value: val(avgGain, avgLoss) }];
  for (let i = period + 1; i < bars.length; i++) {
    const ch = bars[i].close - bars[i - 1].close;
    const g = ch > 0 ? ch : 0, l = ch < 0 ? -ch : 0;
    avgGain = (avgGain * (period - 1) + g) / period;
    avgLoss = (avgLoss * (period - 1) + l) / period;
    out.push({ time: bars[i].time, value: val(avgGain, avgLoss) });
  }
  return out;
}

/**
 * Volume-weighted average price (VWAP) — the intraday fair-value benchmark.
 *
 * Cumulative sum of typical-price × volume divided by cumulative volume. With
 * `sessionReset` (intraday), the running sums reset at the start of each trading
 * day so VWAP re-anchors every session (the textbook intraday VWAP); otherwise
 * it is a single cumulative line from the first bar (an anchored VWAP). Typical
 * price = (high + low + close) / 3. Bars with no volume contribute their typical
 * price at zero weight, so VWAP is undefined until volume arrives.
 */
export function vwap(bars, sessionReset = false) {
  const out = [];
  let pv = 0, v = 0, prevDay = null;
  for (const b of bars) {
    const tp = (b.high + b.low + b.close) / 3;
    if (sessionReset) {
      const day = new Date(b.time * 1000).toISOString().slice(0, 10);
      if (prevDay !== null && day !== prevDay) { pv = 0; v = 0; } // new session → re-anchor
      prevDay = day;
    }
    pv += tp * (b.volume || 0);
    v += (b.volume || 0);
    if (v > 0) out.push({ time: b.time, value: pv / v });
  }
  return out;
}

/**
 * Heikin-Ashi (平均K) — a smoothed candle series that filters noise to expose the
 * underlying trend. Each bar is recomputed from the raw OHLC:
 *   HA_close = (open + high + low + close) / 4          (the bar's average price)
 *   HA_open  = (prev_HA_open + prev_HA_close) / 2       (seeded with (open+close)/2)
 *   HA_high  = max(high, HA_open, HA_close)
 *   HA_low   = min(low,  HA_open, HA_close)
 * Because HA_open carries the prior bar's smoothing, a run of up-bars (HA_close >
 * HA_open, no lower wick) reads as a clean uptrend and vice-versa — the classic
 * "trade with the HA colour" technique. time/volume pass through unchanged so the
 * series drops into a candlestick chart 1:1. Indicators stay on the RAW bars; only
 * the displayed candles are HA.
 */
export function heikinAshi(bars) {
  const n = bars.length;
  if (!n) return [];
  const out = new Array(n);
  const c0 = (bars[0].open + bars[0].high + bars[0].low + bars[0].close) / 4;
  let prevOpen = (bars[0].open + bars[0].close) / 2;
  out[0] = {
    time: bars[0].time, volume: bars[0].volume, open: prevOpen, close: c0,
    high: Math.max(bars[0].high, prevOpen, c0), low: Math.min(bars[0].low, prevOpen, c0),
  };
  for (let i = 1; i < n; i++) {
    const b = bars[i];
    const haClose = (b.open + b.high + b.low + b.close) / 4;
    const haOpen = (prevOpen + out[i - 1].close) / 2;
    out[i] = {
      time: b.time, volume: b.volume, open: haOpen, close: haClose,
      high: Math.max(b.high, haOpen, haClose), low: Math.min(b.low, haOpen, haClose),
    };
    prevOpen = haOpen;
  }
  return out;
}

/**
 * Ichimoku Kinko Hyo (一目均衡表) — the four core lines, returned un-shifted as
 * plain overlays (no leading-span displacement, no cloud canvas): each line is a
 * midpoint of a rolling high/low range.
 *   Tenkan-sen (转换线, conv=9):   midpoint of the conv-bar high/low range
 *   Kijun-sen  (基准线, base=26):  midpoint of the base-bar high/low range
 *   Senkou Span A (先行A):         (Tenkan + Kijun) / 2   (defined once both exist)
 *   Senkou Span B (先行B, span=52): midpoint of the span-bar high/low range
 * Tenkan/Kijun crosses and price's position vs the Span A–B band (the "cloud",
 * shown at-current rather than displaced forward) carry the signals. Each line
 * omits its own leading warm-up. [{time,value}] per line.
 */
export function ichimoku(bars, conv = 9, base = 26, span = 52) {
  const n = bars.length;
  const tenkan = [], kijun = [], spanA = [], spanB = [];
  if (!n) return { tenkan, kijun, spanA, spanB };
  const mid = (i, len) => {
    let hi = -Infinity, lo = Infinity;
    for (let k = i - len + 1; k <= i; k++) { if (bars[k].high > hi) hi = bars[k].high; if (bars[k].low < lo) lo = bars[k].low; }
    return (hi + lo) / 2;
  };
  const tMap = new Map();
  for (let i = conv - 1; i < n; i++) { const v = mid(i, conv); tenkan.push({ time: bars[i].time, value: v }); tMap.set(bars[i].time, v); }
  const kMap = new Map();
  for (let i = base - 1; i < n; i++) { const v = mid(i, base); kijun.push({ time: bars[i].time, value: v }); kMap.set(bars[i].time, v); }
  for (let i = base - 1; i < n; i++) { // Span A needs both Tenkan and Kijun
    const t = tMap.get(bars[i].time), k = kMap.get(bars[i].time);
    if (t != null && k != null) spanA.push({ time: bars[i].time, value: (t + k) / 2 });
  }
  for (let i = span - 1; i < n; i++) spanB.push({ time: bars[i].time, value: mid(i, span) });
  return { tenkan, kijun, spanA, spanB };
}

/**
 * SuperTrend — a single ATR-based trend-following line that flips colour on a
 * stop-and-reverse. Two bands are built off hl2 ± mult·ATR(period) and then
 * "snapped" to trend: within an uptrend the line rides the lower band (only
 * ever rising, since the band is held or raised — never lowered into price),
 * and within a downtrend it rides the upper band (only ever falling). The trend
 * flips only when price closes THROUGH the active band: close below the lower
 * band → switch to the upper band (bearish red); close above the upper band →
 * switch to the lower band (bullish green). Returned as two disjoint point sets
 * — `up` (the green lower-band segments) and `down` (the red upper-band
 * segments) — so each plots as its own line, exactly like `psar`'s up/down.
 * Emits from the first bar where Wilder ATR is defined (index `period`).
 */
export function superTrend(bars, period = 10, mult = 3) {
  const n = bars.length;
  const a = atr(bars, period);
  if (!a.length) return { up: [], down: [] };
  // ATR is [{time,value}] starting at bars[period]; spread it onto a per-index view.
  const atrAt = new Array(n).fill(NaN);
  for (let k = 0; k < a.length; k++) atrAt[period + k] = a[k].value;
  const up = [], down = [];
  let finalUpper = NaN, finalLower = NaN;
  let trend = 1; // 1 = up (line rides the lower band), -1 = down
  let seeded = false;
  for (let i = 0; i < n; i++) {
    if (Number.isNaN(atrAt[i])) continue; // ATR warm-up — no line yet
    const b = bars[i];
    const hl2 = (b.high + b.low) / 2;
    const basicUpper = hl2 + mult * atrAt[i];
    const basicLower = hl2 - mult * atrAt[i];
    const prevClose = bars[i - 1]?.close ?? b.close;
    if (!seeded) { finalUpper = basicUpper; finalLower = basicLower; seeded = true; }
    else {
      // upper band only ever falls (held, or lowered when price pushes through);
      // lower band only ever rises — the "snap" that keeps the stop on trend's side.
      finalUpper = basicUpper < finalUpper || prevClose > finalUpper ? basicUpper : finalUpper;
      finalLower = basicLower > finalLower || prevClose < finalLower ? basicLower : finalLower;
    }
    if (trend === 1) { if (b.close < finalLower) trend = -1; } // close broke the up-stop → flip
    else if (b.close > finalUpper) trend = 1;                  // close broke the down-stop → flip
    (trend === 1 ? up : down).push({ time: b.time, value: trend === 1 ? finalLower : finalUpper });
  }
  return { up, down };
}

/**
 * One-timeframe technical snapshot for a multi-timeframe confluence table:
 * trend (close vs SMA), RSI level + zone, MACD line vs signal, rolled into a
 * single vote in [-3, 3] (trend ±1, MACD ±1, RSI ±1 only when clearly above 55
 * or below 45, else 0). Returns null when there aren't enough bars to form all
 * three. `lastVal` is the last defined point of a [{time,value}] series.
 */
export function tfSignal(bars, { maPeriod = 50, rsiPeriod = 14 } = {}) {
  const need = Math.max(maPeriod, rsiPeriod) + 1;
  if (!bars || bars.length < need) return null;
  const lastVal = (arr) => { for (let i = arr.length - 1; i >= 0; i--) if (arr[i]?.value != null) return arr[i].value; return null; };
  const price = bars[bars.length - 1].close;
  const ma = lastVal(sma(bars, maPeriod));
  const rsiVal = lastVal(rsi(bars, rsiPeriod));
  const M = macd(bars);
  const macdVal = lastVal(M.macd);
  const signalVal = lastVal(M.signal);
  if (ma == null || rsiVal == null || macdVal == null || signalVal == null) return null;
  const trendUp = price > ma;
  const macdBull = macdVal > signalVal;
  const rsiZone = rsiVal > 70 ? "overbought" : rsiVal < 30 ? "oversold" : "neutral";
  const rsiVote = rsiVal > 55 ? 1 : rsiVal < 45 ? -1 : 0;
  const vote = (trendUp ? 1 : -1) + (macdBull ? 1 : -1) + rsiVote; // [-3, 3]
  return { price, ma, trendUp, rsi: rsiVal, rsiZone, macd: macdVal, macdSignal: signalVal, macdBull, vote };
}

/**
 * Money Flow Index (MFI) — the volume-weighted RSI. Where RSI weighs every bar
 * equally by its close-to-close move, MFI weighs each move by the money flow
 * (typical price × volume), so the oscillator reflects whether REAL volume is
 * pushing prices up or down. Range 0–100; >80 = money-flow overbought, <20 =
 * money-flow oversold (a 14-period default, matching TradingView).
 *
 * Typical price TP = (H+L+C)/3; raw money flow RMF = TP·volume. Over the window,
 * positive flow = Σ RMF on bars where TP rose, negative flow = Σ RMF where TP
 * fell; MFI = 100 − 100/(1 + pos/neg). First output is at index `period`.
 */
export function mfi(bars, period = 14) {
  const n = bars.length;
  const out = [];
  if (n < period + 1) return out;
  const tp = bars.map((b) => (b.high + b.low + b.close) / 3);
  for (let i = period; i < n; i++) {
    let pos = 0;
    let neg = 0;
    for (let j = i - period + 1; j <= i; j++) {
      const rmf = tp[j] * bars[j].volume;
      if (tp[j] > tp[j - 1]) pos += rmf;
      else if (tp[j] < tp[j - 1]) neg += rmf;
    }
    const value = neg === 0 ? 100 : 100 - 100 / (1 + pos / neg);
    out.push({ time: bars[i].time, value });
  }
  return out;
}

// Commodity Channel Index (Lambert, 1980): how far the typical price sits, in
// mean-absolute-deviation units, above/below its own SMA. Unbounded and
// 0-centred — unlike RSI/MFI it is NOT pinned to 0–100. Lambert's constant
// 0.015 calibrates ±100 as the "unusually strong / weak" thresholds.
export function cci(bars, period = 20) {
  const n = bars.length;
  const out = [];
  if (n < period) return out;
  const tp = bars.map((b) => (b.high + b.low + b.close) / 3);
  for (let i = period - 1; i < n; i++) {
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) sum += tp[j];
    const ma = sum / period;
    let md = 0;
    for (let j = i - period + 1; j <= i; j++) md += Math.abs(tp[j] - ma);
    md /= period;
    const value = md === 0 ? 0 : (tp[i] - ma) / (0.015 * md);
    out.push({ time: bars[i].time, value });
  }
  return out;
}

// Donchian Channel (the turtle-trading breakout envelope): the highest high and
// lowest low over the last `period` bars, with their midpoint. Price closing
// above the upper band = breakout (new high) / below the lower = breakdown — a
// range-extreme lens, complementary to Bollinger's volatility-around-mean view.
export function donchian(bars, period = 20) {
  const n = bars.length;
  const out = { upper: [], lower: [], mid: [] };
  if (n < period) return out;
  for (let i = period - 1; i < n; i++) {
    let hi = -Infinity, lo = Infinity;
    for (let j = i - period + 1; j <= i; j++) {
      if (bars[j].high > hi) hi = bars[j].high;
      if (bars[j].low < lo) lo = bars[j].low;
    }
    out.upper.push({ time: bars[i].time, value: hi });
    out.lower.push({ time: bars[i].time, value: lo });
    out.mid.push({ time: bars[i].time, value: (hi + lo) / 2 });
  }
  return out;
}
