import { useEffect, useMemo, useState } from 'react'
import { fetchStockOptions, runBacktest } from '../api/analysis'
import type { BacktestResultData, StrategyType } from '../api/types'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import EquityCurve from '../charts/EquityCurve'
import { formatNumber, formatPercent, pctClass, toLocalDate } from '../utils/format'

interface StrategyMeta {
  type: StrategyType
  label: string
  description: string
  params: { key: string; label: string; defaultValue: number; min: number; max: number; step: number }[]
}

const STRATEGIES: StrategyMeta[] = [
  {
    type: 'ma_cross',
    label: '均线交叉',
    description: '短期均线上穿长期均线（金叉）买入，下穿（死叉）卖出。',
    params: [
      { key: 'ma_short', label: '短期均线', defaultValue: 5, min: 1, max: 30, step: 1 },
      { key: 'ma_long', label: '长期均线', defaultValue: 20, min: 10, max: 100, step: 1 },
    ],
  },
  {
    type: 'macd',
    label: 'MACD',
    description: 'DIF 上穿 DEA（金叉）买入，下穿（死叉）卖出。',
    params: [
      { key: 'fast', label: '快线周期', defaultValue: 12, min: 5, max: 30, step: 1 },
      { key: 'slow', label: '慢线周期', defaultValue: 26, min: 15, max: 50, step: 1 },
      { key: 'signal', label: '信号周期', defaultValue: 9, min: 5, max: 20, step: 1 },
    ],
  },
  {
    type: 'kdj',
    label: 'KDJ',
    description: 'KDJ 低位金叉买入，超买区死叉卖出。',
    params: [
      { key: 'period', label: '周期', defaultValue: 9, min: 5, max: 20, step: 1 },
      { key: 'overbought', label: '超买阈值', defaultValue: 80, min: 70, max: 90, step: 1 },
      { key: 'oversold', label: '超卖阈值', defaultValue: 20, min: 10, max: 30, step: 1 },
    ],
  },
  {
    type: 'rsi',
    label: 'RSI',
    description: 'RSI 跌破超卖阈值买入，升破超买阈值卖出。',
    params: [
      { key: 'period', label: '周期', defaultValue: 14, min: 6, max: 30, step: 1 },
      { key: 'overbought', label: '超买阈值', defaultValue: 70, min: 60, max: 80, step: 1 },
      { key: 'oversold', label: '超卖阈值', defaultValue: 30, min: 20, max: 40, step: 1 },
    ],
  },
  {
    type: 'bollinger',
    label: '布林带',
    description: '价格触及下轨买入，触及上轨卖出。',
    params: [
      { key: 'period', label: '周期', defaultValue: 20, min: 10, max: 50, step: 1 },
      { key: 'std_dev', label: '标准差倍数', defaultValue: 2, min: 1, max: 3, step: 0.1 },
    ],
  },
]

type Status = 'idle' | 'running' | 'done' | 'failed'

const STATUS_META: Record<Status, { label: string; className: string }> = {
  idle: { label: '等待回测', className: 'chip' },
  running: { label: '回测中...', className: 'chip' },
  done: { label: '回测完成', className: 'delta down' },
  failed: { label: '回测失败', className: 'delta up' },
}

export default function BacktestPage() {
  const [stocks, setStocks] = useState<{ ts_code: string; symbol: string; name: string }[]>([])
  const [tsCode, setTsCode] = useState('')
  const [strategyType, setStrategyType] = useState<'' | StrategyType>('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [initialCapital, setInitialCapital] = useState('100000')
  const [commissionRate, setCommissionRate] = useState('0.1')
  const [params, setParams] = useState<Record<string, number>>({})
  const [status, setStatus] = useState<Status>('idle')
  const [formError, setFormError] = useState<string | null>(null)
  const [runError, setRunError] = useState<string | null>(null)
  const [result, setResult] = useState<BacktestResultData | null>(null)

  useEffect(() => {
    const end = new Date()
    const start = new Date()
    start.setFullYear(end.getFullYear() - 1)
    setEndDate(toLocalDate(end))
    setStartDate(toLocalDate(start))

    fetchStockOptions()
      .then((data) => setStocks(data.stocks))
      .catch(() => setStocks([]))
  }, [])

  const strategyMeta = useMemo(() => STRATEGIES.find((s) => s.type === strategyType) ?? null, [strategyType])

  useEffect(() => {
    if (!strategyMeta) return
    const defaults: Record<string, number> = {}
    for (const p of strategyMeta.params) defaults[p.key] = p.defaultValue
    setParams(defaults)
  }, [strategyMeta])

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault()
    if (!tsCode || !strategyType) {
      setFormError('请选择股票与策略类型')
      return
    }
    setFormError(null)
    setRunError(null)
    setStatus('running')
    setResult(null)
    try {
      const data = await runBacktest({
        ts_code: tsCode,
        strategy_type: strategyType,
        start_date: startDate,
        end_date: endDate,
        initial_capital: Number(initialCapital) || 100000,
        commission_rate: (Number(commissionRate) || 0) / 100,
        params,
      })
      setResult(data)
      setStatus('done')
    } catch (err) {
      setRunError(err instanceof Error ? err.message : '回测请求失败')
      setStatus('failed')
    }
  }

  const handleReset = () => {
    const end = new Date()
    const start = new Date()
    start.setFullYear(end.getFullYear() - 1)
    setTsCode('')
    setStrategyType('')
    setStartDate(toLocalDate(start))
    setEndDate(toLocalDate(end))
    setInitialCapital('100000')
    setCommissionRate('0.1')
    setParams({})
    setStatus('idle')
    setResult(null)
    setFormError(null)
    setRunError(null)
  }

  const perf = result?.performance

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>回测验证</h2>
          <p className="desc">单股票策略回测：均线 / MACD / KDJ / RSI / 布林带</p>
        </div>
        <span className={STATUS_META[status].className}>{STATUS_META[status].label}</span>
      </div>

      <div className="panel">
        <div className="panel-body">
          <form onSubmit={handleSubmit}>
            <div className="row g-3">
              <div className="col-xl-3 col-md-6">
                <label className="form-label">股票 *</label>
                <select className="form-select" value={tsCode} onChange={(e) => setTsCode(e.target.value)}>
                  <option value="">请选择股票</option>
                  {stocks.map((s) => (
                    <option key={s.ts_code} value={s.ts_code}>
                      {s.symbol} - {s.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="col-xl-3 col-md-6">
                <label className="form-label">策略类型 *</label>
                <select
                  className="form-select"
                  value={strategyType}
                  onChange={(e) => setStrategyType(e.target.value as '' | StrategyType)}
                >
                  <option value="">请选择策略</option>
                  {STRATEGIES.map((s) => (
                    <option key={s.type} value={s.type}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="col-xl-3 col-md-6">
                <label className="form-label">开始日期</label>
                <input type="date" className="form-control" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
              </div>
              <div className="col-xl-3 col-md-6">
                <label className="form-label">结束日期</label>
                <input type="date" className="form-control" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
              </div>
              <div className="col-xl-3 col-md-6">
                <label className="form-label">初始资金（元）</label>
                <input
                  type="number"
                  className="form-control"
                  value={initialCapital}
                  min={10000}
                  step={1000}
                  onChange={(e) => setInitialCapital(e.target.value)}
                />
              </div>
              <div className="col-xl-3 col-md-6">
                <label className="form-label">手续费率（%）</label>
                <input
                  type="number"
                  className="form-control"
                  value={commissionRate}
                  min={0}
                  max={1}
                  step={0.01}
                  onChange={(e) => setCommissionRate(e.target.value)}
                />
              </div>
            </div>

            {strategyMeta && (
              <>
                <div className="alert-note mt-3">策略说明：{strategyMeta.description}</div>
                <div className="row g-3 mt-1">
                  {strategyMeta.params.map((p) => (
                    <div className="col-xl-3 col-md-6" key={p.key}>
                      <label className="form-label">
                        {p.label}（{p.min} ~ {p.max}）
                      </label>
                      <input
                        type="number"
                        className="form-control"
                        value={params[p.key] ?? p.defaultValue}
                        min={p.min}
                        max={p.max}
                        step={p.step}
                        onChange={(e) => setParams({ ...params, [p.key]: Number(e.target.value) })}
                      />
                    </div>
                  ))}
                </div>
              </>
            )}

            {formError && (
              <div className="mt-3">
                <ErrorState message={formError} />
              </div>
            )}

            <div className="mt-3 d-flex gap-2">
              <button type="submit" className="btn btn-primary" disabled={status === 'running'}>
                {status === 'running' ? '回测中…' : '🚀 开始回测'}
              </button>
              <button type="button" className="btn btn-outline-secondary" onClick={handleReset}>
                重置
              </button>
            </div>
          </form>
        </div>
      </div>

      {status === 'running' && <Loading text="回测进行中..." />}
      {runError && <ErrorState message={runError} onRetry={() => handleSubmit()} />}

      {perf && result && (
        <>
          <div className="stat-grid">
            <div className="stat">
              <div className="stat-label">累计收益</div>
              <div className={`stat-value ${pctClass(perf.total_return * 100)}`}>{formatPercent(perf.total_return * 100)}</div>
              <div className="sub">年化 {formatPercent(perf.annual_return * 100)}</div>
            </div>
            <div className="stat">
              <div className="stat-label">夏普比率</div>
              <div className="stat-value">{formatNumber(perf.sharpe_ratio, 2)}</div>
              <div className="sub">最大回撤 {formatPercent(-Math.abs(perf.max_drawdown) * 100)}</div>
            </div>
            <div className="stat">
              <div className="stat-label">胜率</div>
              <div className="stat-value">{formatPercent(perf.win_rate * 100)}</div>
              <div className="sub">
                {perf.winning_trades} / {perf.total_trades} 笔盈利 · 平均持仓 {formatNumber(perf.avg_holding_days, 1)} 天
              </div>
            </div>
            <div className="stat">
              <div className="stat-label">期末资金</div>
              <div className="stat-value">¥{formatNumber(perf.final_capital, 2)}</div>
              <div className="sub">
                成本 ¥{formatNumber(perf.total_commission, 2)} · 基准{' '}
                <span className={pctClass(perf.benchmark_return * 100)}>{formatPercent(perf.benchmark_return * 100)}</span>
              </div>
            </div>
          </div>

          {result.daily_values && result.daily_values.length > 0 && (
            <div className="panel">
              <div className="panel-head">
                <h6 className="panel-title">
                  <span className="kicker" />
                  资金曲线
                  <span className="chip">{result.daily_values.length} 个交易日</span>
                </h6>
              </div>
              <div className="panel-body">
                <EquityCurve dailyValues={result.daily_values} />
              </div>
            </div>
          )}

          <div className="panel">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                回测配置
                <span className="chip">{STRATEGIES.find((s) => s.type === result.config.strategy_type)?.label ?? result.config.strategy_type}</span>
              </h6>
            </div>
            <div className="panel-body d-flex gap-2 flex-wrap">
              <span className="chip">股票 · {result.config.ts_code}</span>
              <span className="chip">
                期间 · {result.config.start_date} ~ {result.config.end_date}
              </span>
              <span className="chip">初始资金 · ¥{formatNumber(result.config.initial_capital, 0)}</span>
              <span className="chip">波动率 · {formatPercent(perf.volatility * 100)}</span>
              {Object.entries(result.config.params ?? {}).map(([k, v]) => (
                <span className="chip" key={k}>
                  {k} = {v}
                </span>
              ))}
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                交易记录
                <span className="chip">最近 20 笔 · 展示前 10 笔</span>
              </h6>
            </div>
            <div className="panel-body tight table-container" style={{ maxHeight: 420 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>日期</th>
                    <th>操作</th>
                    <th className="num">价格</th>
                    <th className="num">数量</th>
                    <th className="num">金额</th>
                    <th className="num">收益率</th>
                  </tr>
                </thead>
                <tbody>
                  {result.trades.slice(0, 10).map((trade, index) => (
                    <tr key={`${trade.date}-${trade.action}-${index}`}>
                      <td>{trade.date}</td>
                      <td>
                        <span className={`badge ${trade.action === 'buy' ? 'text-bg-danger' : 'text-bg-success'}`}>
                          {trade.action === 'buy' ? '买入' : '卖出'}
                        </span>
                      </td>
                      <td className="num">{formatNumber(trade.price, 2)}</td>
                      <td className="num">{trade.quantity}</td>
                      <td className="num">{formatNumber(trade.amount, 2)}</td>
                      <td className={`num ${pctClass(trade.return_rate !== null ? trade.return_rate * 100 : null)}`}>
                        {trade.return_rate !== null ? formatPercent(trade.return_rate * 100) : '--'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {result.trades.length === 0 && <EmptyState icon="🧾" text="回测期间没有产生交易" />}
            </div>
          </div>

          <div className="empty-state" style={{ paddingTop: 20 }}>
            <div className="hint">历史回测不代表未来表现，不构成投资建议；交易记录已计入手续费与印花税；请避免参数过拟合。</div>
          </div>
        </>
      )}
    </div>
  )
}
