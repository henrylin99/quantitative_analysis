// 蜡烛形态维度打分 lib —— 截面级「今天谁走出了锤子/吞没/白三兵」扫描。
// 表面 22 个预计算 pattern_* 旗标 + 生成它们的三个 K 线形状比
// （实体比/上影/下影），覆盖全市场——纯粹的单根 K 线/短窗口价格行为形态。
//
// 复合分是「净多形态数」的截面百分位（看涨形态数 − 看空形态数），而非
// 连续因子的分位混合：旗标是二元的，净额化才是诚实的方向信号。
// 档位取自原始净额（≥2 看多 / 0–1 中性 / ≤−1 看空）——离散计数比其
// 百分位带更可解读。
//
// 颜色方向为混合式：每个形态自带 tone（看涨=绿、看空=红、结构=灰）。
// 数据适配：本截面提供 22 个 pattern_* 列（无晨星/暮星/刺透/乌云盖顶/
// 三内升），长上影/长下影归入结构组、不计入净额。

import { percentileRank, median } from "./scan_shared.js";

// 概览三档（按净额计数，非百分位）：≥2 看多占优，≤−1 看空占优。
export const CANDLE_TIERS = [
  { key: "bull", label: "看多", tone: "pos" },
  { key: "neutral", label: "中性", tone: "warn" },
  { key: "bear", label: "看空", tone: "neg" },
];
export const TIER_ORDER = ["bull", "neutral", "bear"];

// 方向性形态 key。净额 = 触发看涨数 − 触发看空数。
// 中性/结构形态（十字/影线/内含/波动/假突破）有意排除在净额之外
// ——它们描述形状而非方向。
export const BULL_PATTERNS = [
  "pattern_bull_candle", "pattern_hammer", "pattern_bullish_engulfing",
  "pattern_three_white_soldiers", "pattern_trend_confirm", "pattern_ma_bull",
  "pattern_pullback_hold", "pattern_double_bottom", "pattern_volume_breakout",
];
export const BEAR_PATTERNS = [
  "pattern_bear_candle", "pattern_shooting_star",
  "pattern_bearish_engulfing", "pattern_three_black_crows",
];
export const netBullish = (row) => {
  if (!row) return null;
  const b = BULL_PATTERNS.reduce((a, k) => a + (row[k] === 1 ? 1 : 0), 0);
  const s = BEAR_PATTERNS.reduce((a, k) => a + (row[k] === 1 ? 1 : 0), 0);
  return b - s;
};
// 触发形态总数（看涨+看空+中性结构）——「这只票今天的 K 线信息量」。
export const totalPatterns = (row, all) =>
  !row ? null : (all || PATTERNS).reduce((a, p) => a + (row[p.key] === 1 ? 1 : 0), 0);

export const candleTier = (net) =>
  net == null ? null : net >= 2 ? "bull" : net <= -1 ? "bear" : "neutral";

// 每行一个 { symbol, score(0..100|null), net }。score = 净多形态数的
// 截面百分位（平均名次，并列取平均）；net 是带符号原始计数，供页面
// 分档而不必重算。
export function candleScore(rows) {
  if (!rows || !rows.length) return [];
  const nets = rows.map(netBullish);
  return rows.map((r, i) => {
    const net = nets[i];
    const p = percentileRank(nets, net);
    return { symbol: r.symbol, score: p == null ? null : p * 100, net };
  });
}

// 22 个形态（本截面可用全集），按组划分供触发网格展示。tone 驱动
// 点亮色（pos=绿看涨，neg=红看空，warn=灰结构）。
export const PATTERN_GROUPS = [
  { group: "reversal", label: "反转形态" },
  { group: "confirm", label: "持续/确认" },
  { group: "structure", label: "结构形态" },
  { group: "vol", label: "量价/波动" },
];
export const PATTERNS = [
  // reversal（单根/两根的方向性转折）
  { key: "pattern_hammer", label: "锤子", tone: "pos", group: "reversal" },
  { key: "pattern_shooting_star", label: "流星", tone: "neg", group: "reversal" },
  { key: "pattern_bullish_engulfing", label: "看涨吞没", tone: "pos", group: "reversal" },
  { key: "pattern_bearish_engulfing", label: "看跌吞没", tone: "neg", group: "reversal" },
  // 持续 / 确认 / 三根 / 趋势
  { key: "pattern_bull_candle", label: "阳线", tone: "pos", group: "confirm" },
  { key: "pattern_bear_candle", label: "阴线", tone: "neg", group: "confirm" },
  { key: "pattern_three_white_soldiers", label: "白三兵", tone: "pos", group: "confirm" },
  { key: "pattern_three_black_crows", label: "黑三鸦", tone: "neg", group: "confirm" },
  { key: "pattern_trend_confirm", label: "趋势确认", tone: "pos", group: "confirm" },
  { key: "pattern_ma_bull", label: "均线多头", tone: "pos", group: "confirm" },
  { key: "pattern_pullback_hold", label: "回调支撑", tone: "pos", group: "confirm" },
  { key: "pattern_double_bottom", label: "双底", tone: "pos", group: "confirm" },
  // structure（形状描述，方向中性）
  { key: "pattern_doji", label: "十字", tone: "warn", group: "structure" },
  { key: "pattern_long_upper_shadow", label: "长上影", tone: "neg", group: "structure" },
  { key: "pattern_long_lower_shadow", label: "长下影", tone: "pos", group: "structure" },
  { key: "pattern_inside_bar", label: "内含线", tone: "warn", group: "structure" },
  { key: "pattern_platform_breakout", label: "平台突破", tone: "warn", group: "structure" },
  { key: "pattern_false_breakout", label: "假突破", tone: "neg", group: "vol" },
  // 量价 / 波动背景
  { key: "pattern_volume_breakout", label: "放量突破", tone: "pos", group: "vol" },
  { key: "pattern_volume_shrink_pullback", label: "缩量回调", tone: "warn", group: "vol" },
  { key: "pattern_volatility_contraction", label: "波动收窄", tone: "warn", group: "vol" },
  { key: "pattern_volatility_expansion", label: "波动扩张", tone: "warn", group: "vol" },
];
export const PATTERN_TOTAL = PATTERNS.length; // 22
export function patternTally(rows) {
  const n = rows.length || 1;
  return PATTERNS.map((p) => {
    const count = rows.reduce((a, r) => a + (r?.[p.key] === 1 ? 1 : 0), 0);
    return { ...p, count, share: count / n };
  });
}

// 可点击的 K 线形状桶——生成形态旗标的连续比率。tone：长下影/大实体
// =绿，长上影=红。
export const BUCKET_GROUPS = [
  { group: "body", label: "实体比" },
  { group: "up", label: "上影" },
  { group: "down", label: "下影" },
];
export const BUCKETS = [
  // body_ratio（0–1）：大实体 = 方向坚决
  { group: "body", key: "body_big", label: "大实体 ≥60%", tone: "pos", test: (r) => r.body_ratio != null && r.body_ratio >= 0.6 },
  { group: "body", key: "body_mid", label: "中实体 20–60%", tone: "warn", test: (r) => r.body_ratio != null && r.body_ratio >= 0.2 && r.body_ratio < 0.6 },
  { group: "body", key: "body_small", label: "小/十字 <20%", tone: "neg", test: (r) => r.body_ratio != null && r.body_ratio < 0.2 },
  // upper_shadow：长 = 抛压/拒绝（偏空）
  { group: "up", key: "up_long", label: "长上影 ≥40%", tone: "neg", test: (r) => r.upper_shadow_ratio != null && r.upper_shadow_ratio >= 0.4 },
  { group: "up", key: "up_mid", label: "中上影 15–40%", tone: "warn", test: (r) => r.upper_shadow_ratio != null && r.upper_shadow_ratio >= 0.15 && r.upper_shadow_ratio < 0.4 },
  { group: "up", key: "up_short", label: "短上影 <15%", tone: "pos", test: (r) => r.upper_shadow_ratio != null && r.upper_shadow_ratio < 0.15 },
  // lower_shadow：长 = 支撑/买盘（偏多）
  { group: "down", key: "down_long", label: "长下影 ≥40%", tone: "pos", test: (r) => r.lower_shadow_ratio != null && r.lower_shadow_ratio >= 0.4 },
  { group: "down", key: "down_mid", label: "中下影 15–40%", tone: "warn", test: (r) => r.lower_shadow_ratio != null && r.lower_shadow_ratio >= 0.15 && r.lower_shadow_ratio < 0.4 },
  { group: "down", key: "down_short", label: "短下影 <15%", tone: "neg", test: (r) => r.lower_shadow_ratio != null && r.lower_shadow_ratio < 0.15 },
];

// 一键预设。阈值引用形态旗标 / 派生净额。
export const PRESETS = [
  { key: "bull", label: "看多形态", title: "净多形态 ≥ 2", test: (r) => r._net != null && r._net >= 2 },
  { key: "bear", label: "看空形态", title: "净多形态 ≤ −1", test: (r) => r._net != null && r._net <= -1 },
  { key: "reversal", label: "反转形态", title: "任一反转形态(锤子/吞没/流星)", test: (r) => ["pattern_hammer", "pattern_bullish_engulfing", "pattern_shooting_star", "pattern_bearish_engulfing"].some((k) => r[k] === 1) },
  { key: "hammer", label: "锤子线", title: "锤子(下影长/底部反转)", test: (r) => r.pattern_hammer === 1 },
  { key: "engulf", label: "吞没", title: "看涨或看跌吞没", test: (r) => r.pattern_bullish_engulfing === 1 || r.pattern_bearish_engulfing === 1 },
  { key: "mabull", label: "均线多头", title: "均线多头排列(趋势背景)", test: (r) => r.pattern_ma_bull === 1 },
];

// 今日 K 线阴阳（由 bull/bear/doji 基础旗标派生）。
export const dirOf = (row) =>
  !row ? "—" : row.pattern_bull_candle === 1 ? "阳"
    : row.pattern_bear_candle === 1 ? "阴"
      : row.pattern_doji === 1 ? "十字" : "—";

// 表格行形态旗标（激活的形态，含结构）。
export function candleFlags(row) {
  return PATTERNS.filter((p) => row?.[p.key] === 1)
    .map((p) => ({ label: p.label, tone: p.tone, title: p.label }));
}

// 概览统计：中位净多 / 中位触发数。
export const medNet = (rows) => median((rows || []).map((r) => netBullish(r)));
export const medTotal = (rows) => median((rows || []).map((r) => totalPatterns(r)));
