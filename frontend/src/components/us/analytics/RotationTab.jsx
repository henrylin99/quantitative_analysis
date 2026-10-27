// 行业·风格轮动 tab —— /fund/rotation（15 只 ETF 日线 + 多区间收益）。
// 排名 / 轮动矩阵 / 风格价差 / 相关矩阵全部在本组件内计算（后端只给序列与
// 区间收益），保持口径可独立复算。数据约 10 年日线：归一净值、轮动矩阵、
// 相关矩阵、价差均支持回看窗口选择（默认 250 交易日）。
import { useEffect, useMemo, useState } from "react";
import { fetchUsAnalytics } from "../../../api/usAnalytics";
import LineChart from "../LineChart.jsx";
import { Stat } from "./shared.jsx";
import { normTime, num } from "../../../lib/us/analyticsFmt";

// 15 只 ETF 固定展示序（与后端输出序一致），每只一种颜色。
const COLORS = [
  "#2196f3", "#26a69a", "#ef5350", "#ffd166", "#ab47bc", "#26c6da", "#66bb6a",
  "#ff7043", "#5c6bc0", "#ec407a", "#8d6e63", "#9aa6b2", "#42a5f5", "#facc15", "#4dd0e1",
];
const SPREAD_COLOR = { growth_value: "#2196f3", large_small: "#ab47bc", offensive_defensive: "#26a69a" };
const CATEGORY_LABEL = { sector: "行业", style: "风格", index: "指数" };
const CATEGORY_TONE = { sector: "", style: "warn", index: "muted" };
const HORIZONS = [
  { key: "ret_1d", label: "1日" },
  { key: "ret_5d", label: "5日" },
  { key: "ret_20d", label: "20日" },
  { key: "ret_60d", label: "60日" },
  { key: "ret_period", label: "区间" },
];
const STYLE_SPREADS = [
  { key: "growth_value", label: "成长 vs 价值", long: ["IWF"], short: ["IWD"],
    desc: "IWF(成长) − IWD(价值) 累计超额；上行=成长占优" },
  { key: "large_small", label: "大盘 vs 小盘", long: ["SPY"], short: ["IWM"],
    desc: "SPY(大盘) − IWM(小盘) 累计超额；上行=大盘占优" },
  { key: "offensive_defensive", label: "进攻 vs 防御", long: ["XLY", "XLK"], short: ["XLU", "XLP"],
    desc: "可选+科技(进攻) − 公用+必需(防御) 累计超额；上行=风险偏好扩张" },
];
const pct = (v, d = 1) => (num(v) == null ? "—" : (v >= 0 ? "+" : "") + (v * 100).toFixed(d) + "%");

const mean = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;

// 排名：按某区间收益降序 → [{symbol,label,category,ret,rank}]。
function rankBy(series, key) {
  const rows = series
    .map((s) => ({ symbol: s.symbol, label: s.label, category: s.category, ret: s[key] }))
    .filter((r) => num(r.ret) != null)
    .sort((a, b) => b.ret - a.ret);
  rows.forEach((r, i) => { r.rank = i + 1; });
  return rows;
}

// 起点归一为 100 的可比较净值线。
function rebased(s, base = 100) {
  const pts = (s.data || []).filter((d) => d.close != null);
  if (!pts.length) return [];
  const first = pts[0].close;
  return pts.map((d) => ({ time: d.time, value: (d.close / first) * base }));
}

function pearson(pairs) {
  const ps = pairs.filter(([a, b]) => a != null && b != null && Number.isFinite(a) && Number.isFinite(b));
  const n = ps.length;
  if (n < 2) return null;
  const ma = mean(ps.map((p) => p[0])), mb = mean(ps.map((p) => p[1]));
  let cov = 0, va = 0, vb = 0;
  for (const [a, b] of ps) { const da = a - ma, db = b - mb; cov += da * db; va += da * da; vb += db * db; }
  return va && vb ? cov / Math.sqrt(va * vb) : null;
}

// 日收益 Pearson 相关矩阵（对齐共同交易日）。
function corrMatrix(series) {
  const times = new Set();
  series.forEach((s) => (s.data || []).forEach((d) => times.add(d.time)));
  const T = [...times].sort((a, b) => a - b);
  const ret = {};
  series.forEach((s) => {
    const d = (s.data || []).filter((x) => x.close != null);
    const m = {};
    for (let i = 1; i < d.length; i++) m[d[i].time] = d[i].close / d[i - 1].close - 1;
    ret[s.symbol] = m;
  });
  const syms = series.map((s) => s.symbol);
  const matrix = syms.map((a) => syms.map((b) => (a === b ? 1 : pearson(T.map((t) => [ret[a]?.[t], ret[b]?.[t]])))));
  return { syms, labels: syms.map((s) => s.label || s.symbol), matrix };
}

// 多只 ETF 等权平均成一条 [{time,close}]（按共同时间取均值）。
function avgSeries(list) {
  const clean = list.map((s) => (s.data || []).filter((d) => d.close != null)).filter((x) => x.length);
  if (!clean.length) return [];
  const idx = new Map();
  clean.forEach((pts) => pts.forEach((p) => idx.set(p.time, (idx.get(p.time) || []).concat(p.close))));
  return [...idx.entries()].sort((a, b) => a[0] - b[0]).map(([t, cs]) => ({ time: t, close: mean(cs) }));
}

// 多空篮子累计超额价差（长端减短端的归一收益差，小数）。
function styleSpreads(series) {
  const by = Object.fromEntries(series.map((s) => [s.symbol, s]));
  return STYLE_SPREADS.map((sp) => {
    const longS = avgSeries(sp.long.map((s) => by[s]).filter(Boolean));
    const shortS = avgSeries(sp.short.map((s) => by[s]).filter(Boolean));
    if (!longS.length || !shortS.length) return { ...sp, data: [], last: null };
    const lf = longS[0].close, sf = shortS[0].close;
    const lmap = new Map(longS.map((p) => [p.time, p.close]));
    const smap = new Map(shortS.map((p) => [p.time, p.close]));
    const data = [...new Set([...lmap.keys(), ...smap.keys()])]
      .sort((a, b) => a - b)
      .map((t) => (lmap.has(t) && smap.has(t)
        ? { time: t, value: lmap.get(t) / lf - 1 - (smap.get(t) / sf - 1) }
        : null))
      .filter(Boolean);
    return { ...sp, data, last: data.length ? data[data.length - 1].value : null };
  });
}

// 轮动矩阵：行=ETF，列=窗口内等距采样时点；每格 = 该 ETF 该时点的
// trailing horizon 日收益 + 截面分位（1=最强）。着色用分位。
function rotationMatrix(series, horizon = 20, cols = 12) {
  const timeSet = new Set();
  series.forEach((s) => (s.data || []).forEach((d) => { if (d.close != null) timeSet.add(d.time); }));
  const T = [...timeSet].sort((a, b) => a - b);
  const close = {};
  series.forEach((s) => {
    const m = new Map((s.data || []).filter((d) => d.close != null).map((d) => [d.time, d.close]));
    close[s.symbol] = T.map((t) => (m.has(t) ? m.get(t) : null));
  });
  const maxIdx = T.length - 1;
  const sample = new Set();
  for (let c = 0; c < cols; c++) {
    const i = Math.round((c / (cols - 1)) * maxIdx);
    if (i >= horizon) sample.add(i);
  }
  const sampIdx = [...sample].sort((a, b) => a - b);
  const dateLabels = sampIdx.map((i) => {
    const d = new Date(T[i] * 1000);
    return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")}`;
  });
  const rows = series.map((s) => ({
    symbol: s.symbol, label: s.label, category: s.category,
    cells: sampIdx.map((i) => {
      const arr = close[s.symbol];
      const a = arr?.[i - horizon], b = arr?.[i];
      return (a != null && b != null) ? { ret: b / a - 1 } : { ret: null };
    }),
  }));
  // 每列做截面分位排名（0=最弱, 1=最强）
  sampIdx.forEach((_, c) => {
    const vals = rows.map((r) => r.cells[c].ret).filter((v) => v != null && Number.isFinite(v)).sort((x, y) => x - y);
    const n = vals.length;
    rows.forEach((r) => {
      const v = r.cells[c].ret;
      if (v == null || !Number.isFinite(v) || n < 2) { r.cells[c].pctile = null; r.cells[c].rank = null; return; }
      const below = vals.filter((x) => x < v).length;
      r.cells[c].pctile = below / (n - 1);
      r.cells[c].rank = n - below;
    });
  });
  return { dates: dateLabels, rows };
}

// 相关值着色：红(−1) → 透明(0) → 蓝(+1)。
const corrColor = (r) => {
  if (r == null || !Number.isFinite(r)) return "transparent";
  const a = Math.min(1, Math.abs(r));
  return r >= 0 ? `rgba(33,150,243,${0.15 + a * 0.7})` : `rgba(239,83,80,${0.15 + a * 0.7})`;
};

// 轮动分位着色：1=领涨(绿) / 0=落后(红)。
const rotColor = (p) => {
  if (p == null || !Number.isFinite(p)) return "transparent";
  const a = 0.15 + Math.abs(p - 0.5) * 1.4;
  return p >= 0.5 ? `rgba(38,166,154,${Math.min(0.85, a)})` : `rgba(239,83,80,${Math.min(0.85, a)})`;
};

// 截断每只 ETF 序列到最近 windowDays 根（0=全样本）。
function sliceWindow(series, windowDays) {
  if (!windowDays) return series;
  return series.map((s) => ({ ...s, data: (s.data || []).slice(-windowDays) }));
}

export default function RotationTab() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [horizon, setHorizon] = useState("ret_20d");
  const [rotHorizon, setRotHorizon] = useState(20);
  const [windowDays, setWindowDays] = useState(250);

  useEffect(() => {
    let on = true;
    setErr("");
    fetchUsAnalytics("/fund/rotation")
      .then((d) => { if (on) setData(d); })
      .catch((e) => { if (on) setErr(String(e?.message || e)); });
    return () => { on = false; };
  }, []);

  const seriesRaw = useMemo(
    () => (data || []).map((s) => ({ ...s, data: (s.data || []).map((d) => ({ time: normTime(d.time), close: num(d.close) })) })),
    [data],
  );

  const win = useMemo(() => sliceWindow(seriesRaw, windowDays), [seriesRaw, windowDays]);
  const by = useMemo(() => Object.fromEntries(win.map((s) => [s.symbol, s])), [win]);
  const ranked = useMemo(() => rankBy(win, horizon), [win, horizon]);
  const rot = useMemo(() => rotationMatrix(win, rotHorizon, 12), [win, rotHorizon]);
  const corr = useMemo(() => corrMatrix(win), [win]);
  const spreads = useMemo(() => styleSpreads(win), [win]);
  const rebasedSeries = useMemo(
    () => win.map((s, i) => ({ data: rebased(s), color: COLORS[i % COLORS.length], lineWidth: 1.2 })),
    [win],
  );
  const hLabel = HORIZONS.find((h) => h.key === horizon)?.label || "";
  const nPoints = win[0]?.data?.length || 0;
  const firstDay = nPoints ? new Date(win[0].data[0].time * 1000).toISOString().slice(0, 10) : "";

  if (err) return <div className="spinner">行业轮动数据加载失败：{err}</div>;
  if (!data) return <div className="spinner">加载行业/风格 ETF 数据中…</div>;

  return (
    <div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        {seriesRaw.length} 只行业/风格/宽基 ETF（XLK 科技 / XLF 金融 / … / XLV 医疗 / IWF 成长 / IWD 价值 /
        IWM 小盘 / SPY 标普500）。宏观叠加是 <b>自上而下</b> 的风险背景；本页是股票市场<b>内部结构</b>——
        哪些行业/风格在领涨或落后、谁在轮动。排名/轮动矩阵/价差/相关矩阵均由前端从序列现算。
      </div>

      {/* 回看窗口控制 */}
      <div className="card" style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <b style={{ fontSize: 13 }}>回看窗口</b>
        <select value={windowDays} onChange={(e) => setWindowDays(Number(e.target.value))}>
          <option value={60}>60 交易日</option>
          <option value={120}>120 交易日</option>
          <option value={250}>250 交易日</option>
          <option value={0}>全样本</option>
        </select>
        <span className="muted" style={{ fontSize: 12 }}>
          当前 {nPoints} 根日线{firstDay ? `（${firstDay} 起）` : ""}；归一净值 / 轮动矩阵 / 价差 / 相关矩阵均基于该窗口。
        </span>
      </div>

      {/* 区间净值 */}
      <div className="card" style={{ marginTop: 12 }}>
        <h3>区间净值（窗口起点归一为 100）</h3>
        <LineChart series={rebasedSeries} height={260} />
        <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
          所有 ETF 起点归一为 100，直接比区间累计涨幅；最高线 = 窗口最强行业/风格，最低 = 最弱。
        </div>
      </div>

      {/* 相对强度排名 */}
      <div className="card" style={{ marginTop: 12 }}>
        <h3>
          相对强度排名 ·
          <select value={horizon} onChange={(e) => setHorizon(e.target.value)} style={{ marginLeft: 8 }}>
            {HORIZONS.map((h) => <option key={h.key} value={h.key}>{h.label}收益</option>)}
          </select>
        </h3>
        <table className="data">
          <thead><tr><th>#</th><th>ETF</th><th>类别</th><th>{hLabel}收益</th><th>区间收益</th></tr></thead>
          <tbody>
            {ranked.map((r) => (
              <tr key={r.symbol}>
                <td>{r.rank}</td>
                <td><b>{r.symbol}</b> <span className="muted">{r.label}</span></td>
                <td className={CATEGORY_TONE[r.category] || ""}>{CATEGORY_LABEL[r.category] || r.category}</td>
                <td className={num(r.ret) >= 0 ? "pos" : "neg"}>{pct(r.ret)}</td>
                <td className={num(by[r.symbol]?.ret_period) >= 0 ? "pos" : "neg"}>{pct(by[r.symbol]?.ret_period)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
          按 {hLabel} 收益降序排名；绿=领涨、红=落后。切换周期看短中期轮动（区间收益为后端给的最新收盘口径）。
        </div>
      </div>

      {/* 轮动热力图 */}
      <div className="card" style={{ marginTop: 12 }}>
        <h3>
          轮动热力图 · 每格 = 该 ETF 在该时点的
          <select value={rotHorizon} onChange={(e) => setRotHorizon(Number(e.target.value))} style={{ marginLeft: 6 }}>
            {[5, 10, 20, 40, 60].map((h) => <option key={h} value={h}>{h} 日</option>)}
          </select>
          收益 · 按当列截面排名着色
        </h3>
        <div style={{ overflowX: "auto" }}>
          <table className="data" style={{ borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ position: "sticky", left: 0, background: "var(--tv-bg-panel)" }}>ETF</th>
                {rot.dates.map((d) => <th key={d} style={{ fontSize: 10, fontWeight: 400 }}>{d.slice(5)}</th>)}
              </tr>
            </thead>
            <tbody>
              {rot.rows.map((row) => (
                <tr key={row.symbol}>
                  <td style={{ position: "sticky", left: 0, background: "var(--tv-bg-panel)", fontWeight: 600 }}>
                    <b>{row.symbol}</b> <span className="muted" style={{ fontSize: 10 }}>{row.label}</span>
                  </td>
                  {row.cells.map((c, i) => (
                    <td key={i} title={c.ret != null ? `${pct(c.ret)} · 排名 ${c.rank}/${rot.rows.length}` : "—"}
                      style={{ background: rotColor(c.pctile), textAlign: "center", fontSize: 10, minWidth: 46,
                        padding: "4px 2px", fontVariantNumeric: "tabular-nums",
                        color: c.pctile != null && Math.abs(c.pctile - 0.5) > 0.35 ? "#fff" : "inherit" }}>
                      {c.ret != null ? pct(c.ret) : "—"}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
          绿 = 该时点领涨（截面分位靠前）、红 = 落后。横向追踪一行 = 该行业/风格的领先度随时间变化；
          某行由红转绿 = 轮动切入该行业。
        </div>
      </div>

      {/* 风格价差 */}
      <div className="card" style={{ marginTop: 12 }}>
        <h3>风格价差 · 长端累计超额（上行 = 长端风格占优）</h3>
        <LineChart
          series={spreads.map((sp) => ({ data: sp.data, color: SPREAD_COLOR[sp.key] || "#4f93e7", lineWidth: 2 }))}
          height={240}
        />
        <div className="stats" style={{ marginTop: 8 }}>
          {spreads.map((sp) => (
            <Stat key={sp.key} label={sp.label} value={pct(sp.last, 2)}
              tone={num(sp.last) > 0 ? "pos" : num(sp.last) < 0 ? "neg" : ""} sub="窗口累计超额" />
          ))}
        </div>
        <div style={{ marginTop: 8 }}>
          {spreads.map((sp) => (
            <div key={sp.key} className="muted" style={{ fontSize: 12, marginTop: 2 }}>
              <b style={{ color: SPREAD_COLOR[sp.key] || "inherit" }}>{sp.label}</b>：{sp.desc}
            </div>
          ))}
        </div>
      </div>

      {/* 相关矩阵 */}
      <div className="card" style={{ marginTop: 12 }}>
        <h3>相关性矩阵 · {seriesRaw.length} ETF 日收益 Pearson r</h3>
        <div style={{ overflowX: "auto" }}>
          <table className="data" style={{ borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ position: "sticky", left: 0, background: "var(--tv-bg-panel)" }}></th>
                {corr.labels.map((l) => <th key={l} style={{ fontSize: 10, fontWeight: 400 }}>{l}</th>)}
              </tr>
            </thead>
            <tbody>
              {corr.matrix.map((row, i) => (
                <tr key={corr.syms[i]}>
                  <td style={{ position: "sticky", left: 0, background: "var(--tv-bg-panel)", fontWeight: 600, fontSize: 11 }}>
                    {corr.labels[i]}
                  </td>
                  {row.map((r, j) => (
                    <td key={j} title={`${corr.labels[i]} ↔ ${corr.labels[j]}: ${r != null ? r.toFixed(3) : "—"}`}
                      style={{ background: corrColor(r), textAlign: "center", fontSize: 10, minWidth: 38,
                        padding: "3px 2px", fontVariantNumeric: "tabular-nums",
                        color: r != null && Math.abs(r) > 0.6 ? "#fff" : "inherit" }}>
                      {r != null ? r.toFixed(2) : "—"}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
          蓝 = 正相关、红 = 负相关。防御类（XLU/XLP）与进攻类（XLY/XLK）相关性偏低甚至转负 = 风格分化；
          同风格内部高相关（如 XLK↔IWF）。
        </div>
      </div>
    </div>
  );
}
