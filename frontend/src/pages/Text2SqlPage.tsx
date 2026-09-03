import { useEffect, useMemo, useState } from 'react'
import EChart from '../charts/EChart'
import { fetchSqlHistory, fetchSqlSuggestions, runSqlQuery, type Text2SqlResult, type Text2SqlSuggestion } from '../api/ai'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { downloadCsv, formatNumber } from '../utils/format'

export default function Text2SqlPage() {
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState<Text2SqlSuggestion[]>([])
  const [result, setResult] = useState<Text2SqlResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [view, setView] = useState<'table' | 'chart'>('table')
  const [history, setHistory] = useState<Record<string, unknown>[]>([])
  const [showHistory, setShowHistory] = useState(false)

  useEffect(() => {
    fetchSqlSuggestions().then(setSuggestions).catch(() => setSuggestions([]))
  }, [])

  const run = async (text?: string) => {
    const q = (text ?? query).trim()
    if (!q) return
    setQuery(q)
    setLoading(true)
    setResult(null)
    try {
      const r = await runSqlQuery(q)
      setResult(r)
      if (r.error) setView('table')
    } catch (e) {
      setResult({ query: q, error: e instanceof Error ? e.message : '查询失败' })
    } finally {
      setLoading(false)
    }
  }

  const openHistory = async () => {
    setShowHistory(true)
    setHistory(await fetchSqlHistory(20).catch(() => []))
  }

  const rows = result?.data ?? []
  const columns = rows.length > 0 ? Object.keys(rows[0]) : []
  const chart = result?.chart_config

  const chartOption = useMemo(() => {
    if (!chart?.data || chart.data.length === 0) return null
    const labels = chart.data.map((d) => String(d[chart.x_field] ?? ''))
    const values = chart.data.map((d) => Number(d[chart.y_field] ?? 0))
    if (chart.type === 'pie') {
      return {
        tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
        legend: { type: 'scroll', bottom: 0 },
        series: [{ type: 'pie', radius: '50%', data: chart.data.map((d) => ({ name: String(d[chart.x_field] ?? ''), value: Number(d[chart.y_field] ?? 0) })) }],
      }
    }
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: 64, right: 20, top: 36, bottom: 56 },
      title: { text: chart.title, left: 'center', textStyle: { fontSize: 13 } },
      xAxis: { type: 'category', data: labels, name: chart.x_label, axisLabel: { rotate: Math.min(45, labels.length * 2) } },
      yAxis: { type: 'value', name: chart.y_label },
      series: [
        {
          type: (chart.type === 'line' ? 'line' : 'bar') as 'line' | 'bar',
          data: values,
          itemStyle: { color: '#818cf8' },
          ...(chart.type === 'line' ? { smooth: true, areaStyle: { opacity: 0.12, color: '#818cf8' } } : {}),
        },
      ],
    }
  }, [chart])

  const exportCsv = () => {
    if (rows.length === 0) return
    downloadCsv(`查询结果_${new Date().toISOString().slice(0, 10)}.csv`, columns, rows.map((r) => columns.map((c) => r[c] as string | number | null)))
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>智能查数（Text2SQL）</h2>
          <p className="desc">自然语言 → 只读 SQL → 表格 / 图表 / CSV</p>
        </div>
        <button type="button" className="btn btn-outline-secondary btn-sm" onClick={openHistory}>
          🕘 查询历史
        </button>
      </div>

      <div className="panel">
        <div className="panel-body">
          <textarea
            className="form-control"
            rows={2}
            placeholder="例如：查询市盈率最低的10只银行股（最多 500 字，回车或点击按钮查询）"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                run()
              }
            }}
          />
          <div className="d-flex align-items-center gap-2 mt-2 flex-wrap">
            <button type="button" className="btn btn-primary" disabled={loading || !query.trim()} onClick={() => run()}>
              {loading ? '查询中…' : '🔍 查询'}
            </button>
            {suggestions.slice(0, 6).map((s) => (
              <button key={s.text} type="button" className="chip" style={{ cursor: 'pointer' }} title={s.description} onClick={() => run(s.text)}>
                {s.text}
              </button>
            ))}
          </div>
        </div>
      </div>

      {loading && <Loading text="解析意图并执行只读 SQL..." />}

      {result && !loading && (
        <>
          {result.error ? (
            <ErrorState message={result.error} onRetry={() => run(result.query)} />
          ) : (
            <div className="row g-3">
              <div className="col-lg-4">
                <div className="panel h-100">
                  <div className="panel-head">
                    <h6 className="panel-title">
                      <span className="kicker" />
                      查询解析
                    </h6>
                  </div>
                  <div className="panel-body d-flex flex-column gap-2">
                    <div>
                      <span className="badge text-bg-primary">{result.intent?.name ?? '--'}</span>
                      <span className="chip ms-2">置信 {formatNumber((result.intent?.confidence ?? 0) * 100, 0)}%</span>
                    </div>
                    <div>
                      <div className="side-group-label">实体</div>
                      <code style={{ fontSize: 12, wordBreak: 'break-all' }}>{JSON.stringify(result.entities ?? {})}</code>
                    </div>
                    <div>
                      <div className="side-group-label">SQL</div>
                      <pre style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8, padding: 10, fontSize: 11.5, whiteSpace: 'pre-wrap', maxHeight: 220, overflow: 'auto' }}>
                        {result.sql}
                      </pre>
                    </div>
                    <div style={{ fontSize: 12.5, color: 'var(--text-dim)' }}>
                      {result.result_count ?? 0} 行 · 耗时 {formatNumber(result.execution_time, 1)} ms
                    </div>
                    {result.explanation && <div className="alert-note">{result.explanation}</div>}
                  </div>
                </div>
              </div>
              <div className="col-lg-8">
                <div className="panel h-100">
                  <div className="panel-head">
                    <h6 className="panel-title">
                      <span className="kicker" />
                      查询结果
                      <span className="chip">{rows.length} 行</span>
                    </h6>
                    <div className="d-flex gap-2 align-items-center">
                      <div className="seg" role="group">
                        <button type="button" className={`seg-item ${view === 'table' ? 'active' : ''}`} onClick={() => setView('table')}>
                          表格
                        </button>
                        <button type="button" className={`seg-item ${view === 'chart' ? 'active' : ''}`} onClick={() => setView('chart')} disabled={!chartOption}>
                          图表
                        </button>
                      </div>
                      <button type="button" className="btn btn-outline-primary btn-sm" onClick={exportCsv} disabled={rows.length === 0}>
                        导出 CSV ↓
                      </button>
                    </div>
                  </div>
                  <div className="panel-body">
                    {result.formatted_data?.summary && <div className="alert-note mb-2">{result.formatted_data.summary}</div>}
                    {view === 'table' ? (
                      <div className="table-container" style={{ maxHeight: 460 }}>
                        <table className="data-table">
                          <thead>
                            <tr>
                              {columns.map((c) => (
                                <th key={c}>{c}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {rows.slice(0, 200).map((row, i) => (
                              <tr key={i}>
                                {columns.map((c) => (
                                  <td key={c}>{row[c] === null || row[c] === undefined ? '--' : typeof row[c] === 'number' ? formatNumber(row[c] as number, 2) : String(row[c])}</td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        {rows.length === 0 && <EmptyState icon="📭" text="查询结果为空" />}
                      </div>
                    ) : chartOption ? (
                      <EChart option={chartOption} height={440} />
                    ) : (
                      <EmptyState icon="📊" text="无图表配置" />
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {!result && !loading && <EmptyState icon="💬" text="输入自然语言问题或点击示例开始查询" />}

      {showHistory && (
        <div className="modal d-block" style={{ background: 'rgba(0,0,0,0.45)' }} onClick={() => setShowHistory(false)}>
          <div className="modal-dialog modal-lg modal-dialog-scrollable" onClick={(e) => e.stopPropagation()}>
            <div className="modal-content" style={{ background: 'var(--surface)', color: 'var(--text)' }}>
              <div className="modal-header">
                <h5 className="modal-title">查询历史</h5>
                <button type="button" className="btn-close" onClick={() => setShowHistory(false)} />
              </div>
              <div className="modal-body">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>查询</th>
                      <th>时间</th>
                      <th className="num">耗时(ms)</th>
                      <th className="num">行数</th>
                      <th>状态</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((h, i) => (
                      <tr key={i}>
                        <td>{String(h.user_query ?? '')}</td>
                        <td>{String(h.created_at ?? '--')}</td>
                        <td className="num">{formatNumber(Number(h.execution_time ?? 0), 0)}</td>
                        <td className="num">{String(h.result_count ?? '--')}</td>
                        <td>{h.is_successful ? '✅' : '❌'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {history.length === 0 && <EmptyState icon="🕘" text="暂无查询历史" />}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
