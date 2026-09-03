import { apiGet } from './client'
import type { StockBasic, StockListData } from './types'

export function fetchStocks(params: {
  page?: number
  page_size?: number
  industry?: string
  area?: string
  search?: string
}): Promise<StockListData> {
  return apiGet<StockListData>('/stocks', params)
}

export function fetchIndustries(): Promise<string[]> {
  return apiGet<string[]>('/industries')
}

export function fetchAreas(): Promise<string[]> {
  return apiGet<string[]>('/areas')
}

export function fetchStockInfo(tsCode: string): Promise<StockBasic> {
  return apiGet<StockBasic>(`/stocks/${encodeURIComponent(tsCode)}`)
}

export function fetchStockHistory(tsCode: string, limit: number) {
  return apiGet<import('./types').DailyBar[]>(`/stocks/${encodeURIComponent(tsCode)}/history`, { limit })
}

export function fetchStockFactors(tsCode: string, limit: number) {
  return apiGet<import('./types').FactorRow[]>(`/stocks/${encodeURIComponent(tsCode)}/factors`, { limit })
}
