// 回撤分析 Tab：水下路径（price/cummax-1，恒≤0）+ 滚动最大回撤 + 水下时长。
// 数据来自 /risk/drawdown?symbol=（后端逐票由运行峰值算回撤路径、最深谷底、
// 水下时长与是否修复；市场 = 每票自首个有效收盘归一为 1 的等权指数；
// 深度为正数幅度，0.22 = 22% 回撤；滚动窗口固定 63 日口径）。
import { useEffect, useMemo, useState } from "react";
import LineChart from "../LineChart.jsx";
import {
  riskFetch, toLine, num, pct1, depthPct, days, yesno, sortRows,
} from "../../../lib/us/riskUtils";

// 体制 = 当前深度（新高/浅/中/深/崩盘）× 历史韧性（稳健/常态/脆弱）。
function regime(stats) {
  if (!stats) return { key: "n/a", label: "—", tone: "", desc: "无数据" };
  const cur = num(stats.current_dd);
  const mx = num(stats.max_dd);
  if (cur == null || mx == null)
    return { key: "neutral", label: "中性", tone: "", desc: "回撤数据不足。" };
  const depth = cur <= 0.005 ? { key: "ath", label: "历史新高", tone: "pos" }
    : cur <= 0.05 ? { key: "shallow", label: "浅回撤", tone: "pos" }
    : cur <= 0.15 ? { key: "moderate", label: "中度回撤", tone: "" }
    : cur <= 0.30 ? { key: "deep", label: "深度回撤", tone: "neg" }
    : { key: "crash", label: "崩盘级", tone: "neg" };
  const resilience = mx <= 0.20 ? { key: "robust", label: "稳健", tone: "pos" }
    : mx <= 0.40 ? { key: "normal", label: "常态", tone: "" }
    : { key: "fragile", label: "脆弱", tone: "neg" };
  const rank = { neg: 3, "": 1, pos: 0 };
  const tone = rank[depth.tone] >= rank[resilience.tone] ? depth.tone : resilience.tone;
  const curWord = depth.key === "ath" ? "处于历史新高（基本无回撤）"
    : depth.key === "shallow" ? "浅幅回撤（<5%）"
    : depth.key === "moderate" ? "中度回撤（5–15%）"
    : depth.key === "deep" ? "深度回撤（15–30%）" : "崩盘级回撤（>30%）";
  const histWord = resilience.key === "robust" ? "历史最坏回撤 <20%（低波动）"
    : resilience.key === "normal" ? "历史最坏回撤 20–40%（常态）" : "历史最坏回撤 >40%（曾遭重创）";
  const desc = `市场等权指数当前回撤 ${depthPct(cur)}（${curWord}）；历史最大回撤 ${depthPct(mx)}（${histWord}）。`;
  return { key: `${depth.key}_${resilience.key}`, label: `${depth.label} · ${resilience.label}`, tone, desc };
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

export default function DrawdownTab() {
  const [data, setData] = useState(null);
  const [symbols, setSymbols] = useState([]);
  const [symbol, setSymbol] = useState("AAPL");
  const [err, setErr] = useState("");
  const [sortKey, setSortKey] = useState("rank");
  const [sortDir, setSortDir] = useState("asc");

  useEffect(() => {
    riskFetch("/symbols").then((d) => setSymbols(d?.symbols || [])).catch(() => {});
  }, []);

  useEffect(() => {
    let alive = true;
    setData(null); setErr("");
    riskFetch("/risk/drawdown", { symbol })
      .then((d) => { if (alive) setData(d); })
      .catch((e) => { if (alive) setErr(e.message || String(e)); });
    return () => { alive = false; };
  }, [symbol]);

  const reg = useMemo(() => regime(data), [data]);
  const ranking = data?.ranking || [];
  const symInfo = data?.symbol_info;
  const sorted = useMemo(() => sortRows(ranking, sortKey, sortDir), [ranking, sortKey, sortDir]);

  if (err) return <div className="card neg" style={{ fontSize: 13 }}>回撤数据加载失败：{err}</div>;
  if (!data) return <div className="spinner">加载回撤数据中…</div>;

  const mktUnder = toLine(data.underwater_series);
  const rollingMaxDd = toLine(data.rolling_maxdd_series);

  // 最深回撤榜（max_dd 最大）与最接近新高榜（current_dd 最小）
  const deepest = [...ranking].sort((a, b) => (b.max_dd ?? 0) - (a.max_dd ?? 0)).slice(0, 5);
  const atHigh = [...ranking].sort((a, b) => (a.current_dd ?? 9) - (b.current_dd ?? 9)).slice(0, 5);
  const nAtHigh = ranking.filter((r) => (r.current_dd ?? 9) <= 0.005).length;
  const nUnderwater = ranking.length - nAtHigh;

  const toggleSort = (k) => {
    if (k === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(k); setSortDir(k === "symbol" || k === "name" || k === "max_dd_date" ? "asc" : "desc"); }
  };
  const arrow = (k) => (k === sortKey ? (sortDir === "asc" ? " ▲" : " ▼") : "");

  return (
    <div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        回撤与路径风险（{data.n_stocks} 只标的，{data.n_days} 个交易日）。回答「<b>价格从高点回落多深、滞留水下多久</b>」。
        回撤取决于收益的「顺序」（路径依赖）——两只波动率与偏度都相同的股票，回撤可以截然不同。
        最大回撤 ≥ 当前回撤（今天不会比历史最坏更坏）。
      </div>

      <div className={`card ${reg.tone}`} style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        <div style={{ fontSize: 26, fontWeight: 700 }} className={reg.tone}>{reg.label}</div>
        <div className="muted" style={{ flex: 1, minWidth: 260, fontSize: 12 }}>{reg.desc}</div>
      </div>

      <div className="stats" style={{ flexWrap: "wrap" }}>
        <Stat label="市场当前回撤" value={depthPct(data.current_dd)} tone="neg" sub="等权指数距最近高点" />
        <Stat label="市场最大回撤" value={depthPct(data.max_dd)} tone="neg" sub={data.max_dd_date || "历史最深"} />
        <Stat label="水下时间" value={pct1(data.underwater_pct)} tone="neg" sub="低于峰值占比" />
        <Stat label="最长水下" value={days(data.longest_dd_days)} tone="neg" sub="连续交易日" />
        <Stat label="创新高" value={nAtHigh} tone="pos" sub={`只标的（共 ${ranking.length}）`} />
        <Stat label="仍水下" value={nUnderwater} tone="neg" sub="只标的" />
      </div>

      <div className="card">
        <h3>市场水下曲线（等权指数相对自身历史高点，恒 ≤ 0）</h3>
        <LineChart data={mktUnder} color="#ef5350" height={200} />
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          0 线=创新高，谷底即历史最大回撤——路径风险的全貌：跌多深、在水下滞留多久。
        </div>
      </div>

      <div className="card">
        <h3>市场滚动最大回撤（63 日窗口，正数=幅度）</h3>
        <LineChart data={rollingMaxDd} color="#fb8c00" height={180} />
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          每个时点上过去 63 日窗口内的最深峰谷跌幅。高=近期出现急跌；趋降=市场修复中。
        </div>
      </div>

      <div className="card">
        <h3>
          个股水下曲线 ·
          <select value={symbol} onChange={(e) => setSymbol(e.target.value)} style={{ marginLeft: 8 }}>
            {(symbols.length ? symbols : [symbol]).map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </h3>
        {symInfo ? (
          <>
            <LineChart series={[
              { data: toLine(symInfo.underwater_series), color: "#ef5350", lineWidth: 2 },
              { data: toLine(symInfo.mkt_underwater_series), color: "#4f93e7", lineWidth: 1.5 },
            ]} height={200} />
            <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
              红 = 该标的相对自身历史高点的回撤；蓝 = 市场水下曲线。红更深/更久 = 路径风险高于市场。
            </div>
          </>
        ) : <div className="muted" style={{ fontSize: 12 }}>该标的无回撤序列。</div>}
      </div>

      {symInfo && (
        <div className="card" style={{ display: "flex", gap: 24, flexWrap: "wrap", alignItems: "center" }}>
          <b style={{ fontSize: 16 }}>{symInfo.symbol}</b>
          <span className="muted">{symInfo.name}</span>
          <Stat label="最大回撤" value={depthPct(symInfo.max_dd)} tone="neg" sub={symInfo.max_dd_date || ""} />
          <Stat label="当前回撤" value={depthPct(symInfo.current_dd)} tone="neg" />
          <Stat label="水下时间" value={pct1(symInfo.underwater_pct)} />
          <Stat label="最长水下" value={days(symInfo.longest_dd_days)} />
          <Stat label="已修复" value={yesno(symInfo.recovered)} tone={symInfo.recovered ? "pos" : "neg"} />
          <Stat label="回撤排名" value={symInfo.rank != null ? `#${symInfo.rank} / ${ranking.length}` : "—"} sub="最深回撤序" />
        </div>
      )}

      <div className="card">
        <h3>最深回撤 Top 5 / 最接近新高 Top 5</h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
          <div>
            <div className="neg" style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>▲ 最深回撤（点击查看水下曲线）</div>
            {deepest.map((r) => (
              <div key={r.symbol} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", cursor: "pointer" }}
                onClick={() => setSymbol(r.symbol)}>
                <span><b>{r.symbol}</b> <span className="muted" style={{ fontSize: 11 }}>{r.name}</span></span>
                <span className="neg">{depthPct(r.max_dd)}</span>
              </div>
            ))}
          </div>
          <div>
            <div className="pos" style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>▼ 最接近新高</div>
            {atHigh.map((r) => (
              <div key={r.symbol} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", cursor: "pointer" }}
                onClick={() => setSymbol(r.symbol)}>
                <span><b>{r.symbol}</b> <span className="muted" style={{ fontSize: 11 }}>{r.name}</span></span>
                <span className="pos">{depthPct(r.current_dd)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card">
        <h3>全池回撤排名 · 按最大回撤降序</h3>
        <div className="scroll" style={{ maxHeight: 460 }}>
          <table className="data">
            <thead><tr>
              <th onClick={() => toggleSort("rank")}>#{arrow("rank")}</th>
              <th onClick={() => toggleSort("symbol")}>代码{arrow("symbol")}</th>
              <th onClick={() => toggleSort("name")}>名称{arrow("name")}</th>
              <th onClick={() => toggleSort("max_dd")}>最大回撤{arrow("max_dd")}</th>
              <th onClick={() => toggleSort("current_dd")}>当前回撤{arrow("current_dd")}</th>
              <th onClick={() => toggleSort("underwater_pct")}>水下时间{arrow("underwater_pct")}</th>
              <th onClick={() => toggleSort("longest_dd_days")}>最长水下{arrow("longest_dd_days")}</th>
              <th onClick={() => toggleSort("max_dd_date")}>谷底日期{arrow("max_dd_date")}</th>
              <th onClick={() => toggleSort("recovered")}>已修复{arrow("recovered")}</th>
            </tr></thead>
            <tbody>
              {sorted.map((r) => (
                <tr key={r.symbol} style={{ cursor: "pointer" }} onClick={() => setSymbol(r.symbol)}>
                  <td className="muted">{r.rank}</td>
                  <td><b>{r.symbol}</b></td>
                  <td className="muted">{r.name}</td>
                  <td className="neg">{depthPct(r.max_dd)}</td>
                  <td className="neg">{depthPct(r.current_dd)}</td>
                  <td>{pct1(r.underwater_pct)}</td>
                  <td>{days(r.longest_dd_days)}</td>
                  <td className="muted">{r.max_dd_date || "—"}</td>
                  <td className={r.recovered ? "pos" : "neg"}>{yesno(r.recovered)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
