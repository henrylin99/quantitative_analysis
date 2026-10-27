// 估值扫描 tab —— 5 项价格乘数(逆) + 股息率(正)的截面打分：估值分
// （越高=越便宜）直方图与便宜/合理/昂贵分档、乘数桶过滤（低=便宜），
// 可排序排名表（原始乘数 + 估值提示旗标列）。亏损/负净资产股票显示
// 亏损/剔除，不参与乘数排名。
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useScreenerBase } from "./screenerData";
import { TierTiles, ScoreHistogram, BucketGroups, FlagChips } from "./ScanUI";
import {
  valuationScore, bandOf, VAL_TIERS, TIER_ORDER,
  BUCKETS, BUCKET_GROUPS, PRESETS, valuationFlags,
} from "../../../lib/us/valuation_scan";

const COLS = [
  { key: "symbol", label: "代码", str: true },
  { key: "name", label: "名称", str: true, left: true },
  { key: "_score", label: "估值分", title: "5项价格乘数(逆)+股息率(正)截面百分位均值 0–100;越高=越便宜(低估)" },
  { key: "trailing_pe", label: "市盈率TTM", title: "股价/每股收益(过去12月),越低越便宜;亏损剔除" },
  { key: "forward_pe", label: "远期PE", title: "按预测每股收益算的PE;亏损剔除" },
  { key: "price_to_book", label: "市净率", title: "股价/每股净资产;负净资产剔除" },
  { key: "ps_ratio", label: "市销率", title: "市值/年营收" },
  { key: "peg_ratio", label: "PEG", title: "PE/盈利增速,<1常视为低估" },
  { key: "dividend_yield", label: "股息率", title: "年度股息/股价 %(已为百分数)" },
  { key: "pct_change", label: "今日涨跌" },
  { key: "_flags", label: "估值提示" },
];

const fmtCell = (v, key) => {
  if (v == null || Number.isNaN(v)) return "—";
  if (key === "_score") return v.toFixed(0);
  if (key === "trailing_pe" || key === "forward_pe") return v <= 0 ? "亏损" : v.toFixed(1);
  if (key === "price_to_book") return v <= 0 ? "负净资产" : v.toFixed(2);
  if (key === "ps_ratio" || key === "peg_ratio") return v.toFixed(2);
  if (key === "dividend_yield") return v.toFixed(2) + "%";
  if (key === "pct_change") return (v > 0 ? "+" : "") + (v * 100).toFixed(1) + "%";
  return String(v);
};

// 混合着色：估值分/股息率常规（高=绿）；五项逆向乘数（低=绿/高=红，≤0 中性）。
const invCls = (v, good, bad) =>
  v == null || v <= 0 ? "" : v <= good ? "pos" : v >= bad ? "neg" : "";
const cellCls = (key, v) => {
  if (v == null) return "";
  if (key === "_score") return v >= 67 ? "pos" : v <= 33 ? "neg" : "";
  if (key === "trailing_pe" || key === "forward_pe") return invCls(v, 15, 40);
  if (key === "price_to_book") return invCls(v, 3, 12);
  if (key === "ps_ratio") return invCls(v, 2, 10);
  if (key === "peg_ratio") return invCls(v, 1, 3);
  if (key === "dividend_yield") return v >= 3 ? "pos" : "";
  if (key === "pct_change") return v > 0 ? "pos" : v < 0 ? "neg" : "";
  return "";
};

const VAL_SUBS = { cheap: "低估值/深度价值", fair: "合理估值", pricey: "高估值/昂贵" };

export default function ValuationScanTab({ mk = "us" }) {
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
    for (const s of valuationScore(rows)) sm[s.symbol] = s.score;
    return rows.map((r) => ({ ...r, _score: sm[r.symbol] ?? null }));
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
    const m = { cheap: 0, fair: 0, pricey: 0 };
    for (const r of augmented) { const t = tierOf(r._score); if (t) m[t]++; }
    return m;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [augmented]);

  const bucketCounts = useMemo(() => {
    const m = {};
    for (const b of BUCKETS) m[b.group + ":" + b.key] = rows.filter(b.test).length;
    return m;
  }, [rows]);

  const medScore = useMemo(() => {
    const xs = augmented.map((r) => r._score).filter(Number.isFinite).sort((a, b) => a - b);
    return xs.length ? xs[Math.floor(xs.length / 2)] : null;
  }, [augmented]);
  // 最便宜的 5 只（可点过滤为便宜档）。
  const hotCheap = useMemo(
    () => [...augmented].filter((r) => r._score != null).sort((a, b) => b._score - a._score).slice(0, 5),
    [augmented]);

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
          只 · 显示 {filtered.length}/{rows.length} · 估值分按全市场截面排名
        </label>
      </div>

      <div className="card" data-valuation-overview>
        <h3>估值扫描 <span className="muted">截面 {tradeDate || "—"} · 点估值档/乘数桶过滤</span></h3>
        <TierTiles tiers={VAL_TIERS} counts={tierCounts} total={rows.length}
          active={tierFilter} onToggle={setTierFilter} subtitles={VAL_SUBS} />
        <ScoreHistogram scores={augmented.map((r) => r._score)} posEnd />
        <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
          中位估值分 {medScore != null ? medScore.toFixed(0) : "—"}
          · 热门便宜股:
          {hotCheap.map((r) => (
            <button key={r.symbol} type="button" data-hotcheap={r.symbol} onClick={() => setTierFilter(tierFilter === "cheap" ? null : "cheap")}
              style={{ marginLeft: 6, fontSize: 11, padding: "1px 6px", borderRadius: 8, color: "var(--tv-up)", borderColor: "var(--tv-up)55" }}>
              {r.symbol} <b>{r._score.toFixed(0)}</b>
            </button>
          ))}
        </div>
      </div>

      <div className="card" data-valuation-buckets>
        <h3>价格乘数分布 <span className="muted">点乘数桶过滤(低=便宜)</span></h3>
        <BucketGroups groups={BUCKET_GROUPS} buckets={BUCKETS} counts={bucketCounts}
          active={bucketFilter} onToggle={setBucketFilter} />
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          低估(绿)=乘数低=便宜;高估(红)=乘数高=昂贵。亏损/负净资产股票不计入乘数排名。
        </div>
      </div>

      <div className="card" data-valuation-table>
        <h3>估值排名 · 点行跳个股页{hasFilter ? ` · 已筛 ${filtered.length}/${rows.length}` : ""}</h3>
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
                  {shown.map((r) => (
                    <tr key={r.symbol} data-row={r.symbol} onClick={() => navigate(`/${mk}/${r.symbol}`)}>
                      <td><span style={{ fontWeight: 700 }}>{r.symbol}</span></td>
                      <td className="muted" style={{ textAlign: "left" }}>{r.name}</td>
                      {COLS.filter((c) => !["symbol", "name"].includes(c.key)).map((c) => (
                        <td key={c.key} className={cellCls(c.key, r[c.key])} style={{ textAlign: "right" }}>
                          {c.key === "_flags"
                            ? <FlagChips flags={valuationFlags(r)} />
                            : fmtCell(r[c.key], c.key)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <div className="muted" style={{ padding: 12 }}>无满足条件的标的。</div>)
          : <div className="spinner">加载中…</div>}
      </div>
    </div>
  );
}
