import { apiGet, apiPost } from './client'

/** 港股快照行（雅虎财经离线快照，涨跌幅/收益率为小数，0.01 = 1%） */
export interface HkStockRow {
  symbol: string
  name: string | null
  name_zh: string | null
  trade_date: string | null
  open: number | null
  high: number | null
  low: number | null
  close: number | null
  pre_close: number | null
  change: number | null
  pct_change: number | null
  volume: number | null
  amount: number | null
  total_share: number | null
  ma5: number | null
  ma10: number | null
  ma20: number | null
  ma60: number | null
  ret_1d: number | null
  ret_5d: number | null
  ret_20d: number | null
  vol_ratio_5: number | null
  amplitude: number | null
  body_ratio: number | null
  upper_shadow_ratio: number | null
  lower_shadow_ratio: number | null
  market_cap: number | null
  forward_pe: number | null
  trailing_pe: number | null
  price_to_book: number | null
  peg_ratio: number | null
  ps_ratio: number | null
  revenue_growth: number | null
  earnings_growth: number | null
  roe: number | null
  roa: number | null
  profit_margin: number | null
  operating_margin: number | null
  debt_to_equity: number | null
  current_ratio: number | null
  dividend_yield: number | null
  dividend_rate: number | null
  risk_ma20_dev: number | null
  risk_ma60_dev: number | null
  risk_dd_20d: number | null
  risk_vol_20d: number | null
  signal_score: number | null
  [key: string]: string | number | null | undefined
}

export interface HkStockListData {
  total: number
  offset: number
  limit: number
  rows: HkStockRow[]
}

export interface HkMeta {
  total: number
  trade_date: string | null
}

export interface HkHistoryBar {
  day: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  ma5?: number | null
  ma20?: number | null
  ma60?: number | null
  [key: string]: string | number | null | undefined
}

export interface HkHistoryData {
  symbol: string
  name: string
  bars: HkHistoryBar[]
}

export function fetchHkMeta() {
  return apiGet<HkMeta>('/hk-stock/meta')
}

export function fetchHkStocks(params: {
  q?: string
  sort_by?: string
  sort_asc?: boolean
  offset?: number
  limit?: number
}) {
  return apiGet<HkStockListData>('/hk-stock/stocks', params)
}

export function fetchHkStock(symbol: string) {
  return apiGet<HkStockRow>(`/hk-stock/stocks/${encodeURIComponent(symbol)}`)
}

export function fetchHkStockHistory(symbol: string, range = '6m') {
  return apiGet<HkHistoryData>(`/hk-stock/stocks/${encodeURIComponent(symbol)}/history`, { range })
}

/** 同步任务状态（后台子进程运行 build_snapshot.py） */
export interface MarketSyncStatus {
  status: 'idle' | 'running' | 'success' | 'failed'
  message: string | null
  started_at: string | null
  finished_at: string | null
  returncode: number | null
  log_tail?: string | null
  total: number | null
  trade_date: string | null
}

export function fetchSyncStatus() {
  return apiGet<MarketSyncStatus>('/hk-stock/sync')
}

export function startSync() {
  return apiPost<MarketSyncStatus>('/hk-stock/sync')
}
