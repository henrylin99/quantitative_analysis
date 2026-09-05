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

// ================= 涨停池 / 连板天梯 / 同花顺板块 =================

/** 涨停池个股（实测字段 2026-09；seal_money 单位为元） */
export interface LimitUpStock {
  ts_code: string
  ticker?: string
  name?: string
  is_st?: boolean
  is_new?: boolean
  last_price?: number
  pct_chg?: number
  limit_up_time?: string
  reason?: string
  continue_day_text?: string
  continue_day_cnt?: number
  seal_money?: number
  max_seal_money?: number
  [key: string]: unknown
}

export interface LimitUpPoolPayload {
  date: string
  total: number
  page: number
  size: number
  items: LimitUpStock[]
  cached?: boolean
  stale?: boolean
}

/** 连板天梯单日（counts 键为连板数字符串，"7" 即 7 板及以上） */
export interface LadderDay {
  date: string | null
  counts: Record<string, number>
  highest: number
  total: number
}

/** 同花顺板块（行业/概念）排行行 */
export interface ThsBoardRow {
  thscode: string
  name?: string
  last_price?: number
  pct_chg?: number
  turnover_yuan?: number
  volume?: number
}

export interface BoardConstituent {
  ts_code: string
  name?: string | null
  last_price?: number | null
  pct_chg?: number | null
  amount_yuan?: number | null
}

export function fetchLimitUpPool(date?: string, page = 1, size = 100) {
  return apiGet<LimitUpPoolPayload>('/market/limit-up/pool', {
    date: date || undefined,
    page,
    size,
  })
}

export function fetchLimitUpLadder() {
  return apiGet<{ days: LadderDay[] }>('/market/limit-up/ladder')
}

export function fetchBoards(tag: 'industry' | 'cn_concept') {
  return apiGet<{ tag: string; items: ThsBoardRow[]; unavailable: string[] }>(
    '/market/boards',
    { tag },
  )
}

export function fetchBoardConstituents(code: string) {
  return apiGet<{ code: string; total: number; items: BoardConstituent[] }>(
    '/market/boards/constituents',
    { code },
  )
}

// ================= 跌停池 / 炸板池 / 热股榜 / 标的检索 =================

/** 跌停池个股（实测字段 2026-09） */
export interface LimitDownStock {
  ts_code: string
  ticker?: string
  name?: string
  last_price?: number
  pct_chg?: number
  first_limit_time?: string
  last_limit_time?: string
  turnover_ratio_pct?: number
  [key: string]: unknown
}

/** 炸板池个股（曾涨停后开板） */
export interface LimitBreakStock {
  ts_code: string
  ticker?: string
  name?: string
  last_price?: number
  pct_chg?: number
  open_times?: number
  turnover_ratio_pct?: number
  turnover?: number
  [key: string]: unknown
}

export type HotPeriod = 'day' | 'hour'

/** 热股榜/飙升榜个股 */
export interface HotStock {
  ts_code: string
  ticker?: string
  name?: string
  rank?: number
  heat?: number | null
  rank_change?: number
  rank_trend?: 'up' | 'down' | 'flat' | string
  [key: string]: unknown
}

export interface TickerSearchItem {
  ts_code: string
  ticker?: string
  name?: string
  exchange?: string
}

function poolParams(date?: string, page = 1, size = 100) {
  return { date: date || undefined, page, size }
}

export function fetchLimitDownPool(date?: string, page = 1, size = 100) {
  return apiGet<LimitUpPoolPayload & { items: LimitDownStock[] }>(
    '/market/limit-down/pool',
    poolParams(date, page, size),
  )
}

export function fetchLimitBreakPool(date?: string, page = 1, size = 100) {
  return apiGet<LimitUpPoolPayload & { items: LimitBreakStock[] }>(
    '/market/limit-break/pool',
    poolParams(date, page, size),
  )
}

export function fetchHotStocks(period: HotPeriod = 'day') {
  return apiGet<{ period: HotPeriod; hot: HotStock[]; skyrocket: HotStock[] }>(
    '/market/hot-stocks',
    { period },
  )
}

export function fetchTickerSearch(q: string, limit = 8) {
  return apiGet<{ query: string; items: TickerSearchItem[] }>('/market/ticker-search', {
    q,
    limit,
  })
}
