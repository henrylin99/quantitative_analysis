// 隔夜与跳空 tab —— /market/overnight?symbol=（路由不透传 window，滚动窗固定后端默认 126 日）。
// 口径移植自开源参考实现的 OvernightPage：日收益拆成隔夜(open/前收−1)与日内(close/open−1)，
// 累积恒等 cum_total == cum_overnight · cum_intraday；方差分解 overnight+intraday+cross == 1。
import { useEffect, useMemo, useState } from "react";
import { fetchUsAnalytics } from "../../../api/usAnalytics";
import LineChart from "../LineChart.jsx";
import { Stat, ChartCard, RegimeBanner, useSymbols, SymbolSelect } from "./shared.jsx";
import {
  toLine, sortRows, pct1, sharpe, share1, signedShare1, num,
} from "../../../lib/us/analyticsFmt";

const shTone = (v) => (v == null ? "" : v >= 1 ? "pos" : v < 0 ? "neg" : "");
const annTone = (v) => (v == null ? "" : v >= 0 ? "pos" : "neg");

// 体制 = 隔夜/日内主导(夏普差>0.3) × 缺口行为(回补率)。tone 按隔夜漂移强度着色。
function regime(si) {
  if (!si) return { key: "n/a", label: "—", tone: "", desc: "无个股数据" };
  const onS = num(si.overnight_sharpe);
  const inS = num(si.intraday_sharpe);
  const fr = num(si.fill_rate);
  if (onS == null || inS == null)
    return { key: "neutral", label: "数据不足", tone: "", desc: "隔夜/日内夏普数据不足。" };
  const diff = onS - inS;
  const dom = diff > 0.3 ? { key: "overnight", label: "隔夜驱动" }
    : diff < -0.3 ? { key: "intraday", label: "日内驱动" }
    : { key: "balanced", label: "隔夜·日内均衡" };
  const gap = fr == null ? { key: "nogap", label: "缺口数据不足" }
    : fr > 0.6 ? { key: "fade", label: "跳空常回补" }
    : fr < 0.45 ? { key: "trend", label: "跳空常延续" }
    : { key: "mixed", label: "跳空回补参半" };
  const tone = onS >= 0.5 ? "pos" : onS < 0 ? "neg" : "";
  const onTxt = sharpe(onS), inTxt = sharpe(inS);
  const domWord = dom.key === "overnight"
    ? `隔夜(年化 ${pct1(si.ann_overnight)}、Sharpe ${onTxt})显著强于日内(${pct1(si.ann_intraday)}、${inTxt})——收益主要在盘外累积`
    : dom.key === "intraday"
    ? `日内(年化 ${pct1(si.ann_intraday)}、Sharpe ${inTxt})显著强于隔夜(${pct1(si.ann_overnight)}、${onTxt})——收益来自交易时段`
    : `隔夜与日内风险调整后相近(Sharpe ${onTxt} vs ${inTxt})，无单一主导`;
  const gapWord = gap.key === "fade" ? "跳空多数当日回补"
    : gap.key === "trend" ? "跳空多数延续、较少回补"
    : gap.key === "mixed" ? "跳空回补与否参半" : "缺口样本不足";
  return { key: dom.key + "_" + gap.key, label: dom.label + " · " + gap.label, tone,
    desc: domWord + "；" + gapWord + (fr == null ? "。" : `（回补率 ${pct1(fr)}）。`) };
}

// 方差分解横向条（中心 0 线，份额可因交叉项超界为负）。
function ShareBar({ label, v, color }) {
  const val = num(v) ?? 0;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, margin: "4px 0", fontSize: 12 }}>
      <span style={{ width: 72 }}>{label}</span>
      <div style={{ flex: 1, height: 12, background: "rgba(255,255,255,0.06)", borderRadius: 2, position: "relative" }}>
        <div style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 1, background: "rgba(255,255,255,0.15)" }} />
        <div style={{
          position: "absolute", top: 0, bottom: 0,
          left: val >= 0 ? "50%" : (50 + val * 50) + "%",
          width: (Math.abs(val) * 50) + "%",
          background: color, borderRadius: 2,
        }} />
      </div>
      <span style={{ width: 60, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{signedShare1(val)}</span>
    </div>
  );
}

export default function OvernightTab() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [symbol, setSymbol] = useState("AAPL");
  const [sortKey, setSortKey] = useState("rank");
  const [sortDir, setSortDir] = useState("asc");
  const symbols = useSymbols();

  useEffect(() => {
    let on = true;
    setErr("");
    fetchUsAnalytics("/market/overnight", { symbol: symbol || undefined })
      .then((d) => { if (on) setData(d); })
      .catch((e) => { if (on) setErr(String(e?.message || e)); });
    return () => { on = false; };
  }, [symbol]);

  const si = data?.symbol_info || null;
  const mkt = data?.market || null;
  const ranking = useMemo(() => data?.ranking || [], [data]);
  const vd = useMemo(() => regime(si), [si]);
  const sorted = useMemo(() => sortRows(ranking, sortKey, sortDir), [ranking, sortKey, sortDir]);

  if (err) return <div className="spinner">隔夜数据加载失败：{err}</div>;
  if (!data) return <div className="spinner">加载隔夜与跳空数据中…</div>;

  const top = ranking.slice(0, 5);
  const bottom = [...ranking].slice(-5).reverse();

  // 市场累积曲线：隔夜 / 日内 / 总。
  const mktOn = toLine(data.mkt_cum_on_series);
  const mktIn = toLine(data.mkt_cum_in_series);
  const mktTot = toLine(data.mkt_cum_total_series);
  // 个股累积 + 滚动隔夜夏普。
  const symOn = si ? toLine(si.cum_on_series) : [];
  const symIn = si ? toLine(si.cum_in_series) : [];
  const symTot = si ? toLine(si.cum_total_series) : [];
  const shLine = si ? toLine(si.on_sharpe_series) : [];
  const sh0 = shLine.length
    ? [{ time: shLine[0].time, value: 0 }, { time: shLine[shLine.length - 1].time, value: 0 }]
    : [];

  const toggleSort = (k) => {
    if (k === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(k); setSortDir(k === "symbol" || k === "name" ? "asc" : "desc"); }
  };
  const arrow = (k) => (k === sortKey ? (sortDir === "asc" ? " ▲" : " ▼") : "");

  return (
    <div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        隔夜与跳空 / <b>隔夜效应</b>（{data.n_names} 只标的，{data.n_days} 个交易日）。把每日收益拆成
        <b> 隔夜</b>（开盘/前收−1）与 <b>日内</b>（收盘/开盘−1），看收益是<b>盘外累积还是盘中赚取</b>。
        累积恒等：cum_total == cum_overnight · cum_intraday。滚动窗固定 {data.window} 日。
      </div>

      <RegimeBanner label={si ? `${si.symbol} · ${vd.label}` : vd.label} tone={vd.tone} desc={vd.desc}>
        <span style={{ fontSize: 14 }}>标的</span>
        <SymbolSelect symbols={symbols} value={symbol} onChange={setSymbol} />
      </RegimeBanner>

      {/* 市场隔夜效应头条图 */}
      <ChartCard title="等权市场累积收益：隔夜 vs 日内 vs 总（隔夜漂移图）"
        desc="每日全市场等权均值收益的 Π(1+r) 累积。隔夜线（绿）持续高于日内线（蓝）= 隔夜效应：收益主要在盘外累积。三条线各自累积。">
        <LineChart series={[
          { data: mktOn, color: "#26a69a", lineWidth: 2 },
          { data: mktIn, color: "#42a5f5", lineWidth: 2 },
          { data: mktTot, color: "#ab47bc", lineWidth: 1 },
        ]} height={230} />
      </ChartCard>

      {/* 市场统计行 */}
      <div className="muted" style={{ fontSize: 11, margin: "10px 0 8px" }}>等权市场基准（全市场日收益均值，{mkt?.n ?? "—"} 日）</div>
      <div className="stats">
        <Stat label="年化隔夜" value={pct1(mkt?.ann_overnight)} tone={annTone(mkt?.ann_overnight)} sub="mean(隔夜)·252" />
        <Stat label="年化日内" value={pct1(mkt?.ann_intraday)} tone={annTone(mkt?.ann_intraday)} sub="mean(日内)·252" />
        <Stat label="年化总收益" value={pct1(mkt?.ann_total)} tone={annTone(mkt?.ann_total)} sub="mean(日收益)·252" />
        <Stat label="隔夜 Sharpe" value={sharpe(mkt?.overnight_sharpe)} tone={shTone(mkt?.overnight_sharpe)} sub="盘外漂移" />
        <Stat label="日内 Sharpe" value={sharpe(mkt?.intraday_sharpe)} tone={shTone(mkt?.intraday_sharpe)} sub="盘中收益" />
        <Stat label="隔夜方差份额" value={share1(mkt?.overnight_share)} sub="Var(ln_on)/Var(ln_da)" />
      </div>

      {/* 个股统计行 */}
      {si && (
        <>
          <div className="muted" style={{ fontSize: 11, margin: "10px 0 8px" }}>
            {si.symbol} · 滚动 {si.window} 日（{si.n} 个日收益）· 隔夜 Sharpe 排名 #{si.rank}/{data.n_stocks}
          </div>
          <div className="stats">
            <Stat label="年化隔夜" value={pct1(si.ann_overnight)} tone={annTone(si.ann_overnight)} sub="mean(隔夜)·252" />
            <Stat label="年化日内" value={pct1(si.ann_intraday)} tone={annTone(si.ann_intraday)} sub="mean(日内)·252" />
            <Stat label="年化总收益" value={pct1(si.ann_total)} tone={annTone(si.ann_total)} sub="mean(日收益)·252" />
            <Stat label="隔夜 Sharpe" value={sharpe(si.overnight_sharpe)} tone={shTone(si.overnight_sharpe)} sub="排名指标" />
            <Stat label="日内 Sharpe" value={sharpe(si.intraday_sharpe)} tone={shTone(si.intraday_sharpe)} sub="盘中对比" />
            <Stat label="隔夜方差份额" value={share1(si.overnight_share)} sub="Var(ln_on)/Var(ln_da)" />
          </div>
        </>
      )}

      {/* 个股累积 + 滚动隔夜夏普 */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))", gap: 12, marginTop: 8 }}>
        <ChartCard title={`${si ? si.symbol : ""} 累积收益：隔夜 vs 日内 vs 总`}
          desc="Π(1+r) 累积。隔夜线主导 = 该票收益盘外累积。">
          {si ? (
            <LineChart series={[
              { data: symOn, color: "#26a69a", lineWidth: 2 },
              { data: symIn, color: "#42a5f5", lineWidth: 2 },
              { data: symTot, color: "#ab47bc", lineWidth: 1 },
            ]} height={210} />
          ) : <div className="muted" style={{ fontSize: 12 }}>选择标的。</div>}
        </ChartCard>

        <ChartCard title={`${si ? si.symbol : ""} 滚动隔夜 Sharpe（0 参考线）`}
          desc={`trailing ${data.window} 日 mean(隔夜)/std(隔夜)·√252。持续 >0 = 该窗口隔夜漂移稳定为正；跌破 0 = 隔夜不再贡献。`}>
          {si ? (
            <LineChart series={[
              { data: shLine, color: "#26a69a", lineWidth: 2 },
              { data: sh0, color: "#888", lineWidth: 1 },
            ]} height={210} />
          ) : <div className="muted" style={{ fontSize: 12 }}>选择标的。</div>}
        </ChartCard>
      </div>

      {/* 方差分解 + 缺口统计 */}
      {si && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 12, marginTop: 12 }}>
          <div className="card" style={{ padding: 10 }}>
            <h3 style={{ marginBottom: 6 }}>日收益方差分解（对数收益）</h3>
            <ShareBar label="隔夜份额" v={si.overnight_share} color="#ab47bc" />
            <ShareBar label="日内份额" v={si.intraday_share} color="#26a69a" />
            <ShareBar label="交叉项" v={si.cross_term} color="#ff9800" />
            <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
              三项之和 == 1。负交叉项 = 隔夜跳空后盘中反向回补（收益互相抵消）。
            </div>
          </div>

          <div className="card" style={{ padding: 10 }}>
            <h3 style={{ marginBottom: 6 }}>跳空统计</h3>
            <div className="stats" style={{ gridTemplateColumns: "repeat(3, 1fr)", marginBottom: 0 }}>
              <Stat label="跳空频率" value={pct1(si.gap_freq)} sub="|开盘/前收−1|>1e-6" />
              <Stat label="回补率" value={pct1(si.fill_rate)} sub="上跳空:低≤前收" />
              <Stat label="平均幅度" value={pct1(si.mean_abs_gap)} sub="|跳空|均值" />
            </div>
            <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
              回补率高 = 跳空当日盘中常回到前收（均值回复）；低 = 跳空常延续（动量）。
            </div>
          </div>
        </div>
      )}

      {/* 隔夜 Sharpe 最高 / 最低 */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 12, margin: "12px 0" }}>
        <div className="card">
          <h3 style={{ marginBottom: 6 }}>隔夜 Sharpe 最高 Top 5（盘外漂移最强）</h3>
          {top.map((r) => (
            <div key={r.symbol} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", cursor: "pointer" }}
              onClick={() => setSymbol(r.symbol)}>
              <span><b>{r.symbol}</b> <span className="muted" style={{ fontSize: 11 }}>
                {r.name} · 年化隔夜 {pct1(r.ann_overnight)} · 回补 {pct1(r.fill_rate)}</span></span>
              <span className="pos">Sharpe {sharpe(r.overnight_sharpe)}</span>
            </div>
          ))}
        </div>
        <div className="card">
          <h3 style={{ marginBottom: 6 }}>隔夜 Sharpe 最低 Bottom 5（隔夜无溢价 / 负漂移）</h3>
          {bottom.map((r) => (
            <div key={r.symbol} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", cursor: "pointer" }}
              onClick={() => setSymbol(r.symbol)}>
              <span><b>{r.symbol}</b> <span className="muted" style={{ fontSize: 11 }}>
                {r.name} · 年化隔夜 {pct1(r.ann_overnight)} · 回补 {pct1(r.fill_rate)}</span></span>
              <span className={r.overnight_sharpe < 0 ? "neg" : ""}>Sharpe {sharpe(r.overnight_sharpe)}</span>
            </div>
          ))}
        </div>
      </div>

      {/* 全市场排名 */}
      <div className="card">
        <h3>全市场隔夜效应排名 · 按隔夜 Sharpe 降序（rank 1 = 盘外漂移最强）</h3>
        <div className="scroll" style={{ maxHeight: 460 }}>
          <table className="data">
            <thead><tr>
              <th onClick={() => toggleSort("rank")}>#{arrow("rank")}</th>
              <th onClick={() => toggleSort("symbol")}>标的{arrow("symbol")}</th>
              <th onClick={() => toggleSort("name")}>名称{arrow("name")}</th>
              <th onClick={() => toggleSort("overnight_sharpe")}>隔夜Sharpe{arrow("overnight_sharpe")}</th>
              <th onClick={() => toggleSort("intraday_sharpe")}>日内Sharpe{arrow("intraday_sharpe")}</th>
              <th onClick={() => toggleSort("ann_overnight")}>年化隔夜{arrow("ann_overnight")}</th>
              <th onClick={() => toggleSort("ann_intraday")}>年化日内{arrow("ann_intraday")}</th>
              <th onClick={() => toggleSort("overnight_share")}>隔夜份额{arrow("overnight_share")}</th>
              <th onClick={() => toggleSort("fill_rate")}>回补率{arrow("fill_rate")}</th>
              <th onClick={() => toggleSort("mean_abs_gap")}>跳空幅度{arrow("mean_abs_gap")}</th>
              <th onClick={() => toggleSort("n")}>样本{arrow("n")}</th>
            </tr></thead>
            <tbody>
              {sorted.map((r) => (
                <tr key={r.symbol} style={{ cursor: "pointer" }} onClick={() => setSymbol(r.symbol)}>
                  <td className="muted">{r.rank}</td>
                  <td><b>{r.symbol}</b></td>
                  <td className="muted">{r.name}</td>
                  <td className={shTone(r.overnight_sharpe)}>{sharpe(r.overnight_sharpe)}</td>
                  <td className={shTone(r.intraday_sharpe)}>{sharpe(r.intraday_sharpe)}</td>
                  <td className={annTone(r.ann_overnight)}>{pct1(r.ann_overnight)}</td>
                  <td className={annTone(r.ann_intraday)}>{pct1(r.ann_intraday)}</td>
                  <td className="muted">{share1(r.overnight_share)}</td>
                  <td className="muted">{pct1(r.fill_rate)}</td>
                  <td className="muted">{pct1(r.mean_abs_gap)}</td>
                  <td className="muted">{r.n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
