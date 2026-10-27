// 风险调整收益排名 Tab：Sharpe = mean/std·√252（rf=0）、Sortino = mean/下行偏差·√252、
// Calmar = CAGR/|maxDD|，按 Sharpe 降序的全池截面排名（/risk/sharpe?window=）。
// 后端附等权市场基准的同口径统计（market 键）；window 同时控制市场滚动窗口口径。
import { useEffect, useMemo, useState } from "react";
import {
  riskFetch, num, signed, pct1, sortRows,
} from "../../../lib/us/riskUtils";

const WIN_OPTS = [63, 126, 252];

// 风险调整绩效档位：≥2 优秀 / [1,2) 良好 / [0,1) 一般 / <0 差（负风险溢价）。
function sharpeVerdict(sh) {
  const v = num(sh);
  if (v == null) return { label: "—", tone: "" };
  if (v >= 2.0) return { label: "优秀", tone: "pos" };
  if (v >= 1.0) return { label: "良好", tone: "pos" };
  if (v >= 0.0) return { label: "一般", tone: "" };
  return { label: "差（负溢价）", tone: "neg" };
}

function Stat({ label, value, tone = "", sub = "" }) {
  return (
    <div className="stat">
      <div className="muted" style={{ fontSize: 11 }}>{label}</div>
      <div className={tone} style={{ fontSize: 18, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{value}</div>
      {sub && <div className="muted" style={{ fontSize: 10 }}>{sub}</div>}
    </div>
  );
}

const shTone = (v) => (num(v) == null ? "" : v >= 1 ? "pos" : v < 0 ? "neg" : "");
// 回撤字段为负数（-0.56），直接 ×100 显示
const ddpct = (v) => (num(v) == null ? "—" : (v * 100).toFixed(1) + "%");

export default function SharpeTab({ mk = "us" }) {
  const [data, setData] = useState(null);
  const [window_, setWindow] = useState(126);
  const [err, setErr] = useState("");
  const [sortKey, setSortKey] = useState("rank");
  const [sortDir, setSortDir] = useState("asc");

  useEffect(() => {
    let alive = true;
    setData(null); setErr("");
    riskFetch("/risk/sharpe", { window: window_ })
      .then((d) => { if (alive) setData(d); })
      .catch((e) => { if (alive) setErr(e.message || String(e)); });
    return () => { alive = false; };
  }, [window_]);

  const ranking = data?.ranking || [];
  const mkt = data?.market;
  const sorted = useMemo(() => sortRows(ranking, sortKey, sortDir), [ranking, sortKey, sortDir]);

  if (err) return <div className="card neg" style={{ fontSize: 13 }}>风险调整收益数据加载失败：{err}</div>;
  if (!data) return <div className="spinner">加载风险调整收益数据中…</div>;

  const top = ranking.slice(0, 5);
  const bottom = ranking.slice(-5).reverse();
  const mktVd = sharpeVerdict(mkt?.sharpe);

  const toggleSort = (k) => {
    if (k === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(k); setSortDir(k === "symbol" || k === "name" ? "asc" : "desc"); }
  };
  const arrow = (k) => (k === sortKey ? (sortDir === "asc" ? " ▲" : " ▼") : "");

  return (
    <div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        风险调整收益排名（{data.n_stocks} 只标的，{data.n_days} 个交易日）。回答「<b>承担单位风险换来多少收益</b>」。
        三个互补比率：<b>Sharpe 看总波、Sortino 只惩罚下行、Calmar 看最大回撤</b>（后端为全样本口径，
        window 控制等权市场基准的滚动窗口）。
      </div>

      <div className={`card ${mktVd.tone}`} style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span style={{ fontSize: 14 }}>市场窗口</span>
          <select value={window_} onChange={(e) => setWindow(+e.target.value)}>
            {WIN_OPTS.map((w) => <option key={w} value={w}>{w}日</option>)}
          </select>
        </div>
        <div style={{ fontSize: 24, fontWeight: 700 }} className={mktVd.tone}>
          等权市场 · {mktVd.label} · Sharpe {signed(mkt?.sharpe)}
        </div>
        <div className="muted" style={{ flex: 1, minWidth: 260, fontSize: 12 }}>
          等权指数（全池日收益均值复合）的同口径统计，作为个股排名的基准线。
        </div>
      </div>

      <div className="muted" style={{ fontSize: 11, marginTop: 10 }}>等权市场基准</div>
      <div className="stats" style={{ flexWrap: "wrap" }}>
        <Stat label="Sharpe" value={signed(mkt?.sharpe)} tone={shTone(mkt?.sharpe)} sub="mean/std·√252" />
        <Stat label="Sortino" value={signed(mkt?.sortino)} tone={shTone(mkt?.sortino)} sub="仅下行风险" />
        <Stat label="Calmar" value={signed(mkt?.calmar)} tone={shTone(mkt?.calmar)} sub="CAGR/|maxDD|" />
        <Stat label="年化收益(CAGR)" value={pct1(mkt?.cagr)} sub="几何复合" />
        <Stat label="年化波动" value={pct1(mkt?.ann_vol)} sub="std×√252" />
        <Stat label="最大回撤" value={ddpct(mkt?.max_dd)} tone="neg" sub="峰值最大跌幅" />
      </div>

      <div className="card">
        <h3>Sharpe 最高 Top 5 / 最低 Bottom 5</h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
          <div>
            <div className="pos" style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>▲ 单位风险收益最佳</div>
            {top.map((r) => (
              <div key={r.symbol} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0" }}>
                <span><b>{r.symbol}</b> <span className="muted" style={{ fontSize: 11 }}>
                  {r.name} · Sortino {signed(r.sortino)} · Calmar {signed(r.calmar)}</span></span>
                <span className="pos">Sharpe {signed(r.sharpe)}</span>
              </div>
            ))}
          </div>
          <div>
            <div className="neg" style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>▼ 负风险溢价 / 高波动低收益</div>
            {bottom.map((r) => (
              <div key={r.symbol} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0" }}>
                <span><b>{r.symbol}</b> <span className="muted" style={{ fontSize: 11 }}>
                  {r.name} · 回撤 {ddpct(r.max_dd)} · 波动 {pct1(r.ann_vol)}</span></span>
                <span className={r.sharpe < 0 ? "neg" : ""}>Sharpe {signed(r.sharpe)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card">
        <h3>全池风险调整收益排名 · 按 Sharpe 降序（rank 1 = 单位风险收益最佳）</h3>
        <div className="scroll" style={{ maxHeight: 460 }}>
          <table className="data">
            <thead><tr>
              <th onClick={() => toggleSort("rank")}>#{arrow("rank")}</th>
              <th onClick={() => toggleSort("symbol")}>标的{arrow("symbol")}</th>
              <th onClick={() => toggleSort("name")}>名称{arrow("name")}</th>
              <th onClick={() => toggleSort("sharpe")}>Sharpe{arrow("sharpe")}</th>
              <th onClick={() => toggleSort("sortino")}>Sortino{arrow("sortino")}</th>
              <th onClick={() => toggleSort("calmar")}>Calmar{arrow("calmar")}</th>
              <th onClick={() => toggleSort("cagr")}>CAGR{arrow("cagr")}</th>
              <th onClick={() => toggleSort("ann_vol")}>年化波动{arrow("ann_vol")}</th>
              <th onClick={() => toggleSort("max_dd")}>最大回撤{arrow("max_dd")}</th>
              <th onClick={() => toggleSort("n")}>样本{arrow("n")}</th>
            </tr></thead>
            <tbody>
              {sorted.map((r) => (
                <tr key={r.symbol}>
                  <td className="muted">{r.rank}</td>
                  <td><b>{r.symbol}</b></td>
                  <td className="muted">{r.name}</td>
                  <td className={shTone(r.sharpe)}>{signed(r.sharpe)}</td>
                  <td className={shTone(r.sortino)}>{signed(r.sortino)}</td>
                  <td className={shTone(r.calmar)}>{signed(r.calmar)}</td>
                  <td className={r.cagr >= 0 ? "pos" : "neg"}>{pct1(r.cagr)}</td>
                  <td className="muted">{pct1(r.ann_vol)}</td>
                  <td className="neg">{ddpct(r.max_dd)}</td>
                  <td className="muted">{r.n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
