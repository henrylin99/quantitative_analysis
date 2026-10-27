// 基本面维度打分 lib —— 截面级「谁的基本面质量最高」扫描（快照级降级口径）。
// 港股侧没有季度财务长表与财报日历，「基本面轨迹/财务体检」降级为当前截面
// 的质量/成长/股息/资产负债打分：把 ROE、ROA、利润率、盈利增速、股息率、
// 流动比率与资产负债率逐一做透明截面百分位，合成为单一基本面分。
//
// 量纲（港股同步链路的 yfinance 字段）：roe / roa / margins / earnings_growth
// 均为小数（0.199 = 19.9%）；dividend_yield 已是百分数（3.22 = 3.22%）；
// debt_to_equity 形如 37.5（≈37.5%）。revenue_growth 全市场缺失，不参与。
//
// 方向：盈利能力/成长/股息/流动比率正向（高=好），debt_to_equity 逆向
// （低=好）。分数 = 实际拥有分量的百分位均值，全部缺失才 null。
//
// 纯函数：页面组件直接 import 做打分与统计。

import { percentileRank, bandFor } from "./scan_shared.js";

// 基本面分档（0–100，三等分）。>=66.7 优质，33.3–66.7 中性，else 偏弱。
export const FUND_BANDS = [
  { key: "strong", label: "优质", min: 66.7, tone: "pos" },
  { key: "neutral", label: "中性", min: 33.3, tone: "warn" },
  { key: "weak", label: "偏弱", min: 0, tone: "neg" },
];
export const bandOf = (score) => bandFor(score, FUND_BANDS);

// 概览三档。
export const FUND_TIERS = [
  { key: "strong", label: "优质", tone: "pos" },
  { key: "neutral", label: "中性", tone: "warn" },
  { key: "weak", label: "偏弱", tone: "neg" },
];
export const TIER_ORDER = ["strong", "neutral", "weak"];

const FWD = ["roe", "roa", "profit_margin", "operating_margin", "earnings_growth", "dividend_yield", "current_ratio"];
const INV = ["debt_to_equity"];

// 每行一个 { symbol, score(0..100|null) }。正向指标贡献 percentileRank×100，
// 逆向的 debt_to_equity 贡献 (1 − percentileRank)×100。分数 = 实际拥有的
// 分量均值（缺哪个跳哪个），越高 = 基本面越强。
export function fundScore(rows) {
  if (!rows || !rows.length) return [];
  const cols = {};
  for (const k of [...FWD, ...INV]) cols[k] = rows.map((r) => r[k]).filter(Number.isFinite);
  return rows.map((r) => {
    const parts = [];
    for (const k of FWD) {
      const v = r[k];
      if (Number.isFinite(v)) parts.push(percentileRank(cols[k], v));
    }
    for (const k of INV) {
      const v = r[k];
      if (Number.isFinite(v)) parts.push(1 - percentileRank(cols[k], v));
    }
    if (!parts.length) return { symbol: r.symbol, score: null };
    return { symbol: r.symbol, score: (parts.reduce((a, b) => a + b, 0) / parts.length) * 100 };
  });
}

// 八个指标（表格列口径说明）。pct=true 表示小数按百分数展示。
export const METRICS = [
  { key: "roe", label: "ROE", dir: "fwd", pct: true, desc: "净资产收益率(小数,按%展示)" },
  { key: "roa", label: "ROA", dir: "fwd", pct: true, desc: "总资产收益率(小数,按%展示)" },
  { key: "profit_margin", label: "净利率", dir: "fwd", pct: true, desc: "净利润/营收(小数,按%展示)" },
  { key: "operating_margin", label: "经营利润率", dir: "fwd", pct: true, desc: "经营利润/营收(小数,按%展示)" },
  { key: "earnings_growth", label: "盈利增速", dir: "fwd", pct: true, desc: "盈利同比增速(小数,按%展示)" },
  { key: "dividend_yield", label: "股息率", dir: "fwd", pct: true, desc: "年度股息/股价,已是百分数" },
  { key: "debt_to_equity", label: "负债/权益", dir: "inv", pct: false, desc: "总负债/股东权益,越低越稳健" },
  { key: "current_ratio", label: "流动比率", dir: "fwd", pct: false, desc: "流动资产/流动负债,>2 充裕" },
];

// 可点击的质量桶（概览过滤面板用）。固定阈值，不随截面漂移。
export const BUCKET_GROUPS = [
  { group: "roe", label: "ROE" },
  { group: "margin", label: "净利率" },
  { group: "growth", label: "盈利增速" },
  { group: "dividend", label: "股息率" },
  { group: "debt", label: "负债" },
  { group: "current", label: "流动性" },
];
export const BUCKETS = [
  { group: "roe", key: "roe_high", label: "高ROE ≥15%", tone: "pos", test: (r) => r.roe != null && r.roe >= 0.15 },
  { group: "roe", key: "roe_mid", label: "中 8–15%", tone: "warn", test: (r) => r.roe != null && r.roe >= 0.08 && r.roe < 0.15 },
  { group: "roe", key: "roe_low", label: "低 <8%", tone: "neg", test: (r) => r.roe != null && r.roe < 0.08 },
  { group: "margin", key: "pm_high", label: "高净利率 ≥15%", tone: "pos", test: (r) => r.profit_margin != null && r.profit_margin >= 0.15 },
  { group: "margin", key: "pm_mid", label: "中 5–15%", tone: "warn", test: (r) => r.profit_margin != null && r.profit_margin >= 0.05 && r.profit_margin < 0.15 },
  { group: "margin", key: "pm_low", label: "低/亏损 <5%", tone: "neg", test: (r) => r.profit_margin != null && r.profit_margin < 0.05 },
  { group: "growth", key: "gr_high", label: "高增长 ≥10%", tone: "pos", test: (r) => r.earnings_growth != null && r.earnings_growth >= 0.10 },
  { group: "growth", key: "gr_mid", label: "正增长 0–10%", tone: "warn", test: (r) => r.earnings_growth != null && r.earnings_growth >= 0 && r.earnings_growth < 0.10 },
  { group: "growth", key: "gr_neg", label: "负增长", tone: "neg", test: (r) => r.earnings_growth != null && r.earnings_growth < 0 },
  { group: "dividend", key: "dy_high", label: "高股息 ≥4%", tone: "pos", test: (r) => r.dividend_yield != null && r.dividend_yield >= 4 },
  { group: "dividend", key: "dy_mid", label: "中 1–4%", tone: "warn", test: (r) => r.dividend_yield != null && r.dividend_yield >= 1 && r.dividend_yield < 4 },
  { group: "dividend", key: "dy_low", label: "低/无 <1%", tone: "neg", test: (r) => r.dividend_yield != null && r.dividend_yield < 1 },
  { group: "debt", key: "de_low", label: "低负债 ≤40", tone: "pos", test: (r) => r.debt_to_equity != null && r.debt_to_equity <= 40 },
  { group: "debt", key: "de_mid", label: "中 40–120", tone: "warn", test: (r) => r.debt_to_equity != null && r.debt_to_equity > 40 && r.debt_to_equity <= 120 },
  { group: "debt", key: "de_high", label: "高负债 >120", tone: "neg", test: (r) => r.debt_to_equity != null && r.debt_to_equity > 120 },
  { group: "current", key: "cr_high", label: "充裕 ≥2", tone: "pos", test: (r) => r.current_ratio != null && r.current_ratio >= 2 },
  { group: "current", key: "cr_mid", label: "一般 1–2", tone: "warn", test: (r) => r.current_ratio != null && r.current_ratio >= 1 && r.current_ratio < 2 },
  { group: "current", key: "cr_low", label: "紧张 <1", tone: "neg", test: (r) => r.current_ratio != null && r.current_ratio < 1 },
];

// 一键预设。_score 由页面注入（fundScore 结果）。
export const PRESETS = [
  { key: "strong", label: "质量优选", title: "基本面分 ≥ 66.7(截面最强三分之一)", test: (r) => r._score != null && r._score >= 66.7 },
  { key: "highroe", label: "高ROE", title: "ROE ≥ 15%", test: (r) => r.roe != null && r.roe >= 0.15 },
  { key: "highyield", label: "高股息", title: "股息率 ≥ 4%", test: (r) => r.dividend_yield != null && r.dividend_yield >= 4 },
  { key: "growth", label: "双位数增长", title: "盈利增速 ≥ 10%", test: (r) => r.earnings_growth != null && r.earnings_growth >= 0.10 },
  { key: "lowdebt", label: "低负债", title: "负债/权益 ≤ 40", test: (r) => r.debt_to_equity != null && r.debt_to_equity <= 40 },
  { key: "bluechip", label: "千亿蓝筹", title: "市值 ≥ 1000 亿港元", test: (r) => r.market_cap != null && r.market_cap >= 1e11 },
];

// 表格行基本面提示旗标。
export function fundFlags(row) {
  const out = [];
  if (row.roe != null && row.roe >= 0.15) out.push({ label: "高ROE", tone: "pos", title: "ROE ≥ 15%" });
  if (row.dividend_yield != null && row.dividend_yield >= 4) out.push({ label: "高股息", tone: "pos", title: "股息率 ≥ 4%" });
  if (row.debt_to_equity != null && row.debt_to_equity <= 40) out.push({ label: "低负债", tone: "pos", title: "负债/权益 ≤ 40" });
  if (row.earnings_growth != null && row.earnings_growth < 0) out.push({ label: "负增长", tone: "neg", title: "盈利同比下滑" });
  if (row.debt_to_equity != null && row.debt_to_equity > 120) out.push({ label: "高负债", tone: "neg", title: "负债/权益 > 120" });
  if (row.profit_margin != null && row.profit_margin <= 0) out.push({ label: "亏损", tone: "neg", title: "净利润为负" });
  return out;
}
