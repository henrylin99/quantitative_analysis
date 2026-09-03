import { useEffect, useMemo, useRef, useState } from 'react'
import EChart from '../charts/EChart'
import { useTheme } from '../theme/ThemeContext'
import {
  fetchBacktestRunResult,
  fetchBacktestRunStatus,
  fetchFactors,
  fetchModels,
  runMlBacktest,
  type MlBacktestResult,
} from '../api/mlFactor'
import { ErrorState, Loading } from '../components/StateViews'
import { addDaysLocal, formatNumber, formatPercent, pctClass, toLocalDate } from '../utils/format'

const BENCHMARKS = [
  ['000300.SH', '沪深300'],
  ['000905.SH', '中证500'],
  ['000852.SH', '中证1000'],
  ['399006.SZ', '创业板指'],
] as const

const FREQS = [
  ['daily', '每日'],
  ['weekly', '每周'],
  ['monthly', '每月'],
  ['quarterly', '每季'],
] as const

type Status = 'idle' | 'running' | 'done' | 'failed'

export default function MlBacktestPage() {
  const { palette } = useTheme()
  const [models, setModels] = useState<{ model_id: string; model_name: string; model_type: string }[]>([])
  const [factors, setFactors] = useState<{ factor_id: string; factor_name: string; factor_type: string }[]>([])
  const [modelId, setModelId] = useState('')
  const [modelWeight, setModelWeight] = useState(70)
  const [selFactors, setSelFactors] = useState<Set<string>>(new Set())

  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [capital, setCapital] = useState('1000000')
  const [freq, setFreq] = useState('monthly')
  const [topN, setTopN] = useState(20)
  const [commission, setCommission] = useState('0.1')
  const [slippage, setSlippage] = useState('0.05')
  const [benchmark, setBenchmark] = useState('000300.SH')

  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<MlBacktestResult | null>(null)
  const [runId, setRunId] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    const end = new Date()
    setEndDate(toLocalDate(end))
    setStartDate(addDaysLocal(end, -90))
    Promise.all([fetchModels(), fetchFactors()])
      .then(([m, f]) => {
        setModels(m.models ?? [])
        setFactors(f.factors ?? [])
        if ((m.models ?? []).length > 0) setModelId(m.models[0].model_id)
      })
      .catch(() => undefined)
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  const factorWeight = 100 - modelWeight

  const toggleFactor = (id: string) => {
    setSelFactors((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const quickRange = (days: number) => {
    const end = new Date()
    setEndDate(toLocalDate(end))
    setStartDate(addDaysLocal(end, -days))
  }

  const submit = async () => {
    setError(null)
    if (!startDate || !endDate || startDate >= endDate) {
      setError('请设置有效的起止日期（开始 < 结束）')
      return
    }
    if (Number(capital) < 10000) {
      setError('初始资金不可低于 1 万')
      return
    }
    if (selFactors.size === 0 && !modelId) {
      setError('请选择模型或至少一个因子')
      return
    }
    setStatus('running')
    setResult(null)
    setRunId(null)
    const factorList = [...selFactors]
    const strategyConfig: Record<string, unknown> = {
      selection_method: factorList.length > 0 ? 'factor_based' : 'ml_based',
      model_ids: modelId && factorList.length === 0 ? [modelId] : modelId ? [modelId] : [],
      factor_list: factorList,
      factor_weights: Object.fromEntries(factorList.map((f) => [f, 1 / factorList.length])),
      model_weight: modelWeight / 100,
      factor_weight: factorWeight / 100,
      top_n: topN,
      optimization: { method: 'equal_weight', constraints: { max_weight: 0.1, min_weight: 0.01 } },
      commission_rate: (Number(commission) || 0) / 100,
      slippage_rate: (Number(slippage) || 0) / 100,
      benchmark_index: benchmark,
      min_trade_weight: 0.01,
      suspend_policy: 'skip',
      limit_up_down_policy: 'skip',
    }
    try {
      const r = await runMlBacktest({
        strategy_config: strategyConfig,
        start_date: startDate,
        end_date: endDate,
        initial_capital: Number(capital),
        rebalance_frequency: freq,
        mode: 'async',
      })
      if (r.queued && r.run_id) {
        setRunId(r.run_id)
        pollRef.current = setInterval(async () => {
          try {
            const st = await fetchBacktestRunStatus(r.run_id!)
            if (['succeeded', 'success'].includes(st.status ?? '')) {
              if (pollRef.current) clearInterval(pollRef.current)
              const full = await fetchBacktestRunResult(r.run_id!)
              setResult(full)
              setStatus('done')
            } else if (st.status === 'failed') {
              if (pollRef.current) clearInterval(pollRef.current)
              setError(st.message ?? '回测失败')
              setStatus('failed')
            }
          } catch {
            if (pollRef.current) clearInterval(pollRef.current)
            setError('回测状态查询失败')
            setStatus('failed')
          }
        }, 3000)
      } else {
        setResult(r as MlBacktestResult)
        setStatus('done')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '回测提交失败')
      setStatus('failed')
    }
  }

  const pm = result?.performance_metrics

  const returnsOption = useMemo(() => {
    if (!result?.equity_curve?.length) return null
    return {
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => `${((v - 1) * 100).toFixed(2)}%` },
      legend: { top: 0 },
      grid: { left: 60, right: 20, top: 34, bottom: 30 },
      xAxis: { type: 'category', data: result.equity_curve.map((p) => p.date), boundaryGap: false },
      yAxis: { type: 'value', axisLabel: { formatter: (v: number) => `${((v - 1) * 100).toFixed(0)}%` } },
      series: [
        { name: '策略净值', type: 'line', showSymbol: false, data: result.equity_curve.map((p) => p.portfolio), itemStyle: { color: palette.accent }, areaStyle: { color: palette.accent, opacity: 0.1 } },
        { name: '基准净值', type: 'line', showSymbol: false, data: result.equity_curve.map((p) => p.benchmark), itemStyle: { color: palette.text } },
      ],
    }
  }, [result, palette])

  const drawdownOption = useMemo(() => {
    if (!result?.drawdown_series?.length) return null
    return {
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => `${(v * 100).toFixed(2)}%` },
      grid: { left: 60, right: 20, top: 16, bottom: 30 },
      xAxis: { type: 'category', data: result.drawdown_series.map((p) => p.date), boundaryGap: false },
      yAxis: { type: 'value', axisLabel: { formatter: (v: number) => `${(v * 100).toFixed(0)}%` } },
      series: [
        {
          name: '回撤',
          type: 'line',
          showSymbol: false,
          data: result.drawdown_series.map((p) => p.drawdown * 100),
          lineStyle: { color: palette.up },
          areaStyle: { color: palette.up, opacity: 0.18 },
        },
      ],
    }
  }, [result, palette])

  const monthlyOption = useMemo(() => {
    if (!result?.monthly_returns?.length) return null
    return {
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => `${(v * 100).toFixed(2)}%` },
      legend: { top: 0 },
      grid: { left: 60, right: 20, top: 34, bottom: 30 },
      xAxis: { type: 'category', data: result.monthly_returns.map((p) => p.date) },
      yAxis: { type: 'value', axisLabel: { formatter: '{value}%' } },
      series: [
        { name: '策略月收益', type: 'bar', data: result.monthly_returns.map((p) => p.portfolio * 100), itemStyle: { color: (d: { value: number }) => (d.value >= 0 ? palette.up : palette.down) } },
        { name: '基准月收益', type: 'bar', data: result.monthly_returns.map((p) => (p.benchmark != null ? p.benchmark * 100 : null)), itemStyle: { color: palette.text } },
      ],
    }
  }, [result, palette])

  const industryOption = useMemo(() => {
    if (!result?.industry_distribution?.length) return null
    return {
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: { type: 'scroll', bottom: 0 },
      series: [{ type: 'pie', radius: '52%', data: result.industry_distribution.map((d) => ({ name: d.name, value: d.value })) }],
    }
  }, [result])

  const distOption = useMemo(() => {
    if (!result?.returns_distribution?.length) return null
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: 56, right: 20, top: 16, bottom: 30 },
      xAxis: { type: 'category', data: result.returns_distribution.map((d) => `${(d.returns * 100).toFixed(1)}%`), axisLabel: { rotate: 45, fontSize: 10 } },
      yAxis: { type: 'value' },
      series: [{ type: 'bar', barMaxWidth: 14, data: result.returns_distribution.map((d) => d.frequency), itemStyle: { color: palette.violet } }],
    }
  }, [result, palette])

  const rm = result?.risk_metrics

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>组合回测验证</h2>
          <p className="desc">多因子 / 模型混合策略 · 异步执行 · 绩效与风险全指标</p>
        </div>
        <span className="chip">{status === 'running' ? '回测中…' : status === 'done' ? '回测完成' : status === 'failed' ? '回测失败' : '等待回测'}</span>
      </div>

      <div className="panel">
        <div className="panel-body">
          <div className="row g-3">
            <div className="col-lg-2 col-md-3 col-6">
              <label className="form-label">开始日期</label>
              <input type="date" className="form-control" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            </div>
            <div className="col-lg-2 col-md-3 col-6">
              <label className="form-label">结束日期</label>
              <input type="date" className="form-control" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
            </div>
            <div className="col-lg-2 col-md-4 col-6">
              <label className="form-label">快捷区间</label>
              <div className="seg" role="group">
                <button type="button" className="seg-item" onClick={() => quickRange(90)}>
                  近3月
                </button>
                <button type="button" className="seg-item" onClick={() => quickRange(180)}>
                  近6月
                </button>
                <button type="button" className="seg-item" onClick={() => quickRange(365)}>
                  近1年
                </button>
              </div>
            </div>
            <div className="col-lg-2 col-md-4 col-6">
              <label className="form-label">初始资金</label>
              <input type="number" className="form-control" value={capital} min={10000} onChange={(e) => setCapital(e.target.value)} />
            </div>
            <div className="col-lg-2 col-md-4 col-6">
              <label className="form-label">调仓频率</label>
              <select className="form-select" value={freq} onChange={(e) => setFreq(e.target.value)}>
                {FREQS.map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-lg-2 col-md-4 col-6">
              <label className="form-label">持股数量（5-100）</label>
              <input type="number" className="form-control" value={topN} min={5} max={100} onChange={(e) => setTopN(Number(e.target.value))} />
            </div>
            <div className="col-lg-2 col-md-3 col-6">
              <label className="form-label">手续费率%</label>
              <input type="number" className="form-control" value={commission} step={0.01} onChange={(e) => setCommission(e.target.value)} />
            </div>
            <div className="col-lg-2 col-md-3 col-6">
              <label className="form-label">滑点率%</label>
              <input type="number" className="form-control" value={slippage} step={0.01} onChange={(e) => setSlippage(e.target.value)} />
            </div>
            <div className="col-lg-3 col-md-3 col-6">
              <label className="form-label">基准指数</label>
              <select className="form-select" value={benchmark} onChange={(e) => setBenchmark(e.target.value)}>
                {BENCHMARKS.map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="row g-3 mt-1">
            <div className="col-lg-6">
              <div className="p-3 rounded h-100" style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
                <div className="side-group-label">模型策略（权重 {modelWeight}%）</div>
                <select className="form-select mb-2" value={modelId} onChange={(e) => setModelId(e.target.value)}>
                  <option value="">不使用模型</option>
                  {models.map((m) => (
                    <option key={m.model_id} value={m.model_id}>
                      {m.model_name}（{m.model_type}）
                    </option>
                  ))}
                </select>
                <input
                  type="range"
                  className="form-range"
                  min={0}
                  max={100}
                  value={modelWeight}
                  onChange={(e) => setModelWeight(Number(e.target.value))}
                />
              </div>
            </div>
            <div className="col-lg-6">
              <div className="p-3 rounded h-100" style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
                <div className="side-group-label">因子策略（权重 {factorWeight}% · 已选 {selFactors.size}）</div>
                <div style={{ maxHeight: 108, overflowY: 'auto' }}>
                  {factors.slice(0, 40).map((f) => (
                    <label key={f.factor_id} className="d-inline-flex align-items-center gap-1 me-3" style={{ fontSize: 12.5, cursor: 'pointer' }}>
                      <input
                        type="checkbox"
                        className="form-check-input mt-0"
                        checked={selFactors.has(f.factor_id)}
                        onChange={() => toggleFactor(f.factor_id)}
                      />
                      {f.factor_id}
                    </label>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {error && (
            <div className="mt-3">
              <ErrorState message={error} onRetry={submit} />
            </div>
          )}

          <div className="mt-3">
            <button type="button" className="btn btn-primary" disabled={status === 'running'} onClick={submit}>
              {status === 'running' ? '回测中…' : '🏁 开始回测'}
            </button>
          </div>
        </div>
      </div>

      {status === 'running' && (
        <Loading text={runId ? `回测执行中（run ${runId}），每 3 秒轮询状态...` : '提交回测任务...'} />
      )}

      {result && pm && status === 'done' && (
        <>
          <div className="stat-grid">
            <div className="stat">
              <div className="stat-label">总收益率</div>
              <div className={`stat-value ${pctClass(result.total_return * 100)}`}>{formatPercent(result.total_return * 100)}</div>
              <div className="sub">年化 {formatPercent(pm.annual_return * 100)}</div>
            </div>
            <div className="stat">
              <div className="stat-label">最大回撤</div>
              <div className="stat-value text-down">{formatPercent(pm.max_drawdown * 100)}</div>
              <div className="sub">波动率 {formatPercent(pm.volatility * 100)}</div>
            </div>
            <div className="stat">
              <div className="stat-label">夏普比率</div>
              <div className="stat-value">{formatNumber(pm.sharpe_ratio, 2)}</div>
              <div className="sub">胜率 {formatPercent(pm.win_rate * 100)}</div>
            </div>
            <div className="stat">
              <div className="stat-label">回测运行</div>
              <div className="stat-value" style={{ fontSize: 16 }}>{result.run_id ?? runId ?? '--'}</div>
              <div className="sub">
                手续费 {((result.execution_assumptions?.commission_rate ?? 0) * 100).toFixed(2)}% · 滑点{' '}
                {((result.execution_assumptions?.slippage_rate ?? 0) * 100).toFixed(2)}%
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                净值曲线（策略 vs 基准）
              </h6>
            </div>
            <div className="panel-body">{returnsOption ? <EChart option={returnsOption} height={340} /> : <Loading text="暂无净值数据" />}</div>
          </div>

          <div className="row g-3">
            <div className="col-xl-6">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    回撤曲线
                  </h6>
                </div>
                <div className="panel-body">{drawdownOption ? <EChart option={drawdownOption} height={280} /> : <div className="empty-state">暂无数据</div>}</div>
              </div>
            </div>
            <div className="col-xl-6">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    月度收益
                  </h6>
                </div>
                <div className="panel-body">{monthlyOption ? <EChart option={monthlyOption} height={280} /> : <div className="empty-state">暂无数据</div>}</div>
              </div>
            </div>
            <div className="col-xl-6">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    行业分布
                  </h6>
                </div>
                <div className="panel-body">{industryOption ? <EChart option={industryOption} height={300} /> : <div className="empty-state">暂无数据</div>}</div>
              </div>
            </div>
            <div className="col-xl-6">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    收益分布
                  </h6>
                </div>
                <div className="panel-body">{distOption ? <EChart option={distOption} height={300} /> : <div className="empty-state">暂无数据</div>}</div>
              </div>
            </div>
          </div>

          <div className="row g-3">
            <div className="col-xl-7">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    持仓明细
                    <span className="chip">{result.positions.length} 只</span>
                  </h6>
                </div>
                <div className="panel-body tight table-container" style={{ maxHeight: 360 }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>代码</th>
                        <th>名称</th>
                        <th className="num">权重</th>
                        <th>持有期间</th>
                        <th className="num">收益率</th>
                        <th className="num">贡献度</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.positions.map((p) => (
                        <tr key={p.code}>
                          <td>
                            <code>{p.code}</code>
                          </td>
                          <td>{p.name ?? '--'}</td>
                          <td className="num">{formatPercent(p.weight * 100)}</td>
                          <td>{p.period ?? '--'}</td>
                          <td className="num">{p.return != null ? formatPercent(p.return * 100) : '--'}</td>
                          <td className="num">{p.contribution != null ? formatPercent(p.contribution * 100) : '--'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
            <div className="col-xl-5">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    风险指标
                  </h6>
                </div>
                <div className="panel-body tight table-container">
                  <table className="data-table kv-table">
                    <tbody>
                      {(
                        [
                          ['VaR 95%', rm?.var_95],
                          ['CVaR 95%', rm?.cvar_95],
                          ['Beta', rm?.beta],
                          ['Alpha', rm?.alpha],
                          ['信息比率', rm?.information_ratio],
                          ['卡尔马比率', rm?.calmar_ratio],
                        ] as const
                      ).map(([label, v]) => (
                        <tr key={label}>
                          <td>{label}</td>
                          <td className="num">
                            {v == null ? '--' : label.includes('%') || label === 'VaR 95%' || label === 'CVaR 95%' || label === 'Alpha' ? formatPercent(v * 100) : formatNumber(v, 2)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
