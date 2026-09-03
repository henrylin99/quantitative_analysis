import { apiGet, apiPost } from './client'

export interface PatternField {
  key: string
  label: string
  count: number
}

export interface PatternGroup {
  id: string
  label: string
  fields: PatternField[]
}

export interface PatternScreenRow {
  ts_code: string
  name: string
  industry: string | null
  pct_chg: number | null
  close: number | null
  amount: number | null
  total_mv: number | null
  turnover_rate: number | null
  vol_ratio_5: number | null
}

export interface PatternScreenResult {
  total: number
  offset: number
  limit: number
  trade_date: string | null
  rows: PatternScreenRow[]
}

export const PATTERN_SORT_FIELDS = ['pct_chg', 'close', 'amount', 'total_mv', 'turnover_rate', 'vol_ratio_5'] as const
export type PatternSortField = (typeof PATTERN_SORT_FIELDS)[number] | 'ts_code' | 'consec_up_days'

export function fetchPatternGroups(): Promise<PatternGroup[]> {
  return apiGet<PatternGroup[]>('/pattern-screen/groups', undefined, 60_000)
}

export function runPatternScreen(body: {
  patterns: string[]
  sort_by: string
  order: 'asc' | 'desc'
  limit: number
  offset: number
}): Promise<PatternScreenResult> {
  return apiPost<PatternScreenResult>('/pattern-screen/screen', body, 60_000)
}
