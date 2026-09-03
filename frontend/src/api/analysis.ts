import { apiGet, apiPost } from './client'
import type { BacktestConfig, BacktestResultData, ScreenCriteria, ScreenResultData } from './types'
import type { StockListData } from './types'

export function runScreen(criteria: ScreenCriteria): Promise<ScreenResultData> {
  return apiPost<ScreenResultData>('/analysis/screen', criteria)
}

export function runBacktest(config: BacktestConfig): Promise<BacktestResultData> {
  return apiPost<BacktestResultData>('/analysis/backtest', config)
}

export function fetchStockOptions(pageSize = 100): Promise<StockListData> {
  return apiGet<StockListData>('/stocks', { page: 1, page_size: pageSize })
}
