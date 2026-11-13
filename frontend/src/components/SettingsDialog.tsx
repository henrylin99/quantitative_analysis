import { useEffect, useState } from 'react'
import { Modal } from './ui/Modal'
import {
  fetchSystemSettings,
  updateSystemSettings,
  testLlmConfig,
  type LlmProvider,
  type LlmTestResult,
  type SystemSettings,
} from '../api/settings'
import { extractApiError } from '../api/client'

const LLM_PROVIDERS: { value: LlmProvider; label: string; baseUrlHint: string; modelHint: string; needKey: boolean }[] = [
  {
    value: 'openai',
    label: 'OpenAI 兼容（DeepSeek / GLM / Kimi / 通义 / OpenAI …）',
    baseUrlHint: '如 https://api.deepseek.com 或 https://open.bigmodel.cn/api/coding/paas/v4',
    modelHint: '如 deepseek-chat、glm-5.3-flash',
    needKey: true,
  },
  {
    value: 'ollama',
    label: 'Ollama 本地',
    baseUrlHint: '如 http://localhost:11434',
    modelHint: '如 qwen2.5-coder:latest',
    needKey: false,
  },
  {
    value: 'anthropic',
    label: 'Anthropic Claude',
    baseUrlHint: '如 https://api.anthropic.com',
    modelHint: '如 claude-sonnet-4-5',
    needKey: true,
  },
]

/**
 * 系统配置弹窗：tushare token / 扶摇 key / 大模型（base_url + model + api_key）
 * 三组配置在线修改，保存后不重启即生效（后端同步 .env + os.environ）。
 */
export function SettingsDialog({
  open,
  onClose,
  onSaved,
}: {
  open: boolean
  onClose: () => void
  onSaved?: (settings: SystemSettings) => void
}) {
  const [settings, setSettings] = useState<SystemSettings | null>(null)
  const [tushareToken, setTushareToken] = useState('')
  const [fuyaoKey, setFuyaoKey] = useState('')
  const [llmApiKey, setLlmApiKey] = useState('')
  const [llmBaseUrl, setLlmBaseUrl] = useState('')
  const [llmModel, setLlmModel] = useState('')
  const [llmProvider, setLlmProvider] = useState<LlmProvider>('openai')
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<LlmTestResult | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [savedKeys, setSavedKeys] = useState<string[] | null>(null)

  useEffect(() => {
    if (!open) return
    setError(null)
    setSavedKeys(null)
    setTestResult(null)
    setTushareToken('')
    setFuyaoKey('')
    setLlmApiKey('')
    fetchSystemSettings()
      .then((s) => {
        setSettings(s)
        setLlmBaseUrl(s.llm.base_url || '')
        setLlmModel(s.llm.model || '')
        setLlmProvider(s.llm.provider || 'openai')
      })
      .catch(() => setSettings(null))
  }, [open])

  const providerMeta =
    LLM_PROVIDERS.find((p) => p.value === llmProvider) || LLM_PROVIDERS[0]

  /** 保存前先试：填了 api_key 用输入值，否则测已保存配置（后端回退 env） */
  const handleTestLlm = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const result = await testLlmConfig({
        provider: llmProvider,
        base_url: llmBaseUrl.trim(),
        model: llmModel.trim(),
        api_key: llmApiKey.trim(),
      })
      setTestResult(result)
    } catch (e) {
      setTestResult({ ok: false, error: extractApiError(e, '测试请求失败') })
    } finally {
      setTesting(false)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    setSavedKeys(null)
    const payload: Record<string, string> = {}
    if (tushareToken.trim()) payload.TUSHARE_TOKEN = tushareToken.trim()
    if (fuyaoKey.trim()) payload.FUYAO_API_KEY = fuyaoKey.trim()
    if (llmApiKey.trim()) payload.LLM_API_KEY = llmApiKey.trim()
    if (llmBaseUrl.trim()) payload.LLM_BASE_URL = llmBaseUrl.trim()
    if (llmModel.trim()) payload.LLM_MODEL = llmModel.trim()
    payload.LLM_PROVIDER = llmProvider
    if (Object.keys(payload).length === 0) {
      setError('没有填写任何修改项')
      setSaving(false)
      return
    }
    try {
      const result = await updateSystemSettings(payload)
      setSavedKeys(result.updated)
      setTushareToken('')
      setFuyaoKey('')
      setLlmApiKey('')
      const fresh = await fetchSystemSettings(true)
      setSettings(fresh)
      onSaved?.(fresh)
    } catch (e) {
      setError(extractApiError(e, '保存失败'))
    } finally {
      setSaving(false)
    }
  }

  const statusDot = (configured?: boolean) =>
    configured ? '🟢 已配置' : '🔴 未配置'

  return (
    <Modal open={open} onClose={onClose} title="系统配置" width="max-w-xl">
      <div className="space-y-5">
        <p className="text-sm opacity-70">
          配置保存在服务端 .env，保存后立即生效（无需重启）。留空 = 保持不变。
        </p>

        <section className="space-y-2">
          <h4 className="font-medium">
            Tushare 数据源 <span className="ml-2 text-sm opacity-70">{statusDot(settings?.tushare.configured)}</span>
            {settings?.tushare.token_masked && (
              <span className="ml-2 text-xs opacity-50">当前 {settings.tushare.token_masked}</span>
            )}
          </h4>
          <input
            className="kinput w-full"
            type="password"
            placeholder="TUSHARE_TOKEN"
            value={tushareToken}
            onChange={(e) => setTushareToken(e.target.value)}
            autoComplete="off"
          />
        </section>

        <section className="space-y-2">
          <h4 className="font-medium">
            扶摇（fuyao）数据源 <span className="ml-2 text-sm opacity-70">{statusDot(settings?.fuyao.configured)}</span>
            {settings?.fuyao.api_key_masked && (
              <span className="ml-2 text-xs opacity-50">当前 {settings.fuyao.api_key_masked}</span>
            )}
            <a
              className="ml-2 text-xs"
              style={{ color: 'var(--accent)' }}
              href="https://fuyao.aicubes.cn/"
              target="_blank"
              rel="noreferrer"
            >
              获取 API Key ↗
            </a>
          </h4>
          <input
            className="kinput w-full"
            type="password"
            placeholder="FUYAO_API_KEY"
            value={fuyaoKey}
            onChange={(e) => setFuyaoKey(e.target.value)}
            autoComplete="off"
          />
        </section>

        <section className="space-y-2">
          <h4 className="font-medium">
            大模型 <span className="ml-2 text-sm opacity-70">{statusDot(settings?.llm.configured)}</span>
            <button
              className="btn btn-outline-primary btn-sm ml-2"
              onClick={handleTestLlm}
              disabled={testing || saving}
              title="真实调用一次大模型，验证当前填写/已保存的配置是否可用"
            >
              {testing ? '测试中…' : '测试连接'}
            </button>
          </h4>
          <select
            className="kinput w-full"
            value={llmProvider}
            onChange={(e) => {
              setLlmProvider(e.target.value as LlmProvider)
              setTestResult(null)
            }}
          >
            {LLM_PROVIDERS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
          {providerMeta.needKey && (
            <input
              className="kinput w-full"
              type="password"
              placeholder={`LLM_API_KEY${settings?.llm.api_key_masked ? `（当前 ${settings.llm.api_key_masked}）` : ''}`}
              value={llmApiKey}
              onChange={(e) => setLlmApiKey(e.target.value)}
              autoComplete="off"
            />
          )}
          <input
            className="kinput w-full"
            type="text"
            placeholder={`LLM_BASE_URL（${providerMeta.baseUrlHint}）`}
            value={llmBaseUrl}
            onChange={(e) => setLlmBaseUrl(e.target.value)}
          />
          <input
            className="kinput w-full"
            type="text"
            placeholder={`LLM_MODEL（${providerMeta.modelHint}）`}
            value={llmModel}
            onChange={(e) => setLlmModel(e.target.value)}
          />
          {testResult && (
            <div
              className="text-sm"
              style={{ color: testResult.ok ? '#34d399' : '#f87171' }}
            >
              {testResult.ok
                ? `✓ 连接成功（${testResult.provider} · ${testResult.model} · ${testResult.latency_ms}ms）：${testResult.reply ?? ''}`
                : `✕ ${testResult.error ?? '测试失败'}`}
            </div>
          )}
        </section>

        {savedKeys && (
          <div className="text-sm text-emerald-400">
            已保存并生效：{savedKeys.join('、')}
          </div>
        )}
        {error && <div className="text-sm text-red-400">{error}</div>}

        <div className="flex justify-end gap-2 pt-1">
          <button className="btn btn-outline-primary" onClick={onClose} disabled={saving}>
            关闭
          </button>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? '保存中…' : '保存配置'}
          </button>
        </div>
      </div>
    </Modal>
  )
}
