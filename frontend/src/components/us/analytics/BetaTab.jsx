// 贝塔与系统性风险 Tab：市场模型 r_s = α + β·r_m + ε（等权市场 = 全池日收益均值）。
// 数据来自 /risk/beta?symbol=&window=（后端全历史 OLS + trailing 滚动 β/R² 序列 +
// 个股 vs 等权指数归一化双线；方差分解精确成立 Var(r_s) = β²·Var(r_m) + Var(ε)）。
import { useEffect, useMemo, useState } from "react";
import LineChart from "../LineChart.jsx";
import {
  riskFetch, toLine, flatLine, num, signed, pct1, pct0, volAnnual, sortRows,
} from "../../../lib/us/riskUtils";

const WINDOWS = [63, 126, 252];

// 体制 = 系统性风险姿态，由 β 驱动：
// >1.25 进攻型 / >1.10 偏高 / 0.90–1.10 贴近市场 / 0.75–0.90 偏低 / >0 防御型 / ≤0 负相关对冲。
function regime(stats) {
  if (!stats) return { key: "n/a", label: "—", tone: "", desc: "无数据" };
  const beta = num(stats.beta);
  const r2 = num(stats.r2);
  if (beta == null)
    return { key: "neutral", label: "数据不足", tone: "", desc: "收益序列不足以拟合市场模型。" };
  let posture;
  if (beta > 1.25) posture = { key: "aggressive", label: "进攻型", tone: "pos" };
  else if (beta > 1.10) posture = { key: "high", label: "偏高β", tone: "pos" };
  else if (beta >= 0.90) posture = { key: "market", label: "贴近市场", tone: "" };
  else if (beta >= 0.75) posture = { key: "mild", label: "偏低β", tone: "" };
  else if (beta > 0) posture = { key: "defensive", label: "防御型", tone: "neg" };
  else posture = { key: "hedge", label: "负相关·对冲", tone: "neg" };
  const sysPct = r2 != null ? r2 * 100 : null;
  const desc = `全历史市场模型 β = ${signed(beta, 3)}（市场每涨 1%，该标的平均${beta >= 0 ? "涨 " : "跌 "}${Math.abs(beta).toFixed(2)}%` +
    `${Math.abs(beta - 1) < 0.1 ? "，与市场同步" : beta > 1 ? "，放大市场波动" : "，弱于市场"}）。` +
    (sysPct != null ? `R² = ${pct1(r2)}：市场解释了该标的 ${sysPct.toFixed(0)}% 的日收益方差，其余 ${(100 - sysPct).toFixed(0)}% 为特质风险。` : "");
  return { key: posture.key, label: posture.label, tone: posture.tone, desc };
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

const betaTone = (v) => (num(v) == null ? "" : v >= 1.1 ? "pos" : v < 0.8 ? "neg" : "");

export default function BetaTab({ mk = "us" }) {
  const [data, setData] = useState(null);
  const [symbols, setSymbols] = useState([]);
  const [symbol, setSymbol] = useState("");
  const [windowW, setWindowW] = useState(126);
  const [err, setErr] = useState("");
  const [sortKey, setSortKey] = useState("rank");
  const [sortDir, setSortDir] = useState("asc");

  useEffect(() => {
    riskFetch("/symbols", undefined, mk).then((d) => setSymbols(d?.symbols || [])).catch(() => {});
  }, [mk]);

  useEffect(() => {
    if (symbols.length && !symbols.includes(symbol)) setSymbol(symbols[0]);
  }, [symbols, symbol]);


  useEffect(() => {
    let alive = true;
    setData(null); setErr("");
    riskFetch("/risk/beta", { symbol, window: windowW }, mk)
      .then((d) => { if (alive) setData(d); })
      .catch((e) => { if (alive) setErr(e.message || String(e)); });
    return () => { alive = false; };
  }, [symbol, windowW]);

  const symInfo = data?.symbol_info;
  const reg = useMemo(() => regime(symInfo), [symInfo]);
  const ranking = data?.ranking || [];
  const sorted = useMemo(() => sortRows(ranking, sortKey, sortDir), [ranking, sortKey, sortDir]);

  if (err) return <div className="card neg" style={{ fontSize: 13 }}>贝塔数据加载失败：{err}</div>;
  if (!data) return <div className="spinner">加载贝塔/系统性风险数据中…</div>;

  const mostAgg = ranking.filter((r) => r.beta != null).sort((a, b) => b.beta - a.beta).slice(0, 5);
  const mostDef = ranking.filter((r) => r.beta != null).sort((a, b) => a.beta - b.beta).slice(0, 5);
  const sysPct = symInfo?.r2 != null ? symInfo.r2 * 100 : null;

  const stockLine = symInfo ? toLine(symInfo.stock_index) : [];
  const mktLine = toLine(data.index).filter((p) => !stockLine.length || p.time >= stockLine[0].time);
  const betaLine = symInfo ? toLine(symInfo.beta_series) : [];
  const betaBase = symInfo ? flatLine(symInfo.beta_series, 1.0) : [];
  const r2Line = symInfo ? toLine(symInfo.r2_series) : [];

  const toggleSort = (k) => {
    if (k === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(k); setSortDir(k === "symbol" || k === "name" ? "asc" : "desc"); }
  };
  const arrow = (k) => (k === sortKey ? (sortDir === "asc" ? " ▲" : " ▼") : "");

  return (
    <div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        贝塔与系统性风险（{data.n_stocks} 只标的，{data.n_days} 个交易日）。回答「<b>该标的有多少风险是市场带来的、多少是自身的</b>」。
        β&gt;1 放大市场、&lt;1 弱于市场；R² = 市场可解释的<b>方差占比</b>（= corr²）。
        核心恒等：<b>Var(r<sub>s</sub>) = β²·Var(r<sub>m</sub>) + Var(ε)</b>。
      </div>

      <div className={`card ${reg.tone}`} style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        <div style={{ fontSize: 26, fontWeight: 700 }} className={reg.tone}>
          {symInfo ? `${symInfo.symbol} · ${reg.label}` : reg.label}
        </div>
        <div className="muted" style={{ flex: 1, minWidth: 260, fontSize: 12 }}>{reg.desc}</div>
      </div>

      <div className="stats" style={{ flexWrap: "wrap" }}>
        <Stat label="市场年化波动" value={volAnnual(data.mkt_vol)} sub="等权市场 σ_m ×√252" />
        <Stat label="全池中位 β" value={data.median_beta != null ? data.median_beta.toFixed(3) : "—"} sub="长期市场敏感度中位数" />
        <Stat label="进攻型数量" value={data.n_aggressive} tone="pos" sub="β ≥ 1.10" />
        <Stat label="防御型数量" value={data.n_defensive} tone="neg" sub="β < 0.80" />
      </div>

      {symInfo && (
        <div className="stats" style={{ flexWrap: "wrap" }}>
          <Stat label="β（市场敏感度）" value={signed(symInfo.beta, 3)} tone={betaTone(symInfo.beta)} sub="全历史 OLS 斜率" />
          <Stat label="α（日均超额）" value={pct1(symInfo.alpha)} sub="截距，日均" />
          <Stat label="R²（市场解释占比）" value={pct0(symInfo.r2)} tone={symInfo.r2 >= 0.5 ? "pos" : ""} sub="= corr²" />
          <Stat label="相关系数" value={symInfo.corr != null ? symInfo.corr.toFixed(3) : "—"} sub="r_s vs r_m" />
          <Stat label="系统波动(年化)" value={volAnnual(symInfo.sys_vol)} sub="|β|·σ_m" />
          <Stat label="特质波动(年化)" value={volAnnual(symInfo.idio_vol)} tone="neg" sub="σ_ε" />
          <Stat label="总波动(年化)" value={volAnnual(symInfo.tot_vol)} sub="σ_s = √(系统²+特质²)" />
        </div>
      )}

      <div className="card">
        <h3>
          滚动 β · 窗口
          <select value={windowW} onChange={(e) => setWindowW(+e.target.value)} style={{ marginLeft: 8 }}>
            {WINDOWS.map((w) => <option key={w} value={w}>{w} 日</option>)}
          </select>
          （trailing 市场模型 β_t，灰虚线 = 1.0 同步基准）
        </h3>
        {symInfo ? (
          <>
            <LineChart series={[
              { data: betaLine, color: "#ef5350", lineWidth: 2 },
              { data: betaBase, color: "#888", lineWidth: 1 },
            ]} height={200} />
            <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
              持续 &gt;1 放大市场、&lt;1 弱于市场；β 的漂移反映业务/杠杆/行业敏感度的变化。
            </div>
          </>
        ) : <div className="muted" style={{ fontSize: 12 }}>选择标的查看其市场敏感度演变。</div>}
      </div>

      <div className="card">
        <h3>滚动 R²（窗口 {windowW} 日，市场解释的方差占比）</h3>
        {symInfo ? (
          <LineChart data={r2Line} color="#42a5f5" height={180} />
        ) : <div className="muted" style={{ fontSize: 12 }}>选择标的。</div>}
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          1.0 = 完全跟随市场、0 = 完全自身驱动。R² 升高 = 越来越「跟着大盘走」（避险/联动期常见）。
        </div>
      </div>

      <div className="card">
        <h3>
          归一化价格 ·
          <select value={symbol} onChange={(e) => setSymbol(e.target.value)} style={{ marginLeft: 8 }}>
            {(symbols.length ? symbols : [symbol]).map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          （红）vs 等权市场（蓝），均起点 = 1
        </h3>
        {symInfo ? (
          <>
            <LineChart series={[
              { data: stockLine, color: "#ef5350", lineWidth: 2 },
              { data: mktLine, color: "#4f93e7", lineWidth: 1.5 },
            ]} height={220} />
            <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
              两者起点都归一为 1。红线斜率高于蓝 = 跑赢市场、低于 = 跑输。
              β 度量的是日收益的同步性而非累计涨跌——高 β 名字不一定累计涨更多，只是放大市场起伏。
            </div>
          </>
        ) : <div className="muted" style={{ fontSize: 12 }}>选择标的。</div>}
      </div>

      {symInfo && (
        <div className="card">
          <h3>方差分解 · Var(r<sub>s</sub>) = β²·Var(r<sub>m</sub>) + Var(ε)</h3>
          <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
            该标的日收益总方差中，<b style={{ color: "#42a5f5" }}>市场可解释 {sysPct != null ? sysPct.toFixed(1) : "—"}%</b>（= R²），
            <b style={{ color: "#ef5350" }}>特质风险 {sysPct != null ? (100 - sysPct).toFixed(1) : "—"}%</b>。
            特质部分可通过分散化消除，系统部分不能。
          </div>
          <div style={{ display: "flex", height: 22, borderRadius: 4, overflow: "hidden", fontVariantNumeric: "tabular-nums" }}>
            <div style={{ width: `${sysPct || 0}%`, background: "#42a5f5", color: "#fff", fontSize: 11, lineHeight: "22px", paddingLeft: 6 }}>
              {sysPct != null && sysPct > 8 ? `系统 ${sysPct.toFixed(0)}%` : ""}
            </div>
            <div style={{ width: `${sysPct != null ? 100 - sysPct : 100}%`, background: "#ef5350", color: "#fff", fontSize: 11, lineHeight: "22px", paddingLeft: 6 }}>
              {sysPct != null && 100 - sysPct > 8 ? `特质 ${(100 - sysPct).toFixed(0)}%` : ""}
            </div>
          </div>
        </div>
      )}

      <div className="card">
        <h3>最高 / 最低 β Top 5（点击切换标的）</h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
          <div>
            <div className="pos" style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>▲ 最高 β（最进攻）</div>
            {mostAgg.map((r) => (
              <div key={r.symbol} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", cursor: "pointer" }}
                onClick={() => setSymbol(r.symbol)}>
                <span><b>{r.symbol}</b> <span className="muted" style={{ fontSize: 11 }}>R² {pct0(r.r2)}</span></span>
                <span className="pos">{signed(r.beta, 3)}</span>
              </div>
            ))}
          </div>
          <div>
            <div className="neg" style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>▼ 最低 β（最防御）</div>
            {mostDef.map((r) => (
              <div key={r.symbol} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", cursor: "pointer" }}
                onClick={() => setSymbol(r.symbol)}>
                <span><b>{r.symbol}</b> <span className="muted" style={{ fontSize: 11 }}>R² {pct0(r.r2)}</span></span>
                <span className="neg">{signed(r.beta, 3)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card">
        <h3>全池 β 排名 · 按 β 降序（rank 1 = 最高 β / 最进攻）</h3>
        <div className="scroll" style={{ maxHeight: 460 }}>
          <table className="data">
            <thead><tr>
              <th onClick={() => toggleSort("rank")}>#{arrow("rank")}</th>
              <th onClick={() => toggleSort("symbol")}>代码{arrow("symbol")}</th>
              <th onClick={() => toggleSort("name")}>名称{arrow("name")}</th>
              <th onClick={() => toggleSort("beta")}>β{arrow("beta")}</th>
              <th onClick={() => toggleSort("alpha")}>α(日均){arrow("alpha")}</th>
              <th onClick={() => toggleSort("corr")}>corr{arrow("corr")}</th>
              <th onClick={() => toggleSort("r2")}>R²{arrow("r2")}</th>
              <th onClick={() => toggleSort("sys_vol")}>系统σ(年化){arrow("sys_vol")}</th>
              <th onClick={() => toggleSort("idio_vol")}>特质σ(年化){arrow("idio_vol")}</th>
              <th onClick={() => toggleSort("tot_vol")}>总σ(年化){arrow("tot_vol")}</th>
            </tr></thead>
            <tbody>
              {sorted.map((r) => (
                <tr key={r.symbol} style={{ cursor: "pointer" }} onClick={() => setSymbol(r.symbol)}>
                  <td className="muted">{r.rank}</td>
                  <td><b>{r.symbol}</b></td>
                  <td className="muted">{r.name}</td>
                  <td className={betaTone(r.beta)}>{signed(r.beta, 3)}</td>
                  <td className="muted">{pct1(r.alpha)}</td>
                  <td className="muted">{r.corr != null ? r.corr.toFixed(3) : "—"}</td>
                  <td className={r.r2 >= 0.5 ? "pos" : ""}>{pct0(r.r2)}</td>
                  <td className="muted">{volAnnual(r.sys_vol)}</td>
                  <td className="muted">{volAnnual(r.idio_vol)}</td>
                  <td>{volAnnual(r.tot_vol)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
