import { extractApiError, rawGet, rawPost, rawPut } from './client'

// ================= 实时技术指标 =================
export interface SupportedIndicator {
  code: string
  name: string
  description: string
}

export const fetchSupportedIndicators = async (): Promise<SupportedIndicator[]> => {
  const r = await rawGet<{ success: boolean; data: SupportedIndicator[]; total: number }>('/realtime-analysis/indicators/supported')
  return r.data ?? []
}

export const calculateIndicators = async (body: { ts_code: string; period_type: string; indicators: string[]; lookback_days: number }) => {
  try {
    return await rawPost<{
      success: boolean
      total_indicators: number
      data_points: number
      stored_records: number
      latest_values: Record<string, number | number[]>
      indicator_summary: Record<string, { stored_records: number }>
      timeline?: string[]
    }>('/realtime-analysis/indicators/calculate', body, 300_000)
  } catch (e) {
    throw new Error(extractApiError(e, '指标计算失败'))
  }
}

export const calculateMultiPeriod = async (body: { ts_code: string; periods: string[]; indicators: string[] }) => {
  try {
    return await rawPost<{
      success: boolean
      summary: { period_count: number; available_periods: string[] }
      data: Record<string, { success: boolean; total_indicators: number; latest_values?: Record<string, unknown>; message?: string }>
    }>('/realtime-analysis/indicators/multi-period', body, 300_000)
  } catch (e) {
    throw new Error(extractApiError(e, '多周期分析失败'))
  }
}

export const compareIndicators = async (body: { stock_codes: string[]; period_type: string; indicator_name: string; limit: number }) => {
  try {
    return await rawPost<{
      success: boolean
      data: Record<string, { datetime: string; value1?: number; value2?: number; value3?: number; value4?: number }[]>
      indicator_name: string
      period_type: string
      stock_codes: string[]
      empty_state?: { has_data: boolean; message: string }
    }>('/realtime-analysis/indicators/compare', body, 300_000)
  } catch (e) {
    throw new Error(extractApiError(e, '指标对比失败'))
  }
}

export interface IndicatorStats {
  total_records: number
  total_stocks: number
  indicator_stats: Record<string, number>
  period_stats: Record<string, number>
  earliest_time: string | null
  latest_time: string | null
}

export const fetchIndicatorStats = async (): Promise<IndicatorStats | null> => {
  try {
    const r = await rawGet<{ success: boolean; data: IndicatorStats }>('/realtime-analysis/indicators/stats')
    return r.data ?? null
  } catch {
    return null
  }
}

// ================= 实时监控 =================
export interface MonitorQuote {
  name: string
  ts_code: string
  current_price: number
  change_pct: number
  volume: number
  volume_ratio: number | null
  turnover_rate: number | null
}

export interface MonitorSector {
  sector_name: string
  avg_change_pct: number
  rising_ratio: number
  stock_count: number
  total_volume: number
}

export interface MonitorAnomaly {
  name: string
  ts_code: string
  current_price: number
  change_pct: number
  anomaly_types: string[]
  anomaly_score: number
}

export interface MonitorSentiment {
  sentiment_score: number
  market_status: string
  status_color?: string
  rising_stocks: number
  falling_stocks: number
  rising_ratio: number
  avg_change_pct: number
  volatility: number
  total_volume: number
}

const unwrapData = async <T>(p: Promise<{ success: boolean; data?: T; message?: string }>): Promise<T | null> => {
  try {
    const r = await p
    return r.success ? (r.data ?? null) : null
  } catch {
    return null
  }
}

export const fetchMonitorOverview = () =>
  unwrapData<{ total_stocks: number; active_stocks: number; today_records: number; data_delay: string | number; latest_update?: string }>(
    rawGet('/realtime-analysis/monitor/overview'),
  )

export const fetchMonitorQuotes = (periodType: string, limit = 20) =>
  unwrapData<{ quotes: MonitorQuote[] }>(rawGet('/realtime-analysis/monitor/quotes', { period_type: periodType, limit }))

export const fetchMonitorSectors = (periodHours: number) =>
  unwrapData<{ sectors: MonitorSector[] }>(rawGet('/realtime-analysis/monitor/sectors', { period_hours: periodHours }))

export const fetchMonitorAnomalies = (changeThreshold: number, volumeThreshold: number) =>
  unwrapData<{ anomalies: MonitorAnomaly[] }>(
    rawGet('/realtime-analysis/monitor/anomalies', { change_threshold: changeThreshold, volume_threshold: volumeThreshold }),
  )

export const fetchMonitorSentiment = (periodHours: number) =>
  unwrapData<MonitorSentiment>(rawGet('/realtime-analysis/monitor/sentiment', { period_hours: periodHours }))

export const fetchMonitorTopMovers = (limit = 10) =>
  unwrapData<{ top_gainers: MonitorQuote[]; top_losers: MonitorQuote[]; most_active: MonitorQuote[] }>(
    rawGet('/realtime-analysis/monitor/top-movers', { limit }),
  )

// ================= 交易信号 =================
export interface SignalStrategy {
  name: string
  display_name: string
  description: string
}

export const fetchSignalStrategies = async (): Promise<SignalStrategy[]> => {
  const r = await rawGet<{ success: boolean; data: SignalStrategy[] }>('/realtime-analysis/signals/strategies')
  return r.data ?? []
}

export const fetchSignalStats = () =>
  unwrapData<{ total_signals: number; total_stocks: number; status_stats: Record<string, number> }>(rawGet('/realtime-analysis/signals/stats'))

export const generateSignals = async (body: { ts_code: string; period_type: string; strategies: string[]; lookback_days: number }) => {
  try {
    return await rawPost<{
      success: boolean
      data: { signals_generated: number; signals: { strategy_name: string; signal_type: string; signal_strength: number; confidence: number; trigger_price: number }[] }
    }>('/realtime-analysis/signals/generate', body, 300_000)
  } catch (e) {
    throw new Error(extractApiError(e, '信号生成失败'))
  }
}

export const fuseSignals = async (body: { ts_code: string; period_type: string; time_window_hours: number }) => {
  try {
    return await rawPost<{
      success: boolean
      data: { fused_signal: string; signal_strength: number; confidence: number; buy_signals: number; sell_signals: number; contributing_signals?: unknown }
    }>('/realtime-analysis/signals/fuse', body, 300_000)
  } catch (e) {
    throw new Error(extractApiError(e, '信号融合失败'))
  }
}

export interface ActiveSignal {
  ts_code: string
  strategy_name: string
  signal_type: string
  signal_strength: number
  confidence: number
  trigger_price: number
  datetime: string
  status: string
}

export const fetchActiveSignals = async (limit = 50, tsCode?: string, strategyName?: string): Promise<ActiveSignal[]> => {
  try {
    const r = await rawGet<{ success: boolean; data: ActiveSignal[] }>('/realtime-analysis/signals/active', {
      limit,
      ts_code: tsCode || undefined,
      strategy_name: strategyName || undefined,
    })
    return r.data ?? []
  } catch {
    return []
  }
}

export const backtestSignalStrategy = async (body: {
  strategy_name: string
  ts_code: string
  start_date: string
  end_date: string
  period_type: string
}) => {
  try {
    return await rawPost<{
      success: boolean
      data: { strategy_name: string; ts_code: string; period: string; data_points: number; total_return: number; max_drawdown: number; volatility: number; sharpe_ratio: number }
    }>('/realtime-analysis/signals/backtest', body, 300_000)
  } catch (e) {
    throw new Error(extractApiError(e, '信号回测失败'))
  }
}

// ================= 风险管理 =================
export interface RiskPositionMonitor {
  risk_summary: { high_risk_positions: number; medium_risk_positions: number; risk_score: number; overall_risk_level: string }
  portfolio_metrics: { portfolio_var_1d: number | null; portfolio_var_5d: number | null }
  correlation_metrics: { correlation_matrix: Record<string, Record<string, number>> }
}

export const fetchRiskPositionMonitor = (portfolioId: string) =>
  unwrapData<RiskPositionMonitor>(rawGet('/realtime-analysis/risk/position-monitor', { portfolio_id: portfolioId }))

export interface RiskAlert {
  id: number
  ts_code: string
  alert_type: string
  alert_level: string
  alert_message: string
  created_at: string
}

export const fetchRiskAlerts = (portfolioId: string) =>
  unwrapData<{ active_alerts: RiskAlert[] }>(rawGet('/realtime-analysis/risk/alerts', { portfolio_id: portfolioId }))

export const resolveRiskAlert = (alertId: number) => rawPut<{ success: boolean }>(`/realtime-analysis/risk/alerts/${alertId}/resolve`)

export const stopLossTakeProfit = async (body: {
  portfolio_id: string
  stop_loss_method: string
  stop_loss_value: number
  take_profit_method: string
  take_profit_value: number
}) => {
  try {
    return await rawPost<{ success: boolean; data?: { triggered_orders: { ts_code: string; order_type: string; trigger_price: number; position_size: number; unrealized_pnl: number }[] } }>(
      '/realtime-analysis/risk/stop-loss-take-profit',
      body,
      120_000,
    )
  } catch (e) {
    throw new Error(extractApiError(e, '止损止盈检查失败'))
  }
}

export const stressTest = async (portfolioId: string) => {
  try {
    return await rawPost<{
      success: boolean
      data: { scenarios: { scenario_name: string; original_value: number; stressed_value: number; pnl_percentage: number }[]; worst_case: string; best_case: string }
    }>('/realtime-analysis/risk/stress-test', { portfolio_id: portfolioId }, 300_000)
  } catch (e) {
    throw new Error(extractApiError(e, '压力测试失败'))
  }
}

// ================= 报告管理 =================
export interface ReportSection {
  type: string
  title?: string
  content: unknown
}

export interface ReportItem {
  id: number
  report_name: string
  report_type: string
  report_status: string
  generated_at: string | null
  report_content: { sections?: ReportSection[] } | null
}

export const fetchReports = async (): Promise<ReportItem[]> => {
  const r = await rawGet<{ success: boolean; data: ReportItem[] }>('/realtime-analysis/reports/reports')
  return r.data ?? []
}

export const fetchReportTemplates = async () => {
  const r = await rawGet<{ success: boolean; data: { id: number; template_name: string; template_type: string; description: string }[] }>(
    '/realtime-analysis/reports/templates',
  )
  return r.data ?? []
}

export interface ReportSubscription {
  id?: number
  subscription_name: string
  template_name?: string
  subscriber_email: string
  next_send_at?: string | null
}

export const fetchReportSubscriptions = async (): Promise<ReportSubscription[]> => {
  const r = await rawGet<{ success: boolean; data: ReportSubscription[] }>('/realtime-analysis/reports/subscriptions')
  return r.data ?? []
}

export interface ReportStatistics {
  reports: { total: number; completed: number; failed: number; success_rate: number }
  templates: { total: number; active: number }
  subscriptions: { total: number; active: number }
  report_type_stats: Record<string, number>
}

export const fetchReportStatistics = async (): Promise<ReportStatistics | null> => {
  try {
    const r = await rawGet<{ success: boolean; data: ReportStatistics }>('/realtime-analysis/reports/statistics')
    return r.data ?? null
  } catch {
    return null
  }
}

export const generateReport = async (body: { report_type: string; template_id?: number | null; report_name: string; parameters?: Record<string, unknown>; generated_by?: string }) => {
  try {
    return await rawPost<{ success: boolean; message?: string }>('/realtime-analysis/reports/generate-report', body, 300_000)
  } catch (e) {
    throw new Error(extractApiError(e, '生成报告失败'))
  }
}

export const createReportTemplate = async (body: { template_name: string; template_type: string; description: string; created_by?: string }) => {
  try {
    return await rawPost<{ success: boolean }>('/realtime-analysis/reports/templates', body)
  } catch (e) {
    throw new Error(extractApiError(e, '创建模板失败'))
  }
}

export const createReportSubscription = async (body: {
  subscription_name: string
  template_id: number
  subscriber_email: string
  schedule_type: string
  schedule_config?: Record<string, unknown>
  notification_channels: string[]
  created_by?: string
}) => {
  try {
    return await rawPost<{ success: boolean }>('/realtime-analysis/reports/subscriptions', body)
  } catch (e) {
    throw new Error(extractApiError(e, '创建订阅失败'))
  }
}

export const dispatchSubscriptions = async () => {
  try {
    return await rawPost<{ success: boolean; dispatched?: number; message?: string }>('/realtime-analysis/reports/subscriptions/dispatch', {})
  } catch (e) {
    throw new Error(extractApiError(e, '分发失败'))
  }
}

// ================= SocketIO 推送管理 =================
export interface PushConfig {
  [type: string]: { enabled: boolean; interval: number }
}

export const fetchPushConfig = () => rawGet<{ success: boolean; data: PushConfig }>('/websocket/push-config')

export const updatePushConfig = (config: PushConfig) => rawPut<{ success: boolean }>('/websocket/push-config', config)

export const startPush = () => rawPost<{ success: boolean; message?: string }>('/websocket/start', {})

export const stopPush = () => rawPost<{ success: boolean; message?: string }>('/websocket/stop', {})

export const fetchWsConnections = () =>
  rawGet<{ success: boolean; data: { total_clients: number; total_rooms: number; room_details?: unknown; client_details?: unknown } }>('/websocket/connections')

export const fetchWsStatus = () =>
  rawGet<{ success: boolean; data: { is_running: boolean; push_interval?: number; push_config?: PushConfig; last_push_times?: Record<string, string>; connection_stats?: unknown } }>(
    '/websocket/status',
  )

export const testWsConnection = () => rawPost<{ success: boolean; data?: unknown; message?: string }>('/websocket/test-connection', {})
