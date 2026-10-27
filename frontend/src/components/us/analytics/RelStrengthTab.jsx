// 相对强度排名 tab —— /market/relstrength?period=&ma_trend=。
// 口径移植自开源参考实现的 RelStrengthPage：等权市场指数为基准的相对收益排名。
// 适配：后端路由未透传 symbol（symbol_info 恒空），个股相对强度线改为「从排名行取汇总卡」。
import { useEffect, useMemo, useState } from "react";
import { analyticsApiFor } from "../../../api/usAnalytics";
import LineChart from "../LineChart.jsx";
import { Stat, ChartCard, RegimeBanner } from "./shared.jsx";
import {
  toLine, sortRows, signedPct1, pct0, price2, num,
} from "../../../lib/us/analyticsFmt";

const PERIOD_OPTS = [20, 60, 120];

const trendLabel = (t) =>
  t === "improving" ? { label: "▲ 改善", tone: "pos" }
  : t === "deteriorating" ? { label: "▼ 走弱", tone: "neg" }
  : { label: "—", tone: "" };

// 相对强度体制：市场等权涨幅(m) × 跑赢占比(p)——区分「广泛领涨」与「集中领涨」。
function regime(stats) {
  if (!stats) return { key: "n/a", label: "—", tone: "", desc: "无数据" };
  const m = num(stats.mkt_ret_period);
  const p = num(stats.pct_outperformers);
  if (m == null || p == null)
    return { key: "neutral", label: "中性", tone: "", desc: "相对强度数据不足。" };
  if (m >= 0 && p >= 0.55)
    return { key: "broad_leader", label: "广泛领涨", tone: "pos",
      desc: `等权指数 +${(m * 100).toFixed(1)}% 且 ${(p * 100).toFixed(0)}% 标的跑赢——上涨由多数标的驱动，广度健康。` };
  if (m >= 0 && p < 0.40)
    return { key: "narrow_leader", label: "集中领涨·警惕", tone: "warn",
      desc: `指数 +${(m * 100).toFixed(1)}% 但仅 ${(p * 100).toFixed(0)}% 标的跑赢——少数权重股拉升，广度背离，常见于上涨后期。` };
  if (m < 0 && p >= 0.55)
    return { key: "broad_hold", label: "集中抗跌", tone: "warn",
      desc: `指数 ${(m * 100).toFixed(1)}% 但 ${(p * 100).toFixed(0)}% 标的跑赢——多数标的抗跌，潜在底部背离。` };
  if (m < 0 && p < 0.40)
    return { key: "broad_decline", label: "广泛回落", tone: "neg",
      desc: `指数 ${(m * 100).toFixed(1)}% 且仅 ${(p * 100).toFixed(0)}% 标的跑赢——系统性下行，避险为主。` };
  return { key: "mixed", label: "分化", tone: "", desc: "涨跌分化，领涨结构无明确单边体制。" };
}

export default function RelStrengthTab({ mk = "us" }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [period, setPeriod] = useState(60);
  const [symbol, setSymbol] = useState("");
  const [sortKey, setSortKey] = useState("rank");
  const [sortDir, setSortDir] = useState("asc");

  useEffect(() => {
    let on = true;
    setErr("");
    analyticsApiFor(mk).fetch("/market/relstrength", { period, ma_trend: 20 })
      .then((d) => { if (on) setData(d); })
      .catch((e) => { if (on) setErr(String(e?.message || e)); });
    return () => { on = false; };
  }, [period]);

  const reg = useMemo(() => regime(data), [data]);
  const ranking = useMemo(() => data?.ranking || [], [data]);
  useEffect(() => {
    if (ranking.length && !ranking.some((r) => r.symbol === symbol)) setSymbol(ranking[0].symbol);
  }, [ranking, symbol]);

  const sorted = useMemo(() => sortRows(ranking, sortKey, sortDir), [ranking, sortKey, sortDir]);
  // 所选标的的汇总（symbol_info 不可用时从排名行取）。
  const symRow = useMemo(() => ranking.find((r) => r.symbol === symbol) || null, [ranking, symbol]);

  if (err) return <div className="spinner">相对强度数据加载失败：{err}</div>;
  if (!data) return <div className="spinner">加载相对强度数据中…</div>;

  const indexLine = toLine(data.index);
  const breadthLine = toLine(data.breadth);
  const leaders = ranking.slice(0, 5);
  const laggards = ranking.slice(-5).reverse();
  const outperform = ranking.filter((r) => (r.rs_ret ?? 0) > 0).length;

  const toggleSort = (k) => {
    if (k === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(k); setSortDir(k === "symbol" || k === "name" ? "asc" : "desc"); }
  };
  const arrow = (k) => (k === sortKey ? (sortDir === "asc" ? " ▲" : " ▼") : "");

  return (
    <div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        相对强度排名（{data.n_stocks} 只标的，{data.n_days} 个交易日）。基准 = <b>标的池等权指数</b>（剔除权重股偏置）。
        回答「<b>剔除大盘 beta 后谁在真正领涨/领跌</b>」——一只涨 5% 但市场涨 10% 的标的，是跑输的。
      </div>

      <RegimeBanner label={reg.label} tone={reg.tone} desc={reg.desc} />

      <div className="stats">
        <Stat label={`市场等权（${period}日）`} value={signedPct1(data.mkt_ret_period)}
          tone={data.mkt_ret_period > 0 ? "pos" : data.mkt_ret_period < 0 ? "neg" : ""} sub="平均股票基准" />
        <Stat label="中位相对收益" value={signedPct1(data.median_rs_ret)}
          tone={data.median_rs_ret > 0 ? "pos" : data.median_rs_ret < 0 ? "neg" : ""} sub="过半标的的强弱" />
        <Stat label="跑赢占比" value={pct0(data.pct_outperformers)}
          tone={data.pct_outperformers >= 0.55 ? "pos" : data.pct_outperformers <= 0.40 ? "neg" : ""} sub="领涨广度" />
        <Stat label="跑赢 / 跑输" value={`${outperform} / ${ranking.length - outperform}`} sub="家数" />
        <Stat label="标的数" value={ranking.length} sub="有完整历史的标的" />
        <Stat label="排名周期" value={`${period} 日`} sub="相对收益回看窗" />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))", gap: 12 }}>
        <ChartCard title="等权市场指数（归一 1.0）"
          desc="标的池日均收益的累计净值（起点=1.0）。剔除权重股偏置后的「平均股票」路径——本页所有相对收益以此为基准。">
          <LineChart data={indexLine} color="#4f93e7" height={200} />
        </ChartCard>

        <ChartCard title={`跑赢占比时序（滚动 ${period} 日相对收益 > 0）`}
          desc="每日有多少比例的标的跑赢等权指数。>55%=广泛领涨；<40%=集中或系统性。领导力广度温度计。">
          <LineChart data={breadthLine} color="#26a69a" height={200} />
        </ChartCard>
      </div>

      {/* 所选标的汇总（从排名行取，路由未透出逐日 RS 线） */}
      <div className="card" style={{ display: "flex", gap: 18, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
        <span style={{ fontSize: 14 }}>个股相对强度</span>
        <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
          {ranking.map((r) => <option key={r.symbol} value={r.symbol}>{r.symbol} — {r.name}</option>)}
        </select>
        {symRow ? (
          <>
            <b style={{ fontSize: 16 }}>{symRow.symbol}</b>
            <span className="muted">{symRow.name}</span>
            <Stat label="相对收益" value={signedPct1(symRow.rs_ret)}
              tone={symRow.rs_ret > 0 ? "pos" : symRow.rs_ret < 0 ? "neg" : ""} />
            <Stat label="绝对收益" value={signedPct1(symRow.abs_ret)}
              tone={symRow.abs_ret > 0 ? "pos" : symRow.abs_ret < 0 ? "neg" : ""} />
            <Stat label="RS 比率" value={num(symRow.rs_ratio)?.toFixed(3) ?? "—"} sub="股价 / 等权指数" />
            <Stat label="RS 排名" value={symRow.rank != null ? `#${symRow.rank} / ${ranking.length}` : "—"} />
            <Stat label="趋势" value={trendLabel(symRow.trend).label} tone={trendLabel(symRow.trend).tone}
              sub={`RS 比率 vs MA${data.ma_trend ?? 20}`} />
            <Stat label="现价" value={price2(symRow.close)} />
          </>
        ) : <span className="muted" style={{ fontSize: 12 }}>标的不在排名中。</span>}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12, marginBottom: 12 }}>
        <div className="card">
          <h3 style={{ marginBottom: 6 }}>领涨 Top 5（相对收益）</h3>
          {leaders.map((r) => (
            <div key={r.symbol} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", cursor: "pointer" }}
              onClick={() => setSymbol(r.symbol)}>
              <span><b>{r.symbol}</b> <span className="muted" style={{ fontSize: 11 }}>{r.name}</span></span>
              <span className="pos">{signedPct1(r.rs_ret)}</span>
            </div>
          ))}
        </div>
        <div className="card">
          <h3 style={{ marginBottom: 6 }}>领跌 Bottom 5（相对收益）</h3>
          {laggards.map((r) => (
            <div key={r.symbol} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", cursor: "pointer" }}
              onClick={() => setSymbol(r.symbol)}>
              <span><b>{r.symbol}</b> <span className="muted" style={{ fontSize: 11 }}>{r.name}</span></span>
              <span className="neg">{signedPct1(r.rs_ret)}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <h3>全市场相对强度排名 · 周期可调
          <select value={period} onChange={(e) => setPeriod(+e.target.value)} style={{ marginLeft: 8 }}>
            {PERIOD_OPTS.map((p) => <option key={p} value={p}>{p} 日</option>)}
          </select>
        </h3>
        <div className="scroll" style={{ maxHeight: 460 }}>
          <table className="data">
            <thead><tr>
              <th onClick={() => toggleSort("rank")}>#{arrow("rank")}</th>
              <th onClick={() => toggleSort("symbol")}>代码{arrow("symbol")}</th>
              <th onClick={() => toggleSort("name")}>名称{arrow("name")}</th>
              <th onClick={() => toggleSort("rs_ret")}>相对收益{arrow("rs_ret")}</th>
              <th onClick={() => toggleSort("abs_ret")}>绝对收益{arrow("abs_ret")}</th>
              <th onClick={() => toggleSort("rs_ratio")}>RS 比率{arrow("rs_ratio")}</th>
              <th onClick={() => toggleSort("trend")}>趋势{arrow("trend")}</th>
              <th onClick={() => toggleSort("close")}>现价{arrow("close")}</th>
            </tr></thead>
            <tbody>
              {sorted.map((r) => {
                const tl = trendLabel(r.trend);
                return (
                  <tr key={r.symbol} style={{ cursor: "pointer" }} onClick={() => setSymbol(r.symbol)}>
                    <td className="muted">{r.rank}</td>
                    <td><b>{r.symbol}</b></td>
                    <td className="muted">{r.name}</td>
                    <td className={r.rs_ret > 0 ? "pos" : r.rs_ret < 0 ? "neg" : ""}>{signedPct1(r.rs_ret)}</td>
                    <td className={r.abs_ret > 0 ? "pos" : r.abs_ret < 0 ? "neg" : ""}>{signedPct1(r.abs_ret)}</td>
                    <td>{num(r.rs_ratio)?.toFixed(3) ?? "—"}</td>
                    <td className={tl.tone}>{tl.label}</td>
                    <td>{price2(r.close)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
