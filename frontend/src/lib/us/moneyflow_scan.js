// 资金流向维度打分 lib —— 截面级「谁在被吸筹、谁在被派发」扫描。
// 表面原始累积/派发输入——OBV（累积带符号成交量）、Chaikin 振荡器
// （A/D 线动量）、VWAP（日内公允价值）与成交额——并合成为透明的资金分。
//
// 四个原始列都是尺度相关的绝对量（高价股/大市值天然占优），直接做
// 百分位只会按公司规模重排。因此先派生尺度不变比率再排名：
// 收盘 vs VWAP %、成交额/市值（相对换手）、obv/total_share（流通单位
// 净累积）、chaikin_osc/amount（累积强度）。moneyflowScore = 四项分位
// 均值（全部常规方向：高 = 净买入 = 绿）。
//
// 颜色方向常规（与动量同向、与风险相反）：高分/正值 = 吸筹 = 绿。

import { percentileRank, bandFor } from "./scan_shared.js";

// 资金分档（0–100，三等分）。>=66.7 流入，33.3–66.7 中性，else 流出。
export const MF_BANDS = [
  { key: "inflow", label: "资金流入", min: 66.7, tone: "pos" },
  { key: "neutral", label: "中性", min: 33.3, tone: "warn" },
  { key: "outflow", label: "资金流出", min: 0, tone: "neg" },
];
export const bandOf = (score) => bandFor(score, MF_BANDS);

// 概览三档。inflow = 净吸筹（绿），outflow = 净派发（红）。
export const MF_TIERS = [
  { key: "inflow", label: "资金流入", tone: "pos" },
  { key: "neutral", label: "中性", tone: "warn" },
  { key: "outflow", label: "资金流出", tone: "neg" },
];
export const TIER_ORDER = ["inflow", "neutral", "outflow"];

// 从原始 API 字段派生四个尺度不变资金比率。各自守护分母
// （vwap/market_cap/total_share/amount 非零），输入缺失返回 null。
// 后端已直接输出 vwap / obv / chaikin_osc 原始列，这里只做派生。
// 结果注入每行为 _vwap_dev / _rel_turn / _obv_ratio / _chaik_ratio。
export function deriveFlow(r) {
  const c = r.close, vw = r.vwap, amt = r.amount, mc = r.market_cap,
    obv = r.obv, chaik = r.chaikin_osc, shares = r.total_share;
  return {
    _vwap_dev: Number.isFinite(c) && Number.isFinite(vw) && vw !== 0
      ? ((c - vw) / vw) * 100 : null,
    _rel_turn: Number.isFinite(amt) && Number.isFinite(mc) && mc !== 0
      ? (amt / mc) * 100 : null,
    _obv_ratio: Number.isFinite(obv) && Number.isFinite(shares) && shares !== 0
      ? obv / shares : null,
    _chaik_ratio: Number.isFinite(chaik) && Number.isFinite(amt) && amt !== 0
      ? chaik / amt : null,
  };
}

// 四个派生指标 key（展示顺序）。dir 恒为 fwd（高 = 吸筹 = 好）。
export const FLOW_RATIOS = [
  { key: "_vwap_dev", label: "VWAP偏离", dir: "fwd", desc: "(收盘−VWAP)/VWAP,正=收盘在日内均价上方=买盘强" },
  { key: "_rel_turn", label: "相对换手", dir: "fwd", desc: "成交额/市值,今日有多大比例的筹码换手" },
  { key: "_obv_ratio", label: "OBV/流通", dir: "fwd", desc: "OBV/总股本,累计净累积占流通的倍数,正=净流入" },
  { key: "_chaik_ratio", label: "Chaikin强度", dir: "fwd", desc: "Chaikin振荡/成交额,累积/派发动量强度" },
];

// 每行一个 { symbol, score(0..100|null) }。四个派生比率的截面百分位
// 均值——全部常规方向（高 = 净吸筹）。缺失分量跳过；全部缺失才 null。
// 输入须是已注入 deriveFlow 的行（调用方先 augment），页面与测试共享
// 同一条派生路径。
export function moneyflowScore(derivedRows) {
  if (!derivedRows || !derivedRows.length) return [];
  const cols = {};
  for (const r of FLOW_RATIOS) cols[r.key] = derivedRows.map((x) => x[r.key]);
  return derivedRows.map((r) => {
    const parts = [];
    for (const m of FLOW_RATIOS) {
      const v = r[m.key];
      if (Number.isFinite(v)) parts.push(percentileRank(cols[m.key], v));
    }
    if (!parts.length) return { symbol: r.symbol, score: null };
    return { symbol: r.symbol, score: (parts.reduce((a, b) => a + b, 0) / parts.length) * 100 };
  });
}

// 可点击的资金因子桶。test 对照派生值（页面传入已 augment 的行）。
// 三组全部常规方向（吸筹/放量 = 绿，派发/缩量 = 红）。
export const BUCKET_GROUPS = [
  { group: "vwap", label: "VWAP偏离" },
  { group: "turn", label: "相对换手" },
  { group: "obv", label: "OBV/流通" },
];
export const BUCKETS = [
  // 收盘 vs VWAP（%）：站上 = 买盘推升（绿），跌破 = 卖压（红）
  { group: "vwap", key: "vwap_above", label: "站上VWAP >+0.3%", tone: "pos", test: (r) => r._vwap_dev != null && r._vwap_dev > 0.3 },
  { group: "vwap", key: "vwap_mid", label: "贴近 ±0.3%", tone: "warn", test: (r) => r._vwap_dev != null && r._vwap_dev >= -0.3 && r._vwap_dev <= 0.3 },
  { group: "vwap", key: "vwap_below", label: "跌破VWAP <-0.3%", tone: "neg", test: (r) => r._vwap_dev != null && r._vwap_dev < -0.3 },
  // 相对换手（占市值 %）：高 = 交投活跃（绿），低 = 交投清淡（红）
  { group: "turn", key: "turn_hot", label: "放量换手 ≥1%", tone: "pos", test: (r) => r._rel_turn != null && r._rel_turn >= 1 },
  { group: "turn", key: "turn_mid", label: "适中 0.3–1%", tone: "warn", test: (r) => r._rel_turn != null && r._rel_turn >= 0.3 && r._rel_turn < 1 },
  { group: "turn", key: "turn_cold", label: "缩量 <0.3%", tone: "neg", test: (r) => r._rel_turn != null && r._rel_turn < 0.3 },
  // OBV/总股本：高正 = 净吸筹（绿），负 = 派发（红）
  { group: "obv", key: "obv_accum", label: "净累积 ≥0.3", tone: "pos", test: (r) => r._obv_ratio != null && r._obv_ratio >= 0.3 },
  { group: "obv", key: "obv_bal", label: "平衡 −0.1~0.3", tone: "warn", test: (r) => r._obv_ratio != null && r._obv_ratio >= -0.1 && r._obv_ratio < 0.3 },
  { group: "obv", key: "obv_dist", label: "净流出 <-0.1", tone: "neg", test: (r) => r._obv_ratio != null && r._obv_ratio < -0.1 },
];

// 一键预设。引用派生字段（页面先 augment 再过滤）。
export const PRESETS = [
  { key: "inflow", label: "资金流入", title: "资金分 ≥ 66.7", test: (r) => r._flow != null && r._flow >= 66.7 },
  { key: "outflow", label: "资金流出", title: "资金分 < 33.3", test: (r) => r._flow != null && r._flow < 33.3 },
  { key: "abovevwap", label: "站上VWAP", title: "收盘 > VWAP", test: (r) => r._vwap_dev != null && r._vwap_dev > 0 },
  { key: "hotturn", label: "放量换手", title: "相对换手 ≥ 1%", test: (r) => r._rel_turn != null && r._rel_turn >= 1 },
  { key: "strongaccum", label: "强OBV累积", title: "OBV/流通 ≥ 0.5", test: (r) => r._obv_ratio != null && r._obv_ratio >= 0.5 },
  { key: "hotinflow", label: "放量且流入", title: "相对换手≥1% 且 资金分≥66.7", test: (r) => r._rel_turn != null && r._rel_turn >= 1 && r._flow != null && r._flow >= 66.7 },
];

// 表格行资金提示旗标。
export function moneyflowFlags(row) {
  const out = [];
  if (row._vwap_dev != null && row._vwap_dev > 0.3) out.push({ label: "站上VWAP", tone: "pos", title: "收盘高于日内均价" });
  if (row._vwap_dev != null && row._vwap_dev < -0.3) out.push({ label: "跌破VWAP", tone: "neg", title: "收盘低于日内均价" });
  if (row._rel_turn != null && row._rel_turn >= 1) out.push({ label: "放量换手", tone: "pos", title: "相对换手 ≥ 1%" });
  if (row._obv_ratio != null && row._obv_ratio >= 0.3) out.push({ label: "净累积", tone: "pos", title: "OBV/流通 ≥ 0.3" });
  if (row._obv_ratio != null && row._obv_ratio < -0.1) out.push({ label: "净派发", tone: "neg", title: "OBV/流通 < −0.1" });
  return out;
}
