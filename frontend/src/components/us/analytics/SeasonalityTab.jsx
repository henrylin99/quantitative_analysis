// 季节性分析 tab —— /market/seasonality?symbol=。
// 口径移植自开源参考实现的 SeasonalityPage：全历史日收益按日历月(1-12)与星期(周一-五)分组，
// 报告组内日均收益、胜率、t 统计。月度时序横轴为示意月份序（后端以占位时间戳编码）。
import { useEffect, useMemo, useState } from "react";
import { analyticsApiFor } from "../../../api/usAnalytics";
import LineChart from "../LineChart.jsx";
import { Stat, ChartCard, RegimeBanner, useSymbols, SymbolSelect } from "./shared.jsx";
import {
  toLine, sortRows, pctSigned, pct1, monthLabel, num, MONTH_LABELS,
} from "../../../lib/us/analyticsFmt";

// 季节强度格式（12 个月日均收益的标准差）→ 百分数 3 位。
const strengthFmt = (v) => (v == null ? "—" : (v * 100).toFixed(3) + "%");

// 体制 = 当前月份姿态(顺月/逆月/中性) × 季节强度(强/中/弱)。
// 当前月份 = 数据最后一个交易日的月份（确定性，不依赖系统时钟）。
function regime(stats) {
  if (!stats) return { key: "n/a", label: "—", tone: "", desc: "无数据" };
  const cm = stats.cur_month;
  const mm = stats.monthly_mean || [];
  const mw = stats.monthly_win || [];
  const str = num(stats.seasonality_strength);
  const curMean = cm != null ? num(mm[cm - 1]) : null;
  const curWin = cm != null ? num(mw[cm - 1]) : null;
  if (cm == null || curMean == null)
    return { key: "neutral", label: "中性", tone: "", desc: "季节性数据不足。" };
  const posture = (curMean >= 0.0006 && (curWin == null || curWin >= 0.53))
    ? { key: "favor", label: MONTH_LABELS[cm - 1] + " 顺月", tone: "pos" }
    : (curMean <= -0.0006 && (curWin == null || curWin <= 0.47))
    ? { key: "adverse", label: MONTH_LABELS[cm - 1] + " 逆月", tone: "neg" }
    : { key: "neutral", label: MONTH_LABELS[cm - 1] + " 中性", tone: "" };
  const tier = str == null ? { label: "" }
    : str >= 0.0008 ? { key: "pronounced", label: "季节性强" }
    : str >= 0.0003 ? { key: "moderate", label: "季节性中" }
    : { key: "faint", label: "季节性弱" };
  const desc = "当前 " + MONTH_LABELS[cm - 1] + "：历史日均收益 " + pctSigned(curMean) +
    "（胜率 " + (curWin != null ? pct1(curWin) : "—") + "）→ " +
    (posture.key === "favor" ? "季节性偏强（历史上该月易涨）"
      : posture.key === "adverse" ? "季节性偏弱（历史上该月易跌）"
      : "无明显季节倾向") + "。" +
    (tier.label ? "各月日均收益离散度 " + strengthFmt(str) + "（" + tier.label + "）。" : "");
  return { key: posture.key, label: posture.label + (tier.label ? " · " + tier.label : ""), tone: posture.tone, desc };
}

export default function SeasonalityTab({ mk = "us" }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [symbol, setSymbol] = useState("");
  const [sortKey, setSortKey] = useState("seasonality_strength");
  const [sortDir, setSortDir] = useState("desc");
  const symbols = useSymbols(mk);
  useEffect(() => {
    if (symbols.length && !symbols.includes(symbol)) setSymbol(symbols[0]);
  }, [symbols, symbol]);


  useEffect(() => {
    let on = true;
    setErr("");
    analyticsApiFor(mk).fetch("/market/seasonality", { symbol: symbol || undefined })
      .then((d) => { if (on) setData(d); })
      .catch((e) => { if (on) setErr(String(e?.message || e)); });
    return () => { on = false; };
  }, [symbol]);

  const reg = useMemo(() => regime(data), [data]);
  const ranking = useMemo(() => data?.ranking || [], [data]);
  const symInfo = data?.symbol_info || null;
  const sorted = useMemo(() => sortRows(ranking, sortKey, sortDir), [ranking, sortKey, sortDir]);

  if (err) return <div className="spinner">季节性数据加载失败：{err}</div>;
  if (!data) return <div className="spinner">加载季节性数据中…</div>;

  const mktMonthly = toLine(data.mkt_monthly_series);
  const mktWin = toLine(data.mkt_win_series);
  const mktDow = toLine(data.mkt_dow_series);
  const curMonth = data.cur_month;

  const mostSeasonal = [...ranking].sort((a, b) => (b.seasonality_strength ?? 0) - (a.seasonality_strength ?? 0)).slice(0, 5);
  const leastSeasonal = [...ranking].sort((a, b) => (a.seasonality_strength ?? 9) - (b.seasonality_strength ?? 9)).slice(0, 5);
  const isFavor = (r) => {
    const m = r.monthly_mean?.[curMonth - 1], w = r.monthly_win?.[curMonth - 1];
    return m != null && m >= 0.0006 && (w == null || w >= 0.53);
  };
  const isAdverse = (r) => {
    const m = r.monthly_mean?.[curMonth - 1], w = r.monthly_win?.[curMonth - 1];
    return m != null && m <= -0.0006 && (w == null || w <= 0.47);
  };
  const nFavor = ranking.filter(isFavor).length;
  const nAdverse = ranking.filter(isAdverse).length;

  const toggleSort = (k) => {
    if (k === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(k); setSortDir(k === "symbol" || k === "name" ? "asc" : "desc"); }
  };
  const arrow = (k) => (k === sortKey ? (sortDir === "asc" ? " ▲" : " ▼") : "");

  const bestM = data.best_month, worstM = data.worst_month;
  const bestMean = bestM ? data.monthly_mean?.[bestM - 1] : null;
  const worstMean = worstM ? data.monthly_mean?.[worstM - 1] : null;
  const curMean = curMonth ? data.monthly_mean?.[curMonth - 1] : null;

  return (
    <div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        季节性分析（{data.n_stocks} 只标的，{data.n_days} 个交易日）。回答「<b>哪些月份 / 星期历史上涨多</b>」——
        把日收益按<b>日历周期</b>拆解。每个日历月约 40 个样本，读作「近期季节性」。
        当前月份 = {monthLabel(curMonth)}（数据末日）。
      </div>

      <RegimeBanner label={reg.label} tone={reg.tone} desc={reg.desc} />

      <div className="stats">
        <Stat label={`${monthLabel(curMonth)} 日均`} value={pctSigned(curMean)}
          tone={curMean != null && curMean >= 0 ? "pos" : "neg"} sub="当前月份历史" />
        <Stat label="最佳月份" value={monthLabel(bestM)} tone="pos" sub={bestMean != null ? pctSigned(bestMean) + "/日" : "—"} />
        <Stat label="最差月份" value={monthLabel(worstM)} tone="neg" sub={worstMean != null ? pctSigned(worstMean) + "/日" : "—"} />
        <Stat label="季节强度" value={strengthFmt(data.seasonality_strength)} sub="各月离散度" />
        <Stat label="顺月标的" value={nFavor} tone="pos" sub={`${monthLabel(curMonth)} 偏强`} />
        <Stat label="逆月标的" value={nAdverse} tone="neg" sub={`${monthLabel(curMonth)} 偏弱`} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))", gap: 12 }}>
        <ChartCard title="市场月度季节性（日均收益）"
          desc="每个日历月（1→12 月）的历史日均收益——市场的「季节指纹」。柱线越高=该月历史上越容易涨。横轴为示意月份序。">
          <LineChart data={mktMonthly} color="#26a69a" height={200} />
        </ChartCard>

        <ChartCard title="市场月度胜率"
          desc="每个日历月里上涨交易日占比。>50%=该月偏多，<50%=偏空。与上一图互证季节性。">
          <LineChart data={mktWin} color="#42a5f5" height={200} />
        </ChartCard>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))", gap: 12, marginTop: 12 }}>
        <ChartCard title="个股月度季节性 vs 市场"
          desc="红 = 该标的各月历史日均收益；蓝 = 市场。红高于蓝=该标的在该月相对更强（季节 alpha）。">
          <div style={{ marginBottom: 6, display: "flex", gap: 8, alignItems: "center" }}>
            <SymbolSelect symbols={symbols} value={symbol} onChange={setSymbol} />
            {symInfo && <span className="muted" style={{ fontSize: 12 }}>{symInfo.name}</span>}
          </div>
          {symInfo ? (
            <LineChart series={[
              { data: toLine(symInfo.monthly_series), color: "#ef5350", lineWidth: 2 },
              { data: toLine(symInfo.mkt_monthly_series), color: "#4f93e7", lineWidth: 1.5 },
            ]} height={200} />
          ) : <div className="muted" style={{ fontSize: 12 }}>选择一只标的查看其季节指纹。</div>}
        </ChartCard>

        <ChartCard title="市场星期效应（周一→周五）"
          desc="每个星期几的历史日均收益。高=该日历史上偏涨（如「周一效应」「周五效应」）。横轴为示意星期序。">
          <LineChart data={mktDow} color="#fb8c00" height={200} />
        </ChartCard>
      </div>

      {symInfo && (
        <div className="card" style={{ display: "flex", gap: 20, flexWrap: "wrap", alignItems: "center", margin: "12px 0" }}>
          <b style={{ fontSize: 16 }}>{symInfo.symbol}</b>
          <span className="muted">{symInfo.name}</span>
          <Stat label="最佳月" value={monthLabel(symInfo.best_month)} tone="pos" />
          <Stat label="最差月" value={monthLabel(symInfo.worst_month)} tone="neg" />
          <Stat label="当前月日均" value={pctSigned(symInfo.cur_month_mean)}
            tone={symInfo.cur_month_mean != null && symInfo.cur_month_mean >= 0 ? "pos" : "neg"} />
          <Stat label="季节强度" value={strengthFmt(symInfo.seasonality_strength)} />
          <Stat label="季节性排名" value={symInfo.rank != null ? `#${symInfo.rank} / ${ranking.length}` : "—"} sub="越季节化越靠前" />
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12, marginBottom: 12 }}>
        <div className="card">
          <h3 style={{ marginBottom: 6 }}>最季节化 Top 5</h3>
          {mostSeasonal.map((r) => (
            <div key={r.symbol} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", cursor: "pointer" }}
              onClick={() => setSymbol(r.symbol)}>
              <span><b>{r.symbol}</b> <span className="muted" style={{ fontSize: 11 }}>
                {monthLabel(r.best_month)}/{monthLabel(r.worst_month)}</span></span>
              <span className="muted">{strengthFmt(r.seasonality_strength)}</span>
            </div>
          ))}
        </div>
        <div className="card">
          <h3 style={{ marginBottom: 6 }}>最平稳 Top 5</h3>
          {leastSeasonal.map((r) => (
            <div key={r.symbol} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", cursor: "pointer" }}
              onClick={() => setSymbol(r.symbol)}>
              <span><b>{r.symbol}</b> <span className="muted" style={{ fontSize: 11 }}>
                {monthLabel(r.best_month)}/{monthLabel(r.worst_month)}</span></span>
              <span className="muted">{strengthFmt(r.seasonality_strength)}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <h3>全市场季节性排名 · 按季节强度降序</h3>
        <div className="scroll" style={{ maxHeight: 460 }}>
          <table className="data">
            <thead><tr>
              <th onClick={() => toggleSort("rank")}>#{arrow("rank")}</th>
              <th onClick={() => toggleSort("symbol")}>代码{arrow("symbol")}</th>
              <th onClick={() => toggleSort("name")}>名称{arrow("name")}</th>
              <th onClick={() => toggleSort("seasonality_strength")}>季节强度{arrow("seasonality_strength")}</th>
              <th onClick={() => toggleSort("best_month")}>最佳月{arrow("best_month")}</th>
              <th onClick={() => toggleSort("worst_month")}>最差月{arrow("worst_month")}</th>
              <th onClick={() => toggleSort("cur_month_mean")}>{monthLabel(curMonth)}均{arrow("cur_month_mean")}</th>
              <th onClick={() => toggleSort("overall_mean")}>日均收益{arrow("overall_mean")}</th>
            </tr></thead>
            <tbody>
              {sorted.map((r) => (
                <tr key={r.symbol} style={{ cursor: "pointer" }} onClick={() => setSymbol(r.symbol)}>
                  <td className="muted">{r.rank}</td>
                  <td><b>{r.symbol}</b></td>
                  <td className="muted">{r.name}</td>
                  <td>{strengthFmt(r.seasonality_strength)}</td>
                  <td className="pos">{monthLabel(r.best_month)}</td>
                  <td className="neg">{monthLabel(r.worst_month)}</td>
                  <td className={r.cur_month_mean != null && r.cur_month_mean >= 0 ? "pos" : "neg"}>{pctSigned(r.cur_month_mean)}</td>
                  <td className={r.overall_mean != null && r.overall_mean >= 0 ? "pos" : "neg"}>{pctSigned(r.overall_mean)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
