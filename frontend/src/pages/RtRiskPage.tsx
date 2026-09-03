import { useEffect, useMemo, useState } from 'react'
import EChart from '../charts/EChart'
import { useTheme } from '../theme/ThemeContext'
import {
  fetchRiskAlerts,
  fetchRiskPositionMonitor,
  resolveRiskAlert,
  stopLossTakeProfit,
  stressTest,
  type RiskAlert,
} from '../api/realtime'
import {
  fetchPortfolioDetail,
  fetchPortfolios,
  refreshPortfolioPrices,
  type PortfolioListItem,
  type PortfolioSummary,
} from '../api/mlFactor'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { formatDateTime, formatNumber, formatPercent } from '../utils/format'

const TABS = [
  { key: 'positions', label: '持仓管理' },
  { key: 'risk', label: '风险分析' },
  { key: 'alerts', label: '预警管理' },
  { key: 'sltp', label: '止损止盈' },
  { key: 'stress', label: '压力测试' },
] as const

type TabKey = (typeof TABS)[number]['key']

export default function RtRiskPage() {
  const { palette } = useTheme()
  const [portfolios, setPortfolios] = useState<PortfolioListItem[]>([])
  const [pid, setPid] = useState('')
  const [detail, setDetail] = useState<PortfolioSummary | null>(null)
  const [monitor, setMonitor] = useState<Awaited<ReturnType<typeof fetchRiskPositionMonitor>>>(null)
  const [alerts, setAlerts] = useState<RiskAlert[]>([])
  const [alertFilter, setAlertFilter] = useState('')
  const [tab, setTab] = useState<TabKey>('positions')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<string>('--')

  // 止损止盈
  const [slMethod, setSlMethod] = useState('percentage')
  const [slValue, setSlValue] = useState('5')
  const [tpMethod, setTpMethod] = useState('percentage')
  const [tpValue, setTpValue] = useState('10')
  const [sltpResult, setSltpResult] = useState<Awaited<ReturnType<typeof stopLossTakeProfit>>['data'] | null>(null)
  const [sltpBusy, setSltpBusy] = useState(false)

  // 压力测试
  const [stressBusy, setStressBusy] = useState(false)
  const [stressResult, setStressResult] = useState<Awaited<ReturnType<typeof stressTest>>['data'] | null>(null)

  useEffect(() => {
    fetchPortfolios()
      .then((r) => {
        setPortfolios(r.portfolios ?? [])
        if ((r.portfolios ?? []).length > 0) setPid(r.portfolios[0].portfolio_id)
      })
      .catch(() => setPortfolios([]))
  }, [])

  const loadPortfolio = async (id: string) => {
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      await refreshPortfolioPrices(id)
      const [d, m, a] = await Promise.all([fetchPortfolioDetail(id), fetchRiskPositionMonitor(id), fetchRiskAlerts(id)])
      setDetail(d)
      setMonitor(m)
      setAlerts(a?.active_alerts ?? [])
      setLastRefresh(new Date().toLocaleTimeString('zh-CN'))
    } catch (e) {
      setError(e instanceof Error ? e.message : '组合数据加载失败')
      setDetail(null)
      setMonitor(null)
      setAlerts([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadPortfolio(pid)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid])

  const sectorPieOption = useMemo(() => {
    const dist = detail?.metrics.sector_distribution
    if (!dist || Object.keys(dist).length === 0) return null
    return {
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: { type: 'scroll', bottom: 0 },
      series: [{ type: 'pie', radius: '52%', data: Object.entries(dist).map(([name, value]) => ({ name, value })) }],
    }
  }, [detail])

  const varBarOption = useMemo(() => {
    const m = monitor?.portfolio_metrics
    if (!m || (m.portfolio_var_1d == null && m.portfolio_var_5d == null)) return null
    return {
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => formatPercent(v) },
      grid: { left: 64, right: 20, top: 20, bottom: 26 },
      xAxis: { type: 'category', data: ['1日 VaR', '5日 VaR'] },
      yAxis: { type: 'value' },
      series: [
        {
          type: 'bar',
          barMaxWidth: 42,
          itemStyle: { color: palette.amber },
          data: [m.portfolio_var_1d, m.portfolio_var_5d],
        },
      ],
    }
  }, [monitor, palette])

  const corrHeatOption = useMemo(() => {
    const matrix = monitor?.correlation_metrics?.correlation_matrix
    if (!matrix) return null
    const codes = Object.keys(matrix)
    if (codes.length < 2) return null
    const data: [number, number, number][] = []
    codes.forEach((c1, i) => {
      codes.forEach((c2, j) => {
        const v = matrix[c1]?.[c2]
        data.push([i, j, typeof v === 'number' ? Number(v.toFixed(3)) : 0])
      })
    })
    return {
      tooltip: { position: 'top', formatter: (p: { data: [number, number, number] }) => `${codes[p.data[0]]} × ${codes[p.data[1]]}: ${p.data[2]}` },
      grid: { left: 110, right: 60, top: 10, bottom: 70 },
      xAxis: { type: 'category', data: codes, axisLabel: { rotate: 40, fontSize: 10 } },
      yAxis: { type: 'category', data: codes },
      visualMap: {
        min: -1,
        max: 1,
        calculable: true,
        orient: 'horizontal',
        left: 'center',
        bottom: 0,
        inRange: { color: [palette.down, '#bdc3c7', palette.up] },
      },
      series: [
        {
          type: 'heatmap',
          data,
          label: { show: codes.length <= 8, fontSize: 9 },
        },
      ],
    }
  }, [monitor, palette])

  const filteredAlerts = alertFilter ? alerts.filter((a) => a.alert_level === alertFilter) : alerts

  const runSltp = async () => {
    if (!pid) return
    setSltpBusy(true)
    setSltpResult(null)
    try {
      const r = await stopLossTakeProfit({
        portfolio_id: pid,
        stop_loss_method: slMethod,
        stop_loss_value: Number(slValue),
        take_profit_method: tpMethod,
        take_profit_value: Number(tpValue),
      })
      setSltpResult(r.data ?? null)
    } catch (e) {
      window.alert(e instanceof Error ? e.message : '检查失败')
    } finally {
      setSltpBusy(false)
    }
  }

  const runStress = async () => {
    if (!pid) return
    setStressBusy(true)
    setStressResult(null)
    try {
      const r = await stressTest(pid)
      setStressResult(r.data ?? null)
    } catch (e) {
      window.alert(e instanceof Error ? e.message : '压力测试失败')
    } finally {
      setStressBusy(false)
    }
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>风险管理</h2>
          <p className="desc">
            组合持仓 / VaR / 相关性 / 预警 / 压力测试 · 最后更新 <code>{lastRefresh}</code>
          </p>
        </div>
        <div className="d-flex gap-2 align-items-end">
          <div>
            <label className="form-label">选择组合</label>
            <select className="form-select" value={pid} onChange={(e) => setPid(e.target.value)} style={{ minWidth: 200 }}>
              <option value="">请选择组合</option>
              {portfolios.map((p) => (
                <option key={p.portfolio_id} value={p.portfolio_id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          <button type="button" className="btn btn-primary" onClick={() => loadPortfolio(pid)} disabled={!pid || loading}>
            加载
          </button>
        </div>
      </div>

      {loading && <Loading text="刷新价格并加载组合风险数据..." />}
      {error && <ErrorState message={error} onRetry={() => loadPortfolio(pid)} />}

      {detail && !loading && (
        <>
          <div className="stat-grid">
            <div className="stat">
              <div className="stat-value">{formatNumber(detail.metrics.total_market_value ?? null, 0)}</div>
              <div className="stat-label">组合价值（元）</div>
            </div>
            <div className="stat">
              <div className={`stat-value ${detail.metrics.total_pnl_percentage >= 0 ? 'text-up' : 'text-down'}`}>
                {formatPercent(detail.metrics.total_pnl_percentage)}
              </div>
              <div className="stat-label">总收益率</div>
            </div>
            <div className="stat">
              <div className="stat-value">{monitor?.risk_summary?.overall_risk_level ?? '--'}</div>
              <div className="stat-label">风险评级 · 评分 {formatNumber(monitor?.risk_summary?.risk_score ?? null, 0)}</div>
            </div>
            <div className="stat">
              <div className="stat-value">{alerts.length}</div>
              <div className="stat-label">活跃预警</div>
            </div>
          </div>

          <div className="seg mb-3" role="group" style={{ flexWrap: 'wrap' }}>
            {TABS.map((t) => (
              <button key={t.key} type="button" className={`seg-item ${tab === t.key ? 'active' : ''}`} onClick={() => setTab(t.key)}>
                {t.label}
              </button>
            ))}
          </div>

          {tab === 'positions' && (
            <div className="row g-3">
              <div className="col-lg-8">
                <div className="panel h-100">
                  <div className="panel-head">
                    <h6 className="panel-title">
                      <span className="kicker" />
                      持仓明细
                      <span className="chip">{detail.positions.length} 只</span>
                    </h6>
                  </div>
                  <div className="panel-body tight table-container" style={{ maxHeight: 460 }}>
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>代码</th>
                          <th className="num">数量</th>
                          <th className="num">成本</th>
                          <th className="num">现价</th>
                          <th className="num">市值</th>
                          <th className="num">盈亏</th>
                          <th className="num">权重</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.positions.map((p) => (
                          <tr key={p.id}>
                            <td>
                              <code>{p.ts_code}</code>
                            </td>
                            <td className="num">{p.position_size}</td>
                            <td className="num">{formatNumber(p.avg_cost, 2)}</td>
                            <td className="num">{formatNumber(p.current_price, 2)}</td>
                            <td className="num">{formatNumber(p.market_value, 0)}</td>
                            <td className={`num ${(p.unrealized_pnl ?? 0) >= 0 ? 'text-up' : 'text-down'}`}>{formatNumber(p.unrealized_pnl, 0)}</td>
                            <td className="num">{formatPercent(p.weight ?? 0)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
              <div className="col-lg-4">
                <div className="panel h-100">
                  <div className="panel-head">
                    <h6 className="panel-title">
                      <span className="kicker" />
                      行业分布
                    </h6>
                  </div>
                  <div className="panel-body">{sectorPieOption ? <EChart option={sectorPieOption} height={380} /> : <EmptyState icon="🏭" text="无行业分布数据" />}</div>
                </div>
              </div>
            </div>
          )}

          {tab === 'risk' && (
            <div className="row g-3">
              <div className="col-lg-4">
                <div className="panel h-100">
                  <div className="panel-head">
                    <h6 className="panel-title">
                      <span className="kicker" />
                      风险指标
                    </h6>
                  </div>
                  <div className="panel-body d-flex gap-2 flex-wrap">
                    <span className="chip">高风险持仓 · {monitor?.risk_summary?.high_risk_positions ?? '--'}</span>
                    <span className="chip">中风险持仓 · {monitor?.risk_summary?.medium_risk_positions ?? '--'}</span>
                    <span className="chip">1日 VaR · {formatPercent(monitor?.portfolio_metrics?.portfolio_var_1d ?? null)}</span>
                    <span className="chip">5日 VaR · {formatPercent(monitor?.portfolio_metrics?.portfolio_var_5d ?? null)}</span>
                  </div>
                </div>
              </div>
              <div className="col-lg-4">
                <div className="panel h-100">
                  <div className="panel-head">
                    <h6 className="panel-title">
                      <span className="kicker" />
                      VaR
                    </h6>
                  </div>
                  <div className="panel-body">{varBarOption ? <EChart option={varBarOption} height={320} /> : <EmptyState icon="📊" text="暂无 VaR 数据" />}</div>
                </div>
              </div>
              <div className="col-lg-4">
                <div className="panel h-100">
                  <div className="panel-head">
                    <h6 className="panel-title">
                      <span className="kicker" />
                      相关性矩阵
                    </h6>
                  </div>
                  <div className="panel-body">{corrHeatOption ? <EChart option={corrHeatOption} height={320} /> : <EmptyState icon="🔥" text="持仓不足 2 只，无法计算相关性" />}</div>
                </div>
              </div>
            </div>
          )}

          {tab === 'alerts' && (
            <div className="panel">
              <div className="panel-head">
                <h6 className="panel-title">
                  <span className="kicker" />
                  活跃预警
                  <span className="chip">{filteredAlerts.length} 条</span>
                </h6>
                <select className="form-select form-select-sm w-auto" value={alertFilter} onChange={(e) => setAlertFilter(e.target.value)}>
                  <option value="">全部级别</option>
                  {['high', 'medium', 'low'].map((l) => (
                    <option key={l} value={l}>
                      {l}
                    </option>
                  ))}
                </select>
              </div>
              <div className="panel-body d-flex flex-column gap-2">
                {filteredAlerts.map((a) => (
                  <div key={a.id} className="d-flex align-items-center gap-3 p-2 rounded flex-wrap" style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
                    <span className={`badge ${a.alert_level === 'high' ? 'text-bg-danger' : a.alert_level === 'medium' ? 'text-bg-warning' : 'text-bg-secondary'}`}>
                      {a.alert_level}
                    </span>
                    <code>{a.ts_code}</code>
                    <span style={{ flex: 1, minWidth: 200 }}>{a.alert_message}</span>
                    <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>{formatDateTime(a.created_at)}</span>
                    <button
                      type="button"
                      className="btn btn-outline-secondary btn-sm"
                      onClick={async () => {
                        await resolveRiskAlert(a.id)
                        loadPortfolio(pid)
                      }}
                    >
                      解决
                    </button>
                  </div>
                ))}
                {filteredAlerts.length === 0 && <EmptyState icon="🛡️" text="没有活跃预警" />}
              </div>
            </div>
          )}

          {tab === 'sltp' && (
            <div className="panel">
              <div className="panel-body">
                <div className="row g-3 align-items-end">
                  <div className="col-lg-2 col-md-3 col-6">
                    <label className="form-label">止损方式</label>
                    <select className="form-select" value={slMethod} onChange={(e) => setSlMethod(e.target.value)}>
                      <option value="percentage">百分比</option>
                      <option value="atr">ATR</option>
                      <option value="fixed">固定价</option>
                    </select>
                  </div>
                  <div className="col-lg-2 col-md-3 col-6">
                    <label className="form-label">止损数值</label>
                    <input type="number" className="form-control" value={slValue} onChange={(e) => setSlValue(e.target.value)} />
                  </div>
                  <div className="col-lg-2 col-md-3 col-6">
                    <label className="form-label">止盈方式</label>
                    <select className="form-select" value={tpMethod} onChange={(e) => setTpMethod(e.target.value)}>
                      <option value="percentage">百分比</option>
                      <option value="atr">ATR</option>
                      <option value="fixed">固定价</option>
                    </select>
                  </div>
                  <div className="col-lg-2 col-md-3 col-6">
                    <label className="form-label">止盈数值</label>
                    <input type="number" className="form-control" value={tpValue} onChange={(e) => setTpValue(e.target.value)} />
                  </div>
                  <div className="col-lg-3 col-md-4">
                    <button type="button" className="btn btn-primary w-100" disabled={sltpBusy} onClick={runSltp}>
                      {sltpBusy ? '检查中…' : '更新并检查触发'}
                    </button>
                  </div>
                </div>
                {sltpResult && (
                  <div className="table-container mt-3" style={{ maxHeight: 320 }}>
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>代码</th>
                          <th>订单类型</th>
                          <th className="num">触发价</th>
                          <th className="num">持仓数量</th>
                          <th className="num">浮动盈亏</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(sltpResult.triggered_orders ?? []).map((o, i) => (
                          <tr key={`${o.ts_code}-${i}`}>
                            <td>
                              <code>{o.ts_code}</code>
                            </td>
                            <td>
                              <span className={`badge ${o.order_type === 'stop_loss' ? 'text-bg-success' : 'text-bg-danger'}`}>{o.order_type}</span>
                            </td>
                            <td className="num">{formatNumber(o.trigger_price, 2)}</td>
                            <td className="num">{o.position_size}</td>
                            <td className={`num ${(o.unrealized_pnl ?? 0) >= 0 ? 'text-up' : 'text-down'}`}>{formatNumber(o.unrealized_pnl, 0)}</td>
                          </tr>
                        ))}
                        {(sltpResult.triggered_orders ?? []).length === 0 && (
                          <tr>
                            <td colSpan={5}>
                              <EmptyState icon="✅" text="没有触发止损止盈订单" />
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}

          {tab === 'stress' && (
            <div className="panel">
              <div className="panel-head">
                <h6 className="panel-title">
                  <span className="kicker" />
                  压力测试（默认 4 场景）
                </h6>
                <button type="button" className="btn btn-primary btn-sm" disabled={stressBusy} onClick={runStress}>
                  {stressBusy ? '测试中…' : '运行压力测试'}
                </button>
              </div>
              <div className="panel-body">
                {stressBusy && <Loading text="模拟极端场景..." />}
                {stressResult && !stressBusy && (
                  <>
                    <div className="stat-grid mb-3">
                      <div className="stat">
                        <div className="stat-label">最坏情况</div>
                        <div className="stat-value text-down" style={{ fontSize: 18 }}>{stressResult.worst_case}</div>
                      </div>
                      <div className="stat">
                        <div className="stat-label">最好情况</div>
                        <div className="stat-value text-up" style={{ fontSize: 18 }}>{stressResult.best_case}</div>
                      </div>
                    </div>
                    <div className="table-container">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>场景</th>
                            <th className="num">原始价值</th>
                            <th className="num">压力后价值</th>
                            <th className="num">损益%</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(stressResult.scenarios ?? []).map((s) => (
                            <tr key={s.scenario_name}>
                              <td>{s.scenario_name}</td>
                              <td className="num">{formatNumber(s.original_value, 0)}</td>
                              <td className="num">{formatNumber(s.stressed_value, 0)}</td>
                              <td className={`num ${s.pnl_percentage >= 0 ? 'text-up' : 'text-down'}`}>{formatPercent(s.pnl_percentage)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
                {!stressResult && !stressBusy && <EmptyState icon="🧯" text="点击「运行压力测试」模拟极端行情" />}
              </div>
            </div>
          )}
        </>
      )}

      {!detail && !loading && !error && <EmptyState icon="🛡️" text="选择组合并点击「加载」查看风险数据" />}
    </div>
  )
}
