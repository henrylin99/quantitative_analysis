import { useCallback, useEffect, useState } from 'react'
import { OLD_SITE_BASE } from '../App'
import { fetchAreas, fetchIndustries, fetchStocks } from '../api/stocks'
import type { StockListData } from '../api/types'
import { ErrorState, Loading } from '../components/StateViews'

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

  const load = useCallback(
    async (targetPage: number, targetFilters: Filters) => {
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
    },
    [],
  )

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
    <div className="container-fluid px-4">
      <h4 className="mt-2 mb-1">股票列表</h4>
      <p className="text-secondary">浏览所有股票信息，支持按行业、地域筛选</p>

      <div className="card mb-3">
        <div className="card-body">
          <form className="row g-2 align-items-end" onSubmit={handleFilter}>
            <div className="col-md-3">
              <label className="form-label">行业</label>
              <select className="form-select" value={filters.industry} onChange={(e) => setFilters({ ...filters, industry: e.target.value })}>
                <option value="">全部行业</option>
                {industries.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-md-3">
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
            <div className="col-md-3">
              <button type="submit" className="btn btn-primary me-2">
                筛选
              </button>
              <button type="button" className="btn btn-outline-secondary" onClick={handleReset}>
                重置
              </button>
            </div>
          </form>
        </div>
      </div>

      <div className="card">
        <div className="card-header d-flex justify-content-between align-items-center">
          <span>股票列表</span>
          {data && <span className="badge text-bg-primary">共 {data.total} 只</span>}
        </div>
        <div className="card-body">
          {error && <ErrorState message={error} onRetry={() => load(page, applied)} />}
          {loading ? (
            <Loading />
          ) : !error ? (
            <>
              <div className="table-responsive">
                <table className="table table-hover align-middle">
                  <thead>
                    <tr>
                      <th>股票代码</th>
                      <th>股票名称</th>
                      <th>行业</th>
                      <th>地域</th>
                      <th>上市日期</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data && data.stocks.length > 0 ? (
                      data.stocks.map((stock) => (
                        <tr key={stock.ts_code}>
                          <td>
                            <code>{stock.symbol}</code>
                          </td>
                          <td>{stock.name}</td>
                          <td>{stock.industry ? <span className="badge text-bg-info">{stock.industry}</span> : '--'}</td>
                          <td>{stock.area ?? '--'}</td>
                          <td>{stock.list_date ?? '--'}</td>
                          <td>
                            <a className="btn btn-outline-primary btn-sm" href={`${OLD_SITE_BASE}/stock/${stock.ts_code}`} target="_blank" rel="noreferrer">
                              详情
                            </a>
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={6} className="text-center text-secondary py-4">
                          暂无数据
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              {totalPages > 1 && (
                <nav>
                  <ul className="pagination pagination-sm justify-content-center mb-0">
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
              )}
            </>
          ) : null}
        </div>
      </div>
    </div>
  )
}
