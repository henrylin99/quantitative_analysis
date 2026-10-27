// 基本面扫描 tab —— 快照级质量/成长/股息/资产负债截面打分（降级口径）。
// 港股无季度财务序列与财报事件，「基本面轨迹/财务体检」降级为当前截面：
// 基本面分（截面百分位均值）直方图与优质/中性/偏弱分档、固定阈值质量桶
// 过滤、可排序排名表（八项指标 + 提示旗标列）。点行跳个股页。
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useScreenerBase } from "./screenerData";
import { TierTiles, ScoreHistogram, BucketGroups, FlagChips } from "./ScanUI";
import {
  fundScore, bandOf, FUND_TIERS, TIER_ORDER,
  BUCKETS, BUCKET_GROUPS, PRESETS, fundFlags,
} from "../../../lib/us/fundamental_scan";

const COLS = [
  { key: "symbol", label: "代码", str: true },
  { key: "name", label: "名称", str: true, left: true },
  { key: "_score", label: "基本面分", title: "七项正向+负债逆向的截面百分位均值 0–100;越高基本面越强" },
  { key: "roe", label: "ROE", title: "净资产收益率,≥15% 优质" },
  { key: "roa", label: "ROA", title: "总资产收益率" },
  { key: "profit_margin", label: "净利率", title: "净利润/营收" },
  { key: "operating_margin", label: "经营利润率", title: "经营利润/营收" },
  { key: "earnings_growth", label: "盈利增速", title: "盈利同比增速" },
  { key: "dividend_yield", label: "股息率", title: "年度股息/股价" },
  { key: "debt_to_equity", label: "负债/权益", title: "越低越稳健,>120 高负债" },
  { key: "current_ratio", label: "流动比率", title: "流动资产/流动负债,>2 充裕" },
  { key: "market_cap", label: "市值", title: "总市值(港元)" },
  { key: "_flags", label: "基本面提示" },
];

const fmtCell = (v, key) => {
  if (v == null || Number.isNaN(v)) return "—";
  if (key === "_score") return v.toFixed(0);
  if (key === "roe" || key === "roa" || key === "profit_margin"
    || key === "operating_margin" || key === "earnings_growth") {
    return (v * 100).toFixed(1) + "%";
  }
  if (key === "dividend_yield") return v.toFixed(2) + "%";
  if (key === "debt_to_equity") return v.toFixed(0);
  if (key === "current_ratio") return v.toFixed(2);
  if (key === "market_cap") {
    if (v >= 1e12) return (v / 1e12).toFixed(2) + "万亿";
    if (v >= 1e8) return (v / 1e8).toFixed(0) + "亿";
    return String(Math.round(v));
  }
  return String(v);
};

// 混合着色：基本面分/正向指标常规（高=绿）；负债/权益逆向（低=绿/高=红）。
const invCls = (v, good, bad) =>
  v == null ? "" : v <= good ? "pos" : v >= bad ? "neg" : "";
const fwdCls = (v, good, bad) =>
  v == null ? "" : v >= good ? "pos" : v <= bad ? "neg" : "";
const cellCls = (key, v) => {
  if (v == null) return "";
  if (key === "_score") return v >= 67 ? "pos" : v <= 33 ? "neg" : "";
  if (key === "roe") return fwdCls(v, 0.15, 0.02);
  if (key === "roa") return fwdCls(v, 0.06, 0);
  if (key === "profit_margin") return fwdCls(v, 0.15, 0);
  if (key === "operating_margin") return fwdCls(v, 0.2, 0);
  if (key === "earnings_growth") return fwdCls(v, 0.1, 0);
  if (key === "dividend_yield") return v >= 4 ? "pos" : "";
  if (key === "debt_to_equity") return invCls(v, 40, 120);
  if (key === "current_ratio") return fwdCls(v, 2, 1);
  return "";
};

const FUND_SUBS = { strong: "盈利强/成长足/资产负债稳健", neutral: "各项居中", weak: "盈利弱/高负债/负增长" };

export default function FundamentalScanTab({ mk = "us" }) {
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
    for (const s of fundScore(rows)) sm[s.symbol] = s.score;
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
    const m = { strong: 0, neutral: 0, weak: 0 };
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
  // 基本面分最高的 5 只（点击切到优质档过滤）。
  const topFund = useMemo(
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
          只 · 显示 {filtered.length}/{rows.length} · 基本面分按截面排名
        </label>
      </div>

      <div className="card" data-fund-overview>
        <h3>基本面扫描 <span className="muted">截面 {tradeDate || "—"} · 快照级口径 · 点质量桶过滤</span></h3>
        <TierTiles tiers={FUND_TIERS} counts={tierCounts} total={rows.length}
          active={tierFilter} onToggle={setTierFilter} subtitles={FUND_SUBS} />
        <ScoreHistogram scores={augmented.map((r) => r._score)} posEnd />
        <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
          中位基本面分 {medScore != null ? medScore.toFixed(0) : "—"}
          · 质量 Top5:
          {topFund.map((r) => (
            <button key={r.symbol} type="button" data-topfund={r.symbol} onClick={() => setTierFilter(tierFilter === "strong" ? null : "strong")}
              style={{ marginLeft: 6, fontSize: 11, padding: "1px 6px", borderRadius: 8, color: "var(--tv-up)", borderColor: "var(--tv-up)55" }}>
              {r.symbol} <b>{r._score.toFixed(0)}</b>
            </button>
          ))}
        </div>
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          港股无季度财务序列与财报日历——本页为当前截面快照打分（盈利能力/成长/股息/资产负债），
          营收增速全市场缺失未纳入；缺数据的分量自动跳过，不冒充 0。
        </div>
      </div>

      <div className="card" data-fund-buckets>
        <h3>质量指标分布 <span className="muted">点指标桶过滤(绿=好/红=差)</span></h3>
        <BucketGroups groups={BUCKET_GROUPS} buckets={BUCKETS} counts={bucketCounts}
          active={bucketFilter} onToggle={setBucketFilter} />
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          ROE≥15%/净利率≥15%/增速≥10%/股息≥4%/负债≤40/流动比率≥2 视为优；缺数据的股票不计入对应桶。
        </div>
      </div>

      <div className="card" data-fund-table>
        <h3>基本面排名 · 点行跳个股页{hasFilter ? ` · 已筛 ${filtered.length}/${rows.length}` : ""}</h3>
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
                            ? <FlagChips flags={fundFlags(r)} />
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
