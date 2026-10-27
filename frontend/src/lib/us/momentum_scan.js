// 动量与突破维度打分 lib —— 截面级「谁的趋势最强、有无量能确认、
// 是否正在突破」扫描。表面的是多周期收益（1/5/20 日）、量能相对 5 日
// 均量比、日内振幅与四个突破/连涨旗标——纯价格动量输入。
//
// 颜色方向为常规（非反转）：收益/量能越高 = 上升趋势越强 = 绿。
// 与 risk_scan（高=差）相反。ret_1d 有意不进复合分——扫描器已有当日
// 涨跌信息；这个分数衡量的是多日趋势。
//
// 纯函数：页面组件直接 import 做打分与统计。

import { percentileRank, bandFor, median } from "./scan_shared.js";

// 动量分档（0–100 截面百分位）。>=60 强势，40–60 中性，else 弱势。
export const MOMENTUM_BANDS = [
  { key: "strong", label: "强势", min: 60, tone: "pos" },
  { key: "neutral", label: "中性", min: 40, tone: "warn" },
  { key: "weak", label: "弱势", min: 0, tone: "neg" },
];
export const bandOf = (score) => bandFor(score, MOMENTUM_BANDS);

// 概览三档（由分数带派生）。
export const MOMENTUM_TIERS = [
  { key: "strong", label: "强势", tone: "pos" },
  { key: "neutral", label: "中性", tone: "warn" },
  { key: "weak", label: "弱势", tone: "neg" },
];
export const TIER_ORDER = ["strong", "neutral", "weak"];

// 每行一个 { symbol, score(0..100|null) }。三个「越高越强」分位——
// 5日收益（短动量）、20日收益（中动量）、量比（量能确认）——取平均。
// 缺失分量跳过。
export function momentumScore(rows) {
  if (!rows || !rows.length) return [];
  const r5 = rows.map((r) => r.ret_5d);
  const r20 = rows.map((r) => r.ret_20d);
  const vr = rows.map((r) => r.vol_ratio_5);
  return rows.map((r) => {
    const parts = [];
    if (r.ret_5d != null) parts.push(percentileRank(r5, r.ret_5d));
    if (r.ret_20d != null) parts.push(percentileRank(r20, r.ret_20d));
    if (r.vol_ratio_5 != null) parts.push(percentileRank(vr, r.vol_ratio_5));
    if (!parts.length) return { symbol: r.symbol, score: null };
    return { symbol: r.symbol, score: (parts.reduce((a, b) => a + b, 0) / parts.length) * 100 };
  });
}

// 动量加速：近 5 日收益减去 20 日节奏折算到 5 日（ret_20d/4）。
// 正 = 最近 5 日跑赢 20 日平均节奏 → 动量在加速；负 = 减速（即便仍在上行）。
export function accel(row) {
  const { ret_5d, ret_20d } = row || {};
  if (![ret_5d, ret_20d].every(Number.isFinite)) return null;
  return ret_5d - ret_20d / 4;
}

// 突破/连涨二元旗标：四者都是「看涨延续」触发器（tone pos）。
export const TRIGGER_FLAGS = [
  { key: "break_high_20", label: "创20日新高", tone: "pos" },
  { key: "break_high_60", label: "创60日新高", tone: "pos" },
  { key: "consec_up_3", label: "连涨3日", tone: "pos" },
  { key: "consec_up_5", label: "连涨5日", tone: "pos" },
];
export function triggerTally(rows) {
  const n = rows.length || 1;
  return TRIGGER_FLAGS.map((f) => {
    const count = rows.reduce((a, r) => a + (r?.[f.key] === 1 ? 1 : 0), 0);
    return { ...f, count, share: count / n };
  });
}

// 可点击的动量因子桶（概览过滤面板用）。test 对照原始小数值。
export const BUCKET_GROUPS = [
  { group: "ret5", label: "5日动量" },
  { group: "ret20", label: "20日动量" },
  { group: "vol", label: "量比" },
];
export const BUCKETS = [
  // 5日收益（小数：0.08 = 8%）
  { group: "ret5", key: "ret5_strong", label: "强 ≥+8%", tone: "pos", test: (r) => r.ret_5d != null && r.ret_5d >= 0.08 },
  { group: "ret5", key: "ret5_mid", label: "温和 −3~+8%", tone: "warn", test: (r) => r.ret_5d != null && r.ret_5d >= -0.03 && r.ret_5d < 0.08 },
  { group: "ret5", key: "ret5_weak", label: "弱 ≤−3%", tone: "neg", test: (r) => r.ret_5d != null && r.ret_5d < -0.03 },
  // 20日收益（小数）
  { group: "ret20", key: "ret20_strong", label: "强 ≥+15%", tone: "pos", test: (r) => r.ret_20d != null && r.ret_20d >= 0.15 },
  { group: "ret20", key: "ret20_mid", label: "中 −5~+15%", tone: "warn", test: (r) => r.ret_20d != null && r.ret_20d >= -0.05 && r.ret_20d < 0.15 },
  { group: "ret20", key: "ret20_weak", label: "弱 ≤−5%", tone: "neg", test: (r) => r.ret_20d != null && r.ret_20d < -0.05 },
  // 量比（>1 = 高于5日均量）
  { group: "vol", key: "vol_surge", label: "放量 ≥1.5×", tone: "pos", test: (r) => r.vol_ratio_5 != null && r.vol_ratio_5 >= 1.5 },
  { group: "vol", key: "vol_normal", label: "正常 0.8~1.5×", tone: "warn", test: (r) => r.vol_ratio_5 != null && r.vol_ratio_5 >= 0.8 && r.vol_ratio_5 < 1.5 },
  { group: "vol", key: "vol_shrink", label: "缩量 <0.8×", tone: "neg", test: (r) => r.vol_ratio_5 != null && r.vol_ratio_5 < 0.8 },
];

// 一键预设。阈值引用原始动量列。
export const PRESETS = [
  { key: "strong20", label: "强势动量", title: "20日动量 ≥ +15%", test: (r) => r.ret_20d != null && r.ret_20d >= 0.15 },
  { key: "breakout", label: "突破新高", title: "创20日新高", test: (r) => r.break_high_20 === 1 },
  { key: "streak", label: "连涨", title: "连涨3日", test: (r) => r.consec_up_3 === 1 },
  { key: "volup", label: "放量上涨", title: "量比>1.5 且 5日动量为正", test: (r) => r.vol_ratio_5 != null && r.vol_ratio_5 > 1.5 && r.ret_5d > 0 },
  { key: "deepdecline", label: "深度回调", title: "20日动量 ≤ −15%(超跌反弹候选)", test: (r) => r.ret_20d != null && r.ret_20d <= -0.15 },
  { key: "volprice", label: "量价齐升", title: "量比>1.2 且 创20日新高", test: (r) => r.vol_ratio_5 != null && r.vol_ratio_5 > 1.2 && r.break_high_20 === 1 },
];

// 表格行触发旗标（激活的 TRIGGER_FLAGS）。
export function momentumFlags(row) {
  return TRIGGER_FLAGS.filter((f) => row?.[f.key] === 1)
    .map((f) => ({ label: f.label, tone: f.tone, title: f.label }));
}

// 概览统计：中位 5 日 / 20 日收益（小数）。
export const medRet5 = (rows) => median((rows || []).map((r) => r.ret_5d));
export const medRet20 = (rows) => median((rows || []).map((r) => r.ret_20d));
