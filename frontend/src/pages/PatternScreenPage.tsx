import { useEffect, useMemo, useState } from 'react'
import {
  fetchPatternGroups,
  runPatternScreen,
  type PatternGroup,
  type PatternScreenResult,
  type PatternSortField,
} from '../api/patternScreen'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { formatNumber, formatPercent, formatTradeDate, pctClass } from '../utils/format'

const PAGE_SIZE = 50
const SORTABLE: { key: PatternSortField; label: string }[] = [
  { key: 'pct_chg', label: '涨跌幅' },
  { key: 'close', label: '现价' },
  { key: 'amount', label: '成交额' },
  { key: 'total_mv', label: '总市值' },
  { key: 'turnover_rate', label: '换手率' },
  { key: 'vol_ratio_5', label: '量比' },
]

function fmtAmountWan(value: number | null): string {
  if (value == null || Number.isNaN(value)) return '--'
  if (Math.abs(value) >= 1e8) return `${(value / 1e8).toFixed(2)}亿`
  if (Math.abs(value) >= 1e4) return `${(value / 1e4).toFixed(2)}万`
  return value.toFixed(2)
}

export default function PatternScreenPage() {
  const [groups, setGroups] = useState<PatternGroup[]>([])
  const [groupsError, setGroupsError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [result, setResult] = useState<PatternScreenResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sortBy, setSortBy] = useState<PatternSortField>('pct_chg')
  const [order, setOrder] = useState<'asc' | 'desc'>('desc')
  const [page, setPage] = useState(0)

  useEffect(() => {
    fetchPatternGroups()
      .then(setGroups)
      .catch((e) => setGroupsError(e instanceof Error ? e.message : '形态定义加载失败'))
  }, [])

  const filteredGroups = useMemo(() => {
    const kw = search.trim().toLowerCase()
    if (!kw) return groups
    return groups
      .map((g) => ({ ...g, fields: g.fields.filter((f) => f.label.toLowerCase().includes(kw) || f.key.toLowerCase().includes(kw)) }))
      .filter((g) => g.fields.length > 0)
  }, [groups, search])

  const doScreen = (patterns: string[], sortByVal: PatternSortField, orderVal: 'asc' | 'desc', offset: number) => {
    setLoading(true)
    setError(null)
    runPatternScreen({ patterns, sort_by: sortByVal, order: orderVal, limit: PAGE_SIZE, offset })
      .then((data) => {
        setResult(data)
        setPage(Math.floor(offset / PAGE_SIZE))
      })
      .catch((e) => setError(e instanceof Error ? e.message : '筛选请求失败'))
      .finally(() => setLoading(false))
  }

  const togglePattern = (key: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const handleSort = (key: PatternSortField) => {
    if (key === sortBy) {
      setOrder((o) => (o === 'desc' ? 'asc' : 'desc'))
      doScreen([...selected], key, order === 'desc' ? 'asc' : 'desc', 0)
    } else {
      setSortBy(key)
      setOrder('desc')
      doScreen([...selected], key, 'desc', 0)
    }
  }

  const reset = () => {
    setSelected(new Set())
    setSearch('')
    setSortBy('pct_chg')
    setOrder('desc')
    setResult(null)
    setError(null)
  }

  const totalPages = result ? Math.max(1, Math.ceil(result.total / PAGE_SIZE)) : 1
  const sortIcon = (key: PatternSortField) => (key === sortBy ? (order === 'desc' ? ' ↓' : ' ↑') : '')

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>形态选股</h2>
          <p className="desc">
            K 线形态 / 量价关系 / 动量突破标签组合 · 交易日{' '}
            <code>{result?.trade_date ? formatTradeDate(result.trade_date) : '--'}</code>
          </p>
        </div>
      </div>

      <div className="screen-layout">
        {/* 左侧形态面板 */}
        <div className="panel side-panel">
          <div className="panel-head">
            <h6 className="panel-title">
              <span className="kicker" />
              形态条件
            </h6>
          </div>
          <div className="panel-body" style={{ maxHeight: 640, overflowY: 'auto' }}>
            <input
              type="text"
              className="form-control form-control-sm mb-3"
              placeholder="搜索形态名称…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {groupsError && <ErrorState message={groupsError} />}
            {filteredGroups.map((group) => (
              <div key={group.id} className="mb-3">
                <div className="side-group-label" style={{ padding: '2px 0 6px' }}>
                  {group.label} · {group.fields.length}
                </div>
                {group.fields.map((field) => (
                  <label
                    key={field.key}
                    className="d-flex align-items-center gap-2 py-1"
                    style={{ fontSize: 13, cursor: 'pointer' }}
                  >
                    <input
                      type="checkbox"
                      className="form-check-input mt-0"
                      checked={selected.has(field.key)}
                      onChange={() => togglePattern(field.key)}
                    />
                    <span style={{ flex: 1 }}>{field.label}</span>
                    <span className="chip">{field.count}</span>
                  </label>
                ))}
              </div>
            ))}
            {!groupsError && groups.length === 0 && <EmptyState icon="🧩" text="形态定义加载中" />}
          </div>
          <div className="panel-body d-flex gap-2" style={{ borderTop: '1px solid var(--border)' }}>
            <button
              type="button"
              className="btn btn-primary flex-grow-1"
              disabled={loading || selected.size === 0}
              onClick={() => doScreen([...selected], sortBy, order, 0)}
            >
              {loading ? '筛选中…' : `开始筛选 (${selected.size})`}
            </button>
            <button type="button" className="btn btn-outline-secondary" onClick={reset}>
              重置
            </button>
          </div>
        </div>

        {/* 右侧结果 */}
        <div className="flex-grow-1" style={{ minWidth: 0 }}>
          {loading && <Loading text="匹配形态中..." />}
          {error && <ErrorState message={error} onRetry={() => doScreen([...selected], sortBy, order, 0)} />}

          {result && !loading && !error && (
            <div className="panel">
              <div className="panel-head">
                <h6 className="panel-title">
                  <span className="kicker" />
                  匹配结果
                  <span className="chip">共 {result.total} 只 · 已选 {selected.size} 个形态</span>
                </h6>
              </div>
              <div className="panel-body tight table-container">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>代码</th>
                      <th>名称</th>
                      <th>行业</th>
                      {SORTABLE.map((c) => (
                        <th key={c.key} className="num sortable" onClick={() => handleSort(c.key)}>
                          {c.label}
                          {sortIcon(c.key)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.rows.map((row) => (
                      <tr key={row.ts_code}>
                        <td>
                          <code>{row.ts_code}</code>
                        </td>
                        <td style={{ fontWeight: 600 }}>{row.name}</td>
                        <td>{row.industry ?? '--'}</td>
                        <td className={`num ${pctClass(row.pct_chg)}`}>{formatPercent(row.pct_chg)}</td>
                        <td className="num">{formatNumber(row.close, 2)}</td>
                        <td className="num">{fmtAmountWan(row.amount)}</td>
                        <td className="num">{fmtAmountWan(row.total_mv)}</td>
                        <td className="num">{formatNumber(row.turnover_rate, 2)}%</td>
                        <td className="num">{formatNumber(row.vol_ratio_5, 2)}</td>
                      </tr>
                    ))}
                    {result.rows.length === 0 && (
                      <tr>
                        <td colSpan={9}>
                          <EmptyState icon="🔍" text="没有匹配的股票，试试减少形态条件" />
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              {totalPages > 1 && (
                <div className="panel-body d-flex align-items-center gap-2" style={{ borderTop: '1px solid var(--border)' }}>
                  <button
                    type="button"
                    className="btn btn-outline-secondary btn-sm"
                    disabled={page <= 0}
                    onClick={() => doScreen([...selected], sortBy, order, (page - 1) * PAGE_SIZE)}
                  >
                    上一页
                  </button>
                  <span className="chip">
                    第 {page + 1} / {totalPages} 页
                  </span>
                  <button
                    type="button"
                    className="btn btn-outline-secondary btn-sm"
                    disabled={page >= totalPages - 1}
                    onClick={() => doScreen([...selected], sortBy, order, (page + 1) * PAGE_SIZE)}
                  >
                    下一页
                  </button>
                </div>
              )}
              {result.rows.length > 0 && (
                <div className="panel-body" style={{ borderTop: '1px solid var(--border)' }}>
                  <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>点击列头可切换排序与方向</span>
                </div>
              )}
            </div>
          )}

          {!result && !loading && !error && (
            <EmptyState icon="🎯" text="在左侧勾选形态条件（多条件为 AND 组合），点击「开始筛选」" />
          )}
        </div>
      </div>
    </div>
  )
}
