// 市场统计 8 个 tab 共用的小 UI 件：指标卡 / 图卡 / 体制横幅 / 标的下拉。
// 口径与开源参考实现的页面内小组件一致，仅样式挂到 .us-tv 作用域。
import { useEffect, useState } from "react";
import { fetchUsAnalyticsSymbols } from "../../../api/usAnalytics";

export function Stat({ label, value, tone = "", sub = "" }) {
  return (
    <div className="stat">
      <div className="muted" style={{ fontSize: 11 }}>{label}</div>
      <div className={tone} style={{ fontSize: 18, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{value}</div>
      {sub && <div className="muted" style={{ fontSize: 10 }}>{sub}</div>}
    </div>
  );
}

export function ChartCard({ title, desc, children }) {
  return (
    <div className="card">
      <h3 style={{ marginBottom: 4 }}>{title}</h3>
      {children}
      {desc && <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>{desc}</div>}
    </div>
  );
}

/** 体制/判读横幅：左大字标签 + 右解释文案，tone 上色。 */
export function RegimeBanner({ label, tone = "", desc, children }) {
  return (
    <div className={`card ${tone}`} style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap", marginBottom: 12 }}>
      {children}
      <div style={{ fontSize: 24, fontWeight: 700 }} className={tone}>{label}</div>
      <div className="muted" style={{ flex: 1, minWidth: 260, fontSize: 12 }}>{desc}</div>
    </div>
  );
}

/** 拉取标的池（/symbols，list[str]），供 symbol 下拉使用。 */
export function useSymbols() {
  const [symbols, setSymbols] = useState([]);
  useEffect(() => {
    let on = true;
    fetchUsAnalyticsSymbols()
      .then((d) => { if (on) setSymbols(d.symbols || []); })
      .catch(() => {});
    return () => { on = false; };
  }, []);
  return symbols;
}

/** 简洁 symbol 下拉（select + us-tv 样式）。 */
export function SymbolSelect({ symbols, value, onChange }) {
  const opts = symbols.length ? symbols : [value].filter(Boolean);
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      {opts.map((s) => <option key={s} value={s}>{s}</option>)}
    </select>
  );
}
