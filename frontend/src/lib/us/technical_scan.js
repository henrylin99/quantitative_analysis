// 技术信号维度打分 lib —— 截面级「当下谁的技术形态最强」扫描。
// 消费后端预计算的 23 个 ind_* 二元旗标 + signal_score（技术动量强度复合分），
// 在全市场截面上做百分位打分与信号统计，用于一次性扫描全部标的的
// 超卖反弹 / 强趋势 / 布林收口 / MACD 交叉等形态，而不必逐只看图。
//
// 纯函数：页面组件直接 import 这些函数做打分与过滤，共享同一实现。

import { percentileRank, bandFor } from "./scan_shared.js";

// 23 个二元技术信号旗标，按指标族分组并标注方向：
//   bull    — 看多读数（超卖=反弹机会、上升趋势、金叉…）
//   bear    — 看空读数（超买=谨慎、死叉、触上轨…）
//   neutral — 形态而非方向（布林收口=变盘临近，方向未定）
// dir 驱动着色并参与净信号统计；key 与后端列名一致。
export const SIGNALS = [
  // 趋势 — trend regime
  { key: "ind_adx_strong_trend", label: "ADX强趋势", family: "trend", dir: "bull", note: "ADX>25 趋势确立" },
  { key: "ind_di_bull_cross", label: "+DI多头", family: "trend", dir: "bull", note: "+DI 上穿 −DI 多头排列" },
  // 动量 — oscillators（超卖=看涨反转机会，超买=看跌警示）
  { key: "ind_cci_oversold", label: "CCI超卖", family: "momentum", dir: "bull", note: "CCI<−100 超卖反弹机会" },
  { key: "ind_cci_overbought", label: "CCI超买", family: "momentum", dir: "bear", note: "CCI>+100 超买回调风险" },
  { key: "ind_stoch_oversold", label: "Stoch超卖", family: "momentum", dir: "bull", note: "%K<20 超卖" },
  { key: "ind_stoch_overbought", label: "Stoch超买", family: "momentum", dir: "bear", note: "%K>80 超买" },
  { key: "ind_stoch_bull_cross", label: "Stoch金叉", family: "momentum", dir: "bull", note: "%K 上穿 %D" },
  { key: "ind_macd_bull_cross", label: "MACD金叉", family: "momentum", dir: "bull", note: "DIF 上穿 DEA" },
  { key: "ind_macd_bear_cross", label: "MACD死叉", family: "momentum", dir: "bear", note: "DIF 下穿 DEA" },
  { key: "ind_macd_hist_positive", label: "MACD柱>0", family: "momentum", dir: "bull", note: "柱状图为正 多头动能" },
  { key: "ind_rsi_oversold", label: "RSI超卖", family: "momentum", dir: "bull", note: "RSI<30 超卖反弹" },
  { key: "ind_rsi_overbought", label: "RSI超买", family: "momentum", dir: "bear", note: "RSI>70 超买回调风险" },
  { key: "ind_rsi_bull_divergence", label: "RSI底背离", family: "momentum", dir: "bull", note: "价创新低 RSI 不创新低" },
  { key: "ind_willr_oversold", label: "WillR超卖", family: "momentum", dir: "bull", note: "%R<−80 超卖" },
  { key: "ind_willr_overbought", label: "WillR超买", family: "momentum", dir: "bear", note: "%R>−20 超买" },
  { key: "ind_mfi_oversold", label: "MFI超卖", family: "momentum", dir: "bull", note: "MFI<20 资金超卖" },
  { key: "ind_mfi_overbought", label: "MFI超买", family: "momentum", dir: "bear", note: "MFI>80 资金超买" },
  // 波动 — volatility / bands
  { key: "ind_bb_squeeze", label: "布林收口", family: "volatility", dir: "neutral", note: "带宽收窄 变盘临近(方向未定)" },
  { key: "ind_bb_upper_touch", label: "触上轨", family: "volatility", dir: "bear", note: "价格触及布林上轨 超买" },
  { key: "ind_bb_lower_touch", label: "触下轨", family: "volatility", dir: "bull", note: "价格触及布林下轨 超卖" },
  // 量能 — volume / money flow
  { key: "ind_obv_uptrend", label: "OBV上升", family: "volume", dir: "bull", note: "量能潮上升 资金流入" },
  { key: "ind_chaikin_bullish", label: "Chaikin多头", family: "volume", dir: "bull", note: "资金流向多头 Accumulation" },
  { key: "ind_price_above_vwap", label: "VWAP之上", family: "volume", dir: "bull", note: "收盘高于成交加权均价" },
];

export const FAMILY_LABEL = { trend: "趋势", momentum: "动量", volatility: "波动", volume: "量能" };
export const FAMILY_ORDER = ["trend", "momentum", "volatility", "volume"];
export const DIR_TONE = { bull: "pos", bear: "neg", neutral: "warn" };

// 技术分档（0–100 截面百分位）。>=60 技术强势，40–60 中性，<=40 弱势。
export const TECH_BANDS = [
  { key: "strong", label: "技术强势", min: 60, tone: "pos" },
  { key: "neutral", label: "中性", min: 40, tone: "warn" },
  { key: "weak", label: "技术弱势", min: 0, tone: "neg" },
];
export const bandOf = (score) => bandFor(score, TECH_BANDS);

// 每行一个 { symbol, score(0..100|null) }。对预计算 signal_score（跟踪
// RSI / ret_20d / 趋势状态的技术动量强度复合分）做截面百分位：分数越高
// = 该截面上技术动量越强（常伴随超买）。
export function techScore(rows) {
  if (!rows || !rows.length) return [];
  const series = rows.map((r) => r.signal_score);
  return rows.map((r) => ({
    symbol: r.symbol,
    score: r.signal_score == null ? null : percentileRank(series, r.signal_score) * 100,
  }));
}

// 单只股票的活跃旗标统计：看涨 / 看跌 / 中性（收口）个数 + 净信号
// （bull−bear）。neutral 计数但不计入净信号——它是形态而非投票。
export function signalSummary(row) {
  let bull = 0, bear = 0, neutral = 0;
  for (const s of SIGNALS) {
    if (row?.[s.key] === 1) {
      if (s.dir === "bull") bull++;
      else if (s.dir === "bear") bear++;
      else neutral++;
    }
  }
  return { bull, bear, neutral, net: bull - bear, active: bull + bear };
}

// 布林 %B —— 价格在带内的位置。0=下轨 1=上轨（中轨 0.5）。
// >1 破上轨（超买突破），<0 破下轨（超卖）。
export function bbPctB(row) {
  const { close, bb_upper, bb_lower } = row || {};
  if (![close, bb_upper, bb_lower].every(Number.isFinite)) return null;
  const w = bb_upper - bb_lower;
  if (w === 0) return null;
  return (close - bb_lower) / w;
}

// 全市场信号触发统计：每个信号当前有多少只股票触发。
// 返回 SIGNALS 各项附 count + share。
export function marketTally(rows) {
  const n = rows.length || 1;
  return SIGNALS.map((s) => {
    const count = rows.reduce((acc, r) => acc + (r?.[s.key] === 1 ? 1 : 0), 0);
    return { ...s, count, share: count / n };
  });
}

// 一键筛选预设。阈值引用原始 ind_* 旗标与指标值；预设间允许重叠
// —— 它们是观察同一截面的不同视角。
export const PRESETS = [
  { key: "trend", label: "强趋势", title: "ADX 强趋势 且 收盘在 VWAP 之上(顺势)", test: (r) => r.ind_adx_strong_trend === 1 && r.ind_price_above_vwap === 1 },
  { key: "oversold", label: "超卖反弹", title: "任一振荡器超卖(RSI/CCI/Stoch/WillR/MFI)", test: (r) => r.ind_rsi_oversold === 1 || r.ind_cci_oversold === 1 || r.ind_stoch_oversold === 1 || r.ind_willr_oversold === 1 || r.ind_mfi_oversold === 1 },
  { key: "squeeze", label: "布林收口", title: "布林带收口 变盘临近", test: (r) => r.ind_bb_squeeze === 1 },
  { key: "overbought", label: "超买风险", title: "RSI 超买 且 (CCI 或 Stoch 超买)", test: (r) => r.ind_rsi_overbought === 1 && (r.ind_cci_overbought === 1 || r.ind_stoch_overbought === 1) },
  { key: "volbull", label: "放量上涨", title: "OBV 上升 且 收盘在 VWAP 之上(资金流入)", test: (r) => r.ind_obv_uptrend === 1 && r.ind_price_above_vwap === 1 },
];
