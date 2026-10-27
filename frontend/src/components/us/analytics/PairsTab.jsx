// 配对交易·协整 Tab：两段式交互——先展示全池协整扫描（/risk/pairs，按 ADF t 升序的
// top 配对），点击某行（或在详情里改 A/B）再加载该配对细节（/risk/pairs?symbol_a=&symbol_b=
// 价格水平 OLS 对冲 P_a=α+β·P_b 的残差价差 + ADF 检验 + 半衰期 + spread/zscore 序列）。
// 核心提醒：相关系数（收益层面）≠ 协整（价格层面）——同涨同跌不代表价差会回归。
import { useEffect, useMemo, useState } from "react";
import LineChart from "../LineChart.jsx";
import {
  riskFetch, toLine, flatLine, num, signed, pct1, fixed3, hlLabel, sortRows,
} from "../../../lib/us/riskUtils";

// Engle-Granger 残差协整两档临界值（约 n=500）：t ≤ -3.37 拒绝单位根（协整·可交易）、
// ≤ -2.86 边缘、否则非协整。半衰期 = -ln2/ln(1+κ)。
function verdict(stats) {
  if (!stats) return { key: "n/a", label: "—", tone: "", desc: "无数据" };
  const t = num(stats.tstat);
  const hl = num(stats.halflife);
  const corr = num(stats.corr);
  const z = num(stats.spread_z);
  if (t == null)
    return { key: "neutral", label: "数据不足", tone: "", desc: "价差序列不足以做 ADF 检验。" };
  let posture;
  if (t <= -3.37) posture = { key: "coint", label: "协整 · 可交易", tone: "pos" };
  else if (t <= -2.86) posture = { key: "marginal", label: "边缘协整", tone: "" };
  else posture = { key: "none", label: "非协整", tone: "neg" };
  const hlTxt = hl != null ? (hl < 1000 ? `${hl.toFixed(1)} 天` : "极慢/无回归") : "无回归";
  const zTxt = z != null
    ? (Math.abs(z) >= 2
      ? (z > 0 ? "价差偏高（做空 A / 做多 B 信号）" : "价差偏低（做多 A / 做空 B 信号）")
      : "价差中性")
    : "";
  const desc = `ADF t = ${signed(t)}（${t <= -3.37 ? "<-3.37 拒绝单位根，价差平稳"
    : t <= -2.86 ? "边缘，弱均值回归" : ">-2.86 无法拒绝单位根，价差非平稳"}）。` +
    `半衰期 ${hlTxt}；${corr != null ? `收益相关 ${fixed3(corr)}（注意：相关≠协整）。` : ""}` +
    (zTxt ? `当前 z=${signed(z)}，${zTxt}。` : "");
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

const tTone = (t) => (num(t) == null ? "" : t <= -3.37 ? "pos" : t > -2.86 ? "neg" : "");
const zTone = (z) => (num(z) == null || Math.abs(z) < 2 ? "" : z > 0 ? "neg" : "pos");

export default function PairsTab() {
  const [scan, setScan] = useState(null);
  const [detail, setDetail] = useState(null);
  const [symbols, setSymbols] = useState([]);
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [detailErr, setDetailErr] = useState("");
  const [detailLoading, setDetailLoading] = useState(false);
  const [scanErr, setScanErr] = useState("");
  const [sortKey, setSortKey] = useState("rank");
  const [sortDir, setSortDir] = useState("asc");

  useEffect(() => {
    riskFetch("/symbols").then((d) => setSymbols(d?.symbols || [])).catch(() => {});
    setDetailLoading(true);
    riskFetch("/risk/pairs", { top: 12 })
      .then(setScan)
      .catch((e) => setScanErr(e.message || String(e)))
      .finally(() => setDetailLoading(false));
  }, []);

  const pair = detail?.pair;

  // 详情加载：A/B 都必传（路由约定：仅传 A 会落入扫描口径）。
  const loadDetail = (aSym, bSym) => {
    if (!aSym || !bSym || aSym === bSym) return;
    setDetailLoading(true); setDetailErr("");
    riskFetch("/risk/pairs", { symbol_a: aSym, symbol_b: bSym })
      .then(setDetail)
      .catch((e) => setDetailErr(e.message || String(e)))
      .finally(() => setDetailLoading(false));
  };

  // 扫描表点行 → 进入详情
  const openPair = (row) => {
    setA(row.symbol_a); setB(row.symbol_b);
    loadDetail(row.symbol_a, row.symbol_b);
  };

  // 换 A：先用当前 B（或占位 B）拉一次拿 partners，再自动切到 A 的最强协整伙伴
  const changeA = (nextA) => {
    const guessB = b && b !== nextA ? b : (detail?.partners?.[0]?.symbol)
      || symbols.find((s) => s !== nextA) || "";
    setA(nextA); setB(guessB);
    loadDetail(nextA, guessB);
  };
  // 换 B：直接重载（用户显式选择后不再自动纠正）
  const changeB = (nextB) => {
    setB(nextB);
    if (a && nextB && nextB !== a) loadDetail(a, nextB);
  };

  const vd = useMemo(() => verdict(pair), [pair]);
  const partners = detail?.partners || [];
  const sortedPartners = useMemo(() => sortRows(partners, sortKey, sortDir), [partners, sortKey, sortDir]);

  const toggleSort = (k) => {
    if (k === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(k); setSortDir(k === "symbol" || k === "name" ? "asc" : "asc"); }
  };
  const arrow = (k) => (k === sortKey ? (sortDir === "asc" ? " ▲" : " ▼") : "");

  // ---------------------------------------------------------- 详情视图 ----
  if (a && b) {
    const spreadLine = pair ? toLine(pair.spread_series) : [];
    const spreadMean = pair ? flatLine(pair.spread_series, pair.spread_mean) : [];
    const zLine = pair ? toLine(pair.zscore_series) : [];
    const zUp = pair ? flatLine(pair.zscore_series, 2) : [];
    const zDn = pair ? flatLine(pair.zscore_series, -2) : [];
    const priceA = pair ? toLine(pair.priceA) : [];
    const priceB = pair ? toLine(pair.priceB) : [];
    const topCoint = partners.slice(0, 5);

    return (
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8, flexWrap: "wrap" }}>
          <button type="button" onClick={() => { setA(""); setB(""); setDetail(null); }}>← 返回扫描</button>
          <span style={{ fontSize: 14 }}>标的 A</span>
          <select value={a} onChange={(e) => changeA(e.target.value)}>
            {(symbols.length ? symbols : [a]).map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <span className="muted">/</span>
          <span style={{ fontSize: 14 }}>标的 B</span>
          <select value={b} onChange={(e) => changeB(e.target.value)}>
            {(partners.length ? partners.map((p) => p.symbol) : [b]).map((s) => (
              <option key={s} value={s}>{s}{partners.find((p) => p.symbol === s) ? ` — ${partners.find((p) => p.symbol === s).name}` : ""}</option>
            ))}
          </select>
          {detailLoading && <span className="muted" style={{ fontSize: 12 }}>计算协整中（逐伙伴 ADF）…</span>}
        </div>

        {detailErr && <div className="card neg" style={{ fontSize: 13 }}>配对详情加载失败：{detailErr}</div>}
        {!pair && !detailLoading && <div className="spinner">加载配对详情中…</div>}

        {pair && (
          <>
            <div className={`card ${vd.tone}`} style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
              <div style={{ fontSize: 24, fontWeight: 700 }} className={vd.tone}>{pair.a}/{pair.b} · {vd.label}</div>
              <div className="muted" style={{ flex: 1, minWidth: 260, fontSize: 12 }}>{vd.desc}</div>
            </div>

            <div className="stats" style={{ flexWrap: "wrap" }}>
              <Stat label="对冲比 β" value={signed(pair.beta, 3)} sub="价格 OLS 斜率" />
              <Stat label="收益相关" value={fixed3(pair.corr)} tone={(pair.corr ?? 0) >= 0.5 ? "pos" : ""} sub="≠协整" />
              <Stat label="ADF t 统计量" value={signed(pair.tstat)} tone={tTone(pair.tstat)}
                sub={pair.tstat <= -3.37 ? "<-3.37 协整" : pair.tstat <= -2.86 ? "边缘" : "非协整"} />
              <Stat label="半衰期" value={hlLabel(pair.halflife)}
                tone={pair.halflife != null && pair.halflife < 30 ? "pos" : ""} sub="-ln2/ln(1+κ)" />
              <Stat label="价差 z-score" value={signed(pair.spread_z)} tone={zTone(pair.spread_z)}
                sub={Math.abs(pair.spread_z ?? 0) >= 2 ? "交易信号" : "中性"} />
              <Stat label="共同交易日" value={pair.n} sub="价格对齐样本" />
            </div>

            <div className="card">
              <h3>对冲价差 s = P<sub>a</sub> − (α+β·P<sub>b</sub>)（灰线 = 均值）</h3>
              <LineChart series={[
                { data: spreadLine, color: "#26a69a", lineWidth: 2 },
                { data: spreadMean, color: "#888", lineWidth: 1 },
              ]} height={200} />
              <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                残差价差。围绕均值回归 = 可交易；发散 = 非协整。z 偏离 ±2σ 是建仓区。
              </div>
            </div>

            <div className="card">
              <h3>价差 z-score（±2σ 带）</h3>
              <LineChart series={[
                { data: zLine, color: "#ef5350", lineWidth: 2 },
                { data: zUp, color: "#888", lineWidth: 1 },
                { data: zDn, color: "#888", lineWidth: 1 },
              ]} height={200} />
              <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                触及 +2 = 做空 A / 做多 B，触及 -2 = 反之；回归 0 时平仓。带越窄、回归越快 = 越好的配对。
              </div>
            </div>

            <div className="card">
              <h3>归一化价格 · {pair.a}（红）vs {pair.b}（蓝），均起点 = 1</h3>
              <LineChart series={[
                { data: priceA, color: "#ef5350", lineWidth: 2 },
                { data: priceB, color: "#4f93e7", lineWidth: 1.5 },
              ]} height={200} />
              <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                视觉上「同涨同跌」可能相关很高，但只要价差不平稳（非协整），统计套利就会亏——相关≠协整的直观体现。
              </div>
            </div>

            <div className="card">
              <h3>{a} 的最佳协整伙伴 Top 5（ADF t 最负，点击切换 B）</h3>
              {topCoint.map((r) => (
                <div key={r.symbol} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", cursor: "pointer" }}
                  onClick={() => changeB(r.symbol)}>
                  <span><b>{r.symbol}</b> <span className="muted" style={{ fontSize: 11 }}>
                    {r.name} · 半衰期 {hlLabel(r.halflife)} · 相关 {fixed3(r.corr)}</span></span>
                  <span className={tTone(r.tstat)}>t {signed(r.tstat)}</span>
                </div>
              ))}
            </div>

            <div className="card">
              <h3>{a} 的全部协整伙伴排名 · 按 ADF t 升序（rank 1 = 最强协整）</h3>
              <div className="scroll" style={{ maxHeight: 460 }}>
                <table className="data">
                  <thead><tr>
                    <th onClick={() => toggleSort("rank")}>#{arrow("rank")}</th>
                    <th onClick={() => toggleSort("symbol")}>伙伴{arrow("symbol")}</th>
                    <th onClick={() => toggleSort("name")}>名称{arrow("name")}</th>
                    <th onClick={() => toggleSort("tstat")}>ADF t{arrow("tstat")}</th>
                    <th onClick={() => toggleSort("halflife")}>半衰期{arrow("halflife")}</th>
                    <th onClick={() => toggleSort("corr")}>收益相关{arrow("corr")}</th>
                    <th onClick={() => toggleSort("beta")}>对冲β{arrow("beta")}</th>
                    <th onClick={() => toggleSort("spread_z")}>z-score{arrow("spread_z")}</th>
                    <th onClick={() => toggleSort("n")}>样本{arrow("n")}</th>
                  </tr></thead>
                  <tbody>
                    {sortedPartners.map((r) => (
                      <tr key={r.symbol} style={{ cursor: "pointer" }} onClick={() => changeB(r.symbol)}>
                        <td className="muted">{r.rank}</td>
                        <td><b>{r.symbol}</b></td>
                        <td className="muted">{r.name}</td>
                        <td className={tTone(r.tstat)}>{signed(r.tstat)}</td>
                        <td className="muted">{hlLabel(r.halflife)}</td>
                        <td className="muted">{fixed3(r.corr)}</td>
                        <td className="muted">{signed(r.beta, 3)}</td>
                        <td className={zTone(r.spread_z)}>{signed(r.spread_z)}</td>
                        <td className="muted">{r.n}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>
    );
  }

  // ---------------------------------------------------------- 扫描视图 ----
  return (
    <div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        配对交易 / 协整扫描。回答「<b>两只股票对冲后的价差是否平稳（均值回归）</b>」。
        后端在价格水平上拟合 P<sub>a</sub>=α+β·P<sub>b</sub>，残差即价差，再做 ADF 检验；
        预筛条件 |收益相关| ≥ {scan?.min_corr ?? 0.30}（协整几乎必然伴随高收益相关）。
        <b>相关系数（收益层面）≠ 协整（价格层面）</b>。点击任意一行加载该配对的价差 / z-score 图与检验细节。
      </div>

      {scanErr && <div className="card neg" style={{ fontSize: 13 }}>协整扫描加载失败：{scanErr}</div>}
      {!scan && !scanErr && <div className="spinner">扫描全池协整配对中…</div>}

      {scan && (
        <>
          <div className="stats" style={{ flexWrap: "wrap" }}>
            <Stat label="池内标的" value={scan.n_names} sub={`候选对 ${scan.n_pairs_candidates}`} />
            <Stat label="进入 ADF 配对" value={scan.n_pairs_tested} sub={`按 |corr| 降序截断（上限 ${scan.max_adf_pairs}）`} />
            <Stat label="展示 Top" value={scan.pairs?.length ?? 0} sub="按 ADF t 升序（最协整在前）" />
          </div>

          <div className="card">
            <h3>全池协整配对扫描 Top（点击行查看价差详情）</h3>
            <div className="scroll" style={{ maxHeight: 560 }}>
              <table className="data">
                <thead><tr>
                  <th onClick={() => toggleSort("rank")}>#{arrow("rank")}</th>
                  <th onClick={() => toggleSort("symbol_a")}>标的 A{arrow("symbol_a")}</th>
                  <th>名称 A</th>
                  <th onClick={() => toggleSort("symbol_b")}>标的 B{arrow("symbol_b")}</th>
                  <th>名称 B</th>
                  <th onClick={() => toggleSort("tstat")}>ADF t{arrow("tstat")}</th>
                  <th onClick={() => toggleSort("halflife")}>半衰期{arrow("halflife")}</th>
                  <th onClick={() => toggleSort("beta")}>对冲β{arrow("beta")}</th>
                  <th onClick={() => toggleSort("corr")}>收益相关{arrow("corr")}</th>
                  <th onClick={() => toggleSort("spread_z")}>z-score{arrow("spread_z")}</th>
                  <th onClick={() => toggleSort("n")}>样本{arrow("n")}</th>
                </tr></thead>
                <tbody>
                  {sortRows(scan.pairs || [], sortKey, sortDir).map((r) => (
                    <tr key={`${r.symbol_a}|${r.symbol_b}`} style={{ cursor: "pointer" }} onClick={() => openPair(r)}>
                      <td className="muted">{r.rank}</td>
                      <td><b>{r.symbol_a}</b></td>
                      <td className="muted">{r.name_a}</td>
                      <td><b>{r.symbol_b}</b></td>
                      <td className="muted">{r.name_b}</td>
                      <td className={tTone(r.tstat)}>{signed(r.tstat)}</td>
                      <td className="muted">{hlLabel(r.halflife)}</td>
                      <td className="muted">{signed(r.beta, 3)}</td>
                      <td className="muted">{fixed3(r.corr)}</td>
                      <td className={zTone(r.spread_z)}>{signed(r.spread_z)}</td>
                      <td className="muted">{r.n}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
              ADF t ≤ -3.37 视为协整（价差平稳、可统计套利）；-3.37 ~ -2.86 边缘；&gt; -2.86 非协整。
            </div>
          </div>
        </>
      )}
    </div>
  );
}
