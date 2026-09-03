import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { OLD_SITE_BASE } from '../App'
import { fetchStockFactors, fetchStockHistory, fetchStockInfo } from '../api/stocks'
import type { DailyBar, FactorRow, StockBasic } from '../api/types'
import { ErrorState, Loading } from '../components/StateViews'
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
  const priceChange = latest && previous && previous.close
    ? ((latest.close ?? 0) - previous.close) / previous.close * 100
    : 0
  const latestFactor = factorsData && factorsData.length > 0 ? factorsData[0] : null

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
    <div className="container-fluid px-4">
      <h4 className="mt-2 mb-1">技术分析</h4>
      <p className="text-secondary">lightweight-charts v5 · K线/线图 · MACD/KDJ/RSI/布林带</p>

      <div className="card mb-4">
        <div className="card-body">
          <form className="row g-3" onSubmit={handleAnalyze}>
            <div className="col-md-4">
              <label className="form-label">股票代码</label>
              <input
                type="text"
                className={`form-control ${inputError ? 'is-invalid' : ''}`}
                placeholder="请输入股票代码，如：000001.SZ"
                maxLength={9}
                value={stockInput}
                onChange={(e) => setStockInput(e.target.value.toUpperCase())}
                onBlur={handleBlur}
              />
              {inputError ? <div className="invalid-feedback">{inputError}</div> : <div className="form-text">支持格式：000001.SZ（深圳）、600000.SH（上海）</div>}
            </div>
            <div className="col-md-3">
              <label className="form-label">时间周期</label>
              <select className="form-select" value={period} onChange={(e) => setPeriod(Number(e.target.value))}>
                {PERIODS.map((p) => (
                  <option key={p} value={p}>
                    {p}天
                  </option>
                ))}
              </select>
            </div>
            <div className="col-md-3">
              <label className="form-label">图表类型</label>
              <select className="form-select" value={chartType} onChange={(e) => setChartType(e.target.value as MainChartType)}>
                <option value="candlestick">K线图</option>
                <option value="line">线图</option>
              </select>
            </div>
            <div className="col-md-2">
              <label className="form-label">&nbsp;</label>
              <button type="submit" className="btn btn-primary d-block w-100" disabled={loading}>
                📊 分析
              </button>
            </div>
          </form>
        </div>
      </div>

      {showResults && (
        <>
          {/* 股票信息卡片 */}
          <div className="row mb-4">
            <div className="col-12">
              <div className="card">
                <div className="card-body">
                  <div className="row align-items-center">
                    <div className="col-md-8">
                      {stockInfo ? (
                        <>
                          <h5 className="mb-2">
                            {stockInfo.name} <code className="fs-6">{stockInfo.ts_code}</code>{' '}
                            <span className={`badge ${stockInfo.ts_code.endsWith('.SH') ? 'bg-danger' : 'bg-success'}`}>
                              {stockInfo.ts_code.endsWith('.SH') ? '上海' : '深圳'}
                            </span>
                          </h5>
                          <div>
                            行业：<span className="badge text-bg-info me-2">{stockInfo.industry ?? '--'}</span>
                            地域：<span className="badge text-bg-secondary me-2">{stockInfo.area ?? '--'}</span>
                            上市日期：<span>{stockInfo.list_date ?? '--'}</span>
                          </div>
                        </>
                      ) : (
                        <>
                          <h5 className="mb-2">
                            {normalizeStockCode(stockInput)} <span className="badge text-bg-secondary">暂无详细信息</span>
                          </h5>
                          <div className="text-secondary">未查询到股票基本信息，可继续查看行情与指标。</div>
                        </>
                      )}
                    </div>
                    <div className="col-md-4 text-end">
                      <button
                        type="button"
                        className="btn btn-outline-primary btn-sm me-2"
                        onClick={() => window.open(`${OLD_SITE_BASE}/stock/${normalizeStockCode(stockInput)}`, '_blank')}
                      >
                        详情
                      </button>
                      <button type="button" className="btn btn-outline-warning btn-sm" onClick={() => window.alert('已加入自选股（演示功能）')}>
                        自选
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* 关键指标（涨跌幅统一红涨绿跌口径） */}
          <div className="row mb-4 g-3">
            <div className="col-lg-3 col-md-6">
              <div className="card metric-card text-center h-100">
                <div className="card-body">
                  <div className="metric-value">{formatNumber(latest?.close ?? null, 2)}</div>
                  <div className="metric-label">当前价格</div>
                </div>
              </div>
            </div>
            <div className="col-lg-3 col-md-6">
              <div className="card metric-card text-center h-100">
                <div className="card-body">
                  <div className={`metric-value ${pctClass(priceChange)}`}>{formatPercent(priceChange)}</div>
                  <div className="metric-label">涨跌幅</div>
                </div>
              </div>
            </div>
            <div className="col-lg-3 col-md-6">
              <div className="card metric-card text-center h-100">
                <div className="card-body">
                  <div className="metric-value">{formatNumber((latest?.vol ?? 0) / 10000, 1)}万</div>
                  <div className="metric-label">成交量</div>
                </div>
              </div>
            </div>
            <div className="col-lg-3 col-md-6">
              <div className="card metric-card text-center h-100">
                <div className="card-body">
                  <div className="metric-value">{formatNumber((latest?.amount ?? 0) / 100000, 2)}亿</div>
                  <div className="metric-label">成交额</div>
                </div>
              </div>
            </div>
          </div>

          {/* 主图表 */}
          <div className="row mb-4">
            <div className="col-12">
              <div className="card">
                <div className="card-header">
                  <div className="d-flex justify-content-between align-items-center">
                    <h5 className="mb-0">📊 价格图表</h5>
                    <div className="btn-group btn-group-sm btn-view-group" role="group">
                      <button
                        type="button"
                        className={`btn ${mainView === 'price' ? 'btn-primary' : 'btn-outline-primary'}`}
                        onClick={() => setMainView('price')}
                      >
                        价格
                      </button>
                      <button
                        type="button"
                        className={`btn ${mainView === 'volume' ? 'btn-primary' : 'btn-outline-primary'}`}
                        onClick={() => setMainView('volume')}
                      >
                        成交量
                      </button>
                    </div>
                  </div>
                </div>
                <div className="card-body">
                  {loading ? (
                    <Loading text="加载图表数据..." />
                  ) : errorMsg ? (
                    <ErrorState message={errorMsg} onRetry={handleAnalyze} />
                  ) : historyData && historyData.length > 0 ? (
                    <MainChart view={mainView} chartType={chartType} history={historyData} />
                  ) : (
                    <div className="empty-state">暂无行情数据</div>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* 技术指标图表 */}
          <div className="row">
            <div className="col-12 mb-3">
              <div className="d-flex gap-2">
                {(['macd', 'kdj', 'rsi', 'boll'] as IndicatorType[]).map((item) => (
                  <div key={item} className={`chart-tab ${indicator === item ? 'active' : ''}`} onClick={() => setIndicator(item)}>
                    {item === 'boll' ? '布林带' : item.toUpperCase()}
                  </div>
                ))}
              </div>
            </div>
            <div className="col-12">
              <div className="card">
                <div className="card-header">
                  <h6 className="mb-0">{INDICATOR_TITLES[indicator]}</h6>
                </div>
                <div className="card-body">
                  {loading ? (
                    <Loading text="加载指标数据..." />
                  ) : errorMsg ? (
                    <ErrorState message={errorMsg} />
                  ) : factorsData && factorsData.length > 0 ? (
                    <IndicatorChart indicator={indicator} history={historyData} factors={factorsData} />
                  ) : (
                    <div className="empty-state">暂无指标数据</div>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* 详细数据 */}
          <div className="row mt-4">
            <div className="col-12">
              <div className="card">
                <div className="card-header">
                  <h6 className="mb-0">📋 详细数据</h6>
                </div>
                <div className="card-body">
                  <div className="table-responsive">
                    <table className="table table-sm table-hover align-middle">
                      <thead>
                        <tr>
                          <th>日期</th>
                          <th>开盘</th>
                          <th>最高</th>
                          <th>最低</th>
                          <th>收盘</th>
                          <th>成交量</th>
                          <th>涨跌幅</th>
                          <th>RSI</th>
                          <th>MACD</th>
                        </tr>
                      </thead>
                      <tbody>
                        {tableRows.length > 0 ? (
                          tableRows.map((item) => (
                            <tr key={item.trade_date}>
                              <td>{item.trade_date}</td>
                              <td>{formatNumber(item.open, 2)}</td>
                              <td className="text-danger">{formatNumber(item.high, 2)}</td>
                              <td className="text-success">{formatNumber(item.low, 2)}</td>
                              <td>
                                <strong>{formatNumber(item.close, 2)}</strong>
                              </td>
                              <td>{formatNumber((item.vol ?? 0) / 10000, 1)}万</td>
                              <td className={pctClass(item.pct_chg)}>{formatPercent(item.pct_chg)}</td>
                              <td>{formatNumber(item.rsi_6 ?? null, 2)}</td>
                              <td>{formatNumber(item.macd ?? null, 4)}</td>
                            </tr>
                          ))
                        ) : (
                          <tr>
                            <td colSpan={9} className="text-center text-secondary py-4">
                              暂无数据
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </>
      )}

      {!showResults && latestFactor === null && !loading && (
        <div className="empty-state">输入股票代码后点击「分析」查看行情与技术指标</div>
      )}
    </div>
  )
}
