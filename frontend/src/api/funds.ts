import { apiGet } from './client'

// ================= 基金数据 /api/fund（扶摇同花顺，信封 {code,message,data}） =================
// 字段与后端 fund_service 对齐：thscode 带市场后缀（510300.SH / 161725.SZ / 025480.OF），
// 百分数为原值（8.88 即 8.88%），日期已由后端归一为 YYYYMMDD（<field>_ymd）。

export const FUND_CODE_RE = /^\d{6}\.(OF|SH|SZ)$/i

/** 场内代码（ETF/LOF，有实时行情与历史日线） */
export function isOnShelfFund(thscode: string): boolean {
  return /\.(SH|SZ)$/i.test(thscode)
}

export interface FundProfile {
  thscode: string
  ticker?: string
  fund_name?: string | null
  estab_date_ymd?: string
  company_id?: string | null
  mgmt_name?: string | null
  manager_name?: string | null
  fund_scale?: number | null
  unit_nav?: number | null
  manager_info?: { id?: string; name?: string; [key: string]: unknown }[]
  trade_rule?: unknown[]
  rate_info?: unknown[]
  [key: string]: unknown
}

export interface FundSnapshotRow {
  thscode: string
  ticker?: string
  last_price?: number
  open_price?: number
  high_price?: number
  low_price?: number
  prev_price?: number
  price_change_ratio_pct?: number
  change?: number
  amplitude_pct?: number
  volume?: number
  turnover?: number
  turnover_ratio_pct?: number
  [key: string]: unknown
}

export interface FundHistoryPoint {
  date?: string
  date_ms?: number
  open_price?: number
  high_price?: number
  low_price?: number
  close_price?: number
  volume?: number
  turnover?: number
  [key: string]: unknown
}

export interface FundNavPoint {
  nav_date_ymd?: string
  nav_date?: number
  unit_nav?: number | null
  adj_nav?: number | null
  [key: string]: unknown
}

export interface FundPerformance {
  thscode: string
  nav_latest: FundNavPoint
  returns: Record<string, unknown>
  drawdowns: Record<string, unknown>
}

export interface FundHoldingItem {
  thscode?: string
  ticker?: string
  stock_name?: string
  hold_ratio?: number
  asset_type?: 'stock' | 'bond' | 'fund' | string
  position_capital?: number
  investment_rank?: number
  period_increase_rate_pct?: number
  start_date_ms_ymd?: string
  end_date_ms_ymd?: string
  publish_date_ms_ymd?: string
  [key: string]: unknown
}

export interface FundHoldings {
  thscode: string
  summary: {
    total_stock_ratio_pct?: number
    total_bond_ratio_pct?: number
    total_fund_ratio_pct?: number
    turnover_rate_pct?: number
    stock_ratio_pct?: number
    main_industry?: string
    concentration_ratio?: number
    [key: string]: unknown
  }
  items: FundHoldingItem[]
}

export interface FundHolderStructureRow {
  merge_scope?: string
  report_date_ms_ymd?: string
  ins_position?: number
  psnl_rate?: number
  holder_amount?: number
  avg_holder_share?: number
  mgmt_staff_hold_rate?: number
  [key: string]: unknown
}

export interface FundTopHolderRow {
  holder_name?: string
  holder_type?: string
  rank?: number
  hold_share?: number
  hold_rate_pct?: number
  report_date_ms_ymd?: string
  [key: string]: unknown
}

export interface FundHolders {
  thscode: string
  structure: FundHolderStructureRow[]
  top: FundTopHolderRow[]
}

export interface FundAssetAllocationRow {
  report_date_ms_ymd?: string
  stock_ratio_pct?: number
  bond_ratio_pct?: number
  deposit_ratio_pct?: number
  other_ratio_pct?: number
  [key: string]: unknown
}

export interface FundIndustryAllocationRow {
  report_period?: string
  industry_name?: string
  ratio_pct?: number
  [key: string]: unknown
}

export interface FundDividendRow {
  per_ten_cash_before_tax?: number
  per_ten_cash_after_tax?: number
  progress?: string
  publish_date_ms_ymd?: string
  registration_date_ms_ymd?: string
  ex_dividend_date_ms_ymd?: string
  payment_date_ms_ymd?: string
  [key: string]: unknown
}

export interface FundDividends {
  thscode: string
  dividend_count?: number
  dividend_total?: number
  items: FundDividendRow[]
}

export type FundNavRange = 'week' | 'month' | 'tmonth' | 'hyear' | 'year' | 'twoyear' | 'tyear' | 'fyear'

export type FundAssetType = 'fund-etf' | 'fund-lof' | 'fund-otc'

export interface FundSearchItem {
  thscode: string
  ticker?: string
  name?: string
  exchange?: string
  asset_type?: string
  [key: string]: unknown
}

/** 基金检索（名称/代码模糊匹配；assetType 可空=全部基金） */
export function fetchFundSearch(q: string, assetType?: FundAssetType, limit = 20) {
  return apiGet<{ query: string; items: FundSearchItem[] }>('/fund/search', {
    q,
    asset_type: assetType || undefined,
    limit,
  })
}

export const FUND_ASSET_TYPE_LABELS: Record<string, string> = {
  'fund-etf': 'ETF',
  'fund-lof': 'LOF',
  'fund-otc': '场外',
}

export function fetchFundProfile(thscode: string) {
  return apiGet<FundProfile>('/fund/profile', { thscode })
}

export function fetchFundSnapshot(thscode: string) {
  return apiGet<FundSnapshotRow>('/fund/snapshot', { thscode })
}

/** ETF 前复权历史日线（start/end 为 YYYYMMDD，窗口超 5 年后端自动截断） */
export function fetchFundHistory(thscode: string, start: string, end: string) {
  return apiGet<{ thscode: string; start: string; end: string; items: FundHistoryPoint[] }>(
    '/fund/history',
    { thscode, start, end },
  )
}

/** 净值序列（场内外基金均可；range 决定窗口长度） */
export function fetchFundNav(thscode: string, range: FundNavRange = 'year') {
  return apiGet<FundNavPoint[]>('/fund/nav', { thscode, range })
}

export function fetchFundPerformance(thscode: string) {
  return apiGet<FundPerformance>('/fund/performance', { thscode })
}

export function fetchFundHoldings(thscode: string) {
  return apiGet<FundHoldings>('/fund/holdings', { thscode })
}

export function fetchFundHolders(thscode: string) {
  return apiGet<FundHolders>('/fund/holders', { thscode })
}

export function fetchFundAssetAllocation(thscode: string) {
  return apiGet<FundAssetAllocationRow[]>('/fund/asset-allocation', { thscode })
}

export function fetchFundIndustryAllocation(thscode: string) {
  return apiGet<FundIndustryAllocationRow[]>('/fund/industry-allocation', { thscode })
}

export function fetchFundDividends(thscode: string) {
  return apiGet<FundDividends>('/fund/dividends', { thscode })
}

// ================= 取数辅助 =================

/** 区间收益/回撤的字段键（week..now），returns 与 drawdowns 共用 */
export const FUND_PERIOD_KEYS = [
  { key: 'week', label: '近1周' },
  { key: 'month', label: '近1月' },
  { key: 'tmonth', label: '近3月' },
  { key: 'hyear', label: '近6月' },
  { key: 'year', label: '近1年' },
  { key: 'twoyear', label: '近2年' },
  { key: 'tyear', label: '近3年' },
  { key: 'fyear', label: '近5年' },
  { key: 'nowyear', label: '今年以来' },
  { key: 'now', label: '成立以来' },
] as const

/** YYYYMMDD 偏移 n 天（按自然日粗算，仅用于图表窗口） */
export function ymdDaysAgo(days: number): string {
  const dt = new Date(Date.now() - days * 86400_000)
  return dt.toISOString().slice(0, 10).replace(/-/g, '')
}

export function todayYmd(): string {
  return new Date().toISOString().slice(0, 10).replace(/-/g, '')
}
