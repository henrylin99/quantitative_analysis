import { useEffect, useMemo, useState } from 'react'
import {
  calculateFactors,
  createCustomFactor,
  fetchFactorCapabilities,
  fetchFactors,
  type FactorCapabilities,
  type FactorDef,
} from '../api/mlFactor'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { toLocalDate } from '../utils/format'

const TYPE_BADGE: Record<string, string> = {
  technical: 'text-bg-primary',
  fundamental: 'text-bg-success',
  money_flow: 'text-bg-warning',
  chip: 'text-bg-info',
  other: 'text-bg-secondary',
}

export default function MlFactorIndexPage() {
  const [factors, setFactors] = useState<FactorDef[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [fType, setFType] = useState('')
  const [fSource, setFSource] = useState('')
  const [fStatus, setFStatus] = useState('')
  const [search, setSearch] = useState('')

  const [showCreate, setShowCreate] = useState(false)
  const [capabilities, setCapabilities] = useState<FactorCapabilities | null>(null)
  const [form, setForm] = useState({ factor_id: '', factor_name: '', factor_type: 'technical', factor_formula: '', description: '' })
  const [createMsg, setCreateMsg] = useState<string | null>(null)
  const [calcBusy, setCalcBusy] = useState(false)

  const load = () => {
    setLoading(true)
    setError(null)
    fetchFactors()
      .then((r) => setFactors(r.factors ?? []))
      .catch((e) => setError(e instanceof Error ? e.message : '因子列表加载失败'))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const openCreate = () => {
    setShowCreate(true)
    setCreateMsg(null)
    if (!capabilities) {
      fetchFactorCapabilities()
        .then((r) => setCapabilities(r.capabilities))
        .catch(() => setCapabilities(null))
    }
  }

  const handleCreate = async () => {
    setCreateMsg(null)
    try {
      const r = await createCustomFactor(form)
      setCreateMsg(r.success ? `创建成功：${r.message ?? form.factor_id}` : (r.error ?? '创建失败'))
      if (r.success) load()
    } catch (e) {
      setCreateMsg(e instanceof Error ? e.message : '创建失败')
    }
  }

  const handleCalculate = async () => {
    if (!window.confirm('将计算全部因子 × 全部股票（当日），耗时可能较长，继续？')) return
    setCalcBusy(true)
    try {
      const r = await calculateFactors(toLocalDate(new Date()))
      window.alert(`计算完成（${r.trade_date}）\n${JSON.stringify(r.results).slice(0, 800)}`)
    } catch (e) {
      window.alert(e instanceof Error ? e.message : '计算失败')
    } finally {
      setCalcBusy(false)
    }
  }

  const filtered = useMemo(() => {
    const kw = search.trim().toLowerCase()
    return factors.filter((f) => {
      if (fType && f.factor_type !== fType) return false
      if (fSource === 'builtin' && !f.is_builtin) return false
      if (fSource === 'custom' && f.is_builtin) return false
      if (fStatus === 'active' && !f.is_active) return false
      if (fStatus === 'inactive' && f.is_active) return false
      if (kw && !(f.factor_id.toLowerCase().includes(kw) || (f.factor_name ?? '').toLowerCase().includes(kw))) return false
      return true
    })
  }, [factors, fType, fSource, fStatus, search])

  const builtinCount = factors.filter((f) => f.is_builtin).length
  const activeCount = factors.filter((f) => f.is_active).length

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>因子管理</h2>
          <p className="desc">内置与自定义因子清单、表达式白名单与一键计算</p>
        </div>
        <div className="d-flex gap-2">
          <button type="button" className="btn btn-outline-primary btn-sm" disabled={calcBusy} onClick={handleCalculate}>
            {calcBusy ? '计算中…' : '⚡ 计算因子'}
          </button>
          <button type="button" className="btn btn-primary btn-sm" onClick={openCreate}>
            + 创建自定义因子
          </button>
        </div>
      </div>

      <div className="stat-grid">
        <div className="stat">
          <div className="stat-value">{factors.length}</div>
          <div className="stat-label">总因子数</div>
        </div>
        <div className="stat">
          <div className="stat-value">{builtinCount}</div>
          <div className="stat-label">内置因子</div>
        </div>
        <div className="stat">
          <div className="stat-value">{factors.length - builtinCount}</div>
          <div className="stat-label">自定义因子</div>
        </div>
        <div className="stat">
          <div className="stat-value">{activeCount}</div>
          <div className="stat-label">活跃因子</div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <h6 className="panel-title">
            <span className="kicker" />
            因子列表
            <span className="chip">{filtered.length} / {factors.length}</span>
          </h6>
        </div>
        <div className="panel-body">
          <div className="row g-2 mb-3">
            <div className="col-lg-2 col-md-3 col-6">
              <select className="form-select" value={fType} onChange={(e) => setFType(e.target.value)}>
                <option value="">全部类型</option>
                {['technical', 'fundamental', 'money_flow', 'chip', 'other'].map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-lg-2 col-md-3 col-6">
              <select className="form-select" value={fSource} onChange={(e) => setFSource(e.target.value)}>
                <option value="">全部来源</option>
                <option value="builtin">内置</option>
                <option value="custom">自定义</option>
              </select>
            </div>
            <div className="col-lg-2 col-md-3 col-6">
              <select className="form-select" value={fStatus} onChange={(e) => setFStatus(e.target.value)}>
                <option value="">全部状态</option>
                <option value="active">活跃</option>
                <option value="inactive">停用</option>
              </select>
            </div>
            <div className="col-lg-3 col-md-4 col-6">
              <input type="text" className="form-control" placeholder="搜索因子 ID / 名称" value={search} onChange={(e) => setSearch(e.target.value)} />
            </div>
          </div>

          {loading && <Loading text="加载因子..." />}
          {error && <ErrorState message={error} onRetry={load} />}
          {!loading && !error && (
            <div className="table-container" style={{ maxHeight: 560 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>因子 ID</th>
                    <th>名称</th>
                    <th>类型</th>
                    <th>来源</th>
                    <th>状态</th>
                    <th>描述</th>
                    <th>公式</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((f) => (
                    <tr key={f.factor_id}>
                      <td>
                        <code>{f.factor_id}</code>
                      </td>
                      <td style={{ fontWeight: 600 }}>{f.factor_name}</td>
                      <td>
                        <span className={`badge ${TYPE_BADGE[f.factor_type] ?? 'text-bg-secondary'}`}>{f.factor_type}</span>
                      </td>
                      <td>{f.is_builtin ? '内置' : '自定义'}</td>
                      <td>{f.is_active ? '✓ 活跃' : '停用'}</td>
                      <td style={{ maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.description ?? '--'}</td>
                      <td>
                        <code style={{ fontSize: 11.5 }}>{f.formula ?? '--'}</code>
                      </td>
                    </tr>
                  ))}
                  {filtered.length === 0 && (
                    <tr>
                      <td colSpan={7}>
                        <EmptyState icon="🧬" text="没有匹配的因子" />
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* 创建自定义因子 */}
      {showCreate && (
        <div className="modal d-block" style={{ background: 'rgba(0,0,0,0.45)' }} onClick={() => setShowCreate(false)}>
          <div className="modal-dialog modal-lg modal-dialog-scrollable" onClick={(e) => e.stopPropagation()}>
            <div className="modal-content" style={{ background: 'var(--surface)', color: 'var(--text)' }}>
              <div className="modal-header">
                <h5 className="modal-title">创建自定义因子</h5>
                <button type="button" className="btn-close" onClick={() => setShowCreate(false)} />
              </div>
              <div className="modal-body">
                <div className="row g-3">
                  <div className="col-md-6">
                    <label className="form-label">因子 ID（仅字母数字下划线）</label>
                    <input type="text" className="form-control" value={form.factor_id} onChange={(e) => setForm({ ...form, factor_id: e.target.value })} />
                  </div>
                  <div className="col-md-6">
                    <label className="form-label">因子名称</label>
                    <input type="text" className="form-control" value={form.factor_name} onChange={(e) => setForm({ ...form, factor_name: e.target.value })} />
                  </div>
                  <div className="col-md-6">
                    <label className="form-label">因子类型</label>
                    <select className="form-select" value={form.factor_type} onChange={(e) => setForm({ ...form, factor_type: e.target.value })}>
                      {['technical', 'fundamental', 'money_flow', 'chip', 'other'].map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="col-md-6">
                    <label className="form-label">描述</label>
                    <input type="text" className="form-control" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
                  </div>
                  <div className="col-12">
                    <label className="form-label">公式（示例：(close - ma20) / ma20）</label>
                    <textarea
                      className="form-control"
                      rows={2}
                      value={form.factor_formula}
                      onChange={(e) => setForm({ ...form, factor_formula: e.target.value })}
                    />
                  </div>
                </div>
                {capabilities && (
                  <div className="mt-3 p-3 rounded" style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', fontSize: 12.5 }}>
                    <div className="side-group-label">表达式白名单</div>
                    <div className="mb-1">
                      <b>可用列：</b>
                      <span style={{ color: 'var(--text-dim)' }}>{capabilities.allowed_columns.join('、')}</span>
                    </div>
                    <div className="mb-1">
                      <b>序列方法：</b>
                      <span style={{ color: 'var(--text-dim)' }}>{capabilities.allowed_series_methods.join('、')}</span>
                    </div>
                    <div className="mb-1">
                      <b>窗口方法：</b>
                      <span style={{ color: 'var(--text-dim)' }}>{capabilities.allowed_window_methods.join('、')}</span>
                    </div>
                    <div>
                      <b>函数：</b>
                      <span style={{ color: 'var(--text-dim)' }}>{capabilities.allowed_functions.join('、')}</span>
                    </div>
                  </div>
                )}
                {createMsg && <div className="alert-note mt-3">{createMsg}</div>}
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline-secondary" onClick={() => setShowCreate(false)}>
                  关闭
                </button>
                <button type="button" className="btn btn-primary" onClick={handleCreate}>
                  创建
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
