import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchAreas, fetchIndustries, fetchStocks } from '../api/stocks'
import type { StockListData } from '../api/types'
import { EmptyState, ErrorState, TableSkeleton } from '../components/StateViews'

const PAGE_SIZE = 100

interface Filters {
  industry: string
  area: string
  search: string
}

const EMPTY_FILTERS: Filters = { industry: '', area: '', search: '' }

export default function StocksPage() {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS)
  const [applied, setApplied] = useState<Filters>(EMPTY_FILTERS)
  const [page, setPage] = useState(1)
  const [industries, setIndustries] = useState<string[]>([])
  const [areas, setAreas] = useState<string[]>([])
  const [data, setData] = useState<StockListData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchIndustries().then(setIndustries).catch(() => setIndustries([]))
    fetchAreas().then(setAreas).catch(() => setAreas([]))
  }, [])

  const load = useCallback(async (targetPage: number, targetFilters: Filters) => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchStocks({
        page: targetPage,
        page_size: PAGE_SIZE,
        industry: targetFilters.industry || undefined,
        area: targetFilters.area || undefined,
        search: targetFilters.search || undefined,
      })
      setData(result)
      setPage(targetPage)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载股票列表失败')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load(1, EMPTY_FILTERS)
  }, [load])

  const handleFilter = (e: React.FormEvent) => {
    e.preventDefault()
    setApplied(filters)
    load(1, filters)
  }

  const handleReset = () => {
    setFilters(EMPTY_FILTERS)
    setApplied(EMPTY_FILTERS)
    load(1, EMPTY_FILTERS)
  }

  const totalPages = data?.total_pages ?? 0

  const pageButtons = () => {
    const window = 2
    const start = Math.max(1, page - window)
    const end = Math.min(totalPages, page + window)
    const buttons: number[] = []
    for (let i = start; i <= end; i++) buttons.push(i)
    return buttons
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>股票列表</h2>
          <p className="desc">全市场股票浏览，支持按行业、地域筛选与关键字搜索</p>
        </div>
        {data && <span className="chip">共 {data.total} 只</span>}
      </div>

      <div className="panel">
        <div className="panel-body">
          <form className="row g-3 align-items-end" onSubmit={handleFilter}>
            <div className="col-md-3 col-6">
              <label className="form-label">行业</label>
              <select
                className="form-select"
                value={filters.industry}
                onChange={(e) => setFilters({ ...filters, industry: e.target.value })}
              >
                <option value="">全部行业</option>
                {industries.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-md-3 col-6">
              <label className="form-label">地域</label>
              <select className="form-select" value={filters.area} onChange={(e) => setFilters({ ...filters, area: e.target.value })}>
                <option value="">全部地域</option>
                {areas.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-md-3">
              <label className="form-label">关键字</label>
              <input
                type="text"
                className="form-control"
                placeholder="股票代码或名称"
                value={filters.search}
                onChange={(e) => setFilters({ ...filters, search: e.target.value })}
              />
            </div>
            <div className="col-md-3 d-flex gap-2">
              <button type="submit" className="btn btn-primary" style={{ minWidth: 96 }}>
                筛选
              </button>
              <button type="button" className="btn btn-outline-secondary" onClick={handleReset}>
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
              <ErrorState message={error} onRetry={() => load(page, applied)} />
            </div>
          ) : loading ? (
            <TableSkeleton rows={10} />
          ) : (
            <>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>股票代码</th>
                    <th>股票名称</th>
                    <th>行业</th>
                    <th>地域</th>
                    <th>上市日期</th>
                    <th className="num">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {data && data.stocks.length > 0 ? (
                    data.stocks.map((stock) => (
                      <tr key={stock.ts_code}>
                        <td>
                          <code>{stock.symbol}</code>
                        </td>
                        <td style={{ fontWeight: 600 }}>{stock.name}</td>
                        <td>
                          <span className="chip">{stock.industry ?? '--'}</span>
                        </td>
                        <td>{stock.area ?? '--'}</td>
                        <td>{stock.list_date ?? '--'}</td>
                        <td className="num">
                          <Link className="btn btn-outline-primary btn-sm" to={`/stock/${stock.ts_code}`}>
                            详情
                          </Link>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={6}>
                        <EmptyState icon="🔍" text="没有符合条件的股票" />
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
              {totalPages > 1 && (
                <div className="d-flex justify-content-center py-3">
                  <nav>
                    <ul className="pagination pagination-sm mb-0">
                      <li className={`page-item ${page <= 1 ? 'disabled' : ''}`}>
                        <button className="page-link" onClick={() => load(page - 1, applied)}>
                          上一页
                        </button>
                      </li>
                      {pageButtons().map((p) => (
                        <li key={p} className={`page-item ${p === page ? 'active' : ''}`}>
                          <button className="page-link" onClick={() => load(p, applied)}>
                            {p}
                          </button>
                        </li>
                      ))}
                      <li className={`page-item ${page >= totalPages ? 'disabled' : ''}`}>
                        <button className="page-link" onClick={() => load(page + 1, applied)}>
                          下一页
                        </button>
                      </li>
                    </ul>
                  </nav>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
