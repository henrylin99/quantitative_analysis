// 估值维度打分 lib —— 截面级「谁的价格乘数最便宜」扫描。经典价值投资轴：
// 把「便宜」拆解为原始价格乘数并逐一做透明百分位，可独立按 PE/PB/PS/PEG
// 排名扫描。
//
// 五项乘数是逆向的（越低=越便宜=越好）：trailing_pe、forward_pe、
// price_to_book、ps_ratio、peg_ratio；dividend_yield 是正向（越高越好）。
//
// 颜色方向混合：估值分本身常规（高=便宜=绿），原始乘数行逆向
// （低 PE/PB/PS/PEG = 绿，高 = 红），股息率常规（高 = 绿）。
// 边界情况：trailing_pe 可能为 null（亏损股）；forward_pe / price_to_book
// 对亏损/负净资产公司可能为负——负乘数不是「便宜」，不参与排名并显示
// 亏损/剔除；股息率为百分数（0.35 = 0.35%），null = 无股息。
//
// 纯函数：页面组件直接 import 做打分与统计。

import { percentileRank, bandFor } from "./scan_shared.js";

// 估值分档（0–100，三等分）。>=66.7 便宜，33.3–66.7 合理，else 昂贵。
export const VAL_BANDS = [
  { key: "cheap", label: "便宜", min: 66.7, tone: "pos" },
  { key: "fair", label: "合理", min: 33.3, tone: "warn" },
  { key: "pricey", label: "昂贵", min: 0, tone: "neg" },
];
export const bandOf = (score) => bandFor(score, VAL_BANDS);

// 概览三档。
export const VAL_TIERS = [
  { key: "cheap", label: "便宜", tone: "pos" },
  { key: "fair", label: "合理", tone: "warn" },
  { key: "pricey", label: "昂贵", tone: "neg" },
];
export const TIER_ORDER = ["cheap", "fair", "pricey"];

// 逆向乘数（低=便宜）与正向股息率。
const INV = ["trailing_pe", "forward_pe", "price_to_book", "ps_ratio", "peg_ratio"];
const FWD = ["dividend_yield"];

// 乘数参与排名仅当它是有限的正数：负 PE/PB = 亏损/负净资产（不是便宜），
// +inf/NaN 排除。
const validVals = (rows, key) => rows.map((r) => r[key]).filter((v) => Number.isFinite(v) && v > 0);

// 每行一个 { symbol, score(0..100|null) }。每个逆向乘数贡献
// (1 − percentileRank)×100（乘数最低 → ~100 = 最便宜）；dividend_yield 贡献
// percentileRank×100（股息最高 → ~100）。分数 = 实际拥有的贡献均值：
// 无股息公司按乘数排名，无有效 PE 的亏损公司按 PB/PS/PEG 排名。
// 全部缺失才返回 null。越高 = 越便宜。
export function valuationScore(rows) {
  if (!rows || !rows.length) return [];
  const cols = {};
  for (const k of [...INV, ...FWD]) cols[k] = validVals(rows, k);
  return rows.map((r) => {
    const parts = [];
    for (const k of INV) {
      const v = r[k];
      if (Number.isFinite(v) && v > 0) parts.push(1 - percentileRank(cols[k], v));
    }
    for (const k of FWD) {
      const v = r[k];
      if (Number.isFinite(v) && v > 0) parts.push(percentileRank(cols[k], v));
    }
    if (!parts.length) return { symbol: r.symbol, score: null };
    return { symbol: r.symbol, score: (parts.reduce((a, b) => a + b, 0) / parts.length) * 100 };
  });
}

// 六个比率（指标行/表格口径说明）。dir 驱动着色：inv（低=绿）或 fwd（高=绿）。
export const RATIOS = [
  { key: "trailing_pe", label: "市盈率TTM", dir: "inv", desc: "股价/每股收益(过去12月)" },
  { key: "forward_pe", label: "远期市盈率", dir: "inv", desc: "按预测每股收益算的PE" },
  { key: "price_to_book", label: "市净率", dir: "inv", desc: "股价/每股净资产" },
  { key: "ps_ratio", label: "市销率", dir: "inv", desc: "市值/年营收" },
  { key: "peg_ratio", label: "PEG", dir: "inv", desc: "PE/盈利增速,<1常视为低估" },
  { key: "dividend_yield", label: "股息率", dir: "fwd", desc: "年度股息/股价" },
];

// 可点击的乘数桶（概览过滤面板用）。
export const BUCKET_GROUPS = [
  { group: "pe", label: "市盈率" },
  { group: "pb", label: "市净率" },
  { group: "ps", label: "市销率" },
  { group: "peg", label: "PEG" },
];
export const BUCKETS = [
  { group: "pe", key: "pe_low", label: "低估 <15", tone: "pos", test: (r) => r.trailing_pe != null && r.trailing_pe > 0 && r.trailing_pe < 15 },
  { group: "pe", key: "pe_fair", label: "合理 15–25", tone: "warn", test: (r) => r.trailing_pe != null && r.trailing_pe >= 15 && r.trailing_pe <= 25 },
  { group: "pe", key: "pe_high", label: "高估 >25", tone: "neg", test: (r) => r.trailing_pe != null && r.trailing_pe > 25 },
  { group: "pb", key: "pb_low", label: "低估 <3", tone: "pos", test: (r) => r.price_to_book != null && r.price_to_book > 0 && r.price_to_book < 3 },
  { group: "pb", key: "pb_fair", label: "合理 3–8", tone: "warn", test: (r) => r.price_to_book != null && r.price_to_book >= 3 && r.price_to_book <= 8 },
  { group: "pb", key: "pb_high", label: "高估 >8", tone: "neg", test: (r) => r.price_to_book != null && r.price_to_book > 8 },
  { group: "ps", key: "ps_low", label: "低估 <2", tone: "pos", test: (r) => r.ps_ratio != null && r.ps_ratio > 0 && r.ps_ratio < 2 },
  { group: "ps", key: "ps_fair", label: "合理 2–5", tone: "warn", test: (r) => r.ps_ratio != null && r.ps_ratio >= 2 && r.ps_ratio <= 5 },
  { group: "ps", key: "ps_high", label: "高估 >5", tone: "neg", test: (r) => r.ps_ratio != null && r.ps_ratio > 5 },
  { group: "peg", key: "peg_low", label: "低估 <1", tone: "pos", test: (r) => r.peg_ratio != null && r.peg_ratio > 0 && r.peg_ratio < 1 },
  { group: "peg", key: "peg_fair", label: "合理 1–2", tone: "warn", test: (r) => r.peg_ratio != null && r.peg_ratio >= 1 && r.peg_ratio <= 2 },
  { group: "peg", key: "peg_high", label: "高估 >2", tone: "neg", test: (r) => r.peg_ratio != null && r.peg_ratio > 2 },
];

// 一键预设。阈值引用估值分 + 原始乘数。
export const PRESETS = [
  { key: "cheap", label: "便宜价值", title: "估值分 ≥ 66.7(全市场最便宜的三分之一)", test: (r) => r._value != null && r._value >= 66.7 },
  { key: "pricey", label: "昂贵高估", title: "估值分 < 33.3(全市场最贵的三分之一)", test: (r) => r._value != null && r._value < 33.3 },
  { key: "lowpe", label: "低PE", title: "市盈率 0–15(经典低PE)", test: (r) => r.trailing_pe != null && r.trailing_pe > 0 && r.trailing_pe < 15 },
  { key: "lowpeg", label: "低PEG", title: "PEG 0–1(增速调整后低估)", test: (r) => r.peg_ratio != null && r.peg_ratio > 0 && r.peg_ratio < 1 },
  { key: "highyield", label: "高股息", title: "股息率 ≥ 3%", test: (r) => r.dividend_yield != null && r.dividend_yield >= 3 },
  { key: "growcheap", label: "便宜且有盈利", title: "估值分 ≥ 60 且 ROE > 0", test: (r) => r._value != null && r._value >= 60 && r.roe != null && r.roe > 0 },
];

// 表格行估值提示旗标。
export function valuationFlags(row) {
  const out = [];
  if (row.trailing_pe != null && row.trailing_pe > 0 && row.trailing_pe < 15) out.push({ label: "低PE", tone: "pos", title: "市盈率 0–15" });
  if (row.peg_ratio != null && row.peg_ratio > 0 && row.peg_ratio < 1) out.push({ label: "低PEG", tone: "pos", title: "PEG < 1" });
  if (row.dividend_yield != null && row.dividend_yield >= 3) out.push({ label: "高股息", tone: "pos", title: "股息率 ≥ 3%" });
  if (row.trailing_pe != null && row.trailing_pe <= 0) out.push({ label: "亏损", tone: "neg", title: "TTM 亏损,PE 剔除" });
  if (row.price_to_book != null && row.price_to_book <= 0) out.push({ label: "负净资产", tone: "neg", title: "市净率为负,剔除" });
  return out;
}
