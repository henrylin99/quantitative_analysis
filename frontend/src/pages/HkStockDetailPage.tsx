import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import CandleChart from '../charts/candle/CandleChart'
import { fetchHkStock, fetchHkStockHistory, type HkHistoryBar, type HkStockRow } from '../api/hkStock'
import { ErrorState, Loading } from '../components/StateViews'

const RANGES = [
  { key: '3m', label: '3月' },
  { key: '6m', label: '6月' },
  { key: '1y', label: '1年' },
  { key: '2y', label: '2年' },
] as const

const MA_OVERLAYS = [
  { key: 'ma5', color: '#fbbf24', label: 'MA5' },
  { key: 'ma20', color: '#4f93e7', label: 'MA20' },
  { key: 'ma60', color: '#a855f7', label: 'MA60' },
] as const

/** 形态标志 → 中文名（移植自 hk_stock_screener patternLabels） */
const PATTERN_LABELS: Record<string, string> = {
  pattern_bull_candle: '阳线',
  pattern_bear_candle: '阴线',
  pattern_hammer: '锤子线',
  pattern_shooting_star: '射击之星',
  pattern_doji: '十字星',
  pattern_long_upper_shadow: '长上影',
  pattern_long_lower_shadow: '长下影',
  pattern_bullish_engulfing: '看涨吞没',
  pattern_bearish_engulfing: '看跌吞没',
  pattern_inside_bar: '孕线',
  pattern_three_white_soldiers: '三白兵',
  pattern_three_black_crows: '三只乌鸦',
  pattern_ma_bull: '均线多头',
  pattern_trend_confirm: '趋势确认',
  pattern_pullback_hold: '回踩不破',
  pattern_double_bottom: '双底',
  pattern_platform_breakout: '平台突破',
  pattern_false_breakout: '假突破',
  pattern_volume_breakout: '放量突破',
  pattern_volume_shrink_pullback: '缩量回踩',
  pattern_volatility_contraction: '波动收缩',
  pattern_volatility_expansion: '波动扩张',
  break_high_20: '突破20日高点',
  break_high_60: '突破60日高点',
  consec_up_3: '连续上涨3日',
  consec_up_5: '连续上涨5日',
}

type Fmt = 'price' | 'pct' | 'pct_point' | 'ratio' | 'count' | 'money' | 'flag' | 'score' | 'raw'

interface FieldDef {
  key: string
  label: string
  format: Fmt
}

interface FieldGroup {
  title: string
  fields: FieldDef[]
}

const GROUPS: FieldGroup[] = [
  {
    title: '技术指标',
    fields: [
      { key: 'ma5', label: 'MA5', format: 'price' },
      { key: 'ma10', label: 'MA10', format: 'price' },
      { key: 'ma20', label: 'MA20', format: 'price' },
      { key: 'ma60', label: 'MA60', format: 'price' },
      { key: 'ret_1d', label: '1日涨幅', format: 'pct' },
      { key: 'ret_5d', label: '5日涨幅', format: 'pct' },
      { key: 'ret_20d', label: '20日涨幅', format: 'pct' },
      { key: 'vol_ratio_5', label: '量比(5日)', format: 'ratio' },
      { key: 'amplitude', label: '振幅', format: 'ratio' },
      { key: 'body_ratio', label: '实体占比', format: 'ratio' },
      { key: 'upper_shadow_ratio', label: '上影线占比', format: 'ratio' },
      { key: 'lower_shadow_ratio', label: '下影线占比', format: 'ratio' },
    ],
  },
  {
    title: '财务指标',
    fields: [
      { key: 'forward_pe', label: '前瞻市盈率', format: 'ratio' },
      { key: 'trailing_pe', label: '静态市盈率', format: 'ratio' },
      { key: 'price_to_book', label: '市净率', format: 'ratio' },
      { key: 'peg_ratio', label: 'PEG', format: 'ratio' },
      { key: 'ps_ratio', label: '市销率', format: 'ratio' },
      { key: 'roe', label: 'ROE', format: 'pct' },
      { key: 'roa', label: 'ROA', format: 'pct' },
      { key: 'profit_margin', label: '利润率', format: 'pct' },
      { key: 'operating_margin', label: '营业利润率', format: 'pct' },
      { key: 'revenue_growth', label: '营收增长', format: 'pct' },
      { key: 'earnings_growth', label: '盈利增长', format: 'pct' },
      { key: 'debt_to_equity', label: '负债权益比', format: 'ratio' },
      { key: 'current_ratio', label: '流动比率', format: 'ratio' },
      { key: 'dividend_yield', label: '股息率', format: 'pct_point' },
      { key: 'dividend_rate', label: '每股股息', format: 'price' },
    ],
  },
  {
    title: '风险指标',
    fields: [
      { key: 'risk_ma20_dev', label: 'MA20乖离率', format: 'ratio' },
      { key: 'risk_ma60_dev', label: 'MA60乖离率', format: 'ratio' },
      { key: 'risk_dd_20d', label: '20日回撤', format: 'ratio' },
      { key: 'risk_vol_20d', label: '20日波动率', format: 'pct_point' },
    ],
  },
]

function fmtPct(v: number | null | undefined): string {
  if (v == null) return '--'
  const p = v * 100
  return `${p >= 0 ? '+' : ''}${p.toFixed(2)}%`
}

function fmtCount(v: number | null | undefined): string {
  if (v == null) return '--'
  if (v >= 1e12) return `${(v / 1e12).toFixed(2)}万亿`
  if (v >= 1e8) return `${(v / 1e8).toFixed(2)}亿`
  if (v >= 1e4) return `${(v / 1e4).toFixed(2)}万`
  return `${v}`
}

function fmt(v: unknown, f: Fmt): string {
  if (v == null) return '--'
  const n = v as number
  switch (f) {
    case 'price':
      return n.toFixed(2)
    case 'pct':
      return fmtPct(n)
    // 字段本身已是百分数（yfinance dividendYield、日波动率%），直接补 % 不再乘 100
    case 'pct_point':
      return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`
    case 'ratio':
      return n.toFixed(2)
    case 'count':
      return fmtCount(n)
    case 'money':
      return fmtCount(n)
    case 'flag':
      return v === 1 ? '✓' : '✗'
    case 'score':
      return String(v)
    default:
      return String(v)
  }
}

/** 涨跌色（红涨绿跌）；pct/score 按正负，flag 按命中 */
function valClass(v: unknown, f: Fmt): string {
  if (v == null) return ''
  if (f === 'pct' || f === 'score') {
    const n = f === 'pct' ? (v as number) * 100 : (v as number)
    if (n > 0) return 'text-up'
    if (n < 0) return 'text-down'
    return ''
  }
  if (f === 'ratio') {
    const n = v as number
    if (n > 0) return 'text-up'
    if (n < 0) return 'text-down'
  }
  if (f === 'flag') return v === 1 ? 'text-up' : ''
  return ''
}

function toBarTime(day: string): number {
  return Math.floor(new Date(day).getTime() / 1000)
}

/** 港股详情：行情摘要 + K 线 + 技术指标/财务/风险字段（移植自 hk_stock_screener 详情抽屉与技术面板） */
export default function HkStockDetailPage() {
  const { symbol = '' } = useParams()
  const [stock, setStock] = useState<HkStockRow | null>(null)
  const [bars, setBars] = useState<HkHistoryBar[]>([])
  const [range, setRange] = useState<string>('6m')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    Promise.all([fetchHkStock(symbol), fetchHkStockHistory(symbol, range)])
      .then(([row, history]) => {
        if (cancelled) return
        setStock(row)
        setBars(history.bars)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : '加载港股详情失败')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [symbol, range])

  const chartBars = useMemo(
    () =>
      bars.map((b) => ({
        time: toBarTime(b.day),
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
        volume: b.volume,
      })),
    [bars],
  )

  const overlays = useMemo(
    () =>
      MA_OVERLAYS.map((ma) => ({
        color: ma.color,
        lineWidth: 1,
        label: ma.label,
        points: bars
          .filter((b) => b[ma.key] != null)
          .map((b) => ({ time: toBarTime(b.day), value: b[ma.key] as number })),
      })),
    [bars],
  )

  const activePatterns = useMemo(
    () =>
      stock
        ? Object.entries(PATTERN_LABELS).filter(([key]) => (stock[key] as number | null) === 1)
        : [],
    [stock],
  )

  if (loading) return <Loading />
  if (error) return <ErrorState message={error} onRetry={() => window.location.reload()} />
  if (!stock) return null

  const chg = stock.change
  const pct = stock.pct_change
  const upDown = (chg ?? 0) >= 0 ? 'text-up' : 'text-down'

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>
            {stock.name_zh || stock.name || stock.symbol}
            <span className="text-muted" style={{ fontSize: 15, marginLeft: 10 }}>
              {stock.symbol}
              {stock.name_zh && stock.name ? ` · ${stock.name}` : ''} · {stock.trade_date}
            </span>
          </h2>
          <p className="desc">
            港股行情详情（雅虎财经离线快照，非实时）·{' '}
            <a href={`https://finance.yahoo.com/quote/${encodeURIComponent(stock.symbol)}/`} target="_blank" rel="noreferrer">
              Yahoo 行情 ↗
            </a>
          </p>
        </div>
        <Link className="btn btn-outline-secondary btn-sm" to="/hk">
          ← 返回列表
        </Link>
      </div>

      <div className="panel">
        <div className="panel-body stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))' }}>
          <div>
            <div className={`stat-value ${upDown}`}>{stock.close?.toFixed(2) ?? '--'}</div>
            <div className="stat-label">现价 (HKD)</div>
          </div>
          <div>
            <div className={`stat-value ${upDown}`}>
              {chg != null ? `${chg >= 0 ? '+' : ''}${chg.toFixed(2)}` : '--'}
            </div>
            <div className="stat-label">涨跌额</div>
          </div>
          <div>
            <div className={`stat-value ${upDown}`}>{fmtPct(pct)}</div>
            <div className="stat-label">涨跌幅</div>
          </div>
          <div>
            <div className="stat-value">{stock.open?.toFixed(2) ?? '--'}</div>
            <div className="stat-label">今开</div>
          </div>
          <div>
            <div className="stat-value">{stock.high?.toFixed(2) ?? '--'}</div>
            <div className="stat-label">最高</div>
          </div>
          <div>
            <div className="stat-value">{stock.low?.toFixed(2) ?? '--'}</div>
            <div className="stat-label">最低</div>
          </div>
          <div>
            <div className="stat-value">{stock.pre_close?.toFixed(2) ?? '--'}</div>
            <div className="stat-label">昨收</div>
          </div>
          <div>
            <div className="stat-value">{fmtCount(stock.volume)}</div>
            <div className="stat-label">成交量</div>
          </div>
          <div>
            <div className="stat-value">{fmtCount(stock.amount)}</div>
            <div className="stat-label">成交额</div>
          </div>
          <div>
            <div className="stat-value">{fmtCount(stock.market_cap)}</div>
            <div className="stat-label">总市值</div>
          </div>
          <div>
            <div className="stat-value">{stock.signal_score?.toFixed(1) ?? '--'}</div>
            <div className="stat-label">综合评分</div>
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-body">
          <div className="d-flex justify-content-between align-items-center mb-2">
            <h5 className="mb-0">K 线行情</h5>
            <div className="btn-group btn-group-sm">
              {RANGES.map((r) => (
                <button
                  key={r.key}
                  type="button"
                  className={`btn ${range === r.key ? 'btn-primary' : 'btn-outline-secondary'}`}
                  onClick={() => setRange(r.key)}
                >
                  {r.label}
                </button>
              ))}
            </div>
          </div>
          <CandleChart bars={chartBars} overlays={overlays} height={420} title={`${stock.symbol} 日线`} />
        </div>
      </div>

      <div className="panel">
        <div className="panel-body">
          <h5>技术形态（当日）</h5>
          <div className="d-flex flex-wrap gap-2">
            {stock.ma20 != null && stock.close != null && (
              <span className={`chip ${stock.close >= stock.ma20 ? 'text-up' : 'text-down'}`}>
                价格{stock.close >= stock.ma20 ? '站上' : '跌破'} MA20
                {' '}({(((stock.close - stock.ma20) / stock.ma20) * 100).toFixed(1)}%)
              </span>
            )}
            {stock.ma60 != null && stock.close != null && (
              <span className={`chip ${stock.close >= stock.ma60 ? 'text-up' : 'text-down'}`}>
                价格{stock.close >= stock.ma60 ? '站上' : '跌破'} MA60
                {' '}({(((stock.close - stock.ma60) / stock.ma60) * 100).toFixed(1)}%)
              </span>
            )}
            {stock.vol_ratio_5 != null && (
              <span className="chip">
                量比 {stock.vol_ratio_5.toFixed(2)}x ·{' '}
                {stock.vol_ratio_5 >= 2 ? '显著放量' : stock.vol_ratio_5 >= 1.5 ? '温和放量' : stock.vol_ratio_5 <= 0.8 ? '缩量' : '量能正常'}
              </span>
            )}
            {activePatterns.length > 0 ? (
              activePatterns.map(([key, label]) => (
                <span key={key} className="chip text-up">
                  {label}
                </span>
              ))
            ) : (
              <span className="chip text-muted">当日无形态命中</span>
            )}
          </div>
        </div>
      </div>

      {GROUPS.map((group) => (
        <div className="panel" key={group.title}>
          <div className="panel-body">
            <h5>{group.title}</h5>
            <div className="row g-2">
              {group.fields.map((f) => {
                const val = stock[f.key]
                return (
                  <div className="col-6 col-md-3 col-xl-2" key={f.key}>
                    <div className="d-flex justify-content-between border rounded px-2 py-1">
                      <span className="text-muted" style={{ fontSize: 12 }}>
                        {f.label}
                      </span>
                      <span style={{ fontSize: 13, fontWeight: 600 }} className={valClass(val, f.format)}>
                        {fmt(val, f.format)}
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      ))}

      <div className="panel">
        <div className="panel-body">
          <h5>综合评分与形态标志</h5>
          <div className="row g-2">
            <div className="col-6 col-md-3 col-xl-2">
              <div className="d-flex justify-content-between border rounded px-2 py-1">
                <span className="text-muted" style={{ fontSize: 12 }}>综合评分</span>
                <span style={{ fontSize: 13, fontWeight: 600 }} className={valClass(stock.signal_score, 'score')}>
                  {fmt(stock.signal_score, 'score')}
                </span>
              </div>
            </div>
            {Object.entries(PATTERN_LABELS).map(([key, label]) => {
              const val = stock[key]
              return (
                <div className="col-6 col-md-3 col-xl-2" key={key}>
                  <div className="d-flex justify-content-between border rounded px-2 py-1">
                    <span className="text-muted" style={{ fontSize: 12 }}>{label}</span>
                    <span style={{ fontSize: 13, fontWeight: 600 }} className={valClass(val, 'flag')}>
                      {fmt(val, 'flag')}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
          <p className="text-muted mb-0 mt-2" style={{ fontSize: 12 }}>
            综合评分由形态加权 + 动量/盈利分位加成 + 高估值扣分构成（0–100）。
          </p>
        </div>
      </div>
    </div>
  )
}
