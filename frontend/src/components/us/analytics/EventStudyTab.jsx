// 财报事件研究 tab —— /fund/eventstudy?symbol=&pre=&post=。
// symbol 省略 = 全池聚合 AAR/CAAR；有 symbol = 仅该票事件聚合 + 逐事件明细
// （symbol_info.events 含预期/实际 EPS）。事件时间轴为合成时间戳：
// t=0 锚定 2000-01-01，offset k → +k 天（LineChart 只吃时间戳）。
import { useEffect, useMemo, useState } from "react";
import { fetchUsAnalytics } from "../../../api/usAnalytics";
import LineChart from "../LineChart.jsx";
import { Stat, RegimeBanner, useSymbols } from "./shared.jsx";
import { num } from "../../../lib/us/analyticsFmt";

const PRE_OPTS = [5, 10, 20];
const POST_OPTS = [10, 20, 30, 60];
const BASE_TS = Math.floor(Date.UTC(2000, 0, 1) / 1000); // t=0 锚点（合成事件时间轴）
const DAY = 86400;
// 漂移方向判别的最小量级（0.1%）：低于此视为微弱，不贴 PEAD/反转标签。
const DRIFT_EPS = 0.001;

// 横幅：读 CAAR 形态——即时反应 + 财报后漂移是顺势(PEAD)/反转/微弱。
// 如实三分，不预设 PEAD 必然成立；tone 按全样本漂移方向。
export function regime(d) {
  if (!d || !d.caar_all?.length || !d.car)
    return { key: "na", label: "—", tone: "", desc: "无事件数据" };
  const allR = num(d.car.all?.reaction);
  const allD = num(d.car.all?.drift);
  const bD = num(d.car.beat?.drift);
  const mD = num(d.car.miss?.drift);
  const bR = num(d.car.beat?.reaction);
  const mR = num(d.car.miss?.reaction);
  if (allR == null || allD == null || bD == null || mD == null)
    return { key: "na", label: "—", tone: "", desc: "反应/漂移数据不足。" };

  const bSign = bD > DRIFT_EPS ? 1 : bD < -DRIFT_EPS ? -1 : 0;
  const mSign = mD > DRIFT_EPS ? 1 : mD < -DRIFT_EPS ? -1 : 0;
  let key, label;
  if (bSign === 1 && mSign === -1) { key = "pead"; label = "财报后顺势漂移（PEAD）"; }
  else if (bSign === -1 && mSign === 1) { key = "reversal"; label = "财报后反转（反应后回落/反弹）"; }
  else { key = "weak"; label = "财报后漂移微弱/混合"; }

  const tone = allD >= 0 ? "pos" : "neg";
  const reactWord = Math.abs(allR) >= 0.005 ? "显著" : "温和";
  const driftWord = key === "pead" ? "顺势漂移" : key === "reversal" ? "反转" : "微弱漂移";
  const desc = `${d.n_all} 个事件（${d.n_beat} 超预期 / ${d.n_miss} 不及预期${d.n_unk ? ` / ${d.n_unk} 惊喜未知` : ""}）：`
    + `公告窗口 [-1,+1] 平均异常收益 ${(allR * 100).toFixed(2)}%（${reactWord}反应）；`
    + `财报后 [+1,+${d.post}] ${driftWord} ${allD >= 0 ? "+" : ""}${(allD * 100).toFixed(2)}%`
    + `（beat ${bD >= 0 ? "+" : ""}${(bD * 100).toFixed(2)}% / miss ${mD >= 0 ? "+" : ""}${(mD * 100).toFixed(2)}%）。`;
  return { key, label, tone, allReaction: allR, allDrift: allD, beatDrift: bD, missDrift: mD,
    beatReaction: bR, missReaction: mR, desc };
}

// AR/AAR/CAR 小数 → 百分号。
const pct2 = (v) => (num(v) == null ? "—" : (v * 100).toFixed(2) + "%");
const signedPct2 = (v) => (num(v) == null ? "—" : (v >= 0 ? "+" : "") + (v * 100).toFixed(2) + "%");
// surprise_pct 已是百分数（如 31.2 = +31.2%）。
const surpriseFmt = (v) => (num(v) == null ? "—" : (v >= 0 ? "+" : "") + v.toFixed(1) + "%");

// offset 对齐数组（index 0 = offset -pre）→ LineChart [{time,value}]，
// time = 合成事件时间戳（offset k → 2000-01-01 + k 天），跳过 null。
function toEvtLine(arr, offsets) {
  const out = [];
  for (let i = 0; i < (arr || []).length; i++) {
    const v = num(arr[i]);
    if (v == null) continue;
    out.push({ time: BASE_TS + offsets[i] * DAY, value: v });
  }
  return out;
}

const driftTone = (v) => (num(v) == null ? "" : v >= 0 ? "pos" : "neg");

export default function EventStudyTab() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const [symbol, setSymbol] = useState("");            // "" = 全市场聚合
  const [pre, setPre] = useState(10);
  const [post, setPost] = useState(30);
  const [bucket, setBucket] = useState("all");
  const symbols = useSymbols();

  useEffect(() => {
    let on = true;
    setErr("");
    setLoading(true);
    fetchUsAnalytics("/fund/eventstudy", { symbol: symbol || undefined, pre, post })
      .then((d) => { if (on) { setData(d); setLoading(false); } })
      .catch((e) => { if (on) { setErr(String(e?.message || e)); setLoading(false); } });
    return () => { on = false; };
  }, [symbol, pre, post]);

  const offsets = data?.offsets || [];
  const ev = data?.events || [];
  const si = data?.symbol_info;
  const vd = useMemo(() => regime(data), [data]);

  const caarSeries = useMemo(() => (data ? [
    { data: toEvtLine(data.caar_all, offsets), color: "#4f93e7", lineWidth: 2 },
    { data: toEvtLine(data.caar_beat, offsets), color: "#26a69a", lineWidth: 1.5 },
    { data: toEvtLine(data.caar_miss, offsets), color: "#ef5350", lineWidth: 1.5 },
  ] : []), [data, offsets]);
  const aarSeries = useMemo(() => (data ? [
    { data: toEvtLine(data.aar_all, offsets), color: "#4f93e7", lineWidth: 1.5 },
    { data: toEvtLine(data.aar_beat, offsets), color: "#26a69a", lineWidth: 1 },
    { data: toEvtLine(data.aar_miss, offsets), color: "#ef5350", lineWidth: 1 },
  ] : []), [data, offsets]);

  // 事件表：选中标的 → 该票历史（含预期/实际）；否则全市场最近 30 条。按公告日降序。
  const tableRows = useMemo(() => {
    let rows;
    if (symbol && si?.events?.length) {
      rows = si.events.map((e) => ({ ...e, symbol }));
    } else {
      rows = [...ev];
    }
    rows.sort((a, b) => (a.date < b.date ? 1 : -1));
    if (!symbol) rows = rows.slice(0, 30);
    if (bucket !== "all") {
      rows = rows.filter((e) => {
        const s = num(e.surprise_pct);
        return bucket === "beat" ? s != null && s > 0 : s != null && s < 0;
      });
    }
    return rows;
  }, [symbol, si, ev, bucket]);

  if (err) return <div className="spinner">事件研究数据加载失败：{err}</div>;
  if (loading && !data) return <div className="spinner">加载财报事件研究数据中…</div>;
  if (!data) return <div className="spinner">加载财报事件研究数据中…</div>;

  const car = data.car || { all: {}, beat: {}, miss: {} };

  return (
    <div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        财报事件研究（历史公告共 {data.total_events} 条，落入收益窗口 {data.n_all} 个事件，
        {data.n_symbols} 只标的，{data.date_min || "—"} → {data.date_max || "—"}）。
        把每只标的的<b>历史财报公告</b>当事件，对齐<b>事件时间</b>（t=0=公告日后首个交易日），算
        <b>异常收益 AR = 个股收益 − 等权市场收益</b>，跨事件平均出 AAR/CAAR 曲线，按惊喜方向分桶。
        回答「市场对财报是即刻消化、还是之后漂移/反转」。
        {symbol ? "（当前仅统计选中标的的事件）" : ""}
      </div>

      {/* 控制 + 判读横幅 */}
      <RegimeBanner label={vd.label} tone={vd.tone} desc={vd.desc}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span style={{ fontSize: 13 }}>标的</span>
          <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
            <option value="">全市场</option>
            {(symbols.length ? symbols : ["AAPL"]).map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <span style={{ fontSize: 13, marginLeft: 8 }}>前窗</span>
          <select value={pre} onChange={(e) => setPre(Number(e.target.value))}>
            {PRE_OPTS.map((p) => <option key={p} value={p}>{p} 日</option>)}
          </select>
          <span style={{ fontSize: 13 }}>后窗</span>
          <select value={post} onChange={(e) => setPost(Number(e.target.value))}>
            {POST_OPTS.map((p) => <option key={p} value={p}>{p} 日</option>)}
          </select>
          {loading && <span className="muted" style={{ fontSize: 12 }}>计算中…</span>}
        </div>
      </RegimeBanner>

      {/* CAAR / AAR 曲线 */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))", gap: 12 }}>
        <div className="card">
          <h3 style={{ marginBottom: 4 }}>累计平均异常收益 CAAR（事件时间）</h3>
          <LineChart series={caarSeries} height={240} />
          <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
            蓝=全部({data.n_all}) 绿=超预期({data.n_beat}) 红=不及预期({data.n_miss})。
            横轴 = 事件日 t（0=公告日，合成时间戳）。曲线在 0 附近跳升/跳降 = 即时反应；
            之后的斜率 = 财报后漂移（顺势延续=PEAD、反向=反转）。
          </div>
        </div>
        <div className="card">
          <h3 style={{ marginBottom: 4 }}>逐日平均异常收益 AAR</h3>
          <LineChart series={aarSeries} height={240} />
          <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
            每个事件日 t 的平均异常收益（AR 跨事件均值）。t=0/t+1 处的尖峰 = 财报当天的反应幅度；
            之后的正负 = 漂移的逐日方向与速率。
          </div>
        </div>
      </div>

      {/* 分组 CAR 统计 */}
      <div className="card" style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center", marginTop: 12 }}>
        <b style={{ fontSize: 15 }}>分组 CAR</b>
        <Stat label="全部 即时反应" value={signedPct2(car.all?.reaction)} tone={driftTone(car.all?.reaction)}
          sub={`[-1,+1] · n=${data.n_all}`} />
        <Stat label="全部 后漂移" value={signedPct2(car.all?.drift)} tone={driftTone(car.all?.drift)}
          sub={`[+1,+${post}]`} />
        <Stat label="超预期 反应/漂移" value={`${signedPct2(car.beat?.reaction)} / ${signedPct2(car.beat?.drift)}`}
          tone={driftTone(car.beat?.drift)} sub={`beat · n=${data.n_beat}`} />
        <Stat label="不及预期 反应/漂移" value={`${signedPct2(car.miss?.reaction)} / ${signedPct2(car.miss?.drift)}`}
          tone={driftTone(car.miss?.drift)} sub={`miss · n=${data.n_miss}`} />
      </div>

      {/* PEAD/反转 对照 */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 12, marginTop: 12 }}>
        <div className="card">
          <h3 style={{ marginBottom: 6 }}>超预期（beat）财报后漂移</h3>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
            <span className={driftTone(car.beat?.drift)} style={{ fontSize: 28, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
              {signedPct2(car.beat?.drift)}
            </span>
            <span className="muted" style={{ fontSize: 12 }}>CAR[+1,+{post}]，n={data.n_beat}</span>
          </div>
          <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>正=超预期后继续涨（PEAD 顺势）；负=涨后回落（反转）。</div>
        </div>
        <div className="card">
          <h3 style={{ marginBottom: 6 }}>不及预期（miss）财报后漂移</h3>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
            <span className={driftTone(car.miss?.drift)} style={{ fontSize: 28, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
              {signedPct2(car.miss?.drift)}
            </span>
            <span className="muted" style={{ fontSize: 12 }}>CAR[+1,+{post}]，n={data.n_miss}</span>
          </div>
          <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>负=不及预期后继续跌（PEAD 顺势）；正=跌后反弹（反转）。</div>
        </div>
      </div>

      {/* 事件表 */}
      <div className="card" style={{ marginTop: 12 }}>
        <h3 style={{ marginBottom: 6 }}>
          {symbol && si ? `${si.symbol} 历史财报事件（${si.n_events}）` : "全市场最近财报事件（按公告日降序，最近 30 条）"}
          <select value={bucket} onChange={(e) => setBucket(e.target.value)} style={{ marginLeft: 12 }}>
            <option value="all">全部</option>
            <option value="beat">仅超预期</option>
            <option value="miss">仅不及预期</option>
          </select>
        </h3>
        <div className="scroll" style={{ maxHeight: 420 }}>
          <table className="data">
            <thead><tr>
              <th>公告日</th>
              {!symbol && <th>代码</th>}
              <th>EPS 惊喜</th>
              {symbol && si && <th>预期</th>}
              {symbol && si && <th>实际</th>}
              <th>即时反应 CAR[-1,+1]</th>
              <th>后漂移 CAR[+1,+{post}]</th>
            </tr></thead>
            <tbody>
              {tableRows.length === 0 && (
                <tr><td colSpan={symbol && si ? 7 : 6} className="muted" style={{ textAlign: "center", padding: 16 }}>
                  当前筛选下无事件（窗口越界/无惊喜数据的公告已剔除：{data.n_excluded_window || 0} 窗口越界、
                  {data.n_excluded_outside || 0} 区间外、{data.n_excluded_nosym || 0} 无行情）。
                </td></tr>
              )}
              {tableRows.map((e, i) => (
                <tr key={(e.symbol || "") + e.date + i}>
                  <td>{e.date}</td>
                  {!symbol && <td><b>{e.symbol}</b></td>}
                  <td className={num(e.surprise_pct) != null && e.surprise_pct >= 0 ? "pos" : "neg"}>
                    {surpriseFmt(e.surprise_pct)}
                  </td>
                  {symbol && si && <td className="muted">{num(e.estimate) != null ? e.estimate.toFixed(2) : "—"}</td>}
                  {symbol && si && <td className="muted">{num(e.reported) != null ? e.reported.toFixed(2) : "—"}</td>}
                  <td className={driftTone(e.car_reaction)} style={{ fontVariantNumeric: "tabular-nums" }}>
                    {signedPct2(e.car_reaction)}
                  </td>
                  <td className={driftTone(e.car_drift)} style={{ fontVariantNumeric: "tabular-nums" }}>
                    {signedPct2(e.car_drift)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
          惊喜未知的事件计入「全部」但不出现在 beat/miss 分桶中（{data.n_unk || 0} 条）。
        </div>
      </div>
    </div>
  );
}
