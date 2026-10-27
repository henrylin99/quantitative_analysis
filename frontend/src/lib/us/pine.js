/**
 * Pine-style custom indicator: compile a one-line expression over OHLCV into a
 * plotted series, evaluated client-side. Pure (no chart/DOM), so DetailPage and
 * its regression test share one implementation — the established cross-check.
 *
 * Grammar (deliberately small): numbers, the field identifiers close/open/high/
 * low/volume, function calls f(a, b), binary + - * /, unary minus, parentheses.
 * Functions return a rolling series aligned to the bars; arithmetic is element-
 * wise with scalar↔series broadcast. Warmup bars (e.g. the first n-1 of an SMA)
 * are NaN and dropped from the output.
 *
 * Pipeline: tokenize → shunting-yard (RPN) → evaluate over the bars → drop NaN.
 */

export const PINE_VARS = ["close", "open", "high", "low", "volume", "obv"];
export const PINE_FUNCS = ["sma", "ema", "wma", "rma", "hma", "rsi", "std", "change", "roc", "mom", "highest", "lowest", "atr", "abs", "max", "min"];

// ── rolling helpers over a Float64Array (NaN = undefined / warmup) ─────────

function winMean(src, n) {
  const out = new Float64Array(src.length).fill(NaN);
  if (n <= 0) return out;
  for (let i = n - 1; i < src.length; i++) {
    let sum = 0, ok = true;
    for (let j = i - n + 1; j <= i; j++) { const v = src[j]; if (!Number.isFinite(v)) { ok = false; break; } sum += v; }
    if (ok) out[i] = sum / n; // NaN if any term in the window was NaN
  }
  return out;
}

function ema(src, n) {
  const out = new Float64Array(src.length).fill(NaN);
  if (n <= 0) return out;
  let s0 = 0; while (s0 < src.length && !Number.isFinite(src[s0])) s0++; // skip leading NaN (warmup)
  if (src.length - s0 < n) return out;
  const k = 2 / (n + 1);
  let s = 0;
  for (let j = s0; j < s0 + n; j++) s += src[j];
  let prev = s / n;
  out[s0 + n - 1] = prev;
  for (let i = s0 + n; i < src.length; i++) {
    if (!Number.isFinite(src[i])) continue; // tolerate interior gaps without resetting
    prev = src[i] * k + prev * (1 - k);
    out[i] = prev;
  }
  return out;
}

function rsi(src, n) {
  const out = new Float64Array(src.length).fill(NaN);
  if (n <= 0 || src.length <= n) return out;
  let g = 0, l = 0;
  for (let i = 1; i <= n; i++) { const d = src[i] - src[i - 1]; if (d > 0) g += d; else l -= d; }
  let avgG = g / n, avgL = l / n;
  out[n] = 100 - 100 / (1 + (avgL === 0 ? 100 : avgG / avgL));
  for (let i = n + 1; i < src.length; i++) {
    const d = src[i] - src[i - 1];
    avgG = (avgG * (n - 1) + (d > 0 ? d : 0)) / n;
    avgL = (avgL * (n - 1) + (d < 0 ? -d : 0)) / n;
    out[i] = 100 - 100 / (1 + (avgL === 0 ? 100 : avgG / avgL));
  }
  return out;
}

function winStd(src, n) {
  const out = new Float64Array(src.length).fill(NaN);
  if (n <= 0) return out;
  const mean = winMean(src, n); // already NaN for any window containing NaN
  for (let i = n - 1; i < src.length; i++) {
    if (!Number.isFinite(mean[i])) continue; // window had a NaN → no output (matches winMean)
    let s = 0;
    for (let j = i - n + 1; j <= i; j++) s += (src[j] - mean[i]) ** 2;
    out[i] = Math.sqrt(s / n);
  }
  return out;
}

function highest(src, n) {
  const out = new Float64Array(src.length).fill(NaN);
  if (n <= 0) return out;
  for (let i = n - 1; i < src.length; i++) {
    let m = -Infinity, ok = true;
    for (let j = i - n + 1; j <= i; j++) { const v = src[j]; if (!Number.isFinite(v)) { ok = false; break; } if (v > m) m = v; }
    if (ok) out[i] = m;
  }
  return out;
}

function lowest(src, n) {
  const out = new Float64Array(src.length).fill(NaN);
  if (n <= 0) return out;
  for (let i = n - 1; i < src.length; i++) {
    let m = Infinity, ok = true;
    for (let j = i - n + 1; j <= i; j++) { const v = src[j]; if (!Number.isFinite(v)) { ok = false; break; } if (v < m) m = v; }
    if (ok) out[i] = m;
  }
  return out;
}

// Wilder ATR (period n): RMA of true range over high/low/close.
function atr(bars, n) {
  const len = bars.length;
  const out = new Float64Array(len).fill(NaN);
  if (n <= 0 || len <= n) return out;
  const tr = new Float64Array(len);
  tr[0] = bars[0].high - bars[0].low;
  for (let i = 1; i < len; i++) {
    tr[i] = Math.max(bars[i].high - bars[i].low, Math.abs(bars[i].high - bars[i - 1].close), Math.abs(bars[i].low - bars[i - 1].close));
  }
  let a = 0;
  for (let i = 1; i <= n; i++) a += tr[i];
  a /= n;
  out[n] = a;
  for (let i = n + 1; i < len; i++) { a = (a * (n - 1) + tr[i]) / n; out[i] = a; }
  return out;
}

// Linearly-weighted moving average (weights n..1, most recent bar weighs n).
function wma(src, n) {
  const out = new Float64Array(src.length).fill(NaN);
  if (n <= 0) return out;
  const denom = (n * (n + 1)) / 2;
  for (let i = n - 1; i < src.length; i++) {
    let s = 0, ok = true;
    for (let k = 0; k < n; k++) { const v = src[i - k]; if (!Number.isFinite(v)) { ok = false; break; } s += v * (n - k); }
    if (ok) out[i] = s / denom;
  }
  return out;
}

// Wilder's smoothing (RMA, alpha = 1/n, seeded with SMA(n)) — what RSI/ATR use internally.
function rma(src, n) {
  const out = new Float64Array(src.length).fill(NaN);
  if (n <= 0) return out;
  let s0 = 0; while (s0 < src.length && !Number.isFinite(src[s0])) s0++; // skip leading NaN (warmup)
  if (src.length - s0 < n) return out;
  let s = 0;
  for (let j = s0; j < s0 + n; j++) s += src[j];
  let prev = s / n;
  out[s0 + n - 1] = prev;
  for (let i = s0 + n; i < src.length; i++) {
    if (!Number.isFinite(src[i])) continue; // tolerate interior gaps without resetting
    prev = (prev * (n - 1) + src[i]) / n;
    out[i] = prev;
  }
  return out;
}

// Hull MA: WMA( 2*WMA(src, n/2) − WMA(src, n), round(sqrt(n)) ) — low-lag smoothing.
function hma(src, n) {
  const len = src.length;
  const out = new Float64Array(len).fill(NaN);
  if (n <= 0 || len < n) return out;
  const half = Math.max(1, Math.floor(n / 2));
  const sq = Math.max(1, Math.round(Math.sqrt(n)));
  const wHalf = wma(src, half);
  const wFull = wma(src, n);
  const raw = new Float64Array(len);
  for (let i = 0; i < len; i++) raw[i] = 2 * wHalf[i] - wFull[i];
  return wma(raw, sq);
}

// Shift a series back by n bars (out[i] = src[i-n], NaN for the first n) — the base
// for momentum functions (close[1], close[n]) without exposing a general [] operator.
function shift(src, n) {
  if (n <= 0) return src;
  const out = new Float64Array(src.length).fill(NaN);
  for (let i = n; i < src.length; i++) out[i] = src[i - n];
  return out;
}

// ── scalar ↔ series elementwise broadcast ─────────────────────────────────

const isArr = (v) => v instanceof Float64Array;
const toArr = (v, len, what) => {
  if (isArr(v)) return v;
  if (typeof v === "number" && Number.isFinite(v)) {
    const a = new Float64Array(len); a.fill(v); return a;
  }
  throw new Error(`${what} 不是序列或数值`);
};
const asPeriod = (v, what = "周期") => {
  if (typeof v !== "number" || !Number.isFinite(v)) throw new Error(`${what} 需为数值常量`);
  return Math.max(1, Math.round(v));
};
const map1 = (a, len, fn) => {
  if (typeof a === "number") return fn(a);
  const out = new Float64Array(len);
  for (let i = 0; i < len; i++) out[i] = fn(a[i]);
  return out;
};
const map2 = (a, b, len, fn) => {
  const an = typeof a === "number", bn = typeof b === "number";
  if (an && bn) return fn(a, b);
  const out = new Float64Array(len);
  for (let i = 0; i < len; i++) out[i] = fn(an ? a : a[i], bn ? b : b[i]);
  return out;
};

function applyFn(name, args, bars) {
  const len = bars.length;
  const [a, b] = args;
  switch (name) {
    case "sma": return winMean(toArr(a, len, "参数"), asPeriod(b));
    case "ema": return ema(toArr(a, len, "参数"), asPeriod(b));
    case "wma": return wma(toArr(a, len, "参数"), asPeriod(b));
    case "rma": return rma(toArr(a, len, "参数"), asPeriod(b));
    case "hma": return hma(toArr(a, len, "参数"), asPeriod(b));
    case "change": { const s = toArr(a, len, "参数"); const sh = shift(s, 1); return map2(s, sh, len, (x, y) => x - y); }
    case "mom": { const s = toArr(a, len, "参数"); const sh = shift(s, asPeriod(b)); return map2(s, sh, len, (x, y) => x - y); }
    case "roc": {
      const s = toArr(a, len, "参数"); const sh = shift(s, asPeriod(b));
      return map2(s, sh, len, (x, y) => Number.isFinite(y) && y !== 0 ? ((x - y) / y) * 100 : NaN);
    }
    case "rsi": return rsi(toArr(a, len, "参数"), asPeriod(b));
    case "std": return winStd(toArr(a, len, "参数"), asPeriod(b));
    case "highest": return highest(toArr(a, len, "参数"), asPeriod(b));
    case "lowest": return lowest(toArr(a, len, "参数"), asPeriod(b));
    case "atr": return atr(bars, asPeriod(a));
    case "abs": return map1(a, len, Math.abs);
    case "max": return map2(a, b, len, Math.max);
    case "min": return map2(a, b, len, Math.min);
    default: throw new Error(`未知函数 "${name}"`);
  }
}

// ── tokenizer ─────────────────────────────────────────────────────────────

function tokenize(s) {
  const toks = [];
  let i = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === " " || c === "\t") { i++; continue; }
    if (/[0-9.]/.test(c)) {
      let j = i + 1; while (j < s.length && /[0-9.]/.test(s[j])) j++;
      toks.push({ t: "num", v: parseFloat(s.slice(i, j)) }); i = j; continue;
    }
    if (/[a-zA-Z_]/.test(c)) {
      let j = i + 1; while (j < s.length && /[a-zA-Z0-9_]/.test(s[j])) j++;
      toks.push({ t: "id", v: s.slice(i, j).toLowerCase() }); i = j; continue;
    }
    if ("+-*/".includes(c)) { toks.push({ t: "op", v: c }); i++; continue; }
    if (c === "(") { toks.push({ t: "lp" }); i++; continue; }
    if (c === ")") { toks.push({ t: "rp" }); i++; continue; }
    if (c === "[") { toks.push({ t: "lb" }); i++; continue; }
    if (c === "]") { toks.push({ t: "rb" }); i++; continue; }
    if (c === ",") { toks.push({ t: "comma" }); i++; continue; }
    throw new Error(`非法字符 "${c}"`);
  }
  return toks;
}

// ── shunting-yard → RPN (handles functions + unary minus) ─────────────────

const PREC = { "+": 1, "-": 1, "*": 2, "/": 2, neg: 3 };

function toRpn(toks) {
  const out = [];
  const ops = []; // operator / function / lp markers
  const argc = []; // arg counters for open function calls
  const isOpTok = (tk) => tk && (tk.t === "op" || tk.t === "lp" || tk.t === "comma");
  for (let idx = 0; idx < toks.length; idx++) {
    const tk = toks[idx];
    if (tk.t === "num") { out.push({ t: "num", v: tk.v }); }
    else if (tk.t === "id") {
      const isCall = toks[idx + 1] && toks[idx + 1].t === "lp";
      if (isCall) {
        ops.push({ kind: "func", name: tk.v });
        argc.push(0);
      } else {
        out.push({ t: "id", v: tk.v });
      }
    } else if (tk.t === "lp") {
      ops.push({ kind: "lp" });
    } else if (tk.t === "lb") {
      ops.push({ kind: "lb" }); // start of a bar-index subscript: expr[n]
    } else if (tk.t === "comma") {
      while (ops.length && ops[ops.length - 1].kind !== "lp" && ops[ops.length - 1].kind !== "func") out.push(ops.pop());
      if (!ops.length) throw new Error("逗号不在函数调用内");
      if (argc.length) argc[argc.length - 1]++;
    } else if (tk.t === "op") {
      // unary minus at start / after an operator / "(" / "," → neg
      const unary = (tk.v === "-" || tk.v === "+") && (idx === 0 || isOpTok(toks[idx - 1]));
      if (unary) {
        if (tk.v === "-") ops.push({ t: "op", v: "neg", prec: PREC.neg, kind: "op" });
      } else {
        while (ops.length) {
          const top = ops[ops.length - 1];
          if (top.kind === "op" && top.prec >= PREC[tk.v]) out.push(ops.pop());
          else break;
        }
        ops.push({ t: "op", v: tk.v, prec: PREC[tk.v], kind: "op" });
      }
    } else if (tk.t === "rp") {
      while (ops.length && ops[ops.length - 1].kind !== "lp") out.push(ops.pop());
      if (!ops.length) throw new Error("括号不匹配");
      ops.pop(); // the lp
      if (ops.length && ops[ops.length - 1].kind === "func") {
        const f = ops.pop();
        const n = argc.pop();
        out.push({ t: "call", name: f.name, argc: n + 1 });
      }
    } else if (tk.t === "rb") {
      while (ops.length && ops[ops.length - 1].kind !== "lb") out.push(ops.pop());
      if (!ops.length) throw new Error("下标 [] 不匹配");
      ops.pop(); // the lb marker
      out.push({ t: "idx" }); // postfix: pops [series, n], shifts series back n bars
    }
  }
  while (ops.length) {
    const o = ops.pop();
    if (o.kind === "lp" || o.kind === "func" || o.kind === "lb") throw new Error("括号不匹配");
    out.push(o);
  }
  return out;
}

// ── evaluate RPN over the bars ────────────────────────────────────────────

function evaluate(rpn, bars) {
  const len = bars.length;
  const field = (name) => {
    const a = new Float64Array(len);
    for (let i = 0; i < len; i++) a[i] = bars[i][name];
    return a;
  };
  const close = field("close"), open = field("open"), high = field("high"), low = field("low"), volume = field("volume");
  // On-Balance Volume: cumulative signed volume (up-day +volume, down-day −volume),
  // a built-in series like close/open — exposes volume flow to the expression engine.
  const obv = new Float64Array(len);
  if (len > 0) obv[0] = 0;
  for (let i = 1; i < len; i++) {
    obv[i] = close[i] > close[i - 1] ? obv[i - 1] + volume[i]
      : close[i] < close[i - 1] ? obv[i - 1] - volume[i]
      : obv[i - 1];
  }
  const series = { close, open, high, low, volume, obv };
  const st = [];
  for (const node of rpn) {
    if (node.t === "num") st.push(node.v);
    else if (node.t === "id") {
      if (!(node.v in series)) throw new Error(`未知变量 "${node.v}"`);
      st.push(series[node.v]);
    } else if (node.t === "op") {
      if (node.v === "neg") { const a = st.pop(); st.push(map1(a, len, (x) => -x)); }
      else {
        const b = st.pop(), a = st.pop();
        const f = node.v === "+" ? (x, y) => x + y : node.v === "-" ? (x, y) => x - y : node.v === "*" ? (x, y) => x * y : (x, y) => x / y;
        st.push(map2(a, b, len, f));
      }
    } else if (node.t === "call") {
      const args = [];
      for (let k = 0; k < node.argc; k++) args.unshift(st.pop());
      if (args.length !== node.argc) throw new Error(`${node.name}() 参数不足`);
      st.push(applyFn(node.name, args, bars));
    } else if (node.t === "idx") {
      const nv = st.pop();
      const ser = st.pop();
      if (typeof nv !== "number" || !Number.isFinite(nv)) throw new Error("下标需为整数常量");
      const k = Math.round(nv);
      if (k < 0) throw new Error("下标需为非负整数");
      st.push(typeof ser === "number" ? ser : shift(ser, k)); // bar index of a constant is the constant
    }
  }
  if (st.length !== 1) throw new Error("表达式不完整");
  return st[0];
}

/**
 * Compile `expr` against `bars` → { points, stats, error }.
 * points: [{time,value}] (NaN dropped); stats: {min,max,last,n}; error: null | msg.
 */
export function evaluatePine(expr, bars) {
  if (!expr || !expr.trim()) return { points: [], stats: null, error: "请输入表达式" };
  if (!bars || bars.length < 2) return { points: [], stats: null, error: "数据不足" };
  let res;
  try {
    res = evaluate(toRpn(tokenize(expr)), bars);
  } catch (e) {
    return { points: [], stats: null, error: e.message || String(e) };
  }
  const arr = typeof res === "number" ? new Float64Array(bars.length).fill(res) : res;
  const points = [];
  let min = Infinity, max = -Infinity, last = null, n = 0;
  for (let i = 0; i < arr.length; i++) {
    const v = arr[i];
    if (Number.isFinite(v)) {
      points.push({ time: bars[i].time, value: v });
      if (v < min) min = v;
      if (v > max) max = v;
      last = v; n++;
    }
  }
  if (!points.length) return { points: [], stats: null, error: "无有效输出(周期可能大于数据量)" };
  return { points, stats: { min, max, last, n }, error: null };
}

/**
 * Zero-line crossings of an evaluated series — turn a custom indicator into a
 * signal stream. Returns [{ time, dir }]: dir +1 = up-cross (negative→positive),
 * -1 = down-cross. Times are valid bar times, so they double as price-pane
 * markers (e.g. a MACD-style line crossing zero = a trend-shift signal).
 */
export function zeroCrosses(points) {
  const out = [];
  let prev = null;
  for (const p of points) {
    if (!Number.isFinite(p.value)) continue;
    if (prev != null) {
      if (prev < 0 && p.value >= 0) out.push({ time: p.time, dir: 1 });
      else if (prev > 0 && p.value <= 0) out.push({ time: p.time, dir: -1 });
    }
    prev = p.value;
  }
  return out;
}
