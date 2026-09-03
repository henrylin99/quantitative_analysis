import { useEffect, useMemo, useRef, useState } from 'react'
import { io, type Socket } from 'socket.io-client'
import {
  fetchWsConnections,
  fetchWsStatus,
  startPush,
  stopPush,
  testWsConnection,
  updatePushConfig,
  type PushConfig,
} from '../api/realtime'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'

const PUSH_TYPES = ['market_data', 'indicators', 'signals', 'monitor', 'risk_alerts', 'portfolio', 'news']

interface LogEntry {
  time: string
  level: 'info' | 'success' | 'warn' | 'error' | 'push'
  text: string
}

export default function RtWebsocketPage() {
  const socketRef = useRef<Socket | null>(null)
  const [connected, setConnected] = useState(false)
  const [clientId, setClientId] = useState<string | null>(null)
  const [conns, setConns] = useState<{ total_clients: number; total_rooms: number } | null>(null)
  const [pushRunning, setPushRunning] = useState(false)
  const [pushConfig, setPushConfig] = useState<PushConfig>({})
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [liveData, setLiveData] = useState<{ event: string; text: string; time: string }[]>([])
  const [msgCount, setMsgCount] = useState(0)
  const [subType, setSubType] = useState('market_data')
  const [subSymbol, setSubSymbol] = useState('')
  const [subs, setSubs] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)

  const log = (level: LogEntry['level'], text: string) =>
    setLogs((prev) => [...prev.slice(-99), { time: new Date().toLocaleTimeString('zh-CN'), level, text }])

  useEffect(() => {
    const socket = io(window.location.origin, { transports: ['websocket', 'polling'] })
    socketRef.current = socket
    socket.on('connect', () => {
      setConnected(true)
      log('success', `已连接 SocketIO（${socket.id}）`)
    })
    socket.on('connected', (data: { client_id?: string; message?: string }) => {
      setClientId(data?.client_id ?? null)
      log('info', data?.message ?? '服务端已确认连接')
    })
    socket.on('disconnect', () => {
      setConnected(false)
      log('error', '连接已断开')
    })
    socket.on('subscribed', (d: { type?: string; message?: string }) => {
      log('success', `订阅成功：${d?.type} · ${d?.message ?? ''}`)
    })
    socket.on('unsubscribed', (d: { type?: string }) => {
      log('warn', `已退订：${d?.type}`)
    })
    socket.on('pong', (d: { timestamp?: string }) => log('info', `pong ${d?.timestamp ?? ''}`))
    socket.on('status', (d: { total_clients?: number; total_rooms?: number }) => {
      log('info', `状态：客户端 ${d?.total_clients} · 房间 ${d?.total_rooms}`)
      setConns({ total_clients: d?.total_clients ?? 0, total_rooms: d?.total_rooms ?? 0 })
    })
    socket.on('error', (d: { message?: string }) => log('error', d?.message ?? '服务端错误'))

    const pushHandler = (event: string) => (payload: unknown) => {
      setMsgCount((c) => c + 1)
      const text = JSON.stringify(payload)
      setLiveData((prev) => [{ event, text: text.slice(0, 200), time: new Date().toLocaleTimeString('zh-CN') }, ...prev].slice(0, 10))
      log('push', `[${event}] ${text.slice(0, 160)}`)
    }
    const events = ['market_data_update', 'indicators_update', 'signals_update', 'monitor_update', 'risk_alert', 'portfolio_update', 'news_update']
    for (const evt of events) socket.on(evt, pushHandler(evt))

    // REST 状态
    fetchWsStatus()
      .then((r) => {
        setPushRunning(!!r.data?.is_running)
        if (r.data?.push_config) setPushConfig(r.data.push_config)
      })
      .catch(() => undefined)
    refreshConns()

    return () => {
      socket.disconnect()
      socketRef.current = null
    }
  }, [])

  const refreshConns = () => {
    fetchWsConnections()
      .then((r) => setConns({ total_clients: r.data?.total_clients ?? 0, total_rooms: r.data?.total_rooms ?? 0 }))
      .catch(() => undefined)
  }

  // 每 10 秒刷新连接统计
  useEffect(() => {
    const timer = setInterval(refreshConns, 10_000)
    return () => clearInterval(timer)
  }, [])

  const doSubscribe = () => {
    const socket = socketRef.current
    if (!socket) return
    const params = subSymbol ? { symbol: subSymbol.toUpperCase() } : {}
    socket.emit('subscribe', { type: subType, params })
    setSubs((prev) => [...new Set([...prev, `${subType}${subSymbol ? ` · ${subSymbol.toUpperCase()}` : ' · 全部'}`])])
  }

  const doUnsubscribe = () => {
    const socket = socketRef.current
    if (!socket) return
    socket.emit('unsubscribe', { type: subType, params: subSymbol ? { symbol: subSymbol.toUpperCase() } : {} })
    setSubs((prev) => prev.filter((s) => !s.startsWith(subType)))
  }

  const updateConfig = async (type: string, patch: { enabled?: boolean; interval?: number }) => {
    const next: PushConfig = { ...pushConfig, [type]: { enabled: patch.enabled ?? pushConfig[type]?.enabled ?? false, interval: patch.interval ?? pushConfig[type]?.interval ?? 10 } }
    setPushConfig(next)
    try {
      await updatePushConfig(next)
    } catch (e) {
      setError(e instanceof Error ? e.message : '推送配置保存失败')
    }
  }

  const togglePush = async () => {
    setError(null)
    try {
      if (pushRunning) {
        const r = await stopPush()
        log('warn', r.message ?? '推送已停止')
        setPushRunning(false)
      } else {
        const r = await startPush()
        log('success', r.message ?? '推送已启动')
        setPushRunning(true)
      }
      refreshConns()
    } catch (e) {
      setError(e instanceof Error ? e.message : '操作失败')
    }
  }

  const handleTest = async () => {
    try {
      const r = await testWsConnection()
      log('info', r.message ?? '已触发一次测试推送')
    } catch (e) {
      log('error', e instanceof Error ? e.message : '测试失败')
    }
  }

  const configTypes = useMemo(() => {
    const merged = new Set([...PUSH_TYPES, ...Object.keys(pushConfig)])
    return [...merged]
  }, [pushConfig])

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>推送管理</h2>
          <p className="desc">SocketIO 实时连接 · 订阅与推送服务控制</p>
        </div>
        <span className={`badge ${connected ? 'text-bg-success' : 'text-bg-danger'}`}>{connected ? '已连接' : '未连接'}</span>
      </div>

      {error && <ErrorState message={error} />}

      <div className="stat-grid">
        <div className="stat">
          <div className="stat-value">{conns?.total_clients ?? '--'}</div>
          <div className="stat-label">在线客户端</div>
        </div>
        <div className="stat">
          <div className="stat-value">{conns?.total_rooms ?? '--'}</div>
          <div className="stat-label">活跃房间</div>
        </div>
        <div className="stat">
          <div className={`stat-value ${pushRunning ? 'text-up' : ''}`} style={{ fontSize: 18 }}>
            {pushRunning ? '推送中' : '已停止'}
          </div>
          <div className="stat-label">推送服务</div>
        </div>
        <div className="stat">
          <div className="stat-value">{msgCount}</div>
          <div className="stat-label">累计消息</div>
        </div>
      </div>

      <div className="row g-3">
        <div className="col-lg-6">
          <div className="panel h-100">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                推送服务
              </h6>
              <div className="d-flex gap-2">
                <button type="button" className={`btn btn-sm ${pushRunning ? 'btn-outline-danger' : 'btn-primary'}`} onClick={togglePush}>
                  {pushRunning ? '停止推送' : '启动推送'}
                </button>
                <button type="button" className="btn btn-outline-secondary btn-sm" onClick={handleTest}>
                  测试连接
                </button>
              </div>
            </div>
            <div className="panel-body">
              {configTypes.length === 0 && <Loading text="加载推送配置..." />}
              <div className="d-flex flex-column gap-2">
                {configTypes.map((type) => (
                  <div key={type} className="d-flex align-items-center gap-3 p-2 rounded" style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
                    <code style={{ minWidth: 130 }}>{type}</code>
                    <label className="d-flex align-items-center gap-1" style={{ fontSize: 12.5, cursor: 'pointer' }}>
                      <input
                        type="checkbox"
                        className="form-check-input mt-0"
                        checked={pushConfig[type]?.enabled ?? false}
                        onChange={(e) => updateConfig(type, { enabled: e.target.checked })}
                      />
                      启用
                    </label>
                    <input
                      type="number"
                      className="form-control form-control-sm"
                      style={{ width: 100 }}
                      min={10}
                      max={3600}
                      value={pushConfig[type]?.interval ?? 10}
                      onChange={(e) => updateConfig(type, { interval: Number(e.target.value) })}
                    />
                    <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>秒（10-3600）</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="col-lg-6">
          <div className="panel h-100">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                订阅管理
                {clientId && <span className="chip">{clientId.slice(0, 12)}…</span>}
              </h6>
            </div>
            <div className="panel-body">
              <div className="row g-2 align-items-end">
                <div className="col-6">
                  <label className="form-label">推送类型</label>
                  <select className="form-select" value={subType} onChange={(e) => setSubType(e.target.value)}>
                    {PUSH_TYPES.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="col-6">
                  <label className="form-label">股票代码（可选）</label>
                  <input type="text" className="form-control" placeholder="留空 = 全部" value={subSymbol} onChange={(e) => setSubSymbol(e.target.value.toUpperCase())} />
                </div>
              </div>
              <div className="d-flex gap-2 mt-3">
                <button type="button" className="btn btn-primary btn-sm" disabled={!connected} onClick={doSubscribe}>
                  订阅
                </button>
                <button type="button" className="btn btn-outline-secondary btn-sm" disabled={!connected} onClick={doUnsubscribe}>
                  退订
                </button>
              </div>
              <div className="d-flex gap-1 flex-wrap mt-3">
                {subs.map((s) => (
                  <span className="chip" key={s}>
                    {s}
                  </span>
                ))}
                {subs.length === 0 && <span style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>当前会话暂无订阅</span>}
              </div>
            </div>
          </div>
        </div>

        <div className="col-lg-5">
          <div className="panel h-100">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                实时数据（最近 10 条）
              </h6>
            </div>
            <div className="panel-body d-flex flex-column gap-2" style={{ maxHeight: 420, overflowY: 'auto' }}>
              {liveData.map((d, i) => (
                <div key={i} className="p-2 rounded" style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', fontSize: 12 }}>
                  <div className="d-flex justify-content-between">
                    <b>{d.event}</b>
                    <span style={{ color: 'var(--text-faint)' }}>{d.time}</span>
                  </div>
                  <code style={{ fontSize: 10.5, wordBreak: 'break-all' }}>{d.text}</code>
                </div>
              ))}
              {liveData.length === 0 && <EmptyState icon="🔌" text="等待实时数据…（先启动推送并订阅）" />}
            </div>
          </div>
        </div>

        <div className="col-lg-7">
          <div className="panel h-100">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                消息日志
                <span className="chip">{logs.length} 条</span>
              </h6>
              <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => setLogs([])}>
                清空
              </button>
            </div>
            <div className="panel-body" style={{ maxHeight: 420, overflowY: 'auto' }}>
              {logs.map((l, i) => (
                <div key={i} style={{ fontSize: 12, fontFamily: 'ui-monospace, monospace', lineHeight: 1.7 }}>
                  <span style={{ color: 'var(--text-faint)' }}>{l.time}</span>{' '}
                  <span style={{ color: l.level === 'success' ? paletteSafe('#34d399') : l.level === 'error' ? '#f87171' : l.level === 'warn' ? '#fbbf24' : l.level === 'push' ? '#818cf8' : 'inherit' }}>
                    {l.text}
                  </span>
                </div>
              ))}
              {logs.length === 0 && <EmptyState icon="📜" text="暂无日志" />}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function paletteSafe(fallback: string): string {
  try {
    const css = getComputedStyle(document.documentElement).getPropertyValue('--up').trim()
    return css || fallback
  } catch {
    return fallback
  }
}
