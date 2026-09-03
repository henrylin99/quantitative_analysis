import { apiGet } from './client'

// —— 个股资金流（注意：该接口为旧→新升序返回，与 history/factors 的倒序不同） ——
export interface MoneyflowRow {
  trade_date: string
  net_mf_amount: number | null
  buy_elg_amount: number | null
  sell_elg_amount: number | null
  buy_lg_amount: number | null
  sell_lg_amount: number | null
  buy_md_amount: number | null
  sell_md_amount: number | null
  buy_sm_amount: number | null
  sell_sm_amount: number | null
}

// —— 筹码分布（升序返回） ——
export interface CyqRow {
  trade_date: string
  his_low: number | null
  his_high: number | null
  cost_5pct: number | null
  cost_15pct: number | null
  cost_50pct: number | null
  cost_85pct: number | null
  cost_95pct: number | null
  weight_avg: number | null
  winner_rate: number | null
}

export interface FinancialStatements {
  balance_sheet: Record<string, unknown> | null
  income_statement: Record<string, unknown> | null
  cash_flow: Record<string, unknown> | null
}

export function fetchStockMoneyflow(tsCode: string, limit = 30): Promise<MoneyflowRow[]> {
  return apiGet<MoneyflowRow[]>(`/stocks/${encodeURIComponent(tsCode)}/moneyflow`, { limit })
}

export function fetchStockCyq(tsCode: string, limit = 30): Promise<CyqRow[]> {
  return apiGet<CyqRow[]>(`/stocks/${encodeURIComponent(tsCode)}/cyq`, { limit })
}

export function fetchStockFinancials(tsCode: string): Promise<FinancialStatements> {
  return apiGet<FinancialStatements>(`/stocks/${encodeURIComponent(tsCode)}/financials`)
}

export function fetchStockCompany(tsCode: string): Promise<Record<string, unknown>> {
  return apiGet<Record<string, unknown>>(`/stocks/${encodeURIComponent(tsCode)}/company`)
}
