// 风险与波动维度打分 lib —— 截面级「每只股票可能亏多少、止损挂哪」扫描。
// 与动量/技术维度互补：那些回答「买什么、多强」，这里回答「下行风险多大」
// —— 已实现波动与回撤、均线偏离、ATR 止损位、布林带宽，即仓位管理与
// 止损 placement 的输入。
//
// 纯函数：页面组件直接 import 做打分与统计。invPhi 复用本目录 risk.js
// 的正态分位函数（与组合页参数法 VaR 同一套数学）。
// 数据适配：本截面无预分类 risk_level，档位由风险分的分数带派生；
// bb_width 为小数（0.49 = 49%），阈值按同一比例取 0.30/0.12。

import { percentileRank, bandFor, median } from "./scan_shared.js";
import { invPhi } from "./risk.js";

// 风险分档（0–100 截面百分位，越高=下行风险越大）。>=60 高风险，
// 40–60 中等，else 低风险。
export const RISK_BANDS = [
  { key: "high", label: "高风险", min: 60, tone: "neg" },
  { key: "medium", label: "中等", min: 40, tone: "warn" },
  { key: "low", label: "低风险", min: 0, tone: "pos" },
];
export const bandOf = (score) => bandFor(score, RISK_BANDS);

// 概览三档（由分数带派生，非原始列）。
export const RISK_TIERS = [
  { key: "high", label: "高风险", tone: "neg" },
  { key: "medium", label: "中等", tone: "warn" },
  { key: "low", label: "低风险", tone: "pos" },
];
export const TIER_ORDER = ["high", "medium", "low"];

// 每行一个 { symbol, score(0..100|null) }。四个「越高越危险」分位——
// 20日波动、|20日回撤|、|60日线偏离|（向上/向下过度延伸都算）、布林带宽
// ——取平均。缺失分量跳过（只有波动数据的股票按波动单因子排名）。
export function riskScore(rows) {
  if (!rows || !rows.length) return [];
  const vol = rows.map((r) => r.risk_vol_20d);
  const dd = rows.map((r) => (r.risk_dd_20d == null ? null : Math.abs(r.risk_dd_20d)));
  const ext = rows.map((r) => (r.risk_ma60_dev == null ? null : Math.abs(r.risk_ma60_dev)));
  const bbw = rows.map((r) => r.bb_width);
  return rows.map((r) => {
    const parts = [];
    if (r.risk_vol_20d != null) parts.push(percentileRank(vol, r.risk_vol_20d));
    if (r.risk_dd_20d != null) parts.push(percentileRank(dd, Math.abs(r.risk_dd_20d)));
    if (r.risk_ma60_dev != null) parts.push(percentileRank(ext, Math.abs(r.risk_ma60_dev)));
    if (r.bb_width != null) parts.push(percentileRank(bbw, r.bb_width));
    if (!parts.length) return { symbol: r.symbol, score: null };
    return { symbol: r.symbol, score: (parts.reduce((a, b) => a + b, 0) / parts.length) * 100 };
  });
}

// ATR 占价比 —— ATR 除以收盘价（%），跨价格档可比的日均波幅。
export function atrPct(row) {
  const { atr_14, close } = row || {};
  if (![atr_14, close].every(Number.isFinite) || close === 0) return null;
  return (atr_14 / close) * 100;
}

// 止损缓冲：ATR 多头止损位低于现价的空间（%）。正=止损还在下方
// （越大越安全）；负=止损已高于现价（无效，入场即触发）。
export function stopCushionPct(row) {
  const { atr_stop_long, close } = row || {};
  if (![atr_stop_long, close].every(Number.isFinite) || close === 0) return null;
  return ((close - atr_stop_long) / close) * 100;
}

// 由单日波动率（%，日收益标准差）算 1 日 95% 参数法 VaR。
// 乘数 = −Φ⁻¹(0.05) ≈ 1.645（复用 risk.js invPhi，与组合页参数法 VaR 同源）。
// 返回占名义本金的比例与金额。
export function parametricVaR1d95(volDailyPct, notional = 10000) {
  if (volDailyPct == null || !Number.isFinite(volDailyPct)) return null;
  const mult = -invPhi(0.05); // ~1.6449
  const varPct = volDailyPct * mult;
  return { varPct, varAmt: (notional * varPct) / 100 };
}

// 可点击的风险因子桶（概览过滤面板用）。group 排序展示；test(row) 判定
// 成员资格；计数由页面从行集派生。
export const BUCKET_GROUPS = [
  { group: "vol", label: "20日波动率" },
  { group: "dd", label: "20日回撤" },
  { group: "ext", label: "偏离60日线" },
];
export const BUCKETS = [
  // vol（日波动 %）
  { group: "vol", key: "vol_low", label: "低 <2%", tone: "pos", test: (r) => r.risk_vol_20d != null && r.risk_vol_20d < 2 },
  { group: "vol", key: "vol_mid", label: "中 2–4%", tone: "warn", test: (r) => r.risk_vol_20d != null && r.risk_vol_20d >= 2 && r.risk_vol_20d < 4 },
  { group: "vol", key: "vol_high", label: "高 4–8%", tone: "neg", test: (r) => r.risk_vol_20d != null && r.risk_vol_20d >= 4 && r.risk_vol_20d < 8 },
  { group: "vol", key: "vol_extreme", label: "极高 ≥8%", tone: "neg", test: (r) => r.risk_vol_20d != null && r.risk_vol_20d >= 8 },
  // drawdown（恒 ≤0）：按深度分桶
  { group: "dd", key: "dd_shallow", label: "浅 ≥−3%", tone: "pos", test: (r) => r.risk_dd_20d != null && r.risk_dd_20d > -3 },
  { group: "dd", key: "dd_mid", label: "中 −3~−10%", tone: "warn", test: (r) => r.risk_dd_20d != null && r.risk_dd_20d <= -3 && r.risk_dd_20d > -10 },
  { group: "dd", key: "dd_deep", label: "深 ≤−10%", tone: "neg", test: (r) => r.risk_dd_20d != null && r.risk_dd_20d <= -10 },
  // extension：|60日线偏离| %
  { group: "ext", key: "ext_near", label: "贴近 <5%", tone: "pos", test: (r) => r.risk_ma60_dev != null && Math.abs(r.risk_ma60_dev) < 5 },
  { group: "ext", key: "ext_mid", label: "适度 5–15%", tone: "warn", test: (r) => r.risk_ma60_dev != null && Math.abs(r.risk_ma60_dev) >= 5 && Math.abs(r.risk_ma60_dev) < 15 },
  { group: "ext", key: "ext_far", label: "偏离 ≥15%", tone: "neg", test: (r) => r.risk_ma60_dev != null && Math.abs(r.risk_ma60_dev) >= 15 },
];

// 一键预设。阈值引用原始风险列 + 派生止损缓冲。
export const PRESETS = [
  { key: "lowrisk", label: "低风险", title: "风险分 < 40(平静)", test: (r) => r._risk != null && r._risk < 40 },
  { key: "highrisk", label: "高风险", title: "风险分 ≥ 60(剧烈)", test: (r) => r._risk != null && r._risk >= 60 },
  { key: "deepdd", label: "深度回撤", title: "20日回撤 ≤ −10%", test: (r) => r.risk_dd_20d != null && r.risk_dd_20d <= -10 },
  { key: "extension", label: "超买延伸", title: "偏离60日线 |%| ≥ 15%", test: (r) => r.risk_ma60_dev != null && Math.abs(r.risk_ma60_dev) >= 15 },
  { key: "tightstop", label: "紧止损", title: "ATR止损缓冲 < 3%(止损贴近价/已破)", test: (r) => stopCushionPct(r) != null && stopCushionPct(r) < 3 },
  { key: "wideband", label: "宽带", title: "布林带宽 ≥ 30%(高波动)", test: (r) => r.bb_width != null && r.bb_width >= 0.3 },
];

// 表格行提示旗标：一只股票命中哪些风险读数（页面直接渲染 label）。
export function riskFlags(row) {
  const out = [];
  const cushion = stopCushionPct(row);
  if (row.risk_dd_20d != null && row.risk_dd_20d <= -10) out.push({ label: "深回撤", tone: "neg", title: "20日回撤 ≤ −10%" });
  if (row.risk_ma60_dev != null && Math.abs(row.risk_ma60_dev) >= 15) out.push({ label: "偏离60线", tone: "neg", title: "偏离60日线 ≥ 15%" });
  if (cushion != null && cushion < 3) out.push({ label: "紧止损", tone: "warn", title: "ATR止损缓冲 < 3%" });
  if (row.bb_width != null && row.bb_width >= 0.3) out.push({ label: "宽带", tone: "warn", title: "布林带宽 ≥ 30%" });
  if (row.risk_vol_20d != null && row.risk_vol_20d < 2) out.push({ label: "低波动", tone: "pos", title: "20日波动 < 2%" });
  return out;
}

// 概览统计：中位 20 日波动 / 中位 20 日回撤（%）。
export const medVol = (rows) => median((rows || []).map((r) => r.risk_vol_20d));
export const medDd = (rows) => median((rows || []).map((r) => r.risk_dd_20d));
