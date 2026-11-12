import { rawDelete, rawGet, rawPost } from './client'

// ================= AI 工作台 =================
export interface AiStatus {
  llm: { configured: boolean; model?: string }
  config_hint?: string
  tushare_token_configured: boolean
  wide_table: { exists: boolean; wide_table_date?: string }
}

export interface AiSession {
  id: string
  title: string
  updated_at: string
}

export interface AiMessage {
  role: 'user' | 'assistant' | 'tool'
  content: string
  tool_name?: string
  tool_args?: Record<string, unknown> | null
  tool_ok?: boolean
  tool_result?: unknown
  duration_ms?: number
}

export const fetchAiStatus = async (): Promise<AiStatus | null> => {
  try {
    const r = await rawGet<{ success: boolean; data: AiStatus }>('/ai-assistant/status')
    return r.data ?? null
  } catch {
    return null
  }
}

export const fetchAiSessions = async (): Promise<AiSession[]> => {
  const r = await rawGet<{ success: boolean; sessions: AiSession[] }>('/ai-assistant/sessions', { limit: 50 })
  return r.sessions ?? []
}

export const deleteAiSession = (id: string) => rawDelete<{ success: boolean }>(`/ai-assistant/sessions/${id}`)

// ================= 沉淀：看板 + 常用查询 =================

export interface AiBoard {
  id: string
  title: string
  content: string
  content_type: string
  meta: Record<string, unknown>
  created_at: string
}

export interface AiSavedQuery {
  id: string
  title: string
  prompt: string
  created_at: string
}

export const fetchAiSaved = async (): Promise<{ boards: AiBoard[]; queries: AiSavedQuery[] }> => {
  try {
    const r = await rawGet<{ success: boolean; boards: AiBoard[]; queries: AiSavedQuery[] }>('/ai-assistant/saved')
    return { boards: r.boards ?? [], queries: r.queries ?? [] }
  } catch {
    return { boards: [], queries: [] }
  }
}

export const saveAiBoard = (title: string, content: string) =>
  rawPost<{ success: boolean; record: AiBoard }>('/ai-assistant/saved', { kind: 'board', title, content })

export const saveAiQuery = (prompt: string, title?: string) =>
  rawPost<{ success: boolean; record: AiSavedQuery }>('/ai-assistant/saved', { kind: 'query', prompt, title })

export const deleteAiSaved = (kind: 'boards' | 'queries', id: string) =>
  rawDelete<{ success: boolean }>(`/ai-assistant/saved/${kind}/${encodeURIComponent(id)}`)

export const fetchAiMessages = async (id: string): Promise<AiMessage[]> => {
  const r = await rawGet<{ success: boolean; messages: AiMessage[] }>(`/ai-assistant/sessions/${id}/messages`, { limit: 200 })
  return r.messages ?? []
}

export interface ChatStreamHandlers {
  onSession?: (sessionId: string) => void
  onToken?: (content: string) => void
  onToolCall?: (name: string, args: Record<string, unknown>, callId: string) => void
  onToolResult?: (callId: string, ok: boolean, result: unknown, durationMs?: number, name?: string) => void
  onDone?: () => void
  onError?: (message: string) => void
}

/**
 * SSE-over-fetch：POST /chat 返回 text/event-stream，按空行分帧解析 data: JSON 事件。
 * 返回 abort 函数用于停止生成。
 */
export function streamAiChat(
  body: { session_id?: string | null; message: string; allow_actions: boolean },
  handlers: ChatStreamHandlers,
): (reason?: string) => void {
  const controller = new AbortController()
  ;(async () => {
    // done / error 只结算一次：后端发 done 事件后流还会正常关闭，
    // 两处都触发 onDone 会把助手回复重复追加到消息列表
    let settled = false
    const finishDone = () => {
      if (settled) return
      settled = true
      handlers.onDone?.()
    }
    const finishError = (message: string) => {
      if (settled) return
      settled = true
      handlers.onError?.(message)
    }
    try {
      const resp = await fetch('/api/ai-assistant/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      })
      if (!resp.ok || !resp.body) {
        const text = await resp.text().catch(() => '')
        finishError(`请求失败（HTTP ${resp.status}）${text ? `: ${text.slice(0, 200)}` : ''}`)
        return
      }
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const frames = buffer.split('\n\n')
        buffer = frames.pop() ?? ''
        for (const frame of frames) {
          for (const line of frame.split('\n')) {
            if (!line.startsWith('data:')) continue
            const payload = line.slice(5).trim()
            if (!payload) continue
            try {
              const evt = JSON.parse(payload) as {
                type: string
                session_id?: string
                content?: string
                name?: string
                arguments?: Record<string, unknown>
                call_id?: string
                ok?: boolean
                result?: unknown
                duration_ms?: number
                message?: string
              }
              if (evt.type === 'session' && evt.session_id) handlers.onSession?.(evt.session_id)
              else if (evt.type === 'token') handlers.onToken?.(evt.content ?? '')
              else if (evt.type === 'tool_call') handlers.onToolCall?.(evt.name ?? '', evt.arguments ?? {}, evt.call_id ?? '')
              else if (evt.type === 'tool_result') handlers.onToolResult?.(evt.call_id ?? '', !!evt.ok, evt.result, evt.duration_ms, evt.name)
              else if (evt.type === 'done') finishDone()
              else if (evt.type === 'error') finishError(evt.message ?? 'AI 服务错误')
            } catch {
              // 忽略无法解析的心跳/杂散帧
            }
          }
        }
      }
      finishDone()
    } catch (e) {
      if ((e as Error).name !== 'AbortError') finishError(e instanceof Error ? e.message : '连接中断')
    }
  })()
  return (reason?: string) => controller.abort(reason)
}

// ================= text2sql（裸响应 {success,...}） =================
export interface Text2SqlSuggestion {
  text: string
  category?: string
  description: string
}

export interface Text2SqlResult {
  query: string
  intent?: { name: string; confidence: number }
  entities?: Record<string, unknown>
  sql?: string
  data?: Record<string, unknown>[]
  formatted_data?: { summary?: string }
  chart_config?: {
    type: string
    x_field: string
    y_field: string
    x_label?: string
    y_label?: string
    title?: string
    data: Record<string, unknown>[]
  } | null
  explanation?: string
  execution_time?: number
  result_count?: number
  error?: string
}

export const fetchSqlSuggestions = async (): Promise<Text2SqlSuggestion[]> => {
  const r = await rawGet<{ success: boolean; suggestions: Text2SqlSuggestion[] }>('/text2sql/suggestions')
  return r.suggestions ?? []
}

export const runSqlQuery = async (query: string): Promise<Text2SqlResult> => {
  const resp = await fetch('/api/text2sql/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: query.slice(0, 500) }),
  })
  const body = (await resp.json()) as Text2SqlResult & { success?: boolean }
  return body
}

export const fetchSqlHistory = async (limit = 10) => {
  const r = await rawGet<{ success: boolean; history: Record<string, unknown>[] }>('/text2sql/history', { limit })
  return r.history ?? []
}

// ================= 已保存策略（AI save_strategy 产物） =================

export interface SavedStrategy {
  id: number
  name: string
  description: string
  version: number
  is_latest: boolean
  created_at: string
  run_count?: number
  strategy_config: {
    engine_config?: {
      selection_method?: string
      factor_list?: string[]
      weights?: Record<string, number>
      dsl?: { filter?: string; order_by?: string }
      top_n?: number
      benchmark_index?: string
    }
    params?: {
      start_date?: string
      end_date?: string
      rebalance_frequency?: string
    }
    meta?: { derived_from?: { name: string; version: number } }
  }
}

export interface StrategyRunRow {
  run_id: number
  strategy_version?: number
  start_date?: string
  end_date?: string
  status?: string
  created_at?: string
  total_return?: number
  annualized_return?: number
  sharpe_ratio?: number
  max_drawdown?: number
  win_rate?: number
  total_trades?: number
}

export interface StrategyHistory {
  name: string
  versions: SavedStrategy[]
  runs: StrategyRunRow[]
}

export interface RunCompareRow {
  run_id: number
  strategy_name?: string
  start_date?: string
  end_date?: string
  status?: string
  total_return?: number
  annualized_return?: number
  sharpe_ratio?: number
  max_drawdown?: number
  win_rate?: number
  calmar_ratio?: number
  total_trades?: number
  alpha?: number
  beta?: number
  information_ratio?: number
}

export const fetchStrategyHistory = async (name: string): Promise<StrategyHistory | null> => {
  try {
    const r = await rawGet<{ success: boolean; versions: SavedStrategy[]; runs: StrategyRunRow[] }>(
      `/ml-factor/strategies/${encodeURIComponent(name)}/versions`,
    )
    return r.success ? { name, versions: r.versions ?? [], runs: r.runs ?? [] } : null
  } catch {
    return null
  }
}

export const runStrategyByName = (
  name: string,
  overrides: Record<string, unknown>,
): Promise<{ run_id: number; status: string; strategy_version?: number }> =>
  rawPost(`/ml-factor/strategies/${encodeURIComponent(name)}/run`, { overrides })

export const forkStrategyVersion = (
  name: string,
  base_version: number,
  edits: Record<string, unknown>,
  description: string,
): Promise<{ success: boolean; strategy?: SavedStrategy }> =>
  rawPost(`/ml-factor/strategies/${encodeURIComponent(name)}/fork`, {
    base_version,
    edits,
    description,
  })

export const compareStrategyRuns = async (
  run_ids: number[],
): Promise<{ runs: RunCompareRow[]; range_warning?: string | null } | null> => {
  try {
    const r = await rawPost<{ success: boolean; runs: RunCompareRow[]; range_warning?: string }>(
      '/ml-factor/strategies/compare-runs',
      { run_ids },
    )
    return r.success ? { runs: r.runs ?? [], range_warning: r.range_warning } : null
  } catch {
    return null
  }
}

// 回测 run 状态轮询（策略调参重跑后跟踪）
export interface BacktestRunStatus {
  id: number
  status?: string
  error?: string
  start_date?: string
  end_date?: string
  metrics?: Record<string, number>
}

export const fetchBacktestRunStatus = async (runId: number): Promise<BacktestRunStatus | null> => {
  try {
    const r = await rawGet<{ success: boolean; run: Record<string, unknown> }>(
      `/ml-factor/backtest/runs/${runId}`,
    )
    if (!r.success || !r.run) return null
    const summary = (r.run.summary ?? {}) as Record<string, unknown>
    const metrics = (summary.metrics ?? {}) as Record<string, number>
    return {
      id: Number(r.run.id ?? runId),
      status: String(summary.status ?? ''),
      error: summary.error ? String(summary.error) : undefined,
      start_date: r.run.start_date ? String(r.run.start_date) : undefined,
      end_date: r.run.end_date ? String(r.run.end_date) : undefined,
      metrics: Object.keys(metrics).length ? metrics : undefined,
    }
  } catch {
    return null
  }
}

export const fetchBacktestRunMetrics = async (
  runId: number,
): Promise<Record<string, number> | null> => {
  try {
    const r = await rawGet<{ success: boolean; result?: { performance_metrics?: Record<string, number> } }>(
      `/ml-factor/backtest/runs/${runId}/result`,
    )
    return r.result?.performance_metrics ?? null
  } catch {
    return null
  }
}

export interface EquityPoint {
  date: string
  portfolio?: number
  benchmark?: number
  excess?: number
}

export const fetchRunEquityCurve = async (runId: number): Promise<EquityPoint[]> => {
  try {
    const r = await rawGet<{ success: boolean; result?: { equity_curve?: EquityPoint[] } }>(
      `/ml-factor/backtest/runs/${runId}/result`,
    )
    return r.result?.equity_curve ?? []
  } catch {
    return []
  }
}

export const fetchSavedStrategies = async (): Promise<SavedStrategy[]> => {
  try {
    const r = await rawGet<{ success: boolean; strategies: SavedStrategy[] }>('/ml-factor/strategies')
    return r.strategies ?? []
  } catch {
    return []
  }
}

export const deleteSavedStrategy = (name: string) =>
  rawDelete<{ success: boolean; removed_versions: number }>(`/ml-factor/strategies/${encodeURIComponent(name)}`)
