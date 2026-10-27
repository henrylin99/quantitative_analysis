// 动量与突破扫描 tab —— 1/5/20 日收益 + 量比的截面打分 + 四个突破/连涨
// 触发旗标：动量分直方图与强弱分档、突破/连涨触发统计与动量因子桶
// （点过滤）、可排序排名表（触发旗标列）。
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useScreenerBase } from "./screenerData";
import { TierTiles, ScoreHistogram, ChipFilter, BucketGroups, FlagChips } from "./ScanUI";
import {
  momentumScore, bandOf, accel, triggerTally,
  MOMENTUM_TIERS, TIER_ORDER, TRIGGER_FLAGS, BUCKETS, BUCKET_GROUPS, PRESETS,
  momentumFlags, medRet5, medRet20,
} from "../../../lib/us/momentum_scan";

const COLS = [
  { key: "symbol", label: "代码", str: true },
  { key: "name", label: "名称", str: true, left: true },
  { key: "_score", label: "动量分", title: "三因子(5日/20日动量+量比)截面百分位 0–100;越高量价动量越强" },
  { key: "ret_1d", label: "1日", title: "今日涨跌(≈pct_change)" },
  { key: "ret_5d", label: "5日动量", title: "近5日累计涨幅" },
  { key: "ret_20d", label: "20日动量", title: "近20日累计涨幅" },
  { key: "vol_ratio_5", label: "量比", title: "成交量/5日均量 ×" },
  { key: "_accel", label: "动量加速", title: "5日收益−20日速率(÷4),正=加速" },
  { key: "amplitude", label: "振幅", title: "(最高−最低)/前收,日内波幅" },
  { key: "_flags", label: "触发" },
];

const pct1 = (v) => (v == null || Number.isNaN(v)) ? "—" : (v >= 0 ? "+" : "") + (v * 100).toFixed(1) + "%";
const fmtCell = (v, key) => {
  if (v == null || Number.isNaN(v)) return "—";
  if (key === "_score") return v.toFixed(1);
  if (key === "ret_1d" || key === "ret_5d" || key === "ret_20d" || key === "amplitude" || key === "_accel") return pct1(v);
  if (key === "vol_ratio_5") return v.toFixed(2) + "×";
  return String(v);
};

const cellCls = (key, v) => {
  if (v == null) return "";
  if (key === "_score") return v >= 60 ? "pos" : v <= 40 ? "neg" : "warn";
  if (key === "ret_1d" || key === "ret_5d" || key === "ret_20d" || key === "_accel") return v > 0 ? "pos" : v < 0 ? "neg" : "";
  if (key === "vol_ratio_5") return v >= 1.5 ? "pos" : v < 0.5 ? "neg" : "";
  return "";
};

const MOM_SUBS = { strong: "量价齐升/突破", neutral: "温和", weak: "走弱/回调" };

export default function MomentumScanTab() {
  const navigate = useNavigate();
  const { rows, loaded, error, tradeDate } = useScreenerBase();
  const [preset, setPreset] = useState(null);
  const [tierFilter, setTierFilter] = useState(null);
  const [bucketFilter, setBucketFilter] = useState(null);
  const [triggerFilter, setTriggerFilter] = useState(null);
  const [q, setQ] = useState("");
  const [sortKey, setSortKey] = useState("_score");
  const [dir, setDir] = useState(-1);
  const [topN, setTopN] = useState(50);

  const augmented = useMemo(() => {
    if (!rows.length) return [];
    const sm = {};
    for (const s of momentumScore(rows)) sm[s.symbol] = s.score;
    return rows.map((r) => ({ ...r, _score: sm[r.symbol] ?? null, _accel: accel(r) }));
  }, [rows]);

  const tierOf = (score) => bandOf(score)?.key ?? null;

  const filtered = useMemo(() => {
    let r = augmented;
    if (preset) { const p = PRESETS.find((x) => x.key === preset); if (p) r = r.filter(p.test); }
    if (tierFilter) r = r.filter((x) => tierOf(x._score) === tierFilter);
    if (triggerFilter) r = r.filter((x) => x[triggerFilter] === 1);
    if (bucketFilter) {
      const b = BUCKETS.find((x) => x.group === bucketFilter.group && x.key === bucketFilter.key);
      if (b) r = r.filter(b.test);
    }
    const s = q.trim().toUpperCase();
    if (s) r = r.filter((x) => x.symbol.includes(s) || (x.name || "").toUpperCase().includes(s));
    return r;
  }, [augmented, preset, tierFilter, triggerFilter, bucketFilter, q]);

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

  const triggers = useMemo(() => triggerTally(rows), [rows]);
  const bucketCounts = useMemo(() => {
    const m = {};
    for (const b of BUCKETS) m[b.group + ":" + b.key] = rows.filter(b.test).length;
    return m;
  }, [rows]);

  const medR5 = medRet5(rows);
  const medR20 = medRet20(rows);

  const toggleSort = (key) => {
    if (key === "_flags") return;
    if (key === sortKey) setDir((d) => -d);
    else { setSortKey(key); setDir(-1); }
  };
  const hasFilter = preset || tierFilter || triggerFilter || bucketFilter;

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
        {hasFilter && <button type="button" onClick={() => { setPreset(null); setTierFilter(null); setTriggerFilter(null); setBucketFilter(null); }}>清除</button>}
        <label className="muted" style={{ fontSize: 12, marginLeft: "auto" }}>
          前
          <select value={String(topN)} onChange={(e) => setTopN(e.target.value === "all" ? null : Number(e.target.value))} style={{ margin: "0 6px" }}>
            <option value="20">20</option>
            <option value="50">50</option>
            <option value="100">100</option>
            <option value="all">全部</option>
          </select>
          只 · 显示 {filtered.length}/{rows.length} · 动量分按全市场截面排名
        </label>
      </div>

      <div className="card" data-momentum-overview>
        <h3>动量与突破扫描 <span className="muted">截面 {tradeDate || "—"} · 点动量档/触发/因子桶过滤</span></h3>
        <TierTiles tiers={MOMENTUM_TIERS} counts={tierCounts} total={rows.length}
          active={tierFilter} onToggle={setTierFilter} subtitles={MOM_SUBS} />
        <ScoreHistogram scores={augmented.map((r) => r._score)} posEnd />
        <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
          中位 5日 {medR5 != null ? (medR5 >= 0 ? "+" : "") + (medR5 * 100).toFixed(1) + "%" : "—"}
          · 中位 20日 {medR20 != null ? (medR20 >= 0 ? "+" : "") + (medR20 * 100).toFixed(1) + "%" : "—"}
          · {triggers.map((f) => (
            <span key={f.key} style={{ marginLeft: 6 }} className={f.count > 0 ? "pos" : ""}>{f.label} <b>{f.count}</b></span>
          ))}
        </div>
      </div>

      <div className="card" data-momentum-buckets>
        <h3>突破触发与动量因子分布 <span className="muted">点触发/因子桶过滤</span></h3>
        <div style={{ marginBottom: 10 }}>
          <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>突破/连涨触发</div>
          <ChipFilter
            items={triggers.map((f) => ({ key: f.key, label: f.label, tone: f.tone, count: f.count }))}
            activeKey={triggerFilter}
            onToggle={setTriggerFilter}
          />
        </div>
        <BucketGroups groups={BUCKET_GROUPS} buckets={BUCKETS} counts={bucketCounts}
          active={bucketFilter} onToggle={setBucketFilter} />
      </div>

      <div className="card" data-momentum-table>
        <h3>动量排名 · 点行跳个股页{hasFilter ? ` · 已筛 ${filtered.length}/${rows.length}` : ""}</h3>
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
                    <tr key={r.symbol} data-row={r.symbol} onClick={() => navigate(`/us/${r.symbol}`)}>
                      <td><span style={{ fontWeight: 700 }}>{r.symbol}</span></td>
                      <td className="muted" style={{ textAlign: "left" }}>{r.name}</td>
                      {COLS.filter((c) => !["symbol", "name"].includes(c.key)).map((c) => (
                        <td key={c.key} className={cellCls(c.key, r[c.key])} style={{ textAlign: "right" }}>
                          {c.key === "_flags"
                            ? <FlagChips flags={momentumFlags(r)} />
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
