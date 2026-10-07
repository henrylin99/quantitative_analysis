import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { runBacktest, runBacktestOptimize } from '../api/analysis'
import type { OptimizeResult } from '../api/analysis'
import { fetchTickerSearch, type TickerSearchItem } from '../api/market'
import type { BacktestResultData, StrategyType } from '../api/types'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { useDebouncedValue } from '../utils/hooks'
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

/** 6 位代码归一化（600000.SH 直用；裸 6 位按交易所规则推断后缀） */
function normalizeCode(input: string): string | null {
  const text = input.trim().toUpperCase()
  if (/^\d{6}\.(SH|SZ|BJ)$/.test(text)) return text
  if (/^\d{6}$/.test(text)) {
    if (text.startsWith('6')) return `${text}.SH`
    if (text.startsWith('8') || text.startsWith('4')) return `${text}.BJ`
    return `${text}.SZ`
  }
  return null
}

const SUGGEST_BOX: React.CSSProperties = {
  position: 'absolute',
  top: '100%',
  left: 0,
  right: 0,
  zIndex: 30,
  marginTop: 4,
  background: 'var(--surface-2)',
  border: '1px solid var(--border-strong)',
  borderRadius: 'var(--radius-sm)',
  boxShadow: '0 10px 28px rgba(2, 6, 23, 0.35)',
  overflow: 'hidden',
}

const SUGGEST_ROW: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 8,
  width: '100%',
  padding: '7px 12px',
  background: 'transparent',
  border: 'none',
  color: 'var(--text)',
  textAlign: 'left',
  fontSize: 13,
  cursor: 'pointer',
}

const SUGGEST_HINT: React.CSSProperties = {
  padding: '7px 12px',
  color: 'var(--text-faint)',
  fontSize: 12,
}

const rowHover = {
  enter: (e: React.MouseEvent<HTMLButtonElement>) => {
    e.currentTarget.style.background = 'var(--surface-3)'
  },
  leave: (e: React.MouseEvent<HTMLButtonElement>) => {
    e.currentTarget.style.background = 'transparent'
  },
}

/**
 * 股票手工输入 + 模糊检索组合框：代码 / 名称均可匹配（≥2 字符防抖联想），
 * 直接输入 6 位代码不经检索直接可用。选中后以 chip 展示，可点「更换」重选。
 */
function StockSearchInput({
  value,
  name,
  onPick,
  onClear,
}: {
  value: string
  name: string
  onPick: (tsCode: string, stockName: string) => void
  onClear: () => void
}) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<TickerSearchItem[]>([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState(false)
  const boxRef = useRef<HTMLDivElement>(null)
  const debounced = useDebouncedValue(query, 300)
  const direct = normalizeCode(query)

  useEffect(() => {
    const keyword = debounced.trim()
    if (keyword.length < 2 || normalizeCode(keyword)) {
      setItems([])
      setLoading(false)
      return
    }
    let alive = true
    setLoading(true)
    setLoadError(false)
    fetchTickerSearch(keyword, 8)
      .then((r) => {
        if (alive) setItems(r.items.filter((x) => x.ts_code && x.ts_code !== value))
      })
      .catch(() => {
        if (alive) {
          setItems([])
          setLoadError(true)
        }
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [debounced, value])

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  const pick = (tsCode: string, stockName: string) => {
    onPick(tsCode, stockName)
    setQuery('')
    setOpen(false)
  }

  const dropdownOpen = open && query.trim().length >= 2

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== 'Enter' || !dropdownOpen) return
    e.preventDefault() // 下拉展示时 Enter 采纳第一项，避免误触发表单提交
    if (direct) pick(direct, '')
    else if (items.length > 0) pick(items[0].ts_code, items[0].name ?? '')
  }

  if (value) {
    return (
      <div className="d-flex align-items-center gap-2">
        <span className="chip">{name ? `${name} · ${value}` : value}</span>
        <button type="button" className="btn btn-outline-secondary btn-sm" onClick={onClear}>
          更换
        </button>
      </div>
    )
  }

  return (
    <div ref={boxRef} style={{ position: 'relative' }}>
      <input
        type="text"
        className="form-control"
        value={query}
        placeholder="代码或名称，如 600519 / 贵州茅台"
        autoComplete="off"
        onChange={(e) => {
          setQuery(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={handleKeyDown}
      />
      {dropdownOpen && (
        <div style={SUGGEST_BOX}>
          {direct && (
            <button type="button" style={SUGGEST_ROW} onMouseEnter={rowHover.enter} onMouseLeave={rowHover.leave} onClick={() => pick(direct, '')}>
              <span>直接使用 {direct}</span>
              <span className="num" style={{ color: 'var(--text-faint)', fontSize: 11 }}>
                不经检索
              </span>
            </button>
          )}
          {loading ? (
            <div style={SUGGEST_HINT}>搜索中…</div>
          ) : items.length === 0 && !direct ? (
            <div style={SUGGEST_HINT}>
              {loadError ? '检索服务暂不可用，可直接输入 6 位代码' : '没有匹配的 A 股标的'}
            </div>
          ) : (
            items.map((item) => (
              <button
                key={item.ts_code}
                type="button"
                style={SUGGEST_ROW}
                onMouseEnter={rowHover.enter}
                onMouseLeave={rowHover.leave}
                onClick={() => pick(item.ts_code, item.name ?? '')}
              >
                <span>{item.name ?? item.ts_code}</span>
                <span className="num" style={{ color: 'var(--text-faint)', fontSize: 11 }}>
                  {item.ts_code}
                </span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}


const STATUS_META: Record<Status, { label: string; className: string }> = {
  idle: { label: '等待回测', className: 'chip' },
  running: { label: '回测中...', className: 'chip' },
  done: { label: '回测完成', className: 'delta down' },
  failed: { label: '回测失败', className: 'delta up' },
}

export default function BacktestPage() {
  const [tsCode, setTsCode] = useState('')
  const [stockName, setStockName] = useState('')
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

  const [searchParams] = useSearchParams()

  /** 选中股票：缺名称（直输代码 / URL 预选）时用检索接口补一次显示名，失败不阻塞 */
  const applyStock = (code: string, name: string) => {
    setTsCode(code)
    if (name) {
      setStockName(name)
      return
    }
    setStockName('')
    fetchTickerSearch(code, 5)
      .then((r) => {
        const hit = r.items.find((x) => x.ts_code === code)
        if (hit?.name) setStockName(hit.name)
      })
      .catch(() => undefined)
  }

  useEffect(() => {
    const end = new Date()
    const start = new Date()
    start.setFullYear(end.getFullYear() - 1)
    setEndDate(toLocalDate(end))
    setStartDate(toLocalDate(start))

    // 旧版契约：/backtest?stock=CODE 预选股票（个股详情页跳转入口）
    const preset = searchParams.get('stock')?.trim().toUpperCase()
    if (preset) applyStock(preset, '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
      setFormError('请输入股票（代码或名称检索）并选择策略类型')
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
    setStockName('')
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
                <StockSearchInput
                  value={tsCode}
                  name={stockName}
                  onPick={(code, name) => applyStock(code, name)}
                  onClear={() => {
                    setTsCode('')
                    setStockName('')
                  }}
                />
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

      <OptimizePanel tsCode={tsCode} strategyType={strategyType} startDate={startDate} endDate={endDate} />

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
              <span className="chip">
                股票 · {stockName ? `${stockName} ` : ''}
                {result.config.ts_code}
              </span>
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

// ================= 参数寻优（grid / walk_forward） =================

const OPTIMIZEABLE = ['ma_cross', 'kdj', 'rsi']

function OptimizePanel({
  tsCode,
  strategyType,
  startDate,
  endDate,
}: {
  tsCode: string
  strategyType: '' | StrategyType
  startDate: string
  endDate: string
}) {
  const [mode, setMode] = useState<'grid' | 'walk_forward'>('walk_forward')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<OptimizeResult | null>(null)

  const run = async () => {
    if (!tsCode || !strategyType || !startDate || !endDate) {
      setError('请先在上方选择股票、策略与日期区间')
      return
    }
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const r = await runBacktestOptimize({
        ts_code: tsCode,
        strategy_type: strategyType,
        start_date: startDate,
        end_date: endDate,
        mode,
      })
      setResult(r)
    } catch (e) {
      setError(e instanceof Error ? e.message : '寻优请求失败')
    } finally {
      setBusy(false)
    }
  }

  const unsupported = strategyType !== '' && !OPTIMIZEABLE.includes(strategyType)

  return (
    <div className="panel">
      <div className="panel-head d-flex justify-content-between align-items-center flex-wrap gap-2">
        <h6 className="panel-title">
          <span className="kicker" />
          参数寻优（当前股票 / 策略 / 日期区间）
        </h6>
        <div className="d-flex align-items-center gap-2">
          <div className="seg">
            <button type="button" className={`seg-item ${mode === 'walk_forward' ? 'active' : ''}`} onClick={() => setMode('walk_forward')}>
              滚动样本外
            </button>
            <button type="button" className={`seg-item ${mode === 'grid' ? 'active' : ''}`} onClick={() => setMode('grid')}>
              网格搜索
            </button>
          </div>
          <button type="button" className="btn btn-primary btn-sm" disabled={busy || unsupported} onClick={run}>
            {busy ? '寻优中…' : '开始寻优'}
          </button>
        </div>
      </div>
      <div className="panel-body tight">
        <div className="hint mb-2" style={{ fontSize: 12, color: 'var(--text-faint)' }}>
          {unsupported
            ? '该策略的轨道值来自预存技术因子，无可调参数，暂不支持寻优（支持：均线交叉 / KDJ / RSI）。'
            : mode === 'walk_forward'
              ? '滚动样本外：IS 窗内网格选参 → 紧随 OOS 窗验证 → 逐窗前推。OOS 显著差于 IS 即过拟合信号，这是可信的参数结论来源。'
              : '全样本网格搜索：所有组合在同一数据上排名，结果偏乐观，仅用于了解参数敏感度。'}
        </div>
        {error && <ErrorState message={error} />}
        {result?.mode === 'grid' && <GridResult result={result} />}
        {result?.mode === 'walk_forward' && <WalkForwardResult result={result} />}
      </div>
    </div>
  )
}

const fmtParams = (p: Record<string, number>) =>
  Object.entries(p)
    .map(([k, v]) => `${k}=${v}`)
    .join(', ')

function GridResult({ result }: { result: OptimizeResult }) {
  const rows = (result.results ?? []).filter((r) => r.valid).slice(0, 10)
  return (
    <>
      {result.best && (
        <div className="alert-note py-1 mb-2" style={{ fontSize: 12.5 }}>
          最优（按 {result.metric}）：{fmtParams(result.best.params)} · 收益{' '}
          {formatPercent((result.best.total_return ?? 0) * 100)} · 夏普 {formatNumber(result.best.sharpe_ratio ?? 0, 2)} · 交易{' '}
          {result.best.total_trades} 笔
        </div>
      )}
      <table className="data-table">
        <thead>
          <tr>
            <th>排名</th>
            <th>参数</th>
            <th className="num">累计收益</th>
            <th className="num">夏普</th>
            <th className="num">最大回撤</th>
            <th className="num">胜率</th>
            <th className="num">交易数</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td>{i + 1}</td>
              <td style={{ fontSize: 12 }}>{fmtParams(r.params)}</td>
              <td className={`num ${pctClass((r.total_return ?? 0) * 100)}`}>{formatPercent((r.total_return ?? 0) * 100)}</td>
              <td className="num">{formatNumber(r.sharpe_ratio ?? 0, 2)}</td>
              <td className="num">{formatPercent(-Math.abs(r.max_drawdown ?? 0) * 100)}</td>
              <td className="num">{formatPercent((r.win_rate ?? 0) * 100)}</td>
              <td className="num">{r.total_trades}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {result.note && <div className="text-faint mt-2" style={{ fontSize: 11.5 }}>{result.note}</div>}
    </>
  )
}

function WalkForwardResult({ result }: { result: OptimizeResult }) {
  const s = result.summary
  if (!s) return null
  return (
    <>
      <div className="d-flex gap-2 flex-wrap mb-2">
        <span className="chip">窗口数 · {s.n_windows}</span>
        <span className="chip">OOS 正收益窗口 · {s.oos_hit_rate != null ? formatPercent(s.oos_hit_rate * 100) : '--'}</span>
        <span className={`chip`}>OOS 链式收益 · {s.oos_chained_return != null ? formatPercent(s.oos_chained_return * 100) : '--'}</span>
        <span className="chip">OOS 均值 · {s.oos_mean_return != null ? formatPercent(s.oos_mean_return * 100) : '--'}</span>
        <span className="chip">IS 平均{result.metric === 'sharpe_ratio' ? '夏普' : '收益'} · {s.is_mean_metric != null ? formatNumber(s.is_mean_metric, 2) : '--'}</span>
      </div>
      {result.param_stability && Object.keys(result.param_stability).length > 0 && (
        <div className="d-flex gap-2 flex-wrap mb-2" style={{ fontSize: 12 }}>
          {Object.entries(result.param_stability).map(([k, vals]) => (
            <span key={k} className="text-faint">
              {k}：
              {vals.map((v) => `${v.value}×${v.count}`).join(' / ')}
            </span>
          ))}
        </div>
      )}
      <table className="data-table">
        <thead>
          <tr>
            <th>IS 区间</th>
            <th>OOS 区间</th>
            <th>选中参数</th>
            <th className="num">IS {result.metric === 'sharpe_ratio' ? '夏普' : '收益'}</th>
            <th className="num">OOS 收益</th>
            <th className="num">OOS 超额</th>
            <th className="num">OOS 交易</th>
          </tr>
        </thead>
        <tbody>
          {(result.windows ?? []).map((w, i) => {
            const excess = w.oos_total_return != null && w.oos_benchmark_return != null ? w.oos_total_return - w.oos_benchmark_return : null
            return (
              <tr key={i}>
                <td style={{ fontSize: 12, whiteSpace: 'nowrap' }}>{w.is_start} ~ {w.is_end}</td>
                <td style={{ fontSize: 12, whiteSpace: 'nowrap' }}>{w.oos_start} ~ {w.oos_end}</td>
                <td style={{ fontSize: 12 }}>{fmtParams(w.best_params)}</td>
                <td className="num">{result.metric === 'sharpe_ratio' ? formatNumber(w.is_metric, 2) : formatPercent((w.is_total_return ?? 0) * 100)}</td>
                <td className={`num ${pctClass((w.oos_total_return ?? 0) * 100)}`}>
                  {w.oos_total_return != null ? formatPercent(w.oos_total_return * 100) : '--'}
                </td>
                <td className={`num ${excess != null ? pctClass(excess * 100) : ''}`}>
                  {excess != null ? formatPercent(excess * 100) : '--'}
                </td>
                <td className="num">{w.oos_trades ?? '--'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {result.note && <div className="text-faint mt-2" style={{ fontSize: 11.5 }}>{result.note}</div>}
    </>
  )
}
