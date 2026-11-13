import { apiGet, apiPost } from './client'

/** 系统配置状态（后端脱敏，只回显尾 4 位） */
export interface SystemSettings {
  tushare: { configured: boolean; token_masked: string | null }
  fuyao: {
    configured: boolean
    api_key_masked: string | null
    ok?: boolean | null
    error?: string | null
  }
  llm: {
    configured: boolean
    base_url: string | null
    model: string | null
    api_key_masked: string | null
    provider: LlmProvider | null
  }
  all_configured: boolean
}

/** openai 兼容 / ollama 本地 / anthropic Claude */
export type LlmProvider = 'openai' | 'ollama' | 'anthropic'

/** 可写入的配置键（与后端 WRITABLE_ENV_KEYS 白名单一致） */
export type SettingsPayload = Partial<{
  TUSHARE_TOKEN: string
  FUYAO_API_KEY: string
  LLM_API_KEY: string
  LLM_BASE_URL: string
  LLM_MODEL: string
  LLM_PROVIDER: LlmProvider | ''
}>

export interface LlmTestResult {
  ok: boolean
  provider?: string
  model?: string
  latency_ms?: number
  reply?: string
  error?: string
}

export function fetchSystemSettings(probe = false): Promise<SystemSettings> {
  return apiGet<SystemSettings>('/settings', probe ? { probe: 1 } : undefined)
}

export function updateSystemSettings(payload: SettingsPayload): Promise<{ updated: string[] }> {
  return apiPost<{ updated: string[] }>('/settings', payload)
}

/** 真实调用一次大模型验证可用性；参数为空时测当前已保存配置 */
export function testLlmConfig(payload: {
  provider?: string
  base_url?: string
  model?: string
  api_key?: string
}): Promise<LlmTestResult> {
  return apiPost<LlmTestResult>('/settings/test-llm', payload)
}
