import { useEffect, useState } from 'react'
import type React from 'react'
import {
  backtestSignalStrategy,
  fetchActiveSignals,
  fetchSignalStats,
  fetchSignalStrategies,
  fuseSignals,
  generateSignals,
  type ActiveSignal,
  type SignalStrategy,
} from '../api/realtime'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { addDaysLocal, formatDateTime, formatNumber, formatPercent, pctClass, toLocalDate } from '../utils/format'

const TABS = [
  { key: 'generate', label: '信号生成' },
  { key: 'fuse', label: '信号融合' },
  { key: 'monitor', label: '信号监控' },
  { key: 'backtest', label: '策略回测' },
] as const

type TabKey = (typeof TABS)[number]['key']
const LOOKBACKS = [3, 5, 7, 10]
const FUSE_WINDOWS = [0.5, 1, 2, 4, 8]

function strengthBar(v: number): React.ReactElement {
  const pct = Math.max(2, Math.min(100, v * 100))
  return (
    <div className="progress" style={{ height: 6 }}>
      <div className={`progress-bar ${pct >= 70 ? 'bg-danger' : pct >= 40 ? 'bg-warning' : 'bg-secondary'}`} style={{ width: `${pct}%` }} />
    </div>
  )
}

export default function RtSignalsPage() {
  const [tab, setTab] = useState<TabKey>('generate')
  const [strategies, setStrategies] = useState<SignalStrategy[]>([])
  const [selStrategies, setSelStrategies] = useState<Set<string>>(new Set())
  const [stats, setStats] = useState<Awaited<ReturnType<typeof fetchSignalStats>>>(null)

  const [code, setCode] = useState('000001.SZ')
  const [period, setPeriod] = useState('5min')
  const [lookback, setLookback] = useState(5)

  // 生成
  const [genBusy, setGenBusy] = useState(false)
  const [genError, setGenError] = useState<string | null>(null)
  const [genResult, setGenResult] = useState<Awaited<ReturnType<typeof generateSignals>>['data'] | null>(null)

  // 融合
  const [fuseWindow, setFuseWindow] = useState(1)
  const [fuseBusy, setFuseBusy] = useState(false)
  const [fuseError, setFuseError] = useState<string | null>(null)
  const [fuseResult, setFuseResult] = useState<Awaited<ReturnType<typeof fuseSignals>>['data'] | null>(null)

  // 监控
  const [monCode, setMonCode] = useState('')
  const [monStrategy, setMonStrategy] = useState('')
  const [signals, setSignals] = useState<ActiveSignal[]>([])
  const [monBusy, setMonBusy] = useState(false)

  // 回测
  const [btStart, setBtStart] = useState(addDaysLocal(new Date(), -7))
  const [btEnd, setBtEnd] = useState(toLocalDate(new Date()))
  const [btBusy, setBtBusy] = useState(false)
  const [btError, setBtError] = useState<string | null>(null)
  const [btResult, setBtResult] = useState<Awaited<ReturnType<typeof backtestSignalStrategy>>['data'] | null>(null)

  useEffect(() => {
    fetchSignalStrategies()
      .then((list) => {
        setStrategies(list)
        setSelStrategies(new Set(list.map((s) => s.name)))
      })
      .catch(() => setStrategies([]))
    refreshMonitor()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const refreshMonitor = async () => {
    setMonBusy(true)
    setSignals(await fetchActiveSignals(50, monCode || undefined, monStrategy || undefined))
    setStats(await fetchSignalStats())
    setMonBusy(false)
  }

  const runGenerate = async () => {
    setGenBusy(true)
    setGenError(null)
    setGenResult(null)
    try {
      const r = await generateSignals({ ts_code: code, period_type: period, strategies: [...selStrategies], lookback_days: lookback })
      setGenResult(r.data ?? null)
    } catch (e) {
      setGenError(e instanceof Error ? e.message : '生成失败')
    } finally {
      setGenBusy(false)
    }
  }

  const runFuse = async () => {
    setFuseBusy(true)
    setFuseError(null)
    setFuseResult(null)
    try {
      const r = await fuseSignals({ ts_code: code, period_type: period, time_window_hours: fuseWindow })
      setFuseResult(r.data ?? null)
    } catch (e) {
      setFuseError(e instanceof Error ? e.message : '融合失败')
    } finally {
      setFuseBusy(false)
    }
  }

  const runBacktest = async () => {
    setBtBusy(true)
    setBtError(null)
    setBtResult(null)
    try {
      const r = await backtestSignalStrategy({
        strategy_name: monStrategy || strategies[0]?.name || '',
        ts_code: code,
        start_date: btStart,
        end_date: btEnd,
        period_type: period,
      })
      setBtResult(r.data ?? null)
    } catch (e) {
      setBtError(e instanceof Error ? e.message : '回测失败')
    } finally {
      setBtBusy(false)
    }
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>交易信号</h2>
          <p className="desc">
            信号生成 / 融合 / 监控 / 回测 · 总信号 {stats?.total_signals ?? '--'} · 覆盖 {stats?.total_stocks ?? '--'} 只
          </p>
        </div>
        <div className="seg" role="group" style={{ flexWrap: 'wrap' }}>
          {TABS.map((t) => (
            <button key={t.key} type="button" className={`seg-item ${tab === t.key ? 'active' : ''}`} onClick={() => setTab(t.key)}>
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {tab === 'generate' && (
        <>
          <div className="panel">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                生成配置
                <span className="chip">已选 {selStrategies.size} / {strategies.length} 个策略</span>
              </h6>
              <div className="d-flex gap-2">
                <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => setSelStrategies(new Set(strategies.map((s) => s.name)))}>
                  全选
                </button>
                <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => setSelStrategies(new Set())}>
                  清空
                </button>
              </div>
            </div>
            <div className="panel-body">
              <div className="row g-3 align-items-end mb-2">
                <div className="col-lg-3 col-md-4 col-6">
                  <label className="form-label">股票代码</label>
                  <input type="text" className="form-control" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} />
                </div>
                <div className="col-lg-2 col-md-3 col-6">
                  <label className="form-label">周期</label>
                  <select className="form-select" value={period} onChange={(e) => setPeriod(e.target.value)}>
                    {['5min', '15min', '30min', '60min'].map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="col-lg-2 col-md-3 col-6">
                  <label className="form-label">回看天数</label>
                  <select className="form-select" value={lookback} onChange={(e) => setLookback(Number(e.target.value))}>
                    {LOOKBACKS.map((d) => (
                      <option key={d} value={d}>
                        {d} 天
                      </option>
                    ))}
                  </select>
                </div>
                <div className="col-lg-3 col-md-4">
                  <button type="button" className="btn btn-primary w-100" disabled={genBusy || selStrategies.size === 0} onClick={runGenerate}>
                    {genBusy ? '生成中…' : '🚦 生成信号'}
                  </button>
                </div>
              </div>
              <div className="row g-2">
                {strategies.map((s) => (
                  <div className="col-lg-3 col-md-4 col-6" key={s.name}>
                    <label className="d-flex align-items-start gap-2 p-2 rounded" style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', cursor: 'pointer', fontSize: 12.5 }}>
                      <input
                        type="checkbox"
                        className="form-check-input mt-0"
                        checked={selStrategies.has(s.name)}
                        onChange={() =>
                          setSelStrategies((prev) => {
                            const next = new Set(prev)
                            if (next.has(s.name)) next.delete(s.name)
                            else next.add(s.name)
                            return next
                          })
                        }
                      />
                      <span>
                        <b>{s.display_name}</b>
                        <br />
                        <span style={{ color: 'var(--text-faint)' }}>{s.description}</span>
                      </span>
                    </label>
                  </div>
                ))}
              </div>
            </div>
          </div>
          {genBusy && <Loading text="基于分钟数据生成信号..." />}
          {genError && <ErrorState message={genError} onRetry={runGenerate} />}
          {genResult && !genBusy && (
            <div className="panel">
              <div className="panel-head">
                <h6 className="panel-title">
                  <span className="kicker" />
                  生成结果
                  <span className="chip">{genResult.signals_generated} 个信号</span>
                </h6>
              </div>
              <div className="panel-body">
                <div className="row g-2">
                  {(genResult.signals ?? []).map((s, i) => (
                    <div className="col-xl-3 col-md-4 col-6" key={`${s.strategy_name}-${i}`}>
                      <div className="stat" style={{ padding: '12px 14px' }}>
                        <div className="d-flex justify-content-between align-items-center mb-1">
                          <b>{s.strategy_name}</b>
                          <span className={`badge ${s.signal_type === 'BUY' ? 'text-bg-danger' : 'text-bg-success'}`}>
                            {s.signal_type === 'BUY' ? '买入' : '卖出'}
                          </span>
                        </div>
                        {strengthBar(s.signal_strength)}
                        <div className="sub mt-1">
                          强度 {formatNumber(s.signal_strength * 100, 0)}% · 置信 {formatNumber((s.confidence ?? 0) * 100, 0)}% · 触发价 {formatNumber(s.trigger_price, 2)}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
                {(genResult.signals ?? []).length === 0 && <EmptyState icon="🚦" text="该区间没有产生信号" />}
              </div>
            </div>
          )}
        </>
      )}

      {tab === 'fuse' && (
        <>
          <div className="panel">
            <div className="panel-body">
              <div className="row g-3 align-items-end">
                <div className="col-lg-3 col-md-4 col-6">
                  <label className="form-label">股票代码</label>
                  <input type="text" className="form-control" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} />
                </div>
                <div className="col-lg-2 col-md-3 col-6">
                  <label className="form-label">周期</label>
                  <select className="form-select" value={period} onChange={(e) => setPeriod(e.target.value)}>
                    {['5min', '15min', '30min', '60min'].map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="col-lg-3 col-md-3 col-6">
                  <label className="form-label">时间窗口</label>
                  <select className="form-select" value={fuseWindow} onChange={(e) => setFuseWindow(Number(e.target.value))}>
                    {FUSE_WINDOWS.map((w) => (
                      <option key={w} value={w}>
                        {w} 小时
                      </option>
                    ))}
                  </select>
                </div>
                <div className="col-lg-3 col-md-4">
                  <button type="button" className="btn btn-primary w-100" disabled={fuseBusy} onClick={runFuse}>
                    {fuseBusy ? '融合中…' : '信号融合'}
                  </button>
                </div>
              </div>
            </div>
          </div>
          {fuseBusy && <Loading text="融合窗口内信号..." />}
          {fuseError && <ErrorState message={fuseError} onRetry={runFuse} />}
          {fuseResult && !fuseBusy && (
            <div className="stat-grid">
              <div className="stat">
                <div className="stat-value" style={{ fontSize: 22 }}>
                  <span className={`badge ${fuseResult.fused_signal === 'BUY' ? 'text-bg-danger' : fuseResult.fused_signal === 'SELL' ? 'text-bg-success' : 'text-bg-secondary'}`}>
                    {fuseResult.fused_signal === 'BUY' ? '买入' : fuseResult.fused_signal === 'SELL' ? '卖出' : '中性'}
                  </span>
                </div>
                <div className="stat-label">融合方向</div>
                <div className="sub">
                  强度 {formatNumber((fuseResult.signal_strength ?? 0) * 100, 0)}% · 置信 {formatNumber((fuseResult.confidence ?? 0) * 100, 0)}%
                </div>
              </div>
              <div className="stat">
                <div className="stat-value text-up">{fuseResult.buy_signals}</div>
                <div className="stat-label">买入信号</div>
              </div>
              <div className="stat">
                <div className="stat-value text-down">{fuseResult.sell_signals}</div>
                <div className="stat-label">卖出信号</div>
              </div>
              <div className="stat">
                <div className="stat-value" style={{ fontSize: 18 }}>
                  {formatNumber(((fuseResult.buy_signals ?? 0) - (fuseResult.sell_signals ?? 0)), 0)}
                </div>
                <div className="stat-label">净信号差</div>
              </div>
            </div>
          )}
        </>
      )}

      {tab === 'monitor' && (
        <div className="panel">
          <div className="panel-head">
            <h6 className="panel-title">
              <span className="kicker" />
              活跃信号
              <span className="chip">{signals.length} 条</span>
            </h6>
            <div className="d-flex gap-2 align-items-end">
              <input type="text" className="form-control form-control-sm" placeholder="股票代码（可空）" style={{ width: 150 }} value={monCode} onChange={(e) => setMonCode(e.target.value.toUpperCase())} />
              <select className="form-select form-select-sm" style={{ width: 170 }} value={monStrategy} onChange={(e) => setMonStrategy(e.target.value)}>
                <option value="">全部策略</option>
                {strategies.map((s) => (
                  <option key={s.name} value={s.name}>
                    {s.display_name}
                  </option>
                ))}
              </select>
              <button type="button" className="btn btn-outline-secondary btn-sm" onClick={refreshMonitor} disabled={monBusy}>
                ⟳ 刷新
              </button>
            </div>
          </div>
          <div className="panel-body tight table-container" style={{ maxHeight: 560 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>代码</th>
                  <th>策略</th>
                  <th>方向</th>
                  <th className="num">强度</th>
                  <th className="num">置信</th>
                  <th className="num">触发价</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((s, i) => (
                  <tr key={`${s.ts_code}-${s.strategy_name}-${i}`}>
                    <td>{formatDateTime(s.datetime)}</td>
                    <td>
                      <code>{s.ts_code}</code>
                    </td>
                    <td>{s.strategy_name}</td>
                    <td>
                      <span className={`badge ${s.signal_type === 'BUY' ? 'text-bg-danger' : 'text-bg-success'}`}>
                        {s.signal_type === 'BUY' ? '买入' : '卖出'}
                      </span>
                    </td>
                    <td className="num">{formatNumber(s.signal_strength * 100, 0)}%</td>
                    <td className="num">{formatNumber((s.confidence ?? 0) * 100, 0)}%</td>
                    <td className="num">{formatNumber(s.trigger_price, 2)}</td>
                    <td>{s.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {signals.length === 0 && <EmptyState icon="🚦" text="暂无活跃信号" />}
          </div>
        </div>
      )}

      {tab === 'backtest' && (
        <>
          <div className="panel">
            <div className="panel-body">
              <div className="row g-3 align-items-end">
                <div className="col-lg-2 col-md-4 col-6">
                  <label className="form-label">策略</label>
                  <select className="form-select" value={monStrategy} onChange={(e) => setMonStrategy(e.target.value)}>
                    <option value="">默认首个</option>
                    {strategies.map((s) => (
                      <option key={s.name} value={s.name}>
                        {s.display_name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="col-lg-2 col-md-4 col-6">
                  <label className="form-label">股票代码</label>
                  <input type="text" className="form-control" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} />
                </div>
                <div className="col-lg-2 col-md-4 col-6">
                  <label className="form-label">开始日期</label>
                  <input type="date" className="form-control" value={btStart} onChange={(e) => setBtStart(e.target.value)} />
                </div>
                <div className="col-lg-2 col-md-4 col-6">
                  <label className="form-label">结束日期</label>
                  <input type="date" className="form-control" value={btEnd} onChange={(e) => setBtEnd(e.target.value)} />
                </div>
                <div className="col-lg-2 col-md-4 col-6">
                  <label className="form-label">周期</label>
                  <select className="form-select" value={period} onChange={(e) => setPeriod(e.target.value)}>
                    {['5min', '15min', '30min', '60min'].map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="col-lg-2 col-md-4">
                  <button type="button" className="btn btn-primary w-100" disabled={btBusy} onClick={runBacktest}>
                    {btBusy ? '回测中…' : '回测'}
                  </button>
                </div>
              </div>
            </div>
          </div>
          {btBusy && <Loading text="策略信号回测中..." />}
          {btError && <ErrorState message={btError} onRetry={runBacktest} />}
          {btResult && !btBusy && (
            <div className="stat-grid">
              <div className="stat">
                <div className="stat-label">总收益</div>
                <div className={`stat-value ${pctClass(btResult.total_return * 100)}`}>{formatPercent(btResult.total_return * 100)}</div>
                <div className="sub">{btResult.strategy_name} · {btResult.period}</div>
              </div>
              <div className="stat">
                <div className="stat-label">最大回撤</div>
                <div className="stat-value text-down">{formatPercent(btResult.max_drawdown * 100)}</div>
              </div>
              <div className="stat">
                <div className="stat-label">波动率</div>
                <div className="stat-value">{formatPercent(btResult.volatility * 100)}</div>
              </div>
              <div className="stat">
                <div className="stat-label">夏普比率</div>
                <div className="stat-value">{formatNumber(btResult.sharpe_ratio, 2)}</div>
                <div className="sub">数据点 {btResult.data_points}</div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
