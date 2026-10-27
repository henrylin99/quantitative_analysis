// 美股市场热力图 —— squarified treemap 全市场
// 市值块 + 多配色模式（涨跌/成交量/市值/ROE/股息/综合评分），附市场宽度与收益分布卡。
// 数据源为本项目 /api/us-stock 快照截面（pct_change/roe 为小数，dividend_yield 为百分数）。
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchUsSnapshotRows } from "../../api/usTerminal";
import { treemap } from "../../lib/us/treemap.js";
import { breadth } from "../../lib/us/breadth.js";
import { distribution } from "../../lib/us/dist.js";
import "./us-tv.css";

// color metric for the tiles. Block SIZE is always market_cap (or |pct|); COLOR is
// the selected metric, so the same treemap doubles as a multi-factor market map.
const COLOR_MODES = [
  { key: "pct", label: "涨跌" },
  { key: "score", label: "评分" },
  { key: "vol", label: "成交量" },
  { key: "cap", label: "市值" },
  { key: "roe", label: "ROE" },
  { key: "div", label: "股息" },
];

const DIM = [30, 36, 41];
const mix = (a, b, k) => a.map((c, i) => Math.round(c + (b[i] - c) * Math.max(0, Math.min(1, k))));
const rgb = (c) => `rgb(${c[0]},${c[1]},${c[2]})`;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// diverging teal↔dim↔red around a centre (used by pct around 0 and ROE around 0)
const diverging = (t) => (t >= 0 ? rgb(mix(DIM, [38, 166, 154], t)) : rgb(mix(DIM, [239, 83, 80], -t)));
// sequential dim↔blue for log-distributed magnitudes (volume, market cap)
const sequential = (t) => rgb(mix(DIM, [79, 147, 231], t));

const fmtPct = (v) => (v == null || Number.isNaN(v) ? "—" : (v >= 0 ? "+" : "") + v.toFixed(2) + "%");
const fmtCompact = (v) => {
  if (v == null || Number.isNaN(v)) return "—";
  const a = Math.abs(v);
  if (a >= 1e12) return (v / 1e12).toFixed(2) + "T";
  if (a >= 1e9) return (v / 1e9).toFixed(2) + "B";
  if (a >= 1e6) return (v / 1e6).toFixed(1) + "M";
  return String(Math.round(v));
};

export default function UsHeatmapPage() {
  const navigate = useNavigate();
  const wrapRef = useRef(null);
  const [rows, setRows] = useState([]);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [sortBy, setSortBy] = useState("cap"); // cap | pct — controls block SIZE
  const [colorBy, setColorBy] = useState("pct"); // pct | score | vol | cap | roe | div
  const [q, setQ] = useState("");

  useEffect(() => { fetchUsSnapshotRows().then(setRows).catch(() => {}); }, []);

  // measure container
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0].contentRect;
      setSize({ w: r.width, h: Math.max(420, r.width * 0.58) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const items = useMemo(() => {
    let r = rows.filter((x) => x.market_cap && x.market_cap > 0);
    if (q.trim()) {
      const s = q.toUpperCase();
      r = r.filter((x) => x.symbol.includes(s) || (x.name || "").toUpperCase().includes(s));
    }
    const value = sortBy === "cap" ? (x) => x.market_cap : (x) => Math.abs(x.pct_change || 0) + 1;
    // pct_change is a decimal fraction in the data -> show as a percent number
    return r.map((x) => ({ ...x, value: value(x), pct: (x.pct_change || 0) * 100 }));
  }, [rows, sortBy, q]);

  // log-range maxima for the sequential (vol/cap) color modes
  const maxLog = useMemo(() => {
    const m = (key) => Math.log10(Math.max(1, ...items.map((x) => x[key] || 0)));
    return { vol: m("volume"), cap: m("market_cap") };
  }, [items]);

  // color + secondary label for a tile under the active mode
  const styleOf = useMemo(() => {
    const fns = {
      pct: (r) => diverging(clamp(r.pct / 6, -1, 1)),
      // 综合评分 (signal_score, 0–100)：越高越强 → 蓝色渐进
      score: (r) => (r.signal_score == null ? rgb(DIM) : sequential(clamp(r.signal_score / 100, 0, 1))),
      vol: (r) => sequential(r.volume > 0 ? Math.log10(r.volume) / maxLog.vol : 0),
      cap: (r) => sequential(r.market_cap > 0 ? Math.log10(r.market_cap) / maxLog.cap : 0),
      // ROE: decimal fraction in the data → diverging around 0 (negative ROE =
      // value destruction → red, ≥40% → teal). dividend_yield is already a percent
      // number → sequential blue ramp to ≥5%.
      roe: (r) => (r.roe == null ? rgb(DIM) : diverging(clamp(r.roe / 0.4, -1, 1))),
      div: (r) => (r.dividend_yield == null ? rgb(DIM) : sequential(clamp(r.dividend_yield / 5, 0, 1))),
    };
    const labels = {
      pct: (r) => fmtPct(r.pct),
      score: (r) => (r.signal_score == null ? "—" : r.signal_score.toFixed(0)),
      vol: (r) => fmtCompact(r.volume),
      cap: (r) => fmtCompact(r.market_cap),
      roe: (r) => (r.roe == null ? "—" : (r.roe * 100).toFixed(0) + "%"),
      div: (r) => (r.dividend_yield == null ? "—" : r.dividend_yield.toFixed(1) + "%"),
    };
    return { color: fns[colorBy], label: labels[colorBy] };
  }, [colorBy, maxLog]);

  const rects = useMemo(
    () => treemap(items, 0, 0, size.w, size.h),
    [items, size]
  );

  const stats = useMemo(() => {
    if (!rows.length) return null;
    const adv = rows.filter((r) => (r.pct_change || 0) > 0).length;
    const dec = rows.filter((r) => (r.pct_change || 0) < 0).length;
    const avg = (rows.reduce((s, r) => s + (r.pct_change || 0), 0) / rows.length) * 100;
    return { adv, dec, avg };
  }, [rows]);

  // whole-market breadth: advance/decline, up/down volume, participation thrust.
  const b = useMemo(() => breadth(rows), [rows]);

  // today's return distribution: fixed 1%-wide buckets + shape moments. The
  // breadth card counts up vs down; this shows the SHAPE — how dispersed today's
  // moves are, whether a few big winners/losers skew it, and if tails are fat.
  const dist = useMemo(() => distribution(rows.map((r) => (r.pct_change || 0) * 100)), [rows]);
  const skewLabel = dist.n ? (dist.skew > 0.3 ? "右偏" : dist.skew < -0.3 ? "左偏" : "近对称") : "";
  const kurtLabel = dist.n ? (dist.kurt > 1 ? "厚尾" : dist.kurt < -0.5 ? "薄尾" : "近正态") : "";
  const peak = dist.n ? dist.bins.reduce((a, x) => (x.count > a.count ? x : a), dist.bins[0]) : null;
  const peakLabel = peak ? (Number.isFinite(peak.lo) && Number.isFinite(peak.hi) ? `${peak.lo}~${peak.hi}%` : Number.isFinite(peak.lo) ? `≥${peak.lo}%` : `<${peak.hi}%`) : "";
  const binXLabel = (bin) => (bin.lo === -Infinity ? "<" + bin.hi : bin.hi === Infinity ? bin.lo + "+" : String(bin.lo));
  const shapeNote = dist.n
    ? `今日 ${dist.n} 只个股涨跌标准差 ${dist.std.toFixed(2)}%,${dist.std > 3 ? "个股分化较大" : "涨跌较集中"};分布${skewLabel}${dist.kurt > 1 ? "、尾部偏厚(极端涨跌多于常态)" : dist.kurt < -0.5 ? "、尾部偏薄" : ""},峰集中在 ${peakLabel}。`
    : "";

  // mode-aware legend: diverging (pct/roe) gets red↔teal, sequential (vol/cap/score) a blue ramp
  const legend = useMemo(() => {
    if (colorBy === "score") return { left: "0 弱", right: "100 强", grad: "linear-gradient(90deg,#1e2428,#4f93e7)" };
    if (colorBy === "vol") return { left: "低", right: "高", grad: "linear-gradient(90deg,#1e2428,#4f93e7)" };
    if (colorBy === "cap") return { left: "小", right: "大", grad: "linear-gradient(90deg,#1e2428,#4f93e7)" };
    if (colorBy === "roe") return { left: "<0 亏损", right: "≥40% 高回报", grad: "linear-gradient(90deg,#ef5350,#1e2428,#26a69a)" };
    if (colorBy === "div") return { left: "0%", right: "≥5% 高息", grad: "linear-gradient(90deg,#1e2428,#4f93e7)" };
    return { left: "-6%", right: "+6%", grad: "linear-gradient(90deg,#ef5350,#1e2428,#26a69a)" };
  }, [colorBy]);

  return (
    <div className="us-tv">
      <div className="toolbar">
        <input placeholder="搜索代码/名称…" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="group">
          <button className={sortBy === "cap" ? "active" : ""} onClick={() => setSortBy("cap")}>按市值</button>
          <button className={sortBy === "pct" ? "active" : ""} onClick={() => setSortBy("pct")}>按涨跌幅</button>
        </div>
        <span className="muted">配色</span>
        <div className="group">
          {COLOR_MODES.map((m) => (
            <button key={m.key} className={colorBy === m.key ? "active" : ""} onClick={() => setColorBy(m.key)}>{m.label}</button>
          ))}
        </div>
        {stats && (
          <span className="muted" style={{ marginLeft: "auto" }}>
            全市场 <span className="pos">↑{stats.adv}</span> · <span className="neg">↓{stats.dec}</span> · 均值 <b className={stats.avg >= 0 ? "pos" : "neg"}>{fmtPct(stats.avg)}</b>
          </span>
        )}
      </div>

      <div className="card" style={{ padding: 10 }}>
        <div ref={wrapRef} style={{ position: "relative", width: "100%", height: size.h || 480 }}>
          {rects.map((r) => {
            const area = r.width * r.height;
            const big = area > 7000;
            return (
              <div
                key={r.symbol}
                className="heat-tile"
                style={{ left: r.x, top: r.y, width: r.width, height: r.height, background: styleOf.color(r) }}
                onClick={() => navigate(`/us/${r.symbol}`)}
                title={`${r.symbol} ${r.name || ""}\n涨跌 ${fmtPct(r.pct)} · 量 ${fmtCompact(r.volume)} · 市值 $${fmtCompact(r.market_cap)}`}
              >
                {big && <span className="sym">{r.symbol}</span>}
                {big && <span className="pct">{styleOf.label(r)}</span>}
              </div>
            );
          })}
          {!rects.length && <div className="spinner">…</div>}
        </div>

        <div className="heatmap-legend">
          <span className="muted">{legend.left}</span>
          <span style={{ width: 130, height: 10, background: legend.grad, borderRadius: 3, display: "inline-block", verticalAlign: "middle", margin: "0 8px" }} />
          <span className="muted">{legend.right}</span>
          <span className="muted" style={{ marginLeft: 12 }}>块大小 = {sortBy === "cap" ? "市值" : "|涨跌|"} · 颜色 = {COLOR_MODES.find((m) => m.key === colorBy)?.label} · 点击进个股详情</span>
        </div>
      </div>

      {b && (
        <div className="card" style={{ padding: 14, marginTop: 12 }}>
          <h3 style={{ margin: "0 0 12px", fontSize: 14 }}>
            市场宽度 <span className="muted">Advance/Decline · 上涨/下跌成交量 · 宽度信号(参与度≥70% 且 成交量确认)</span>
          </h3>

          {/* advance/decline stacked bar */}
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
            <div style={{ flex: 1, height: 16, borderRadius: 4, overflow: "hidden", display: "flex", background: "#1e2429" }}>
              <span style={{ width: `${b.advPct * 100}%`, background: "#26a69a" }} />
              <span style={{ width: `${(1 - b.advPct - b.decPct) * 100}%`, background: "#4a525a" }} />
              <span style={{ width: `${b.decPct * 100}%`, background: "#ef5350" }} />
            </div>
            <span className="muted">涨跌比 <b style={{ color: "#e0e6ed" }} data-bread-adr={b.adRatio === Infinity ? "inf" : b.adRatio.toFixed(2)}>{b.adRatio === Infinity ? "∞" : b.adRatio.toFixed(2)} : 1</b></span>
          </div>
          <div style={{ display: "flex", gap: 22, flexWrap: "wrap", fontSize: 13, marginBottom: 14 }}>
            <span data-bread-adv={b.advancing}><span className="pos">▲ {b.advancing}</span> ({(b.advPct * 100).toFixed(0)}%)</span>
            <span data-bread-dec={b.declining}><span className="neg">▼ {b.declining}</span> ({(b.decPct * 100).toFixed(0)}%)</span>
            <span className="muted">平盘 {b.unchanged}</span>
            <span className="muted">均值 <b style={{ color: b.meanPct >= 0 ? "#26a69a" : "#ef5350" }}>{fmtPct(b.meanPct)}</b></span>
            <span className="muted">中位 <b style={{ color: b.medianPct >= 0 ? "#26a69a" : "#ef5350" }}>{fmtPct(b.medianPct)}</b></span>
          </div>

          {/* up/down volume bar */}
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
            <span className="muted" style={{ width: 76 }}>上涨成交量</span>
            <div style={{ flex: 1, height: 12, borderRadius: 4, overflow: "hidden", display: "flex", background: "#1e2429" }}>
              <span style={{ width: `${b.upVolPct * 100}%`, background: "#26a69a" }} />
              <span style={{ width: `${(1 - b.upVolPct) * 100}%`, background: "#ef5350" }} />
            </div>
            <b className="pos" data-bread-upvol={(b.upVolPct * 100).toFixed(0)}>{(b.upVolPct * 100).toFixed(0)}%</b>
          </div>

          <div style={{ display: "flex", gap: 18, alignItems: "center", flexWrap: "wrap", fontSize: 13 }}>
            <span>宽度信号 <b className={b.signal === "bull" ? "pos" : b.signal === "bear" ? "neg" : "muted"} data-bread-sig={b.signal}>{b.signal === "bull" ? "看涨宽度强" : b.signal === "bear" ? "看跌宽度强" : "中性 / 分歧"}</b></span>
            <span className="muted">领涨 {b.topGainer?.symbol} <span className="pos">{fmtPct(b.topGainer?.pct)}</span> · 领跌 {b.topLoser?.symbol} <span className="neg">{fmtPct(b.topLoser?.pct)}</span></span>
          </div>
        </div>
      )}

      {dist.n > 0 && (
        <div className="card" style={{ padding: 14, marginTop: 12 }} data-dist-n={dist.n}>
          <h3 style={{ margin: "0 0 10px", fontSize: 14 }}>
            收益分布 <span className="muted">±1% 分桶直方图 · 形状:σ <b style={{ color: "#e0e6ed" }} data-dist-std={dist.std.toFixed(2)}>{dist.std.toFixed(2)}</b> · 偏度 <b style={{ color: "#e0e6ed" }} data-dist-skew={dist.skew.toFixed(2)}>{dist.skew.toFixed(2)}</b>({skewLabel}) · 超额峰度 <b style={{ color: "#e0e6ed" }} data-dist-kurt={dist.kurt.toFixed(2)}>{dist.kurt.toFixed(2)}</b>({kurtLabel})</span>
          </h3>
          <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 120, padding: "0 4px" }}>
            {dist.bins.map((bin, i) => {
              const h = dist.maxCount ? Math.max(2, (bin.count / dist.maxCount) * 108) : 2;
              const far = Math.abs(bin.mid) >= 1;
              const col = !far ? "#4a525a" : bin.mid < 0 ? "#ef5350" : "#26a69a";
              return (
                <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", height: "100%", justifyContent: "flex-end" }} title={`${binXLabel(bin)}: ${bin.count} 只 (${(bin.share * 100).toFixed(0)}%)`}>
                  <div data-hist={i} style={{ width: "100%", height: h, background: col, borderRadius: "2px 2px 0 0" }} />
                  <div className="muted" style={{ fontSize: 9, marginTop: 2 }}>{binXLabel(bin)}</div>
                </div>
              );
            })}
          </div>
          <div style={{ display: "flex", gap: 22, flexWrap: "wrap", fontSize: 12, marginTop: 10 }}>
            <span className="muted">均值 <b style={{ color: dist.mean >= 0 ? "#26a69a" : "#ef5350" }}>{fmtPct(dist.mean)}</b></span>
            <span className="muted">中位 <b style={{ color: dist.median >= 0 ? "#26a69a" : "#ef5350" }}>{fmtPct(dist.median)}</b></span>
            <span className="muted">最集中 <b style={{ color: "#e0e6ed" }}>{peakLabel}</b> ({peak?.count} 只)</span>
          </div>
          <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>{shapeNote}</div>
        </div>
      )}
    </div>
  );
}
