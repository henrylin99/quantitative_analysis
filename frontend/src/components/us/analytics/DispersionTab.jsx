// 截面离散度 tab —— /market/dispersion?window=。
// 口径移植自开源参考实现的 DispersionPage：恒等式 mean(r²) = m² + d² 的二阶矩分解，
// 回答「这是不是选股环境」（高离散=收益分化，低离散=联动锁步）。
import { useEffect, useMemo, useState } from "react";
import { analyticsApiFor } from "../../../api/usAnalytics";
import LineChart from "../LineChart.jsx";
import { Stat, ChartCard, RegimeBanner } from "./shared.jsx";
import {
  toLine, disp2, shr0, vol1, fixed3, pct0, num,
} from "../../../lib/us/analyticsFmt";

const WINDOW_OPTS = [40, 60, 90, 126];

// 标准化一条 series（均值0/标准差1）——离散度与 |收益| 量纲不同，标准化后看协同运动。
const zScoreLine = (series) => {
  const vs = series.map((p) => p.value).filter((v) => v != null);
  if (vs.length < 2) return [];
  const m = vs.reduce((s, v) => s + v, 0) / vs.length;
  const sd = Math.sqrt(vs.reduce((s, v) => s + (v - m) ** 2, 0) / vs.length) || 1;
  return series.map((p) => (p.value == null ? null : { time: p.time, value: (p.value - m) / sd }))
    .filter(Boolean);
};

// 体制 = 离散度全历史分位：低=联动锁步(neg)、中=常态、高=选股环境(pos)。
function regime(stats) {
  if (!stats) return { key: "n/a", label: "—", tone: "", desc: "无数据" };
  const d = num(stats.dispersion);
  const dp = num(stats.dispersion_pctile);
  const nx = num(stats.corr_disp_absret);
  if (d == null || dp == null)
    return { key: "neutral", label: "中性", tone: "", desc: "离散度数据不足。" };
  const r = dp < 0.33 ? { key: "lockstep", label: "联动锁步", tone: "neg" }
    : dp < 0.67 ? { key: "normal", label: "分化常态", tone: "" }
    : { key: "stockpick", label: "选股环境", tone: "pos" };
  const dpWord = dp < 0.33 ? "收益趋同·选股难分化" : dp < 0.67 ? "分化适中" : "收益分化·选股空间大";
  const nxWord = nx != null && nx > 0.4
    ? "；大动日离散骤升（离散-|收益|强耦合）"
    : nx != null && nx > 0 ? "；大动日离散略升" : "";
  return { key: r.key, label: r.label, tone: r.tone,
    desc: `截面离散度 ${disp2(d)}（全历史 ${(dp * 100).toFixed(0)}% 分位，${dpWord}）${nxWord}。` };
}

// 特异/平静标的小表。
function CsTable({ title, tone, rows }) {
  return (
    <div>
      <div className={tone} style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>{title}</div>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
        <thead>
          <tr className="muted">
            <th style={{ textAlign: "left", padding: "2px 4px" }}>标的</th>
            <th style={{ textAlign: "right", padding: "2px 4px" }}>特异波动</th>
            <th style={{ textAlign: "right", padding: "2px 4px" }}>总波动</th>
            <th style={{ textAlign: "right", padding: "2px 4px" }}>特异占比</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.symbol} style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
              <td style={{ padding: "2px 4px", fontWeight: 600 }}>{r.symbol}</td>
              <td style={{ padding: "2px 4px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{vol1(r.idio_vol)}</td>
              <td style={{ padding: "2px 4px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{vol1(r.total_vol)}</td>
              <td style={{ padding: "2px 4px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{shr0(r.idio_share)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function DispersionTab({ mk = "us" }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [win, setWin] = useState(60);

  useEffect(() => {
    let on = true;
    setErr("");
    analyticsApiFor(mk).fetch("/market/dispersion", { window: win })
      .then((d) => { if (on) setData(d); })
      .catch((e) => { if (on) setErr(String(e?.message || e)); });
    return () => { on = false; };
  }, [win]);

  const reg = useMemo(() => regime(data), [data]);
  const nexusLine = useMemo(() => (data ? {
    disp: zScoreLine(toLine(data.dispersion_series)),
    absret: zScoreLine(toLine((data.m_series || []).map((p) => ({ time: p.time, value: Math.abs(p.value) })))),
  } : null), [data]);

  if (err) return <div className="spinner">离散度数据加载失败：{err}</div>;
  if (!data) return <div className="spinner">加载离散度数据中…</div>;

  const dispLine = toLine(data.dispersion_series);
  const band = (key) => (data.disp_pcts?.[key] == null ? []
    : dispLine.map((p) => ({ time: p.time, value: data.disp_pcts[key] })));
  const commonLine = toLine(data.common_share_series).map((p) => ({ time: p.time, value: p.value * 100 }));
  const idioLine = toLine(data.common_share_series).map((p) => ({ time: p.time, value: (1 - p.value) * 100 }));

  const dp = num(data.dispersion_pctile);
  const cs = num(data.common_share);
  const nx = num(data.corr_disp_absret);
  const worst = data.most_idiosyncratic?.[0];
  const quiet = data.least_idiosyncratic?.[0];

  return (
    <div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        截面离散度 / 选股环境（{data.n_names} 只标的，{data.n_days} 个交易日，滚动 {win} 日）。回答「<b>这是不是选股环境</b>」。
        高离散=收益分化（选股空间大）；低离散=联动趋同（锁步）。恒等式：<b>mean(r²) = m² + d²</b>（市场共同 + 截面方差）。
      </div>

      <RegimeBanner label={reg.label} tone={reg.tone} desc={reg.desc} />

      <div className="stats">
        <Stat label="截面离散度" value={disp2(data.dispersion)}
          tone={dp != null ? (dp >= 0.67 ? "pos" : dp < 0.33 ? "neg" : "") : ""}
          sub={`全历史 ${pct0(data.dispersion_pctile)} 分位`} />
        <Stat label="共同份额（宏观驱动）" value={shr0(data.common_share)}
          tone={cs != null ? (cs >= 0.5 ? "neg" : cs < 0.3 ? "pos" : "") : ""}
          sub="m²/均方；高=联动·低=个股主导" />
        <Stat label="离散-|收益|耦合" value={fixed3(data.corr_disp_absret)}
          tone={nx != null && nx > 0.4 ? "warn" : ""} sub="大动日离散↑（正=同扩）" />
        <Stat label="市场波动率" value={vol1(data.mkt_vol)} sub="等权·年化（上下文）" />
        <Stat label="最特异标的" value={worst ? worst.symbol : "—"}
          sub={worst ? `特异 ${vol1(worst.idio_vol)} · 占比 ${shr0(worst.idio_share)}` : ""} />
        <Stat label="最平静标的" value={quiet ? quiet.symbol : "—"}
          sub={quiet ? `特异 ${vol1(quiet.idio_vol)} · 占比 ${shr0(quiet.idio_share)}` : ""} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))", gap: 12 }}>
        <ChartCard title="截面离散度（逐日横截面标准差，滚动均值）"
          desc="蓝线=离散度；灰=全历史中位、绿=25% 分位（锁步）、暗红=75% 分位（选股环境）。飙升=收益分化加剧。">
          <LineChart series={[
            { data: dispLine, color: "#42a5f5", lineWidth: 2 },
            { data: band("p75"), color: "rgba(239,83,80,0.4)", lineWidth: 1 },
            { data: band("p50"), color: "rgba(154,166,178,0.4)", lineWidth: 1 },
            { data: band("p25"), color: "rgba(102,187,106,0.4)", lineWidth: 1 },
          ]} height={210} />
        </ChartCard>

        <ChartCard title="二阶矩分解：共同 vs 个股特异份额（%）"
          desc="把 mean(r²)=m²+d² 拆成两块占比。橙=共同 m²（联动/宏观）；蓝=特异 d²（个股）。特异占比高=选股环境；共同占比高=锁步。">
          <LineChart series={[
            { data: idioLine, color: "#42a5f5", lineWidth: 2 },
            { data: commonLine, color: "#ffa726", lineWidth: 1.5 },
          ]} height={210} />
        </ChartCard>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))", gap: 12, marginTop: 12 }}>
        <ChartCard title="离散-|收益| nexus（标准化叠加）"
          desc="两条线均标准化为均值0/标准差1。蓝=离散度、橙=|市场收益|。同向上行=大动日离散扩大（耦合）。">
          {nexusLine && nexusLine.disp.length > 1 ? (
            <LineChart series={[
              { data: nexusLine.disp, color: "#42a5f5", lineWidth: 2 },
              { data: nexusLine.absret, color: "#ffa726", lineWidth: 1.5 },
            ]} height={210} />
          ) : <div className="muted" style={{ fontSize: 11 }}>数据不足</div>}
        </ChartCard>

        <ChartCard title="截面：最特异 vs 最平静标的（全历史单因子特异波动）"
          desc="特异波动=剔除市场因子后的残差波动（年化）。左=最高（驱动离散的小盘/高波）；右=最低（最平静的防御/低波）。特异占比=1−R²。">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, marginTop: 4 }}>
            <CsTable title="▲ 最特异（驱动离散）" tone="neg" rows={data.most_idiosyncratic || []} />
            <CsTable title="▼ 最平静（离散最小）" tone="pos" rows={data.least_idiosyncratic || []} />
          </div>
        </ChartCard>
      </div>

      <div className="card" style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", marginTop: 12 }}>
        <b>离散度窗口</b>
        <select value={win} onChange={(e) => setWin(+e.target.value)}>
          {WINDOW_OPTS.map((w) => <option key={w} value={w}>{w} 日</option>)}
        </select>
        <span className="muted" style={{ fontSize: 11 }}>
          离散度 = 逐日各标的收益的横截面标准差的滚动均值。共同份额 {shr0(data.common_share)}：越低越「个股特异主导」（选股环境）。
        </span>
      </div>
    </div>
  );
}
