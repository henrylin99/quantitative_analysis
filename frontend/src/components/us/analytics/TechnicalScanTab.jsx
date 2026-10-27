// 技术信号扫描 tab —— 23 个 ind_* 旗标 + signal_score 的截面打分：
// 技术分直方图与强弱分档、全市场信号触发统计（点信号过滤）、
// 可排序排名表（旗标明细列）。点行跳个股页。
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useScreenerBase } from "./screenerData";
import { TierTiles, ScoreHistogram, ChipFilter, FlagChips } from "./ScanUI";
import {
  techScore, signalSummary, bbPctB, marketTally, bandOf,
  SIGNALS, FAMILY_LABEL, FAMILY_ORDER, DIR_TONE, PRESETS,
} from "../../../lib/us/technical_scan";

const COLS = [
  { key: "symbol", label: "代码", str: true },
  { key: "name", label: "名称", str: true, left: true },
  { key: "_score", label: "技术分", title: "signal_score 截面百分位 0–100;越高技术动量越强(常伴随超买)" },
  { key: "rsi_14", label: "RSI", title: "相对强弱 0–100" },
  { key: "macd_hist", label: "MACD柱" },
  { key: "adx_14", label: "ADX", title: "趋势强度 >25 有趋势" },
  { key: "cci_20", label: "CCI" },
  { key: "stoch_k_14", label: "Stoch%K" },
  { key: "willr_14", label: "WillR" },
  { key: "mfi_14", label: "MFI", title: "量加权 RSI 0–100" },
  { key: "_bb_pctb", label: "布林%B", title: "价格在布林带中位置 0=下轨 1=上轨" },
  { key: "_net", label: "信号净", title: "活跃看涨信号数 − 看跌信号数(布林收口不计)" },
  { key: "_flags", label: "旗标明细" },
];

const fmtCell = (v, key) => {
  if (v == null || Number.isNaN(v)) return "—";
  if (key === "_score") return v.toFixed(1);
  if (key === "rsi_14" || key === "mfi_14" || key === "stoch_k_14" || key === "adx_14" || key === "willr_14") return v.toFixed(0);
  if (key === "macd_hist") return (v > 0 ? "+" : "") + v.toFixed(2);
  if (key === "cci_20") return String(Math.round(v));
  if (key === "_bb_pctb") return (v * 100).toFixed(0) + "%";
  if (key === "_net") return (v > 0 ? "+" : "") + v;
  return String(v);
};

const cellCls = (key, v) => {
  if (v == null) return "";
  if (key === "_score") return v >= 60 ? "pos" : v <= 40 ? "neg" : "warn";
  if (key === "_net") return v > 0 ? "pos" : v < 0 ? "neg" : "";
  return "";
};

const TECH_TIERS = [
  { key: "strong", label: "技术强势", tone: "pos", sub: "技术分≥60" },
  { key: "neutral", label: "中性", tone: "warn", sub: "40–60" },
  { key: "weak", label: "技术弱势", tone: "neg", sub: "≤40 弱势" },
];

export default function TechnicalScanTab() {
  const navigate = useNavigate();
  const { rows, loaded, error, tradeDate } = useScreenerBase();
  const [preset, setPreset] = useState(null);
  const [tierFilter, setTierFilter] = useState(null);
  const [signalFilter, setSignalFilter] = useState(null);
  const [q, setQ] = useState("");
  const [sortKey, setSortKey] = useState("_score");
  const [dir, setDir] = useState(-1);
  const [topN, setTopN] = useState(50);

  // 打分在全市场上算，股票分数不随过滤器漂移。
  const augmented = useMemo(() => {
    if (!rows.length) return [];
    const sm = {};
    for (const s of techScore(rows)) sm[s.symbol] = s.score;
    return rows.map((r) => {
      const summ = signalSummary(r);
      return { ...r, _score: sm[r.symbol] ?? null, _bb_pctb: bbPctB(r), _net: summ.net };
    });
  }, [rows]);

  const tierOf = (score) => bandOf(score)?.key ?? null;

  const filtered = useMemo(() => {
    let r = augmented;
    if (preset) { const p = PRESETS.find((x) => x.key === preset); if (p) r = r.filter(p.test); }
    if (tierFilter) r = r.filter((x) => tierOf(x._score) === tierFilter);
    if (signalFilter) r = r.filter((x) => x[signalFilter] === 1);
    const s = q.trim().toUpperCase();
    if (s) r = r.filter((x) => x.symbol.includes(s) || (x.name || "").toUpperCase().includes(s));
    return r;
  }, [augmented, preset, tierFilter, signalFilter, q]);

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

  const tallyByFamily = useMemo(() => {
    const tally = marketTally(rows);
    const m = {};
    for (const fam of FAMILY_ORDER) m[fam] = tally.filter((t) => t.family === fam).sort((a, b) => b.count - a.count);
    return m;
  }, [rows]);

  const medScore = useMemo(() => {
    const xs = augmented.map((r) => r._score).filter(Number.isFinite).sort((a, b) => a - b);
    return xs.length ? xs[Math.floor(xs.length / 2)] : null;
  }, [augmented]);

  const withTrend = rows.filter((r) => r.ta_with_trend === 1).length;
  const counterTrend = rows.filter((r) => r.ta_counter_trend === 1).length;

  const toggleSort = (key) => {
    if (key === "_flags") return;
    if (key === sortKey) setDir((d) => -d);
    else { setSortKey(key); setDir(-1); }
  };
  const hasFilter = preset || tierFilter || signalFilter;

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
        {hasFilter && (
          <button type="button" onClick={() => { setPreset(null); setTierFilter(null); setSignalFilter(null); }}>清除</button>
        )}
        <label className="muted" style={{ fontSize: 12, marginLeft: "auto" }}>
          前
          <select value={String(topN)} onChange={(e) => setTopN(e.target.value === "all" ? null : Number(e.target.value))} style={{ margin: "0 6px" }}>
            <option value="20">20</option>
            <option value="50">50</option>
            <option value="100">100</option>
            <option value="all">全部</option>
          </select>
          只 · 显示 {filtered.length}/{rows.length} · 技术分按全市场截面排名
        </label>
      </div>

      <div className="card" data-tech-overview>
        <h3>技术信号扫描 <span className="muted">截面 {tradeDate || "—"} · 点强弱档/信号过滤</span></h3>
        <TierTiles tiers={TECH_TIERS} counts={tierCounts} total={rows.length}
          active={tierFilter} onToggle={setTierFilter} subtitles={{ strong: TECH_TIERS[0].sub, neutral: TECH_TIERS[1].sub, weak: TECH_TIERS[2].sub }} />
        <ScoreHistogram scores={augmented.map((r) => r._score)} posEnd />
        <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
          顺势 <span className="pos">{withTrend}</span> · 逆势 <span className="neg">{counterTrend}</span>
          · 全市场中位技术分 {medScore != null ? medScore.toFixed(1) : "—"}
          {signalFilter ? <> · 已按信号过滤 · <b style={{ color: "#f5a623" }}>{SIGNALS.find((s) => s.key === signalFilter)?.label}</b> 点标签取消</> : " · 点下方信号标签过滤"}
        </div>
      </div>

      <div className="card" data-signal-tally>
        <h3>全市场信号触发 <span className="muted">绿=看涨 红=看跌 琥珀=中性(收口) · 点过滤</span></h3>
        {FAMILY_ORDER.map((fam) => (
          <div key={fam} style={{ marginBottom: 8 }}>
            <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>{FAMILY_LABEL[fam]}</div>
            <ChipFilter
              items={tallyByFamily[fam].map((s) => ({ key: s.key, label: s.label, tone: DIR_TONE[s.dir], title: s.note, count: s.count }))}
              activeKey={signalFilter}
              onToggle={setSignalFilter}
            />
          </div>
        ))}
      </div>

      <div className="card" data-tech-table>
        <h3>技术排名 · 点行跳个股页{hasFilter ? ` · 已筛 ${filtered.length}/${rows.length}` : ""}</h3>
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
                            ? <FlagChips flags={SIGNALS.filter((s) => r[s.key] === 1).map((s) => ({ label: s.label, tone: DIR_TONE[s.dir], title: s.note }))} />
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
