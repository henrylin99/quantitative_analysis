import { rawDelete, rawGet } from './client'

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
    try {
      const resp = await fetch('/api/ai-assistant/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      })
      if (!resp.ok || !resp.body) {
        const text = await resp.text().catch(() => '')
        handlers.onError?.(`请求失败（HTTP ${resp.status}）${text ? `: ${text.slice(0, 200)}` : ''}`)
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
              else if (evt.type === 'done') handlers.onDone?.()
              else if (evt.type === 'error') handlers.onError?.(evt.message ?? 'AI 服务错误')
            } catch {
              // 忽略无法解析的心跳/杂散帧
            }
          }
        }
      }
      handlers.onDone?.()
    } catch (e) {
      if ((e as Error).name !== 'AbortError') handlers.onError?.(e instanceof Error ? e.message : '连接中断')
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
