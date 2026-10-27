/* eslint-disable react-hooks/exhaustive-deps */
// 美股 K线终端 —— 参考开源 K线终端实现：24 指标叠加、画线（水平/趋势/
// 测距/矩形，按代码+周期持久化到 localStorage）、Bar 回放、持仓模拟、背离、告警、
// 蜡烛形态、Pine 风格自定义指标、技术信号雷达、截图导出、自选股。
// 数据源为本项目的 /api/us-stock 历史日线（雅虎财经离线快照），周线由日线客户端聚合。
import { useEffect, useMemo, useRef, useState } from "react";
import { LineStyle } from "lightweight-charts";
import CandleChart from "../../components/us/CandleChart.jsx";
import SymbolPicker from "../../components/us/SymbolPicker.jsx";
import { fetchUsBars, fetchUsSnapshotRows, fetchUsSymbols, markersFromBars, toWeekly } from "../../api/usTerminal";
import { sma, ema, bollinger, macd, stochastic, rsi, pivotLevels, psar, fibLevels, fibExtension, divergence, vwap, priceCross, candlePatterns, atr, adx, heikinAshi, ichimoku, superTrend, mfi, cci, donchian } from "../../lib/us/indicators.js";
import { evaluatePine, zeroCrosses, PINE_VARS, PINE_FUNCS } from "../../lib/us/pine.js";
import "./us-tv.css";

const TFS = [
  { key: "daily", label: "日线" },
  { key: "weekly", label: "周线" },
];

const CHART_TYPES = [
  { key: "candle", label: "K线" },
  { key: "bar", label: "柱状" },
  { key: "line", label: "线形" },
  { key: "area", label: "面积" },
];

// visible-range presets, expressed in trading bars (null = fit all)
const RANGES = [
  { key: "3m", label: "3月", bars: 63 },
  { key: "6m", label: "6月", bars: 126 },
  { key: "1y", label: "1年", bars: 252 },
  { key: "all", label: "全部", bars: null },
];

// bar-replay playback speeds (ms per advanced bar)
const REPLAY_SPEEDS = [
  { key: 800, label: "0.5×" },
  { key: 400, label: "1×" },
  { key: 200, label: "2×" },
  { key: 100, label: "4×" },
];

// technical-radar strength → label / colour. score is the net vote share in [-1, 1].
const ratingLabel = (s) => (s > 0.4 ? "强烈看涨" : s > 0.1 ? "看涨" : s < -0.4 ? "强烈看跌" : s < -0.1 ? "看跌" : "中性");
const ratingColor = (s) => (s > 0.1 ? "#26a69a" : s < -0.1 ? "#ef5350" : "#9aa6b2");

// fundamentals shown for the charted symbol, each with a cross-sectional percentile
// (where it ranks in the whole market snapshot, 0 = lowest).
const FUND_METRICS = [
  { key: "market_cap", label: "市值" },
  { key: "forward_pe", label: "FwdPE" },
  { key: "roe", label: "ROE" },
  { key: "ret_20d", label: "20日涨" },
  { key: "dividend_yield", label: "股息" },
  { key: "signal_score", label: "评分" },
];
const fmtFund = (v, key) => {
  if (v == null || Number.isNaN(v)) return "—";
  if (key === "market_cap") return "$" + (v / 1e9).toFixed(1) + "B";
  if (key === "roe" || key === "ret_20d") return (v * 100).toFixed(1) + "%";
  if (key === "dividend_yield") return (v * 100).toFixed(2) + "%";
  return v.toFixed(1); // forward_pe, signal_score
};

export default function UsTerminalPage() {
  const [symbols, setSymbols] = useState([]);
  const [symbol, setSymbol] = useState(() => localStorage.getItem("us_tv_last_symbol") || "AAPL");
  const [tf, setTf] = useState("daily");
  const [dailyBars, setDailyBars] = useState([]); // 日线原始数据（周线由它聚合）
  const [dailyPatterns, setDailyPatterns] = useState([]); // 日线形态标记
  const [showMA, setShowMA] = useState(true);
  const [maType, setMaType] = useState("sma"); // sma | ema
  const [maPeriods, setMaPeriods] = useState([5, 20, 60]);
  const [showBB, setShowBB] = useState(false);
  const [showDC, setShowDC] = useState(false); // Donchian breakout channel overlay
  const [showMACD, setShowMACD] = useState(false);
  const [showStoch, setShowStoch] = useState(false);
  const [showRSI, setShowRSI] = useState(false);
  const [showMFI, setShowMFI] = useState(false); // MFI: volume-weighted RSI sub-pane
  const [showCCI, setShowCCI] = useState(false); // CCI: mean-deviation oscillator sub-pane
  const [showADX, setShowADX] = useState(false); // ADX/DMI trend-strength sub-pane
  const [showPSAR, setShowPSAR] = useState(false);
  const [showMarkers, setShowMarkers] = useState(true);
  const [showSR, setShowSR] = useState(false);
  const [showFib, setShowFib] = useState(false);
  const [showFibExt, setShowFibExt] = useState(false); // Fibonacci extension profit targets beyond the range high
  const [showVP, setShowVP] = useState(false);
  const [showVWAP, setShowVWAP] = useState(false);
  const [chartType, setChartType] = useState("candle");
  const [heikin, setHeikin] = useState(false); // Heikin-Ashi (平均K): display smoothed candles, indicators stay on raw bars
  const [showIchi, setShowIchi] = useState(false); // Ichimoku (一目均衡) four-line overlay
  const [showST, setShowST] = useState(false); // SuperTrend (超趋): ATR stop-and-reverse trend line
  const [range, setRange] = useState(252); // last ~1Y of trading days
  const [logScale, setLogScale] = useState(false);
  const [magnet, setMagnet] = useState(false);
  const [drawMode, setDrawMode] = useState(false);
  const [drawTool, setDrawTool] = useState("hline"); // hline | trend | measure | rect
  const [userLines, setUserLines] = useState([]); // manually drawn price lines
  const [pending, setPending] = useState(null); // first endpoint of an in-progress trendline / measurement / rectangle
  const [trendlines, setTrendlines] = useState([]); // [{ a:{time,price}, b:{time,price} }]
  const [measures, setMeasures] = useState([]); // [{ a:{time,price}, b:{time,price} }] — ruler measurements
  const [rects, setRects] = useState([]); // [{ t1, p1, t2, p2 }] — highlight zones (support/resistance, supply/demand)
  const [replay, setReplay] = useState(false); // bar-replay mode
  const [replayIdx, setReplayIdx] = useState(0); // how many bars revealed
  const [replayPlaying, setReplayPlaying] = useState(false);
  const [replaySpeed, setReplaySpeed] = useState(400);
  const [compareSyms, setCompareSyms] = useState([]); // [{symbol, bars}] rebased onto the main symbol
  const [compareInput, setCompareInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [snap, setSnap] = useState([]); // full-market snapshot, for the fundamentals panel
  const [showPos, setShowPos] = useState(false); // position/risk-reward simulator
  const [posEntry, setPosEntry] = useState("");
  const [posStop, setPosStop] = useState("");
  const [posTarget, setPosTarget] = useState("");
  const [posQty, setPosQty] = useState(100);
  const [posRisk, setPosRisk] = useState(""); // $ risk budget for risk-based position sizing
  const [posAtrMult, setPosAtrMult] = useState(1.5); // ATR stop multiplier
  const [showDiv, setShowDiv] = useState(false); // price↔oscillator divergence overlay + card
  const [divOsc, setDivOsc] = useState("rsi"); // rsi | macd — oscillator divergence is measured against
  const [showAlerts, setShowAlerts] = useState(false); // price-alert overlay + card
  const [alerts, setAlerts] = useState([]); // [{ id, price, dir }] — dir: "up" | "down" (session-only)
  const [alertPrice, setAlertPrice] = useState("");
  const [alertDir, setAlertDir] = useState("up");
  const [showCP, setShowCP] = useState(false); // candlestick reversal patterns overlay + card
  const [showPine, setShowPine] = useState(false); // Pine-style custom-indicator sub-pane + card
  const [showPineCross, setShowPineCross] = useState(true); // mark the indicator's zero-line crossings on the price pane
  const [pineExpr, setPineExpr] = useState("close - sma(close, 50)"); // user's indicator expression
  // persistent watchlist (自选): starred symbols kept in localStorage so the
  // quick-switch strip survives reloads. Stored as a plain symbol list.
  const [favs, setFavs] = useState(() => { try { return JSON.parse(localStorage.getItem("us_tv_favs") || "[]"); } catch (_) { return []; } });
  const writeFavs = (next) => { try { localStorage.setItem("us_tv_favs", JSON.stringify(next)); } catch (_) { /* storage disabled */ } return next; };
  const toggleFav = () => setFavs((prev) => writeFavs(prev.includes(symbol) ? prev.filter((s) => s !== symbol) : [...prev, symbol]));
  const removeFav = (s) => setFavs((prev) => writeFavs(prev.filter((x) => x !== s)));

  const pickSymbol = (s) => {
    setSymbol(s);
    try { localStorage.setItem("us_tv_last_symbol", s); } catch (_) { /* storage disabled */ }
  };

  // 全市场列表 + 截面快照（基本面面板用）
  useEffect(() => {
    fetchUsSymbols().then(setSymbols).catch(() => {});
    fetchUsSnapshotRows().then(setSnap).catch(() => {});
  }, []);

  // 当前生效的 bars（周线 = 日线客户端聚合）与后端形态标记
  const bars = useMemo(() => (tf === "weekly" ? toWeekly(dailyBars) : dailyBars), [tf, dailyBars]);

  useEffect(() => {
    if (!symbol) return;
    setLoading(true);
    // restore this symbol/timeframe's saved drawings (horizontal lines + trendlines + measurements)
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem(`us_tv_draw_${symbol}__${tf}`) || "{}"); } catch (_) { /* corrupt entry */ }
    setUserLines(Array.isArray(saved.lines) ? saved.lines : []);
    setTrendlines(Array.isArray(saved.trends) ? saved.trends : []);
    setMeasures(Array.isArray(saved.measures) ? saved.measures : []);
    setRects(Array.isArray(saved.rects) ? saved.rects : []);
    setPending(null);
    setPosEntry(""); setPosStop(""); setPosTarget(""); // re-default the position levels for the new price
    setCompareSyms([]); // compare bars are timeframe-specific; refetch after switch
    fetchUsBars(symbol, "2y")
      .then((b) => {
        setDailyBars(b);
        setDailyPatterns(markersFromBars(b));
        setReplayIdx(Math.max(20, Math.floor(b.length * 0.5))); // replay cursor → mid-history
      })
      .catch(() => { setDailyBars([]); setDailyPatterns([]); })
      .finally(() => setLoading(false));
  }, [symbol, tf]);

  // bar-replay: only the first `replayIdx` bars are visible, so every indicator /
  // signal / marker recomputes exactly as it would have at that moment in time.
  const chartBars = replay && bars.length ? bars.slice(0, replayIdx) : bars;
  // bars actually in view (respects the visible-range control) — S/R & Fib are
  // computed over this window so their levels stay on-screen.
  const viewBars = range == null || range >= chartBars.length ? chartBars : chartBars.slice(chartBars.length - range);
  // bars fed to the candle renderer: Heikin-Ashi smooths the OHLC for display when
  // toggled, while every indicator / price-line / marker keeps using the raw bars.
  const displayBars = heikin && chartBars.length ? heikinAshi(chartBars) : chartBars;
  const last = chartBars.length ? chartBars[chartBars.length - 1] : null;
  const prevBar = chartBars.length > 1 ? chartBars[chartBars.length - 2] : null;
  const change = last && prevBar ? ((last.close - prevBar.close) / prevBar.close) * 100 : null;
  const meta = symbols.find((s) => s.symbol === symbol);
  const lastTime = chartBars.length ? chartBars[chartBars.length - 1].time : Infinity;
  // 周线 bar 时间与日线标记不完全对齐 → 周线只显示客户端重算的形态标记
  const viewPatterns = tf === "weekly" ? [] : (replay ? dailyPatterns.filter((p) => p.time <= lastTime) : dailyPatterns);
  const filteredPatterns = showMarkers ? viewPatterns : [];

  // Ichimoku four-line overlay source (declared here, before `overlays` uses it,
  // to avoid a temporal-dead-zone reference — the overlays memo runs first).
  const ichiInfo = useMemo(() => (showIchi ? ichimoku(chartBars) : null), [showIchi, chartBars]);
  // SuperTrend overlay source (same TDZ precaution — overlays runs before later memos).
  const stInfo = useMemo(() => (showST ? superTrend(chartBars, 10, 3) : null), [showST, chartBars]);
  // Donchian breakout channel overlay source (same TDZ precaution).
  const dcInfo = useMemo(() => (showDC ? donchian(chartBars, 20) : null), [showDC, chartBars]);
  const dcNow = useMemo(() => {
    if (!dcInfo || !dcInfo.upper.length) return null;
    const u = dcInfo.upper[dcInfo.upper.length - 1].value;
    const l = dcInfo.lower[dcInfo.lower.length - 1].value;
    const m = dcInfo.mid[dcInfo.mid.length - 1].value;
    return { upper: u, lower: l, mid: m };
  }, [dcInfo]);
  // current SuperTrend regime: which series holds the most recent point (1=up, -1=down)
  const stNow = useMemo(() => {
    if (!stInfo) return null;
    const u = stInfo.up.length ? stInfo.up[stInfo.up.length - 1] : null;
    const d = stInfo.down.length ? stInfo.down[stInfo.down.length - 1] : null;
    if (!u && !d) return null;
    if (!d) return { dir: 1, value: u.value };
    if (!u) return { dir: -1, value: d.value };
    return u.time >= d.time ? { dir: 1, value: u.value } : { dir: -1, value: d.value };
  }, [stInfo]);

  // price-pane overlays: moving averages + optional Bollinger Bands
  const overlays = useMemo(() => {
    const o = [];
    if (showMA) {
      const fn = maType === "ema" ? ema : sma;
      const maCols = ["#ffd166", "#4f93e7", "#c792ea"];
      const tag = maType.toUpperCase();
      maPeriods.forEach((p, k) => {
        if (p > 0) o.push({ color: maCols[k], label: `${tag}${p}`, points: fn(chartBars, p) });
      });
    }
    if (showBB) {
      const bb = bollinger(chartBars, 20, 2);
      o.push({ color: "rgba(79,147,231,0.55)", label: "BOLL中", points: bb.middle });
      o.push({ color: "rgba(38,166,154,0.45)", label: "BOLL上", points: bb.upper });
      o.push({ color: "rgba(239,83,80,0.45)", label: "BOLL下", points: bb.lower });
    }
    if (showDC && dcInfo) {
      // Donchian: N-bar high/low envelope (the breakout channel) + midpoint.
      o.push({ color: "rgba(149,117,205,0.55)", label: "DC上", points: dcInfo.upper });
      o.push({ color: "rgba(149,117,205,0.55)", label: "DC下", points: dcInfo.lower });
      o.push({ color: "rgba(149,117,205,0.3)", label: "DC中", points: dcInfo.mid });
    }
    if (showPSAR) {
      const ps = psar(chartBars);
      o.push({ color: "#4dd0e1", dots: true, label: "SAR↑", points: ps.up });
      o.push({ color: "#ec407a", dots: true, label: "SAR↓", points: ps.down });
    }
    if (showVWAP) {
      // daily/weekly → cumulative from first bar
      o.push({ color: "#29b6f6", lineWidth: 1.5, label: "VWAP", points: vwap(chartBars, false) });
    }
    if (showST && stInfo) {
      // SuperTrend: green lower-band line (uptrend) / red upper-band line (downtrend)
      o.push({ color: "#26a69a", lineWidth: 2, label: "ST↑", points: stInfo.up });
      o.push({ color: "#ef5350", lineWidth: 2, label: "ST↓", points: stInfo.down });
    }
    if (showIchi && ichiInfo) {
      // Ichimoku four-line overlay (un-shifted): the Span A–B band is the "cloud".
      o.push({ color: "#ef5350", lineWidth: 1, label: "转换", points: ichiInfo.tenkan });
      o.push({ color: "#4f93e7", lineWidth: 2, label: "基准", points: ichiInfo.kijun });
      o.push({ color: "#26a69a", lineWidth: 1, label: "先行A", points: ichiInfo.spanA });
      o.push({ color: "#c792ea", lineWidth: 1, label: "先行B", points: ichiInfo.spanB });
    }
    // comparison symbols, rebased onto the main symbol's price at the first overlap:
    // the line starts at the main close and diverges by the compare symbol's return,
    // so out/under-performance reads directly off the main candle axis.
    if (compareSyms.length) {
      const mainByTime = new Map(chartBars.map((b) => [b.time, b.close]));
      const cmpCols = ["#ba68c8", "#4db6ac", "#ff8a65"];
      compareSyms.forEach((c, idx) => {
        const anchor = c.bars.find((b) => mainByTime.has(b.time));
        if (!anchor) return;
        const baseMain = mainByTime.get(anchor.time);
        const baseCmp = anchor.close || baseMain;
        const pts = [];
        for (const b of c.bars) {
          if (!mainByTime.has(b.time)) continue;
          pts.push({ time: b.time, value: baseMain * (b.close / baseCmp) });
        }
        o.push({ color: cmpCols[idx % cmpCols.length], lineWidth: 1, label: c.symbol, points: pts });
      });
    }
    // hand-drawn trendlines (two-point segments) + the pending first endpoint dot
    for (const t of trendlines) {
      o.push({ color: "#ff9800", lineWidth: 1, label: "", points: [
        { time: t.a.time, value: t.a.price }, { time: t.b.time, value: t.b.price },
      ] });
    }
    if (pending) o.push({ color: "#ff9800", dots: true, label: "", points: [{ time: pending.time, value: pending.price }] });
    return o;
  }, [chartBars, showMA, maType, maPeriods, showBB, showDC, dcInfo, showPSAR, showVWAP, stInfo, ichiInfo, compareSyms, trendlines, pending]);

  // chart click in draw mode: horizontal lines add/remove at the price; trendlines
  // anchor on the first click and commit a segment on the second (both need a bar time).
  // persist drawings (horizontal lines + trendlines) per symbol/timeframe, so they
  // survive reloads. Saved explicitly at each draw action to avoid stale-write races
  // that an always-on save effect would hit on symbol/timeframe switches.
  const saveDrawings = (lines, trends, meas, rs) => {
    try { localStorage.setItem(`us_tv_draw_${symbol}__${tf}`, JSON.stringify({ lines, trends, measures: meas, rects: rs })); } catch (_) { /* storage full / disabled */ }
  };

  const handleChartClick = ({ time, price }) => {
    if (drawTool === "hline") {
      const tol = price * 0.003;
      const idx = userLines.findIndex((l) => Math.abs(l.price - price) <= tol);
      const next = idx >= 0 ? userLines.filter((_, i) => i !== idx) : [...userLines, { price, color: "#ff9800", title: price.toFixed(2) }];
      setUserLines(next);
      saveDrawings(next, trendlines, measures, rects);
      return;
    }
    if (time == null) return; // trendline / measurement / rectangle endpoints must sit on a bar
    if (!pending) { setPending({ time, price }); return; }
    if (drawTool === "measure") {
      const next = [...measures, { a: pending, b: { time, price } }];
      setMeasures(next);
      setPending(null);
      saveDrawings(userLines, trendlines, next, rects);
      return;
    }
    if (drawTool === "rect") {
      const next = [...rects, { t1: pending.time, p1: pending.price, t2: time, p2: price }];
      setRects(next);
      setPending(null);
      saveDrawings(userLines, trendlines, measures, next);
      return;
    }
    const next = [...trendlines, { a: pending, b: { time, price } }];
    setTrendlines(next);
    setPending(null);
    saveDrawings(userLines, next, measures, rects);
  };

  const addCompare = async () => {
    const sym = compareInput.trim().toUpperCase();
    setCompareInput("");
    if (!sym || sym === symbol || compareSyms.some((c) => c.symbol === sym)) return;
    try {
      const b = await fetchUsBars(sym, "2y");
      if (b.length) setCompareSyms((prev) => [...prev, { symbol: sym, bars: b }].slice(0, 3));
    } catch (_) { /* symbol not available */ }
  };

  // Pine-style custom indicator: compile the user's expression over the (replay-
  // trimmed) bars; the resulting series is appended to `panes` as its own sub-pane.
  const pineInfo = useMemo(
    () => (showPine && chartBars.length >= 2 ? evaluatePine(pineExpr, chartBars) : null),
    [showPine, pineExpr, chartBars]
  );

  // ADX/DMI (Wilder) — the trend-STRENGTH system: +DI/−DI (bulls vs bears) and ADX
  // (>~25 = a tradeable trend). Computed once here and shared by the sub-pane and
  // the read-out so the legend numbers and the plotted line stay in lockstep.
  const adxInfo = useMemo(() => (showADX && chartBars.length > 28 ? adx(chartBars, 14) : null), [showADX, chartBars]);
  const adxNow = useMemo(() => {
    if (!adxInfo) return null;
    const lv = (arr) => { for (let i = arr.length - 1; i >= 0; i--) if (arr[i]?.value != null) return arr[i].value; return null; };
    return { pdi: lv(adxInfo.plusDI), mdi: lv(adxInfo.minusDI), adx: lv(adxInfo.adx) };
  }, [adxInfo]);

  // MFI (volume-weighted RSI): computed once, shared by the sub-pane and the
  // overbought/oversold read-out so the legend tracks the plotted line exactly.
  const mfiInfo = useMemo(() => (showMFI ? mfi(chartBars, 14) : null), [showMFI, chartBars]);
  const mfiNow = useMemo(() => {
    if (!mfiInfo || !mfiInfo.length) return null;
    for (let i = mfiInfo.length - 1; i >= 0; i--) if (mfiInfo[i]?.value != null) return mfiInfo[i].value;
    return null;
  }, [mfiInfo]);

  // CCI (Commodity Channel Index): typical price vs its SMA, in mean-deviation
  // units. 0-centred and unbounded; ±100 = Lambert's strong/weak thresholds.
  const cciInfo = useMemo(() => (showCCI ? cci(chartBars, 20) : null), [showCCI, chartBars]);
  const cciNow = useMemo(() => {
    if (!cciInfo || !cciInfo.length) return null;
    for (let i = cciInfo.length - 1; i >= 0; i--) if (cciInfo[i]?.value != null) return cciInfo[i].value;
    return null;
  }, [cciInfo]);

  // oscillator sub-panes, stacked top-to-bottom in this order
  const panes = useMemo(() => {
    const p = [];
    if (showMACD) {
      const m = macd(chartBars);
      p.push({
        lines: [{ color: "#4f93e7", label: "DIF", points: m.macd }, { color: "#ffd166", label: "DEA", points: m.signal }],
        hist: { points: m.hist },
        refs: [{ price: 0, color: "rgba(255,255,255,0.2)" }],
      });
    }
    if (showStoch) {
      const st = stochastic(chartBars, 14, 3);
      p.push({
        lines: [{ color: "#4f93e7", label: "K", points: st.k }, { color: "#ffd166", label: "D", points: st.d }],
        refs: [
          { price: 80, color: "rgba(239,83,80,0.5)" },
          { price: 50, color: "rgba(255,255,255,0.12)" },
          { price: 20, color: "rgba(38,166,154,0.5)" },
        ],
      });
    }
    if (showRSI) p.push({ lines: [{ color: "#b39ddb", label: "RSI", points: rsi(chartBars, 14) }], refs: [
      { price: 70, color: "rgba(239,83,80,0.5)" }, { price: 30, color: "rgba(38,166,154,0.5)" },
    ] });
    if (showMFI && mfiInfo) p.push({ lines: [{ color: "#80deea", label: "MFI", points: mfiInfo }], refs: [
      { price: 80, color: "rgba(239,83,80,0.5)" }, { price: 20, color: "rgba(38,166,154,0.5)" },
    ] });
    if (showCCI && cciInfo) p.push({ lines: [{ color: "#f06292", label: "CCI", points: cciInfo }], refs: [
      { price: 100, color: "rgba(239,83,80,0.5)" }, { price: 0, color: "rgba(255,255,255,0.12)" }, { price: -100, color: "rgba(38,166,154,0.5)" },
    ] });
    if (showADX && adxInfo) {
      p.push({
        lines: [
          { color: "#26a69a", label: "+DI", points: adxInfo.plusDI },
          { color: "#ef5350", label: "−DI", points: adxInfo.minusDI },
          { color: "#ffd166", lineWidth: 2, label: "ADX", points: adxInfo.adx },
        ],
        refs: [
          { price: 25, color: "rgba(255,193,7,0.45)" }, // 25 = the "is it trending?" line
          { price: 20, color: "rgba(255,255,255,0.10)" },
        ],
      });
    }
    // custom Pine indicator — its own sub-pane so its scale never clashes with price
    if (showPine && pineInfo && pineInfo.points.length) {
      p.push({ lines: [{ color: "#ff9800", label: "自定义", points: pineInfo.points }] });
    }
    return p;
  }, [chartBars, showMACD, showStoch, showRSI, showMFI, mfiInfo, showCCI, cciInfo, showADX, adxInfo, showPine, pineInfo]);

  // position simulator (long): entry/stop/target levels → risk-reward + $/% outcomes.
  // Null until all three prices are entered; the price-line memo draws them as solid refs.
  const posCalc = useMemo(() => {
    const pf = (v) => { const n = +v; return v !== "" && Number.isFinite(n) ? n : null; };
    const e = pf(posEntry), s = pf(posStop), t = pf(posTarget), q = pf(posQty);
    if (e == null || s == null || t == null) return null; // need all three prices
    const risk = e - s; // per-share loss to the stop (long)
    const reward = t - e;
    return {
      e, s, t, q: q ?? 0,
      rr: risk !== 0 ? reward / risk : null,
      risk$: risk * (q ?? 0), reward$: reward * (q ?? 0),
      lossPct: e ? s / e - 1 : 0, gainPct: e ? t / e - 1 : 0,
    };
  }, [posEntry, posStop, posTarget, posQty]);

  // ATR(14) of the current series + risk-based position sizing: given a $ risk
  // budget and the per-share risk (entry→stop), how many shares to hold. Pure.
  const posAtrVal = useMemo(() => { const s = atr(chartBars, 14); return s.length ? s[s.length - 1].value : null; }, [chartBars]);
  const sizing = useMemo(() => {
    const e = +posEntry, s = +posStop, r = +posRisk;
    if (!(Number.isFinite(e) && Number.isFinite(s) && Number.isFinite(r) && r > 0 && e !== s)) return null;
    return Math.floor(r / Math.abs(e - s));
  }, [posEntry, posStop, posRisk]);

  // horizontal price lines: manually drawn ones, auto S/R and Fib, then the position levels
  const priceLines = useMemo(
    () => [
      ...userLines,
      ...(showSR ? pivotLevels(viewBars) : []),
      ...(showFib ? fibLevels(viewBars) : []),
      ...(showFibExt ? fibExtension(viewBars) : []),
      ...(posCalc ? [
        { price: posCalc.e, color: "#4f93e7", lineStyle: LineStyle.Solid, lineWidth: 1, title: "入场" },
        { price: posCalc.s, color: "#ef5350", lineStyle: LineStyle.Solid, lineWidth: 1, title: "止损" },
        { price: posCalc.t, color: "#26a69a", lineStyle: LineStyle.Solid, lineWidth: 1, title: "止盈" },
      ] : []),
      // price alerts — dashed green (上穿) / red (下穿), labelled with direction
      ...(showAlerts ? alerts.map((a) => ({
        price: a.price,
        color: a.dir === "up" ? "#26a69a" : "#ef5350",
        lineStyle: LineStyle.Dashed, lineWidth: 1,
        title: `告警 ${a.dir === "up" ? "↑" : "↓"}`,
      })) : []),
    ],
    [userLines, viewBars, showSR, showFib, showFibExt, posCalc, showAlerts, alerts]
  );

  // alert rows with live cross status: re-scans chartBars so the badge updates as
  // more bars are revealed during replay (and on symbol/timeframe switch).
  const alertRows = useMemo(
    () => alerts.map((a) => ({ ...a, crossed: priceCross(chartBars, a.price, a.dir) })),
    [alerts, chartBars]
  );
  const addAlert = () => {
    const p = parseFloat(alertPrice);
    if (!Number.isFinite(p) || p <= 0) return;
    setAlerts((prev) => [...prev, { id: `${Date.now()}-${Math.random()}`, price: p, dir: alertDir }]);
    setAlertPrice("");
  };
  const removeAlert = (id) => setAlerts((prev) => prev.filter((a) => a.id !== id));

  // range statistics over the visible window (respects the range control & replay):
  // period return, annualized volatility (√252), high/low, average volume.
  const rangeStats = useMemo(() => {
    if (viewBars.length < 2) return null;
    const rets = [];
    for (let i = 1; i < viewBars.length; i++) {
      const r = viewBars[i].close / viewBars[i - 1].close - 1;
      if (Number.isFinite(r)) rets.push(r);
    }
    const mean = rets.reduce((a, b) => a + b, 0) / (rets.length || 1);
    const variance = rets.reduce((a, b) => a + (b - mean) ** 2, 0) / (rets.length || 1);
    const close = viewBars.map((b) => b.close);
    return {
      periodRet: close[close.length - 1] / close[0] - 1,
      annVol: Math.sqrt(variance) * Math.sqrt(252),
      high: Math.max(...viewBars.map((b) => b.high)),
      low: Math.min(...viewBars.map((b) => b.low)),
      avgVol: viewBars.reduce((a, b) => a + (b.volume || 0), 0) / viewBars.length,
      n: viewBars.length,
    };
  }, [viewBars]);

  // technical signal radar: each standard indicator casts a buy(+1)/sell(-1)/neutral(0)
  // vote on the latest bar, aggregated into a single -1..1 strength — the TradingView
  // "Technical Rating" idea. Runs over chartBars so it recomputes under bar-replay.
  const rating = useMemo(() => {
    if (chartBars.length < 60) return null;
    const lastClose = chartBars[chartBars.length - 1].close;
    const lv = (arr) => { for (let i = arr.length - 1; i >= 0; i--) if (arr[i]?.value != null) return arr[i].value; return null; };
    const votes = [];
    for (const p of [20, 50, 200]) {
      if (chartBars.length > p) {
        const sv = lv(sma(chartBars, p));
        if (sv != null) votes.push({ label: `价vs MA${p}`, vote: lastClose > sv ? 1 : -1 });
      }
    }
    if (chartBars.length > 50) {
      const e20 = lv(ema(chartBars, 20)), e50 = lv(ema(chartBars, 50));
      if (e20 != null && e50 != null) votes.push({ label: "EMA20/50", vote: e20 > e50 ? 1 : -1 });
    }
    const M = macd(chartBars);
    const mv = lv(M.macd), ms = lv(M.signal);
    if (mv != null && ms != null) votes.push({ label: "MACD", vote: mv > ms ? 1 : -1 });
    const rv = lv(rsi(chartBars, 14));
    if (rv != null) votes.push({ label: "RSI14", vote: rv > 55 ? 1 : rv < 45 ? -1 : 0 });
    const ST = stochastic(chartBars, 14, 3);
    const k = lv(ST.k), d = lv(ST.d);
    if (k != null && d != null) votes.push({ label: "KDJ", vote: k > d ? 1 : -1 });
    const buy = votes.filter((x) => x.vote > 0).length;
    const sell = votes.filter((x) => x.vote < 0).length;
    const neutral = votes.filter((x) => x.vote === 0).length;
    return { votes, buy, sell, neutral, score: votes.length ? (buy - sell) / votes.length : 0 };
  }, [chartBars]);

  // price↔oscillator divergence (regular bullish/bearish) over the charted bars.
  // Runs over chartBars so it recomputes under bar-replay; the oscillator source
  // (RSI or MACD-hist) is user-selectable. Markers join the patterns set so each
  // divergence prints an arrow at its confirmation pivot; the connectors are drawn
  // by CandleChart on the divergence overlay.
  const divInfo = useMemo(() => {
    const events = divergence(chartBars, { osc: divOsc });
    const bull = events.filter((e) => e.type === "bull").length;
    const bear = events.filter((e) => e.type === "bear").length;
    return { events, bull, bear, latest: events.length ? events[events.length - 1] : null };
  }, [chartBars, divOsc]);
  const divMarkers = useMemo(() => (showDiv ? divInfo.events.map((e) => ({
    time: e.bTime,
    position: e.type === "bull" ? "belowBar" : "aboveBar",
    color: e.type === "bull" ? "#26a69a" : "#ef5350",
    shape: e.type === "bull" ? "arrowUp" : "arrowDown",
    text: e.type === "bull" ? "底背" : "顶背",
  })) : []), [divInfo, showDiv]);

  // Pine indicator zero-line crossings → price-pane signal arrows (▲ up-cross /
  // ▼ down-cross). Turns the custom indicator into a custom signal generator.
  const pineCrosses = useMemo(
    () => (showPine && showPineCross && pineInfo?.points ? zeroCrosses(pineInfo.points) : []),
    [showPine, showPineCross, pineInfo]
  );
  const pineCrossMarkers = useMemo(() => pineCrosses.map((c) => ({
    time: c.time,
    position: c.dir > 0 ? "belowBar" : "aboveBar",
    color: c.dir > 0 ? "#ff9800" : "#ff7043",
    shape: c.dir > 0 ? "arrowUp" : "arrowDown",
    text: c.dir > 0 ? "↑0" : "↓0",
  })), [pineCrosses]);

  // candlestick reversal patterns (锤子/流星/看涨·看跌吞没) over chartBars — re-scans
  // under replay. Counts feed the card; cpMarkers join the merged pattern set.
  const cpInfo = useMemo(() => candlePatterns(chartBars), [chartBars]);
  const cpMarkers = useMemo(() => (showCP ? [
    ...cpInfo.hammer.map((p) => ({ time: p.time, position: "belowBar", color: "#26a69a", shape: "arrowUp", text: "锤" })),
    ...cpInfo.bullEngulf.map((p) => ({ time: p.time, position: "belowBar", color: "#26a69a", shape: "arrowUp", text: "吞" })),
    ...cpInfo.threeSoldiers.map((p) => ({ time: p.time, position: "belowBar", color: "#26a69a", shape: "arrowUp", text: "兵" })),
    ...cpInfo.shootingStar.map((p) => ({ time: p.time, position: "aboveBar", color: "#ef5350", shape: "arrowDown", text: "星" })),
    ...cpInfo.bearEngulf.map((p) => ({ time: p.time, position: "aboveBar", color: "#ef5350", shape: "arrowDown", text: "吞" })),
    ...cpInfo.threeCrows.map((p) => ({ time: p.time, position: "aboveBar", color: "#ef5350", shape: "arrowDown", text: "鸦" })),
    ...cpInfo.marubozu.map((p) => ({ time: p.time, position: p.dir > 0 ? "belowBar" : "aboveBar", color: p.dir > 0 ? "#4dd0e1" : "#ff8a65", shape: p.dir > 0 ? "arrowUp" : "arrowDown", text: "强" })),
    ...cpInfo.doji.map((p) => ({ time: p.time, position: "aboveBar", color: "#9aa6b2", shape: "circle", text: "十" })),
  ] : []), [cpInfo, showCP]);

  // candle markers + candle-pattern arrows + divergence arrows + Pine
  // zero-cross signals, merged + time-sorted.
  const chartPatterns = useMemo(() => {
    const all = [...filteredPatterns, ...cpMarkers, ...divMarkers, ...pineCrossMarkers];
    all.sort((a, b) => (a.time || 0) - (b.time || 0));
    return all;
  }, [filteredPatterns, cpMarkers, divMarkers, pineCrossMarkers]);

  // fundamentals for the charted symbol + each factor's cross-sectional percentile
  // (fraction of the market snapshot strictly below it). Null metrics get no bar.
  const fund = useMemo(() => {
    if (!snap.length) return null;
    const row = snap.find((s) => s.symbol === symbol);
    if (!row) return null;
    const stats = {};
    for (const m of FUND_METRICS) {
      const v = row[m.key];
      const vals = snap.map((r) => r[m.key]).filter((x) => x != null && !Number.isNaN(x)).sort((a, b) => a - b);
      stats[m.key] = { v, pct: v != null && Number.isFinite(v) && vals.length ? vals.filter((x) => x < v).length / vals.length : null };
    }
    return stats;
  }, [snap, symbol]);

  const toggleReplay = () => {
    if (!replay) {
      setReplayIdx(Math.max(20, Math.floor(bars.length * 0.5)));
      setReplayPlaying(false);
      setReplay(true);
    } else {
      setReplay(false);
      setReplayPlaying(false);
    }
  };

  // when the position simulator opens with all levels empty, default them off the
  // last close (entry = last, stop = −5%, target = +10%). Depends on showPos/last only
  // — NOT on the field values — so a user clearing one field isn't fought by a reseed;
  // the all-empty guard still re-seeds after a symbol switch (which clears all three).
  useEffect(() => {
    if (showPos && last && posEntry === "" && posStop === "" && posTarget === "") {
      setPosEntry(last.close.toFixed(2));
      setPosStop((last.close * 0.95).toFixed(2));
      setPosTarget((last.close * 1.10).toFixed(2));
    }
  }, [showPos, last]);

  const chartHandleRef = useRef(null);
  // export the current chart (candles/overlays/panes/markers/price lines) as a PNG.
  // takeScreenshot renders the lightweight-charts scene to an offscreen canvas; the
  // custom VP overlay + legend are separate DOM/canvas layers and aren't included.
  const screenshot = () => {
    const h = chartHandleRef.current;
    if (!h?.chart) return;
    const canvas = h.chart.takeScreenshot(true);
    const a = document.createElement("a");
    a.href = canvas.toDataURL("image/png");
    a.download = `${symbol}_${tf}.png`;
    a.click();
  };

  // bar-replay auto-advance: reveal one more bar per tick until the end
  useEffect(() => {
    if (!replay || !replayPlaying) return;
    const id = setInterval(() => {
      setReplayIdx((i) => {
        if (i >= bars.length) { setReplayPlaying(false); return i; }
        return i + 1;
      });
    }, replaySpeed);
    return () => clearInterval(id);
  }, [replay, replayPlaying, replaySpeed, bars.length]);

  return (
    <div className="us-tv">
      <div className="toolbar">
        <SymbolPicker symbols={symbols} value={symbol} onChange={pickSymbol} />
        <button data-fav-btn data-fav-active={favs.includes(symbol) ? "1" : "0"} className={favs.includes(symbol) ? "active" : ""} onClick={toggleFav} title={favs.includes(symbol) ? "移出自选" : "加入自选"} style={{ fontSize: 16, lineHeight: 1 }}>{favs.includes(symbol) ? "★" : "☆"}</button>
        <div className="group">
          {CHART_TYPES.map((c) => (
            <button key={c.key} className={chartType === c.key ? "active" : ""} onClick={() => setChartType(c.key)}>{c.label}</button>
          ))}
        </div>
        <span className="muted">{meta?.name}</span>
        <div className="group">
          {TFS.map((t) => (
            <button key={t.key} className={tf === t.key ? "active" : ""} onClick={() => setTf(t.key)}>
              {t.label}
            </button>
          ))}
        </div>
        <label><input type="checkbox" checked={showMA} onChange={(e) => setShowMA(e.target.checked)} /> MA</label>
        <label><input type="checkbox" checked={showBB} onChange={(e) => setShowBB(e.target.checked)} /> BOLL</label>
        <label title="Donchian 通道:N 根最高/最低价形成的突破包络(海龟交易),收盘突破上轨=创新高突破/跌破下轨=破位,中线=区间中值——与 BOLL 的均值回归视角互补,看区间极值"><input type="checkbox" checked={showDC} onChange={(e) => setShowDC(e.target.checked)} /> DC</label>
        <label><input type="checkbox" checked={showMACD} onChange={(e) => setShowMACD(e.target.checked)} /> MACD</label>
        <label><input type="checkbox" checked={showStoch} onChange={(e) => setShowStoch(e.target.checked)} /> KDJ</label>
        <label><input type="checkbox" checked={showRSI} onChange={(e) => setShowRSI(e.target.checked)} /> RSI</label>
        <label title="MFI 资金流量:成交量加权 RSI(0–100,>80 资金超买/<20 资金超卖),用量能确认 RSI 的超买超卖"><input type="checkbox" checked={showMFI} onChange={(e) => setShowMFI(e.target.checked)} /> MFI</label>
        <label title="CCI 商品通道指标:典型价(MA±0.015×均价偏差)的均值偏离度,0 居中且无上下界(区别于 RSI/MFI 的 0–100),>+100 强势上攻/<−100 弱势下行"><input type="checkbox" checked={showCCI} onChange={(e) => setShowCCI(e.target.checked)} /> CCI</label>
        <label><input type="checkbox" checked={showADX} onChange={(e) => setShowADX(e.target.checked)} /> ADX</label>
        <label><input type="checkbox" checked={showIchi} onChange={(e) => setShowIchi(e.target.checked)} /> 一目</label>
        <label><input type="checkbox" checked={showPSAR} onChange={(e) => setShowPSAR(e.target.checked)} /> SAR</label>
        <label title="SuperTrend 超趋:ATR 波动止损线(绿↑多头/红↓空头,翻转即转势)"><input type="checkbox" checked={showST} onChange={(e) => setShowST(e.target.checked)} /> 超趋</label>
        <label><input type="checkbox" checked={showMarkers} onChange={(e) => setShowMarkers(e.target.checked)} /> 信号</label>
        <label><input type="checkbox" checked={showSR} onChange={(e) => setShowSR(e.target.checked)} /> 支撑/阻力</label>
        <label><input type="checkbox" checked={showFib} onChange={(e) => setShowFib(e.target.checked)} /> Fib</label>
        <label><input type="checkbox" checked={showFibExt} onChange={(e) => setShowFibExt(e.target.checked)} /> Fib扩</label>
        <label><input type="checkbox" checked={showVP} onChange={(e) => setShowVP(e.target.checked)} /> 量能分布</label>
        <label><input type="checkbox" checked={showVWAP} onChange={(e) => setShowVWAP(e.target.checked)} /> VWAP</label>
        <div className="group">
          {RANGES.map((r) => (
            <button key={r.key} className={range === r.bars ? "active" : ""} onClick={() => setRange(r.bars)}>{r.label}</button>
          ))}
        </div>
        <label><input type="checkbox" checked={logScale} onChange={(e) => setLogScale(e.target.checked)} /> 对数</label>
        <label><input type="checkbox" checked={magnet} onChange={(e) => setMagnet(e.target.checked)} /> 磁吸</label>
        <label title="平均K(Heikin-Ashi):平滑后的K线,利于看趋势;指标/价位线仍按原始价计算"><input type="checkbox" checked={heikin} onChange={(e) => setHeikin(e.target.checked)} /> 平均K</label>
        <button className={drawMode ? "active" : ""} onClick={() => { setDrawMode((v) => !v); setPending(null); }}>画线</button>
        {drawMode && (
          <div className="group">
            <button className={drawTool === "hline" ? "active" : ""} onClick={() => { setDrawTool("hline"); setPending(null); }}>水平</button>
            <button className={drawTool === "trend" ? "active" : ""} onClick={() => { setDrawTool("trend"); setPending(null); }}>趋势</button>
            <button className={drawTool === "measure" ? "active" : ""} onClick={() => { setDrawTool("measure"); setPending(null); }}>测距</button>
            <button className={drawTool === "rect" ? "active" : ""} onClick={() => { setDrawTool("rect"); setPending(null); }}>矩形</button>
          </div>
        )}
        {(userLines.length > 0 || trendlines.length > 0 || measures.length > 0 || rects.length > 0) && (
          <button onClick={() => { setUserLines([]); setTrendlines([]); setMeasures([]); setRects([]); setPending(null); saveDrawings([], [], [], []); }}>清除</button>
        )}
        <button className={replay ? "active" : ""} onClick={toggleReplay}>回放</button>
        <button onClick={screenshot} title="导出当前图表为 PNG">📷 截图</button>
        <button className={showPos ? "active" : ""} onClick={() => setShowPos((v) => !v)} title="持仓/风险回报模拟(入场·止损·止盈)">持仓</button>
        <button className={showDiv ? "active" : ""} onClick={() => setShowDiv((v) => !v)} title="价格↔震荡指标背离(看涨/看跌)">背离</button>
        <button className={showAlerts ? "active" : ""} onClick={() => setShowAlerts((v) => !v)} title="价格告警(上穿/下穿价位)">告警</button>
        <button className={showCP ? "active" : ""} onClick={() => setShowCP((v) => !v)} title="蜡烛图反转形态(锤子/流星/吞没)">形态</button>
        <button className={showPine ? "active" : ""} onClick={() => setShowPine((v) => !v)} title="自定义指标(Pine 风格表达式,本地编译成序列)">自定义</button>
        <div className="group" style={{ alignItems: "center" }}>
          <input value={compareInput} onChange={(e) => setCompareInput(e.target.value)} placeholder="对比" style={{ width: 76 }}
            onKeyDown={(e) => { if (e.key === "Enter") addCompare(); }} />
          <button onClick={addCompare} title="添加对比标的">+</button>
        </div>
        {compareSyms.map((c, i) => (
          <span key={c.symbol} className="chip" style={{ borderColor: ["#ba68c8", "#4db6ac", "#ff8a65"][i % 3] }}>
            <i style={{ background: ["#ba68c8", "#4db6ac", "#ff8a65"][i % 3] }} />{c.symbol}
            <button onClick={() => setCompareSyms((prev) => prev.filter((x) => x.symbol !== c.symbol))}>×</button>
          </span>
        ))}
        {last && (
          <span style={{ marginLeft: "auto", fontVariantNumeric: "tabular-nums" }}>
            {symbol} <b>${last.close?.toFixed(2)}</b>{" "}
            <span className={change >= 0 ? "pos" : "neg"}>{change >= 0 ? "+" : ""}{change?.toFixed(2)}%</span>
            <span className="muted"> · {chartBars.length} bars{replay && " (回放)"}</span>
          </span>
        )}
      </div>

      {favs.length > 0 && (
        <div className="toolbar" style={{ flexWrap: "wrap", gap: 6, padding: "4px 10px", fontSize: 12 }}>
          <span className="muted">自选({favs.length}):</span>
          {favs.map((s) => (
            <span key={s} className="chip" data-fav={s} style={{ borderColor: s === symbol ? "#ff9800" : "rgba(255,152,0,0.4)" }}>
              <i style={{ background: "#ffd166" }} />
              <button onClick={() => pickSymbol(s)} style={{ background: "none", border: "none", color: s === symbol ? "#ff9800" : "#cdd6e0", cursor: "pointer", padding: 0, fontWeight: s === symbol ? 700 : 400 }}>{s}</button>
              <button onClick={() => removeFav(s)} title="移除" style={{ background: "none", border: "none", color: "#9aa6b2", cursor: "pointer", padding: 0, fontSize: 14, lineHeight: 1 }}>×</button>
            </span>
          ))}
        </div>
      )}

      {replay && bars.length > 0 && (
        <div className="replay-bar">
          <button onClick={() => { setReplayPlaying(false); setReplayIdx(Math.max(1, Math.floor(bars.length * 0.2))); }} title="跳到 20%">⏮</button>
          <button onClick={() => { setReplayPlaying(false); setReplayIdx((i) => Math.max(1, i - 1)); }} title="上一根">←</button>
          <button className="primary" onClick={() => setReplayPlaying((p) => !p)}>{replayPlaying ? "⏸ 暂停" : "▶ 播放"}</button>
          <button onClick={() => { setReplayPlaying(false); setReplayIdx((i) => Math.min(bars.length, i + 1)); }} title="下一根">→</button>
          <button onClick={() => { setReplayPlaying(false); setReplayIdx(bars.length); }} title="跳到最新">⏭</button>
          <input type="range" min={1} max={bars.length} value={replayIdx} onChange={(e) => { setReplayPlaying(false); setReplayIdx(+e.target.value); }} />
          <select value={replaySpeed} onChange={(e) => setReplaySpeed(+e.target.value)}>
            {REPLAY_SPEEDS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
          <span className="muted" style={{ fontVariantNumeric: "tabular-nums" }}>
            {replayIdx} / {bars.length}{last && <> · {new Date(last.time * 1000).toISOString().slice(0, 10)}</>}
          </span>
        </div>
      )}

      {showMA && !loading && (
        <div className="params-row">
          <span className="muted">均线</span>
          <div className="group">
            <button className={maType === "sma" ? "active" : ""} onClick={() => setMaType("sma")}>SMA</button>
            <button className={maType === "ema" ? "active" : ""} onClick={() => setMaType("ema")}>EMA</button>
          </div>
          {maPeriods.map((p, k) => (
            <label key={k}>P{k + 1}
              <input type="number" min={1} max={500} value={p} style={{ width: 52 }}
                onChange={(e) => setMaPeriods((prev) => prev.map((v, i) => (i === k ? Math.max(1, +e.target.value || 1) : v)))} />
            </label>
          ))}
        </div>
      )}

      {loading ? (
        <div className="spinner">加载中…</div>
      ) : bars.length ? (
        <div className="card">
          <CandleChart
            bars={displayBars}
            patterns={chartPatterns}
            overlays={overlays}
            panes={panes}
            priceLines={priceLines}
            height={460}
            showVP={showVP}
            title={symbol}
            chartType={chartType}
            range={range}
            logScale={logScale}
            magnet={magnet}
            drawMode={drawMode}
            onChartClick={handleChartClick}
            onReady={(h) => { chartHandleRef.current = h; }}
            measures={measures}
            pendingMeasure={(drawTool === "measure" && pending) || null}
            rects={rects}
            pendingRect={(drawTool === "rect" && pending) || null}
            divergence={showDiv ? divInfo.events : []}
          />
          <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
            {showMA && maPeriods.map((p, k) => (
              <span key={k} style={{ color: ["#ffd166", "#4f93e7", "#c792ea"][k] }}>●{maType.toUpperCase()}{p}</span>
            ))}&nbsp;
            {showBB && <span>●BOLL(20,2)&nbsp;&nbsp;</span>}
            {showDC && dcNow != null && <span data-dc-upper={dcNow.upper.toFixed(2)} data-dc-lower={dcNow.lower.toFixed(2)} data-dc-mid={dcNow.mid.toFixed(2)}>&nbsp;&nbsp;<span style={{ color: "rgba(149,117,205,0.9)" }}>●DC(20) 上{dcNow.upper.toFixed(2)} 下{dcNow.lower.toFixed(2)} 宽{((dcNow.upper - dcNow.lower) / dcNow.mid * 100).toFixed(1)}%</span></span>}
            {showMACD && <span>●MACD(12,26,9)&nbsp;&nbsp;</span>}
            {showStoch && <span>●KDJ(14,3)&nbsp;&nbsp;</span>}
            {showRSI && <span style={{ color: "#b39ddb" }}>●RSI(14)</span>}
            {showMFI && mfiNow != null && <span data-mfi={mfiNow.toFixed(1)}>&nbsp;&nbsp;<span style={{ color: "#80deea" }}>●MFI(14) {mfiNow.toFixed(1)}</span>{mfiNow >= 80 ? " 资金超买" : mfiNow <= 20 ? " 资金超卖" : ""}</span>}
            {showCCI && cciNow != null && <span data-cci={cciNow.toFixed(1)}>&nbsp;&nbsp;<span style={{ color: "#f06292" }}>●CCI(20) {cciNow.toFixed(1)}</span>{cciNow >= 100 ? " 强势" : cciNow <= -100 ? " 弱势" : ""}</span>}
            {showADX && adxNow && adxNow.adx != null && (
              <span data-adx-line>
                &nbsp;&nbsp;<span style={{ color: "#26a69a" }}>●+DI</span><b data-pdi style={{ fontVariantNumeric: "tabular-nums" }}>{adxNow.pdi.toFixed(1)}</b>
                &nbsp;<span style={{ color: "#ef5350" }}>●−DI</span><b data-mdi style={{ fontVariantNumeric: "tabular-nums" }}>{adxNow.mdi.toFixed(1)}</b>
                &nbsp;<span style={{ color: "#ffd166" }}>●ADX</span><b data-adx style={{ fontVariantNumeric: "tabular-nums" }}>{adxNow.adx.toFixed(1)}</b>
                &nbsp;({adxNow.adx >= 25 ? "强趋势" : adxNow.adx >= 20 ? "酝酿中" : "无趋势"})
              </span>
            )}
            {showPSAR && <span>&nbsp;&nbsp;<span style={{ color: "#4dd0e1" }}>●SAR↑</span> <span style={{ color: "#ec407a" }}>●SAR↓</span>&nbsp;&nbsp;</span>}
            {showST && stNow && <span data-st={stNow.dir} data-st-val={stNow.value != null ? stNow.value.toFixed(2) : ""}>&nbsp;&nbsp;<span style={{ color: stNow.dir > 0 ? "#26a69a" : "#ef5350" }}>●超趋 {stNow.dir > 0 ? "↑多头" : "↓空头"}{stNow.value != null ? ` $${stNow.value.toFixed(2)}` : ""}</span> (ATR(10)×3 波动止损,翻转即转势)</span>}
            {showSR && <span>&nbsp;&nbsp;<span style={{ color: "#ef5350" }}>---阻力</span> <span style={{ color: "#26a69a" }}>---支撑</span> (自动pivot)</span>}
            {showFib && <span style={{ color: "#ab47bc" }}>&nbsp;&nbsp;---Fib(0–100% 区间回撤)</span>}
            {showFibExt && <span style={{ color: "#ffc107" }}>&nbsp;&nbsp;---Fib扩(区间测距盈利目标 ↑1.272/1.618/2.618×)</span>}
            {showVP && <span style={{ color: "#64b5f6" }}>&nbsp;&nbsp;▌量能分布(按价位)</span>}
            {showVP && <span style={{ color: "#ffc107" }}>&nbsp;— POC(成交密集价) + 70%价值区</span>}
            {showVWAP && <span style={{ color: "#29b6f6" }}>&nbsp;&nbsp;●VWAP(累计)</span>}
            {showIchi && ichiInfo && <span data-ichi={ichiInfo.kijun.length}>&nbsp;&nbsp;<span style={{ color: "#ef5350" }}>●转换(9)</span> <span style={{ color: "#4f93e7" }}>●基准(26)</span> <span style={{ color: "#26a69a" }}>●先行A</span> <span style={{ color: "#c792ea" }}>●先行B(52)</span> 一目均衡(云=先行A/B 之间,价格在云上=多头)</span>}
            {showDiv && <span>&nbsp;&nbsp;<span style={{ color: "#26a69a" }}>— 看涨背离</span> <span style={{ color: "#ef5350" }}>— 看跌背离</span> ({divOsc === "macd" ? "MACD柱" : "RSI"})</span>}
            {(userLines.length > 0 || trendlines.length > 0 || measures.length > 0 || rects.length > 0) && <span style={{ color: "#ff9800" }}>&nbsp;&nbsp;---手动({userLines.length + trendlines.length + measures.length + rects.length})</span>}
            {drawMode && <span className="muted">&nbsp;&nbsp;{drawTool === "hline" ? "点击添加/移除水平价位线" : drawTool === "trend" ? "点击两点绘制趋势线" : drawTool === "rect" ? "点击两点框选区域(支撑/阻力带)" : "点击两点测距(Δ价/Δ%/根数)"}{pending && " (再点一点成线)"}</span>}
            {!showMA && !showBB && !showDC && !showMACD && !showStoch && !showRSI && !showMFI && !showCCI && !showADX && !showIchi && !showPSAR && !showST && !showSR && !showFib && !showFibExt && !showVP && !showVWAP && !showDiv && userLines.length === 0 && trendlines.length === 0 && measures.length === 0 && rects.length === 0 && <span>{heikin ? "平均K(Heikin-Ashi 平滑) · " : ""}纯 K 线 · 勾选上方指标叠加</span>}
            {heikin && <span style={{ color: "#ff9800" }}>&nbsp;&nbsp;●平均K(显示已平滑,指标仍按原始价)</span>}
          </div>
          {rangeStats && (
            <div className="stats" style={{ marginTop: 8 }}>
              <div className="stat"><div className="muted" style={{ fontSize: 11 }}>区间涨幅</div><div className={rangeStats.periodRet >= 0 ? "pos" : "neg"} style={{ fontSize: 15, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{(rangeStats.periodRet * 100).toFixed(2)}%</div></div>
              <div className="stat"><div className="muted" style={{ fontSize: 11 }}>年化波动</div><div style={{ fontSize: 15, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{(rangeStats.annVol * 100).toFixed(1)}%</div></div>
              <div className="stat"><div className="muted" style={{ fontSize: 11 }}>区间最高</div><div style={{ fontSize: 15, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>${rangeStats.high.toFixed(2)}</div></div>
              <div className="stat"><div className="muted" style={{ fontSize: 11 }}>区间最低</div><div style={{ fontSize: 15, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>${rangeStats.low.toFixed(2)}</div></div>
              <div className="stat"><div className="muted" style={{ fontSize: 11 }}>日均量</div><div style={{ fontSize: 15, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{(rangeStats.avgVol / 1e6).toFixed(2)}M</div></div>
              <div className="stat"><div className="muted" style={{ fontSize: 11 }}>窗口</div><div className="muted" style={{ fontSize: 15, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{rangeStats.n} 根</div></div>
            </div>
          )}
        </div>
      ) : (
        <div className="muted">该标的无历史数据（雅虎财经离线快照可能尚未覆盖）。</div>
      )}

      {showPos && (
        <div className="card">
          <h3>持仓模拟(做多) · <span className="muted">入场/止损/止盈价位线 + 风险回报</span></h3>
          <div className="params-row">
            <label>入场 <input type="number" value={posEntry} onChange={(e) => setPosEntry(e.target.value)} style={{ width: 80 }} /></label>
            <label>止损 <input type="number" value={posStop} onChange={(e) => setPosStop(e.target.value)} style={{ width: 80 }} /></label>
            <label>止盈 <input type="number" value={posTarget} onChange={(e) => setPosTarget(e.target.value)} style={{ width: 80 }} /></label>
            <label>股数 <input type="number" min={0} value={posQty} onChange={(e) => setPosQty(+e.target.value)} style={{ width: 70 }} /></label>
          </div>
          {posAtrVal != null && (
            <div className="params-row" style={{ marginTop: 6 }}>
              <span className="muted">ATR(14) <b data-pos-atr={posAtrVal} style={{ color: "#e0e6ed" }}>{posAtrVal.toFixed(2)}</b></span>
              <label>倍数 <input type="number" step="0.1" min={0.1} value={posAtrMult} onChange={(e) => setPosAtrMult(+e.target.value || 1.5)} style={{ width: 52 }} /></label>
              <button onClick={() => { const e = +posEntry; if (e > 0 && Number.isFinite(e)) setPosStop((e - posAtrMult * posAtrVal).toFixed(2)); }} title={`止损 = 入场 − ${posAtrMult}×ATR(波动止损)`}>用 {posAtrMult}×ATR 设止损</button>
              <label style={{ marginLeft: "auto" }}>风险$ <input type="number" min={0} value={posRisk} data-pos-risk onChange={(e) => setPosRisk(e.target.value)} style={{ width: 90 }} placeholder="按止损定仓" /></label>
              {sizing != null && sizing > 0 ? (
                <span>建议 <b data-pos-suggest={sizing} style={{ color: "#e0e6ed" }}>{sizing.toLocaleString()}</b> 股 <button onClick={() => setPosQty(sizing)}>应用</button></span>
              ) : <span className="muted">填风险$ → 按入场/止损算股数</span>}
            </div>
          )}
          {posCalc ? (
            <div className="stats" style={{ marginTop: 8 }}>
              <div className="stat"><div className="muted" style={{ fontSize: 11 }}>风险回报</div><div className={posCalc.rr >= 2 ? "pos" : posCalc.rr < 1 ? "neg" : ""} style={{ fontSize: 15, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{posCalc.rr != null ? posCalc.rr.toFixed(2) + "R" : "—"}</div></div>
              <div className="stat"><div className="muted" style={{ fontSize: 11 }}>止损亏损</div><div className="neg" style={{ fontSize: 15, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{(posCalc.lossPct * 100).toFixed(2)}% · ${posCalc.risk$.toFixed(0)}</div></div>
              <div className="stat"><div className="muted" style={{ fontSize: 11 }}>止盈盈利</div><div className="pos" style={{ fontSize: 15, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>+{(posCalc.gainPct * 100).toFixed(2)}% · ${posCalc.reward$.toFixed(0)}</div></div>
              <div className="stat"><div className="muted" style={{ fontSize: 11 }}>名义价值</div><div className="muted" style={{ fontSize: 15, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>${(posCalc.e * posCalc.q).toFixed(0)}</div></div>
            </div>
          ) : (
            <div className="muted" style={{ marginTop: 8 }}>输入入场/止损/止盈价位以计算风险回报。</div>
          )}
        </div>
      )}

      {rating && (
        <div className="card">
          <h3>技术信号雷达 · <span style={{ color: ratingColor(rating.score) }}>{ratingLabel(rating.score)}</span>
            <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}> · 综合 {rating.score.toFixed(2)} · 买 {rating.buy} / 中 {rating.neutral} / 卖 {rating.sell}</span>
          </h3>
          <div style={{ position: "relative", height: 12, borderRadius: 6, background: "linear-gradient(90deg,#ef5350,#6b4a55 45%,#4a5a66 55%,#26a69a)", marginTop: 4 }}>
            <div style={{ position: "absolute", left: `calc(${((rating.score + 1) / 2) * 100}% - 2px)`, top: -3, width: 4, height: 18, background: "#fff", borderRadius: 2, boxShadow: "0 0 4px rgba(0,0,0,0.7)" }} />
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
            {rating.votes.map((v, i) => (
              <span key={i} style={{ fontSize: 11, padding: "2px 8px", borderRadius: 10,
                background: v.vote > 0 ? "rgba(38,166,154,0.15)" : v.vote < 0 ? "rgba(239,83,80,0.15)" : "rgba(154,166,178,0.12)",
                color: v.vote > 0 ? "#26a69a" : v.vote < 0 ? "#ef5350" : "#9aa6b2",
                border: `1px solid ${v.vote > 0 ? "rgba(38,166,154,0.4)" : v.vote < 0 ? "rgba(239,83,80,0.4)" : "rgba(154,166,178,0.3)"}` }}>
                {v.label} {v.vote > 0 ? "▲" : v.vote < 0 ? "▼" : "–"}
              </span>
            ))}
          </div>
          <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>由 MA/EMA/MACD/RSI/KDJ 各投一票(±1/0)聚合;随回放重算。</div>
        </div>
      )}

      {showDiv && (
        <div className="card">
          <h3>背离检测 · <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>价格 ↔ {divOsc === "macd" ? "MACD柱" : "RSI(14)"} · 看涨 {divInfo.bull} / 看跌 {divInfo.bear}{divInfo.latest ? ` · 最近 ${new Date(divInfo.latest.bTime * 1000).toISOString().slice(0, 10)}` : ""}</span>
            <select value={divOsc} onChange={(e) => setDivOsc(e.target.value)} style={{ marginLeft: 8, maxWidth: 110 }}>
              <option value="rsi">RSI</option>
              <option value="macd">MACD柱</option>
            </select>
          </h3>
          {divInfo.events.length ? (
            <div className="scroll" style={{ maxHeight: 188, marginTop: 6 }}>
              <table className="data">
                <thead><tr><th>类型</th><th>确认日</th><th>价位 (前→后)</th><th>{divOsc === "macd" ? "MACD" : "RSI"} (前→后)</th></tr></thead>
                <tbody>
                  {[...divInfo.events].reverse().map((e, i) => (
                    <tr key={i}>
                      <td className={e.type === "bull" ? "pos" : "neg"}>{e.type === "bull" ? "看涨 ▲" : "看跌 ▼"}</td>
                      <td>{new Date(e.bTime * 1000).toISOString().slice(0, 10)}</td>
                      <td>${e.aPrice.toFixed(2)} → ${e.bPrice.toFixed(2)}</td>
                      <td>{e.aOsc.toFixed(1)} → {e.bOsc.toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="muted" style={{ marginTop: 8 }}>该标的在当前周期无明显常规背离(价格与{divOsc === "macd" ? "MACD柱" : "RSI"}同向)。</div>
          )}
          <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>看涨=价格更低的低点但震荡指标更高的低点(下行动能减弱);看跌反之。摇摆点以 5/5 根窗口判定,故最近 5 根不出信号;连线与箭头画在主图上,随回放重算。</div>
        </div>
      )}

      {showAlerts && (
        <div className="card">
          <h3>价格告警 · {symbol} <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>· 价位线虚线画在图上 · 收盘价穿越即标记已触发</span></h3>
          <div className="toolbar" style={{ flexWrap: "wrap", gap: 8, marginBottom: 8 }}>
            <input type="number" value={alertPrice} onChange={(e) => setAlertPrice(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") addAlert(); }}
              placeholder="价位" style={{ width: 96 }} />
            <select value={alertDir} onChange={(e) => setAlertDir(e.target.value)} style={{ maxWidth: 90 }}>
              <option value="up">上穿 ↑</option>
              <option value="down">下穿 ↓</option>
            </select>
            <button onClick={addAlert}>添加告警</button>
            {last && <button onClick={() => setAlertPrice(last.close.toFixed(2))} title="用最新收盘价填充">在最新价</button>}
            <span className="muted" style={{ fontSize: 12, marginLeft: "auto" }}>{alertRows.filter((a) => a.crossed).length}/{alertRows.length} 已触发</span>
          </div>
          {alertRows.length ? (
            <div className="scroll" style={{ maxHeight: 200 }}>
              <table className="data">
                <thead><tr><th>方向</th><th>价位</th><th>状态</th><th></th></tr></thead>
                <tbody>
                  {alertRows.map((a) => (
                    <tr key={a.id}>
                      <td className={a.dir === "up" ? "pos" : "neg"}>{a.dir === "up" ? "↑ 上穿" : "↓ 下穿"}</td>
                      <td>{a.price.toFixed(2)}</td>
                      <td className={a.crossed ? "pos" : "muted"}>{a.crossed ? `已触发 ${new Date(a.crossed * 1000).toISOString().slice(0, 10)}` : "监控中"}</td>
                      <td><button onClick={() => removeAlert(a.id)} style={{ padding: "0 6px" }}>×</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="muted">尚无告警。输入价位选方向后添加;虚线画在主图(绿=上穿/红=下穿),历史已收盘穿越即标记触发日期,随回放重算。</div>
          )}
        </div>
      )}

      {showCP && (
        <div className="card">
          <h3>蜡烛形态 · {symbol} <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>
            · <span className="pos">锤子 {cpInfo.hammer.length}</span> · <span className="neg">流星 {cpInfo.shootingStar.length}</span>
            · <span className="pos">看涨吞没 {cpInfo.bullEngulf.length}</span> · <span className="neg">看跌吞没 {cpInfo.bearEngulf.length}</span>
            · <span className="pos">三兵 {cpInfo.threeSoldiers.length}</span> · <span className="neg">三鸦 {cpInfo.threeCrows.length}</span>
            · <span style={{ color: "#4dd0e1" }}>光头光脚 {cpInfo.marubozu.length}</span> · <span className="muted">十字 {cpInfo.doji.length}</span>
          </span></h3>
          <div className="muted" style={{ fontSize: 12 }}>单/双/三根形态,客户端由 OHLC 算(Pine 风格本地计算)。锤子=长下影·小实体(看涨)、流星=长上影·小实体(看跌)、吞没=当前实体完全包住前一根(反向)、三兵/三鸦=三连阳/阴且每根开盘在前根实体内(强反转)、光头光脚(marubozu)=实体占满整根(强动量)、十字=开收几乎相等(犹豫)。箭头画在主图(绿▲=看涨/红▼=看跌/青·橙=动量/灰●=十字),随回放重算;形态密度反映震荡程度,需结合趋势/位置确认。</div>
        </div>
      )}

      {showPine && (
        <div className="card">
          <h3>自定义指标 · <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>Pine 风格表达式 · 本地编译成序列,画在独立子窗格,随回放重算</span></h3>
          <div className="toolbar" style={{ flexWrap: "wrap", gap: 8, marginBottom: 8, alignItems: "center" }}>
            <input value={pineExpr} onChange={(e) => setPineExpr(e.target.value)} spellCheck={false}
              placeholder="例: close - sma(close, 50)" style={{ flex: 1, minWidth: 220, fontFamily: "monospace" }} />
            {pineInfo && pineInfo.stats ? (
              <span className="muted" style={{ fontSize: 12, fontVariantNumeric: "tabular-nums" }}>
                有效 {pineInfo.stats.n} 点 · 最新 <b>{pineInfo.stats.last.toFixed(2)}</b> · 最低 {pineInfo.stats.min.toFixed(2)} / 最高 {pineInfo.stats.max.toFixed(2)}
              </span>
            ) : pineInfo && pineInfo.error ? (
              <span className="neg" style={{ fontSize: 12 }}>⚠ {pineInfo.error}</span>
            ) : null}
            {pineInfo && !pineInfo.error && (
              <label style={{ fontSize: 12, display: "inline-flex", alignItems: "center", gap: 4 }}>
                <input type="checkbox" checked={showPineCross} onChange={(e) => setShowPineCross(e.target.checked)} />
                标记过零 <span className="muted">(<span className="pos">↑{pineCrosses.filter((c) => c.dir > 0).length}</span>/<span className="neg">↓{pineCrosses.filter((c) => c.dir < 0).length}</span> 信号画在主图)</span>
              </label>
            )}
          </div>
          <div className="muted" style={{ fontSize: 12 }}>
            变量: <b>{PINE_VARS.join(" / ")}</b> · 函数: <b>{PINE_FUNCS.join(" / ")}</b> · 运算: + − * / ( ) 负号 · <b>序列[n]</b>(取 n 根前的值)。函数可<b>嵌套</b>(预热期自动跳过,内层 warmup 不再污染外层)。
            例:<code> close-close[5]</code>(=5 日动量)、<code> close[1]</code>(昨日收盘)、<code> ema(roc(close,12),9)</code>(变动率的平滑)、<code> sma(rsi(close,14),10)</code>(RSI 的平滑)、<code> ema(close,12)-ema(close,26)</code>(MACD 雏形)、<code> close-lowest(low,20)</code>(动量)、<code> roc(close,12)</code>(12 日变动率)、<code> change(close)</code>(逐根涨跌)、<code> hma(close,21)</code>(低滞后 Hull MA)、<code> obv-ema(obv,20)</code>(量能 OBV 动量)、<code> std(close,20)*2</code>(布林半宽)。
          </div>
        </div>
      )}

      {fund && (
        <div className="card">
          <h3>基本面 · {symbol} <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>· 截面 {snap.length} 只 · {meta?.name}</span></h3>
          <div className="stats" style={{ marginTop: 4 }}>
            {FUND_METRICS.map((m) => (
              <div className="stat" key={m.key}>
                <div className="muted" style={{ fontSize: 11 }}>{m.label}</div>
                <div style={{ fontSize: 15, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{fmtFund(fund[m.key].v, m.key)}</div>
              </div>
            ))}
          </div>
          <div className="muted" style={{ fontSize: 11, marginTop: 12, marginBottom: 6 }}>截面分位(在全市场中由低到高的位置,0%=最低)</div>
          {FUND_METRICS.map((m) => {
            const p = fund[m.key].pct;
            return (
              <div key={m.key} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <span style={{ width: 52, fontSize: 11 }} className="muted">{m.label}</span>
                <div style={{ position: "relative", flex: 1, height: 8, borderRadius: 4, background: "rgba(255,255,255,0.06)" }}>
                  {p != null && (
                    <div style={{ position: "absolute", left: 0, top: 0, height: 8, width: `${Math.max(2, p * 100)}%`, borderRadius: 4, background: "linear-gradient(90deg,#4f93e7,#64b5f6)" }} />
                  )}
                </div>
                <span style={{ width: 46, fontSize: 11, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{p != null ? Math.round(p * 100) + "%" : "—"}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
