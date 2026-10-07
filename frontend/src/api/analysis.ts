import { apiPost } from './client'
import type { BacktestConfig, BacktestResultData, ScreenCriteria, ScreenResultData } from './types'

export function runScreen(criteria: ScreenCriteria): Promise<ScreenResultData> {
  return apiPost<ScreenResultData>('/analysis/screen', criteria)
}

export function runBacktest(config: BacktestConfig): Promise<BacktestResultData> {
  return apiPost<BacktestResultData>('/analysis/backtest', config)
}

// ================= 参数寻优（grid / walk_forward） =================

export interface OptimizeGridRow {
  params: Record<string, number>
  valid: boolean
  error?: string
  total_return: number | null
  annual_return?: number | null
  sharpe_ratio: number | null
  max_drawdown: number | null
  win_rate: number | null
  total_trades: number
  benchmark_return?: number | null
}

export interface OptimizeResult {
  mode: 'grid' | 'walk_forward'
  ts_code: string
  strategy_type: string
  metric: string
  error?: string
  // grid
  n_combos?: number
  results?: OptimizeGridRow[]
  best?: OptimizeGridRow | null
  note?: string
  // walk_forward
  is_days?: number
  oos_days?: number
  step?: number
  windows?: Array<{
    is_start: string
    is_end: string
    oos_start: string
    oos_end: string
    best_params: Record<string, number>
    is_metric: number
    is_total_return: number | null
    oos_total_return: number | null
    oos_sharpe: number | null
    oos_trades: number | null
    oos_benchmark_return: number | null
    oos_valid: boolean
  }>
  param_stability?: Record<string, Array<{ value: number; count: number }>>
  summary?: {
    n_windows: number
    n_oos_valid: number
    oos_hit_rate: number | null
    oos_chained_return: number | null
    oos_mean_return: number | null
    is_mean_metric: number | null
  }
}

export function runBacktestOptimize(body: {
  ts_code: string
  strategy_type: string
  start_date: string
  end_date: string
  mode: 'grid' | 'walk_forward'
  metric?: string
  is_days?: number
  oos_days?: number
  step?: number
}): Promise<OptimizeResult> {
  return apiPost<OptimizeResult>('/analysis/backtest/optimize', body, 300_000)
}
