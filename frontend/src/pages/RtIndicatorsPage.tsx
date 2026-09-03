import { useEffect, useMemo, useState } from 'react'
import EChart from '../charts/EChart'
import { useTheme } from '../theme/ThemeContext'
import {
  calculateIndicators,
  calculateMultiPeriod,
  compareIndicators,
  fetchIndicatorStats,
  fetchSupportedIndicators,
  type IndicatorStats,
  type SupportedIndicator,
} from '../api/realtime'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { formatNumber } from '../utils/format'

const TABS = [
  { key: 'calc', label: '指标计算' },
  { key: 'multi', label: '多周期分析' },
  { key: 'compare', label: '指标对比' },
  { key: 'stats', label: '统计信息' },
] as const

type TabKey = (typeof TABS)[number]['key']
const PERIODS = ['5min', '15min', '30min', '60min']

export default function RtIndicatorsPage() {
  const { palette } = useTheme()
  const [tab, setTab] = useState<TabKey>('calc')
  const [indicators, setIndicators] = useState<SupportedIndicator[]>([])
  const [stats, setStats] = useState<IndicatorStats | null>(null)

  // 指标计算
  const [code, setCode] = useState('000001.SZ')
  const [period, setPeriod] = useState('5min')
  const [lookback, setLookback] = useState(5)
  const [selInds, setSelInds] = useState<Set<string>>(new Set())
  const [calcBusy, setCalcBusy] = useState(false)
  const [calcError, setCalcError] = useState<string | null>(null)
  const [calcResult, setCalcResult] = useState<Awaited<ReturnType<typeof calculateIndicators>> | null>(null)

  // 多周期
  const [mpPeriods, setMpPeriods] = useState<Set<string>>(new Set(['5min', '15min']))
  const [mpBusy, setMpBusy] = useState(false)
  const [mpError, setMpError] = useState<string | null>(null)
  const [mpResult, setMpResult] = useState<Awaited<ReturnType<typeof calculateMultiPeriod>> | null>(null)

  // 对比
  const [cmpCodes, setCmpCodes] = useState('000001.SZ,600000.SH')
  const [cmpPeriod, setCmpPeriod] = useState('5min')
  const [cmpIndicator, setCmpIndicator] = useState('')
  const [cmpBusy, setCmpBusy] = useState(false)
  const [cmpError, setCmpError] = useState<string | null>(null)
  const [cmpResult, setCmpResult] = useState<Awaited<ReturnType<typeof compareIndicators>> | null>(null)

  useEffect(() => {
    fetchSupportedIndicators()
      .then((list) => {
        setIndicators(list)
        setSelInds(new Set(list.slice(0, 3).map((i) => i.code)))
        setCmpIndicator(list[0]?.code ?? '')
      })
      .catch(() => setIndicators([]))
    fetchIndicatorStats().then(setStats)
  }, [])

  const toggle = (set: Set<string>, apply: (s: Set<string>) => void, key: string) => {
    const next = new Set(set)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    apply(next)
  }

  const runCalc = async () => {
    setCalcBusy(true)
    setCalcError(null)
    setCalcResult(null)
    try {
      setCalcResult(await calculateIndicators({ ts_code: code, period_type: period, indicators: [...selInds], lookback_days: lookback }))
    } catch (e) {
      setCalcError(e instanceof Error ? e.message : '计算失败')
    } finally {
      setCalcBusy(false)
    }
  }

  const runMulti = async () => {
    setMpBusy(true)
    setMpError(null)
    setMpResult(null)
    try {
      setMpResult(await calculateMultiPeriod({ ts_code: code, periods: [...mpPeriods], indicators: [...selInds] }))
    } catch (e) {
      setMpError(e instanceof Error ? e.message : '分析失败')
    } finally {
      setMpBusy(false)
    }
  }

  const runCompare = async () => {
    setCmpBusy(true)
    setCmpError(null)
    setCmpResult(null)
    try {
      const codes = cmpCodes.split(/[,，\s]+/).map((s) => s.trim().toUpperCase()).filter(Boolean)
      setCmpResult(await compareIndicators({ stock_codes: codes, period_type: cmpPeriod, indicator_name: cmpIndicator, limit: 50 }))
    } catch (e) {
      setCmpError(e instanceof Error ? e.message : '对比失败')
    } finally {
      setCmpBusy(false)
    }
  }

  const cmpOption = useMemo(() => {
    if (!cmpResult?.data) return null
    const entries = Object.entries(cmpResult.data)
    if (entries.length === 0) return null
    const seriesColors = [palette.accent, palette.up, palette.teal, palette.amber, palette.violet]
    return {
      tooltip: { trigger: 'axis' },
      legend: { top: 0 },
      grid: { left: 56, right: 20, top: 34, bottom: 52 },
      dataZoom: [
        { type: 'inside', start: 0, end: 100 },
        { type: 'slider', start: 0, end: 100, height: 16, bottom: 6 },
      ],
      xAxis: { type: 'category', data: entries[0][1].map((p) => p.datetime.slice(5, 16)) },
      yAxis: { type: 'value', scale: true },
      series: entries.map(([tsCode, points], i) => ({
        name: tsCode,
        type: 'line' as const,
        showSymbol: false,
        connectNulls: false,
        itemStyle: { color: seriesColors[i % seriesColors.length] },
        data: points.map((p) => (p.value1 ?? null) as number | null),
      })),
    }
  }, [cmpResult, palette])

  const statsPieOption = useMemo(() => {
    if (!stats?.indicator_stats) return null
    const entries = Object.entries(stats.indicator_stats)
    if (entries.length === 0) return null
    return {
      tooltip: { trigger: 'item', formatter: '{b}: {c} 条 ({d}%)' },
      legend: { type: 'scroll', bottom: 0 },
      series: [{ type: 'pie', radius: ['34%', '62%'], data: entries.map(([name, value]) => ({ name, value })) }],
    }
  }, [stats])

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>实时技术指标</h2>
          <p className="desc">基于分钟数据的多周期指标计算、对比与统计</p>
        </div>
        <div className="seg" role="group" style={{ flexWrap: 'wrap' }}>
          {TABS.map((t) => (
            <button key={t.key} type="button" className={`seg-item ${tab === t.key ? 'active' : ''}`} onClick={() => setTab(t.key)}>
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {tab === 'calc' && (
        <>
          <div className="panel">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                计算配置
                <span className="chip">已选 {selInds.size} / {indicators.length} 个指标</span>
              </h6>
              <div className="d-flex gap-2">
                <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => setSelInds(new Set(indicators.map((i) => i.code)))}>
                  全选
                </button>
                <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => setSelInds(new Set())}>
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
                    {PERIODS.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="col-lg-2 col-md-3 col-6">
                  <label className="form-label">回看天数（1-90）</label>
                  <input type="number" className="form-control" min={1} max={90} value={lookback} onChange={(e) => setLookback(Number(e.target.value))} />
                </div>
                <div className="col-lg-3 col-md-4">
                  <button type="button" className="btn btn-primary w-100" disabled={calcBusy || selInds.size === 0} onClick={runCalc}>
                    {calcBusy ? '计算中…' : '计算指标'}
                  </button>
                </div>
              </div>
              <div className="d-flex gap-2 flex-wrap">
                {indicators.map((ind) => (
                  <label key={ind.code} className="d-inline-flex align-items-center gap-1" style={{ fontSize: 13, cursor: 'pointer' }} title={ind.description}>
                    <input type="checkbox" className="form-check-input mt-0" checked={selInds.has(ind.code)} onChange={() => toggle(selInds, setSelInds, ind.code)} />
                    {ind.name}
                  </label>
                ))}
              </div>
            </div>
          </div>
          {calcBusy && <Loading text="计算并入库指标..." />}
          {calcError && <ErrorState message={calcError} onRetry={runCalc} />}
          {calcResult && !calcBusy && (
            <div className="panel">
              <div className="panel-head">
                <h6 className="panel-title">
                  <span className="kicker" />
                  计算结果
                  <span className="chip">{calcResult.total_indicators} 指标 · {calcResult.data_points} 点 · 入库 {calcResult.stored_records} 条</span>
                </h6>
              </div>
              <div className="panel-body tight table-container" style={{ maxHeight: 400 }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>指标</th>
                      <th className="num">最新值</th>
                      <th className="num">入库条数</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(calcResult.latest_values).map(([name, v]) => (
                      <tr key={name}>
                        <td>
                          <code>{name}</code>
                        </td>
                        <td className="num">{Array.isArray(v) ? v.map((x) => formatNumber(x, 2)).join(' / ') : formatNumber(v as number, 2)}</td>
                        <td className="num">{calcResult.indicator_summary?.[name]?.stored_records ?? '--'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {tab === 'multi' && (
        <>
          <div className="panel">
            <div className="panel-body">
              <div className="row g-3 align-items-end">
                <div className="col-lg-3 col-md-4 col-6">
                  <label className="form-label">股票代码</label>
                  <input type="text" className="form-control" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} />
                </div>
                <div className="col-lg-5 col-md-6">
                  <label className="form-label">周期</label>
                  <div className="d-flex gap-3">
                    {PERIODS.map((p) => (
                      <label key={p} className="d-inline-flex align-items-center gap-1" style={{ fontSize: 13, cursor: 'pointer' }}>
                        <input type="checkbox" className="form-check-input mt-0" checked={mpPeriods.has(p)} onChange={() => toggle(mpPeriods, setMpPeriods, p)} />
                        {p}
                      </label>
                    ))}
                  </div>
                </div>
                <div className="col-lg-3 col-md-4">
                  <button type="button" className="btn btn-primary w-100" disabled={mpBusy || mpPeriods.size === 0} onClick={runMulti}>
                    {mpBusy ? '分析中…' : '多周期分析'}
                  </button>
                </div>
              </div>
            </div>
          </div>
          {mpBusy && <Loading text="逐周期计算..." />}
          {mpError && <ErrorState message={mpError} onRetry={runMulti} />}
          {mpResult && !mpBusy && (
            <div className="row g-3">
              {Object.entries(mpResult.data).map(([p, r]) => (
                <div className="col-lg-6" key={p}>
                  <div className="panel h-100">
                    <div className="panel-head">
                      <h6 className="panel-title">
                        <span className="kicker" />
                        {p}
                        <span className={`badge ${r.success ? 'text-bg-success' : 'text-bg-secondary'}`}>{r.success ? `${r.total_indicators} 指标` : '无数据'}</span>
                      </h6>
                    </div>
                    <div className="panel-body tight table-container" style={{ maxHeight: 300 }}>
                      <table className="data-table">
                        <tbody>
                          {Object.entries(r.latest_values ?? {}).map(([name, v]) => (
                            <tr key={name}>
                              <td>
                                <code>{name}</code>
                              </td>
                              <td className="num">
                                {Array.isArray(v) ? v.map((x) => formatNumber(x as number, 2)).join(' / ') : formatNumber(v as number, 2)}
                              </td>
                            </tr>
                          ))}
                          {!r.success && (
                            <tr>
                              <td>{r.message ?? '该周期暂无数据'}</td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {tab === 'compare' && (
        <>
          <div className="panel">
            <div className="panel-body">
              <div className="row g-3 align-items-end">
                <div className="col-lg-4 col-md-6">
                  <label className="form-label">多股票代码（逗号分隔）</label>
                  <input type="text" className="form-control" value={cmpCodes} onChange={(e) => setCmpCodes(e.target.value.toUpperCase())} />
                </div>
                <div className="col-lg-2 col-md-3 col-6">
                  <label className="form-label">周期</label>
                  <select className="form-select" value={cmpPeriod} onChange={(e) => setCmpPeriod(e.target.value)}>
                    {PERIODS.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="col-lg-3 col-md-3 col-6">
                  <label className="form-label">指标</label>
                  <select className="form-select" value={cmpIndicator} onChange={(e) => setCmpIndicator(e.target.value)}>
                    {indicators.map((i) => (
                      <option key={i.code} value={i.code}>
                        {i.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="col-lg-2 col-md-3">
                  <button type="button" className="btn btn-primary w-100" disabled={cmpBusy} onClick={runCompare}>
                    {cmpBusy ? '对比中…' : '开始对比'}
                  </button>
                </div>
              </div>
            </div>
          </div>
          {cmpBusy && <Loading text="生成对比序列..." />}
          {cmpError && <ErrorState message={cmpError} onRetry={runCompare} />}
          {cmpResult && !cmpBusy && (
            <div className="panel">
              <div className="panel-head">
                <h6 className="panel-title">
                  <span className="kicker" />
                  对比结果 · {cmpResult.indicator_name}
                  <span className="chip">{cmpResult.period_type}</span>
                </h6>
              </div>
              <div className="panel-body">
                {cmpOption ? <EChart option={cmpOption} height={420} /> : <EmptyState icon="📉" text={cmpResult.empty_state?.message ?? '暂无对比数据'} />}
              </div>
            </div>
          )}
        </>
      )}

      {tab === 'stats' && (
        <div className="row g-3">
          <div className="col-lg-4">
            <div className="panel h-100">
              <div className="panel-head">
                <h6 className="panel-title">
                  <span className="kicker" />
                  统计概览
                </h6>
              </div>
              <div className="panel-body d-flex gap-2 flex-wrap">
                <span className="chip">总记录 {formatNumber(stats?.total_records ?? null, 0)}</span>
                <span className="chip">股票数 {formatNumber(stats?.total_stocks ?? null, 0)}</span>
                <span className="chip">最早 {stats?.earliest_time ?? '--'}</span>
                <span className="chip">最新 {stats?.latest_time ?? '--'}</span>
              </div>
            </div>
          </div>
          <div className="col-lg-4">
            <div className="panel h-100">
              <div className="panel-head">
                <h6 className="panel-title">
                  <span className="kicker" />
                  支持的指标
                </h6>
              </div>
              <div className="panel-body d-flex gap-1 flex-wrap">
                {indicators.map((i) => (
                  <span className="chip" key={i.code} title={i.description}>
                    {i.name}
                  </span>
                ))}
              </div>
            </div>
          </div>
          <div className="col-lg-4">
            <div className="panel h-100">
              <div className="panel-head">
                <h6 className="panel-title">
                  <span className="kicker" />
                  指标分布
                </h6>
              </div>
              <div className="panel-body">{statsPieOption ? <EChart option={statsPieOption} height={320} /> : <EmptyState icon="📊" text="暂无统计" />}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
