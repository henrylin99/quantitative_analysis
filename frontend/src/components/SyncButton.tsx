import { useCallback, useEffect, useRef, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import * as hkApi from '../api/hkStock'
import * as usApi from '../api/usStock'
import type { MarketSyncStatus } from '../api/hkStock'

const APIS = {
  hk: hkApi,
  us: usApi,
} as const

type Market = keyof typeof APIS

interface Props {
  market: Market
  /** 同步成功后回调（页面借此刷新列表与数据日期） */
  onSynced?: () => void
}

const POLL_INTERVAL_MS = 3000
const POLL_ERROR_MS = 5000

/** 港美股列表页共用：后台同步按钮 + 上次同步时间/状态展示 */
export default function SyncButton({ market, onSynced }: Props) {
  const [status, setStatus] = useState<MarketSyncStatus | null>(null)
  const [starting, setStarting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const aliveRef = useRef(true)
  const timerRef = useRef<number | null>(null)
  const prevStatusRef = useRef<MarketSyncStatus['status'] | ''>('')

  const tick = useCallback(async () => {
    timerRef.current = null
    if (!aliveRef.current) return
    const api = APIS[market]
    let s: MarketSyncStatus | null = null
    try {
      s = await api.fetchSyncStatus()
    } catch {
      s = null
    }
    if (!aliveRef.current) return
    if (s) {
      if (s.status === 'success' && prevStatusRef.current === 'running') {
        onSynced?.()
      }
      prevStatusRef.current = s.status
      setStatus(s)
    }
    // 状态接口暂不可达但上一轮是 running 时也继续重试，避免轮询意外中断
    const stillRunning = s ? s.status === 'running' : prevStatusRef.current === 'running'
    if (stillRunning) {
      timerRef.current = window.setTimeout(tick, s ? POLL_INTERVAL_MS : POLL_ERROR_MS)
    }
  }, [market, onSynced])

  useEffect(() => {
    aliveRef.current = true
    tick()
    return () => {
      aliveRef.current = false
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
  }, [tick])

  const handleClick = async () => {
    setActionError(null)
    setStarting(true)
    try {
      const s = await APIS[market].startSync()
      prevStatusRef.current = s.status
      setStatus(s)
    } catch (err) {
      const msg = err instanceof Error ? err.message : '启动同步失败'
      // 409 = 已有同步在跑，不算错误，转轮询跟踪即可
      if (!msg.includes('已在进行中')) setActionError(msg)
    } finally {
      setStarting(false)
      if (!timerRef.current) {
        timerRef.current = window.setTimeout(tick, 800)
      }
    }
  }

  const running = status?.status === 'running'
  const failed = status?.status === 'failed'

  return (
    <div className="d-flex align-items-center gap-2 flex-wrap">
      {running && (
        <span className="chip" title={status?.message ?? ''}>
          <RefreshCw size={12} style={{ marginRight: 4 }} />
          同步中…
        </span>
      )}
      {!running && status?.finished_at && (
        <span className="chip text-muted">上次同步 {status.finished_at}</span>
      )}
      <button
        type="button"
        className="btn btn-outline-primary btn-sm"
        disabled={running || starting}
        onClick={handleClick}
        title="后台重新拉取雅虎财经数据（约 3-8 分钟，完成后自动刷新列表）"
      >
        <RefreshCw size={13} style={{ marginRight: 4 }} />
        {running ? '同步中…' : starting ? '启动中…' : '同步数据'}
      </button>
      {failed && (
        <span
          className="text-danger"
          style={{ fontSize: 12 }}
          title={status?.log_tail ?? undefined}
        >
          {status?.message}
        </span>
      )}
      {actionError && <span className="text-danger" style={{ fontSize: 12 }}>{actionError}</span>}
    </div>
  )
}
