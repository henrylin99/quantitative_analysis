import { apiGet } from './client'
import { fetchAuctionBenchmark, fetchAnomalyAnalysis, fetchAnomalyAnalysisByStocks, type AnomalyItem, type AnomalyTag, type AuctionBenchmarkItem } from './market'

export { fetchAuctionBenchmark, fetchAnomalyAnalysis, fetchAnomalyAnalysisByStocks }
export type { AnomalyItem, AnomalyTag, AuctionBenchmarkItem }

// ================= 集合竞价快照 =================

export interface AuctionSnapshotItem {
  ts_code: string
  ticker?: string
  name?: string
  auction_price: number | null
  auction_pct: number | null
  auction_volume: number | null
  auction_amount: number | null
  auction_unmatched: number | null
  auction_turnover_pct: number | null
  auction_yesterday_ratio_pct: number | null
  auction_volume_ratio: number | null
  pre_close_price: number | null
  open_price: number | null
  last_price: number | null
  float_market_cap: number | null
}

export interface AuctionSnapshotData {
  codes: string[]
  stage: 'live' | 'final' | null
  auction_phase: string | null
  data_status: string | null
  items: AuctionSnapshotItem[]
  server_ts?: number
  cached?: boolean
  stale?: boolean
}

/** 实测上游合法值为 live/final（文档写 finallive） */
export function fetchAuctionSnapshot(codes: string[], stage?: 'live' | 'final') {
  return apiGet<AuctionSnapshotData>('/realtime-analysis/auction/snapshot', {
    codes: codes.join(','),
    stage: stage || undefined,
  })
}

// ================= 集合竞价个股机会筛选 =================

export interface AuctionOpportunityItem {
  ts_code: string
  ticker?: string
  name?: string
  warn_type: string | null
  warn_name: string | null
  warn_time: string | null
  bid_price: number | null
  bid_pct: number | null
  bid_amount: number | null
  previous_amount: number | null
  explain: string | null
  grade: string | null
  related_block: unknown
}

export interface AuctionOpportunitiesData {
  date: string | null
  mode: 'real_time' | 'history' | null
  total: number
  page: number
  size: number
  has_next: boolean
  items: AuctionOpportunityItem[]
  server_ts?: number
  cached?: boolean
  stale?: boolean
}

export const AUCTION_MARKETS = [
  { value: 'a_share', label: '全市场' },
  { value: 'sh_sz_main', label: '沪深主板' },
  { value: 'sh_a', label: '沪市A股' },
  { value: 'sz_a', label: '深市A股' },
  { value: 'gem', label: '创业板' },
  { value: 'star', label: '科创板' },
] as const

export function fetchAuctionOpportunities(params: {
  date?: string
  market?: string
  exclude_st?: boolean
  page?: number
  size?: number
}) {
  return apiGet<AuctionOpportunitiesData>('/realtime-analysis/auction/opportunities', {
    date: params.date || undefined,
    market: params.market || undefined,
    exclude_st: params.exclude_st ? 'true' : undefined,
    page: params.page ?? 1,
    size: params.size ?? 20,
  })
}

export interface AuctionOpportunityDates {
  dates: string[]
  latest_date: string | null
  server_ts?: number
}

export function fetchAuctionOpportunityDates() {
  return apiGet<AuctionOpportunityDates>('/realtime-analysis/auction/opportunity-dates')
}

// ================= 异动股票监控名单 =================

export interface AbnormalMonitorItem {
  ts_code: string | null
  name: string | null
  start_date: string | null
  end_date: string | null
  monitor_type: number | null
  severe: boolean
  monitor_label: number | null
}

export interface AbnormalMonitorData {
  state: 'current' | 'history'
  page: number
  size: number
  total: number
  has_next: boolean
  items: AbnormalMonitorItem[]
  server_ts?: number
  cached?: boolean
  stale?: boolean
}

export function fetchAbnormalMonitor(state: 'current' | 'history' = 'current', page = 1, size = 30) {
  return apiGet<AbnormalMonitorData>('/realtime-analysis/auction/abnormal', { state, page, size })
}
