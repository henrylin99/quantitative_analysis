// 蜡烛形态扫描 tab —— 22 个 pattern_* 旗标 + 实体/影线比的截面打分：
// 形态分（净多形态数的截面百分位）直方图与看多/中性/看空分档、
// 形态触发网格与形状桶（点过滤）、可排序排名表（形态旗标列）。
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useScreenerBase } from "./screenerData";
import { TierTiles, ScoreHistogram, ChipFilter, BucketGroups, FlagChips } from "./ScanUI";
import {
  candleScore, netBullish, totalPatterns, candleTier, dirOf, patternTally,
  CANDLE_TIERS, TIER_ORDER, PATTERNS, PATTERN_GROUPS, PATTERN_TOTAL,
  BUCKETS, BUCKET_GROUPS, PRESETS, candleFlags, medNet, medTotal,
} from "../../../lib/us/candle_scan";

const COLS = [
  { key: "symbol", label: "代码", str: true },
  { key: "name", label: "名称", str: true, left: true },
  { key: "_score", label: "形态分", title: "净多形态数的截面百分位 0–100;越高今日价格行为越偏多" },
  { key: "_net", label: "净多", title: "看涨形态数−看空形态数,正=偏多" },
  { key: "_total", label: "触发数", title: "今日触发形态总数(含中性结构)" },
  { key: "body_ratio", label: "实体比", title: "|开−收|/全距,大=方向坚决" },
  { key: "upper_shadow_ratio", label: "上影", title: "(高−max(开,收))/全距,长=卖压" },
  { key: "lower_shadow_ratio", label: "下影", title: "(min(开,收)−低)/全距,长=支撑" },
  { key: "pattern_ma_bull", label: "均线多头", title: "均线多头排列旗标" },
  { key: "pct_change", label: "今日涨跌", title: "今日涨跌幅" },
  { key: "_dir", label: "K线" },
  { key: "_flags", label: "形态明细" },
];

const fmtCell = (v, key) => {
  if (v == null || Number.isNaN(v)) return "—";
  if (key === "_score") return v.toFixed(1);
  if (key === "_net") return (v >= 0 ? "+" : "") + v;
  if (key === "body_ratio" || key === "upper_shadow_ratio" || key === "lower_shadow_ratio") return (v * 100).toFixed(0) + "%";
  if (key === "pct_change") return (v >= 0 ? "+" : "") + (v * 100).toFixed(1) + "%";
  if (key === "pattern_ma_bull") return v === 1 ? "▲" : "";
  return String(v);
};

const cellCls = (key, v) => {
  if (v == null) return "";
  if (key === "_score") return v >= 60 ? "pos" : v <= 40 ? "neg" : "warn";
  if (key === "_net") return v > 0 ? "pos" : v < 0 ? "neg" : "";
  if (key === "_total") return v >= 5 ? "pos" : "";
  if (key === "body_ratio") return v >= 0.6 ? "pos" : v <= 0.2 ? "neg" : "";
  if (key === "upper_shadow_ratio") return v >= 0.4 ? "neg" : "";
  if (key === "lower_shadow_ratio") return v >= 0.4 ? "pos" : "";
  if (key === "pattern_ma_bull") return v === 1 ? "pos" : "";
  if (key === "pct_change") return v > 0 ? "pos" : v < 0 ? "neg" : "";
  return "";
};

const CANDLE_SUBS = { bull: "净多形态 ≥2", neutral: "多空均衡", bear: "净多 ≤−1" };

export default function CandleScanTab({ mk = "us" }) {
  const navigate = useNavigate();
  const { rows, loaded, error, tradeDate } = useScreenerBase(mk);
  const [preset, setPreset] = useState(null);
  const [tierFilter, setTierFilter] = useState(null);
  const [patternFilter, setPatternFilter] = useState(null);
  const [bucketFilter, setBucketFilter] = useState(null);
  const [q, setQ] = useState("");
  const [sortKey, setSortKey] = useState("_score");
  const [dir, setDir] = useState(-1);
  const [topN, setTopN] = useState(50);

  const augmented = useMemo(() => {
    if (!rows.length) return [];
    const sm = {};
    for (const s of candleScore(rows)) sm[s.symbol] = { score: s.score, net: s.net };
    return rows.map((r) => ({
      ...r,
      _score: sm[r.symbol]?.score ?? null,
      _net: sm[r.symbol]?.net ?? netBullish(r),
      _total: totalPatterns(r),
      _dir: dirOf(r),
    }));
  }, [rows]);

  const filtered = useMemo(() => {
    let r = augmented;
    if (preset) { const p = PRESETS.find((x) => x.key === preset); if (p) r = r.filter(p.test); }
    if (tierFilter) r = r.filter((x) => candleTier(x._net) === tierFilter);
    if (patternFilter) r = r.filter((x) => x[patternFilter] === 1);
    if (bucketFilter) {
      const b = BUCKETS.find((x) => x.group === bucketFilter.group && x.key === bucketFilter.key);
      if (b) r = r.filter(b.test);
    }
    const s = q.trim().toUpperCase();
    if (s) r = r.filter((x) => x.symbol.includes(s) || (x.name || "").toUpperCase().includes(s));
    return r;
  }, [augmented, preset, tierFilter, patternFilter, bucketFilter, q]);

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

  // 档位按原始净额计数（离散计数比百分位带更可解读）。
  const tierCounts = useMemo(() => {
    const m = { bull: 0, neutral: 0, bear: 0 };
    for (const r of augmented) { const t = candleTier(r._net); if (t) m[t]++; }
    return m;
  }, [augmented]);

  const tally = useMemo(() => patternTally(rows), [rows]);
  const tallyByKey = useMemo(() => Object.fromEntries(tally.map((p) => [p.key, p.count])), [tally]);
  const bucketCounts = useMemo(() => {
    const m = {};
    for (const b of BUCKETS) m[b.group + ":" + b.key] = rows.filter(b.test).length;
    return m;
  }, [rows]);

  const medNetV = medNet(rows);
  const medTotalV = medTotal(rows);
  const hotPatterns = [...tally].filter((p) => p.count > 0).sort((a, b) => b.count - a.count).slice(0, 8);

  const toggleSort = (key) => {
    if (key === "_flags" || key === "_dir") return;
    if (key === sortKey) setDir((d) => -d);
    else { setSortKey(key); setDir(-1); }
  };
  const hasFilter = preset || tierFilter || patternFilter || bucketFilter;

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
        {hasFilter && <button type="button" onClick={() => { setPreset(null); setTierFilter(null); setPatternFilter(null); setBucketFilter(null); }}>清除</button>}
        <label className="muted" style={{ fontSize: 12, marginLeft: "auto" }}>
          前
          <select value={String(topN)} onChange={(e) => setTopN(e.target.value === "all" ? null : Number(e.target.value))} style={{ margin: "0 6px" }}>
            <option value="20">20</option>
            <option value="50">50</option>
            <option value="100">100</option>
            <option value="all">全部</option>
          </select>
          只 · 显示 {filtered.length}/{rows.length} · 形态分按全市场截面排名
        </label>
      </div>

      <div className="card" data-candle-overview>
        <h3>蜡烛形态扫描 <span className="muted">截面 {tradeDate || "—"} · 点形态档/热门形态/形态网格过滤</span></h3>
        <TierTiles tiers={CANDLE_TIERS} counts={tierCounts} total={rows.length}
          active={tierFilter} onToggle={setTierFilter} subtitles={CANDLE_SUBS} />
        <ScoreHistogram scores={augmented.map((r) => r._score)} posEnd />
        <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
          中位净多 {medNetV != null ? (medNetV >= 0 ? "+" : "") + medNetV : "—"}
          · 中位触发 {medTotalV != null ? medTotalV : "—"}/{PATTERN_TOTAL}
          · 热门形态:
          {hotPatterns.map((p) => (
            <span key={p.key} data-hotpattern={p.key} onClick={() => setPatternFilter(patternFilter === p.key ? null : p.key)}
              style={{
                marginLeft: 6, cursor: "pointer",
                color: patternFilter === p.key ? "var(--tv-text)" : undefined,
                fontWeight: patternFilter === p.key ? 700 : 400,
              }}
              className={patternFilter === p.key ? "" : p.tone === "pos" ? "pos" : p.tone === "neg" ? "neg" : "warn"}>
              {p.label} <b>{p.count}</b>
            </span>
          ))}
        </div>
      </div>

      <div className="card" data-candle-patterns>
        <h3>形态触发网格 <span className="muted">点形态过滤</span></h3>
        {PATTERN_GROUPS.map((g) => (
          <div key={g.group} style={{ marginBottom: 10 }}>
            <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>{g.label}</div>
            <ChipFilter
              items={PATTERNS.filter((p) => p.group === g.group)}
              counts={tallyByKey}
              activeKey={patternFilter}
              onToggle={setPatternFilter}
            />
          </div>
        ))}
        <div style={{ marginTop: 4, paddingTop: 8, borderTop: "1px solid var(--tv-border)" }}>
          <BucketGroups groups={BUCKET_GROUPS} buckets={BUCKETS} counts={bucketCounts}
            active={bucketFilter} onToggle={setBucketFilter} />
        </div>
      </div>

      <div className="card" data-candle-table>
        <h3>形态排名 · 点行跳个股页{hasFilter ? ` · 已筛 ${filtered.length}/${rows.length}` : ""}</h3>
        {error ? <div className="muted" style={{ padding: 12 }}>加载失败：{error}</div>
          : loaded ? (shown.length ? (
            <div className="scroll" style={{ maxHeight: 460 }}>
              <table className="data">
                <thead>
                  <tr>
                    {COLS.map((c) => (
                      <th key={c.key} onClick={() => toggleSort(c.key)} title={c.title}
                        style={{ textAlign: c.left ? "left" : "right", cursor: c.key === "_flags" || c.key === "_dir" ? "default" : "pointer" }}>
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
                            ? <FlagChips flags={candleFlags(r)} max={4} />
                            : c.key === "_dir" ? <span className={r._dir === "阳" ? "pos" : r._dir === "阴" ? "neg" : "muted"}>{r._dir}</span>
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
