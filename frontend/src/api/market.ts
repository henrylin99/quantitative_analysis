import { apiGet } from './client'

// ================= 行情与数据源 /api/market、/api/datasources（信封 {code,message,data}） =================

export interface QuoteRow {
  ts_code: string
  name: string | null
  last_price: number | null
  open: number | null
  high: number | null
  low: number | null
  prev_close: number | null
  change: number | null
  pct_chg: number | null
  volume: number | null
  turnover: number | null
}

export interface IndexQuote {
  ts_code: string
  last_price: number | null
  pct_chg: number | null
}

export interface BoardRow {
  ts_code: string
  name: string | null
  price: number | null
  pct_chg: number | null
  amount_yuan: number | null
}

export interface MarketDashboard {
  breadth: {
    up: number
    down: number
    flat: number
    limit_up: number
    limit_down: number
    total: number
  }
  distribution: { bucket: string; count: number }[]
  total_amount_yuan: number
  top_gainers: BoardRow[]
  top_losers: BoardRow[]
  top_amount: BoardRow[]
  degraded: boolean
  degraded_reason?: string
  source: 'fuyao' | 'local_parquet' | 'none'
  as_of: string | null
  server_ts?: number | null
}

/** 龙虎榜个股（实测字段 2026-09；change 为小数比例 0.0875=8.75%） */
export interface DragonTigerStock {
  thscode: string
  ticker?: string
  name?: string
  concept_list?: { name: string }[]
  change?: number
  net_value?: number
  net_rate?: number
  hot_rank?: number
  buy_value?: number
  sell_value?: number
  limit_reason?: string
  range_days?: number
  org_net_value?: number
  org_buy_num?: number
  org_sell_num?: number
  hot_money_net_value?: number
  [key: string]: unknown
}

export interface DragonTigerPayload {
  trade_date?: string
  count?: number
  stock_count?: number
  stock_items?: DragonTigerStock[]
  org_items?: DragonTigerStock[]
  hot_money_items?: DragonTigerStock[]
  [key: string]: unknown
}

export interface AuctionBenchmarkItem {
  thscode: string
  ticker?: string
  name?: string
  auction_pct?: number
  tags?: string[]
  [key: string]: unknown
}

export interface SourceStatus {
  checked_at: number
  tushare: { configured: boolean }
  fuyao: { configured: boolean; ok?: boolean; error?: string | null }
  tickflow: { configured: boolean; tier: 'none' | 'free' | 'paid' }
}

export function fetchDashboard() {
  return apiGet<MarketDashboard>('/market/dashboard', undefined, 30_000)
}

export function fetchQuotes(codes: string[]) {
  return apiGet<{ quotes: Record<string, QuoteRow> }>('/market/snapshot', {
    codes: codes.join(','),
  })
}

export function fetchIndices(codes?: string[]) {
  return apiGet<{ indices: IndexQuote[] }>('/market/indices', codes ? { codes: codes.join(',') } : undefined)
}

export function fetchDragonTiger(board: 'all' | 'org' | 'hot_money' = 'all', date?: string) {
  return apiGet<DragonTigerPayload>('/market/dragon-tiger', { board, date: date || undefined })
}

export function fetchAuctionBenchmark(date?: string) {
  return apiGet<{ date?: string; date_ms?: number; item: AuctionBenchmarkItem[] }>(
    '/market/auction-benchmark',
    { date: date || undefined },
  )
}

export function fetchSourceStatus(force = false) {
  return apiGet<SourceStatus>('/datasources/status', force ? { force: 1 } : undefined)
}
