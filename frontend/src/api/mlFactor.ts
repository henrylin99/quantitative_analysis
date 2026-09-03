import { extractApiError, rawDelete, rawGet, rawPost, rawPut } from './client'

// ================= 因子 =================
export interface FactorDef {
  factor_id: string
  factor_name: string
  factor_type: 'technical' | 'fundamental' | 'money_flow' | 'chip' | 'other' | string
  is_builtin: boolean
  is_active: boolean
  description: string | null
  formula: string | null
  params: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface FactorCapabilities {
  allowed_columns: string[]
  allowed_series_methods: string[]
  allowed_window_methods: string[]
  allowed_functions: string[]
  examples: string[]
}

export const fetchFactors = (factorType?: string) =>
  rawGet<{ success: boolean; factors: FactorDef[]; total_count: number }>(
    '/ml-factor/factors/list',
    factorType ? { factor_type: factorType } : undefined,
  )

export const fetchFactorCapabilities = () => rawGet<{ success: boolean; capabilities: FactorCapabilities }>('/ml-factor/factors/custom-capabilities')

export const createCustomFactor = async (body: {
  factor_id: string
  factor_name: string
  factor_type: string
  factor_formula: string
  description?: string
}) => {
  try {
    return await rawPost<{ success: boolean; message?: string; error?: string }>('/ml-factor/factors/custom', body)
  } catch (e) {
    throw new Error(extractApiError(e, '创建因子失败'))
  }
}

export const calculateFactors = async (tradeDate: string) => {
  try {
    return await rawPost<{ success: boolean; trade_date: string; results: unknown }>('/ml-factor/factors/calculate', {
      trade_date: tradeDate,
      factor_ids: [],
      ts_codes: [],
    }, 600_000)
  } catch (e) {
    throw new Error(extractApiError(e, '因子计算失败'))
  }
}

// ================= 模型 =================
export interface ModelDef {
  model_id: string
  model_name: string
  model_type: string
  target_type: string
  status: string
  accuracy: number | null
  factor_list?: string[]
  model_params?: Record<string, unknown>
  training_config?: Record<string, unknown>
  created_at: string
  updated_at?: string
}

export interface ModelPrediction {
  ts_code: string
  trade_date: string
  model_id: string
  predicted_return: number
  probability_score: number | null
  rank_score: number | null
}

export interface ModelDetail extends ModelDef {
  model_file_exists: boolean
  scaler_file_exists: boolean
  prediction_summary: {
    total_predictions: number
    unique_trade_dates: number
    unique_ts_codes: number
    latest_trade_date: string | null
    latest_created_at: string | null
  } | null
  recent_predictions: ModelPrediction[]
}

export interface TrainJob {
  job_id: string
  model_id: string
  status: 'queued' | 'running' | 'success' | 'failed' | string
  progress: number
  step: string | null
  logs: string[]
  result: { metrics?: Record<string, number> } | null
  error: string | null
  created_at: string | null
  started_at: string | null
  finished_at: string | null
}

export const fetchModels = () => rawGet<{ success: boolean; models: ModelDef[]; total_count: number }>('/ml-factor/models/list')

export const fetchModelDetail = async (modelId: string): Promise<ModelDetail> => {
  try {
    return await rawGet<ModelDetail>(`/ml-factor/models/${encodeURIComponent(modelId)}`)
  } catch (e) {
    throw new Error(extractApiError(e, '模型详情加载失败'))
  }
}

export const createModel = async (body: {
  model_id: string
  model_name: string
  model_type: string
  target_type: string
  factor_list: string[]
}) => {
  try {
    return await rawPost<{ success: boolean; message?: string; error?: string }>('/ml-factor/models/create', body)
  } catch (e) {
    throw new Error(extractApiError(e, '创建模型失败'))
  }
}

export const deleteModel = async (modelId: string) => {
  try {
    return await rawDelete<{ success: boolean; deleted_prediction_count?: number }>(`/ml-factor/models/${encodeURIComponent(modelId)}`)
  } catch (e) {
    throw new Error(extractApiError(e, '删除模型失败'))
  }
}

export const fetchTrainingDateRange = async (modelId: string) => {
  try {
    const r = await rawGet<{ success: boolean; date_range: { start_date: string; end_date: string; target_period?: number; adjusted?: boolean; message?: string } }>(
      `/ml-factor/models/${encodeURIComponent(modelId)}/training-date-range`,
    )
    return r.date_range
  } catch {
    return null
  }
}

export const startTraining = async (body: { model_id: string; start_date: string; end_date: string }) => {
  try {
    return await rawPost<{ success: boolean; job_id: string; status: string; date_range_adjusted?: boolean; start_date: string; end_date: string; message?: string }>(
      '/ml-factor/models/train',
      body,
    )
  } catch (e) {
    throw new Error(extractApiError(e, '训练任务提交失败'))
  }
}

export const fetchTrainJob = (jobId: string) => rawGet<{ success: boolean; job: TrainJob }>(`/ml-factor/models/train-jobs/${encodeURIComponent(jobId)}`)

export const predictModel = async (body: { model_id: string; trade_date: string; ts_codes?: string[] | null }) => {
  try {
    return await rawPost<{ success: boolean; message?: string; predictions: ModelPrediction[] }>('/ml-factor/models/predict', body, 600_000)
  } catch (e) {
    throw new Error(extractApiError(e, '预测失败'))
  }
}

// ================= 评分 =================
export interface ScoreTopStock {
  ts_code: string
  symbol?: string
  name?: string
  industry?: string
  area?: string
  composite_score?: number
  ensemble_score?: number
  predicted_return?: number
  model_count?: number
  rank: number
  percentile_rank: number
}

export const fetchScoringLatestTradeDate = () =>
  rawGet<{ success: boolean; latest_trade_date: string }>('/ml-factor/scoring/latest-trade-date')

export const scoreFactorBased = async (body: {
  trade_date: string
  factor_list: string[]
  weights: Record<string, number>
  method: string
  top_n: number
}) => {
  try {
    return await rawPost<{ success: boolean; top_stocks: ScoreTopStock[]; total_stocks?: number; selected_stocks?: number }>(
      '/ml-factor/scoring/factor-based',
      body,
      300_000,
    )
  } catch (e) {
    throw new Error(extractApiError(e, '因子评分失败'))
  }
}

export const scoreMlBased = async (body: { trade_date: string; model_ids: string[]; top_n: number; ensemble_method: string }) => {
  try {
    return await rawPost<{ success: boolean; top_stocks: ScoreTopStock[] }>('/ml-factor/scoring/ml-based', body, 300_000)
  } catch (e) {
    throw new Error(extractApiError(e, '模型评分失败'))
  }
}

// ================= 投资组合 =================
export interface PortfolioPosition {
  id: number
  ts_code: string
  position_size: number
  avg_cost: number
  current_price: number | null
  market_value: number | null
  unrealized_pnl: number | null
  weight: number | null
  sector: string | null
  stop_loss_price: number | null
  take_profit_price: number | null
  is_active: boolean
}

export interface PortfolioSummary {
  portfolio_id: string
  name: string
  metrics: {
    total_positions: number
    total_market_value: number
    total_unrealized_pnl: number
    total_pnl_percentage: number
    max_position_weight: number
    risk_score?: number
    sector_distribution?: Record<string, number>
  }
  positions: PortfolioPosition[]
}

export interface PortfolioListItem {
  portfolio_id: string
  name: string
  position_count: number
  current_value: number
  unrealized_pnl: number
  return_rate: number
  max_position_weight: number
  created_at: string
}

export interface IntegratedSelectionResult {
  trade_date: string
  stock_selection?: { total_candidates?: number }
  portfolio_optimization: {
    method: string
    weights: Record<string, number>
    portfolio_stats: {
      expected_return: number
      volatility: number
      sharpe_ratio: number
      max_weight: number
    }
  }
  final_portfolio?: { weights: Record<string, number> }
}

export const fetchPortfolios = () => rawGet<{ success: boolean; portfolios: PortfolioListItem[] }>('/ml-factor/portfolio/list')

export const fetchPortfolioDetail = async (pid: string): Promise<PortfolioSummary> => {
  try {
    return await rawGet<{ success: boolean; portfolio: PortfolioSummary }>(`/ml-factor/portfolio/${encodeURIComponent(pid)}`).then((r) => r.portfolio)
  } catch (e) {
    throw new Error(extractApiError(e, '组合详情加载失败'))
  }
}

export const createPortfolioPosition = async (body: {
  portfolio_id: string
  ts_code: string
  position_size: number
  avg_cost: number
  sector?: string
}) => {
  try {
    return await rawPost<{ success: boolean; message?: string }>('/ml-factor/portfolio', body)
  } catch (e) {
    throw new Error(extractApiError(e, '创建组合失败'))
  }
}

export const deletePortfolio = async (pid: string) => {
  try {
    return await rawDelete<{ success: boolean }>(`/ml-factor/portfolio/${encodeURIComponent(pid)}`)
  } catch (e) {
    throw new Error(extractApiError(e, '删除组合失败'))
  }
}

export const updatePosition = async (pid: string, positionId: number, body: Partial<PortfolioPosition>) => {
  try {
    return await rawPut<{ success: boolean }>(`/ml-factor/portfolio/${encodeURIComponent(pid)}/positions/${positionId}`, body)
  } catch (e) {
    throw new Error(extractApiError(e, '更新持仓失败'))
  }
}

export const deletePosition = async (pid: string, positionId: number) => {
  try {
    return await rawDelete<{ success: boolean }>(`/ml-factor/portfolio/${encodeURIComponent(pid)}/positions/${positionId}`)
  } catch (e) {
    throw new Error(extractApiError(e, '删除持仓失败'))
  }
}

export const runIntegratedSelection = async (body: {
  trade_date: string
  selection_method: string
  factor_list: string[]
  weights: Record<string, number>
  top_n: number
  optimization_method: string
  constraints: Record<string, number>
}) => {
  try {
    return await rawPost<IntegratedSelectionResult>('/ml-factor/portfolio/integrated-selection', body, 600_000)
  } catch (e) {
    throw new Error(extractApiError(e, '组合优化失败'))
  }
}

export const saveOptimizedPortfolio = async (body: { portfolio_id: string; total_capital: number; weights: Record<string, number> }) => {
  try {
    return await rawPost<{ success: boolean; created_count?: number }>('/ml-factor/portfolio/save-optimized', body, 300_000)
  } catch (e) {
    throw new Error(extractApiError(e, '保存组合失败'))
  }
}

export const rebalancePreview = async (body: { current_weights: Record<string, number>; target_weights: Record<string, number>; transaction_cost: number }) => {
  try {
    return await rawPost<{ trade_instructions: Record<string, number>; turnover: number; transaction_cost: number }>(
      '/ml-factor/portfolio/rebalance',
      body,
      120_000,
    )
  } catch (e) {
    throw new Error(extractApiError(e, '再平衡预览失败'))
  }
}

export const rebalanceApply = async (body: { portfolio_id: string; target_weights: Record<string, number>; rebalance_note?: string }) => {
  try {
    return await rawPost<{ success: boolean; updated_count?: number; created_count?: number; deactivated_count?: number }>(
      '/ml-factor/portfolio/rebalance/apply',
      body,
      300_000,
    )
  } catch (e) {
    throw new Error(extractApiError(e, '执行再平衡失败'))
  }
}

export const refreshPortfolioPrices = async (pid: string) => {
  try {
    return await rawPost<{ success: boolean; data?: { updated: number; total: number } }>(`/ml-factor/portfolio/${encodeURIComponent(pid)}/refresh-prices`, {})
  } catch {
    return null
  }
}

// ================= 分析报告 =================
export interface ModelPerfPoint {
  date: string
  train_r2: number | null
  test_r2: number | null
  mae: number | null
}

export interface MlAnalysisData {
  modelPerformance: {
    total_models: number
    best_r2: number | null
    performance_data: ModelPerfPoint[]
    comparison_data: { model_type: string; r2_score: number | null; mae_score: number | null }[]
  } | null
  factorEffectiveness: {
    active_factors: number
    importance_data: { factor_name: string; importance: number; correlation: number | null }[]
  } | null
  portfolioPerformance: {
    portfolio_count: number
    annual_return: number | null
    max_drawdown: number | null
    sharpe_ratio: number | null
    win_rate: number | null
    performance_data: { date: string; portfolio_return: number | null }[]
    sector_distribution: Record<string, number> | null
  } | null
  riskAnalysis: { risk_data: { name: string; value: number }[] } | null
}

const safeRawGet = async <T>(url: string): Promise<T | null> => {
  try {
    return await rawGet<T>(url, undefined, 300_000)
  } catch {
    return null
  }
}

export const fetchMlAnalysisData = async (): Promise<MlAnalysisData> => {
  const [modelPerformance, factorEffectiveness, portfolioPerformance, riskAnalysis] = await Promise.all([
    safeRawGet<{
      total_models: number
      best_r2: number | null
      performance_data: ModelPerfPoint[]
      comparison_data: { model_type: string; r2_score: number | null; mae_score: number | null }[]
    }>('/ml-factor/analysis/model-performance'),
    safeRawGet<{ active_factors: number; importance_data: { factor_name: string; importance: number; correlation: number | null }[] }>('/ml-factor/analysis/factor-effectiveness'),
    safeRawGet<{
      portfolio_count: number
      annual_return: number | null
      max_drawdown: number | null
      sharpe_ratio: number | null
      win_rate: number | null
      performance_data: { date: string; portfolio_return: number | null }[]
      sector_distribution: Record<string, number> | null
    }>('/ml-factor/analysis/portfolio-performance'),
    safeRawGet<{ risk_data: { name: string; value: number }[] }>('/ml-factor/analysis/risk-analysis'),
  ])
  return { modelPerformance, factorEffectiveness, portfolioPerformance, riskAnalysis }
}

export const generateMlReport = async () => {
  try {
    return await rawPost<{ success: boolean; report?: unknown }>('/ml-factor/analysis/generate-report', {}, 300_000)
  } catch (e) {
    throw new Error(extractApiError(e, '生成报告失败'))
  }
}

// ================= 组合回测 =================
export interface MlBacktestResult {
  run_id?: string
  total_return: number
  performance_metrics: {
    annual_return: number
    max_drawdown: number
    sharpe_ratio: number
    volatility: number
    win_rate: number
  }
  execution_assumptions?: { commission_rate: number; slippage_rate: number; benchmark_index: string }
  trade_constraints?: { max_position_count: number; min_trade_weight: number; suspend_policy: string; limit_up_down_policy: string }
  equity_curve: { date: string; portfolio: number; benchmark: number | null }[]
  drawdown_series: { date: string; drawdown: number }[]
  monthly_returns: { date: string; portfolio: number; benchmark: number | null }[]
  industry_distribution: { name: string; value: number }[]
  returns_distribution: { returns: number; frequency: number }[]
  positions: { code: string; name: string | null; weight: number; period: string | null; return: number | null; contribution: number | null }[]
  risk_metrics: {
    var_95: number | null
    cvar_95: number | null
    beta: number | null
    alpha: number | null
    information_ratio: number | null
    calmar_ratio: number | null
  }
}

export const runMlBacktest = async (body: {
  strategy_config: Record<string, unknown>
  start_date: string
  end_date: string
  initial_capital: number
  rebalance_frequency: string
  mode: 'sync' | 'async'
}) => {
  try {
    return await rawPost<MlBacktestResult & { queued?: boolean; run_id?: string; status_url?: string; result_url?: string }>(
      '/ml-factor/backtest/run',
      body,
      600_000,
    )
  } catch (e) {
    throw new Error(extractApiError(e, '组合回测失败'))
  }
}

export const fetchBacktestRunStatus = (runId: string) =>
  rawGet<{ ready?: boolean; status?: string; message?: string }>(`/ml-factor/backtest/runs/${encodeURIComponent(runId)}`)

export const fetchBacktestRunResult = async (runId: string): Promise<MlBacktestResult> => {
  const r = await rawGet<{ ready: boolean; result?: MlBacktestResult; status?: string; message?: string }>(
    `/ml-factor/backtest/runs/${encodeURIComponent(runId)}/result`,
  )
  if (!r.ready || !r.result) throw new Error(r.message || `回测未完成（${r.status ?? 'unknown'}）`)
  return r.result
}
