import { useEffect, useMemo, useState } from 'react'
import EChart from '../charts/EChart'
import {
  createReportSubscription,
  createReportTemplate,
  dispatchSubscriptions,
  fetchReportStatistics,
  fetchReportSubscriptions,
  fetchReportTemplates,
  fetchReports,
  generateReport,
  type ReportItem,
  type ReportSection,
  type ReportStatistics,
  type ReportSubscription,
} from '../api/realtime'
import { fetchPortfolios } from '../api/mlFactor'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { formatDateTime, formatNumber } from '../utils/format'

const TABS = [
  { key: 'reports', label: '报告列表' },
  { key: 'templates', label: '模板管理' },
  { key: 'subs', label: '订阅管理' },
  { key: 'stats', label: '统计分析' },
] as const

type TabKey = (typeof TABS)[number]['key']
const REPORT_TYPES = ['daily_summary', 'market_overview', 'portfolio_analysis', 'risk_assessment']

function SectionRenderer({ section }: { section: ReportSection }) {
  const content = section.content
  if (section.type === 'chart' && content && typeof content === 'object') {
    const chart = content as { chart_type?: string; data?: { name: string; value: number }[] }
    const option =
      chart.chart_type === 'pie'
        ? { tooltip: { trigger: 'item' }, series: [{ type: 'pie', radius: '50%', data: chart.data ?? [] }] }
        : {
            tooltip: { trigger: 'axis' },
            xAxis: { type: 'category', data: (chart.data ?? []).map((d) => d.name) },
            yAxis: { type: 'value' },
            series: [{ type: 'bar', data: (chart.data ?? []).map((d) => d.value) }],
          }
    return (
      <div className="mb-3">
        <div className="side-group-label">{section.title ?? '图表'}</div>
        <EChart option={option} height={260} />
      </div>
    )
  }
  if (section.type === 'metrics' && Array.isArray(content)) {
    return (
      <div className="row g-2 mb-3">
        {(content as { value: number; format?: string; label: string }[]).map((m, i) => (
          <div className="col-md-3 col-6" key={i}>
            <div className="stat" style={{ padding: '10px 12px' }}>
              <div className="stat-value" style={{ fontSize: 17 }}>
                {formatNumber(m.value, 2)}
                {m.format === 'percent' ? '%' : ''}
              </div>
              <div className="stat-label">{m.label}</div>
            </div>
          </div>
        ))}
      </div>
    )
  }
  if (section.type === 'table' && content) {
    const table = Array.isArray(content)
      ? { columns: null, rows: content as Record<string, unknown>[] }
      : (content as { columns?: { label: string; key: string }[]; rows: Record<string, unknown>[] })
    const rows = table.rows ?? []
    const cols = table.columns ?? (rows[0] ? Object.keys(rows[0]).map((k) => ({ label: k, key: k })) : [])
    return (
      <div className="mb-3">
        <div className="side-group-label">{section.title ?? '表格'}</div>
        <div className="table-container" style={{ maxHeight: 260 }}>
          <table className="data-table">
            <thead>
              <tr>
                {cols.map((c) => (
                  <th key={c.key}>{c.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 30).map((row, i) => (
                <tr key={i}>
                  {cols.map((c) => (
                    <td key={c.key}>{String(row[c.key] ?? '--')}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    )
  }
  return (
    <div className="mb-3">
      {section.title && <div className="side-group-label">{section.title}</div>}
      <div style={{ whiteSpace: 'pre-wrap', fontSize: 13.5, lineHeight: 1.8 }}>{String(content ?? '')}</div>
    </div>
  )
}

export default function RtReportsPage() {
  const [tab, setTab] = useState<TabKey>('reports')
  const [reports, setReports] = useState<ReportItem[]>([])
  const [templates, setTemplates] = useState<Awaited<ReturnType<typeof fetchReportTemplates>>>([])
  const [subs, setSubs] = useState<ReportSubscription[]>([])
  const [stats, setStats] = useState<ReportStatistics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [typeFilter, setTypeFilter] = useState('')
  const [expanded, setExpanded] = useState<number | null>(null)
  const [msg, setMsg] = useState<string | null>(null)

  // 生成报告
  const [genType, setGenType] = useState(REPORT_TYPES[0])
  const [genName, setGenName] = useState('')
  const [genTemplate, setGenTemplate] = useState('')
  const [genPid, setGenPid] = useState('')
  const [genBusy, setGenBusy] = useState(false)

  // 新建模板 / 订阅
  const [tplForm, setTplForm] = useState({ template_name: '', template_type: 'daily_summary', description: '' })
  const [subForm, setSubForm] = useState({ subscription_name: '', template_id: '', subscriber_email: '', channels: 'email,log' })

  const loadAll = () => {
    setLoading(true)
    setError(null)
    Promise.all([fetchReports(), fetchReportTemplates(), fetchReportSubscriptions(), fetchReportStatistics()])
      .then(([r, t, s, st]) => {
        setReports(r)
        setTemplates(t)
        setSubs(s)
        setStats(st)
      })
      .catch((e) => setError(e instanceof Error ? e.message : '报告数据加载失败'))
      .finally(() => setLoading(false))
  }
  useEffect(loadAll, [])

  const filteredReports = typeFilter ? reports.filter((r) => r.report_type === typeFilter) : reports
  const portfolioReport = genType === 'portfolio_analysis' || genType === 'risk_assessment'
  const portfolios = useMemo(() => fetchPortfolios().then((r) => r.portfolios ?? []).catch(() => []), [])

  const handleGenerate = async () => {
    setGenBusy(true)
    setMsg(null)
    try {
      await generateReport({
        report_type: genType,
        template_id: genTemplate ? Number(genTemplate) : null,
        report_name: genName || `${genType}_${new Date().toISOString().slice(0, 10)}`,
        parameters: portfolioReport && genPid ? { portfolio_id: genPid } : {},
        generated_by: 'react-ui',
      })
      setMsg('报告生成请求已提交')
      setTimeout(loadAll, 1200)
    } catch (e) {
      setMsg(e instanceof Error ? e.message : '生成失败')
    } finally {
      setGenBusy(false)
    }
  }

  const handleCreateTemplate = async () => {
    setMsg(null)
    try {
      const r = await createReportTemplate({ ...tplForm, created_by: 'react-ui' })
      setMsg(r.success ? '模板已创建' : '创建失败')
      if (r.success) loadAll()
    } catch (e) {
      setMsg(e instanceof Error ? e.message : '创建失败')
    }
  }

  const handleCreateSub = async () => {
    setMsg(null)
    try {
      const r = await createReportSubscription({
        subscription_name: subForm.subscription_name,
        template_id: Number(subForm.template_id),
        subscriber_email: subForm.subscriber_email,
        schedule_type: 'daily',
        schedule_config: {},
        notification_channels: subForm.channels.split(',').map((c) => c.trim()).filter(Boolean),
        created_by: 'react-ui',
      })
      setMsg(r.success ? '订阅已创建' : '创建失败')
      if (r.success) loadAll()
    } catch (e) {
      setMsg(e instanceof Error ? e.message : '创建失败')
    }
  }

  const handleDispatch = async () => {
    setMsg(null)
    try {
      const r = await dispatchSubscriptions()
      setMsg(r.message ?? `已分发 ${r.dispatched ?? 0} 条订阅`)
      loadAll()
    } catch (e) {
      setMsg(e instanceof Error ? e.message : '分发失败')
    }
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>报告管理</h2>
          <p className="desc">报告生成 / 模板 / 订阅 / 统计</p>
        </div>
        <div className="d-flex gap-2 align-items-end flex-wrap">
          <input className="form-control form-control-sm w-auto" placeholder="报告名称（可空）" value={genName} onChange={(e) => setGenName(e.target.value)} />
          <select className="form-select form-select-sm w-auto" value={genType} onChange={(e) => setGenType(e.target.value)}>
            {REPORT_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <select className="form-select form-select-sm w-auto" value={genTemplate} onChange={(e) => setGenTemplate(e.target.value)}>
            <option value="">默认模板</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.template_name}
              </option>
            ))}
          </select>
          {portfolioReport && (
            <select className="form-select form-select-sm w-auto" value={genPid} onChange={(e) => setGenPid(e.target.value)}>
              <option value="">选择组合</option>
              {(Array.isArray(portfolios) ? portfolios : []).map((p) => (
                <option key={p.portfolio_id} value={p.portfolio_id}>
                  {p.name}
                </option>
              ))}
            </select>
          )}
          <button type="button" className="btn btn-primary btn-sm" disabled={genBusy || (portfolioReport && !genPid)} onClick={handleGenerate}>
            {genBusy ? '生成中…' : '生成报告'}
          </button>
          <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => setTab('templates')}>
            新建模板
          </button>
          <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => setTab('subs')}>
            新建订阅
          </button>
          <button type="button" className="btn btn-outline-secondary btn-sm" onClick={loadAll}>
            ⟳ 刷新
          </button>
        </div>
      </div>

      {msg && <div className="alert-note mb-3">{msg}</div>}
      {loading && <Loading text="加载报告数据..." />}
      {error && <ErrorState message={error} onRetry={loadAll} />}

      {stats && !loading && (
        <div className="stat-grid">
          <div className="stat">
            <div className="stat-value">{stats.reports.total}</div>
            <div className="stat-label">总报告</div>
            <div className="sub">成功率 {formatNumber(stats.reports.success_rate, 1)}%</div>
          </div>
          <div className="stat">
            <div className="stat-value">{stats.templates.total}</div>
            <div className="stat-label">总模板</div>
          </div>
          <div className="stat">
            <div className="stat-value">{stats.subscriptions.total}</div>
            <div className="stat-label">总订阅</div>
          </div>
          <div className="stat">
            <div className="stat-value">{formatNumber(stats.reports.success_rate, 1)}%</div>
            <div className="stat-label">报告成功率</div>
          </div>
        </div>
      )}

      <div className="seg mb-3" role="group" style={{ flexWrap: 'wrap' }}>
        {TABS.map((t) => (
          <button key={t.key} type="button" className={`seg-item ${tab === t.key ? 'active' : ''}`} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'reports' && (
        <div className="panel">
          <div className="panel-head">
            <h6 className="panel-title">
              <span className="kicker" />
              报告列表
              <span className="chip">{filteredReports.length} 份</span>
            </h6>
            <select className="form-select form-select-sm w-auto" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
              <option value="">全部类型</option>
              {[...new Set([...REPORT_TYPES, ...reports.map((r) => r.report_type)])].map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
          <div className="panel-body d-flex flex-column gap-2">
            {filteredReports.map((r) => (
              <div key={r.id} className="p-3 rounded" style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
                <div className="d-flex align-items-center gap-2 flex-wrap" role="button" onClick={() => setExpanded(expanded === r.id ? null : r.id)} style={{ cursor: 'pointer' }}>
                  <b>{r.report_name}</b>
                  <span className="chip">{r.report_type}</span>
                  <span className={`badge ${r.report_status === 'completed' ? 'text-bg-success' : r.report_status === 'failed' ? 'text-bg-danger' : 'text-bg-secondary'}`}>
                    {r.report_status}
                  </span>
                  <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>{formatDateTime(r.generated_at)}</span>
                  <span className="ms-auto">{expanded === r.id ? '▲' : '▼'}</span>
                </div>
                {expanded === r.id && (
                  <div className="mt-3 pt-3" style={{ borderTop: '1px solid var(--border)' }}>
                    {(r.report_content?.sections ?? []).map((sec, i) => (
                      <SectionRenderer section={sec} key={i} />
                    ))}
                    {(r.report_content?.sections ?? []).length === 0 && <EmptyState icon="📄" text="报告内容为空" />}
                  </div>
                )}
              </div>
            ))}
            {filteredReports.length === 0 && <EmptyState icon="📄" text="暂无报告，点击右上角「生成报告」" />}
          </div>
        </div>
      )}

      {tab === 'templates' && (
        <>
          <div className="panel">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                新建模板
              </h6>
            </div>
            <div className="panel-body">
              <div className="row g-3 align-items-end">
                <div className="col-lg-3 col-md-6">
                  <label className="form-label">模板名称</label>
                  <input type="text" className="form-control" value={tplForm.template_name} onChange={(e) => setTplForm({ ...tplForm, template_name: e.target.value })} />
                </div>
                <div className="col-lg-3 col-md-6">
                  <label className="form-label">模板类型</label>
                  <select className="form-select" value={tplForm.template_type} onChange={(e) => setTplForm({ ...tplForm, template_type: e.target.value })}>
                    {REPORT_TYPES.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="col-lg-4 col-md-6">
                  <label className="form-label">描述</label>
                  <input type="text" className="form-control" value={tplForm.description} onChange={(e) => setTplForm({ ...tplForm, description: e.target.value })} />
                </div>
                <div className="col-lg-2 col-md-6">
                  <button type="button" className="btn btn-primary w-100" onClick={handleCreateTemplate}>
                    创建模板
                  </button>
                </div>
              </div>
            </div>
          </div>
          <div className="panel">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                模板列表
                <span className="chip">{templates.length} 个</span>
              </h6>
            </div>
            <div className="panel-body tight table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>名称</th>
                    <th>类型</th>
                    <th>描述</th>
                  </tr>
                </thead>
                <tbody>
                  {templates.map((t) => (
                    <tr key={t.id}>
                      <td>#{t.id}</td>
                      <td style={{ fontWeight: 600 }}>{t.template_name}</td>
                      <td>{t.template_type}</td>
                      <td>{t.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {tab === 'subs' && (
        <>
          <div className="panel">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                新建订阅
              </h6>
              <button type="button" className="btn btn-outline-primary btn-sm" onClick={handleDispatch}>
                立即分发
              </button>
            </div>
            <div className="panel-body">
              <div className="row g-3 align-items-end">
                <div className="col-lg-2 col-md-6">
                  <label className="form-label">订阅名称</label>
                  <input type="text" className="form-control" value={subForm.subscription_name} onChange={(e) => setSubForm({ ...subForm, subscription_name: e.target.value })} />
                </div>
                <div className="col-lg-3 col-md-6">
                  <label className="form-label">模板</label>
                  <select className="form-select" value={subForm.template_id} onChange={(e) => setSubForm({ ...subForm, template_id: e.target.value })}>
                    <option value="">选择模板</option>
                    {templates.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.template_name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="col-lg-3 col-md-6">
                  <label className="form-label">邮箱</label>
                  <input type="email" className="form-control" value={subForm.subscriber_email} onChange={(e) => setSubForm({ ...subForm, subscriber_email: e.target.value })} />
                </div>
                <div className="col-lg-2 col-md-6">
                  <label className="form-label">通知渠道</label>
                  <input type="text" className="form-control" value={subForm.channels} onChange={(e) => setSubForm({ ...subForm, channels: e.target.value })} />
                </div>
                <div className="col-lg-2 col-md-6">
                  <button type="button" className="btn btn-primary w-100" onClick={handleCreateSub}>
                    创建订阅
                  </button>
                </div>
              </div>
            </div>
          </div>
          <div className="panel">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                订阅列表
                <span className="chip">{subs.length} 条</span>
              </h6>
            </div>
            <div className="panel-body tight table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>名称</th>
                    <th>模板</th>
                    <th>邮箱</th>
                    <th>下次发送</th>
                  </tr>
                </thead>
                <tbody>
                  {subs.map((s, i) => (
                    <tr key={`${s.subscription_name}-${i}`}>
                      <td style={{ fontWeight: 600 }}>{s.subscription_name}</td>
                      <td>{s.template_name ?? '--'}</td>
                      <td>{s.subscriber_email}</td>
                      <td>{formatDateTime(s.next_send_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {subs.length === 0 && <EmptyState icon="📨" text="暂无订阅" />}
            </div>
          </div>
        </>
      )}

      {tab === 'stats' && (
        <div className="row g-3">
          <div className="col-lg-6">
            <div className="panel h-100">
              <div className="panel-head">
                <h6 className="panel-title">
                  <span className="kicker" />
                  报告类型分布
                </h6>
              </div>
              <div className="panel-body">
                {Object.keys(stats?.report_type_stats ?? {}).length > 0 ? (
                  <EChart
                    option={{
                      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
                      legend: { type: 'scroll', bottom: 0 },
                      series: [{ type: 'pie', radius: '48%', data: Object.entries(stats?.report_type_stats ?? {}).map(([name, value]) => ({ name, value })) }],
                    }}
                    height={340}
                  />
                ) : (
                  <EmptyState icon="📊" text="暂无统计" />
                )}
              </div>
            </div>
          </div>
          <div className="col-lg-6">
            <div className="panel h-100">
              <div className="panel-head">
                <h6 className="panel-title">
                  <span className="kicker" />
                  统计概览
                </h6>
              </div>
              <div className="panel-body d-flex gap-2 flex-wrap">
                <span className="chip">报告完成 {stats?.reports.completed ?? '--'} / 失败 {stats?.reports.failed ?? '--'}</span>
                <span className="chip">活跃模板 {stats?.templates.active ?? '--'}</span>
                <span className="chip">活跃订阅 {stats?.subscriptions.active ?? '--'}</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
