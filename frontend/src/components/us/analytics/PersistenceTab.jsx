// 均值回归与持续性 tab —— /market/persistence?symbol=。
// 口径移植自开源参考实现的 PersistencePage：自相关 ρ(k) / 方差比 VR(k) / R/S Hurst，
// 核心恒等 VR(2) = 1 + ρ(1)（Lo 1988）：>1 趋势 / <1 均值回归 / ≈1 随机游走。
// 横轴时间戳是后端以 lag 序号生成的示意 unix 秒（非真实交易日），仅作 lag 顺序展示。
import { useEffect, useMemo, useState } from "react";
import { analyticsApiFor } from "../../../api/usAnalytics";
import LineChart from "../LineChart.jsx";
import { Stat, ChartCard, RegimeBanner, useSymbols, SymbolSelect } from "./shared.jsx";
import {
  toLine, sortRows, rho, vr, fixed3, num,
} from "../../../lib/us/analyticsFmt";

// 体制 = 姿态(均值回归/趋势持续/随机游走) × 偏离强度，由 VR(2) 驱动。
function regime(stats) {
  if (!stats) return { key: "n/a", label: "—", tone: "", desc: "无数据" };
  const vr2 = num(stats.vr2);
  const rho1 = num(stats.rho1);
  const hurst = num(stats.hurst);
  if (vr2 == null)
    return { key: "neutral", label: "数据不足", tone: "", desc: "收益序列不足以估计持续性。" };
  const posture = vr2 <= 0.97 ? { key: "revert", label: "均值回归", tone: "neg" }
    : vr2 >= 1.03 ? { key: "trend", label: "趋势持续", tone: "pos" }
    : { key: "random", label: "随机游走", tone: "" };
  const dev = Math.abs(vr2 - 1);
  const tier = dev >= 0.05 ? { key: "pronounced", label: "持续性强" }
    : dev >= 0.02 ? { key: "moderate", label: "持续性中" }
    : { key: "faint", label: "持续性弱" };
  const desc = "市场日收益方差比 VR(2) = " + vr(vr2) +
    "（" + (vr2 < 1 ? "负自相关、涨跌交替——反转/区间策略友好，趋势策略易失效"
      : vr2 > 1 ? "正自相关、动量延续——趋势/突破策略友好"
      : "近乎无记忆，历史收益难以预测未来") + "）。" +
    "一阶自相关 ρ(1) = " + rho(rho1) +
    (hurst != null ? "，Hurst " + fixed3(hurst) + "（<0.5 均值回归 / ≈0.5 随机 / >0.5 长记忆持续）。" : "。");
  return { key: posture.key + "_" + tier.key, label: posture.label + " · " + tier.label, tone: posture.tone, desc };
}

export default function PersistenceTab({ mk = "us" }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [symbol, setSymbol] = useState("");
  const [sortKey, setSortKey] = useState("abs_rho1");
  const [sortDir, setSortDir] = useState("desc");
  const symbols = useSymbols(mk);
  useEffect(() => {
    if (symbols.length && !symbols.includes(symbol)) setSymbol(symbols[0]);
  }, [symbols, symbol]);


  useEffect(() => {
    let on = true;
    setErr("");
    analyticsApiFor(mk).fetch("/market/persistence", { symbol: symbol || undefined })
      .then((d) => { if (on) setData(d); })
      .catch((e) => { if (on) setErr(String(e?.message || e)); });
    return () => { on = false; };
  }, [symbol]);

  const reg = useMemo(() => regime(data), [data]);
  const ranking = useMemo(() => data?.ranking || [], [data]);
  const symInfo = data?.symbol_info || null;
  const ranked = useMemo(
    () => ranking.map((r) => ({ ...r, abs_rho1: Math.abs(num(r.rho1) ?? 0) })),
    [ranking],
  );
  const sorted = useMemo(() => sortRows(ranked, sortKey, sortDir), [ranked, sortKey, sortDir]);

  if (err) return <div className="spinner">持续性数据加载失败：{err}</div>;
  if (!data) return <div className="spinner">加载持续性数据中…</div>;

  const mktAcf = toLine(data.mkt_acf_series);
  const mktVr = toLine(data.mkt_vr_series);

  const mostRevert = [...ranking].filter((r) => r.vr2 != null).sort((a, b) => a.vr2 - b.vr2).slice(0, 5);
  const mostTrend = [...ranking].filter((r) => r.vr2 != null).sort((a, b) => b.vr2 - a.vr2).slice(0, 5);
  const nRevert = ranking.filter((r) => r.vr2 != null && r.vr2 <= 0.97).length;
  const nTrend = ranking.filter((r) => r.vr2 != null && r.vr2 >= 1.03).length;

  const toggleSort = (k) => {
    if (k === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(k); setSortDir(k === "symbol" || k === "name" ? "asc" : "desc"); }
  };
  const arrow = (k) => (k === sortKey ? (sortDir === "asc" ? " ▲" : " ▼") : "");

  return (
    <div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        均值回归与持续性（{data.n_stocks} 只标的，{data.n_days} 个交易日）。回答「<b>日收益是否记得自己的过去</b>」。
        核心恒等 <b>VR(2) = 1 + ρ(1)</b>（Lo 1988）：&gt;1 趋势 / &lt;1 均值回归 / ≈1 随机游走。
        同样的波动率，一只票可能均值回归（涨跌交替），另一只可能趋势持续（动量延续）。
      </div>

      <RegimeBanner label={reg.label} tone={reg.tone} desc={reg.desc} />

      <div className="stats">
        <Stat label="市场 ρ(1)" value={rho(data.rho1)} tone={data.rho1 != null && data.rho1 >= 0 ? "pos" : "neg"} sub="一阶自相关" />
        <Stat label="市场 VR(2)" value={vr(data.vr2)} tone={data.vr2 != null && data.vr2 >= 1 ? "pos" : "neg"}
          sub={data.vr2 != null ? "偏离随机 " + rho(data.vr2 - 1) : ""} />
        <Stat label="市场 Hurst" value={fixed3(data.hurst)}
          sub={data.hurst != null ? (data.hurst < 0.45 ? "均值回归" : data.hurst > 0.55 ? "持续" : "近随机") : ""} />
        <Stat label="均值回归数" value={nRevert} tone="neg" sub="VR(2)≤0.97" />
        <Stat label="趋势持续数" value={nTrend} tone="pos" sub="VR(2)≥1.03" />
        <Stat label="随机游走数" value={ranking.length - nRevert - nTrend} sub="0.97<VR(2)<1.03" />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))", gap: 12 }}>
        <ChartCard title="市场自相关函数 ACF（ρ vs 滞后期）"
          desc="各滞后期(1/2/5/10/20 日)的日收益自相关。0 线=无记忆；负=反转、正=趋势。横轴为滞后期示意。">
          <LineChart data={mktAcf} color="#26a69a" height={200} />
        </ChartCard>

        <ChartCard title="市场方差比 VR(k)（k=2/5/10/20）"
          desc="重叠 k 日收益方差 ÷ (k×单日方差)。1.0 线=随机游走；<1 均值回归、>1 趋势。">
          <LineChart data={mktVr} color="#42a5f5" height={200} />
        </ChartCard>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))", gap: 12, marginTop: 12 }}>
        <ChartCard title="个股自相关 vs 市场"
          desc="红 = 该标的各滞后期自相关；蓝 = 市场。红为负且低于蓝=该标的更偏均值回归。">
          <div style={{ marginBottom: 6, display: "flex", gap: 8, alignItems: "center" }}>
            <SymbolSelect symbols={symbols} value={symbol} onChange={setSymbol} />
            {symInfo && <span className="muted" style={{ fontSize: 12 }}>{symInfo.name}</span>}
          </div>
          {symInfo ? (
            <LineChart series={[
              { data: toLine(symInfo.acf_series), color: "#ef5350", lineWidth: 2 },
              { data: toLine(symInfo.mkt_acf_series), color: "#4f93e7", lineWidth: 1.5 },
            ]} height={200} />
          ) : <div className="muted" style={{ fontSize: 12 }}>选择一只标的查看其自相关结构。</div>}
        </ChartCard>

        <ChartCard title="个股方差比 vs 市场"
          desc="红 = 该标的 VR(k)；蓝 = 市场；1.0 = 随机游走基准。红持续低于 1=均值回归、高于 1=趋势。">
          {symInfo ? (
            <LineChart series={[
              { data: toLine(symInfo.vr_series), color: "#ef5350", lineWidth: 2 },
              { data: toLine(symInfo.mkt_vr_series), color: "#4f93e7", lineWidth: 1.5 },
            ]} height={200} />
          ) : <div className="muted" style={{ fontSize: 12 }}>选择一只标的。</div>}
        </ChartCard>
      </div>

      {symInfo && (
        <div className="card" style={{ display: "flex", gap: 20, flexWrap: "wrap", alignItems: "center", margin: "12px 0" }}>
          <b style={{ fontSize: 16 }}>{symInfo.symbol}</b>
          <span className="muted">{symInfo.name}</span>
          <Stat label="ρ(1)" value={rho(symInfo.rho1)} tone={symInfo.rho1 != null && symInfo.rho1 >= 0 ? "pos" : "neg"} />
          <Stat label="VR(2)" value={vr(symInfo.vr2)} tone={symInfo.vr2 != null && symInfo.vr2 >= 1 ? "pos" : "neg"} />
          <Stat label="Hurst" value={fixed3(symInfo.hurst)}
            sub={symInfo.hurst != null ? (symInfo.hurst < 0.45 ? "均值回归" : symInfo.hurst > 0.55 ? "持续" : "近随机") : ""} />
          <Stat label="持续性排名" value={symInfo.rank != null ? `#${symInfo.rank} / ${ranking.length}` : "—"} sub="按 |ρ(1)| 降序" />
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12, marginBottom: 12 }}>
        <div className="card">
          <h3 style={{ marginBottom: 6 }}>最均值回归 Top 5（VR(2) 最低）</h3>
          {mostRevert.map((r) => (
            <div key={r.symbol} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", cursor: "pointer" }}
              onClick={() => setSymbol(r.symbol)}>
              <span><b>{r.symbol}</b> <span className="muted" style={{ fontSize: 11 }}>{r.name}</span></span>
              <span className="muted">{rho(r.rho1)} / VR {vr(r.vr2)}</span>
            </div>
          ))}
        </div>
        <div className="card">
          <h3 style={{ marginBottom: 6 }}>最趋势持续 Top 5（VR(2) 最高）</h3>
          {mostTrend.map((r) => (
            <div key={r.symbol} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", cursor: "pointer" }}
              onClick={() => setSymbol(r.symbol)}>
              <span><b>{r.symbol}</b> <span className="muted" style={{ fontSize: 11 }}>{r.name}</span></span>
              <span className="muted">{rho(r.rho1)} / VR {vr(r.vr2)}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <h3>全市场持续性排名 · 按 |ρ(1)| 降序（持续性最强在前）</h3>
        <div className="scroll" style={{ maxHeight: 460 }}>
          <table className="data">
            <thead><tr>
              <th onClick={() => toggleSort("rank")}>#{arrow("rank")}</th>
              <th onClick={() => toggleSort("symbol")}>代码{arrow("symbol")}</th>
              <th onClick={() => toggleSort("name")}>名称{arrow("name")}</th>
              <th onClick={() => toggleSort("abs_rho1")}>|ρ(1)|{arrow("abs_rho1")}</th>
              <th onClick={() => toggleSort("rho1")}>ρ(1){arrow("rho1")}</th>
              <th onClick={() => toggleSort("vr2")}>VR(2){arrow("vr2")}</th>
              <th title="VR(5)/VR(10)">VR(5/10)</th>
              <th onClick={() => toggleSort("hurst")}>Hurst{arrow("hurst")}</th>
            </tr></thead>
            <tbody>
              {sorted.map((r) => {
                const vr5 = r.vr && r.vr[1], vr10 = r.vr && r.vr[2];
                return (
                  <tr key={r.symbol} style={{ cursor: "pointer" }} onClick={() => setSymbol(r.symbol)}>
                    <td className="muted">{r.rank}</td>
                    <td><b>{r.symbol}</b></td>
                    <td className="muted">{r.name}</td>
                    <td>{fixed3(r.abs_rho1)}</td>
                    <td className={r.rho1 != null && r.rho1 >= 0 ? "pos" : "neg"}>{rho(r.rho1)}</td>
                    <td className={r.vr2 != null && r.vr2 >= 1 ? "pos" : "neg"}>{vr(r.vr2)}</td>
                    <td className="muted">{vr(vr5)}/{vr(vr10)}</td>
                    <td className="muted">{fixed3(r.hurst)}</td>
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
