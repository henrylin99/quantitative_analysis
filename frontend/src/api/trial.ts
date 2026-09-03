import { apiGet } from './client'

// ================= 每日市场简报 =================
export interface BriefSummary {
  trade_date: string
  stock_count: number
  advance_count: number
  decline_count: number
  flat_count: number
  limit_up_count: number
  limit_down_count: number
  turnover_total: number
}

export interface BriefSpecialStats {
  first_limit_count: number
  multi_limit_count: number
  bullish_engulfing_count: number
  consec_up_2p_count: number
  consec_up_3p_count: number
  consec_up_5p_count: number
  limit_up_count: number
  limit_down_count: number
}

export interface BriefStockRow {
  ts_code: string
  name: string
  industry: string
  amount: number
  pct_chg: number
  net_mf_amount: number
}

export interface BriefIndustryRow {
  industry: string
  stock_count: number
  advance_count: number
  decline_count: number
  avg_pct_chg: number
  total_amount: number
  net_mf_amount: number
}

export interface MarketBriefData {
  summary: BriefSummary
  brief_lines: string[]
  brief_text: string
  top_amount: BriefStockRow[]
  industry_top: BriefIndustryRow[]
  industry_bottom: BriefIndustryRow[]
  top_mf: { ts_code: string; name: string; industry: string; net_mf_amount: number; pct_chg: number }[]
  special_stats: BriefSpecialStats
}

export const fetchMarketBrief = () => apiGet<MarketBriefData>('/trial/market-brief', undefined, 120_000)

// ================= 财务健康度 =================
export interface ScoredRow {
  ts_code: string
  name: string
  industry: string
  fin_gross_margin: number | null
  fin_net_margin: number | null
  fin_n_cashflow_act: number | null
  fin_debt_ratio: number | null
  fin_n_income_attr_p: number | null
  fin_total_hldr_eqy: number | null
  roe_ratio: number | null
  score_gross_margin: number
  score_net_margin: number
  score_cashflow: number
  score_debt_ratio: number
  score_roe: number
  health_score: number
}

export interface FinancialHealthData {
  summary: {
    trade_date: string
    stock_count: number
    avg_score: number
    max_score: number
    min_score: number
    full_score_count: number
    qualified_count: number
  }
  score_distribution: { score: number; count: number; label: string }[]
  scored_rows: ScoredRow[]
}

export const fetchFinancialHealth = () => apiGet<FinancialHealthData>('/trial/financial-health', undefined, 120_000)

// ================= 资金流统计 =================
export interface MoneyflowStatRow {
  ts_code: string
  name: string
  industry: string
  net_mf_amount: number
  lg_net_amount: number
  elg_net_amount: number
}

export interface MoneyflowIndustryRow {
  industry: string
  stock_count: number
  net_mf_amount: number
  lg_buy_amount: number
  lg_sell_amount: number
  elg_buy_amount: number
  elg_sell_amount: number
  lg_net_amount: number
  elg_net_amount: number
}

export interface MoneyflowStatsData {
  summary: {
    trade_date: string
    stock_count: number
    industry_count: number
    total_net_mf_amount: number
    positive_stock_count: number
    negative_stock_count: number
  }
  top_inflow: MoneyflowStatRow[]
  bottom_outflow: MoneyflowStatRow[]
  industry_rows: MoneyflowIndustryRow[]
}

export const fetchMoneyflowStats = () => apiGet<MoneyflowStatsData>('/trial/moneyflow', undefined, 120_000)

// ================= 板块热力图 =================
export interface HeatmapSector {
  name: string
  avg_pct_chg: number
  total_mv: number
  stock_count: number
  up_count: number
  down_count: number
  net_mf_amount: number
  trade_date: string
}

export interface HeatmapStock {
  ts_code: string
  name: string
  industry: string
  pct_chg: number | null
  close: number | null
  total_mv: number | null
  net_mf_amount: number | null
  turnover_rate: number | null
}

export interface HeatmapData {
  sectors: HeatmapSector[]
  stocks: HeatmapStock[]
  trade_date: string
}

export const fetchHeatmap = () => apiGet<HeatmapData>('/trial/heatmap', undefined, 120_000)

// ================= 个股对比雷达 =================
export interface RadarStockRow {
  ts_code: string
  name: string
  industry: string
  pe_ttm: number | null
  pb: number | null
  fin_revenue: number | null
  fin_n_income: number | null
  rsi_6: number | null
  macd: number | null
  turnover_rate: number | null
  net_mf_amount: number | null
  volume_ratio: number | null
  valuation_score: number | null
  growth_score: number | null
  technical_score: number | null
  moneyflow_score: number | null
}

export interface StockRadarData {
  summary: { trade_date: string; stock_count: number; input_codes: string[] }
  radar_axes: { name: string; max: number }[]
  radar_series: { name: string; ts_code: string; industry: string; value: number[] }[]
  stock_rows: RadarStockRow[]
  input_codes_text: string
}

export const fetchStockRadar = (tsCodes: string) =>
  apiGet<StockRadarData>('/trial/stock-radar', { ts_codes: tsCodes }, 120_000)

// ================= 个股全景 =================
export interface PanoramaMetric {
  label: string
  value: number | string | null
}

export interface StockPanoramaData {
  overview: {
    ts_code: string
    name: string
    industry: string
    area: string
    trade_date: string
    close: number | null
    pct_chg: number | null
    amount: number | null
    pe_ttm: number | null
    pb: number | null
    ps_ttm: number | null
    dv_ttm: number | null
  } | null
  financial_panel: PanoramaMetric[]
  technical_panel: PanoramaMetric[]
  moneyflow_panel: PanoramaMetric[]
  status_panel: PanoramaMetric[]
  detail_rows: PanoramaMetric[]
  special_flags: {
    pattern_first_limit: number
    pattern_multi_limit: number
    pattern_bullish_engulfing: number
    consec_up_days: number
  }
  radar_chart: { labels: string[]; values: number[] }
  latest_trade_date: string
}

export const fetchStockPanorama = (tsCode: string) =>
  apiGet<StockPanoramaData>('/trial/stock-panorama', { ts_code: tsCode }, 120_000)
