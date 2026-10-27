// 美股组合分析 —— 参考开源组合分析实现：多标的等权组合视角——
// 相对表现（共同起始日归一）、回撤水下图、年化收益/波动/Sharpe/Beta 表、VaR/CVaR、
// 风险-收益散点 + 马科维茨有效前沿、滚动相关性与滚动 Beta、相关矩阵。
// 全部由 /api/us-stock 历史日线在客户端纯函数计算。
import { useEffect, useMemo, useState } from "react";
import LineChart from "../../components/us/LineChart.jsx";
import ScatterChart from "../../components/us/ScatterChart.jsx";
import { fetchUsBars, fetchUsSnapshotRows } from "../../api/usTerminal";
import { returns, corrMatrix, rebasedAt, equalWeightPortfolio, basketReturns, betaOf, rollingBeta, avgRollingCorr, drawdownSeries } from "../../lib/us/portfolio.js";
import { efficientFrontier } from "../../lib/us/frontier.js";
import { perfMetrics } from "../../lib/us/performance.js";
import { historicalVaR, parametricVaR, cvarHistorical } from "../../lib/us/risk.js";
import "./us-tv.css";

// max drawdown of an equity curve (peak-tracking); perfMetrics needs it for Calmar.
const drawdownOf = (eq) => {
  let peak = -Infinity, dd = 0;
  for (const p of eq) { if (p.value > peak) peak = p.value; if (peak > 0) dd = Math.min(dd, p.value / peak - 1); }
  return dd;
};

const COLORS = ["#4f93e7", "#ffd166", "#26a69a", "#ef5350", "#c792ea", "#4dd0e1", "#ff8a65", "#aed581"];
const DIM = [30, 36, 41];
const mix = (a, b, k) => a.map((c, i) => Math.round(c + (b[i] - c) * Math.max(0, Math.min(1, k))));
// correlation cell tint: +1 → blue (co-move), 0 → dim (uncorrelated), −1 → red (opposed)
const cellColor = (r) => {
  if (r == null) return "rgba(154,166,178,0.12)";
  const k = Math.max(-1, Math.min(1, r));
  return k >= 0 ? `rgb(${mix(DIM, [79, 147, 231], k)})` : `rgb(${mix(DIM, [239, 83, 80], -k)})`;
};

// One-line payoff read-out: how much risk the basket shed vs holding its members.
const diversificationNote = (rows) => {
  const members = rows.filter((r) => !r.isPort && r.perf);
  const port = rows.find((r) => r.isPort && r.perf);
  if (!members.length || !port) return "成员不足,无法对比。";
  const avgVol = members.reduce((s, r) => s + r.perf.vol, 0) / members.length;
  const avgSharpe = members.reduce((s, r) => s + (r.perf.sharpe ?? 0), 0) / members.length;
  const pVol = (port.perf.vol * 100).toFixed(1);
  const aVol = (avgVol * 100).toFixed(1);
  const cut = (avgVol - port.perf.vol) * 100;
  const bits = [`等权组合年化波动 ${pVol}% vs 成员均值 ${aVol}%`];
  if (cut > 0.2) bits.push(`分散使风险降低约 ${cut.toFixed(1)} 个百分点`);
  const psh = port.perf.sharpe ?? 0;
  if (psh > avgSharpe + 0.05) bits.push(`风险调整后收益更优(Sharpe ${psh.toFixed(2)} > 成员均值 ${avgSharpe.toFixed(2)})`);
  else if (psh < avgSharpe - 0.05) bits.push(`Sharpe(${psh.toFixed(2)})未超成员均值(${avgSharpe.toFixed(2)}),分散主要降风险而非抬收益`);
  return bits.join(" · ") + "。";
};

export default function UsPortfolioPage() {
  const [symbols, setSymbols] = useState([]); // 全部候选 {symbol, name}
  const [sel, setSel] = useState([]);
  const [barsMap, setBarsMap] = useState({}); // symbol → daily bars
  const [query, setQuery] = useState(""); // candidate-picker search filter

  // 候选池 = 全部美股；默认选中市值前 6
  useEffect(() => {
    fetchUsSnapshotRows().then((rows) => {
      setSymbols(rows.map((r) => ({ symbol: r.symbol, name: r.name || r.symbol })));
      const top = [...rows]
        .filter((r) => r.market_cap != null)
        .sort((a, b) => b.market_cap - a.market_cap)
        .slice(0, 6)
        .map((r) => r.symbol);
      setSel((prev) => (prev.length ? prev : top));
    }).catch(() => {});
  }, []);

  // refetch only when the selection changes (capped at 8 for a readable matrix)
  useEffect(() => {
    if (!sel.length) return;
    let alive = true;
    Promise.all(sel.map((sym) => fetchUsBars(sym, "2y").then((b) => [sym, b]).catch(() => [sym, []])))
      .then((entries) => { if (alive) setBarsMap(Object.fromEntries(entries)); })
      .catch(() => {});
    return () => { alive = false; };
  }, [sel]);

  const series = useMemo(
    () => sel.map((sym) => ({ symbol: sym, rets: returns(barsMap[sym] || []) })),
    [sel, barsMap]
  );
  const { matrix, mean } = useMemo(() => corrMatrix(series), [series]);

  // Equal-weight basket over the date range EVERY member shares; that shared
  // start is the anchor the relative-performance lines are rebased to, so the
  // white portfolio line and the coloured members start at 100 together.
  const portEq = useMemo(() => equalWeightPortfolio(series), [series]);
  const start = portEq.length ? portEq[0].time : -Infinity;
  const lines = useMemo(
    () => sel.map((sym, i) => ({ color: COLORS[i % COLORS.length], lineWidth: 2, label: sym, data: rebasedAt(barsMap[sym] || [], start) }))
      .filter((l) => l.data.length),
    [sel, barsMap, start]
  );
  const portPerf = useMemo(() => (portEq.length ? perfMetrics(portEq, "daily", drawdownOf(portEq)) : null), [portEq]);

  // Portfolio underwater (drawdown) curve + its path stats: max depth, current
  // depth, and the longest / current "below water" runs — the WHEN behind the
  // single max-drawdown number. Pure peak-tracking over the equal-weight equity.
  const portDD = useMemo(() => drawdownSeries(portEq), [portEq]);
  const ddStats = useMemo(() => {
    if (!portDD.length) return null;
    const vs = portDD.map((p) => p.value);
    let longest = 0, run = 0;
    for (const v of vs) { if (v < -1e-12) { run++; if (run > longest) longest = run; } else run = 0; }
    return { max: Math.min(...vs), cur: vs[vs.length - 1], longest, curRun: run, n: vs.length };
  }, [portDD]);

  // Beta of each member vs the equal-weight basket (the in-house market proxy):
  // >1 amplifies the basket, <1 stabilises. The basket's own beta is exactly 1.
  const basketRets = useMemo(() => basketReturns(series), [series]);
  const betaBySym = useMemo(() => {
    const m = {};
    for (const s of series) m[s.symbol] = betaOf(s.rets, basketRets);
    return m;
  }, [series, basketRets]);

  // One-day tail risk per member + the equal-weight basket: VaR (the loss not
  // exceeded on 95% of days) both historical (empirical 5th percentile) and
  // parametric (mean-1.645σ, normal assumption), plus CVaR / expected shortfall
  // (the average loss on the worst 5% of days). 历史/参数 > 1 = realized tails
  // deeper than normal predicts (fat left tail → parametric understates risk).
  const varRows = useMemo(() => {
    if (!basketRets.length) return null;
    const br = basketRets.map((p) => p.r);
    const rows = series.map((s) => {
      const rr = s.rets.map((p) => p.r);
      return { symbol: s.symbol, hv: historicalVaR(rr, 0.05), pv: parametricVaR(rr, 0.05), cv: cvarHistorical(rr, 0.05) };
    });
    rows.push({ symbol: "组合(等权)", hv: historicalVaR(br, 0.05), pv: parametricVaR(br, 0.05), cv: cvarHistorical(br, 0.05), isPort: true });
    return rows;
  }, [series, basketRets]);

  // Every member's risk-adjusted return over the SAME shared window (its
  // common-start rebased curve) plus the basket as a final highlighted row —
  // the diversification payoff is "portfolio vol < average member vol" and a
  // Sharpe that holds up vs the (more volatile) individuals.
  const perfRows = useMemo(() => {
    const rows = lines.map((l) => ({ symbol: l.label, eq: l.data, perf: perfMetrics(l.data, "daily", drawdownOf(l.data)), dd: drawdownOf(l.data), beta: betaBySym[l.label] }));
    if (portEq.length) rows.push({ symbol: "组合(等权)", eq: portEq, perf: portPerf, dd: drawdownOf(portEq), beta: 1, isPort: true });
    return rows;
  }, [lines, portEq, portPerf, betaBySym]);
  // risk-return frontier: each member plotted at (annualized vol, annualized
  // return). Upper-left dominates; the equal-weight basket should sit on the
  // efficient edge of the member cloud — the visual case for diversification.
  const frontierPts = useMemo(() => perfRows.filter((r) => r.perf).map((r) => ({
    x: r.perf.vol * 100, y: r.perf.cagr * 100, symbol: r.symbol, size: r.isPort ? 7 : 5,
    color: r.isPort ? "#ffffff" : COLORS[sel.indexOf(r.symbol) % COLORS.length],
  })), [perfRows, sel]);
  // Markowitz efficient frontier (closed-form, shorts allowed) over the members'
  // common window: the theoretical min-variance hyperbola that DOMINATES every real
  // portfolio. Plotted as an amber curve through the member cloud, with the global
  // min-variance and max-Sharpe (tangency) portfolios highlighted.
  const ef = useMemo(() => (series.length >= 2 ? efficientFrontier(series, 40) : null), [series]);
  const allLines = useMemo(() => {
    const out = [...lines];
    if (portEq.length) out.push({ color: "#ffffff", lineWidth: 3, label: "组合(等权)", data: portEq.map((p) => ({ time: p.time, value: p.value * 100 })) });
    return out;
  }, [lines, portEq]);

  // Rolling correlation regime: how tightly the basket co-moves over time (60-bar
  // window). A spike = holdings converging (diversification failing, classic in
  // sell-offs); current above its own history mean+1σ flags an elevated regime.
  const rollCorr = useMemo(() => (series.length >= 2 ? avgRollingCorr(series, 60) : []), [series]);
  const rollStats = useMemo(() => {
    if (rollCorr.length < 2) return null;
    const vs = rollCorr.map((p) => p.value);
    const avg = vs.reduce((s, v) => s + v, 0) / vs.length;
    const sd = Math.sqrt(vs.reduce((s, v) => s + (v - avg) ** 2, 0) / vs.length);
    const cur = vs[vs.length - 1];
    const max = Math.max(...vs), min = Math.min(...vs);
    return { avg, sd, cur, max, min, elevated: cur > avg + sd };
  }, [rollCorr]);

  // Per-member rolling beta vs the basket (60-bar). Member betas sum to n, so the
  // MEAN is always 1; the individual lines + amplifier count carry the signal.
  const rollBeta = useMemo(() => (series.length >= 2
    ? series.map((s, i) => ({ sym: s.symbol, color: COLORS[i % COLORS.length], pts: rollingBeta(s.rets, basketRets, 60) }))
    : []), [series, basketRets]);
  const betaLines = useMemo(() => rollBeta.map((r) => ({ data: r.pts, color: r.color, lineWidth: 2 })).filter((l) => l.data.length), [rollBeta]);
  const betaNow = useMemo(() => rollBeta.map((r) => ({ sym: r.sym, color: r.color, b: r.pts.length ? r.pts[r.pts.length - 1].value : null })), [rollBeta]);
  const ampCount = betaNow.filter((x) => x.b != null && x.b > 1).length;
  const betaValid = betaNow.filter((x) => x.b != null).length;

  // Selection handlers for the chip + search picker. add() refuses past the 8-cap
  // (no silent drop of the oldest — the disabled candidates + cue explain it).
  const remove = (sym) => setSel((p) => p.filter((x) => x !== sym));
  const add = (sym) => setSel((p) => (p.length >= 8 || p.includes(sym) ? p : [...p, sym]));
  const clearAll = () => setSel([]);
  const atCap = sel.length >= 8;
  // Candidate cloud: unselected symbols matching the search box (symbol OR name).
  const candidates = useMemo(() => {
    const q = query.trim().toUpperCase();
    const picked = new Set(sel);
    return symbols
      .filter((s) => !picked.has(s.symbol))
      .filter((s) => !q || s.symbol.includes(q) || (s.name || "").toUpperCase().includes(q));
  }, [symbols, sel, query]);

  return (
    <div className="us-tv">
      <div className="card" style={{ padding: "10px 12px", marginBottom: 14 }} data-pf-select>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span className="muted" style={{ fontSize: 12, whiteSpace: "nowrap" }}>已选 <b data-sel-count={sel.length}>{sel.length}</b>/8:</span>
          {sel.length === 0 && <span className="muted" style={{ fontSize: 12 }}>点击下方候选加入组合</span>}
          {sel.map((sym, i) => (
            <span key={sym} className="chip" data-sel-chip={sym} style={{ borderColor: COLORS[i % COLORS.length] }}>
              <i style={{ background: COLORS[i % COLORS.length] }} />{sym}
              <button onClick={() => remove(sym)} title="移除">×</button>
            </span>
          ))}
          {mean != null && (
            <span className="muted" style={{ marginLeft: "auto", fontSize: 12, whiteSpace: "nowrap" }}>
              平均相关性 <b className={mean > 0.5 ? "neg" : "pos"} data-mean={mean.toFixed(2)}>{mean.toFixed(2)}</b>{" "}
              {mean > 0.5 ? "(趋同,分散度低)" : mean < 0.2 ? "(较分散)" : "(中等)"}
            </span>
          )}
        </div>
        <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索代码或名称…" style={{ width: 180 }} data-pf-search />
          <button onClick={clearAll} disabled={!sel.length}>清空</button>
          <span className="muted" style={{ fontSize: 12 }}>
            {atCap ? "已达 8 只上限,移除一个再添加" : `候选 ${candidates.length}${query ? " (已筛选)" : ""}`}
          </span>
        </div>
        <div style={{ marginTop: 8, maxHeight: 120, overflowY: "auto", display: "flex", flexWrap: "wrap", gap: 6, alignContent: "flex-start" }} data-pf-candidates>
          {candidates.slice(0, 80).map((s) => (
            <button key={s.symbol} className="cand" data-cand={s.symbol} disabled={atCap}
              onClick={() => add(s.symbol)} title={`${s.symbol} · ${s.name}`}>
              {s.symbol}
            </button>
          ))}
          {candidates.length === 0 && <span className="muted" style={{ fontSize: 12 }}>无匹配候选。</span>}
          {candidates.length > 80 && <span className="muted" style={{ fontSize: 12, alignSelf: "center" }}>+{candidates.length - 80} 更多,细化搜索</span>}
        </div>
      </div>

      <div className="card">
        <h3>相对表现 · 全部以共同起始日归一化至 100 <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>· 白线=等权组合</span></h3>
        {allLines.length ? <LineChart series={allLines} height={260} /> : <div className="muted">点击上方候选加入组合。</div>}
      </div>

      {ddStats && (
        <div className="card">
          <h3>回撤曲线 · 等权组合逐点低于历史峰值的幅度 <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>· 水下(underwater)图 · 0%=创新高,谷底=最大回撤</span></h3>
          <LineChart series={[{ color: "#ef5350", lineWidth: 2, data: portDD.map((p) => ({ time: p.time, value: p.value * 100 })) }]} height={180} />
          <div className="stats" style={{ marginTop: 8 }}>
            <div className="stat"><div className="muted" style={{ fontSize: 11 }}>最大回撤</div><div className="neg" data-dd-max={ddStats.max} style={{ fontSize: 15, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{(Math.abs(ddStats.max) * 100).toFixed(1)}%</div></div>
            <div className="stat"><div className="muted" style={{ fontSize: 11 }}>当前回撤</div><div className={ddStats.cur < -0.001 ? "neg" : "pos"} data-dd-cur={ddStats.cur} style={{ fontSize: 15, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{(Math.abs(ddStats.cur) * 100).toFixed(1)}%</div></div>
            <div className="stat"><div className="muted" style={{ fontSize: 11 }}>最长水下</div><div data-dd-longest={ddStats.longest} style={{ fontSize: 15, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{ddStats.longest} 根</div></div>
            <div className="stat"><div className="muted" style={{ fontSize: 11 }}>已连水</div><div className="muted" data-dd-currun={ddStats.curRun} style={{ fontSize: 15, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{ddStats.curRun} 根</div></div>
            <div className="stat"><div className="muted" style={{ fontSize: 11 }}>窗口</div><div className="muted" style={{ fontSize: 15, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{ddStats.n} 根</div></div>
          </div>
          <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>把组合净值逐点对比其历史最高点:跌破峰值即为"水下"(红色下沉),回到 0%=收复前高。曲线显示分散化表里那个单一最大回撤数字<b>发生在何时、持续多久</b>——长而深的谷(长期水下)比尖锐但快速恢复的回撤更难承受。</div>
        </div>
      )}

      {perfRows.some((r) => r.perf) && (
        <div className="card">
          <h3>分散化收益 · 共同窗口内 年化波动/Sharpe/Beta <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>· 等权组合 vs 各成员</span></h3>
          <table className="data">
            <thead>
              <tr>
                <th>标的</th>
                <th style={{ textAlign: "right" }}>年化收益</th>
                <th style={{ textAlign: "right" }}>年化波动</th>
                <th style={{ textAlign: "right" }}>Sharpe</th>
                <th style={{ textAlign: "right" }}>最大回撤</th>
                <th style={{ textAlign: "right" }} title="相对等权组合的系统风险:Beta>1 放大组合,Beta<1 稳定/分散">Beta</th>
              </tr>
            </thead>
            <tbody>
              {perfRows.filter((r) => r.perf).map((r) => (
                <tr key={r.symbol} style={r.isPort ? { background: "rgba(255,255,255,0.06)", fontWeight: 700 } : undefined}>
                  <td className="sym">{r.symbol}</td>
                  <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{(r.perf.cagr * 100).toFixed(1)}%</td>
                  <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{(r.perf.vol * 100).toFixed(1)}%</td>
                  <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{r.perf.sharpe != null ? r.perf.sharpe.toFixed(2) : "—"}</td>
                  <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{(r.dd * 100).toFixed(1)}%</td>
                  <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }} data-beta={r.symbol} className={r.isPort ? "muted" : r.beta > 1.2 ? "neg" : r.beta < 0.8 ? "pos" : ""}>
                    {r.beta == null ? "—" : r.isPort ? "1.00 (基准)" : r.beta.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>{diversificationNote(perfRows)}</div>
          <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>Beta(基准=等权组合) 衡量各成员对组合的系统风险贡献:&gt;1 放大组合波动,&lt;1 起稳定/分散作用。组合自身 Beta=1。</div>
        </div>
      )}

      {varRows && (
        <div className="card">
          <h3>风险价值 VaR/CVaR · 1 日 <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>· 95% 置信 · 历史 vs 正态参数 · CVaR=条件期望损失(预期缺口)</span></h3>
          <table className="data">
            <thead>
              <tr>
                <th>标的</th>
                <th style={{ textAlign: "right" }} title="历史 VaR:实测日收益的第 5 分位(最坏 5% 的边界亏损)">95% VaR(历史)</th>
                <th style={{ textAlign: "right" }} title="参数 VaR:均值−1.645σ(正态分布假设,σ=样本标准差)">95% VaR(参数)</th>
                <th style={{ textAlign: "right" }} title="CVaR/预期缺口:最坏 5% 日的平均亏损(必 ≥ VaR)">95% CVaR</th>
                <th style={{ textAlign: "right" }} title="历史 VaR ÷ 参数 VaR:&gt;1 实测尾部比正态更深(肥尾,参数法低估风险) / &lt;1 正态偏保守">历史/参数</th>
              </tr>
            </thead>
            <tbody>
              {varRows.map((r) => {
                const ratio = r.hv != null && r.pv ? r.hv / r.pv : null;
                return (
                  <tr key={r.symbol} style={r.isPort ? { background: "rgba(255,255,255,0.06)", fontWeight: 700 } : undefined}>
                    <td className="sym">{r.symbol}</td>
                    <td className="neg" style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{r.hv == null ? "—" : (r.hv * 100).toFixed(1) + "%"}</td>
                    <td className="neg" style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{r.pv == null ? "—" : (r.pv * 100).toFixed(1) + "%"}</td>
                    <td className="neg" style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{r.cv == null ? "—" : (r.cv * 100).toFixed(1) + "%"}</td>
                    <td className={ratio == null ? "muted" : ratio > 1.15 ? "neg" : ratio < 0.9 ? "pos" : ""} style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{ratio == null ? "—" : ratio.toFixed(2)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>VaR 回答"95% 的日子里亏损不超过多少",CVaR 回答"一旦落入最坏 5%,平均亏多少"——CVaR 恒 ≥ VaR,更能反映尾部深度。历史法直接取实测分位(不假设分布),参数法用正态假设(均值−1.645σ);<b>历史/参数 &gt; 1</b> 说明真实尾部比正态更深(肥尾),参数法会低估极端亏损。</div>
        </div>
      )}

      {frontierPts.length >= 2 && (
        <div className="card">
          <h3>风险-收益前沿 · 各成员 年化收益 vs 年化波动 <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>· 左上=高回报低风险(优) / 右下=高风险低回报(劣) · 白点=等权组合 · 橙线=有效前沿</span></h3>
          <div data-frontier={frontierPts.length}>
            <ScatterChart
              points={[
                ...frontierPts,
                ...(ef ? [{ x: ef.minVar.x, y: ef.minVar.y, symbol: "最小方差", color: "#ff9800", size: 8 }] : []),
                ...(ef && ef.maxSharpe ? [{ x: ef.maxSharpe.x, y: ef.maxSharpe.y, symbol: "最大夏普", color: "#ffc107", size: 8 }] : []),
              ]}
              curve={ef ? ef.curve : []}
              xLabel="年化波动 %" yLabel="年化收益 %" height={300} regression={false}
            />
          </div>
          {ef && (
            <div className="stats" style={{ marginTop: 8 }}>
              <div className="stat"><div className="muted" style={{ fontSize: 11 }}>最小方差</div><div style={{ fontSize: 13, fontVariantNumeric: "tabular-nums" }}>σ {(ef.minVar.x).toFixed(1)}% · R {(ef.minVar.y).toFixed(1)}%</div></div>
              <div className="stat"><div className="muted" style={{ fontSize: 11 }}>最大夏普</div><div style={{ fontSize: 13, fontVariantNumeric: "tabular-nums" }}>{ef.maxSharpe ? `Sharpe ${ef.maxSharpe.sharpe.toFixed(2)} · σ ${ef.maxSharpe.x.toFixed(1)}%` : "—"}</div></div>
              <div className="stat"><div className="muted" style={{ fontSize: 11 }}>等权组合</div><div className="muted" style={{ fontSize: 13, fontVariantNumeric: "tabular-nums" }}>{(() => { const p = perfRows.find((r) => r.isPort); return p && p.perf ? `σ ${(p.perf.vol * 100).toFixed(1)}%` : "—"; })()}</div></div>
            </div>
          )}
          <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>橙线为<b>有效前沿</b>(闭式解,允许做空):同一期望收益下可达的最低风险轨迹,故它一定在所有成员/等权点的左上方——任何落在曲线右下方的点(含被占优的成员)都可被前沿上同收益更低风险的组合替代。最小方差点=全曲线风险最低;最大夏普点=风险调整后收益最优(切点)。</div>
        </div>
      )}

      {rollStats && (
        <div className="card">
          <h3>相关性随时间 · 60 根滚动平均两两相关 <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>· {rollStats.elevated ? <span className="neg">当前相关性偏高(高于历史均值+1σ)</span> : <span className="pos">当前相关性处于常态</span>}</span></h3>
          <LineChart series={[{ color: rollStats.elevated ? "#ef5350" : "#4f93e7", lineWidth: 2, data: rollCorr }]} height={200} />
          <div className="stats" style={{ marginTop: 8 }}>
            <div className="stat"><div className="muted" style={{ fontSize: 11 }}>当前</div><div className={rollStats.cur > 0.5 ? "neg" : rollStats.cur < 0.2 ? "pos" : ""} style={{ fontSize: 15, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{rollStats.cur.toFixed(2)}</div></div>
            <div className="stat"><div className="muted" style={{ fontSize: 11 }}>历史均值</div><div style={{ fontSize: 15, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{rollStats.avg.toFixed(2)}</div></div>
            <div className="stat"><div className="muted" style={{ fontSize: 11 }}>区间</div><div className="muted" style={{ fontSize: 15, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{rollStats.min.toFixed(2)} ~ {rollStats.max.toFixed(2)}</div></div>
            <div className="stat"><div className="muted" style={{ fontSize: 11 }}>波动 σ</div><div style={{ fontSize: 15, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{rollStats.sd.toFixed(2)}</div></div>
          </div>
          <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>静态矩阵是整段历史的一个平均;这条线显示组合内部相关性的<b>时变</b>:上升=成员趋同(分散失效,常见于暴跌)、下降=趋异。当前 {rollStats.cur.toFixed(2)} {rollStats.elevated ? "明显高于常态,分散效果正在减弱" : "处于常态区间"}。</div>
        </div>
      )}

      {betaLines.length >= 2 && (
        <div className="card">
          <h3>Beta 随时间 · 60 根滚动 各成员 vs 等权组合 <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>· β&gt;1 放大组合 / β&lt;1 稳定 · 当前 <b className={ampCount > betaValid / 2 ? "neg" : "pos"} data-amp={ampCount} data-amp-total={betaValid}>{ampCount}/{betaValid}</b> 成员放大</span></h3>
          <LineChart series={betaLines} height={200} />
          <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>每条线是一只成员相对等权组合的滚动 Beta:上升=该成员对组合的系统风险贡献增大(更放大波动)。等权组合各成员 Beta 之和恒等于成员数(均值恒为 1),但<b>单个成员</b>的 Beta 时变——看谁在放大、谁在稳定。</div>
        </div>
      )}

      {sel.length >= 2 && (
        <div className="card">
          <h3>相关性矩阵 · 日收益 Pearson r <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>· 蓝=正相关(同涨同跌) / 红=负相关 / 暗≈0(无关,最利于分散)</span></h3>
          <div className="scroll" style={{ maxHeight: 380, overflowX: "auto" }}>
            <table className="data">
              <thead>
                <tr>
                  <th></th>
                  {sel.map((s) => <th key={s} style={{ fontSize: 11, textAlign: "center" }}>{s}</th>)}
                </tr>
              </thead>
              <tbody>
                {matrix.map((row, i) => (
                  <tr key={i}>
                    <td className="sym" style={{ fontSize: 11 }}>{sel[i]}</td>
                    {row.map((r, j) => (
                      <td key={j} data-i={i} data-j={j} className="corr-cell" style={{ textAlign: "center", background: cellColor(r), color: "#fff", fontSize: 11, fontVariantNumeric: "tabular-nums" }}>
                        {r == null ? "—" : r.toFixed(2)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>大量暗/红格(低或负相关)→ 组合分散良好;全蓝格 → 持仓高度趋同,等于重复押注同一驱动因子。</div>
        </div>
      )}
    </div>
  );
}
