// 基本面轨迹 tab —— /fund/trajectory（无 symbol=全票最新季截面；有 symbol=逐季明细）。
// 展示口径：体制横幅（增长×盈利）+ 最新季指标卡 + 逐季营收/净利/毛利/营业利/EPS/
// 利润率/增速轨迹 + 截面分位（vs 市场 P25/P50/P75）+ Top5 榜 + 全票可排序排名表。
// 注意：本实现 symbol_info 的 metrics/margins/growth 直接在顶层（后端已展平）。
import { useEffect, useMemo, useState } from "react";
import { fetchUsAnalytics } from "../../../api/usAnalytics";
import LineChart from "../LineChart.jsx";
import { Stat, ChartCard, RegimeBanner, useSymbols, SymbolSelect } from "./shared.jsx";
import { toLine, num, sortRows } from "../../../lib/us/analyticsFmt";

const METRICS = {
  revenue: { label: "营收", color: "#42a5f5" },
  rev_yoy: { label: "营收 YoY", color: "#26a69a" },
  rev_qoq: { label: "营收 QoQ", color: "#66bb6a" },
  gross_margin: { label: "毛利率", color: "#ab47bc" },
  operating_margin: { label: "营业利润率", color: "#7e57c2" },
  net_margin: { label: "净利率", color: "#ec407a" },
  diluted_eps: { label: "稀释 EPS", color: "#ff9800" },
  eps_yoy: { label: "EPS YoY", color: "#8d6e63" },
};

// 美元自适应格式：按量级选 T/B/M/K。
export const dollars = (v) => {
  const x = num(v);
  if (x == null) return "—";
  const sign = x < 0 ? "-" : "", a = Math.abs(x);
  if (a >= 1e12) return sign + "$" + (a / 1e12).toFixed(2) + "T";
  if (a >= 1e9) return sign + "$" + (a / 1e9).toFixed(2) + "B";
  if (a >= 1e6) return sign + "$" + (a / 1e6).toFixed(2) + "M";
  if (a >= 1e3) return sign + "$" + (a / 1e3).toFixed(2) + "K";
  return sign + "$" + a.toFixed(0);
};
const epsFmt = (v) => (num(v) == null ? "—" : "$" + num(v).toFixed(2));
const pct1 = (v) => (num(v) == null ? "—" : (v * 100).toFixed(1) + "%");
const signedPct1 = (v) => (num(v) == null ? "—" : (v >= 0 ? "+" : "") + (v * 100).toFixed(1) + "%");

// 体制 = 最新季营收 YoY(增长) × 净利率(盈利能力) 合成判读。
export function regime(info) {
  if (!info) return { key: "na", label: "—", tone: "", desc: "无数据" };
  const g = num(info.rev_yoy);
  const m = num(info.net_margin);
  if (g == null && m == null)
    return { key: "neutral", label: "中性", tone: "muted", desc: "增长/盈利数据不足。" };

  const growth = g == null ? { key: "na" }
    : g > 0.25 ? { key: "high", label: "高增长", tone: "pos" }
    : g >= 0 ? { key: "mid", label: "温和增长", tone: "" }
    : { key: "neg", label: "营收下滑", tone: "warn" };
  const profit = m == null ? { key: "na" }
    : m > 0.15 ? { key: "high", label: "高利润率", tone: "pos" }
    : m >= 0 ? { key: "mid", label: "微利", tone: "" }
    : { key: "neg", label: "亏损", tone: "warn" };

  let label, tone, kind;
  if (growth.key === "high" && profit.key === "high") { kind = "growth_quality"; label = "成长·高利"; tone = "pos"; }
  else if (growth.key !== "neg" && profit.key === "high") { kind = "cashcow"; label = "现金牛·高利低增长"; tone = ""; }
  else if (growth.key === "high" && profit.key !== "high") { kind = "growth_unprofitable"; label = "高增长·未盈利"; tone = "warn"; }
  else if (growth.key === "neg" && profit.key === "neg") { kind = "distress"; label = "困境·下滑亏损"; tone = "warn"; }
  else if (profit.key === "neg") { kind = "loss"; label = "亏损"; tone = "warn"; }
  else if (growth.key === "neg") { kind = "shrinking"; label = "营收下滑"; tone = "warn"; }
  else { kind = "average"; label = "增长·盈利均衡"; tone = ""; }

  const gTxt = g == null ? "未知" : (g * 100).toFixed(1) + "%";
  const mTxt = m == null ? "未知" : (m * 100).toFixed(1) + "%";
  const kindWord = {
    growth_quality: "高增长叠加高利润率——量价齐升的优质成长",
    cashcow: "利润率厚但增长温和——典型成熟现金牛",
    growth_unprofitable: "营收高增长但仍未盈利——烧钱换规模",
    distress: "营收下滑且亏损——基本面承压",
    loss: "处于亏损状态",
    shrinking: "营收同比下滑",
    average: "增长与盈利处于市场中性水平",
  }[kind];
  return { key: kind, label, tone, desc: `最新季营收 YoY ${gTxt}、净利率 ${mTxt}（${kindWord}）。财季深度有限，趋势方向参考为主。` };
}

// 截面位置：个股最新季值 vs 市场分位。
function Place({ label, symVal, q, fmt }) {
  const v = num(symVal);
  let pos = "—";
  if (v != null && q && q["0.5"] != null)
    pos = v >= (q["0.75"] ?? Infinity) ? "P75 上方" : v >= q["0.5"] ? "P50–P75"
      : v >= (q["0.25"] ?? -Infinity) ? "P25–P50" : "P25 下方";
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", fontSize: 12 }}>
      <span className="muted">{label}</span>
      <span style={{ fontVariantNumeric: "tabular-nums" }}>
        <b>{fmt(v)}</b>
        <span className="muted" style={{ fontSize: 10 }}>
          {" "}vs P25 {fmt(q?.["0.25"])} / 中位 {fmt(q?.["0.5"])} / P75 {fmt(q?.["0.75"])}
        </span>
        <span className="muted" style={{ marginLeft: 6 }}>[{pos}]</span>
      </span>
    </div>
  );
}

export default function FundTrajectoryTab() {
  const [symbol, setSymbol] = useState("AAPL");
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [sortKey, setSortKey] = useState("rev_yoy");
  const [sortDir, setSortDir] = useState("desc");
  const symbols = useSymbols();

  useEffect(() => {
    let on = true;
    setErr("");
    fetchUsAnalytics("/fund/trajectory", { symbol })
      .then((d) => { if (on) setData(d); })
      .catch((e) => { if (on) setErr(String(e?.message || e)); });
    return () => { on = false; };
  }, [symbol]);

  const ranking = data?.ranking || [];
  const si = data?.symbol_info || null;
  const mkt = data?.market || {};
  const reg = useMemo(() => regime(si?.latest), [si]);
  const sorted = useMemo(() => sortRows(ranking, sortKey, sortDir), [ranking, sortKey, sortDir]);

  const toggleSort = (k) => {
    if (k === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(k); setSortDir(k === "symbol" || k === "name" || k === "latest_period" ? "asc" : "desc"); }
  };
  const arrow = (k) => (k === sortKey ? (sortDir === "asc" ? " ▲" : " ▼") : "");

  if (err) return <div className="spinner">基本面轨迹加载失败：{err}</div>;
  if (!data) return <div className="spinner">加载基本面轨迹数据中…</div>;

  const hasSym = !!si;
  const latest = si?.latest || {};
  const metrics = si?.metrics || {};
  const margins = si?.margins || {};
  const growth = si?.growth || {};
  const scaleB = (arr) => toLine(arr).map((p) => ({ time: p.time, value: p.value / 1e9 }));
  const scalePct = (arr) => toLine(arr).map((p) => ({ time: p.time, value: p.value * 100 }));

  return (
    <div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        基本面轨迹 / 逐季财务（{data.n_stocks} 只标的，每家 {data.quarter_depth?.min}–{data.quarter_depth?.max} 个财季，
        {data.period_span}）· 个股
        <span style={{ marginLeft: 8 }}><SymbolSelect symbols={symbols} value={symbol} onChange={setSymbol} /></span>。
        回答「营收/盈利/EPS/利润率随财季如何演变、这家公司在截面里处在哪」。
        <br />⚠️ {data.data_window_note}
      </div>

      <RegimeBanner label={reg.label} tone={reg.tone} desc={reg.desc} />

      {/* 选中个股最新季指标 */}
      {hasSym ? (
        <div className="stats">
          <Stat label="最新季营收" value={dollars(latest.revenue)} sub={latest.latest_period} />
          <Stat label="营收 YoY" value={signedPct1(latest.rev_yoy)}
            tone={num(latest.rev_yoy) >= 0 ? "pos" : "neg"} sub="同比上年同期" />
          <Stat label="营收 QoQ" value={signedPct1(latest.rev_qoq)}
            tone={num(latest.rev_qoq) >= 0 ? "pos" : "neg"} sub="环比上一财季" />
          <Stat label="毛利率" value={pct1(latest.gross_margin)} sub="毛利/营收" />
          <Stat label="净利率" value={pct1(latest.net_margin)}
            tone={num(latest.net_margin) < 0 ? "neg" : ""} sub="净利润/营收" />
          <Stat label="稀释 EPS" value={epsFmt(latest.diluted_eps)}
            tone={num(latest.diluted_eps) < 0 ? "neg" : ""} sub={`YoY ${signedPct1(latest.eps_yoy)}`} />
          <Stat label="财季数 / 排名" value={`${latest.n_quarters} / #${latest.rank}`} sub={`按营收 YoY · 共 ${ranking.length} 只`} />
        </div>
      ) : (
        <div className="card muted">该标的无季度财务数据（quarterly 段无记录）。</div>
      )}

      {/* 逐季轨迹图 */}
      {hasSym && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))", gap: 12, marginTop: 12 }}>
          <ChartCard title="营收 · 净利轨迹（$十亿）"
            desc="逐季总收入(蓝)与净利润(青)。两线间距即成本/费用消耗；净利为负时线下穿零。">
            <LineChart series={[
              { data: scaleB(metrics.total_revenue), color: METRICS.revenue.color, lineWidth: 2 },
              { data: scaleB(metrics.net_income), color: "#26a69a", lineWidth: 2 },
            ]} height={200} />
          </ChartCard>
          <ChartCard title="毛利 · 营业利润轨迹（$十亿）"
            desc="逐季毛利(紫)与营业利润(深紫)。毛利−营业利润=期间费用(SG&A/R&D)规模。">
            <LineChart series={[
              { data: scaleB(metrics.gross_profit), color: METRICS.gross_margin.color, lineWidth: 2 },
              { data: scaleB(metrics.operating_income), color: METRICS.operating_margin.color, lineWidth: 2 },
            ]} height={200} />
          </ChartCard>
          <ChartCard title="利润率走势（%）"
            desc="逐季毛利率(紫)/营业利润率(深紫)/净利率(粉)。越高越好；负值=亏损季（如实呈现）。">
            <LineChart series={[
              { data: scalePct(margins.gross), color: METRICS.gross_margin.color, lineWidth: 1.5 },
              { data: scalePct(margins.operating), color: METRICS.operating_margin.color, lineWidth: 1.5 },
              { data: scalePct(margins.net), color: METRICS.net_margin.color, lineWidth: 1.5 },
            ]} height={200} />
          </ChartCard>
          <ChartCard title="稀释 EPS 轨迹（$）"
            desc="逐季摊薄每股收益(橙)。负值=每股亏损；YoY 增速见增速图与指标卡。">
            <LineChart data={toLine(metrics.diluted_eps)} color={METRICS.diluted_eps.color} height={200} />
          </ChartCard>
          <ChartCard title="营收增速（YoY / QoQ，%）"
            desc="青=同比（仅存在上年同期时可算，通常最近 1-2 季）、绿=环比。正值=增长。">
            <LineChart series={[
              { data: scalePct(growth.rev_yoy), color: METRICS.rev_yoy.color, lineWidth: 2 },
              { data: scalePct(growth.rev_qoq), color: METRICS.rev_qoq.color, lineWidth: 1.5 },
            ]} height={180} />
          </ChartCard>
          <ChartCard title="EPS 增速（YoY / QoQ，%）"
            desc="盈利的同比/环比增速。窗口限制下 YoY 历史很短，方向参考为主。">
            <LineChart series={[
              { data: scalePct(growth.eps_yoy), color: METRICS.eps_yoy.color, lineWidth: 2 },
              { data: scalePct(growth.eps_qoq), color: METRICS.rev_qoq.color, lineWidth: 1.5 },
            ]} height={180} />
          </ChartCard>
        </div>
      )}

      {/* 截面位置 */}
      {hasSym && (
        <div className="card" style={{ marginTop: 12 }}>
          <h3 style={{ marginBottom: 6 }}>截面位置 · {si.symbol} 在 {ranking.length} 只中的分位</h3>
          <Place label="营收 YoY" symVal={latest.rev_yoy} q={mkt.rev_yoy} fmt={(v) => (num(v) == null ? "—" : (v >= 0 ? "+" : "") + (v * 100).toFixed(1) + "%")} />
          <Place label="毛利率" symVal={latest.gross_margin} q={mkt.gross_margin} fmt={(v) => (num(v) == null ? "—" : (v * 100).toFixed(1) + "%")} />
          <Place label="净利率" symVal={latest.net_margin} q={mkt.net_margin} fmt={(v) => (num(v) == null ? "—" : (v * 100).toFixed(1) + "%")} />
        </div>
      )}

      {/* Top5 榜 */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12, marginTop: 12 }}>
        <div className="card">
          <h3 style={{ marginBottom: 6 }}>最高营收增速 Top 5（YoY）</h3>
          {[...ranking].filter((r) => r.rev_yoy != null)
            .sort((a, b) => b.rev_yoy - a.rev_yoy).slice(0, 5)
            .map((r) => (
              <div key={r.symbol} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", cursor: "pointer" }}
                onClick={() => setSymbol(r.symbol)}>
                <span><b>{r.symbol}</b> <span className="muted" style={{ fontSize: 11 }}>{r.name}</span></span>
                <span className="pos">{(r.rev_yoy >= 0 ? "+" : "") + (r.rev_yoy * 100).toFixed(1) + "%"}</span>
              </div>
            ))}
        </div>
        <div className="card">
          <h3 style={{ marginBottom: 6 }}>最高净利率 Top 5</h3>
          {[...ranking].filter((r) => r.net_margin != null)
            .sort((a, b) => b.net_margin - a.net_margin).slice(0, 5)
            .map((r) => (
              <div key={r.symbol} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", cursor: "pointer" }}
                onClick={() => setSymbol(r.symbol)}>
                <span><b>{r.symbol}</b> <span className="muted" style={{ fontSize: 11 }}>{r.name}</span></span>
                <span className="pos">{(r.net_margin * 100).toFixed(1) + "%"}</span>
              </div>
            ))}
        </div>
      </div>

      {/* 全票排名表 */}
      <div className="card" style={{ marginTop: 12 }}>
        <h3>全市场基本面排名 · 最新财季 · 列可排序（点行切换个股）</h3>
        <div className="muted" style={{ fontSize: 11, marginBottom: 6 }}>
          默认按营收 YoY 降序（无上年同期者排末尾）。最新季为各公司自有财季期末日。
        </div>
        <div className="scroll" style={{ maxHeight: 460 }}>
          <table className="data">
            <thead><tr>
              <th onClick={() => toggleSort("rank")}>#{arrow("rank")}</th>
              <th onClick={() => toggleSort("symbol")}>代码{arrow("symbol")}</th>
              <th onClick={() => toggleSort("name")}>名称{arrow("name")}</th>
              <th onClick={() => toggleSort("latest_period")}>最新季{arrow("latest_period")}</th>
              <th onClick={() => toggleSort("revenue")}>营收{arrow("revenue")}</th>
              <th onClick={() => toggleSort("rev_yoy")}>营收YoY{arrow("rev_yoy")}</th>
              <th onClick={() => toggleSort("rev_qoq")}>营收QoQ{arrow("rev_qoq")}</th>
              <th onClick={() => toggleSort("gross_margin")}>毛利率{arrow("gross_margin")}</th>
              <th onClick={() => toggleSort("operating_margin")}>营业利润率{arrow("operating_margin")}</th>
              <th onClick={() => toggleSort("net_margin")}>净利率{arrow("net_margin")}</th>
              <th onClick={() => toggleSort("diluted_eps")}>EPS{arrow("diluted_eps")}</th>
              <th onClick={() => toggleSort("n_quarters")}>季数{arrow("n_quarters")}</th>
            </tr></thead>
            <tbody>
              {sorted.map((r) => (
                <tr key={r.symbol} style={{ cursor: "pointer" }} onClick={() => setSymbol(r.symbol)}>
                  <td className="muted">{r.rank}</td>
                  <td><b>{r.symbol}</b></td>
                  <td className="muted">{r.name}</td>
                  <td className="muted">{r.latest_period}</td>
                  <td>{dollars(r.revenue)}</td>
                  <td className={num(r.rev_yoy) < 0 ? "neg" : ""}>
                    {r.rev_yoy == null ? "—" : (r.rev_yoy >= 0 ? "+" : "") + (r.rev_yoy * 100).toFixed(1) + "%"}
                  </td>
                  <td className={num(r.rev_qoq) < 0 ? "neg" : ""}>
                    {r.rev_qoq == null ? "—" : (r.rev_qoq >= 0 ? "+" : "") + (r.rev_qoq * 100).toFixed(1) + "%"}
                  </td>
                  <td>{r.gross_margin == null ? "—" : (r.gross_margin * 100).toFixed(1) + "%"}</td>
                  <td>{r.operating_margin == null ? "—" : (r.operating_margin * 100).toFixed(1) + "%"}</td>
                  <td className={num(r.net_margin) < 0 ? "neg" : ""}>
                    {r.net_margin == null ? "—" : (r.net_margin * 100).toFixed(1) + "%"}
                  </td>
                  <td className={num(r.diluted_eps) < 0 ? "neg" : ""}>{epsFmt(r.diluted_eps)}</td>
                  <td className="muted">{r.n_quarters}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
