// 尾部风险 Tab：收益分布形态（偏度/超额峰度）+ 历史 VaR/CVaR + Sortino。
// 数据来自 /risk/tailrisk?window=（后端逐票全历史日收益算标准化矩与分位损失，
// 市场聚合为等权截面日收益；损失一律为正数幅度，VaR 3% = 0.03）。
// 后端按 CVaR95 降序给出全池排名，本 Tab 只做展示与客户端排序。
import { useEffect, useMemo, useState } from "react";
import LineChart from "../LineChart.jsx";
import {
  riskFetch, toLine, num, signed, pct1, sortRows,
} from "../../../lib/us/riskUtils";

const WINDOW_OPTS = [42, 63, 126];

// 体制 = 偏度（左偏/对称/右偏）× 峰度（薄尾/近正态/厚尾）。
// 左偏+厚尾 = 偶发崩盘（风险被波动率低估）；对称+薄尾 = 平稳。
function regime(stats) {
  if (!stats) return { key: "n/a", label: "—", tone: "", desc: "无数据" };
  const sk = num(stats.skew);
  const ek = num(stats.excess_kurt);
  if (sk == null || ek == null)
    return { key: "neutral", label: "中性", tone: "", desc: "分布形态数据不足。" };
  const skew = sk < -0.3 ? { key: "left", label: "左偏", tone: "neg" }
    : sk > 0.3 ? { key: "right", label: "右偏", tone: "pos" }
    : { key: "sym", label: "对称", tone: "" };
  const kurt = ek < 1 ? { key: "thin", label: "薄尾", tone: "pos" }
    : ek < 3 ? { key: "normal", label: "近正态", tone: "" }
    : { key: "fat", label: "厚尾", tone: "neg" };
  const rank = { neg: 3, pos: 1, "": 0 };
  const tone = rank[skew.tone] >= rank[kurt.tone] ? skew.tone : kurt.tone;
  const skWord = skew.key === "left" ? "左偏·偶发大崩盘（小赚多、大亏狠）"
    : skew.key === "right" ? "右偏·偶发大涨（彩票型）" : "涨跌基本对称";
  const ekWord = kurt.key === "fat" ? "厚尾·极端日远多于正态预测（风险常被波动率低估）"
    : kurt.key === "thin" ? "薄尾·极端日少于正态" : "近正态·极端日与正态相当";
  const desc = `偏度 ${signed(sk)}（${skWord}）；超额峰度 ${signed(ek, 1)}（${ekWord}）。`;
  return { key: `${skew.key}_${kurt.key}`, label: `${skew.label} · ${kurt.label}`, tone, desc };
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

function ChartCard({ title, desc, children }) {
  return (
    <div className="card">
      <h3 style={{ marginBottom: 4 }}>{title}</h3>
      {children}
      {desc && <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>{desc}</div>}
    </div>
  );
}

const tailTone = (sk) => (sk == null ? "" : sk < -0.3 ? "neg" : sk > 0.3 ? "pos" : "");
const kurtTone = (ek) => (ek == null ? "" : ek >= 3 ? "neg" : ek < 1 ? "pos" : "");
const sortinoTone = (v) => (num(v) == null ? "" : v > 1 ? "pos" : v < 0 ? "neg" : "");

export default function TailRiskTab() {
  const [data, setData] = useState(null);
  const [window_, setWindow] = useState(63);
  const [err, setErr] = useState("");
  const [sortKey, setSortKey] = useState("rank");
  const [sortDir, setSortDir] = useState("asc");

  useEffect(() => {
    let alive = true;
    setData(null); setErr("");
    riskFetch("/risk/tailrisk", { window: window_ })
      .then((d) => { if (alive) setData(d); })
      .catch((e) => { if (alive) setErr(e.message || String(e)); });
    return () => { alive = false; };
  }, [window_]);

  const reg = useMemo(() => regime(data), [data]);
  const ranking = data?.ranking || [];
  const sorted = useMemo(() => sortRows(ranking, sortKey, sortDir), [ranking, sortKey, sortDir]);

  if (err) return <div className="card neg" style={{ fontSize: 13 }}>尾部风险数据加载失败：{err}</div>;
  if (!data) return <div className="spinner">加载尾部风险数据中…</div>;

  const mktVar = toLine(data.var95_series);
  const mktCvar = toLine(data.cvar95_series);
  const mktSkew = toLine(data.skew_series);
  const mktKurt = toLine(data.kurt_series);
  const highTail = ranking.slice(0, 5);
  const lowTail = ranking.slice(-5).reverse();

  const toggleSort = (k) => {
    if (k === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(k); setSortDir(k === "symbol" || k === "name" ? "asc" : "desc"); }
  };
  const arrow = (k) => (k === sortKey ? (sortDir === "asc" ? " ▲" : " ▼") : "");

  return (
    <div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        尾部风险与收益分布（{data.n_stocks} 只标的，{data.n_days} 个交易日，滚动 {data.window} 日）。
        回答「<b>收益分布的尾部有多厚、偏哪边</b>」——两只波动率相同的股票，尾部可以截然不同：
        左偏+厚尾=偶发崩盘（风险被波动率低估）；对称+薄尾=平稳。CVaR（预期缺口）恒 ≥ VaR。
      </div>

      <div className={`card ${reg.tone}`} style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        <div style={{ fontSize: 26, fontWeight: 700 }} className={reg.tone}>{reg.label}</div>
        <div className="muted" style={{ flex: 1, minWidth: 260, fontSize: 12 }}>{reg.desc}</div>
      </div>

      <div className="stats" style={{ flexWrap: "wrap" }}>
        <Stat label="偏度" value={signed(data.skew)} tone={tailTone(data.skew)} sub="第三标准化矩" />
        <Stat label="超额峰度" value={signed(data.excess_kurt, 1)} tone={kurtTone(data.excess_kurt)} sub="第四矩−3，厚尾度" />
        <Stat label="95% VaR" value={pct1(data.var95)} tone="neg" sub="5% 分位日损失" />
        <Stat label="95% CVaR" value={pct1(data.cvar95)} tone="neg" sub="最坏5%日均损失" />
        <Stat label="最大单日跌幅" value={pct1(data.max_loss)} tone="neg" sub="市场等权历史最差" />
        <Stat label="市场 Sortino" value={signed(data.sortino)} tone={sortinoTone(data.sortino)} sub="年化收益÷下行偏差" />
      </div>

      <div className="card">
        <h3>
          市场滚动 95% VaR / CVaR（日度损失） · 窗口
          <select value={window_} onChange={(e) => setWindow(+e.target.value)} style={{ marginLeft: 8 }}>
            {WINDOW_OPTS.map((w) => <option key={w} value={w}>{w} 日</option>)}
          </select>
        </h3>
        <LineChart series={[
          { data: mktCvar, color: "#ef5350", lineWidth: 2 },
          { data: mktVar, color: "#ff9800", lineWidth: 1.5 },
        ]} height={200} />
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          滚动窗口的 5% 分位损失（VaR，橙）与最坏 5% 日均损失（CVaR，红）。CVaR 恒 ≥ VaR——尾部均值；
          市场 CVaR {pct1(data.cvar95)} &gt; VaR {pct1(data.var95)} 说明尾部比正态厚。
        </div>
      </div>

      <div className="card">
        <h3>市场滚动偏度 / 超额峰度（窗口 {data.window} 日）</h3>
        <LineChart series={[
          { data: mktKurt, color: "#7e57c2", lineWidth: 2 },
          { data: mktSkew, color: "#42a5f5", lineWidth: 1.5 },
        ]} height={200} />
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          蓝=偏度（左偏&lt;0=崩盘倾向）、紫=超额峰度（&gt;0=厚尾）。峰度长期 &gt;0 = 股票收益恒是厚尾分布，
          正态假设会系统性低估极端日。
        </div>
      </div>

      <div className="card">
        <h3>最高 / 最低尾部风险（按 95% CVaR，后端排名）</h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
          <div>
            <div className="neg" style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>▲ 崩盘倾向 Top 5（CVaR 最高）</div>
            {highTail.map((r) => (
              <div key={r.symbol} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0" }}>
                <span><b>{r.symbol}</b> <span className="muted" style={{ fontSize: 11 }}>{r.name}</span></span>
                <span className="neg">{pct1(r.cvar95)}</span>
              </div>
            ))}
          </div>
          <div>
            <div className="pos" style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>▼ 尾部最薄 Bottom 5（CVaR 最低）</div>
            {lowTail.map((r) => (
              <div key={r.symbol} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0" }}>
                <span><b>{r.symbol}</b> <span className="muted" style={{ fontSize: 11 }}>{r.name}</span></span>
                <span className="pos">{pct1(r.cvar95)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card">
        <h3>全池尾部风险排名 · 按 95% CVaR（预期缺口）降序 · 窗口可调</h3>
        <div className="scroll" style={{ maxHeight: 460 }}>
          <table className="data">
            <thead><tr>
              <th onClick={() => toggleSort("rank")}>#{arrow("rank")}</th>
              <th onClick={() => toggleSort("symbol")}>代码{arrow("symbol")}</th>
              <th onClick={() => toggleSort("name")}>名称{arrow("name")}</th>
              <th onClick={() => toggleSort("skew")}>偏度{arrow("skew")}</th>
              <th onClick={() => toggleSort("excess_kurt")}>超额峰度{arrow("excess_kurt")}</th>
              <th onClick={() => toggleSort("var95")}>95% VaR{arrow("var95")}</th>
              <th onClick={() => toggleSort("cvar95")}>95% CVaR{arrow("cvar95")}</th>
              <th onClick={() => toggleSort("max_loss")}>最大跌幅{arrow("max_loss")}</th>
              <th onClick={() => toggleSort("downside_dev")}>下行偏差{arrow("downside_dev")}</th>
              <th onClick={() => toggleSort("sortino")}>Sortino{arrow("sortino")}</th>
            </tr></thead>
            <tbody>
              {sorted.map((r) => (
                <tr key={r.symbol}>
                  <td className="muted">{r.rank}</td>
                  <td><b>{r.symbol}</b></td>
                  <td className="muted">{r.name}</td>
                  <td className={tailTone(r.skew)}>{signed(r.skew)}</td>
                  <td className={kurtTone(r.excess_kurt)}>{signed(r.excess_kurt, 1)}</td>
                  <td className="neg">{pct1(r.var95)}</td>
                  <td className="neg">{pct1(r.cvar95)}</td>
                  <td className="neg">{pct1(r.max_loss)}</td>
                  <td>{pct1(r.downside_dev)}</td>
                  <td className={sortinoTone(r.sortino)}>{signed(r.sortino)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
