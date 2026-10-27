// 风险与波动扫描 tab —— 20日波动/回撤/均线偏离/布林带宽的截面打分 +
// ATR 止损与止损缓冲 + 1日 95% 参数法 VaR：风险分直方图与高中低分档、
// 风险因子桶过滤（点桶过滤）、可排序排名表（风险提示旗标列）。
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useScreenerBase } from "./screenerData";
import { TierTiles, ScoreHistogram, BucketGroups, FlagChips } from "./ScanUI";
import {
  riskScore, bandOf, atrPct, stopCushionPct, parametricVaR1d95,
  RISK_TIERS, TIER_ORDER, BUCKETS, BUCKET_GROUPS, PRESETS, riskFlags, medVol, medDd,
} from "../../../lib/us/risk_scan";

const COLS = [
  { key: "symbol", label: "代码", str: true },
  { key: "name", label: "名称", str: true, left: true },
  { key: "_score", label: "风险分", title: "四因子(波动/回撤/偏离/带宽)截面百分位 0–100;越高下行风险越大" },
  { key: "risk_vol_20d", label: "20日波动", title: "日收益标准差 %" },
  { key: "risk_dd_20d", label: "20日回撤", title: "近20日最大跌幅 %(≤0)" },
  { key: "risk_ma20_dev", label: "偏离20线", title: "收盘相对20日均线 %,短期超买/超卖代理" },
  { key: "risk_ma60_dev", label: "偏离60线", title: "收盘相对60日均线 %" },
  { key: "_atr_pct", label: "ATR占价", title: "ATR/收盘 %,跨价格档可比的日均波幅" },
  { key: "_stop_cushion", label: "止损缓冲", title: "(收盘−ATR止损)/收盘 %,正=止损在下方的空间" },
  { key: "_bb_width_pct", label: "带宽", title: "布林带宽 %(波动率代理)" },
  { key: "_flags", label: "风险提示" },
];

const fmtCell = (v, key) => {
  if (v == null || Number.isNaN(v)) return "—";
  if (key === "_score") return v.toFixed(1);
  if (key === "_stop_cushion") return (v > 0 ? "+" : "") + v.toFixed(1) + "%";
  if (key === "_atr_pct" || key === "_bb_width_pct" || key === "risk_vol_20d" || key === "risk_dd_20d" || key === "risk_ma20_dev" || key === "risk_ma60_dev") {
    return v.toFixed(1);
  }
  return String(v);
};

const cellCls = (key, v) => {
  if (v == null) return "";
  if (key === "_score") return v >= 60 ? "neg" : v <= 40 ? "pos" : "warn";
  if (key === "risk_dd_20d") return v <= -10 ? "neg" : v >= -3 ? "pos" : "";
  if (key === "risk_vol_20d") return v >= 4 ? "neg" : v <= 2 ? "pos" : "";
  if (key === "_stop_cushion") return v < 3 ? "neg" : v > 10 ? "pos" : "warn";
  if (key === "_bb_width_pct") return v >= 30 ? "neg" : v <= 12 ? "pos" : "";
  return "";
};

const RISK_SUBS = { high: "风险分≥60 高波动/深回撤", medium: "40–60 正常波动", low: "<40 低波动/平稳" };

export default function RiskScanTab({ mk = "us" }) {
  const navigate = useNavigate();
  const { rows, loaded, error, tradeDate } = useScreenerBase(mk);
  const [preset, setPreset] = useState(null);
  const [tierFilter, setTierFilter] = useState(null);
  const [bucketFilter, setBucketFilter] = useState(null);
  const [q, setQ] = useState("");
  const [sortKey, setSortKey] = useState("_score");
  const [dir, setDir] = useState(-1);
  const [topN, setTopN] = useState(50);

  const augmented = useMemo(() => {
    if (!rows.length) return [];
    const sm = {};
    for (const s of riskScore(rows)) sm[s.symbol] = s.score;
    return rows.map((r) => {
      const atr = atrPct(r);
      const bbw = r.bb_width;
      return {
        ...r,
        _score: sm[r.symbol] ?? null,
        _atr_pct: atr,
        _stop_cushion: stopCushionPct(r),
        _bb_width_pct: bbw == null ? null : bbw * 100,
      };
    });
  }, [rows]);

  const tierOf = (score) => bandOf(score)?.key ?? null;

  const filtered = useMemo(() => {
    let r = augmented;
    if (preset) { const p = PRESETS.find((x) => x.key === preset); if (p) r = r.filter(p.test); }
    if (tierFilter) r = r.filter((x) => tierOf(x._score) === tierFilter);
    if (bucketFilter) {
      const b = BUCKETS.find((x) => x.group === bucketFilter.group && x.key === bucketFilter.key);
      if (b) r = r.filter(b.test);
    }
    const s = q.trim().toUpperCase();
    if (s) r = r.filter((x) => x.symbol.includes(s) || (x.name || "").toUpperCase().includes(s));
    return r;
  }, [augmented, preset, tierFilter, bucketFilter, q]);

  const sorted = useMemo(() => {
    const col = COLS.find((c) => c.key === sortKey);
    return [...filtered].sort((a, b) => {
      const va = a[sortKey], vb = b[sortKey];
      if (va == null) return 1;
      if (vb == null) return -1;
      const cmp = col?.str ? String(va).localeCompare(String(vb)) : va - vb;
      return cmp * dir;
    });
  }, [filtered, sortKey, dir]);

  const shown = topN == null ? sorted : sorted.slice(0, topN);

  const tierCounts = useMemo(() => {
    const m = { high: 0, medium: 0, low: 0 };
    for (const r of augmented) { const t = tierOf(r._score); if (t) m[t]++; }
    return m;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [augmented]);

  const bucketCounts = useMemo(() => {
    const m = {};
    for (const b of BUCKETS) m[b.group + ":" + b.key] = rows.filter(b.test).length;
    return m;
  }, [rows]);

  const medVolV = medVol(rows);
  const medDdV = medDd(rows);

  const toggleSort = (key) => {
    if (key === "_flags") return;
    if (key === sortKey) setDir((d) => -d);
    else { setSortKey(key); setDir(-1); }
  };
  const hasFilter = preset || tierFilter || bucketFilter;

  return (
    <div>
      <div className="toolbar" style={{ flexWrap: "wrap", gap: 8 }}>
        <span className="muted" style={{ fontSize: 12 }}>筛选:</span>
        {PRESETS.map((p) => (
          <button key={p.key} type="button" data-preset={p.key} title={p.title}
            className={preset === p.key ? "active" : ""}
            onClick={() => setPreset(preset === p.key ? null : p.key)}>
            {p.label}
          </button>
        ))}
        <input placeholder="搜索代码/名称…" value={q} onChange={(e) => setQ(e.target.value)} style={{ marginLeft: 8, width: 170 }} />
        {hasFilter && <button type="button" onClick={() => { setPreset(null); setTierFilter(null); setBucketFilter(null); }}>清除</button>}
        <label className="muted" style={{ fontSize: 12, marginLeft: "auto" }}>
          前
          <select value={String(topN)} onChange={(e) => setTopN(e.target.value === "all" ? null : Number(e.target.value))} style={{ margin: "0 6px" }}>
            <option value="20">20</option>
            <option value="50">50</option>
            <option value="100">100</option>
            <option value="all">全部</option>
          </select>
          只 · 显示 {filtered.length}/{rows.length} · 风险分按全市场截面排名
        </label>
      </div>

      <div className="card" data-risk-overview>
        <h3>风险与波动扫描 <span className="muted">截面 {tradeDate || "—"} · 点风险档/因子桶过滤</span></h3>
        <TierTiles tiers={RISK_TIERS} counts={tierCounts} total={rows.length}
          active={tierFilter} onToggle={setTierFilter} subtitles={RISK_SUBS} />
        <ScoreHistogram scores={augmented.map((r) => r._score)} posEnd={false} />
        <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
          中位 20日波动 {medVolV != null ? medVolV.toFixed(1) + "%" : "—"}
          · 中位 20日回撤 {medDdV != null ? medDdV.toFixed(1) + "%" : "—"}
          {tierFilter ? <> · 已按风险档过滤 · <b>点档块取消</b></> : " · 点风险档/因子桶过滤"}
        </div>
      </div>

      <div className="card" data-risk-buckets>
        <h3>风险因子分布 <span className="muted">点因子桶过滤</span></h3>
        <BucketGroups groups={BUCKET_GROUPS} buckets={BUCKETS} counts={bucketCounts}
          active={bucketFilter} onToggle={setBucketFilter} />
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          风险分 = 波动/|回撤|/|60线偏离|/带宽 四项分位均值;ATR 止损与止损缓冲是仓位与止损 placement 的参照。
        </div>
      </div>

      <div className="card" data-risk-table>
        <h3>风险排名 · 点行跳个股页{hasFilter ? ` · 已筛 ${filtered.length}/${rows.length}` : ""}</h3>
        {error ? <div className="muted" style={{ padding: 12 }}>加载失败：{error}</div>
          : loaded ? (shown.length ? (
            <div className="scroll" style={{ maxHeight: 460 }}>
              <table className="data">
                <thead>
                  <tr>
                    {COLS.map((c) => (
                      <th key={c.key} onClick={() => toggleSort(c.key)} title={c.title}
                        style={{ textAlign: c.left ? "left" : "right", cursor: c.key === "_flags" ? "default" : "pointer" }}>
                        {c.label} {sortKey === c.key ? (dir > 0 ? "▲" : "▼") : ""}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {shown.map((r) => {
                    const va = parametricVaR1d95(r.risk_vol_20d, 10000);
                    return (
                      <tr key={r.symbol} data-row={r.symbol} onClick={() => navigate(`/${mk}/${r.symbol}`)}
                        title={va ? `1日95% VaR ≈ −${va.varPct.toFixed(1)}%($1万仓 −$${va.varAmt.toFixed(0)})` : undefined}>
                        <td><span style={{ fontWeight: 700 }}>{r.symbol}</span></td>
                        <td className="muted" style={{ textAlign: "left" }}>{r.name}</td>
                        {COLS.filter((c) => !["symbol", "name"].includes(c.key)).map((c) => (
                          <td key={c.key} className={cellCls(c.key, r[c.key])} style={{ textAlign: "right" }}>
                            {c.key === "_flags"
                              ? <FlagChips flags={riskFlags(r)} />
                              : fmtCell(r[c.key], c.key)}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : <div className="muted" style={{ padding: 12 }}>无满足条件的标的。</div>)
          : <div className="spinner">加载中…</div>}
      </div>
    </div>
  );
}
