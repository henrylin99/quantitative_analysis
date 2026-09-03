/** 股票基本信息（stock_basic） */
export interface StockBasic {
  ts_code: string
  symbol: string
  name: string
  industry: string | null
  area: string | null
  list_date: string | null
}

export interface StockListData {
  stocks: StockBasic[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

/** 日线行情（GET /api/stocks/{code}/history，按 trade_date 倒序，vol 单位手、amount 单位千元） */
export interface DailyBar {
  ts_code: string
  trade_date: string
  open: number | null
  high: number | null
  low: number | null
  close: number | null
  pre_close: number | null
  change: number | null
  pct_chg: number | null
  vol: number | null
  amount: number | null
}

/** 技术因子（GET /api/stocks/{code}/factors，按 trade_date 倒序；注意涨跌幅字段名为 pct_change） */
export interface FactorRow {
  ts_code: string
  trade_date: string
  close: number | null
  open: number | null
  high: number | null
  low: number | null
  pre_close: number | null
  change: number | null
  pct_change: number | null
  vol: number | null
  amount: number | null
  adj_factor: number | null
  macd_dif: number | null
  macd_dea: number | null
  macd: number | null
  kdj_k: number | null
  kdj_d: number | null
  kdj_j: number | null
  rsi_6: number | null
  rsi_12: number | null
  rsi_24: number | null
  boll_upper: number | null
  boll_mid: number | null
  boll_lower: number | null
  cci: number | null
}

/** 选股请求条件：数字以字符串提交，空值不发送 */
export interface ScreenCriteria {
  industry?: string
  area?: string
  market?: 'SZ' | 'SH'
  trade_date?: string
  pe_min?: string
  pe_max?: string
  pb_min?: string
  pb_max?: string
  ps_min?: string
  ps_max?: string
  dv_min?: string
  dv_max?: string
  mv_min?: string
  mv_max?: string
  circ_mv_min?: string
  circ_mv_max?: string
  turnover_min?: string
  turnover_max?: string
  volume_ratio_min?: string
  volume_ratio_max?: string
  rsi6_min?: string
  rsi6_max?: string
  kdj_k_min?: string
  kdj_k_max?: string
  macd_min?: string
  macd_max?: string
  cci_min?: string
  cci_max?: string
  net_amount_min?: string
  net_amount_max?: string
  dynamic_conditions?: DynamicCondition[]
}

export interface DynamicCondition {
  field_a: string
  operator: '>' | '>=' | '<' | '<=' | '=' | '!='
  field_b: string | null
  value: string | null
}

/** 选股结果行 = stock_basic 合并列 + 宽表当日全列（NaN 已转 null） */
export type ScreenRow = StockBasic & Record<string, number | string | null>

export interface ScreenResultData {
  stocks: ScreenRow[]
  total: number
  criteria: ScreenCriteria
  has_more: boolean
  error?: string
}

/** 回测表现：比例类字段为小数（0.05 = 5%） */
export interface BacktestPerformance {
  total_return: number
  annual_return: number
  sharpe_ratio: number
  max_drawdown: number
  volatility: number
  win_rate: number
  total_trades: number
  winning_trades: number
  avg_holding_days: number
  final_capital: number
  total_commission: number
  total_cost: number
  liquidation_cost: number
  benchmark_return: number
}

export interface BacktestTrade {
  date: string
  action: 'buy' | 'sell'
  price: number
  quantity: number
  amount: number
  commission: number
  slippage: number
  stamp_duty?: number
  return_rate: number | null
}

/** 每日资产快照（回测资金曲线数据） */
export interface DailyValue {
  date: string
  cash: number
  position_value: number
  total_value: number
}

export interface BacktestConfig {
  ts_code: string
  strategy_type: string
  start_date: string
  end_date: string
  initial_capital: number
  commission_rate?: number
  params?: Record<string, number>
}

export interface BacktestResultData {
  performance: BacktestPerformance
  trades: BacktestTrade[]
  config: BacktestConfig
  daily_values?: DailyValue[]
}

export type StrategyType = 'ma_cross' | 'macd' | 'kdj' | 'rsi' | 'bollinger'
