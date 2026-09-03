import { useEffect, useMemo, useState } from 'react'
import { OLD_SITE_BASE } from '../App'
import { fetchAreas, fetchIndustries } from '../api/stocks'
import { runScreen } from '../api/analysis'
import type { DynamicCondition, ScreenCriteria, ScreenResultData } from '../api/types'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { formatNumber, formatPercent, pctClass, toLocalDate } from '../utils/format'

const OPERATORS = ['>', '>=', '<', '<=', '=', '!='] as const
const VALUE_SENTINEL = '__value__'
const TEMPLATE_KEY = 'screenTemplates'

const NUMERIC_FIELDS: { group: string; fields: { key: string; label: string }[] }[] = [
  {
    group: '基本信息',
    fields: [
      { key: 'daily_close', label: '收盘价' },
      { key: 'factor_change', label: '涨跌额' },
      { key: 'factor_pct_change', label: '涨跌幅' },
    ],
  },
  {
    group: '估值指标',
    fields: [
      { key: 'pe', label: 'PE' },
      { key: 'pe_ttm', label: 'PE(TTM)' },
      { key: 'pb', label: 'PB' },
      { key: 'ps', label: 'PS' },
      { key: 'ps_ttm', label: 'PS(TTM)' },
      { key: 'dv_ratio', label: '股息率' },
      { key: 'dv_ttm', label: '股息率(TTM)' },
    ],
  },
  {
    group: '市值交易',
    fields: [
      { key: 'total_mv', label: '总市值(万)' },
      { key: 'circ_mv', label: '流通市值(万)' },
      { key: 'turnover_rate', label: '换手率' },
      { key: 'turnover_rate_f', label: '换手率(自由流通)' },
      { key: 'volume_ratio', label: '量比' },
      { key: 'factor_vol', label: '成交量' },
      { key: 'factor_amount', label: '成交额' },
    ],
  },
  {
    group: '技术指标',
    fields: [
      { key: 'factor_macd_dif', label: 'MACD DIF' },
      { key: 'factor_macd_dea', label: 'MACD DEA' },
      { key: 'factor_macd', label: 'MACD' },
      { key: 'factor_kdj_k', label: 'KDJ K' },
      { key: 'factor_kdj_d', label: 'KDJ D' },
      { key: 'factor_kdj_j', label: 'KDJ J' },
      { key: 'factor_rsi_6', label: 'RSI6' },
      { key: 'factor_rsi_12', label: 'RSI12' },
      { key: 'factor_rsi_24', label: 'RSI24' },
      { key: 'factor_boll_upper', label: 'BOLL上轨' },
      { key: 'factor_boll_mid', label: 'BOLL中轨' },
      { key: 'factor_boll_lower', label: 'BOLL下轨' },
      { key: 'factor_cci', label: 'CCI' },
    ],
  },
  {
    group: '均线指标',
    fields: [
      { key: 'ma5', label: 'MA5' },
      { key: 'ma10', label: 'MA10' },
      { key: 'ma20', label: 'MA20' },
      { key: 'ma30', label: 'MA30' },
      { key: 'ma60', label: 'MA60' },
      { key: 'ma120', label: 'MA120' },
    ],
  },
  {
    group: '资金流向',
    fields: [
      { key: 'moneyflow_net_amount', label: '净流入额(万)' },
      { key: 'moneyflow_buy_lg_amount', label: '特大单买入(万)' },
      { key: 'moneyflow_buy_md_amount', label: '大单买入(万)' },
      { key: 'moneyflow_buy_md_amount_rate', label: '大单买入占比' },
      { key: 'moneyflow_buy_sm_amount', label: '小单买入(万)' },
      { key: 'moneyflow_buy_sm_amount_rate', label: '小单买入占比' },
    ],
  },
]

const FIELD_LABELS = new Map(NUMERIC_FIELDS.flatMap((g) => g.fields).map((f) => [f.key, f.label]))

interface FormState {
  industry: string
  area: string
  market: '' | 'SZ' | 'SH'
  trade_date: string
  pe_min: string
  pe_max: string
  pb_min: string
  pb_max: string
  ps_min: string
  ps_max: string
  dv_min: string
  dv_max: string
  mv_min: string
  mv_max: string
  circ_mv_min: string
  circ_mv_max: string
  turnover_min: string
  turnover_max: string
  volume_ratio_min: string
  volume_ratio_max: string
  rsi6_min: string
  rsi6_max: string
  kdj_k_min: string
  kdj_k_max: string
  macd_min: string
  macd_max: string
  cci_min: string
  cci_max: string
  net_amount_min: string
  net_amount_max: string
}

const EMPTY_FORM: FormState = {
  industry: '', area: '', market: '', trade_date: '',
  pe_min: '', pe_max: '', pb_min: '', pb_max: '', ps_min: '', ps_max: '', dv_min: '', dv_max: '',
  mv_min: '', mv_max: '', circ_mv_min: '', circ_mv_max: '', turnover_min: '', turnover_max: '',
  volume_ratio_min: '', volume_ratio_max: '',
  rsi6_min: '', rsi6_max: '', kdj_k_min: '', kdj_k_max: '', macd_min: '', macd_max: '', cci_min: '', cci_max: '',
  net_amount_min: '', net_amount_max: '',
}

interface TemplateEntry {
  name: string
  conditions: FormState & { dynamic_conditions?: DynamicCondition[] }
  created_at: string
}

function loadTemplates(): TemplateEntry[] {
  try {
    return JSON.parse(localStorage.getItem(TEMPLATE_KEY) ?? '[]') as TemplateEntry[]
  } catch {
    return []
  }
}

/** 只把有值的字段拼进请求体（数字以字符串提交，与旧版一致） */
function buildCriteria(form: FormState, dynamics: DynamicCondition[]): ScreenCriteria {
  const criteria: Record<string, string> = {}
  for (const [key, value] of Object.entries(form)) {
    if (value !== '') criteria[key] = value
  }
  const result = criteria as unknown as ScreenCriteria
  if (dynamics.length > 0) result.dynamic_conditions = dynamics
  return result
}

function formatCriteria(form: FormState, dynamics: DynamicCondition[]): string {
  const parts: string[] = []
  if (form.industry) parts.push(`行业=${form.industry}`)
  if (form.area) parts.push(`地域=${form.area}`)
  if (form.market) parts.push(`市场=${form.market === 'SZ' ? '深圳' : '上海'}`)
  if (form.trade_date) parts.push(`日期=${form.trade_date}`)
  const ranges: [string, string, string][] = [
    ['PE', 'pe_min', 'pe_max'],
    ['PB', 'pb_min', 'pb_max'],
    ['PS', 'ps_min', 'ps_max'],
    ['股息率', 'dv_min', 'dv_max'],
    ['总市值(万)', 'mv_min', 'mv_max'],
    ['流通市值(万)', 'circ_mv_min', 'circ_mv_max'],
    ['换手率%', 'turnover_min', 'turnover_max'],
    ['量比', 'volume_ratio_min', 'volume_ratio_max'],
    ['RSI6', 'rsi6_min', 'rsi6_max'],
    ['KDJ-K', 'kdj_k_min', 'kdj_k_max'],
    ['MACD', 'macd_min', 'macd_max'],
    ['CCI', 'cci_min', 'cci_max'],
    ['净流入(万)', 'net_amount_min', 'net_amount_max'],
  ]
  for (const [label, minKey, maxKey] of ranges) {
    const min = form[minKey as keyof FormState]
    const max = form[maxKey as keyof FormState]
    if (min !== '' || max !== '') {
      parts.push(`${label} ${min || '-∞'} ~ ${max || '+∞'}`)
    }
  }
  for (const cond of dynamics) {
    const label = FIELD_LABELS.get(cond.field_a) ?? cond.field_a
    if (cond.field_b === null || cond.field_b === undefined) {
      parts.push(`${label} ${cond.operator} ${cond.value ?? ''}`)
    } else {
      parts.push(`${label} ${cond.operator} ${FIELD_LABELS.get(cond.field_b) ?? cond.field_b}`)
    }
  }
  return parts.length > 0 ? parts.join('；') : '未设置条件'
}

function exportCsv(data: ScreenResultData) {
  const headers = ['股票代码', '股票名称', '行业', '地域', '收盘价', '涨跌幅%', 'PE', 'PB', '总市值(万)', '换手率%', '净流入(万)', '数据日期']
  const lines = data.stocks.map((row) =>
    [
      row.ts_code,
      row.name,
      row.industry ?? '',
      row.area ?? '',
      row.daily_close ?? row.close ?? '',
      row.factor_pct_change ?? '',
      row.pe ?? '',
      row.pb ?? '',
      row.total_mv ?? '',
      row.turnover_rate ?? '',
      row.moneyflow_net_amount ?? '',
      row.trade_date ?? '',
    ]
      .map((v) => `"${String(v).replace(/"/g, '""')}"`)
      .join(','),
  )
  const csv = '\uFEFF' + headers.join(',') + '\n' + lines.join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `股票筛选结果_${toLocalDate(new Date())}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

export default function ScreenPage() {
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [dynamics, setDynamics] = useState<DynamicCondition[]>([])
  const [industries, setIndustries] = useState<string[]>([])
  const [areas, setAreas] = useState<string[]>([])
  const [templates, setTemplates] = useState<TemplateEntry[]>([])
  const [selectedTemplate, setSelectedTemplate] = useState('')
  const [result, setResult] = useState<ScreenResultData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchIndustries().then(setIndustries).catch(() => setIndustries([]))
    fetchAreas().then(setAreas).catch(() => setAreas([]))
    setTemplates(loadTemplates())
  }, [])

  const setField = (key: keyof FormState, value: string) => setForm((prev) => ({ ...prev, [key]: value }))

  const handleScreen = async (e?: React.FormEvent) => {
    e?.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const data = await runScreen(buildCriteria(form, dynamics))
      setResult(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : '筛选请求失败')
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  const handleReset = () => {
    setForm(EMPTY_FORM)
    setDynamics([])
    setResult(null)
    setError(null)
  }

  const handleSaveTemplate = () => {
    const name = window.prompt('请输入模板名称：')
    if (!name) return
    const entry: TemplateEntry = {
      name,
      conditions: { ...form, dynamic_conditions: dynamics },
      created_at: new Date().toISOString(),
    }
    const next = [...loadTemplates().filter((t) => t.name !== name), entry]
    localStorage.setItem(TEMPLATE_KEY, JSON.stringify(next))
    setTemplates(next)
    setSelectedTemplate(name)
  }

  const handleLoadTemplate = () => {
    const entry = templates.find((t) => t.name === selectedTemplate)
    if (!entry) return
    const { dynamic_conditions, ...rest } = entry.conditions
    setForm({ ...EMPTY_FORM, ...rest })
    setDynamics(dynamic_conditions ?? [])
  }

  const handleDeleteTemplate = () => {
    if (!selectedTemplate) return
    const next = loadTemplates().filter((t) => t.name !== selectedTemplate)
    localStorage.setItem(TEMPLATE_KEY, JSON.stringify(next))
    setTemplates(next)
    setSelectedTemplate('')
  }

  const updateDynamic = (index: number, patch: Partial<DynamicCondition>) => {
    setDynamics((prev) => prev.map((row, i) => (i === index ? { ...row, ...patch } : row)))
  }

  const summary = useMemo(() => formatCriteria(form, dynamics), [form, dynamics])

  const rangeInput = (label: string, minKey: keyof FormState, maxKey: keyof FormState) => (
    <div className="col-xl-3 col-md-6">
      <label className="form-label">{label}</label>
      <div className="d-flex gap-2">
        <input
          type="number"
          className="form-control"
          placeholder="最小"
          value={form[minKey]}
          onChange={(e) => setField(minKey, e.target.value)}
        />
        <input
          type="number"
          className="form-control"
          placeholder="最大"
          value={form[maxKey]}
          onChange={(e) => setField(maxKey, e.target.value)}
        />
      </div>
    </div>
  )

  const fieldGroupSelect = (value: string, onChange: (v: string) => void) => (
    <select className="form-select" value={value} onChange={(e) => onChange(e.target.value)}>
      {NUMERIC_FIELDS.map((group) => (
        <optgroup key={group.group} label={group.group}>
          {group.fields.map((f) => (
            <option key={f.key} value={f.key}>
              {f.label}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  )

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>选股筛选</h2>
          <p className="desc">估值、市值、技术指标多条件组合，支持动态条件、模板与 CSV 导出</p>
        </div>
      </div>

      <form onSubmit={handleScreen}>
        <div className="panel">
          <div className="panel-head">
            <h6 className="panel-title">
              <span className="kicker" />
              基本条件
            </h6>
          </div>
          <div className="panel-body">
            <div className="row g-3">
              <div className="col-xl-3 col-md-6">
                <label className="form-label">行业</label>
                <select className="form-select" value={form.industry} onChange={(e) => setField('industry', e.target.value)}>
                  <option value="">全部行业</option>
                  {industries.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </div>
              <div className="col-xl-3 col-md-6">
                <label className="form-label">地域</label>
                <select className="form-select" value={form.area} onChange={(e) => setField('area', e.target.value)}>
                  <option value="">全部地域</option>
                  {areas.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </div>
              <div className="col-xl-3 col-md-6">
                <label className="form-label">市场</label>
                <select className="form-select" value={form.market} onChange={(e) => setField('market', e.target.value)}>
                  <option value="">全部市场</option>
                  <option value="SZ">深圳</option>
                  <option value="SH">上海</option>
                </select>
              </div>
              <div className="col-xl-3 col-md-6">
                <label className="form-label">数据日期（留空取最新）</label>
                <input type="date" className="form-control" value={form.trade_date} onChange={(e) => setField('trade_date', e.target.value)} />
              </div>
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <h6 className="panel-title">
              <span className="kicker" />
              估值指标
            </h6>
          </div>
          <div className="panel-body">
            <div className="row g-3">
              {rangeInput('PE', 'pe_min', 'pe_max')}
              {rangeInput('PB', 'pb_min', 'pb_max')}
              {rangeInput('PS', 'ps_min', 'ps_max')}
              {rangeInput('股息率(%)', 'dv_min', 'dv_max')}
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <h6 className="panel-title">
              <span className="kicker" />
              市值与交易
            </h6>
          </div>
          <div className="panel-body">
            <div className="row g-3">
              {rangeInput('总市值(万)', 'mv_min', 'mv_max')}
              {rangeInput('流通市值(万)', 'circ_mv_min', 'circ_mv_max')}
              {rangeInput('换手率(%)', 'turnover_min', 'turnover_max')}
              {rangeInput('量比', 'volume_ratio_min', 'volume_ratio_max')}
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <h6 className="panel-title">
              <span className="kicker" />
              技术指标与资金流
            </h6>
          </div>
          <div className="panel-body">
            <div className="row g-3">
              {rangeInput('RSI(6日)', 'rsi6_min', 'rsi6_max')}
              {rangeInput('KDJ-K', 'kdj_k_min', 'kdj_k_max')}
              {rangeInput('MACD', 'macd_min', 'macd_max')}
              {rangeInput('CCI', 'cci_min', 'cci_max')}
              {rangeInput('净流入额(万)', 'net_amount_min', 'net_amount_max')}
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <h6 className="panel-title">
              <span className="kicker" />
              动态查询条件
              <span className="chip">字段间比较，如 MA5 &gt; 收盘价</span>
            </h6>
            <button
              type="button"
              className="btn btn-outline-primary btn-sm"
              onClick={() => setDynamics([...dynamics, { field_a: 'daily_close', operator: '>', field_b: null, value: '' }])}
            >
              + 添加条件
            </button>
          </div>
          <div className="panel-body">
            {dynamics.length === 0 && <EmptyState icon="🧩" text="未添加动态条件" />}
            {dynamics.map((row, index) => (
              <div className="row g-2 align-items-center mb-2" key={index}>
                <div className="col-md-4">{fieldGroupSelect(row.field_a, (v) => updateDynamic(index, { field_a: v }))}</div>
                <div className="col-md-2">
                  <select
                    className="form-select"
                    value={row.operator}
                    onChange={(e) => updateDynamic(index, { operator: e.target.value as DynamicCondition['operator'] })}
                  >
                    {OPERATORS.map((op) => (
                      <option key={op} value={op}>
                        {op}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="col-md-4">
                  {fieldGroupSelect(row.field_b ?? VALUE_SENTINEL, (v) => {
                    updateDynamic(index, v === VALUE_SENTINEL ? { field_b: null, value: row.value ?? '' } : { field_b: v, value: null })
                  })}
                </div>
                {(row.field_b === null || row.field_b === undefined) && (
                  <div className="col-md-1">
                    <input
                      type="number"
                      className="form-control"
                      placeholder="数值"
                      value={row.value ?? ''}
                      onChange={(e) => updateDynamic(index, { value: e.target.value })}
                    />
                  </div>
                )}
                <div className="col-md-1">
                  <button
                    type="button"
                    className="btn btn-outline-danger btn-sm w-100"
                    onClick={() => setDynamics(dynamics.filter((_, i) => i !== index))}
                  >
                    删除
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="d-flex gap-2 flex-wrap mb-4 align-items-center">
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? '筛选中…' : '🔍 开始筛选'}
          </button>
          <button type="button" className="btn btn-outline-secondary" onClick={handleReset}>
            重置
          </button>
          <div className="seg" role="group">
            <button type="button" className="seg-item" onClick={handleSaveTemplate}>
              保存模板
            </button>
            <button type="button" className={`seg-item ${selectedTemplate ? '' : 'disabled'}`} onClick={handleLoadTemplate}>
              加载模板
            </button>
            <button type="button" className={`seg-item ${selectedTemplate ? '' : 'disabled'}`} onClick={handleDeleteTemplate}>
              删除模板
            </button>
          </div>
          <select className="form-select w-auto" value={selectedTemplate} onChange={(e) => setSelectedTemplate(e.target.value)}>
            <option value="">选择模板…</option>
            {templates.map((t) => (
              <option key={t.name} value={t.name}>
                {t.name}
              </option>
            ))}
          </select>
        </div>
      </form>

      {loading && <Loading text="筛选中..." />}
      {error && <ErrorState message={error} onRetry={() => handleScreen()} />}

      {result && !loading && (
        <div className="panel">
          <div className="panel-head">
            <h6 className="panel-title">
              <span className="kicker" />
              筛选结果
              <span className="chip">共 {result.total} 只</span>
              {result.has_more && <span className="alert-note py-1">仅展示前 200 条，请缩小范围</span>}
            </h6>
            {result.stocks.length > 0 && (
              <button type="button" className="btn btn-outline-primary btn-sm" onClick={() => exportCsv(result)}>
                导出 CSV ↓
              </button>
            )}
          </div>
          <div className="panel-body">
            <div className="chip mb-3" style={{ whiteSpace: 'normal', lineHeight: 1.8 }}>
              条件：{summary}
            </div>
            {result.error && <ErrorState message={result.error} />}
            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>股票代码</th>
                    <th>股票名称</th>
                    <th>行业</th>
                    <th>地域</th>
                    <th className="num">收盘价</th>
                    <th className="num">涨跌幅%</th>
                    <th className="num">PE</th>
                    <th className="num">PB</th>
                    <th className="num">总市值(万)</th>
                    <th className="num">换手率%</th>
                    <th className="num">净流入(万)</th>
                    <th>数据日期</th>
                    <th className="num">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {result.stocks.map((row) => (
                    <tr key={row.ts_code}>
                      <td>
                        <code>{row.symbol}</code>
                      </td>
                      <td style={{ fontWeight: 600 }}>{row.name}</td>
                      <td>{row.industry ?? '--'}</td>
                      <td>{row.area ?? '--'}</td>
                      <td className="num">{formatNumber((row.daily_close ?? row.close) as number ?? null, 2)}</td>
                      <td className={`num ${pctClass(row.factor_pct_change as number)}`}>{formatPercent(row.factor_pct_change as number)}</td>
                      <td className="num">{formatNumber(row.pe as number ?? null, 2)}</td>
                      <td className="num">{formatNumber(row.pb as number ?? null, 2)}</td>
                      <td className="num">{formatNumber(row.total_mv as number ?? null, 0)}</td>
                      <td className="num">{formatNumber(row.turnover_rate as number ?? null, 2)}</td>
                      <td className="num">{formatNumber(row.moneyflow_net_amount as number ?? null, 0)}</td>
                      <td>{row.trade_date ?? '--'}</td>
                      <td className="num">
                        <a
                          className="btn btn-outline-primary btn-sm me-1"
                          href={`${OLD_SITE_BASE}/stock/${row.ts_code}`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          详情 ↗
                        </a>
                        <a
                          className="btn btn-outline-secondary btn-sm"
                          href={`${OLD_SITE_BASE}/analysis?stock=${row.ts_code}`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          分析 ↗
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {result.stocks.length === 0 && <EmptyState icon="🔍" text="没有符合条件的股票，试试放宽条件" />}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
