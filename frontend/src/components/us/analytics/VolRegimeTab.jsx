// 波动率体制 tab —— /market/volregime?window=。
// 口径移植自开源参考实现的 VolRegimePage：市场 RMS 波动 / 截面离散度 / 隐含相关系数三视角。
// 适配：后端路由未透传 symbol（symbol_info 恒空），个股波动时序改为「从排名行取汇总卡」。
import { useEffect, useMemo, useState } from "react";
import { analyticsApiFor } from "../../../api/usAnalytics";
import LineChart from "../LineChart.jsx";
import { Stat, ChartCard, RegimeBanner } from "./shared.jsx";
import {
  toLine, sortRows, vol1, pct0, signedPct1, fixed2, price2, num,
} from "../../../lib/us/analyticsFmt";

const WINDOW_OPTS = [10, 20, 40, 60];

// 体制 = 波动体制(全历史分位) × 离散体制(隐含相关系数水平：高=齐涨齐跌宏观市)。
function regime(stats) {
  if (!stats) return { key: "n/a", label: "—", tone: "", desc: "无数据" };
  const mv = num(stats.mkt_vol);
  const corr = num(stats.implied_corr);
  const vp = num(stats.vol_pctile);
  if (mv == null || corr == null || vp == null)
    return { key: "neutral", label: "中性", tone: "", desc: "波动/离散度数据不足。" };
  const vol = vp < 0.33 ? { key: "calm", label: "平静", tone: "pos" }
    : vp < 0.67 ? { key: "normal", label: "正常", tone: "" }
    : { key: "turbulent", label: "动荡", tone: "neg" };
  const disp = corr < 0.30 ? { key: "stockpicker", label: "选股市", tone: "pos" }
    : corr < 0.60 ? { key: "balanced", label: "均衡", tone: "" }
    : { key: "macro", label: "宏观市", tone: "warn" };
  const rank = { neg: 3, warn: 2, pos: 1, "": 0 };
  const tone = rank[vol.tone] >= rank[disp.tone] ? vol.tone : disp.tone;
  const volWord = vp >= 0.67 ? "高波动" : vp < 0.33 ? "低波动" : "中性波动";
  const corrWord = disp.key === "macro" ? "齐涨齐跌·分散失效"
    : disp.key === "stockpicker" ? "个股分化·自下而上" : "中等相关";
  return {
    key: vol.key + "_" + disp.key,
    label: vol.label + " · " + disp.label, tone,
    desc: `市场年化波动率 ${(mv * 100).toFixed(1)}%（全历史 ${(vp * 100).toFixed(0)}% 分位，${volWord}）；` +
      `隐含相关系数 ${(corr * 100).toFixed(0)}%（${corrWord}）。`,
  };
}

export default function VolRegimeTab({ mk = "us" }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [win, setWin] = useState(20);
  const [symbol, setSymbol] = useState("");
  const [sortKey, setSortKey] = useState("rank");
  const [sortDir, setSortDir] = useState("asc");

  useEffect(() => {
    let on = true;
    setErr("");
    analyticsApiFor(mk).fetch("/market/volregime", { window: win })
      .then((d) => { if (on) setData(d); })
      .catch((e) => { if (on) setErr(String(e?.message || e)); });
    return () => { on = false; };
  }, [win]);

  const reg = useMemo(() => regime(data), [data]);
  const ranking = useMemo(() => data?.ranking || [], [data]);
  useEffect(() => {
    if (ranking.length && !ranking.some((r) => r.symbol === symbol)) setSymbol(ranking[0].symbol);
  }, [ranking, symbol]);

  const sorted = useMemo(() => sortRows(ranking, sortKey, sortDir), [ranking, sortKey, sortDir]);
  const symRow = useMemo(() => ranking.find((r) => r.symbol === symbol) || null, [ranking, symbol]);

  if (err) return <div className="spinner">波动体制数据加载失败：{err}</div>;
  if (!data) return <div className="spinner">加载波动与离散度数据中…</div>;

  const mktVol = toLine(data.mkt_vol_series);
  const dispLine = toLine(data.dispersion_series);
  const corrLine = toLine(data.implied_corr_series);
  const band = (val) => (val == null ? [] : mktVol.map((p) => ({ time: p.time, value: val })));

  const mktVolVal = num(data.mkt_vol);
  const highVol = ranking.slice(0, 5);
  const lowVol = ranking.slice(-5).reverse();
  const nHigh = ranking.filter((r) => (r.realized_vol ?? 0) > mktVolVal).length;

  const toggleSort = (k) => {
    if (k === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(k); setSortDir(k === "symbol" || k === "name" ? "asc" : "desc"); }
  };
  const arrow = (k) => (k === sortKey ? (sortDir === "asc" ? " ▲" : " ▼") : "");

  return (
    <div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        市场波动与离散度（{data.n_stocks} 只标的，{data.n_days} 个交易日，滚动 {win} 日）。回答「<b>市场有多动荡、是选股市还是宏观市</b>」。
        截面离散度高=个股各自走（自下而上选股友好）；隐含相关系数高=齐涨齐跌（分散化失效、宏观驱动）。
      </div>

      <RegimeBanner label={reg.label} tone={reg.tone} desc={reg.desc} />

      <div className="stats">
        <Stat label="市场波动率" value={vol1(data.mkt_vol)}
          tone={data.vol_pctile >= 0.67 ? "neg" : data.vol_pctile < 0.33 ? "pos" : ""}
          sub={`全历史 ${pct0(data.vol_pctile)} 分位`} />
        <Stat label="截面离散度" value={vol1(data.dispersion)} sub="年化横截面标准差" />
        <Stat label="隐含相关系数" value={pct0(data.implied_corr)}
          tone={data.implied_corr >= 0.6 ? "neg" : data.implied_corr < 0.3 ? "pos" : ""}
          sub={`全历史 ${pct0(data.corr_pctile)} 分位`} />
        <Stat label="高 / 低波动" value={`${nHigh} / ${ranking.length - nHigh}`} sub="相对市场波动" />
        <Stat label="标的数" value={ranking.length} sub="有完整历史的标的" />
        <Stat label="波动窗" value={`${win} 日`} sub="滚动标准差窗口" />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))", gap: 12 }}>
        <ChartCard title="市场实现波动率（RMS 年化）"
          desc="标的池实现波动率的均方根（内部 VIX）。红线=全历史 75% 分位、灰线=中位、绿线=25% 分位——当前值相对位置即动荡程度。">
          <LineChart series={[
            { data: mktVol, color: "#ef5350", lineWidth: 2 },
            { data: band(data.vol_pcts?.p75), color: "rgba(239,83,80,0.5)", lineWidth: 1 },
            { data: band(data.vol_pcts?.p50), color: "rgba(154,166,178,0.45)", lineWidth: 1 },
            { data: band(data.vol_pcts?.p25), color: "rgba(102,187,106,0.5)", lineWidth: 1 },
          ]} height={200} />
        </ChartCard>

        <ChartCard title="截面离散度（年化）"
          desc="每日收益在标的间的横截面标准差（滚动平滑）。高=个股各自走（选股市），低=齐涨齐跌（宏观市）。">
          <LineChart data={dispLine} color="#ab47bc" height={200} />
        </ChartCard>

        <ChartCard title="隐含平均相关系数"
          desc="由 σ²_cs/σ̄² 反推的平均两两相关 ρ̄。→1=危机式齐涨齐跌（分散失效）；低=个股分化。">
          <LineChart data={corrLine} color="#ff9800" height={200} />
        </ChartCard>
      </div>

      {/* 所选标的汇总（从排名行取，路由未透出逐日个股波动序列） */}
      <div className="card" style={{ display: "flex", gap: 18, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
        <span style={{ fontSize: 14 }}>个股波动</span>
        <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
          {ranking.map((r) => <option key={r.symbol} value={r.symbol}>{r.symbol} — {r.name}</option>)}
        </select>
        {symRow ? (
          <>
            <b style={{ fontSize: 16 }}>{symRow.symbol}</b>
            <span className="muted">{symRow.name}</span>
            <Stat label="实现波动率" value={vol1(symRow.realized_vol)}
              tone={symRow.vol_pctile >= 0.67 ? "neg" : symRow.vol_pctile < 0.33 ? "pos" : ""} />
            <Stat label="波动分位" value={pct0(symRow.vol_pctile)} sub="在全市场中的位置" />
            <Stat label="波动率的波动" value={vol1(symRow.vol_of_vol)} sub="波动稳定性" />
            <Stat label={`${win}日收益`} value={signedPct1(symRow.ret)}
              tone={symRow.ret > 0 ? "pos" : symRow.ret < 0 ? "neg" : ""} />
            <Stat label="单位波动收益" value={fixed2(symRow.vol_adj_ret)}
              tone={symRow.vol_adj_ret > 0 ? "pos" : symRow.vol_adj_ret < 0 ? "neg" : ""} sub="收益÷波动" />
            <Stat label="波动排名" value={symRow.rank != null ? `#${symRow.rank} / ${ranking.length}` : "—"} />
          </>
        ) : <span className="muted" style={{ fontSize: 12 }}>标的不在排名中。</span>}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12, marginBottom: 12 }}>
        <div className="card">
          <h3 style={{ marginBottom: 6 }}>最高波动 Top 5</h3>
          {highVol.map((r) => (
            <div key={r.symbol} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", cursor: "pointer" }}
              onClick={() => setSymbol(r.symbol)}>
              <span><b>{r.symbol}</b> <span className="muted" style={{ fontSize: 11 }}>{r.name}</span></span>
              <span className="neg">{vol1(r.realized_vol)}</span>
            </div>
          ))}
        </div>
        <div className="card">
          <h3 style={{ marginBottom: 6 }}>最低波动 Bottom 5</h3>
          {lowVol.map((r) => (
            <div key={r.symbol} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", cursor: "pointer" }}
              onClick={() => setSymbol(r.symbol)}>
              <span><b>{r.symbol}</b> <span className="muted" style={{ fontSize: 11 }}>{r.name}</span></span>
              <span className="pos">{vol1(r.realized_vol)}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <h3>全市场波动率排名 · 滚动 {win} 日 · 窗口可调
          <select value={win} onChange={(e) => setWin(+e.target.value)} style={{ marginLeft: 8 }}>
            {WINDOW_OPTS.map((w) => <option key={w} value={w}>{w} 日</option>)}
          </select>
        </h3>
        <div className="scroll" style={{ maxHeight: 460 }}>
          <table className="data">
            <thead><tr>
              <th onClick={() => toggleSort("rank")}>#{arrow("rank")}</th>
              <th onClick={() => toggleSort("symbol")}>代码{arrow("symbol")}</th>
              <th onClick={() => toggleSort("name")}>名称{arrow("name")}</th>
              <th onClick={() => toggleSort("realized_vol")}>实现波动率{arrow("realized_vol")}</th>
              <th onClick={() => toggleSort("vol_pctile")}>波动分位{arrow("vol_pctile")}</th>
              <th onClick={() => toggleSort("vol_of_vol")}>波动的波动{arrow("vol_of_vol")}</th>
              <th onClick={() => toggleSort("ret")}>{win}日收益{arrow("ret")}</th>
              <th onClick={() => toggleSort("vol_adj_ret")}>单位波动收益{arrow("vol_adj_ret")}</th>
              <th onClick={() => toggleSort("close")}>现价{arrow("close")}</th>
            </tr></thead>
            <tbody>
              {sorted.map((r) => (
                <tr key={r.symbol} style={{ cursor: "pointer" }} onClick={() => setSymbol(r.symbol)}>
                  <td className="muted">{r.rank}</td>
                  <td><b>{r.symbol}</b></td>
                  <td className="muted">{r.name}</td>
                  <td className={r.vol_pctile >= 0.67 ? "neg" : r.vol_pctile < 0.33 ? "pos" : ""}>{vol1(r.realized_vol)}</td>
                  <td>{pct0(r.vol_pctile)}</td>
                  <td>{vol1(r.vol_of_vol)}</td>
                  <td className={r.ret > 0 ? "pos" : r.ret < 0 ? "neg" : ""}>{signedPct1(r.ret)}</td>
                  <td className={r.vol_adj_ret > 0 ? "pos" : r.vol_adj_ret < 0 ? "neg" : ""}>{fixed2(r.vol_adj_ret)}</td>
                  <td>{price2(r.close)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
