import { useEffect, useRef, useState } from 'react'
import {
  aggregateMinuteData,
  buildWideTable,
  fetchDataJobDefs,
  fetchDataJobRun,
  fetchDataJobRuns,
  fetchInitStatus,
  fetchMinuteQuality,
  fetchMinuteStats,
  fetchMinuteSyncStatus,
  fetchWideTableStatus,
  submitDataJob,
  syncMinuteData,
  syncMinuteMultiple,
  type DataJobDef,
  type DataJobRun,
  type InitStatus,
  type MinuteStats,
  type WideTableStatus,
} from '../api/dataJobs'
import { EmptyState, ErrorState } from '../components/StateViews'
import { formatDateTime, formatNumber, toLocalDate } from '../utils/format'

const RECOMMENDED = ['trade_calendar', 'stock_basic', 'daily_history_by_date', 'daily_basic']
const PERIODS = ['5min', '15min', '30min', '60min']
const RUN_BADGE: Record<string, string> = {
  pending: 'text-bg-secondary',
  queued: 'text-bg-info',
  running: 'text-bg-primary',
  success: 'text-bg-success',
  failed: 'text-bg-danger',
  cancelled: 'text-bg-warning',
}

function addDays(base: Date, days: number): string {
  const d = new Date(base)
  d.setDate(d.getDate() + days)
  return toLocalDate(d)
}

export default function DataManagementPage() {
  // —— 初始化状态 ——
  const [initStatus, setInitStatus] = useState<InitStatus | null>(null)

  // —— 分钟统计 ——
  const [stats, setStats] = useState<MinuteStats | null>(null)

  // —— 大宽表 ——
  const [wideTable, setWideTable] = useState<WideTableStatus | null>(null)
  const [wideBusy, setWideBusy] = useState(false)
  const [wideMsg, setWideMsg] = useState<string | null>(null)

  // —— 日频任务 ——
  const [jobDefs, setJobDefs] = useState<DataJobDef[]>([])
  const [runs, setRuns] = useState<DataJobRun[]>([])
  const [jobType, setJobType] = useState('')
  const [jobStart, setJobStart] = useState(addDays(new Date(), -30))
  const [jobEnd, setJobEnd] = useState(toLocalDate(new Date()))
  const [jobBusy, setJobBusy] = useState(false)
  const [jobMsg, setJobMsg] = useState<string | null>(null)
  const [jobError, setJobError] = useState<string | null>(null)
  const [currentRun, setCurrentRun] = useState<DataJobRun | null>(null)
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null)

  // —— 分钟同步 ——
  const [syncCode, setSyncCode] = useState('000001.SZ')
  const [syncPeriod, setSyncPeriod] = useState('5min')
  const [syncSource, setSyncSource] = useState<'tdx' | 'baostock'>('tdx')
  const [syncStart, setSyncStart] = useState(addDays(new Date(), -7))
  const [syncEnd, setSyncEnd] = useState(toLocalDate(new Date()))
  const [syncBusy, setSyncBusy] = useState(false)
  const [syncProgress, setSyncProgress] = useState(0)
  const [logs, setLogs] = useState<string[]>([])
  const [batchText, setBatchText] = useState('')
  const [batchBusy, setBatchBusy] = useState(false)
  const [batchSize, setBatchSize] = useState(10)

  // —— 聚合 / 质检 ——
  const [aggFrom, setAggFrom] = useState('5min')
  const [aggTo, setAggTo] = useState('15min')
  const [aggBusy, setAggBusy] = useState(false)
  const [aggMsg, setAggMsg] = useState<string | null>(null)
  const [qualityHours, setQualityHours] = useState(24)
  const [quality, setQuality] = useState<Record<string, unknown> | null>(null)
  const [qualityBusy, setQualityBusy] = useState(false)

  const appendLog = (line: string) =>
    setLogs((prev) => [...prev.slice(-200), `[${new Date().toLocaleTimeString('zh-CN')}] ${line}`])

  const refreshAll = () => {
    fetchInitStatus().then((r) => setInitStatus(r.status)).catch(() => setInitStatus(null))
    fetchMinuteStats().then(setStats).catch(() => setStats(null))
    fetchWideTableStatus().then((r) => setWideTable(r.status)).catch(() => setWideTable(null))
    fetchDataJobDefs().then((r) => {
      setJobDefs(r.jobs)
      setJobType((prev) => prev || (r.jobs[0]?.job_type ?? ''))
    }).catch(() => setJobDefs([]))
    fetchDataJobRuns(20).then((r) => setRuns(r.runs)).catch(() => setRuns([]))
  }

  useEffect(refreshAll, [])

  useEffect(() => () => {
    if (pollTimer.current) clearInterval(pollTimer.current)
  }, [])

  const currentDef = jobDefs.find((j) => j.job_type === jobType)

  const startPolling = (runId: number) => {
    if (pollTimer.current) clearInterval(pollTimer.current)
    pollTimer.current = setInterval(async () => {
      try {
        const r = await fetchDataJobRun(runId)
        setCurrentRun(r.run)
        if (['success', 'failed', 'cancelled'].includes(r.run.status)) {
          if (pollTimer.current) clearInterval(pollTimer.current)
          appendLog(`任务 #${runId} 结束：${r.run.status}`)
          fetchDataJobRuns(20).then((x) => setRuns(x.runs)).catch(() => undefined)
          fetchWideTableStatus().then((x) => setWideTable(x.status)).catch(() => undefined)
        }
      } catch {
        if (pollTimer.current) clearInterval(pollTimer.current)
      }
    }, 3000)
  }

  const submitJob = async (type = jobType) => {
    setJobBusy(true)
    setJobError(null)
    setJobMsg(null)
    try {
      const r = await submitDataJob(type, { start_date: jobStart, end_date: jobEnd })
      setJobMsg(`任务已提交：run #${r.run_id}（${r.status}）`)
      appendLog(`提交任务 ${type} → run #${r.run_id}`)
      setCurrentRun(null)
      startPolling(r.run_id)
      fetchDataJobRuns(20).then((x) => setRuns(x.runs)).catch(() => undefined)
    } catch (e) {
      setJobError(e instanceof Error ? e.message : '提交失败')
    } finally {
      setJobBusy(false)
    }
  }

  const handleWideBuild = async () => {
    setWideBusy(true)
    setWideMsg(null)
    try {
      const r = await buildWideTable()
      setWideMsg(`大宽表构建任务已提交：run #${r.run_id}`)
      appendLog(`提交大宽表构建 → run #${r.run_id}`)
      startPolling(r.run_id)
      setTimeout(() => fetchWideTableStatus().then((x) => setWideTable(x.status)).catch(() => undefined), 5000)
    } catch (e) {
      setWideMsg(e instanceof Error ? e.message : '提交失败')
    } finally {
      setWideBusy(false)
    }
  }

  const runSync = async () => {
    setSyncBusy(true)
    setSyncProgress(5)
    appendLog(`开始同步 ${syncCode} ${syncPeriod} ${syncStart} ~ ${syncEnd}`)
    const timer = setInterval(() => setSyncProgress((p) => Math.min(92, p + Math.random() * 8)), 600)
    try {
      const r = await syncMinuteData({
        ts_code: syncCode,
        period_type: syncPeriod,
        start_date: syncStart,
        end_date: syncEnd,
        use_baostock: syncSource === 'baostock',
      })
      setSyncProgress(100)
      appendLog(`同步完成：${r.message}`)
      fetchMinuteStats().then(setStats).catch(() => undefined)
    } catch (e) {
      setSyncProgress(0)
      appendLog(`同步失败：${e instanceof Error ? e.message : '未知错误'}`)
    } finally {
      clearInterval(timer)
      setSyncBusy(false)
    }
  }

  const runBatchSync = async () => {
    const list = batchText.split(/[\n,，\s]+/).map((s) => s.trim().toUpperCase()).filter(Boolean)
    if (list.length === 0) {
      appendLog('批量同步：股票列表为空')
      return
    }
    setBatchBusy(true)
    appendLog(`批量同步 ${list.length} 只 · ${syncPeriod} · 批大小 ${batchSize}`)
    try {
      const r = await syncMinuteMultiple({
        stock_list: list,
        period_type: syncPeriod,
        start_date: syncStart,
        end_date: syncEnd,
        batch_size: batchSize,
        use_baostock: syncSource === 'baostock',
      })
      appendLog(`批量同步完成：成功 ${r.success_stocks} · 失败 ${r.failed_stocks} · 数据 ${r.total_data_count} 条`)
    } catch (e) {
      appendLog(`批量同步失败：${e instanceof Error ? e.message : '未知错误'}`)
    } finally {
      setBatchBusy(false)
    }
  }

  const runAggregate = async () => {
    setAggBusy(true)
    setAggMsg(null)
    try {
      const r = await aggregateMinuteData({ ts_code: syncCode, source_period: aggFrom, target_period: aggTo })
      setAggMsg(r.message)
    } catch (e) {
      setAggMsg(e instanceof Error ? e.message : '聚合失败')
    } finally {
      setAggBusy(false)
    }
  }

  const runQuality = async () => {
    setQualityBusy(true)
    setQuality(null)
    try {
      const r = await fetchMinuteQuality(syncCode, syncPeriod, qualityHours)
      setQuality(r as Record<string, unknown>)
    } catch (e) {
      setQuality({ status: 'error', message: e instanceof Error ? e.message : '检查失败' })
    } finally {
      setQualityBusy(false)
    }
  }

  const checkSyncStatus = async () => {
    try {
      const r = await fetchMinuteSyncStatus(syncCode, syncPeriod)
      appendLog(
        `同步状态 ${syncCode} ${syncPeriod}：${r.status} · ${r.data_count} 条 · 完整性 ${r.completeness}% · 最新 ${r.latest_time ?? '--'}`,
      )
    } catch (e) {
      appendLog(`同步状态查询失败：${e instanceof Error ? e.message : '未知错误'}`)
    }
  }

  const initOk = initStatus?.database.ok

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>数据管理</h2>
          <p className="desc">日频任务调度 · 大宽表构建 · 分钟数据同步 / 聚合 / 质检</p>
        </div>
        <button type="button" className="btn btn-outline-secondary btn-sm" onClick={refreshAll}>
          ⟳ 刷新
        </button>
      </div>

      {/* 初始化状态 */}
      <div className="panel">
        <div className="panel-head">
          <h6 className="panel-title">
            <span className="kicker" />
            初始化状态
            <span className={`badge ${initOk ? 'text-bg-success' : 'text-bg-warning'}`}>
              {initStatus ? (initOk ? '基础状态正常' : '需要初始化') : '检查中…'}
            </span>
          </h6>
          <span className="chip">执行模式 · {initStatus?.data_jobs.execution_mode ?? '--'}</span>
        </div>
        <div className="panel-body d-flex gap-2 flex-wrap">
          <span className="chip">Parquet 连接 · {initOk ? '正常' : '异常'}</span>
          <span className="chip">缺失资产 · {initStatus?.database.missing_parquet_assets.length ?? '--'}</span>
          <span className="chip">空资产 · {initStatus?.database.empty_parquet_assets.length ?? '--'}</span>
          {(initStatus?.database.next_actions ?? []).slice(0, 3).map((a) => (
            <span className="chip" key={a}>
              下一步 · {a}
            </span>
          ))}
        </div>
      </div>

      {/* 统计 */}
      <div className="stat-grid">
        <div className="stat">
          <div className="stat-value">{stats ? formatNumber(stats.total_stocks, 0) : '--'}</div>
          <div className="stat-label">总股票数（分钟库）</div>
        </div>
        <div className="stat">
          <div className="stat-value">{stats ? formatNumber(stats.total_records, 0) : '--'}</div>
          <div className="stat-label">总记录数</div>
        </div>
        <div className="stat">
          <div className="stat-value" style={{ fontSize: 16 }}>{stats?.latest_time ?? '--'}</div>
          <div className="stat-label">最新时间</div>
        </div>
        <div className="stat">
          <div className="stat-value" style={{ fontSize: 16 }}>{wideTable ? (wideTable.exists ? '正常' : '缺失') : '…'}</div>
          <div className="stat-label">大宽表数据状态</div>
        </div>
      </div>

      {/* 大宽表 */}
      <div className="panel">
        <div className="panel-head">
          <h6 className="panel-title">
            <span className="kicker" />
            大宽表（stock_business）
            <span
              className={`badge ${
                !wideTable ? 'text-bg-secondary' : wideTable.exists ? (wideTable.should_update ? 'text-bg-warning' : 'text-bg-success') : 'text-bg-danger'
              }`}
            >
              {!wideTable ? '检查中…' : wideTable.exists ? (wideTable.should_update ? '需更新' : '正常') : '缺失'}
            </span>
          </h6>
          <div className="d-flex gap-2">
            <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => fetchWideTableStatus().then((r) => setWideTable(r.status))}>
              刷新状态
            </button>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={wideBusy || (wideTable ? !wideTable.past_cutoff : true)}
              title={wideTable && !wideTable.past_cutoff ? '当前时间未过 18:00，数据源可能尚未下载完毕' : '合并日线基本指标、技术因子、资金流向与股票资料（仅保留最新交易日）'}
              onClick={handleWideBuild}
            >
              {wideBusy ? '提交中…' : '构建 / 更新大宽表'}
            </button>
          </div>
        </div>
        <div className="panel-body d-flex gap-2 flex-wrap align-items-center">
          <span className="chip">宽表日期 · {wideTable?.wide_table_date ?? '--'}</span>
          {wideTable &&
            Object.entries(wideTable.source_dates).map(([k, v]) => (
              <span className="chip" key={k}>
                {k} · {v ?? '--'}
              </span>
            ))}
          {wideTable && <span className="chip">原因 · {wideTable.reason}</span>}
          {wideMsg && <span className="alert-note py-1">{wideMsg}</span>}
        </div>
      </div>

      {/* 推荐初始化顺序 + 当前任务 */}
      <div className="row g-3">
        <div className="col-lg-5">
          <div className="panel h-100">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                推荐初始化顺序
              </h6>
            </div>
            <div className="panel-body">
              <div className="d-flex gap-2 flex-wrap mb-2">
                {RECOMMENDED.map((type, i) => {
                  const def = jobDefs.find((j) => j.job_type === type)
                  return (
                    <button
                      key={type}
                      type="button"
                      className={`seg-item ${jobType === type ? 'active' : ''}`}
                      onClick={() => setJobType(type)}
                    >
                      {i + 1}. {def?.display_name ?? type}
                    </button>
                  )
                })}
              </div>
              <div className="hint" style={{ fontSize: 12, color: 'var(--text-faint)' }}>
                推荐顺序：交易日历 → 股票基础信息 → 公司信息 → 日线历史 → 财务三表 → 每日指标 → 资金流 → 技术因子 → 筹码 → 大宽表。
              </div>
            </div>
          </div>
        </div>
        <div className="col-lg-7">
          <div className="panel h-100">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                当前任务说明
              </h6>
            </div>
            <div className="panel-body d-flex gap-2 flex-wrap align-items-center">
              <span className="chip">{currentDef?.display_name ?? (jobType || '--')}</span>
              <span className="chip">分组 · {currentDef?.group ?? '--'}</span>
              <span className="chip">数据来源 · {currentDef ? `${currentDef.source_name} / ${currentDef.source_mode}` : '--'}</span>
              {currentDef && <span className="alert-note py-1">{currentDef.description}</span>}
            </div>
          </div>
        </div>
      </div>

      {/* 日频数据中心 */}
      <div className="panel">
        <div className="panel-head">
          <h6 className="panel-title">
            <span className="kicker" />
            日频数据中心
          </h6>
          <button
            type="button"
            className="btn btn-outline-secondary btn-sm"
            onClick={() => fetchDataJobRuns(20).then((r) => setRuns(r.runs)).catch(() => undefined)}
          >
            ⟳ 刷新任务
          </button>
        </div>
        <div className="panel-body">
          <div className="row g-3 align-items-end">
            <div className="col-lg-4 col-md-6">
              <label className="form-label">任务类型</label>
              <select className="form-select" value={jobType} onChange={(e) => setJobType(e.target.value)}>
                {jobDefs.map((j) => (
                  <option key={j.job_type} value={j.job_type}>
                    {j.recommended_order ? `${j.recommended_order} - ` : ''}
                    {j.display_name}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-lg-2 col-md-3 col-6">
              <label className="form-label">开始日期</label>
              <input type="date" className="form-control" value={jobStart} onChange={(e) => setJobStart(e.target.value)} />
            </div>
            <div className="col-lg-2 col-md-3 col-6">
              <label className="form-label">结束日期</label>
              <input type="date" className="form-control" value={jobEnd} onChange={(e) => setJobEnd(e.target.value)} />
            </div>
            <div className="col-lg-2 col-md-4">
              <button type="button" className="btn btn-primary w-100" disabled={jobBusy || !jobType} onClick={() => submitJob()}>
                {jobBusy ? '提交中…' : '启动任务'}
              </button>
            </div>
          </div>
          {jobMsg && <div className="alert-note mt-2">{jobMsg}</div>}
          {jobError && (
            <div className="mt-2">
              <ErrorState message={jobError} />
            </div>
          )}

          {/* 任务进度面板 */}
          {currentRun && (
            <div className="mt-3 p-3 rounded" style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
              <div className="d-flex align-items-center gap-2 flex-wrap mb-2">
                <span className={`badge ${RUN_BADGE[currentRun.status] ?? 'text-bg-secondary'}`}>{currentRun.status}</span>
                <span className="chip">run #{currentRun.id}</span>
                <span className="chip">{currentRun.job_type}</span>
                <span className="chip">{currentRun.progress.toFixed(1)}%</span>
                {currentRun.progress_message && <span className="chip">{currentRun.progress_message}</span>}
                {currentRun.error_message && <span className="delta down">{currentRun.error_message}</span>}
              </div>
              <div className="progress mb-2" style={{ height: 8 }}>
                <div
                  className="progress-bar"
                  style={{ width: `${Math.min(100, Math.max(0, currentRun.progress))}%` }}
                  role="progressbar"
                />
              </div>
              {(currentRun.result_json?.stdout || currentRun.result_json?.stderr) && (
                <pre
                  style={{
                    maxHeight: 180,
                    overflow: 'auto',
                    fontSize: 11.5,
                    background: 'var(--surface)',
                    border: '1px solid var(--border)',
                    borderRadius: 8,
                    padding: 10,
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {currentRun.result_json?.stdout}
                  {currentRun.result_json?.stderr}
                </pre>
              )}
            </div>
          )}

          {/* 最近任务 */}
          <div className="table-container mt-3" style={{ maxHeight: 320 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Run ID</th>
                  <th>任务</th>
                  <th>状态</th>
                  <th className="num">进度%</th>
                  <th>进度消息</th>
                  <th>开始时间</th>
                  <th>结束时间</th>
                  <th className="num">操作</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr
                    key={r.id}
                    style={{ cursor: 'pointer' }}
                    onClick={() => {
                      setCurrentRun(r)
                      startPolling(r.id)
                    }}
                  >
                    <td>#{r.id}</td>
                    <td>{jobDefs.find((j) => j.job_type === r.job_type)?.display_name ?? r.job_type}</td>
                    <td>
                      <span className={`badge ${RUN_BADGE[r.status] ?? 'text-bg-secondary'}`}>{r.status}</span>
                    </td>
                    <td className="num">{r.progress.toFixed(0)}</td>
                    <td style={{ maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {r.progress_message ?? '--'}
                    </td>
                    <td>{formatDateTime(r.started_at)}</td>
                    <td>{formatDateTime(r.finished_at)}</td>
                    <td className="num">
                      {r.status === 'failed' && (
                        <button
                          type="button"
                          className="btn btn-outline-secondary btn-sm"
                          onClick={(e) => {
                            e.stopPropagation()
                            setJobType(r.job_type)
                            submitJob(r.job_type)
                          }}
                        >
                          重试
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {runs.length === 0 && (
                  <tr>
                    <td colSpan={8}>
                      <EmptyState icon="🗃️" text="暂无任务记录" />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* 分钟数据同步 */}
      <div className="panel">
        <div className="panel-head">
          <h6 className="panel-title">
            <span className="kicker" />
            分钟数据同步
            <span className="chip">周期 {PERIODS.join(' / ')}</span>
          </h6>
          <div className="d-flex gap-2">
            <button type="button" className="btn btn-outline-secondary btn-sm" onClick={checkSyncStatus}>
              同步状态
            </button>
          </div>
        </div>
        <div className="panel-body">
          <div className="row g-3 align-items-end">
            <div className="col-lg-2 col-md-4 col-6">
              <label className="form-label">股票代码</label>
              <input type="text" className="form-control" value={syncCode} onChange={(e) => setSyncCode(e.target.value.toUpperCase())} />
            </div>
            <div className="col-lg-2 col-md-4 col-6">
              <label className="form-label">周期类型</label>
              <select className="form-select" value={syncPeriod} onChange={(e) => setSyncPeriod(e.target.value)}>
                {PERIODS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-lg-2 col-md-4 col-6">
              <label className="form-label">数据源</label>
              <select className="form-select" value={syncSource} onChange={(e) => setSyncSource(e.target.value as 'tdx' | 'baostock')}>
                <option value="tdx">通达信</option>
                <option value="baostock">Baostock</option>
              </select>
            </div>
            <div className="col-lg-2 col-md-3 col-6">
              <label className="form-label">开始日期</label>
              <input type="date" className="form-control" value={syncStart} onChange={(e) => setSyncStart(e.target.value)} />
            </div>
            <div className="col-lg-2 col-md-3 col-6">
              <label className="form-label">结束日期</label>
              <input type="date" className="form-control" value={syncEnd} onChange={(e) => setSyncEnd(e.target.value)} />
            </div>
            <div className="col-lg-2 col-md-3">
              <button type="button" className="btn btn-primary w-100" disabled={syncBusy} onClick={runSync}>
                {syncBusy ? '同步中…' : '同步数据'}
              </button>
            </div>
          </div>

          {syncProgress > 0 && (
            <div className="progress mt-3" style={{ height: 8 }}>
              <div className="progress-bar progress-bar-striped progress-bar-animated" style={{ width: `${syncProgress}%` }} />
            </div>
          )}

          <div className="d-flex gap-2 mt-3 flex-wrap align-items-center">
            <input
              type="text"
              className="form-control"
              style={{ maxWidth: 420 }}
              placeholder="批量同步：逗号或换行分隔多只代码"
              value={batchText}
              onChange={(e) => setBatchText(e.target.value)}
            />
            <input
              type="number"
              className="form-control"
              style={{ maxWidth: 110 }}
              min={1}
              max={50}
              value={batchSize}
              onChange={(e) => setBatchSize(Number(e.target.value))}
              title="批处理大小"
            />
            <button type="button" className="btn btn-outline-primary" disabled={batchBusy || !batchText.trim()} onClick={runBatchSync}>
              {batchBusy ? '批量同步中…' : '批量同步'}
            </button>
          </div>

          <div className="d-flex gap-2 mt-3 flex-wrap align-items-end">
            <div>
              <label className="form-label">源周期</label>
              <select className="form-select" value={aggFrom} onChange={(e) => setAggFrom(e.target.value)}>
                {PERIODS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="form-label">目标周期</label>
              <select className="form-select" value={aggTo} onChange={(e) => setAggTo(e.target.value)}>
                {PERIODS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
            <button type="button" className="btn btn-outline-secondary" disabled={aggBusy} onClick={runAggregate}>
              {aggBusy ? '聚合中…' : '执行聚合'}
            </button>
            <div>
              <label className="form-label">质检时长(小时)</label>
              <input
                type="number"
                className="form-control"
                style={{ width: 120 }}
                min={1}
                max={168}
                value={qualityHours}
                onChange={(e) => setQualityHours(Number(e.target.value))}
              />
            </div>
            <button type="button" className="btn btn-outline-secondary" disabled={qualityBusy} onClick={runQuality}>
              {qualityBusy ? '检查中…' : '数据质量检查'}
            </button>
            {aggMsg && <span className="alert-note py-1">聚合：{aggMsg}</span>}
            {quality && (
              <span className="alert-note py-1">
                质检：{String(quality.status)} · {String(quality.data_count ?? '--')} 条 · 完整性 {String(quality.completeness ?? '--')}% ·{' '}
                {String(quality.message ?? '')}
              </span>
            )}
          </div>

          {/* 周期统计 + 日志 */}
          <div className="d-flex gap-2 mt-3 flex-wrap">
            {stats &&
              Object.entries(stats.period_stats).map(([p, count]) => (
                <span className="chip" key={p}>
                  {p} · {formatNumber(count, 0)} 条
                </span>
              ))}
          </div>

          {logs.length > 0 && (
            <div className="mt-3">
              <div className="d-flex justify-content-between align-items-center mb-1">
                <span className="side-group-label">操作日志</span>
                <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => setLogs([])}>
                  清空日志
                </button>
              </div>
              <pre
                style={{
                  maxHeight: 200,
                  overflow: 'auto',
                  fontSize: 11.5,
                  background: 'var(--surface-2)',
                  border: '1px solid var(--border)',
                  borderRadius: 8,
                  padding: 10,
                  whiteSpace: 'pre-wrap',
                }}
              >
                {logs.join('\n')}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
