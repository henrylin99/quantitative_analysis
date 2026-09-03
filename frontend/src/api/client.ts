import axios from 'axios'

/** 后端统一响应信封：{code, message, data}，code===200 为业务成功 */
export interface Envelope<T> {
  code: number
  message: string
  data: T | null
}

export class ApiError extends Error {
  constructor(
    public code: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/**
 * 后端个别列（如 delist_date）会输出裸 NaN/Infinity——不是合法 JSON，
 * JSON.parse 直接抛错。响应进入解析前把这类裸 token 清洗为 null。
 * （旧版前端同样受此影响；为不改后端契约，在新前端侧兜底。）
 */
function sanitizeBareNan(text: string): string {
  return text.replace(/(:\s*|,\s*|\[\s*)\b(NaN|-?Infinity)\b/g, '$1null')
}

const http = axios.create({
  baseURL: '/api',
  timeout: 60_000,
  headers: { 'Content-Type': 'application/json' },
  transformResponse: [
    (data) => {
      if (typeof data !== 'string') return data
      try {
        return JSON.parse(sanitizeBareNan(data))
      } catch {
        return data
      }
    },
  ],
})

async function unwrap<T>(promise: Promise<{ data: Envelope<T> }>): Promise<T> {
  const resp = await promise
  const env = resp.data
  if (env.code !== 200) {
    throw new ApiError(env.code, env.message || `请求失败（code=${env.code}）`)
  }
  return env.data as T
}

export function apiGet<T>(url: string, params?: Record<string, unknown>, timeoutMs?: number): Promise<T> {
  return unwrap<T>(http.get<Envelope<T>>(url, { params, timeout: timeoutMs }))
}

export function apiPost<T>(url: string, body?: unknown, timeoutMs?: number): Promise<T> {
  return unwrap<T>(http.post<Envelope<T>>(url, body ?? {}, { timeout: timeoutMs }))
}

export function apiPut<T>(url: string, body?: unknown, timeoutMs?: number): Promise<T> {
  return unwrap<T>(http.put<Envelope<T>>(url, body ?? {}, { timeout: timeoutMs }))
}

export function apiDelete<T>(url: string, timeoutMs?: number): Promise<T> {
  return unwrap<T>(http.delete<Envelope<T>>(url, { timeout: timeoutMs }))
}

/** 非 200 业务码也把响应体交还给调用方（部分接口用 code 表达业务状态而非抛错） */
export async function apiGetEnvelope<T>(url: string, params?: Record<string, unknown>): Promise<Envelope<T>> {
  const resp = await http.get<Envelope<T>>(url, { params })
  return resp.data
}

export async function apiPostEnvelope<T>(url: string, body?: unknown, timeoutMs?: number): Promise<Envelope<T>> {
  const resp = await http.post<Envelope<T>>(url, body ?? {}, { timeout: timeoutMs })
  return resp.data
}

// —— 裸响应接口（ml-factor / data-jobs / realtime-analysis 等返回 {success,...} 而非信封） ——
export async function rawGet<T>(url: string, params?: Record<string, unknown>, timeoutMs?: number): Promise<T> {
  const resp = await http.get<T>(url, { params, timeout: timeoutMs })
  return resp.data
}

export async function rawPost<T>(url: string, body?: unknown, timeoutMs?: number): Promise<T> {
  const resp = await http.post<T>(url, body ?? {}, { timeout: timeoutMs })
  return resp.data
}

export async function rawPut<T>(url: string, body?: unknown, timeoutMs?: number): Promise<T> {
  const resp = await http.put<T>(url, body ?? {}, { timeout: timeoutMs })
  return resp.data
}

export async function rawDelete<T>(url: string, timeoutMs?: number): Promise<T> {
  const resp = await http.delete<T>(url, { timeout: timeoutMs })
  return resp.data
}

/** 从 axios/raw 错误中提取后端 message/error 字段 */
export function extractApiError(e: unknown, fallback = '请求失败'): string {
  if (axios.isAxiosError(e)) {
    const data = e.response?.data as { message?: string; error?: string } | string | undefined
    if (typeof data === 'string') return data || fallback
    return data?.error || data?.message || e.message || fallback
  }
  return e instanceof Error ? e.message : fallback
}

/** 原始 axios 实例：blob 下载等特殊场景 */
export { http }
