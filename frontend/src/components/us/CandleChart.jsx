import { useEffect, useRef } from "react";
import {
  createChart,
  CandlestickSeries,
  BarSeries,
  LineSeries,
  AreaSeries,
  HistogramSeries,
  createSeriesMarkers,
  ColorType,
  CrosshairMode,
  LineStyle,
  PriceScaleMode,
} from "lightweight-charts";

// Fixed pixel height for each oscillator sub-pane; the price pane takes the rest.
const PANE_HEIGHT = 120;

const p2 = (x) => (x == null ? "—" : Number(x).toFixed(2));
// UTC time → "YYYY-MM-DD" (daily/weekly) or "YYYY-MM-DD HH:MM" (intraday).
const fmtTime = (t) => {
  const s = new Date(t * 1000).toISOString();
  return t % 86400 === 0 ? s.slice(0, 10) : s.slice(0, 16).replace("T", " ");
};
const fmtVol = (v) =>
  v == null ? "—" : v >= 1e9 ? (v / 1e9).toFixed(2) + "B" : v >= 1e6 ? (v / 1e6).toFixed(2) + "M" : v >= 1e3 ? (v / 1e3).toFixed(1) + "K" : String(v);

/**
 * Generic lightweight-charts v5 chart.
 *
 * - pane 0: main price series (candle/bar/line/area) + volume overlay + price-pane `overlays`
 * - panes 1..N: optional oscillator `panes` (e.g. MACD, Stoch, RSI)
 *
 * overlays: [{ color, lineWidth?, label?, dots?, points: [{time,value}] }]
 * panes:    [{ lines: [{ color, lineWidth?, label?, points }], hist?: { points },
 *             refs?: [{ price, color }] }]
 *
 * The main series is rebuilt whenever `chartType` changes (candle↔bar↔line↔area);
 * overlays/panes are torn down and rebuilt on any of their own changes, so toggles
 * are cheap and there is no stale-series bookkeeping. Overlays re-add after the
 * rebuilt main so moving-average lines always render on top of the price series.
 *
 * A top-left legend follows the crosshair, showing OHLC/volume + the value of
 * every active line (MA/BB/oscillator) at the hovered bar (or the last bar when
 * the cursor is off-chart) — the core TradingView price-legend affordance.
 */
export default function CandleChart({
  bars = [],
  patterns = [],
  overlays = [],
  panes = [],
  priceLines = [], // [{ price, color, lineWidth?, lineStyle?, title? }] on the main series
  showVolume = true,
  showVP = false, // volume profile: horizontal volume-by-price histogram over pane 0
  height = 460,
  title = "",
  chartType = "candle", // candle | bar | line | area
  logScale = false,
  magnet = false,
  range = null, // null = fit all, or N = show last N bars
  drawMode = false, // when true, a chart click reports the cursor {time, price} upward
  onChartClick, // ({ time, price }) => void — used by the drawing tools
  onReady, // (handle) => void — exposes { chart, getMain, getBars, renderLegendAt } once, for cross-chart linking
  measures = [], // [{ a:{time,price}, b:{time,price} }] — committed ruler measurements
  pendingMeasure = null, // { time, price } — first endpoint of an in-progress measurement (drives the live preview)
  rects = [], // [{ t1, p1, t2, p2 }] — committed highlight zones (support/resistance, supply/demand)
  pendingRect = null, // { time, price } — first corner of an in-progress rectangle (drives the live preview)
  divergence = [], // [{ type:"bull"|"bear", aTime, aPrice, bTime, bPrice }] — price↔oscillator divergence connectors
  showSessions = false, // draw vertical day-boundary separators on intraday charts
}) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const base = useRef({ main: null, volume: null, markers: null });
  const extras = useRef([]); // series created for overlays + panes, for clean teardown
  const priceLineHandles = useRef([]); // [{price,color,title,handle}] — diffed, not rebuilt wholesale
  const legendRef = useRef(null);
  const vpCanvasRef = useRef(null); // overlay canvas for the volume-profile histogram
  const measureCanvasRef = useRef(null); // overlay canvas for the ruler measurements
  const rectCanvasRef = useRef(null); // overlay canvas for highlight rectangles
  const divCanvasRef = useRef(null); // overlay canvas for divergence connectors
  const sessionCanvasRef = useRef(null); // overlay canvas for intraday day-boundary separators
  const cursorRef = useRef(null); // last crosshair { time, price, x, y } — drives the measure / rect preview
  // latest props mirrored into refs so the chartType effect can seed data/markers
  // without waiting for the [bars]/[patterns] effects to re-run.
  const barsRef = useRef(bars);
  barsRef.current = bars;
  const patternsRef = useRef(patterns);
  patternsRef.current = patterns;
  // legend lookup state, kept in a ref so the once-registered crosshair handler reads current data
  const stateRef = useRef({ barByTime: new Map(), lastBar: null, lines: [], title });
  // latest click callback in a ref so the draw effect need not re-subscribe each render
  const onChartClickRef = useRef(onChartClick);
  onChartClickRef.current = onChartClick;
  const onReadyRef = useRef(onReady);
  onReadyRef.current = onReady;

  const totalH = height + panes.length * PANE_HEIGHT;

  // legend renderer — reassigned every render so it always sees the latest props/refs
  const renderLegend = useRef(() => {});
  renderLegend.current = (time) => {
    const el = legendRef.current;
    const { barByTime, lastBar, lines, title: ttl } = stateRef.current;
    if (!el || !lastBar) return;
    const bar = (time != null && barByTime.get(time)) || lastBar;
    const up = bar.close >= bar.open;
    const col = up ? "#26a69a" : "#ef5350";
    const chg = bar.open ? bar.close / bar.open - 1 : 0;
    const chgCls = chg >= 0 ? "pos" : "neg";
    let h = `<div class="cl-title">${ttl ? ttl + " " : ""}<span class="cl-date">${fmtTime(bar.time)}</span></div>`;
    h += `<div class="cl-ohlcv">开 <b style="color:${col}">${p2(bar.open)}</b> 高 <b style="color:${col}">${p2(bar.high)}</b> 低 <b style="color:${col}">${p2(bar.low)}</b> 收 <b style="color:${col}">${p2(bar.close)}</b> <span class="${chgCls}">${(chg * 100).toFixed(2)}%</span> 量 ${fmtVol(bar.volume)}</div>`;
    for (const ln of lines) {
      const v = ln.byTime.get(bar.time);
      if (v == null) continue;
      h += `<span class="cl-line"><i style="background:${ln.color}"></i>${ln.label ? ln.label + " " : ""}<b>${p2(v)}</b></span>`;
    }
    el.innerHTML = h;
    el.style.display = "block";
  };

  // volume profile: bin the visible bars' volume by price, draw horizontal bars
  // on the overlay canvas. Bars are price-locked (mapped via the main series'
  // priceToCoordinate), so they track the scale on pan/zoom/log toggle — unlike
  // every other overlay here, which is time-anchored. Recomputed over the bars
  // currently in view (chart.timeScale().getVisibleRange()).
  const drawVP = useRef(() => {});
  drawVP.current = () => {
    const canvas = vpCanvasRef.current;
    const chart = chartRef.current;
    const main = base.current.main;
    const container = containerRef.current;
    if (!canvas || !chart || !main || !container) return;
    const dpr = window.devicePixelRatio || 1;
    const w = container.clientWidth, h = container.clientHeight;
    if (w === 0 || h === 0) return;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      canvas.style.width = w + "px"; canvas.style.height = h + "px";
    }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    if (!showVP) return;

    const vr = chart.timeScale().getVisibleRange(); // { from, to } UTC seconds
    let vis = barsRef.current;
    if (vr && vr.from != null && vr.to != null) {
      vis = barsRef.current.filter((b) => b.time >= vr.from && b.time <= vr.to);
    }
    if (!vis.length) return;

    const BINS = 24;
    let lo = Infinity, hi = -Infinity;
    for (const b of vis) { if (b.low < lo) lo = b.low; if (b.high > hi) hi = b.high; }
    if (!(hi > lo)) return;
    const span = hi - lo;
    const vol = new Array(BINS).fill(0);
    for (const b of vis) {
      const px = (b.high + b.low) / 2;
      let idx = Math.floor(((px - lo) / span) * BINS);
      if (idx < 0) idx = 0; else if (idx >= BINS) idx = BINS - 1;
      vol[idx] += b.volume || 0;
    }
    const maxVol = Math.max(...vol);
    if (!maxVol) return;

    // POC = the single price bin with the most volume. Value area = the price
    // range holding 70% of volume, found by expanding outward from the POC one
    // bin at a time, always taking the heavier of the two neighbours (TPO-style).
    const totalVol = vol.reduce((a, b) => a + b, 0);
    const target = 0.7 * totalVol;
    let poc = 0; for (let i = 1; i < BINS; i++) if (vol[i] > vol[poc]) poc = i;
    let vlo = poc, vhi = poc, vaVol = vol[poc];
    while (vaVol < target && (vlo > 0 || vhi < BINS - 1)) {
      const above = vhi < BINS - 1 ? vol[vhi + 1] : -1;
      const below = vlo > 0 ? vol[vlo - 1] : -1;
      if (above >= below) { vhi++; vaVol += vol[vhi]; } else { vlo--; vaVol += vol[vlo]; }
    }
    const VAH = lo + (span * (vhi + 1)) / BINS;
    const VAL = lo + (span * vlo) / BINS;
    const pocPrice = lo + (span * (poc + 0.5)) / BINS;

    // value-area band (faint, full width, behind the bars)
    const yVAH = main.priceToCoordinate(VAH);
    const yVAL = main.priceToCoordinate(VAL);
    if (yVAH != null && yVAL != null) {
      ctx.fillStyle = "rgba(100,181,246,0.08)";
      ctx.fillRect(0, Math.min(yVAH, yVAL), w, Math.abs(yVAL - yVAH));
    }

    const maxW = w * 0.22; // bars grow rightward from the left edge
    ctx.fillStyle = "rgba(100,181,246,0.30)";
    ctx.strokeStyle = "rgba(100,181,246,0.55)";
    ctx.lineWidth = 1;
    for (let i = 0; i < BINS; i++) {
      if (!vol[i]) continue;
      const priceLo = lo + (span * i) / BINS;
      const priceHi = lo + (span * (i + 1)) / BINS;
      const yHi = main.priceToCoordinate(priceHi); // higher price → smaller y
      const yLo = main.priceToCoordinate(priceLo);
      if (yHi == null || yLo == null) continue;
      const top = yHi;
      const bh = Math.max(1, yLo - yHi - 1);
      const bw = (vol[i] / maxVol) * maxW;
      ctx.fillRect(0, top, bw, bh);
      ctx.strokeRect(0.5, top + 0.5, bw, bh);
    }

    // POC line (bright amber, full width) — the fair-value magnet for the session
    const yPOC = main.priceToCoordinate(pocPrice);
    if (yPOC != null) {
      ctx.strokeStyle = "rgba(255,193,7,0.9)";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(0, yPOC);
      ctx.lineTo(w, yPOC);
      ctx.stroke();
    }
  };

  // ruler measurements: a committed two-point segment reads Δprice / Δ% / bar-count
  // between its endpoints, drawn on a dedicated always-on overlay canvas (independent
  // of the VP toggle). Endpoints are price+time-locked, so segments track pan/zoom; a
  // dashed live preview runs from the anchored first point to the current crosshair.
  const drawMeasure = useRef(() => {});
  drawMeasure.current = () => {
    const canvas = measureCanvasRef.current;
    const chart = chartRef.current;
    const main = base.current.main;
    const container = containerRef.current;
    if (!canvas || !chart || !main || !container) return;
    if (!measures.length && !pendingMeasure) { // nothing to draw — clear and bail
      const dpr0 = window.devicePixelRatio || 1;
      const ctx0 = canvas.getContext("2d");
      ctx0.setTransform(dpr0, 0, 0, dpr0, 0, 0);
      ctx0.clearRect(0, 0, canvas.width, canvas.height);
      return;
    }
    const dpr = window.devicePixelRatio || 1;
    const w = container.clientWidth, h = container.clientHeight;
    if (w === 0 || h === 0) return;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      canvas.style.width = w + "px"; canvas.style.height = h + "px";
    }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const ts = chart.timeScale();
    const barsBetween = (ta, tb) => {
      const lo = Math.min(ta, tb), hi = Math.max(ta, tb);
      return barsRef.current.filter((b) => b.time >= lo && b.time <= hi).length;
    };
    const drawOne = (a, b, preview) => {
      const xa = ts.timeToCoordinate(a.time);
      const xb = preview ? b.x : ts.timeToCoordinate(b.time);
      const ya = main.priceToCoordinate(a.price);
      const yb = main.priceToCoordinate(b.price);
      if (xa == null || xb == null || ya == null || yb == null) return;
      ctx.setLineDash(preview ? [5, 4] : []);
      ctx.strokeStyle = preview ? "rgba(255,193,7,0.55)" : "rgba(255,193,7,0.95)";
      ctx.lineWidth = 1.25;
      ctx.beginPath(); ctx.moveTo(xa, ya); ctx.lineTo(xb, yb); ctx.stroke();
      ctx.setLineDash([]);
      // endpoint dots
      ctx.fillStyle = "rgba(255,193,7,0.95)";
      for (const [px, py] of [[xa, ya], [xb, yb]]) { ctx.beginPath(); ctx.arc(px, py, 2.5, 0, Math.PI * 2); ctx.fill(); }
      if (preview) return; // no readout box while dragging
      const dp = b.price - a.price;
      const pct = a.price ? (dp / a.price) * 100 : 0;
      const n = barsBetween(a.time, b.time);
      const text = `${dp >= 0 ? "+" : ""}${dp.toFixed(2)}  ${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%  ${n}根`;
      ctx.font = "11px sans-serif";
      const tw = ctx.measureText(text).width;
      const lx = Math.min(xb + 8, w - tw - 10);
      const ly = Math.max(yb - 22, 2);
      ctx.fillStyle = "rgba(40,44,52,0.92)";
      ctx.strokeStyle = "rgba(255,193,7,0.6)";
      ctx.fillRect(lx - 4, ly - 2, tw + 8, 16);
      ctx.strokeRect(lx - 4, ly - 2, tw + 8, 16);
      ctx.fillStyle = dp >= 0 ? "#26a69a" : "#ef5350";
      ctx.textBaseline = "top"; ctx.textAlign = "left";
      ctx.fillText(text, lx, ly);
    };
    for (const m of measures) drawOne(m.a, m.b, false);
    if (pendingMeasure && cursorRef.current) drawOne(pendingMeasure, cursorRef.current, true);
  };

  // highlight rectangles (support/resistance or supply/demand zones): a committed
  // two-corner box on a dedicated always-on overlay canvas. Corners are price+time-
  // locked, so boxes track pan/zoom; a dashed live preview runs from the anchored
  // first corner to the current crosshair. Mirrors the measure overlay's lifecycle.
  const drawRects = useRef(() => {});
  drawRects.current = () => {
    const canvas = rectCanvasRef.current;
    const chart = chartRef.current;
    const main = base.current.main;
    const container = containerRef.current;
    if (!canvas || !chart || !main || !container) return;
    const dpr = window.devicePixelRatio || 1;
    const w = container.clientWidth, h = container.clientHeight;
    if (w === 0 || h === 0) return;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      canvas.style.width = w + "px"; canvas.style.height = h + "px";
    }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    if (!rects.length && !pendingRect) return;
    const ts = chart.timeScale();
    const drawOne = (a, b, preview) => {
      const xa = ts.timeToCoordinate(a.time);
      const xb = preview ? b.x : ts.timeToCoordinate(b.time);
      const ya = main.priceToCoordinate(a.price);
      const yb = preview ? b.y : main.priceToCoordinate(b.price);
      if (xa == null || xb == null || ya == null || yb == null) return;
      const left = Math.min(xa, xb), right = Math.max(xa, xb);
      const top = Math.min(ya, yb), bot = Math.max(ya, yb);
      const rw = Math.max(1, right - left), rh = Math.max(1, bot - top);
      ctx.setLineDash(preview ? [5, 4] : []);
      ctx.fillStyle = preview ? "rgba(139,92,246,0.08)" : "rgba(139,92,246,0.13)";
      ctx.strokeStyle = preview ? "rgba(139,92,246,0.5)" : "rgba(139,92,246,0.85)";
      ctx.lineWidth = 1.25;
      ctx.fillRect(left, top, rw, rh);
      ctx.strokeRect(left + 0.5, top + 0.5, rw, rh);
      ctx.setLineDash([]);
      if (!preview) {
        ctx.fillStyle = "rgba(139,92,246,0.95)";
        for (const [px, py] of [[xa, ya], [xb, yb]]) { ctx.beginPath(); ctx.arc(px, py, 2.5, 0, Math.PI * 2); ctx.fill(); }
      }
    };
    for (const r of rects) drawOne({ time: r.t1, price: r.p1 }, { time: r.t2, price: r.p2 }, false);
    if (pendingRect && cursorRef.current) drawOne(pendingRect, cursorRef.current, true);
  };

  // divergence connectors: a committed two-point segment joining the two price
  // swings of each divergence event (green = bullish / bottom, red = bearish /
  // top), on a dedicated always-on overlay canvas above the rectangles. Both
  // endpoints are price+time-locked, so segments track pan/zoom/log toggle.
  const drawDiv = useRef(() => {});
  drawDiv.current = () => {
    const canvas = divCanvasRef.current;
    const chart = chartRef.current;
    const main = base.current.main;
    const container = containerRef.current;
    if (!canvas || !chart || !main || !container) return;
    const dpr = window.devicePixelRatio || 1;
    const w = container.clientWidth, h = container.clientHeight;
    if (w === 0 || h === 0) return;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      canvas.style.width = w + "px"; canvas.style.height = h + "px";
    }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    if (!divergence.length) return;
    const ts = chart.timeScale();
    for (const e of divergence) {
      const xa = ts.timeToCoordinate(e.aTime);
      const xb = ts.timeToCoordinate(e.bTime);
      const ya = main.priceToCoordinate(e.aPrice);
      const yb = main.priceToCoordinate(e.bPrice);
      if (xa == null || xb == null || ya == null || yb == null) continue;
      const bull = e.type === "bull";
      ctx.strokeStyle = bull ? "rgba(38,166,154,0.9)" : "rgba(239,83,80,0.9)";
      ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(xa, ya); ctx.lineTo(xb, yb); ctx.stroke();
      ctx.fillStyle = bull ? "rgba(38,166,154,0.95)" : "rgba(239,83,80,0.95)";
      for (const [px, py] of [[xa, ya], [xb, yb]]) { ctx.beginPath(); ctx.arc(px, py, 3, 0, Math.PI * 2); ctx.fill(); }
    }
  };

  // intraday session separators: a faint dashed vertical line at the first bar of
  // each new trading day, so consecutive sessions don't visually blend on 60/15/5-min
  // charts. No-op on daily/weekly (one bar per day → a line per bar would be noise,
  // detected via distinct-days ≈ bar count). Time-anchored → tracks pan/zoom.
  const drawSession = useRef(() => {});
  drawSession.current = () => {
    const canvas = sessionCanvasRef.current;
    const chart = chartRef.current;
    const container = containerRef.current;
    if (!canvas || !chart || !container) return;
    const dpr = window.devicePixelRatio || 1;
    const w = container.clientWidth, h = container.clientHeight;
    if (w === 0 || h === 0) return;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      canvas.style.width = w + "px"; canvas.style.height = h + "px";
    }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    if (!showSessions) return;
    const bs = barsRef.current;
    if (bs.length < 2) return;
    const dayOf = (t) => new Date(t * 1000).toISOString().slice(0, 10);
    const days = new Set(bs.map((b) => dayOf(b.time)));
    if (days.size >= bs.length) return; // daily/weekly: skip (would draw a line per bar)
    const ts = chart.timeScale();
    ctx.strokeStyle = "rgba(255,255,255,0.10)";
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 3]);
    let prevDay = dayOf(bs[0].time);
    for (let i = 1; i < bs.length; i++) {
      const d = dayOf(bs[i].time);
      if (d !== prevDay) {
        const x = ts.timeToCoordinate(bs[i].time);
        if (x != null) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke(); }
        prevDay = d;
      }
    }
    ctx.setLineDash([]);
  };

  // create chart + volume once (the main price series is created in the [chartType] effect)
  useEffect(() => {
    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#9aa6b2",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.04)" },
        horzLines: { color: "rgba(255,255,255,0.04)" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.1)" },
      timeScale: { borderColor: "rgba(255,255,255,0.1)", timeVisible: true, secondsVisible: false },
    });
    chartRef.current = chart;

    // expose a stable handle for cross-chart linking (e.g. synced crosshairs on
    // the multi-timeframe page). The getters read live refs, so a caller that
    // subscribes once always sees the current main series / bars after rebuilds.
    if (onReadyRef.current) {
      onReadyRef.current({
        chart,
        getMain: () => base.current.main,
        getBars: () => barsRef.current,
        renderLegendAt: (time) => renderLegend.current(time),
      });
    }

    base.current.volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" }, priceScaleId: "",
    });
    base.current.volume.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    base.current.volume.applyOptions({ visible: showVolume });

    const onMove = (param) => {
      renderLegend.current(param.time);
      drawVP.current();
      // track the cursor (price at its Y) so the measure preview can follow it
      const py = param?.point?.y;
      if (py != null && base.current.main) {
        cursorRef.current = { time: param?.time ?? null, price: base.current.main.coordinateToPrice(py), x: param.point.x, y: py };
      } else cursorRef.current = null;
      drawMeasure.current();
      drawRects.current();
      drawDiv.current();
      drawSession.current();
    };
    chart.subscribeCrosshairMove(onMove);

    // redraw the volume profile + measurements + rectangles + divergence whenever the
    // visible range changes (pan/zoom); rAF-throttled because the event fires per animation frame during a drag.
    let raf = 0;
    const onRange = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(() => { drawVP.current(); drawMeasure.current(); drawRects.current(); drawDiv.current(); drawSession.current(); }); };
    chart.timeScale().subscribeVisibleLogicalRangeChange(onRange);

    return () => {
      cancelAnimationFrame(raf);
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(onRange);
      chart.unsubscribeCrosshairMove(onMove);
      chart.remove();
      chartRef.current = null;
      base.current = { main: null, volume: null, markers: null };
      extras.current = [];
    };
  }, []);

  // main price series — rebuilt whenever chartType changes.
  // declared BEFORE the overlays effect and that effect lists chartType in its
  // deps, so on a type switch overlays re-add after the rebuilt main (on top).
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    // teardown previous main series + its markers
    if (base.current.markers) { try { base.current.markers.detach(); } catch (_) { /* already gone */ } base.current.markers = null; }
    if (base.current.main) { try { chart.removeSeries(base.current.main); } catch (_) { /* already gone */ } base.current.main = null; }

    const data = barsRef.current;
    const ohlc = data.map((b) => ({ time: b.time, open: b.open, high: b.high, low: b.low, close: b.close }));
    const line = data.map((b) => ({ time: b.time, value: b.close }));

    let series;
    if (chartType === "line") {
      series = chart.addSeries(LineSeries, { color: "#4f93e7", lineWidth: 2 });
      series.setData(line);
    } else if (chartType === "area") {
      series = chart.addSeries(AreaSeries, {
        lineColor: "#4f93e7", lineWidth: 2,
        topColor: "rgba(79,147,231,0.40)", bottomColor: "rgba(79,147,231,0.02)",
      });
      series.setData(line);
    } else if (chartType === "bar") {
      series = chart.addSeries(BarSeries, { upColor: "#26a69a", downColor: "#ef5350", thinBars: false });
      series.setData(ohlc);
    } else {
      series = chart.addSeries(CandlestickSeries, {
        upColor: "#26a69a", downColor: "#ef5350", borderVisible: false,
        wickUpColor: "#26a69a", wickDownColor: "#ef5350",
      });
      series.setData(ohlc);
    }
    base.current.main = series;
    // the rebuilt series is a fresh object; any price-line handles we hold point
    // at the removed one. Drop them so the price-line effect recreates the lines
    // on the new series instead of diffing against dead handles (matters under
    // React.StrictMode's mount→cleanup→mount, and on a real chartType switch).
    priceLineHandles.current = [];
    base.current.markers = createSeriesMarkers(series, patternsRef.current);
    renderLegend.current();
  }, [chartType]);

  // horizontal price lines on the main series (support/resistance, hand-drawn).
  // Diffed against the previous set so a single add/remove touches one line, not
  // all of them — cheaper redraws and no wholesale teardown. chartType is a dep
  // because a series rebuild discards every price line it owned.
  useEffect(() => {
    const main = base.current.main;
    if (!main) return;
    const prev = priceLineHandles.current;
    const used = new Array(prev.length).fill(false);
    const keyOf = (p) => `${p.price}|${p.color}|${p.title || ""}`;
    const next = [];
    for (const pl of priceLines) {
      const key = keyOf(pl);
      const idx = prev.findIndex((p, i) => !used[i] && keyOf(p) === key);
      if (idx >= 0) { used[idx] = true; next.push(prev[idx]); }
      else {
        const handle = main.createPriceLine({
          price: pl.price, color: pl.color, lineWidth: pl.lineWidth || 1,
          lineStyle: pl.lineStyle || LineStyle.Dashed, axisLabelVisible: true, title: pl.title || "",
        });
        next.push({ price: pl.price, color: pl.color, title: pl.title || "", handle });
      }
    }
    for (let i = 0; i < prev.length; i++) {
      if (!used[i]) { try { main.removePriceLine(prev[i].handle); } catch (_) { /* line already gone */ } }
    }
    priceLineHandles.current = next;
  }, [priceLines, chartType]);

  // click-to-draw: in draw mode a chart click converts the cursor's Y to a price
  // and reports it up, so the parent can add/remove a horizontal price line there.
  useEffect(() => {
    const chart = chartRef.current;
    const container = containerRef.current;
    if (!chart || !container) return;
    if (!drawMode) { container.style.cursor = ""; return; }
    container.style.cursor = "crosshair";
    const onClick = (param) => {
      const y = param?.point?.y;
      if (y == null) return;
      const price = base.current.main?.coordinateToPrice(y);
      if (price != null && onChartClickRef.current) onChartClickRef.current({ time: param?.time ?? null, price });
    };
    chart.subscribeClick(onClick);
    return () => {
      try { chart.unsubscribeClick(onClick); } catch (_) { /* already gone */ }
      container.style.cursor = "";
    };
  }, [drawMode]);

  // candle + volume data + legend bar lookup
  useEffect(() => {
    const main = base.current.main;
    const volume = base.current.volume;
    if (!main) return;
    if (chartType === "line" || chartType === "area") {
      main.setData(bars.map((b) => ({ time: b.time, value: b.close })));
    } else {
      main.setData(bars.map((b) => ({ time: b.time, open: b.open, high: b.high, low: b.low, close: b.close })));
    }
    volume.setData(
      bars.map((b) => ({
        time: b.time,
        value: b.volume,
        color: b.close >= b.open ? "rgba(38,166,154,0.5)" : "rgba(239,83,80,0.5)",
      }))
    );
    if (bars.length) {
      const m = new Map();
      for (const b of bars) m.set(b.time, b);
      stateRef.current.barByTime = m;
      stateRef.current.lastBar = bars[bars.length - 1];
    } else {
      stateRef.current.barByTime = new Map();
      stateRef.current.lastBar = null;
    }
    renderLegend.current();
  }, [bars, chartType]);

  // volume visibility
  useEffect(() => {
    if (base.current.volume) base.current.volume.applyOptions({ visible: showVolume });
  }, [showVolume]);

  // price scale: arithmetic vs logarithmic
  useEffect(() => {
    if (chartRef.current) chartRef.current.applyOptions({
      rightPriceScale: { mode: logScale ? PriceScaleMode.Logarithmic : PriceScaleMode.Normal },
    });
  }, [logScale]);

  // crosshair: normal vs magnet (snaps to nearest OHLC)
  useEffect(() => {
    if (chartRef.current) chartRef.current.applyOptions({ crosshair: { mode: magnet ? CrosshairMode.Magnet : CrosshairMode.Normal } });
  }, [magnet]);

  // visible range: last N bars, or fit all when range is null
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const ts = chart.timeScale();
    if (range == null || !bars.length) { ts.fitContent(); return; }
    const n = bars.length;
    ts.setVisibleLogicalRange({ from: Math.max(0, n - 1 - range), to: n - 1 });
  }, [range, bars]);

  // volume-profile overlay: redraw on resize, and on toggle / main-series rebuild
  // (a chartType switch replaces the series that priceToCoordinate maps through).
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    drawVP.current();
    const ro = new ResizeObserver(() => drawVP.current());
    ro.observe(container);
    return () => ro.disconnect();
  }, []);
  useEffect(() => { requestAnimationFrame(() => drawVP.current()); }, [showVP, chartType]);

  // measurement overlay: redraw on resize, and whenever the committed measures, the
  // pending endpoint, or the main series (chartType rebuild) change.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    drawMeasure.current();
    const ro = new ResizeObserver(() => drawMeasure.current());
    ro.observe(container);
    return () => ro.disconnect();
  }, []);
  useEffect(() => { requestAnimationFrame(() => drawMeasure.current()); }, [measures, pendingMeasure, chartType]);

  // rectangle overlay: redraw on resize, and whenever the committed rects, the pending
  // corner, or the main series (chartType rebuild) change.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    drawRects.current();
    const ro = new ResizeObserver(() => drawRects.current());
    ro.observe(container);
    return () => ro.disconnect();
  }, []);
  useEffect(() => { requestAnimationFrame(() => drawRects.current()); }, [rects, pendingRect, chartType]);

  // divergence overlay: redraw on resize, and whenever the events or the main
  // series (chartType rebuild) change.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    drawDiv.current();
    const ro = new ResizeObserver(() => drawDiv.current());
    ro.observe(container);
    return () => ro.disconnect();
  }, []);
  useEffect(() => { requestAnimationFrame(() => drawDiv.current()); }, [divergence, chartType]);

  // session-separator overlay: redraw on resize, and whenever the bars, the toggle,
  // or the main series (chartType rebuild) change.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    drawSession.current();
    const ro = new ResizeObserver(() => drawSession.current());
    ro.observe(container);
    return () => ro.disconnect();
  }, []);
  useEffect(() => { requestAnimationFrame(() => drawSession.current()); }, [showSessions, chartType, bars]);

  // overlays (price pane) + oscillator panes — rebuild on any change.
  // chartType is a dep so overlays re-add after the rebuilt main series (correct z-order).
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    for (const s of extras.current) { try { chart.removeSeries(s); } catch (_) { /* already gone */ } }
    extras.current = [];

    const lines = []; // { color, label, byTime } — surfaced in the legend

    for (const ov of overlays) {
      const line = chart.addSeries(LineSeries, {
        color: ov.color, lineWidth: ov.lineWidth || 1,
        lineVisible: ov.dots ? false : true,          // dots overlay: points only, no connecting line
        pointMarkersVisible: !!ov.dots,
        priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
      }, 0);
      line.setData(ov.points || []);
      extras.current.push(line);
      const byTime = new Map();
      for (const p of (ov.points || [])) byTime.set(p.time, p.value);
      lines.push({ color: ov.color, label: ov.label || "", byTime });
    }

    panes.forEach((pane, j) => {
      const paneIndex = j + 1;
      let first = null;
      for (const ln of pane.lines || []) {
        const line = chart.addSeries(LineSeries, {
          color: ln.color, lineWidth: ln.lineWidth || 1,
          priceLineVisible: false, lastValueVisible: false,
        }, paneIndex);
        line.setData(ln.points || []);
        extras.current.push(line);
        if (!first) first = line;
        const byTime = new Map();
        for (const p of (ln.points || [])) byTime.set(p.time, p.value);
        lines.push({ color: ln.color, label: ln.label || "", byTime });
      }
      if (pane.hist) {
        const h = chart.addSeries(HistogramSeries, {
          priceFormat: { type: "price" }, priceLineVisible: false, lastValueVisible: false,
        }, paneIndex);
        h.setData(pane.hist.points || []);
        extras.current.push(h);
        if (!first) first = h;
      }
      if (first && pane.refs) {
        for (const r of pane.refs) {
          first.createPriceLine({ price: r.price, color: r.color, lineWidth: 1, lineStyle: LineStyle.Dashed });
        }
      }
      try { chart.panes()[paneIndex].setHeight(PANE_HEIGHT); } catch (_) { /* pane not present yet */ }
    });

    stateRef.current.lines = lines;
    renderLegend.current();
  }, [overlays, panes, chartType]);

  // keep title current for the legend
  useEffect(() => { stateRef.current.title = title; renderLegend.current(); }, [title]);

  // pattern markers — attach to the active main series
  useEffect(() => {
    const main = base.current.main;
    if (!main) return;
    if (!base.current.markers) base.current.markers = createSeriesMarkers(main, []);
    base.current.markers.setMarkers(patterns);
  }, [patterns]);

  return (
    <div className="chart-box">
      <div ref={containerRef} style={{ height: totalH, width: "100%" }} />
      <canvas
        ref={sessionCanvasRef}
        className="session-overlay"
        style={{ position: "absolute", left: 0, top: 0, width: "100%", height: totalH, pointerEvents: "none" }}
      />
      <canvas
        ref={vpCanvasRef}
        className="vp-overlay"
        style={{ position: "absolute", left: 0, top: 0, width: "100%", height: totalH, pointerEvents: "none" }}
      />
      <canvas
        ref={measureCanvasRef}
        className="measure-overlay"
        style={{ position: "absolute", left: 0, top: 0, width: "100%", height: totalH, pointerEvents: "none" }}
      />
      <canvas
        ref={rectCanvasRef}
        className="rect-overlay"
        style={{ position: "absolute", left: 0, top: 0, width: "100%", height: totalH, pointerEvents: "none" }}
      />
      <canvas
        ref={divCanvasRef}
        className="div-overlay"
        style={{ position: "absolute", left: 0, top: 0, width: "100%", height: totalH, pointerEvents: "none" }}
      />
      <div className="chart-legend" ref={legendRef} style={{ display: "none" }} />
    </div>
  );
}
