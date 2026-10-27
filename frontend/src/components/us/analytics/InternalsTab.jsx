// 市场宽度时序 tab —— /market/internals（后端固定 ma_short=50 / ma_long=200 / new_high=20）。
// 展示口径移植自开源参考实现的 InternalsPage：体制横幅 + 指标卡 + 6 图 + Zweig 推力事件表。
import { useEffect, useMemo, useState } from "react";
import { fetchUsAnalytics } from "../../../api/usAnalytics";
import LineChart from "../LineChart.jsx";
import { Stat, ChartCard, RegimeBanner } from "./shared.jsx";
import {
  toLine, num, int0, pct1, signed1, ymd, bandOn,
} from "../../../lib/us/analyticsFmt";

// Zweig 推力阈值（与后端 params.thrust_low/high 一致）。
const THRUST_LOW = 0.40;
const THRUST_HIGH = 0.615;

// 宽度健康度体制：参与度(%站上MA50) + McClellan(宽度动量) + 新高/新低(领导力)综合判定。
function regime(latest) {
  if (!latest) return { key: "n/a", label: "—", tone: "", desc: "无数据" };
  const p = num(latest.pct_above_ma_short);
  const mcc = num(latest.mcclellan);
  const nh = num(latest.new_highs) ?? 0;
  const nl = num(latest.new_lows) ?? 0;
  if (p != null && p < 0.30) return { key: "crisis", label: "广度崩塌", tone: "neg",
    desc: "不足 30% 标的站上 MA50，参与度崩塌——价格通常滞后跟随。" };
  if (mcc != null && mcc < -40) return { key: "crisis", label: "广度崩塌", tone: "neg",
    desc: "McClellan 深度为负（<" + mcc.toFixed(0) + "），下跌家数远超上涨。" };
  if (p != null && p >= 0.70 && mcc != null && mcc > 0 && nh >= nl * 2)
    return { key: "strong_bull", label: "强势·广参与", tone: "pos",
      desc: "≥70% 站上 MA50、McClellan 为正、新高引领——广度确认上涨。" };
  if (p != null && p >= 0.55 && mcc != null && mcc > 0)
    return { key: "bull", label: "健康上行", tone: "pos",
      desc: "多数标的站上 MA50 且宽度动量为正。" };
  if (p != null && p >= 0.50 && mcc != null && mcc < 0)
    return { key: "caution", label: "广度背离·警惕", tone: "warn",
      desc: "参与度尚可但 McClellan 转负——上涨动能收窄，常领先价格见顶。" };
  if (p != null && p < 0.50 && mcc != null && mcc < 0)
    return { key: "bear", label: "广度转弱", tone: "neg",
      desc: "多数标的跌破 MA50 且宽度动量为负。" };
  return { key: "neutral", label: "中性·拉锯", tone: "",
    desc: "宽度指标多空交织，无明确方向。" };
}

export default function InternalsTab() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let on = true;
    setErr("");
    fetchUsAnalytics("/market/internals")
      .then((d) => { if (on) setData(d); })
      .catch((e) => { if (on) setErr(String(e?.message || e)); });
    return () => { on = false; };
  }, []);

  const reg = useMemo(() => regime(data?.latest), [data]);
  if (err) return <div className="spinner">宽度数据加载失败：{err}</div>;
  if (!data) return <div className="spinner">加载市场宽度数据中…</div>;

  const latest = data.latest || {};
  const series = data.series || [];
  const adLine = toLine(series, "ad_cum");
  const aboveShort = toLine(series, "pct_above_ma_short");
  const aboveLong = toLine(series, "pct_above_ma_long");
  const newHi = toLine(series, "new_highs");
  const newLo = toLine(series, "new_lows");
  const thrust = toLine(series, "thrust_ratio");
  const hiLo = toLine(series.map((p) => ({ time: p.time, value: num(p.new_highs) - num(p.new_lows) })));
  const mccPos = [], mccNeg = [];
  for (const p of series) {
    const v = num(p.mcclellan);
    if (v == null) continue;
    (v >= 0 ? mccPos : mccNeg).push({ time: p.time, value: v });
  }
  const thrusts = data.thrusts || [];

  return (
    <div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        市场宽度时序（{data.n_days} 个交易日）。自上而下的择时视角——<b>A/D 线</b>、<b>McClellan 震荡</b>、
        <b>%站上均线</b>、<b>新高/新低</b>、<b>Zweig 广度推力</b>。判断「广度是否确认价格」。
      </div>

      <RegimeBanner label={reg.label} tone={reg.tone} desc={reg.desc} />

      <div className="stats">
        <Stat label="上涨 / 下跌" value={`${int0(latest.adv)} / ${int0(latest.dec)}`} sub={`平 ${int0(latest.unc)}`} />
        <Stat label="涨家占比" value={pct1(latest.adv_ratio)}
          tone={latest.adv_ratio >= 0.55 ? "pos" : latest.adv_ratio <= 0.45 ? "neg" : ""} />
        <Stat label="McClellan" value={signed1(latest.mcclellan)}
          tone={latest.mcclellan > 0 ? "pos" : latest.mcclellan < 0 ? "neg" : ""} sub="宽度动量 EMA19-39" />
        <Stat label="% 站上 MA50" value={pct1(latest.pct_above_ma_short)}
          tone={latest.pct_above_ma_short >= 0.6 ? "pos" : latest.pct_above_ma_short <= 0.4 ? "neg" : ""} sub="参与度" />
        <Stat label="% 站上 MA200" value={pct1(latest.pct_above_ma_long)}
          tone={latest.pct_above_ma_long >= 0.6 ? "pos" : latest.pct_above_ma_long <= 0.4 ? "neg" : ""} sub="结构性" />
        <Stat label="20日新高 / 新低" value={`${int0(latest.new_highs)} / ${int0(latest.new_lows)}`} sub="领导力 / 抛压" />
        <Stat label="推力比(10dEMA)" value={pct1(latest.thrust_ratio)}
          tone={latest.thrust_ratio > THRUST_HIGH ? "pos" : latest.thrust_ratio < THRUST_LOW ? "neg" : ""}
          sub={`${THRUST_LOW}–${THRUST_HIGH} 推力带`} />
        <Stat label="推力事件数" value={thrusts.length} sub="全历史检测" />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))", gap: 12 }}>
        <ChartCard title="A/D 线 · 涨跌家数累计"
          desc="每日(上涨家数-下跌家数)的累计。持续上行=广度健康确认价格；顶背离=预警。">
          <LineChart data={adLine} color="#4f93e7" height={200} />
        </ChartCard>

        <ChartCard title="McClellan 震荡指标（>0 多头 / <0 空头）"
          desc="(adv-dec) 的 EMA19-EMA39。过零=动量转换。">
          <LineChart series={[
            { data: mccPos, color: "#26a69a", lineWidth: 2 },
            { data: mccNeg, color: "#ef5350", lineWidth: 2 },
          ]} height={200} />
        </ChartCard>

        <ChartCard title="% 站上均线 · MA50 / MA200"
          desc="绿 = % 站上 MA50（参与度，>70% 强势 / <30% 崩塌）；暗绿 = % 站上 MA200（结构性）。">
          <LineChart series={[
            { data: aboveShort, color: "#26a69a", lineWidth: 2 },
            { data: aboveLong, color: "#3ba776", lineWidth: 1.5 },
          ]} height={200} />
        </ChartCard>

        <ChartCard title="20日新高 / 新低家数"
          desc="绿=新高（领导力），红=新低（抛压）。新高持续多于新低=健康；反转时新低急升=预警。">
          <LineChart series={[
            { data: newHi, color: "#26a69a", lineWidth: 2 },
            { data: newLo, color: "#ef5350", lineWidth: 2 },
          ]} height={200} />
        </ChartCard>

        <ChartCard title={`Zweig 广度推力比 · ${THRUST_LOW}–${THRUST_HIGH} 带为推力区`}
          desc="涨家占比的 10 日 EMA。10 日内从低位升穿推力带 = 罕见强势启动信号。">
          <LineChart series={[
            { data: thrust, color: "#ffd166", lineWidth: 2 },
            { data: bandOn(thrust, THRUST_HIGH), color: "rgba(38,166,154,0.4)", lineWidth: 1 },
            { data: bandOn(thrust, THRUST_LOW), color: "rgba(239,83,80,0.4)", lineWidth: 1 },
          ]} height={180} />
        </ChartCard>

        <ChartCard title="新高-新低净额（领导力净扩散）"
          desc="持续为正=广度扩张；转负=扩散萎缩。">
          <LineChart data={hiLo} color="#4dd0e1" height={180} />
        </ChartCard>
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        <h3>Zweig 广度推力事件 · 10日内推力比从 &lt;{THRUST_LOW} 升至 &gt;{THRUST_HIGH}</h3>
        <div className="scroll" style={{ maxHeight: 260 }}>
          <table className="data">
            <thead><tr><th>#</th><th>日期</th><th>触发时推力比</th><th>窗口低点</th><th>解读</th></tr></thead>
            <tbody>
              {thrusts.length === 0 && (
                <tr><td colSpan={5} className="muted" style={{ textAlign: "center", padding: 16 }}>
                  区间内无推力事件（该信号本就稀有，历史上数年一遇；出现时多为重要中期底部）。
                </td></tr>
              )}
              {thrusts.map((t, i) => (
                <tr key={t.time}>
                  <td>{i + 1}</td>
                  <td>{ymd(t.time)}</td>
                  <td className="pos">{pct1(t.ratio)}</td>
                  <td>{pct1(t.window_low)}</td>
                  <td className="muted">宽度从极弱急剧转为强势参与，常标志中长期底部</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
