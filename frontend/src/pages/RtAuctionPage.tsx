import { useCallback, useEffect, useState } from 'react'
import { EmptyState, ErrorState } from '../components/StateViews'
import {
  fetchAbnormalMonitor,
  fetchAuctionBenchmark,
  fetchAuctionOpportunities,
  fetchAuctionOpportunityDates,
  fetchAuctionSnapshot,
  fetchAnomalyAnalysis,
  fetchAnomalyAnalysisByStocks,
  AUCTION_MARKETS,
  type AbnormalMonitorData,
  type AuctionBenchmarkItem,
  type AuctionOpportunitiesData,
  type AuctionOpportunityDates,
  type AuctionSnapshotData,
  type AnomalyItem,
  type AnomalyTag,
} from '../api/rtAuction'
import { formatAmount, formatNumber, formatPercent, formatTradeDate, pctClass } from '../utils/format'

const TABS = [
  { key: 'snapshot', label: '竞价快照' },
  { key: 'opportunities', label: '竞价机会' },
  { key: 'benchmark', label: '竞价基准' },
  { key: 'abnormal', label: '异动股票' },
  { key: 'reasons', label: '异动原因' },
] as const
type TabKey = (typeof TABS)[number]['key']

const ANOMALY_TAGS: Array<{ value: AnomalyTag; label: string }> = [
  { value: 'LIMIT_UP', label: '涨停' },
  { value: 'LIMIT_DOWN', label: '跌停' },
  { value: 'SHARP_RISE', label: '大涨' },
  { value: 'SHARP_FALL', label: '大跌' },
  { value: 'RAPID_RALLY', label: '快速拉升' },
  { value: 'RAPID_DECLINE', label: '快速下挫' },
]

/** 代码输入容错：逗号/空格/换行/顿号分隔；6 位裸代码按首位自动补交易所后缀 */
function parseCodeInput(raw: string, limit = 100): string[] {
  const tokens = raw
    .split(/[\s,，;；、]+/)
    .map((t) => t.trim().toUpperCase())
    .filter(Boolean)
  const normalized = tokens.map((t) => {
    if (!/^\d{6}$/.test(t)) return t
    if (t.startsWith('6')) return `${t}.SH`
    if (t.startsWith('4') || t.startsWith('8')) return `${t}.BJ`
    return `${t}.SZ`
  })
  return [...new Set(normalized)].slice(0, limit)
}

function FreshChip({ data }: { data: { cached?: boolean; stale?: boolean } | null }) {
  if (!data) return null
  if (data.stale) return <span className="chip" title="上游异常，回供过期缓存">过期缓存</span>
  if (data.cached) return <span className="chip">缓存</span>
  return <span className="chip">实时</span>
}

// ================= 竞价快照 =================

function SnapshotTab() {
  const [input, setInput] = useState('600519.SH 000001.SZ 300750.SZ 688981.SH')
  const [stage, setStage] = useState<'live' | 'final'>('live')
  const [data, setData] = useState<AuctionSnapshotData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async (codesRaw: string, st: 'live' | 'final') => {
    const codes = parseCodeInput(codesRaw)
    if (codes.length === 0) {
      setError('请输入至少一个股票代码')
      setData(null)
      return
    }
    setLoading(true)
    try {
      setData(await fetchAuctionSnapshot(codes, st))
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : '竞价快照获取失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load(input, stage)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage])

  const rows = data?.items ?? []
  return (
    <div className="panel">
      <div className="panel-head">
        <h6 className="panel-title">
          <span className="kicker" />
          集合竞价快照
          <span className="chip">{rows.length} 只</span>
          {data?.auction_phase && <span className="chip">阶段 {data.auction_phase}</span>}
          <FreshChip data={data} />
        </h6>
        <div className="seg" role="group">
          <button type="button" className={`seg-item ${stage === 'live' ? 'active' : ''}`} onClick={() => setStage('live')}>
            实时
          </button>
          <button type="button" className={`seg-item ${stage === 'final' ? 'active' : ''}`} onClick={() => setStage('final')}>
            终态
          </button>
        </div>
      </div>
      <div className="panel-body">
        <div className="d-flex gap-2 flex-wrap align-items-center" style={{ marginBottom: 10 }}>
          <input
            className="form-control form-control-sm"
            style={{ maxWidth: 420, fontFamily: 'monospace' }}
            value={input}
            placeholder="支持 600519.SH / 600519，逗号或空格分隔，≤100 只"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && load(input, stage)}
          />
          <button type="button" className="btn btn-primary btn-sm" disabled={loading} onClick={() => load(input, stage)}>
            {loading ? '查询中…' : '查询'}
          </button>
        </div>
        {error && <ErrorState message={error} onRetry={() => load(input, stage)} />}
        {!error && (
          <div className="table-container" style={{ maxHeight: 520 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>代码</th>
                  <th>名称</th>
                  <th className="num">竞价价</th>
                  <th className="num">竞价涨幅</th>
                  <th className="num">竞价量</th>
                  <th className="num">竞价额</th>
                  <th className="num">未匹配量</th>
                  <th className="num">换手%</th>
                  <th className="num">量比</th>
                  <th className="num">前收</th>
                  <th className="num">最新价</th>
                  <th className="num">流通市值</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.ts_code}>
                    <td>
                      <code>{r.ts_code}</code>
                    </td>
                    <td style={{ fontWeight: 600 }}>{r.name ?? '--'}</td>
                    <td className="num">{formatNumber(r.auction_price, 2)}</td>
                    <td className={`num ${pctClass(r.auction_pct)}`}>{formatPercent(r.auction_pct)}</td>
                    <td className="num">{formatNumber(r.auction_volume, 0)}</td>
                    <td className="num">{formatAmount(r.auction_amount)}</td>
                    <td className="num">{formatNumber(r.auction_unmatched, 0)}</td>
                    <td className="num">{formatNumber(r.auction_turnover_pct, 2)}</td>
                    <td className="num">{formatNumber(r.auction_volume_ratio, 2)}</td>
                    <td className="num">{formatNumber(r.pre_close_price, 2)}</td>
                    <td className="num">{formatNumber(r.last_price, 2)}</td>
                    <td className="num">{formatAmount(r.float_market_cap)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {rows.length === 0 && <EmptyState icon="竞价" text={loading ? '加载中…' : '输入代码后查询集合竞价快照'} />}
          </div>
        )}
      </div>
    </div>
  )
}

// ================= 竞价机会 =================

function OpportunitiesTab() {
  const [dates, setDates] = useState<AuctionOpportunityDates | null>(null)
  const [date, setDate] = useState('') // 空=今日实时
  const [market, setMarket] = useState('a_share')
  const [excludeSt, setExcludeSt] = useState(false)
  const [page, setPage] = useState(1)
  const [data, setData] = useState<AuctionOpportunitiesData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    fetchAuctionOpportunityDates()
      .then(setDates)
      .catch(() => setDates(null))
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setData(await fetchAuctionOpportunities({ date: date || undefined, market, exclude_st: excludeSt, page }))
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : '竞价机会获取失败')
    } finally {
      setLoading(false)
    }
  }, [date, market, excludeSt, page])

  useEffect(() => {
    load()
  }, [load])

  const rows = data?.items ?? []
  return (
    <div className="panel">
      <div className="panel-head">
        <h6 className="panel-title">
          <span className="kicker" />
          集合竞价个股机会
          {data?.mode && <span className="chip">{data.mode === 'real_time' ? '实时' : '历史'}</span>}
          <span className="chip">共 {formatNumber(data?.total ?? null, 0)} 条</span>
          <FreshChip data={data} />
        </h6>
        <div className="d-flex align-items-center gap-2 flex-wrap">
          <select className="form-select form-select-sm" style={{ width: 150 }} value={date} onChange={(e) => { setDate(e.target.value); setPage(1) }}>
            <option value="">今日（实时）</option>
            {(dates?.dates ?? []).slice().reverse().map((d) => (
              <option key={d} value={d}>
                {formatTradeDate(d)}
              </option>
            ))}
          </select>
          <select className="form-select form-select-sm" style={{ width: 120 }} value={market} onChange={(e) => { setMarket(e.target.value); setPage(1) }}>
            {AUCTION_MARKETS.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
          <label className="d-flex align-items-center gap-1" style={{ fontSize: 13, cursor: 'pointer' }}>
            <input type="checkbox" className="form-check-input mt-0" checked={excludeSt} onChange={(e) => { setExcludeSt(e.target.checked); setPage(1) }} />
            剔除ST
          </label>
          <button type="button" className="btn btn-outline-secondary btn-sm" disabled={loading} onClick={load}>
            ⟳ 刷新
          </button>
        </div>
      </div>
      {error && <ErrorState message={error} onRetry={load} />}
      {!error && (
        <>
          <div className="panel-body tight table-container" style={{ maxHeight: 480 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>代码</th>
                  <th>名称</th>
                  <th>类型</th>
                  <th className="num">匹配价</th>
                  <th className="num">竞价涨幅</th>
                  <th className="num">竞价额</th>
                  <th className="num">昨日成交额</th>
                  <th>说明</th>
                  <th>评级</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={`${r.ts_code}-${r.warn_type}-${i}`}>
                    <td>{r.warn_time ?? '--'}</td>
                    <td>
                      <code>{r.ts_code}</code>
                    </td>
                    <td style={{ fontWeight: 600 }}>{r.name ?? '--'}</td>
                    <td>
                      <span className="chip">{r.warn_name ?? r.warn_type ?? '--'}</span>
                    </td>
                    <td className="num">{formatNumber(r.bid_price, 2)}</td>
                    <td className={`num ${pctClass(r.bid_pct)}`}>{formatPercent(r.bid_pct)}</td>
                    <td className="num">{formatAmount(r.bid_amount)}</td>
                    <td className="num">{formatAmount(r.previous_amount)}</td>
                    <td style={{ maxWidth: 260 }}>{r.explain ?? '--'}</td>
                    <td>{r.grade ?? '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {rows.length === 0 && <EmptyState icon="🎯" text={loading ? '加载中…' : '当前条件下暂无竞价机会记录'} />}
          </div>
          <div className="d-flex align-items-center gap-2 justify-content-end" style={{ padding: '8px 12px' }}>
            <button type="button" className="btn btn-outline-secondary btn-sm" disabled={loading || page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
              上一页
            </button>
            <span style={{ fontSize: 13 }}>
              第 {data?.page ?? page} 页 / 共 {formatNumber(data?.total ?? null, 0)} 条
            </span>
            <button type="button" className="btn btn-outline-secondary btn-sm" disabled={loading || !data?.has_next} onClick={() => setPage((p) => p + 1)}>
              下一页
            </button>
          </div>
        </>
      )}
    </div>
  )
}

// ================= 竞价基准 =================

function BenchmarkTab() {
  const [date, setDate] = useState('')
  const [items, setItems] = useState<AuctionBenchmarkItem[]>([])
  const [queryDate, setQueryDate] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async (d: string) => {
    setLoading(true)
    try {
      const data = await fetchAuctionBenchmark(d || undefined)
      setItems(data.item ?? [])
      setQueryDate(data.date ?? null)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : '竞价基准获取失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load('')
  }, [load])

  return (
    <div className="panel">
      <div className="panel-head">
        <h6 className="panel-title">
          <span className="kicker" />
          短线风向标竞价基准
          <span className="chip">{items.length} 只</span>
          {queryDate && <span className="chip">{formatTradeDate(queryDate)}</span>}
        </h6>
        <div className="d-flex align-items-center gap-2">
          <input
            type="date"
            className="form-control form-control-sm"
            style={{ width: 160 }}
            value={date}
            onChange={(e) => {
              setDate(e.target.value)
              load(e.target.value)
            }}
          />
          {date && (
            <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => { setDate(''); load('') }}>
              回到今日
            </button>
          )}
        </div>
      </div>
      {error && <ErrorState message={error} onRetry={() => load(date)} />}
      {!error && (
        <div className="panel-body tight table-container" style={{ maxHeight: 520 }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>代码</th>
                <th>名称</th>
                <th className="num">竞价涨幅</th>
                <th>标签</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.thscode}>
                  <td>
                    <code>{r.thscode}</code>
                  </td>
                  <td style={{ fontWeight: 600 }}>{r.name ?? '--'}</td>
                  <td className={`num ${pctClass(r.auction_pct ?? null)}`}>{formatPercent(r.auction_pct ?? null)}</td>
                  <td>
                    <span className="d-flex gap-1 flex-wrap">
                      {(r.tags ?? []).map((t) => (
                        <span key={t} className="chip">
                          {t}
                        </span>
                      ))}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {items.length === 0 && <EmptyState icon="🧭" text={loading ? '加载中…' : '暂无竞价基准数据'} />}
        </div>
      )}
    </div>
  )
}

// ================= 异动股票 =================

function AbnormalTab() {
  const [state, setState] = useState<'current' | 'history'>('current')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<AbnormalMonitorData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setData(await fetchAbnormalMonitor(state, page, 30))
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : '异动股票获取失败')
    } finally {
      setLoading(false)
    }
  }, [state, page])

  useEffect(() => {
    load()
  }, [load])

  const rows = data?.items ?? []
  return (
    <div className="panel">
      <div className="panel-head">
        <h6 className="panel-title">
          <span className="kicker" />
          异动股票监控名单
          <span className="chip">共 {formatNumber(data?.total ?? null, 0)} 只</span>
          <FreshChip data={data} />
        </h6>
        <div className="seg" role="group">
          <button type="button" className={`seg-item ${state === 'current' ? 'active' : ''}`} onClick={() => { setState('current'); setPage(1) }}>
            当前监控
          </button>
          <button type="button" className={`seg-item ${state === 'history' ? 'active' : ''}`} onClick={() => { setState('history'); setPage(1) }}>
            历史
          </button>
        </div>
      </div>
      {error && <ErrorState message={error} onRetry={load} />}
      {!error && (
        <>
          <div className="panel-body tight table-container" style={{ maxHeight: 480 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>代码</th>
                  <th>名称</th>
                  <th>类型</th>
                  <th className="num">监控类型码</th>
                  <th>开始日期</th>
                  <th>结束日期</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={`${r.ts_code}-${r.start_date}-${i}`}>
                    <td>
                      <code>{r.ts_code ?? '--'}</code>
                    </td>
                    <td style={{ fontWeight: 600 }}>{r.name ?? '--'}</td>
                    <td>
                      <span className={`chip ${r.severe ? 'text-up' : ''}`}>{r.severe ? '严重异动' : '重点监控'}</span>
                    </td>
                    <td className="num">{r.monitor_type ?? '--'}</td>
                    <td>{formatTradeDate(r.start_date)}</td>
                    <td>{r.end_date ? formatTradeDate(r.end_date) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {rows.length === 0 && <EmptyState icon="🚨" text={loading ? '加载中…' : '暂无监控名单'} />}
          </div>
          <div className="d-flex align-items-center gap-2 justify-content-end" style={{ padding: '8px 12px' }}>
            <button type="button" className="btn btn-outline-secondary btn-sm" disabled={loading || page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
              上一页
            </button>
            <span style={{ fontSize: 13 }}>第 {data?.page ?? page} 页</span>
            <button type="button" className="btn btn-outline-secondary btn-sm" disabled={loading || !data?.has_next} onClick={() => setPage((p) => p + 1)}>
              下一页
            </button>
          </div>
        </>
      )}
    </div>
  )
}

// ================= 异动原因 =================

function ReasonsTab() {
  const [tags, setTags] = useState<AnomalyTag[]>([])
  const [items, setItems] = useState<AnomalyItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [codeInput, setCodeInput] = useState('')
  const [byStocks, setByStocks] = useState(false)

  const load = useCallback(async (selected: AnomalyTag[], stockQuery: boolean, raw: string) => {
    setLoading(true)
    try {
      if (stockQuery) {
        const codes = parseCodeInput(raw, 50)
        if (codes.length === 0) throw new Error('请输入至少一个股票代码')
        const data = await fetchAnomalyAnalysisByStocks(codes)
        setItems(data.items ?? [])
      } else {
        const data = await fetchAnomalyAnalysis(selected.length ? selected : undefined)
        setItems(data.items ?? [])
      }
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : '异动原因获取失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load([], false, '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const toggleTag = (tag: AnomalyTag) => {
    setByStocks(false)
    const next = tags.includes(tag) ? tags.filter((t) => t !== tag) : [...tags, tag]
    setTags(next)
    load(next, false, '')
  }

  return (
    <div className="panel">
      <div className="panel-head">
        <h6 className="panel-title">
          <span className="kicker" />
          个股异动原因（当日）
          <span className="chip">{items.length} 条</span>
        </h6>
        <div className="d-flex gap-2 align-items-center flex-wrap">
          <input
            className="form-control form-control-sm"
            style={{ maxWidth: 320, fontFamily: 'monospace' }}
            value={codeInput}
            placeholder="按股票查询：600519.SH 000001.SZ（≤50 只）"
            onChange={(e) => setCodeInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                setByStocks(true)
                setTags([])
                load([], true, codeInput)
              }
            }}
          />
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={loading}
            onClick={() => {
              setByStocks(true)
              setTags([])
              load([], true, codeInput)
            }}
          >
            查询
          </button>
        </div>
      </div>
      <div className="panel-body">
        <div className="seg" role="group" style={{ marginBottom: 10 }}>
          {ANOMALY_TAGS.map((t) => (
            <button key={t.value} type="button" className={`seg-item ${tags.includes(t.value) ? 'active' : ''}`} onClick={() => toggleTag(t.value)}>
              {t.label}
            </button>
          ))}
        </div>
        {error && <ErrorState message={error} onRetry={() => load(tags, byStocks, codeInput)} />}
        {!error && (
          <div className="table-container" style={{ maxHeight: 480 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>代码</th>
                  <th>名称</th>
                  <th>标签</th>
                  <th>关键词</th>
                  <th>解读</th>
                </tr>
              </thead>
              <tbody>
                {items.map((r, i) => (
                  <tr key={`${r.ts_code}-${i}`}>
                    <td>
                      <code>{r.ts_code}</code>
                    </td>
                    <td style={{ fontWeight: 600 }}>{r.name ?? '--'}</td>
                    <td>
                      <span className="chip">{r.tag ?? '--'}</span>
                    </td>
                    <td>
                      <span className="d-flex gap-1 flex-wrap">
                        {(r.keywords ?? []).map((k) => (
                          <span key={k} className="chip">
                            {k}
                          </span>
                        ))}
                      </span>
                    </td>
                    <td style={{ maxWidth: 420 }}>{r.content ?? '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {items.length === 0 && <EmptyState icon="💬" text={loading ? '加载中…' : '当日暂无异动解读'} />}
          </div>
        )}
      </div>
    </div>
  )
}

// ================= 页面 =================

export default function RtAuctionPage() {
  const [tab, setTab] = useState<TabKey>('snapshot')
  return (
    <div>
      <div className="page-head">
        <div>
          <h2>竞价与异动</h2>
          <p className="desc">集合竞价快照与个股机会 · 短线风向标基准 · 异动股票监控与异动解读（数据来自同花顺扶摇）</p>
        </div>
        <div className="seg" role="group">
          {TABS.map((t) => (
            <button key={t.key} type="button" className={`seg-item ${tab === t.key ? 'active' : ''}`} onClick={() => setTab(t.key)}>
              {t.label}
            </button>
          ))}
        </div>
      </div>
      {tab === 'snapshot' && <SnapshotTab />}
      {tab === 'opportunities' && <OpportunitiesTab />}
      {tab === 'benchmark' && <BenchmarkTab />}
      {tab === 'abnormal' && <AbnormalTab />}
      {tab === 'reasons' && <ReasonsTab />}
    </div>
  )
}
