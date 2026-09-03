import { useEffect, useMemo, useState } from 'react'
import {
  createPortfolioPosition,
  deletePortfolio,
  deletePosition,
  fetchPortfolioDetail,
  fetchPortfolios,
  rebalanceApply,
  rebalancePreview,
  refreshPortfolioPrices,
  runIntegratedSelection,
  saveOptimizedPortfolio,
  type IntegratedSelectionResult,
  type PortfolioListItem,
  type PortfolioSummary,
} from '../api/mlFactor'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { downloadCsv, formatNumber, formatPercent, toLocalDate } from '../utils/format'

const OPT_METHODS = [
  ['mean_variance', '均值-方差'],
  ['risk_parity', '风险平价'],
  ['equal_weight', '等权'],
] as const

const RISK_LEVELS: Record<string, { label: string; max: number; min: number; target: number; tol: number }> = {
  conservative: { label: '保守', max: 0.08, min: 0.02, target: 0.08, tol: 0.12 },
  moderate: { label: '稳健', max: 0.12, min: 0.01, target: 0.12, tol: 0.18 },
  aggressive: { label: '积极', max: 0.2, min: 0.005, target: 0.18, tol: 0.25 },
}

const SELECTION_FACTORS = ['momentum_5d', 'pe_percentile', 'money_flow_strength']

function fmtAmount(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '--'
  if (Math.abs(value) >= 1e8) return `${(value / 1e8).toFixed(2)} 亿`
  if (Math.abs(value) >= 1e4) return `${(value / 1e4).toFixed(2)} 万`
  return value.toFixed(2)
}

export default function MlPortfolioPage() {
  const [portfolios, setPortfolios] = useState<PortfolioListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 组合优化
  const [optMethod, setOptMethod] = useState<string>('equal_weight')
  const [riskLevel, setRiskLevel] = useState<'conservative' | 'moderate' | 'aggressive'>('moderate')
  const [maxStocks, setMaxStocks] = useState(20)
  const [optBusy, setOptBusy] = useState(false)
  const [optError, setOptError] = useState<string | null>(null)
  const [optResult, setOptResult] = useState<IntegratedSelectionResult | null>(null)

  // 创建组合
  const [showCreate, setShowCreate] = useState(false)
  const [createForm, setCreateForm] = useState({ portfolio_id: '', ts_code: '', position_size: '1000', avg_cost: '10', sector: '' })
  const [createMsg, setCreateMsg] = useState<string | null>(null)

  // 组合详情
  const [detail, setDetail] = useState<PortfolioSummary | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [rebalance, setRebalance] = useState<{ instructions: [string, number][]; turnover: number; cost: number } | null>(null)
  const [rebBusy, setRebBusy] = useState(false)

  const load = () => {
    setLoading(true)
    setError(null)
    fetchPortfolios()
      .then((r) => setPortfolios(r.portfolios ?? []))
      .catch((e) => setError(e instanceof Error ? e.message : '组合列表加载失败'))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const weights = useMemo(() => Object.entries(optResult?.portfolio_optimization.weights ?? {}), [optResult])
  const maxWeight = useMemo(() => Math.max(...weights.map(([, w]) => w), 0.0001), [weights])

  const runOptimize = async () => {
    setOptBusy(true)
    setOptError(null)
    setOptResult(null)
    try {
      const constraint = RISK_LEVELS[riskLevel]
      const r = await runIntegratedSelection({
        trade_date: toLocalDate(new Date()).replace(/-/g, ''),
        selection_method: 'factor_based',
        factor_list: SELECTION_FACTORS,
        weights: { momentum_5d: 0.4, pe_percentile: 0.3, money_flow_strength: 0.3 },
        top_n: Math.max(maxStocks * 2, 20),
        optimization_method: optMethod,
        constraints: {
          max_weight: constraint.max,
          min_weight: constraint.min,
          max_stocks: maxStocks,
          target_return: constraint.target,
          risk_tolerance: constraint.tol,
        },
      })
      setOptResult(r)
    } catch (e) {
      setOptError(e instanceof Error ? e.message : '组合优化失败')
    } finally {
      setOptBusy(false)
    }
  }

  const handleCreate = async () => {
    setCreateMsg(null)
    try {
      const r = await createPortfolioPosition({
        portfolio_id: createForm.portfolio_id,
        ts_code: createForm.ts_code.toUpperCase(),
        position_size: Number(createForm.position_size) || 0,
        avg_cost: Number(createForm.avg_cost) || 0,
        sector: createForm.sector || undefined,
      })
      setCreateMsg(r.success ? '组合创建成功' : '创建失败')
      if (r.success) {
        setShowCreate(false)
        load()
      }
    } catch (e) {
      setCreateMsg(e instanceof Error ? e.message : '创建失败')
    }
  }

  const openDetail = async (pid: string) => {
    setDetailLoading(true)
    setRebalance(null)
    try {
      setDetail(await fetchPortfolioDetail(pid))
    } catch (e) {
      window.alert(e instanceof Error ? e.message : '详情加载失败')
    } finally {
      setDetailLoading(false)
    }
  }

  const handleDelete = async (p: PortfolioListItem) => {
    if (!window.confirm(`确认删除组合 ${p.name}（${p.portfolio_id}）？`)) return
    try {
      await deletePortfolio(p.portfolio_id)
      load()
    } catch (e) {
      window.alert(e instanceof Error ? e.message : '删除失败')
    }
  }

  const currentWeights = useMemo(() => {
    if (!detail) return {}
    const totalMv = detail.positions.reduce((acc, p) => acc + (p.market_value ?? 0), 0)
    if (totalMv <= 0) return {}
    return Object.fromEntries(detail.positions.map((p) => [p.ts_code, (p.market_value ?? 0) / totalMv]))
  }, [detail])

  const previewRebalance = async () => {
    const target = Object.fromEntries(weights)
    if (Object.keys(target).length === 0) return
    setRebBusy(true)
    try {
      const r = await rebalancePreview({ current_weights: currentWeights, target_weights: target, transaction_cost: 0.001 })
      setRebalance({
        instructions: Object.entries(r.trade_instructions ?? {}),
        turnover: r.turnover ?? 0,
        cost: r.transaction_cost ?? 0,
      })
    } catch (e) {
      window.alert(e instanceof Error ? e.message : '再平衡预览失败')
    } finally {
      setRebBusy(false)
    }
  }

  const applyRebalance = async () => {
    if (!detail) return
    const target = Object.fromEntries(weights)
    if (!window.confirm('按优化权重执行再平衡？该操作会调整组合持仓。')) return
    try {
      await rebalanceApply({ portfolio_id: detail.portfolio_id, target_weights: target, rebalance_note: '来自 React 前端优化结果' })
      window.alert('再平衡已执行')
      setRebalance(null)
      openDetail(detail.portfolio_id)
      load()
    } catch (e) {
      window.alert(e instanceof Error ? e.message : '执行失败')
    }
  }

  const saveAsPortfolio = async () => {
    const defaultId = `portfolio_${toLocalDate(new Date()).replace(/-/g, '')}`
    const pid = window.prompt('输入新组合 ID：', defaultId)
    if (!pid) return
    try {
      const r = await saveOptimizedPortfolio({ portfolio_id: pid, total_capital: 1_000_000, weights: Object.fromEntries(weights) })
      window.alert(`已保存为组合 ${pid}（创建 ${r.created_count ?? '--'} 个持仓）`)
      load()
    } catch (e) {
      window.alert(e instanceof Error ? e.message : '保存失败')
    }
  }

  const exportOptResult = () => {
    downloadCsv(
      `组合优化_${optMethod}_${toLocalDate(new Date())}.csv`,
      ['排名', '代码', '权重'],
      weights.map(([code, w], i) => [i + 1, code, w.toFixed(6)]),
    )
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>投资组合</h2>
          <p className="desc">真实持仓管理 · 选股 + 优化一体化 · 再平衡</p>
        </div>
        <button type="button" className="btn btn-primary btn-sm" onClick={() => setShowCreate(true)}>
          + 创建组合
        </button>
      </div>

      {/* 组合优化工具 */}
      <div className="panel">
        <div className="panel-head">
          <h6 className="panel-title">
            <span className="kicker" />
            组合优化（选股 + 优化一体化）
          </h6>
        </div>
        <div className="panel-body">
          <div className="row g-3 align-items-end">
            <div className="col-lg-3 col-md-6">
              <label className="form-label">优化方法</label>
              <select className="form-select" value={optMethod} onChange={(e) => setOptMethod(e.target.value)}>
                {OPT_METHODS.map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-lg-3 col-md-6">
              <label className="form-label">风险水平</label>
              <select className="form-select" value={riskLevel} onChange={(e) => setRiskLevel(e.target.value as typeof riskLevel)}>
                {Object.entries(RISK_LEVELS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-lg-3 col-md-6">
              <label className="form-label">最大持股数（5-50）</label>
              <input type="number" className="form-control" min={5} max={50} value={maxStocks} onChange={(e) => setMaxStocks(Number(e.target.value))} />
            </div>
            <div className="col-lg-3 col-md-6">
              <button type="button" className="btn btn-primary w-100" disabled={optBusy} onClick={runOptimize}>
                {optBusy ? '优化中（打分+协方差+求解）…' : '⚖️ 优化组合'}
              </button>
            </div>
          </div>
          {optError && (
            <div className="mt-3">
              <ErrorState message={optError} onRetry={runOptimize} />
            </div>
          )}
          {optBusy && <Loading text="因子打分 → 收益定标 → 协方差估计 → 权重求解..." />}

          {optResult && !optBusy && (
            <div className="mt-3">
              <div className="stat-grid">
                <div className="stat">
                  <div className={`stat-value ${formatPercent((optResult.portfolio_optimization.portfolio_stats.expected_return ?? 0) * 100).startsWith('+') ? 'text-up' : 'text-down'}`}>
                    {formatPercent((optResult.portfolio_optimization.portfolio_stats.expected_return ?? 0) * 100)}
                  </div>
                  <div className="stat-label">预期收益率</div>
                </div>
                <div className="stat">
                  <div className="stat-value">{formatPercent((optResult.portfolio_optimization.portfolio_stats.volatility ?? 0) * 100)}</div>
                  <div className="stat-label">组合波动率</div>
                </div>
                <div className="stat">
                  <div className="stat-value">{formatNumber(optResult.portfolio_optimization.portfolio_stats.sharpe_ratio, 2)}</div>
                  <div className="stat-label">夏普比率</div>
                </div>
                <div className="stat">
                  <div className="stat-value">{formatPercent((optResult.portfolio_optimization.portfolio_stats.max_weight ?? 0) * 100)}</div>
                  <div className="stat-label">最大权重</div>
                </div>
              </div>

              <div className="table-container mt-2" style={{ maxHeight: 380 }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>排名</th>
                      <th>代码</th>
                      <th className="num">权重</th>
                      <th style={{ width: 220 }}>分布</th>
                    </tr>
                  </thead>
                  <tbody>
                    {weights.map(([code, w], i) => (
                      <tr key={code}>
                        <td>
                          <span className={`badge ${i < 3 ? 'text-bg-success' : i < 10 ? 'text-bg-primary' : 'text-bg-secondary'}`}>{i + 1}</span>
                        </td>
                        <td>
                          <code>{code}</code>
                        </td>
                        <td className="num">{formatPercent(w * 100)}</td>
                        <td>
                          <div className="progress" style={{ height: 6 }}>
                            <div className="progress-bar" style={{ width: `${(w / maxWeight) * 100}%` }} />
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="d-flex gap-2 mt-3 flex-wrap">
                <button type="button" className="btn btn-outline-primary btn-sm" onClick={previewRebalance} disabled={rebBusy || Object.keys(currentWeights).length === 0}>
                  再平衡预览
                </button>
                <button type="button" className="btn btn-outline-primary btn-sm" onClick={saveAsPortfolio}>
                  保存为投资组合
                </button>
                <button type="button" className="btn btn-outline-secondary btn-sm" onClick={exportOptResult}>
                  导出结果 ↓
                </button>
              </div>

              {rebalance && (
                <div className="mt-3 p-3 rounded" style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
                  <div className="d-flex gap-2 flex-wrap mb-2">
                    <span className="chip">换手率 · {formatPercent(rebalance.turnover * 100)}</span>
                    <span className="chip">估算成本 · {formatPercent(rebalance.cost * 100)}</span>
                    <span className="chip">{rebalance.instructions.length} 笔调整</span>
                    <button type="button" className="btn btn-primary btn-sm ms-auto" onClick={applyRebalance}>
                      执行再平衡
                    </button>
                  </div>
                  <div className="table-container" style={{ maxHeight: 240 }}>
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>代码</th>
                          <th>方向</th>
                          <th className="num">权重变化</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rebalance.instructions.map(([code, diff]) => (
                          <tr key={code}>
                            <td>
                              <code>{code}</code>
                            </td>
                            <td>
                              <span className={`badge ${diff > 0 ? 'text-bg-danger' : 'text-bg-success'}`}>
                                {diff > 0 ? (currentWeights[code] ? '增持' : '买入') : '减持'}
                              </span>
                            </td>
                            <td className="num">{formatPercent(Math.abs(diff) * 100)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 组合列表 */}
      <div className="panel">
        <div className="panel-head">
          <h6 className="panel-title">
            <span className="kicker" />
            组合列表
            <span className="chip">{portfolios.length} 个</span>
          </h6>
          <button type="button" className="btn btn-outline-secondary btn-sm" onClick={load}>
            ⟳ 刷新
          </button>
        </div>
        <div className="panel-body">
          {loading && <Loading text="加载组合..." />}
          {error && <ErrorState message={error} onRetry={load} />}
          <div className="row g-3">
            {portfolios.map((p) => (
              <div className="col-xl-4 col-md-6" key={p.portfolio_id}>
                <div className="panel h-100" style={{ margin: 0 }}>
                  <div className="panel-body">
                    <div className="d-flex justify-content-between align-items-start mb-2">
                      <div>
                        <div style={{ fontWeight: 700, fontSize: 15.5 }}>{p.name}</div>
                        <code style={{ fontSize: 11.5 }}>{p.portfolio_id}</code>
                      </div>
                      <span className="chip">{p.position_count} 持仓</span>
                    </div>
                    <div className="d-flex gap-3 flex-wrap" style={{ fontSize: 13 }}>
                      <span>
                        现值 <b>{fmtAmount(p.current_value)}</b>
                      </span>
                      <span>
                        浮动 <b className={p.return_rate >= 0 ? 'text-up' : 'text-down'}>{formatPercent(p.return_rate * 100)}</b>
                      </span>
                      <span>
                        最大权重 <b>{formatPercent(p.max_position_weight * 100)}</b>
                      </span>
                    </div>
                    <div className="d-flex gap-2 mt-3">
                      <button type="button" className="btn btn-outline-primary btn-sm" onClick={() => openDetail(p.portfolio_id)}>
                        详情
                      </button>
                      <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => refreshPortfolioPrices(p.portfolio_id).then(() => window.alert('已触发实时价刷新'))}>
                        刷新价格
                      </button>
                      <button type="button" className="btn btn-outline-danger btn-sm ms-auto" onClick={() => handleDelete(p)}>
                        删除
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            ))}
            {!loading && !error && portfolios.length === 0 && (
              <div className="col-12">
                <EmptyState icon="💼" text="暂无组合，点击右上角创建" />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 创建组合 */}
      {showCreate && (
        <div className="modal d-block" style={{ background: 'rgba(0,0,0,0.45)' }} onClick={() => setShowCreate(false)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-content" style={{ background: 'var(--surface)', color: 'var(--text)' }}>
              <div className="modal-header">
                <h5 className="modal-title">创建组合（首个持仓）</h5>
                <button type="button" className="btn-close" onClick={() => setShowCreate(false)} />
              </div>
              <div className="modal-body">
                <div className="row g-3">
                  <div className="col-md-6">
                    <label className="form-label">组合 ID</label>
                    <input type="text" className="form-control" value={createForm.portfolio_id} onChange={(e) => setCreateForm({ ...createForm, portfolio_id: e.target.value })} />
                  </div>
                  <div className="col-md-6">
                    <label className="form-label">股票代码</label>
                    <input type="text" className="form-control" placeholder="000001.SZ" value={createForm.ts_code} onChange={(e) => setCreateForm({ ...createForm, ts_code: e.target.value.toUpperCase() })} />
                  </div>
                  <div className="col-md-4">
                    <label className="form-label">持仓数量</label>
                    <input type="number" className="form-control" value={createForm.position_size} onChange={(e) => setCreateForm({ ...createForm, position_size: e.target.value })} />
                  </div>
                  <div className="col-md-4">
                    <label className="form-label">平均成本</label>
                    <input type="number" className="form-control" value={createForm.avg_cost} onChange={(e) => setCreateForm({ ...createForm, avg_cost: e.target.value })} />
                  </div>
                  <div className="col-md-4">
                    <label className="form-label">行业</label>
                    <input type="text" className="form-control" value={createForm.sector} onChange={(e) => setCreateForm({ ...createForm, sector: e.target.value })} />
                  </div>
                </div>
                {createMsg && <div className="alert-note mt-3">{createMsg}</div>}
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline-secondary" onClick={() => setShowCreate(false)}>
                  取消
                </button>
                <button type="button" className="btn btn-primary" onClick={handleCreate}>
                  创建
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 组合详情 */}
      {detailLoading && <Loading text="加载组合详情..." />}
      {detail && !detailLoading && (
        <div className="modal d-block" style={{ background: 'rgba(0,0,0,0.45)' }} onClick={() => setDetail(null)}>
          <div className="modal-dialog modal-xl modal-dialog-scrollable" onClick={(e) => e.stopPropagation()}>
            <div className="modal-content" style={{ background: 'var(--surface)', color: 'var(--text)' }}>
              <div className="modal-header">
                <h5 className="modal-title">
                  {detail.name} · <code>{detail.portfolio_id}</code>
                </h5>
                <button type="button" className="btn-close" onClick={() => setDetail(null)} />
              </div>
              <div className="modal-body">
                <div className="stat-grid mb-3">
                  <div className="stat">
                    <div className="stat-value" style={{ fontSize: 18 }}>{fmtAmount(detail.metrics.total_market_value)}</div>
                    <div className="stat-label">组合市值</div>
                  </div>
                  <div className="stat">
                    <div className={`stat-value ${detail.metrics.total_pnl_percentage >= 0 ? 'text-up' : 'text-down'}`} style={{ fontSize: 18 }}>
                      {formatPercent(detail.metrics.total_pnl_percentage)}
                    </div>
                    <div className="stat-label">浮动收益率</div>
                  </div>
                  <div className="stat">
                    <div className="stat-value" style={{ fontSize: 18 }}>{detail.metrics.total_positions}</div>
                    <div className="stat-label">持仓数量</div>
                  </div>
                  <div className="stat">
                    <div className="stat-value" style={{ fontSize: 18 }}>{formatPercent(detail.metrics.max_position_weight)}</div>
                    <div className="stat-label">最大权重</div>
                  </div>
                </div>
                <div className="table-container" style={{ maxHeight: 420 }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>持仓 ID</th>
                        <th>代码</th>
                        <th className="num">权重</th>
                        <th className="num">市值</th>
                        <th className="num">浮动盈亏</th>
                        <th className="num">现价</th>
                        <th className="num">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.positions.map((pos) => (
                        <tr key={pos.id}>
                          <td>#{pos.id}</td>
                          <td>
                            <code>{pos.ts_code}</code>
                          </td>
                          <td className="num">{pos.weight != null ? formatPercent(pos.weight) : '--'}</td>
                          <td className="num">{fmtAmount(pos.market_value)}</td>
                          <td className={`num ${(pos.unrealized_pnl ?? 0) >= 0 ? 'text-up' : 'text-down'}`}>{fmtAmount(pos.unrealized_pnl)}</td>
                          <td className="num">{formatNumber(pos.current_price, 2)}</td>
                          <td className="num">
                            <button
                              type="button"
                              className="btn btn-outline-danger btn-sm"
                              onClick={async () => {
                                if (!window.confirm(`删除持仓 ${pos.ts_code}？`)) return
                                try {
                                  await deletePosition(detail.portfolio_id, pos.id)
                                  openDetail(detail.portfolio_id)
                                  load()
                                } catch (e) {
                                  window.alert(e instanceof Error ? e.message : '删除失败')
                                }
                              }}
                            >
                              删除
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
