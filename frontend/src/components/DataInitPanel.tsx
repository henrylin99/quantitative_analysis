import { useEffect, useRef, useState } from 'react'
import {
  cancelDataInit,
  fetchDataInitStatus,
  startDataInit,
  type DataInitStep,
  type DataInitStatus,
} from '../api/dataJobs'
import { extractApiError } from '../api/client'

/**
 * 数据初始化面板（新项目从零建库）：
 * - tushare 行情类默认下载 1 年（可改 1~30），fuyao 财务三表默认 10 年；
 * - 一键启动分阶段串行下载（元数据 → 日频 → 宽表/分区 → 财务 → 因子）；
 * - 运行中每 3s 轮询进度（步骤状态 + progress + message）。
 */
export function DataInitPanel() {
  const [status, setStatus] = useState<DataInitStatus | null>(null)
  const [tushareYears, setTushareYears] = useState(1)
  const [financialYears, setFinancialYears] = useState(10)
  const [starting, setStarting] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const timerRef = useRef<number | null>(null)

  const refresh = () => {
    fetchDataInitStatus().then(setStatus).catch(() => {})
  }

  useEffect(() => {
    refresh()
  }, [])

  // 运行中每 3s 轮询；结束后停表并再刷一次（拿最终状态）
  useEffect(() => {
    if (status?.running) {
      timerRef.current = window.setInterval(refresh, 3000)
    }
    return () => {
      if (timerRef.current) {
        window.clearInterval(timerRef.current)
        timerRef.current = null
      }
    }
  }, [status?.running])

  const start = async () => {
    setStarting(true)
    setError(null)
    try {
      await startDataInit(tushareYears, financialYears)
      refresh()
    } catch (e) {
      setError(extractApiError(e, '启动失败'))
    } finally {
      setStarting(false)
    }
  }

  const cancel = async () => {
    setCancelling(true)
    try {
      await cancelDataInit()
      refresh()
    } catch (e) {
      setError(extractApiError(e, '中断请求失败'))
    } finally {
      setCancelling(false)
    }
  }

  const record = status?.record ?? null
  const steps: DataInitStep[] = record
    ? Object.keys(record.steps)
        .sort((a, b) => Number(a) - Number(b))
        .map((k) => record.steps[k])
    : []
  const doneCount = steps.filter((s) => s.status === 'success' || s.status === 'skipped').length
  const running = status?.running ?? false

  const statusBadge = (s: DataInitStep) => {
    if (s.status === 'success') return <span className="chip" style={{ color: '#34d399' }}>✓ 完成</span>
    if (s.status === 'running') return <span className="chip" style={{ color: '#fbbf24' }}>⟳ 进行中</span>
    if (s.status === 'queued' || s.status === 'pending') return <span className="chip">排队</span>
    if (s.status === 'skipped') return <span className="chip" style={{ color: '#93c5fd' }}>⤿ 已存在，跳过</span>
    if (s.status === 'cancelled') return <span className="chip" style={{ color: '#fbbf24' }}>⊘ 已中断</span>
    if (s.status === 'failed' || s.status === 'error') return <span className="chip" style={{ color: '#f87171' }}>✕ 失败</span>
    return <span className="chip">{s.status}</span>
  }

  return (
    <div className="panel">
      <div className="panel-head">
        <h6 className="panel-title">
          <span className="kicker" />
          数据初始化
          {running && <span className="chip" style={{ color: '#fbbf24' }}>运行中</span>}
          {record && !running && (
            <span className="chip" style={{ color: record.ok ? '#34d399' : '#f87171' }}>
              {record.ok ? '✓ 已完成' : '✕ 未完成'}
            </span>
          )}
        </h6>
      </div>
      <div className="panel-body d-flex flex-column gap-2">
        <div style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>
          新项目从零建库：按阶段串行下载并派生（元数据 → 日频行情 → 宽表/分区 → 财务三表 → 因子）。
          已存在的数据自动跳过，只补缺失部分（中断后重跑即续传）。
        </div>

        <div className="d-flex align-items-center gap-2" style={{ fontSize: 12.5 }}>
          <label>
            Tushare 年数
            <input
              className="kinput"
              style={{ width: 64, marginLeft: 6 }}
              type="number"
              min={1}
              max={30}
              value={tushareYears}
              disabled={running}
              onChange={(e) => setTushareYears(Math.max(1, Math.min(30, Number(e.target.value) || 1)))}
            />
          </label>
          <label>
            财务年数
            <input
              className="kinput"
              style={{ width: 64, marginLeft: 6 }}
              type="number"
              min={1}
              max={30}
              value={financialYears}
              disabled={running}
              onChange={(e) => setFinancialYears(Math.max(1, Math.min(30, Number(e.target.value) || 10)))}
            />
          </label>
          <button
            className="btn btn-primary btn-sm"
            onClick={start}
            disabled={running || starting}
            title="启动后可在下方查看每步进度；整链可能耗时数十分钟"
          >
            {starting ? '启动中…' : running ? '初始化进行中' : '开始初始化'}
          </button>
          {running && (
            <button
              className="btn btn-outline-primary btn-sm"
              onClick={cancel}
              disabled={cancelling}
              title="中断：当前步骤跑完后停止（不硬杀正在下载的作业，防写坏数据分区）"
            >
              {cancelling ? '请求中…' : '中断'}
            </button>
          )}
        </div>

        {error && <div style={{ fontSize: 12.5, color: '#f87171' }}>{error}</div>}

        {record && (
          <>
            <div style={{ fontSize: 12, color: 'var(--text-faint)' }}>
              {record.started_at} 启动 · Tushare {record.tushare_years} 年（{record.tushare_window.start_date}~）
              · 财务 {record.financial_years} 年（{record.financial_window.start_date}~）
              · 步骤 {doneCount}/{record.steps_total}
              {record.message && !running && ` · ${record.message}`}
            </div>
            {running && (
              <div style={{ height: 6, background: 'var(--surface-2)', borderRadius: 3, overflow: 'hidden' }}>
                <div
                  style={{
                    width: `${Math.round((doneCount / Math.max(1, record.steps_total)) * 100)}%`,
                    height: '100%',
                    background: 'var(--accent)',
                    transition: 'width .4s',
                  }}
                />
              </div>
            )}
            <div className="d-flex flex-column gap-1" style={{ maxHeight: 360, overflowY: 'auto' }}>
              {steps.map((s) => (
                <div
                  key={s.index}
                  className="p-2 rounded d-flex align-items-center gap-2"
                  style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', fontSize: 12.5 }}
                >
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <strong>{s.label}</strong>
                    {s.message && (
                      <span style={{ color: 'var(--text-faint)', marginLeft: 8, fontSize: 11.5 }}>
                        {s.message}
                      </span>
                    )}
                  </span>
                  {s.status === 'running' && (
                    <span style={{ fontSize: 11, color: '#fbbf24' }}>{Math.round((s.progress || 0) * 100)}%</span>
                  )}
                  {statusBadge(s)}
                </div>
              ))}
            </div>
          </>
        )}
        {!record && !running && (
          <div style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>
            尚未执行过初始化。请先在首页「系统配置」确认 Tushare / 扶摇 token 已配置。
          </div>
        )}
      </div>
    </div>
  )
}
