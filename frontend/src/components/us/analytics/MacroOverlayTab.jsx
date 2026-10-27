// 宏观叠加 tab —— /fund/macro（宏观 4 序列 + 全池 β 敏感度表）。
// 展示口径：宏观序列卡（水位/区间涨跌/历史分位/regime）+ 市场中位 β 统计 +
// 按宏观因子分类的敏感度排名表。β = cov(r_stock, r_macro)/var(r_macro)，
// 后端仅在重叠交易日 ≥ 40 时给出，否则为 null。
import { useEffect, useMemo, useState } from "react";
import { fetchUsAnalytics } from "../../../api/usAnalytics";
import LineChart from "../LineChart.jsx";
import { Stat, ChartCard } from "./shared.jsx";
import { toLine, signedPct1 } from "../../../lib/us/analyticsFmt";

const SPARK = { vix: "#ef5350", spx: "#26a69a", dxy: "#ffd166", tnx: "#ab47bc" };
const REGIME_TONE = { risk_on: "pos", normal: "", risk_off: "neg", crisis: "neg", up: "pos", down: "neg", flat: "" };
const SORTS = [
  { key: "vix", label: "按|β_VIX|" },
  { key: "spx", label: "按β_SPX" },
  { key: "dxy", label: "按β_DXY" },
];

// 按 β_SPX(市场贝塔) × β_VIX(波动敏感) 把个股分类。
// 几乎所有股票 β_VIX 为负（恐慌时下跌），问题是负到什么程度；
// β_SPX ≤ 0 的视为逆周期。
export function classify(spx, vix) {
  if (spx == null || vix == null || !Number.isFinite(+spx) || !Number.isFinite(+vix))
    return { key: "na", label: "—", tone: "muted" };
  if (spx <= 0) return { key: "counter", label: "逆周期", tone: "pos" };
  if (spx > 1.2 && vix < -0.12) return { key: "aggressive", label: "进攻高弹性", tone: "neg" };
  if (spx < 0.7) return { key: "defensive", label: "防御", tone: "pos" };
  return { key: "neutral", label: "中性", tone: "" };
}

const fmtBeta = (v) => (v == null || !Number.isFinite(+v) ? "—" : (+v).toFixed(2));

export default function MacroOverlayTab() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [sortBy, setSortBy] = useState("vix");

  useEffect(() => {
    let on = true;
    setErr("");
    fetchUsAnalytics("/fund/macro")
      .then((d) => { if (on) setData(d); })
      .catch((e) => { if (on) setErr(String(e?.message || e)); });
    return () => { on = false; };
  }, []);

  const rows = data?.sensitivity?.rows || [];
  const series = data?.series || [];

  const med = useMemo(() => {
    const f = (k) => {
      const xs = rows.map((r) => r[`beta_${k}`]).filter((v) => v != null && Number.isFinite(+v)).map(Number);
      xs.sort((a, b) => a - b);
      return xs.length ? xs[Math.floor(xs.length / 2)] : null;
    };
    return { vix: f("vix"), spx: f("spx"), dxy: f("dxy") };
  }, [rows]);

  const counts = useMemo(() => {
    const c = { aggressive: 0, defensive: 0, counter: 0, neutral: 0 };
    for (const r of rows) {
      const k = classify(r.beta_spx, r.beta_vix).key;
      if (k in c) c[k] += 1;
    }
    return c;
  }, [rows]);

  const ranked = useMemo(() => {
    const key = `beta_${sortBy}`;
    return [...rows].sort((a, b) => {
      const av = a[key], bv = b[key];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return sortBy === "vix" ? Math.abs(bv) - Math.abs(av) : bv - av;
    }).slice(0, 20);
  }, [rows, sortBy]);

  if (err) return <div className="spinner">宏观数据加载失败：{err}</div>;
  if (!data) return <div className="spinner">加载宏观数据中…</div>;

  return (
    <div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        宏观背景（VIX / 标普500 / 美元指数 / 美债10Y）+ 全池个股对宏观因子的敏感度
        （β，重叠 {data.sensitivity?.n_days ?? 0} 个交易日）。
        <b> β_VIX</b> 几乎全为负（恐慌时下跌，越负越敏感）；<b>β_SPX</b> 为市场贝塔
        （&gt;1 进攻 / &lt;1 防御 / ≤0 逆周期）；<b>β_DXY</b> 对美元升值的敏感方向。
      </div>

      {/* 宏观 4 序列卡 */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))", gap: 12 }}>
        {series.map((m) => (
          <ChartCard key={m.key} title={m.label}
            desc={`区间累计 ${signedPct1(m.period_pct)} · 处于自身历史 ${(m.pctile * 100).toFixed(0)}% 分位`}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 4 }}>
              <span style={{ fontSize: 20, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
                {m.last != null ? m.last.toFixed(m.key === "vix" ? 1 : 2) : "—"}
              </span>
              <span className={REGIME_TONE[m.regime?.key] || ""} style={{ fontSize: 12 }}>{m.regime?.label}</span>
            </div>
            <LineChart series={[{
              data: toLine(m.data, "close"),
              color: SPARK[m.key] || "#4f93e7",
              lineWidth: 1.5,
            }]} height={90} />
          </ChartCard>
        ))}
      </div>

      {/* 市场中位 β + 分类计数 */}
      <div className="stats" style={{ marginTop: 12 }}>
        <Stat label="市场中位 β_VIX" value={fmtBeta(med.vix)} tone="neg" sub="波动敏感度" />
        <Stat label="市场中位 β_SPX" value={fmtBeta(med.spx)} sub="市场贝塔" />
        <Stat label="市场中位 β_DXY" value={fmtBeta(med.dxy)} sub="美元敏感度" />
        <Stat label="进攻高弹性" value={counts.aggressive} tone="neg" sub="β_SPX>1.2 且 β_VIX<-0.12" />
        <Stat label="防御型" value={counts.defensive} tone="pos" sub="β_SPX<0.7" />
        <Stat label="逆周期" value={counts.counter} tone="pos" sub="β_SPX≤0" />
        <Stat label="重叠交易日" value={data.sensitivity?.n_days ?? 0} sub="β 估计窗口" />
        <Stat label="覆盖标的" value={rows.length} sub="全池" />
      </div>

      {/* 敏感度排名表 */}
      <div className="card" style={{ marginTop: 12 }}>
        <h3>
          宏观敏感度排名 Top 20 ·
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} style={{ marginLeft: 8 }}>
            {SORTS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
        </h3>
        <div className="scroll" style={{ maxHeight: 460 }}>
          <table className="data">
            <thead><tr><th>#</th><th>标的</th><th>分类</th><th>β_VIX</th><th>β_SPX</th><th>β_DXY</th></tr></thead>
            <tbody>
              {ranked.length === 0 && (
                <tr><td colSpan={6} className="muted" style={{ textAlign: "center", padding: 16 }}>
                  无敏感度数据（宏观与个股重叠交易日不足）。
                </td></tr>
              )}
              {ranked.map((r, i) => {
                const c = classify(r.beta_spx, r.beta_vix);
                return (
                  <tr key={r.symbol}>
                    <td>{i + 1}</td>
                    <td><b>{r.symbol}</b> <span className="muted">{r.name}</span></td>
                    <td className={c.tone}>{c.label}</td>
                    <td className="neg">{fmtBeta(r.beta_vix)}</td>
                    <td className={Number(r.beta_spx) > 1 ? "neg" : Number(r.beta_spx) < 0.7 ? "pos" : ""}>{fmtBeta(r.beta_spx)}</td>
                    <td className={Number(r.beta_dxy) > 0 ? "pos" : "neg"}>{fmtBeta(r.beta_dxy)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
          按所选 β 降序取前 20（β_VIX 按 |β| 排）。分类口径：进攻高弹性 = 高市场贝塔叠加强负波动敏感；
          防御 = 低市场贝塔；逆周期 = 市场贝塔非正。β 值基于日收益率回归，重叠不足 40 交易日的标的为 —。
        </div>
      </div>
    </div>
  );
}
