import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { OLD_SITE_BASE } from '../App'
import { fetchStockFactors, fetchStockHistory, fetchStockInfo } from '../api/stocks'
import type { DailyBar, FactorRow, StockBasic } from '../api/types'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import MainChart, { type MainChartType, type MainChartView } from '../charts/MainChart'
import IndicatorChart, { INDICATOR_TITLES, type IndicatorType } from '../charts/IndicatorChart'
import { formatNumber, formatPercent, pctClass } from '../utils/format'

const STOCK_CODE_RE = /^[0-9]{6}\.(SZ|SH)$/
const PERIODS = [30, 60, 120, 250]

/** 输入规范化：转大写；6 位纯数字按首位补后缀（0/3→.SZ，6→.SH） */
function normalizeStockCode(raw: string): string {
  const value = raw.trim().toUpperCase()
  if (/^[0-9]{6}$/.test(value)) {
    const suffix = value.startsWith('0') || value.startsWith('3') ? '.SZ' : value.startsWith('6') ? '.SH' : ''
    return value + suffix
  }
  return value
}

function DeltaChip({ value }: { value: number | null | undefined }) {
  const cls = value == null || Number.isNaN(value) || value === 0 ? 'flat' : value > 0 ? 'up' : 'down'
  const arrow = cls === 'up' ? '↑' : cls === 'down' ? '↓' : '—'
  return (
    <span className={`delta ${cls}`}>
      {arrow} {formatPercent(value)}
    </span>
  )
}

export default function AnalysisPage() {
  const [searchParams] = useSearchParams()
  const [stockInput, setStockInput] = useState('000001.SZ')
  const [inputError, setInputError] = useState<string | null>(null)
  const [period, setPeriod] = useState(60)
  const [chartType, setChartType] = useState<MainChartType>('candlestick')
  const [mainView, setMainView] = useState<MainChartView>('price')
  const [indicator, setIndicator] = useState<IndicatorType>('macd')

  const [stockInfo, setStockInfo] = useState<StockBasic | null>(null)
  const [historyData, setHistoryData] = useState<DailyBar[] | null>(null)
  const [factorsData, setFactorsData] = useState<FactorRow[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [showResults, setShowResults] = useState(false)

  // URL 参数预填股票代码（与旧版一致：只填输入框，不自动分析）
  useEffect(() => {
    const stock = searchParams.get('stock')
    if (stock) {
      setStockInput(stock.toUpperCase())
    }
  }, [searchParams])

  const handleBlur = () => {
    const normalized = normalizeStockCode(stockInput)
    setStockInput(normalized)
    setInputError(STOCK_CODE_RE.test(normalized) ? null : '股票代码格式不正确，应为 000001.SZ 或 600000.SH')
  }

  const handleAnalyze = async (e?: React.FormEvent) => {
    e?.preventDefault()
    const code = normalizeStockCode(stockInput)
    setStockInput(code)
    if (!STOCK_CODE_RE.test(code)) {
      setInputError('股票代码格式不正确，应为 000001.SZ 或 600000.SH')
      return
    }
    setInputError(null)
    setLoading(true)
    setErrorMsg(null)

    // 股票基本信息失败可容忍，历史与因子失败则报错（与旧版 Promise.all 行为对齐）
    const [infoRes, histRes, facRes] = await Promise.allSettled([
      fetchStockInfo(code),
      fetchStockHistory(code, period),
      fetchStockFactors(code, period),
    ])

    setStockInfo(infoRes.status === 'fulfilled' ? infoRes.value : null)

    if (histRes.status === 'rejected' || facRes.status === 'rejected') {
      const reason = histRes.status === 'rejected' ? histRes.reason : facRes.status === 'rejected' ? facRes.reason : null
      setErrorMsg(reason instanceof Error ? reason.message : '数据加载失败，请检查股票代码后重试')
      setHistoryData(null)
      setFactorsData(null)
    } else {
      setHistoryData(histRes.value)
      setFactorsData(facRes.value)
    }
    setShowResults(true)
    setLoading(false)
  }

  const latest = historyData && historyData.length > 0 ? historyData[0] : null
  const previous = historyData && historyData.length > 1 ? historyData[1] : null
  const priceChange =
    latest && previous && previous.close ? (((latest.close ?? 0) - previous.close) / previous.close) * 100 : 0

  // 详细数据表：前 20 行按 trade_date 精确匹配合并因子（直接用倒序原始数组）
  const tableRows = useMemo(() => {
    if (!historyData || historyData.length === 0) return []
    const factorMap = new Map((factorsData ?? []).map((f) => [f.trade_date, f]))
    return historyData.slice(0, 20).map((history) => {
      const factor = factorMap.get(history.trade_date)
      return { ...history, ...(factor ?? {}) } as DailyBar & Partial<FactorRow>
    })
  }, [historyData, factorsData])

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>技术分析</h2>
          <p className="desc">lightweight-charts v5 · K线 / 线图 · MACD / KDJ / RSI / 布林带</p>
        </div>
      </div>

      {/* 分析工具栏 */}
      <div className="panel">
        <div className="panel-body">
          <form className="row g-3 align-items-end" onSubmit={handleAnalyze}>
            <div className="col-lg-4 col-md-6">
              <label className="form-label">股票代码</label>
              <input
                type="text"
                className={`form-control ${inputError ? 'is-invalid' : ''}`}
                placeholder="000001.SZ"
                maxLength={9}
                value={stockInput}
                onChange={(e) => setStockInput(e.target.value.toUpperCase())}
                onBlur={handleBlur}
                style={{ fontSize: 15, fontWeight: 600, letterSpacing: '0.04em' }}
              />
              {inputError ? (
                <div className="invalid-feedback">{inputError}</div>
              ) : (
                <div className="form-text" style={{ color: 'var(--text-faint)' }}>
                  6 位数字自动补后缀：0/3 → .SZ · 6 → .SH
                </div>
              )}
            </div>
            <div className="col-lg-2 col-md-3 col-6">
              <label className="form-label">时间周期</label>
              <select className="form-select" value={period} onChange={(e) => setPeriod(Number(e.target.value))}>
                {PERIODS.map((p) => (
                  <option key={p} value={p}>
                    {p} 天
                  </option>
                ))}
              </select>
            </div>
            <div className="col-lg-2 col-md-3 col-6">
              <label className="form-label">图表类型</label>
              <select className="form-select" value={chartType} onChange={(e) => setChartType(e.target.value as MainChartType)}>
                <option value="candlestick">K线图</option>
                <option value="line">线图</option>
              </select>
            </div>
            <div className="col-lg-2 col-md-4">
              <label className="form-label">&nbsp;</label>
              <button type="submit" className="btn btn-primary w-100" disabled={loading}>
                {loading ? '分析中…' : '⚡ 分析'}
              </button>
            </div>
          </form>
        </div>
      </div>

      {showResults && (
        <>
          {/* 股票信息条 */}
          <div className="panel">
            <div className="panel-body d-flex align-items-center justify-content-between flex-wrap gap-3">
              {stockInfo ? (
                <div>
                  <span style={{ fontSize: 19, fontWeight: 750 }}>{stockInfo.name}</span>
                  <code style={{ marginLeft: 10 }}>{stockInfo.ts_code}</code>
                  <span className={`badge ms-2 ${stockInfo.ts_code.endsWith('.SH') ? 'bg-danger' : 'bg-success'}`}>
                    {stockInfo.ts_code.endsWith('.SH') ? '上海' : '深圳'}
                  </span>
                  <div className="d-flex gap-2 mt-2 flex-wrap">
                    <span className="chip">行业 · {stockInfo.industry ?? '--'}</span>
                    <span className="chip">地域 · {stockInfo.area ?? '--'}</span>
                    <span className="chip">上市 · {stockInfo.list_date ?? '--'}</span>
                  </div>
                </div>
              ) : (
                <div>
                  <span style={{ fontSize: 19, fontWeight: 750 }}>{normalizeStockCode(stockInput)}</span>
                  <span className="chip ms-2">暂无详细信息，可继续查看行情与指标</span>
                </div>
              )}
              <div className="d-flex gap-2">
                <button
                  type="button"
                  className="btn btn-outline-primary btn-sm"
                  onClick={() => window.open(`${OLD_SITE_BASE}/stock/${normalizeStockCode(stockInput)}`, '_blank')}
                >
                  旧版详情 ↗
                </button>
                <button
                  type="button"
                  className="btn btn-outline-secondary btn-sm"
                  onClick={() => window.alert('已加入自选股（演示功能）')}
                >
                  ☆ 自选
                </button>
              </div>
            </div>
          </div>

          {/* 关键指标（涨跌幅统一 A 股红涨绿跌口径） */}
          <div className="stat-grid">
            <div className="stat">
              <div className="stat-value">{formatNumber(latest?.close ?? null, 2)}</div>
              <div className="stat-label">当前价格</div>
            </div>
            <div className="stat">
              <div className="stat-value">
                <DeltaChip value={priceChange} />
              </div>
              <div className="stat-label">涨跌幅</div>
            </div>
            <div className="stat">
              <div className="stat-value">{formatNumber((latest?.vol ?? 0) / 10000, 1)}万</div>
              <div className="stat-label">成交量（手）</div>
            </div>
            <div className="stat">
              <div className="stat-value">{formatNumber((latest?.amount ?? 0) / 100000, 2)}亿</div>
              <div className="stat-label">成交额</div>
            </div>
          </div>

          {/* 主图表 */}
          <div className="panel">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                价格走势
              </h6>
              <div className="seg" role="group">
                <button
                  type="button"
                  className={`seg-item ${mainView === 'price' ? 'active' : ''}`}
                  onClick={() => setMainView('price')}
                >
                  价格
                </button>
                <button
                  type="button"
                  className={`seg-item ${mainView === 'volume' ? 'active' : ''}`}
                  onClick={() => setMainView('volume')}
                >
                  成交量
                </button>
              </div>
            </div>
            <div className="panel-body">
              {loading ? (
                <Loading text="加载行情数据..." />
              ) : errorMsg ? (
                <ErrorState message={errorMsg} onRetry={() => handleAnalyze()} />
              ) : historyData && historyData.length > 0 ? (
                <MainChart view={mainView} chartType={chartType} history={historyData} />
              ) : (
                <EmptyState icon="📉" text="暂无行情数据" />
              )}
            </div>
          </div>

          {/* 技术指标 */}
          <div className="panel">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                {INDICATOR_TITLES[indicator].replace(/^\S+\s/, '')}
              </h6>
              <div className="seg" role="group">
                {(['macd', 'kdj', 'rsi', 'boll'] as IndicatorType[]).map((item) => (
                  <button
                    key={item}
                    type="button"
                    className={`seg-item ${indicator === item ? 'active' : ''}`}
                    onClick={() => setIndicator(item)}
                  >
                    {item === 'boll' ? '布林带' : item.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>
            <div className="panel-body">
              {loading ? (
                <Loading text="加载指标数据..." />
              ) : errorMsg ? (
                <ErrorState message={errorMsg} />
              ) : factorsData && factorsData.length > 0 ? (
                <IndicatorChart indicator={indicator} history={historyData} factors={factorsData} />
              ) : (
                <EmptyState icon="📊" text="暂无指标数据" />
              )}
            </div>
          </div>

          {/* 详细数据 */}
          <div className="panel">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                详细数据
                <span className="chip">{tableRows.length} 条</span>
              </h6>
            </div>
            <div className="panel-body tight table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>日期</th>
                    <th className="num">开盘</th>
                    <th className="num">最高</th>
                    <th className="num">最低</th>
                    <th className="num">收盘</th>
                    <th className="num">成交量</th>
                    <th className="num">涨跌幅</th>
                    <th className="num">RSI</th>
                    <th className="num">MACD</th>
                  </tr>
                </thead>
                <tbody>
                  {tableRows.length > 0 ? (
                    tableRows.map((item) => (
                      <tr key={item.trade_date}>
                        <td>{item.trade_date}</td>
                        <td className="num">{formatNumber(item.open, 2)}</td>
                        <td className="num">{formatNumber(item.high, 2)}</td>
                        <td className="num">{formatNumber(item.low, 2)}</td>
                        <td className="num" style={{ fontWeight: 650 }}>
                          {formatNumber(item.close, 2)}
                        </td>
                        <td className="num">{formatNumber((item.vol ?? 0) / 10000, 1)}万</td>
                        <td className={`num ${pctClass(item.pct_chg)}`}>{formatPercent(item.pct_chg)}</td>
                        <td className="num">{formatNumber(item.rsi_6 ?? null, 2)}</td>
                        <td className="num">{formatNumber(item.macd ?? null, 4)}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={9}>
                        <EmptyState icon="📋" text="暂无数据" />
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {!showResults && (
        <EmptyState icon="⚡" text="输入股票代码，点击「分析」查看行情与技术指标" />
      )}
    </div>
  )
}
