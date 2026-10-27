// 资金流向扫描 tab —— VWAP 偏离/相对换手/OBV/流通/Chaikin 强度四个
// 尺度不变派生比率的截面打分（后端直接输出 vwap/obv/chaikin_osc 原始列，
// 派生在本 lib 完成）：资金分直方图与流入/中性/流出分档、资金因子桶
// 过滤、可排序排名表（资金提示旗标列）。
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useScreenerBase } from "./screenerData";
import { TierTiles, ScoreHistogram, BucketGroups, FlagChips } from "./ScanUI";
import {
  deriveFlow, moneyflowScore, bandOf, MF_TIERS, TIER_ORDER,
  BUCKETS, BUCKET_GROUPS, PRESETS, moneyflowFlags,
} from "../../../lib/us/moneyflow_scan";

const COLS = [
  { key: "symbol", label: "代码", str: true },
  { key: "name", label: "名称", str: true, left: true },
  { key: "_score", label: "资金分", title: "4项资金指标(VWAP偏离/相对换手/OBV/Chaikin)截面百分位 0–100;越高净买盘越强" },
  { key: "_vwap_dev", label: "VWAP偏离", title: "(收盘−VWAP)/VWAP %,正=站上日内均价" },
  { key: "_rel_turn", label: "相对换手", title: "成交额/市值 %,今日多大比例市值换手" },
  { key: "_obv_ratio", label: "OBV/流通", title: "OBV/总股本,累计净累积倍数,正=净流入" },
  { key: "_chaik_ratio", label: "Chaikin", title: "Chaikin振荡/成交额 ‰,累积/派发动量" },
  { key: "pct_change", label: "今日涨跌", title: "今日涨跌幅(价格面,与资金分对照:价升量入=健康)" },
  { key: "close", label: "收盘价", title: "最新收盘价" },
  { key: "amount", label: "成交额", title: "今日成交额" },
  { key: "_flags", label: "资金提示" },
];

const fmtCell = (v, key) => {
  if (v == null || Number.isNaN(v)) return "—";
  if (key === "_score") return v.toFixed(1);
  if (key === "_vwap_dev" || key === "pct_change") return (v >= 0 ? "+" : "") + v.toFixed(2) + "%";
  if (key === "_rel_turn") return v.toFixed(2) + "%";
  if (key === "_obv_ratio") return (v >= 0 ? "+" : "") + v.toFixed(2);
  if (key === "_chaik_ratio") return (v >= 0 ? "+" : "") + (v * 1000).toFixed(2) + "‰";
  if (key === "close") return v.toFixed(2);
  if (key === "amount") return v >= 1e9 ? (v / 1e9).toFixed(2) + "B" : (v / 1e6).toFixed(0) + "M";
  return String(v);
};

// 常规资金方向着色：高/正 = 吸筹 = 绿。
const cellCls = (key, v) => {
  if (v == null) return "";
  if (key === "_score") return v >= 67 ? "pos" : v <= 33 ? "neg" : "";
  if (key === "_vwap_dev" || key === "pct_change") return v > 0 ? "pos" : v < 0 ? "neg" : "";
  if (key === "_rel_turn") return v >= 1 ? "pos" : v <= 0.2 ? "neg" : "";
  if (key === "_obv_ratio") return v >= 0.3 ? "pos" : v <= -0.1 ? "neg" : "";
  if (key === "_chaik_ratio") return v >= 0.005 ? "pos" : v <= -0.003 ? "neg" : "";
  return "";
};

const MF_SUBS = { inflow: "净吸筹/买盘强", neutral: "买卖平衡", outflow: "净派发/卖压" };

export default function MoneyflowScanTab() {
  const navigate = useNavigate();
  const { rows, loaded, error, tradeDate } = useScreenerBase();
  const [preset, setPreset] = useState(null);
  const [tierFilter, setTierFilter] = useState(null);
  const [bucketFilter, setBucketFilter] = useState(null);
  const [q, setQ] = useState("");
  const [sortKey, setSortKey] = useState("_score");
  const [dir, setDir] = useState(-1);
  const [topN, setTopN] = useState(50);

  // 先注入 deriveFlow 派生比率，再在全市场派生集上打分（分数不随过滤漂移）。
  const augmented = useMemo(() => {
    if (!rows.length) return [];
    const derived = rows.map((r) => ({ ...r, ...deriveFlow(r) }));
    const sm = {};
    for (const s of moneyflowScore(derived)) sm[s.symbol] = s.score;
    return derived.map((r) => ({ ...r, _score: sm[r.symbol] ?? null }));
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
    const m = { inflow: 0, neutral: 0, outflow: 0 };
    for (const r of augmented) { const t = tierOf(r._score); if (t) m[t]++; }
    return m;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [augmented]);

  // 桶对照派生字段，计数也要在派生集上做。
  const bucketCounts = useMemo(() => {
    const m = {};
    for (const b of BUCKETS) m[b.group + ":" + b.key] = augmented.filter(b.test).length;
    return m;
  }, [augmented]);

  const medFlow = useMemo(() => {
    const xs = augmented.map((r) => r._score).filter(Number.isFinite).sort((a, b) => a - b);
    return xs.length ? xs[Math.floor(xs.length / 2)] : null;
  }, [augmented]);
  const medTurn = useMemo(() => {
    const xs = augmented.map((r) => r._rel_turn).filter(Number.isFinite).sort((a, b) => a - b);
    return xs.length ? xs[Math.floor(xs.length / 2)] : null;
  }, [augmented]);
  // 热门流入 top5（点选过滤为流入档）。
  const hotInflow = useMemo(
    () => [...augmented].filter((r) => Number.isFinite(r._score)).sort((a, b) => b._score - a._score).slice(0, 5),
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
          只 · 显示 {filtered.length}/{rows.length} · 资金分按全市场截面排名
        </label>
      </div>

      <div className="card" data-moneyflow-overview>
        <h3>资金流向扫描 <span className="muted">截面 {tradeDate || "—"} · 点资金档/因子桶过滤</span></h3>
        <TierTiles tiers={MF_TIERS} counts={tierCounts} total={rows.length}
          active={tierFilter} onToggle={setTierFilter} subtitles={MF_SUBS} />
        <ScoreHistogram scores={augmented.map((r) => r._score)} posEnd />
        <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
          中位资金分 {medFlow != null ? medFlow.toFixed(1) : "—"}
          · 中位换手 {medTurn != null ? medTurn.toFixed(2) + "%" : "—"}
          · 热门流入:
          {hotInflow.map((r) => (
            <button key={r.symbol} type="button" data-hotlinflow={r.symbol} onClick={() => setTierFilter(tierFilter === "inflow" ? null : "inflow")}
              style={{ marginLeft: 6, fontSize: 11, padding: "1px 6px", borderRadius: 8, color: "var(--tv-up)", borderColor: "var(--tv-up)55" }}>
              {r.symbol} <b>{r._score.toFixed(0)}</b>
            </button>
          ))}
        </div>
      </div>

      <div className="card" data-moneyflow-buckets>
        <h3>资金因子分布 <span className="muted">点因子桶过滤</span></h3>
        <BucketGroups groups={BUCKET_GROUPS} buckets={BUCKETS} counts={bucketCounts}
          active={bucketFilter} onToggle={setBucketFilter} />
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          四个派生比率均为尺度不变量(对价格/市值规模归一),资金分 = 其截面百分位均值;高 = 净买盘。
        </div>
      </div>

      <div className="card" data-moneyflow-table>
        <h3>资金分排名 · 点行跳个股页{hasFilter ? ` · 已筛 ${filtered.length}/${rows.length}` : ""}</h3>
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
                            ? <FlagChips flags={moneyflowFlags(r)} />
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
