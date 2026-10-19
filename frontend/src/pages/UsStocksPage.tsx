import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { fetchUsMeta, fetchUsStocks, type UsStockRow } from '../api/usStock'
import { EmptyState, ErrorState, TableSkeleton } from '../components/StateViews'
import SyncButton from '../components/SyncButton'

const PAGE_SIZE = 50

type Tone =
  | 'price'
  | 'change'
  | 'percent'
  | 'compact'
  | 'vol'
  | 'ratio'
  | 'score'
  | 'financial_ratio'
  | 'financial_pct'
  | 'risk_ratio'
  | 'yield_pct'

interface ColumnDef {
  key: string
  label: string
  sortable: boolean
  tone?: Tone
  group?: 'financial'
}

const DEFAULT_COLUMNS: ColumnDef[] = [
  { key: 'symbol', label: '代码', sortable: false },
  { key: 'name', label: '名称', sortable: false },
  { key: 'pct_change', label: '涨跌幅', sortable: true, tone: 'percent' },
  { key: 'signal_score', label: '综合评分', sortable: true, tone: 'score' },
  { key: 'close', label: '现价', sortable: true, tone: 'price' },
  { key: 'amount', label: '成交额', sortable: true, tone: 'vol' },
  { key: 'volume', label: '成交量', sortable: true, tone: 'vol' },
  { key: 'vol_ratio_5', label: '量比', sortable: true, tone: 'ratio' },
  { key: 'ret_5d', label: '5日涨幅', sortable: true, tone: 'percent' },
  { key: 'ret_20d', label: '20日涨幅', sortable: true, tone: 'percent' },
  { key: 'ma20', label: 'MA20', sortable: true, tone: 'price' },
  { key: 'market_cap', label: '总市值', sortable: true, tone: 'compact', group: 'financial' },
  { key: 'forward_pe', label: '前瞻PE', sortable: true, tone: 'financial_ratio', group: 'financial' },
  { key: 'trailing_pe', label: '静态PE', sortable: true, tone: 'financial_ratio', group: 'financial' },
  { key: 'price_to_book', label: '市净率', sortable: true, tone: 'financial_ratio', group: 'financial' },
  { key: 'roe', label: 'ROE', sortable: true, tone: 'financial_pct', group: 'financial' },
  { key: 'revenue_growth', label: '营收增长', sortable: true, tone: 'financial_pct', group: 'financial' },
  { key: 'profit_margin', label: '利润率', sortable: true, tone: 'financial_pct', group: 'financial' },
]

const EXTRA_COLUMNS: ColumnDef[] = [
  { key: 'open', label: '今开', sortable: true, tone: 'price' },
  { key: 'high', label: '最高', sortable: true, tone: 'price' },
  { key: 'low', label: '最低', sortable: true, tone: 'price' },
  { key: 'pre_close', label: '昨收', sortable: true, tone: 'price' },
  { key: 'change', label: '涨跌额', sortable: true, tone: 'change' },
  { key: 'ret_1d', label: '1日涨幅', sortable: true, tone: 'percent' },
  { key: 'ma5', label: 'MA5', sortable: true, tone: 'price' },
  { key: 'ma10', label: 'MA10', sortable: true, tone: 'price' },
  { key: 'ma60', label: 'MA60', sortable: true, tone: 'price' },
  { key: 'amplitude', label: '振幅', sortable: true, tone: 'vol' },
  { key: 'body_ratio', label: '实体比', sortable: true, tone: 'vol' },
  { key: 'upper_shadow_ratio', label: '上影比', sortable: true, tone: 'vol' },
  { key: 'lower_shadow_ratio', label: '下影比', sortable: true, tone: 'vol' },
  { key: 'peg_ratio', label: 'PEG', sortable: true, tone: 'financial_ratio', group: 'financial' },
  { key: 'ps_ratio', label: '市销率', sortable: true, tone: 'financial_ratio', group: 'financial' },
  { key: 'roa', label: 'ROA', sortable: true, tone: 'financial_pct', group: 'financial' },
  { key: 'operating_margin', label: '营业利润率', sortable: true, tone: 'financial_pct', group: 'financial' },
  { key: 'earnings_growth', label: '盈利增长', sortable: true, tone: 'financial_pct', group: 'financial' },
  { key: 'debt_to_equity', label: '负债权益比', sortable: true, tone: 'risk_ratio', group: 'financial' },
  { key: 'current_ratio', label: '流动比率', sortable: true, tone: 'risk_ratio', group: 'financial' },
  { key: 'dividend_yield', label: '股息率', sortable: true, tone: 'yield_pct', group: 'financial' },
  { key: 'dividend_rate', label: '每股股息', sortable: true, tone: 'price', group: 'financial' },
  { key: 'risk_ma20_dev', label: 'MA20乖离', sortable: true, tone: 'risk_ratio' },
  { key: 'risk_ma60_dev', label: 'MA60乖离', sortable: true, tone: 'risk_ratio' },
  { key: 'risk_dd_20d', label: '20日回撤', sortable: true, tone: 'risk_ratio' },
  { key: 'risk_vol_20d', label: '20日波动', sortable: true, tone: 'vol' },
]

/** 美股行情页（数据：雅虎财经离线快照，非实时；移植自 us_stock_screener 列表） */
export default function UsStocksPage() {
  const navigate = useNavigate()
  const [keyword, setKeyword] = useState('')
  const [appliedKeyword, setAppliedKeyword] = useState('')
  const [sortBy, setSortBy] = useState<string | null>(null)
  const [sortAsc, setSortAsc] = useState(false)
  const [offset, setOffset] = useState(0)
  const [expanded, setExpanded] = useState(false)
  const [data, setData] = useState<{ total: number; rows: UsStockRow[] } | null>(null)
  const [tradeDate, setTradeDate] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchUsMeta().then((meta) => setTradeDate(meta.trade_date)).catch(() => setTradeDate(null))
  }, [])

  const load = useCallback(async (targetOffset: number, q: string, col: string | null, asc: boolean) => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchUsStocks({
        q: q || undefined,
        sort_by: col || undefined,
        sort_asc: asc,
        offset: targetOffset,
        limit: PAGE_SIZE,
      })
      setData({ total: result.total, rows: result.rows })
      setOffset(targetOffset)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载美股列表失败')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load(0, '', null, false)
  }, [load])

  /** 同步成功后：重取数据日期 + 重载当前列表 */
  const refreshAll = useCallback(() => {
    fetchUsMeta().then((meta) => setTradeDate(meta.trade_date)).catch(() => setTradeDate(null))
    load(offset, appliedKeyword, sortBy, sortAsc)
  }, [load, offset, appliedKeyword, sortBy, sortAsc])

  const handleSort = (key: string) => {
    if (key === sortBy) {
      const nextAsc = !sortAsc
      setSortAsc(nextAsc)
      load(offset, appliedKeyword, key, nextAsc)
    } else {
      setSortBy(key)
      setSortAsc(false)
      load(offset, appliedKeyword, key, false)
    }
  }

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setAppliedKeyword(keyword)
    setSortBy(null)
    load(0, keyword, null, false)
  }

  const page = data?.total === 0 ? 1 : Math.floor(offset / PAGE_SIZE) + 1
  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0
  const pageButtons = () => {
    const win = 2
    const start = Math.max(1, page - win)
    const end = Math.min(totalPages, page + win)
    const buttons: number[] = []
    for (let i = start; i <= end; i++) buttons.push(i)
    return buttons
  }

  const columns = expanded ? [...DEFAULT_COLUMNS, ...EXTRA_COLUMNS] : DEFAULT_COLUMNS

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>美股行情</h2>
          <p className="desc">美股市场核心股票池行情与技术指标，数据来自雅虎财经离线快照（约 15 分钟延迟，非实时）</p>
        </div>
        <div className="d-flex align-items-center gap-2 flex-wrap">
          {data && <span className="chip">共 {data.total} 只</span>}
          <span className="chip">最新数据日期 {tradeDate ?? '--'}</span>
          <SyncButton market="us" onSynced={refreshAll} />
        </div>
      </div>

      <div className="panel">
        <div className="panel-body">
          <form className="row g-3 align-items-end" onSubmit={handleSearch}>
            <div className="col-md-4">
              <label className="form-label">关键字</label>
              <input
                type="text"
                className="form-control"
                placeholder="代码 / 名称，如 AAPL 或 苹果"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
              />
            </div>
            <div className="col-md-4 d-flex gap-2">
              <button type="submit" className="btn btn-primary" style={{ minWidth: 96 }}>
                搜索
              </button>
              <button
                type="button"
                className="btn btn-outline-secondary"
                onClick={() => {
                  setKeyword('')
                  setAppliedKeyword('')
                  setSortBy(null)
                  load(0, '', null, false)
                }}
              >
                重置
              </button>
            </div>
          </form>
        </div>
      </div>

      <div className="panel">
        <div className="panel-body tight table-container">
          {error ? (
            <div className="p-3">
              <ErrorState message={error} onRetry={() => load(offset, appliedKeyword, sortBy, sortAsc)} />
            </div>
          ) : loading ? (
            <TableSkeleton rows={10} />
          ) : (
            <>
              <table className="data-table">
                <thead>
                  <tr>
                    {columns.map((col, idx) => {
                      const isFirstFinancial =
                        col.group === 'financial' && (idx === 0 || columns[idx - 1]?.group !== 'financial')
                      const thClass = [
                        col.sortable ? 'sortable' : '',
                        col.tone ? 'num' : '',
                        isFirstFinancial ? 'financial-first' : '',
                      ]
                        .filter(Boolean)
                        .join(' ')
                      if (!col.sortable) {
                        return (
                          <th key={col.key} className={thClass}>
                            {col.label}
                          </th>
                        )
                      }
                      return (
                        <th key={col.key} className={thClass} onClick={() => handleSort(col.key)} style={{ cursor: 'pointer' }}>
                          {col.label}
                          {sortBy === col.key ? (sortAsc ? ' ↑' : ' ↓') : ''}
                        </th>
                      )
                    })}
                  </tr>
                </thead>
                <tbody>
                  {data && data.rows.length > 0 ? (
                    data.rows.map((row) => (
                      <tr
                        key={row.symbol}
                        style={{ cursor: 'pointer' }}
                        onClick={() => navigate(`/us/${row.symbol}`)}
                      >
                        {columns.map((col, idx) => {
                          const value = row[col.key as string]
                          const isFirstFinancial =
                            col.group === 'financial' && (idx === 0 || columns[idx - 1]?.group !== 'financial')
                          if (col.key === 'symbol') {
                            return (
                              <td key={col.key}>
                                <code>{row.symbol}</code>
                              </td>
                            )
                          }
                          if (col.key === 'name') {
                            return (
                              <td key={col.key} style={{ fontWeight: 600 }}>
                                {row.name_zh || row.name || '--'}
                                {row.name_zh && row.name && (
                                  <div className="text-muted" style={{ fontSize: 11, fontWeight: 400 }}>
                                    {row.name}
                                  </div>
                                )}
                              </td>
                            )
                          }
                          return (
                            <td
                              key={col.key}
                              className={`num ${isFirstFinancial ? 'financial-first' : ''} ${cellClass(col, value)}`}
                            >
                              {formatValue(value, col.tone)}
                            </td>
                          )
                        })}
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={columns.length}>
                        <EmptyState icon="🔍" text="没有符合条件的美股" />
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
              <div className="d-flex justify-content-between align-items-center py-3">
                <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => setExpanded((v) => !v)}>
                  {expanded ? '收起扩展列' : '更多列'}
                </button>
                {totalPages > 1 && (
                  <nav>
                    <ul className="pagination pagination-sm mb-0">
                      <li className={`page-item ${page <= 1 ? 'disabled' : ''}`}>
                        <button
                          className="page-link"
                          onClick={() => load(offset - PAGE_SIZE, appliedKeyword, sortBy, sortAsc)}
                        >
                          上一页
                        </button>
                      </li>
                      {pageButtons().map((p) => (
                        <li key={p} className={`page-item ${p === page ? 'active' : ''}`}>
                          <button
                            className="page-link"
                            onClick={() => load((p - 1) * PAGE_SIZE, appliedKeyword, sortBy, sortAsc)}
                          >
                            {p}
                          </button>
                        </li>
                      ))}
                      <li className={`page-item ${page >= totalPages ? 'disabled' : ''}`}>
                        <button
                          className="page-link"
                          onClick={() => load(offset + PAGE_SIZE, appliedKeyword, sortBy, sortAsc)}
                        >
                          下一页
                        </button>
                      </li>
                    </ul>
                  </nav>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      <p className="text-muted" style={{ fontSize: 12 }}>
        股票池与数据处理移植自 us_stock_screener 项目（雅虎财经 2 年日线 + 技术指标/形态/财务字段）。
        点击行查看 <Link to="/us">详情</Link>：K 线行情与技术指标。
      </p>
    </div>
  )
}

// ── 单元格配色（涨红跌绿；估值/风险字段越界标警示） ─────────────────────────

function cellClass(col: ColumnDef, value: string | number | null | undefined): string {
  const n = typeof value === 'number' ? value : NaN
  if (col.tone === 'percent' || col.tone === 'financial_pct' || col.tone === 'change') {
    if (!isNaN(n)) {
      if (n > 0) return 'text-up'
      if (n < 0) return 'text-down'
    }
    return ''
  }
  if (col.tone === 'financial_ratio') {
    if (isNaN(n)) return ''
    if ((col.key === 'forward_pe' || col.key === 'trailing_pe') && n > 80) return 'text-warning'
    return ''
  }
  if (col.tone === 'risk_ratio') {
    if (isNaN(n)) return ''
    if (col.key === 'debt_to_equity' && n > 200) return 'text-warning'
    if (col.key === 'current_ratio' && n < 1) return 'text-warning'
    return ''
  }
  return ''
}

// ── 数值格式化（tone 语义移植自 StockTable.tsx） ─────────────────────────────

function fmtCompact(value: number, maxDigits = 2): string {
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: maxDigits }).format(value)
}

function formatValue(value: string | number | null | undefined, tone?: Tone): string {
  if (value === null || value === undefined || value === '') return '--'
  if (typeof value === 'string') return value
  switch (tone) {
    case 'percent':
      return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(2)}%`
    case 'financial_pct':
      return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}%`
    case 'change':
      return `${value >= 0 ? '+' : ''}${value.toFixed(2)}`
    case 'compact':
      return fmtCompact(value)
    case 'vol':
      return fmtCompact(value, 1)
    case 'score':
      return value.toFixed(1)
    case 'yield_pct':
      return `${value.toFixed(2)}%`
    case 'ratio':
    case 'risk_ratio':
      return value.toFixed(2)
    case 'price':
      return value.toFixed(2)
    case 'financial_ratio':
      if (value < 0) return '--'
      return value.toFixed(1)
    default:
      return String(value)
  }
}
