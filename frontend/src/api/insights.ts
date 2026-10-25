import { apiGet, apiPost } from './client'

// ============ 估值分位 ============

export interface ValuationPoint { date: string; value: number | null }

export interface ValuationResult {
  error?: string
  ts_code: string
  name: string | null
  start_date: string
  end_date: string
  current: Record<string, number | null>
  percentiles: Record<string, number | null>
  series: Record<string, ValuationPoint[]>
  prices: ValuationPoint[]
}

export interface ThermometerResult {
  error?: string
  series: { date: string; pe: number | null; pb: number | null; pe_pct: number | null; pb_pct: number | null }[]
  index_series: ValuationPoint[]
  index_code: string
  latest: { date: string; pe: number | null; pb: number | null; pe_pct: number | null }
}

export function fetchValuation(tsCode: string): Promise<ValuationResult> {
  return apiGet('/insights/valuation', { ts_code: tsCode }, 120_000)
}

export function fetchThermometer(): Promise<ThermometerResult> {
  return apiGet('/insights/valuation/thermometer', undefined, 120_000)
}

// ============ 资金流深历史 ============

export interface MfStreakRow {
  ts_code: string; name: string | null; streak: number; cum_amount: number; close: number | null
}

export interface MfStreaksResult {
  error?: string
  end_date: string
  window_days: number
  stocks: MfStreakRow[]
}

export interface MfDivRow {
  ts_code: string; name: string | null; pct: number; cum_net: number; close: number | null
}

export interface MfDivergenceResult {
  error?: string
  end_date: string
  window_days: number
  stocks: MfDivRow[]
}

export function fetchMfStreaks(days: number, minStreak: number, top: number): Promise<MfStreaksResult> {
  return apiGet('/insights/moneyflow/streaks', { days, min_streak: minStreak, top }, 120_000)
}

export function fetchMfDivergence(days: number, top: number): Promise<MfDivergenceResult> {
  return apiGet('/insights/moneyflow/divergence', { days, top }, 120_000)
}

// ============ 同业对比 ============

export interface PeerRow {
  ts_code: string; name: string | null; is_target: boolean
  revenue: number | null; n_income: number | null
  rev_yoy: number | null; ni_yoy: number | null
  net_margin: number | null; roe: number | null
  debt_ratio: number | null; ocf_ni: number | null
}

export interface PeerCompareResult {
  error?: string
  ts_code: string; name: string | null; industry: string; year: string
  peers: PeerRow[]
  trend: {
    years: string[]
    stock_revenue: (number | null)[]
    stock_n_income: (number | null)[]
    median_revenue: (number | null)[]
    median_n_income: (number | null)[]
  }
}

export function fetchPeerCompare(tsCode: string, top = 15): Promise<PeerCompareResult> {
  return apiGet('/insights/peer-compare', { ts_code: tsCode, top }, 120_000)
}

// ============ 组合相关性 ============

export interface CorrStatRow {
  ts_code: string; name: string | null
  cum_return: number; ann_vol: number; sharpe: number | null
  max_drawdown: number; risk_contrib: number
}

export interface CorrelationResult {
  error?: string
  days: number; start_date: string; end_date: string
  codes: string[]
  corr_matrix: number[][]
  avg_corr: number | null
  nav: { date: string; value: number }[]
  stats: CorrStatRow[]
}

export function fetchCorrelation(tsCodes: string[], days: number): Promise<CorrelationResult> {
  return apiPost('/insights/correlation', { ts_codes: tsCodes, days }, 120_000)
}

// ============ 日内统计 ============

export interface IntradayResult {
  error?: string
  ts_code: string; name: string | null
  days: number; start_date: string | null; end_date: string | null
  volume_profile: { time: string; avg_vol: number }[]
  overnight: { mean: number | null; std: number | null; win_rate: number | null }
  intraday: { mean: number | null; std: number | null; win_rate: number | null }
  tail30: { mean: number | null; std: number | null; win_rate: number | null }
  scatter: { date: string; overnight: number | null; intraday: number }[]
}

export function fetchIntraday(tsCode: string, days = 60): Promise<IntradayResult> {
  return apiGet('/insights/intraday', { ts_code: tsCode, days }, 120_000)
}

// ============ 事件复盘 ============

export type EventSectionKey = 'limit_up' | 'limit_down' | 'limit_break' | 'ladder' | 'dragon_tiger' | 'mood'

export interface EventDatesResult {
  [key: string]: { label: string; dates: string[] }
}

export interface EventReplayResult {
  error?: string
  date: string
  sections: Partial<Record<EventSectionKey, { label: string; count: number; rows: Record<string, unknown>[] }>>
}

export function fetchEventDates(): Promise<EventDatesResult> {
  return apiGet('/insights/event-dates')
}

export function fetchEventReplay(date: string): Promise<EventReplayResult> {
  return apiGet('/insights/event-replay', { date })
}
