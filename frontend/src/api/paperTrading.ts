import { apiGet, apiPost } from './client'

// ================= Paper trading 模拟盘 /api/paper-trading（纯虚拟记账，无券商接口） =================

export interface PaperPosition {
  ts_code: string
  qty: number
  avg_cost: number
  last_close: number
  market_value: number
  pnl: number
  pnl_pct: number | null
  since?: string
}

export interface PaperOrder {
  order_id: string
  signal_date: string
  ts_code: string
  side: 'buy' | 'sell' | string
  signal_close: number | null
  target_value: number
  reason?: string
  status?: string
  attempts?: number
  skip_reason?: string
}

export interface PaperTrade {
  trade_id: number
  date: string
  ts_code: string
  side: 'buy' | 'sell' | string
  qty: number
  price: number
  value: number
  costs: { commission: number; slippage: number; stamp_duty: number; total_cost: number }
  signal_close: number | null
  price_gap: number | null
  reason?: string
}

export interface PaperNavPoint {
  date: string
  cash: number
  market_value: number
  nav: number
  positions: number
  paper_ret: number
  basket_ret: number | null
}

export interface PaperStatus {
  account_id: string
  created_at: string
  initial_cash: number
  top_n: number
  cash: number
  nav: number
  total_pnl: number
  total_pnl_pct: number
  positions: PaperPosition[]
  pending_orders: PaperOrder[]
  closed_orders: PaperOrder[]
  stats: { filled: number; skipped: number; expired: number }
  last_signal_date?: string | null
}

export interface PaperAlignment {
  n_days: number
  paper_cum_ret: number | null
  basket_cum_ret: number | null
  tracking_error_daily: number | null
  nav_corr: number | null
  attribution: {
    avg_buy_fill_gap: number | null
    avg_sell_fill_gap: number | null
    cost_drag_pct: number
    n_trades: number
    n_filled: number
    n_expired: number
  }
  note: string
}

export function fetchPaperStatus() {
  return apiGet<PaperStatus>('/paper-trading/status')
}

export function fetchPaperHistory(limit = 200) {
  return apiGet<{ nav_history: PaperNavPoint[]; trades: PaperTrade[] }>('/paper-trading/history', { limit })
}

export function fetchPaperAlignment() {
  return apiGet<PaperAlignment>('/paper-trading/alignment')
}

/** 手动触发一轮：结算 → 盯市 → 生成挂单 */
export function runPaperDaily() {
  return apiPost<Record<string, unknown>>('/paper-trading/run')
}

export function resetPaperAccount(initialCash: number, topN: number) {
  return apiPost<{ ok: boolean }>('/paper-trading/reset', { initial_cash: initialCash, top_n: topN })
}
