import { useEffect, useMemo, useState } from 'react'
import EChart from '../charts/EChart'
import { useTheme } from '../theme/ThemeContext'
import { fetchMlAnalysisData, generateMlReport, type MlAnalysisData } from '../api/mlFactor'
import { Loading } from '../components/StateViews'
import { formatNumber } from '../utils/format'

export default function MlAnalysisPage() {
  const { palette } = useTheme()
  const [data, setData] = useState<MlAnalysisData | null>(null)
  const [loading, setLoading] = useState(true)
  const [msg, setMsg] = useState<string | null>(null)
  const [genBusy, setGenBusy] = useState(false)

  const load = () => {
    setLoading(true)
    fetchMlAnalysisData()
      .then(setData)
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const handleGenerate = async () => {
    setGenBusy(true)
    setMsg(null)
    try {
      await generateMlReport()
      setMsg('报告已生成，正在刷新数据…')
      setTimeout(load, 800)
    } catch (e) {
      setMsg(e instanceof Error ? e.message : '生成报告失败')
    } finally {
      setGenBusy(false)
    }
  }

  const handleExport = () => {
    window.open('/api/ml-factor/analysis/export-report', '_blank')
  }

  const modelPerfOption = useMemo(() => {
    const perf = data?.modelPerformance?.performance_data
    if (!perf || perf.length === 0) return null
    return {
      tooltip: { trigger: 'axis' },
      legend: { top: 0 },
      grid: { left: 52, right: 20, top: 34, bottom: 28 },
      xAxis: { type: 'category', data: perf.map((p) => p.date), boundaryGap: false },
      yAxis: { type: 'value' },
      series: [
        { name: '训练R²', type: 'line', showSymbol: false, data: perf.map((p) => p.train_r2), itemStyle: { color: palette.accent } },
        { name: '测试R²', type: 'line', showSymbol: false, data: perf.map((p) => p.test_r2), itemStyle: { color: palette.teal } },
        { name: 'MAE', type: 'line', showSymbol: false, data: perf.map((p) => p.mae), itemStyle: { color: palette.amber } },
      ],
    }
  }, [data, palette])

  const comparisonOption = useMemo(() => {
    const comp = data?.modelPerformance?.comparison_data
    if (!comp || comp.length === 0) return null
    return {
      tooltip: { trigger: 'axis' },
      legend: { top: 0 },
      grid: { left: 52, right: 20, top: 34, bottom: 28 },
      xAxis: { type: 'category', data: comp.map((c) => c.model_type) },
      yAxis: { type: 'value' },
      series: [
        { name: 'R²得分', type: 'bar', data: comp.map((c) => c.r2_score), itemStyle: { color: palette.accent } },
        { name: 'MAE得分', type: 'bar', data: comp.map((c) => c.mae_score), itemStyle: { color: palette.amber } },
      ],
    }
  }, [data, palette])

  const importanceOption = useMemo(() => {
    const imp = data?.factorEffectiveness?.importance_data
    if (!imp || imp.length === 0) return null
    const top = imp.slice(0, 15)
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: 130, right: 24, top: 12, bottom: 28 },
      xAxis: { type: 'value' },
      yAxis: { type: 'category', data: top.map((d) => d.factor_name).reverse() },
      series: [{ type: 'bar', data: top.map((d) => d.importance).reverse(), itemStyle: { color: palette.violet } }],
    }
  }, [data, palette])

  const portfolioOption = useMemo(() => {
    const perf = data?.portfolioPerformance?.performance_data
    if (!perf || perf.length === 0) return null
    return {
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => `${formatNumber(Number(v), 2)}%` },
      legend: { top: 0 },
      grid: { left: 56, right: 20, top: 34, bottom: 28 },
      xAxis: { type: 'category', data: perf.map((p) => p.date), boundaryGap: false },
      yAxis: { type: 'value', axisLabel: { formatter: '{value}%' } },
      series: [
        {
          name: '组合收益',
          type: 'line',
          showSymbol: false,
          data: perf.map((p) => p.portfolio_return),
          itemStyle: { color: palette.accent },
          areaStyle: { color: palette.accent, opacity: 0.12 },
        },
      ],
    }
  }, [data, palette])

  const riskOption = useMemo(() => {
    const risk = data?.riskAnalysis?.risk_data
    if (!risk || risk.length === 0) return null
    return {
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: { type: 'scroll', bottom: 0 },
      series: [
        {
          type: 'pie',
          radius: '50%',
          data: risk.map((r) => ({ name: r.name, value: r.value })),
        },
      ],
    }
  }, [data])

  const p = data?.portfolioPerformance

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>多因子分析报告</h2>
          <p className="desc">模型性能 · 因子有效性 · 组合表现 · 风险分布</p>
        </div>
        <div className="d-flex gap-2">
          <button type="button" className="btn btn-outline-primary btn-sm" disabled={genBusy} onClick={handleGenerate}>
            {genBusy ? '生成中…' : '生成报告'}
          </button>
          <button type="button" className="btn btn-outline-secondary btn-sm" onClick={handleExport}>
            导出
          </button>
        </div>
      </div>

      {msg && <div className="alert-note mb-3">{msg}</div>}
      {loading && <Loading text="聚合分析数据（模型较多时较慢）..." />}

      {data && !loading && (
        <>
          <div className="stat-grid">
            <div className="stat">
              <div className="stat-value">{data.modelPerformance?.total_models ?? 0}</div>
              <div className="stat-label">模型总数</div>
            </div>
            <div className="stat">
              <div className="stat-value">{formatNumber(data.modelPerformance?.best_r2 ?? null, 3)}</div>
              <div className="stat-label">最高模型 R²</div>
            </div>
            <div className="stat">
              <div className="stat-value">{data.factorEffectiveness?.active_factors ?? 0}</div>
              <div className="stat-label">活跃因子数</div>
            </div>
            <div className="stat">
              <div className="stat-value">{data.portfolioPerformance?.portfolio_count ?? 0}</div>
              <div className="stat-label">投资组合数</div>
            </div>
          </div>

          {(p?.annual_return != null || p?.sharpe_ratio != null) && (
            <div className="stat-grid">
              <div className="stat">
                <div className="stat-value">{formatNumber(p?.annual_return ?? null, 2)}%</div>
                <div className="stat-label">年化收益率</div>
              </div>
              <div className="stat">
                <div className="stat-value">{p?.max_drawdown != null ? formatNumber(p.max_drawdown, 2) + '%' : '—'}</div>
                <div className="stat-label">最大回撤</div>
              </div>
              <div className="stat">
                <div className="stat-value">{p?.sharpe_ratio != null ? formatNumber(p.sharpe_ratio, 2) : '—'}</div>
                <div className="stat-label">夏普比率</div>
              </div>
              <div className="stat">
                <div className="stat-value">{p?.win_rate != null ? formatNumber(p.win_rate, 1) + '%' : '—'}</div>
                <div className="stat-label">胜率</div>
              </div>
            </div>
          )}

          <div className="row g-3">
            <div className="col-xl-6">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    模型性能趋势
                  </h6>
                </div>
                <div className="panel-body">
                  {modelPerfOption ? <EChart option={modelPerfOption} height={300} /> : <EmptyChart />}
                </div>
              </div>
            </div>
            <div className="col-xl-6">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    模型类型对比
                  </h6>
                </div>
                <div className="panel-body">{comparisonOption ? <EChart option={comparisonOption} height={300} /> : <EmptyChart />}</div>
              </div>
            </div>
            <div className="col-xl-6">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    因子重要性 TOP15
                  </h6>
                </div>
                <div className="panel-body">{importanceOption ? <EChart option={importanceOption} height={320} /> : <EmptyChart />}</div>
              </div>
            </div>
            <div className="col-xl-6">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    组合收益趋势
                  </h6>
                </div>
                <div className="panel-body">{portfolioOption ? <EChart option={portfolioOption} height={320} /> : <EmptyChart />}</div>
              </div>
            </div>
            <div className="col-xl-6">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    行业/板块权重分布
                  </h6>
                </div>
                <div className="panel-body">{riskOption ? <EChart option={riskOption} height={320} /> : <EmptyChart />}</div>
              </div>
            </div>
            <div className="col-xl-6">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    因子统计
                  </h6>
                </div>
                <div className="panel-body tight table-container" style={{ maxHeight: 320 }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>因子</th>
                        <th className="num">重要性</th>
                        <th className="num">相关性</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(data.factorEffectiveness?.importance_data ?? []).slice(0, 20).map((d) => (
                        <tr key={d.factor_name}>
                          <td>
                            <code>{d.factor_name}</code>
                          </td>
                          <td className="num">{formatNumber(d.importance, 3)}</td>
                          <td className="num">{d.correlation != null ? formatNumber(d.correlation, 3) : '--'}</td>
                        </tr>
                      ))}
                      {(data.factorEffectiveness?.importance_data ?? []).length === 0 && (
                        <tr>
                          <td colSpan={3} style={{ textAlign: 'center', color: 'var(--text-faint)' }}>
                            暂无数据
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function EmptyChart() {
  return <div style={{ height: 300, display: 'grid', placeItems: 'center', color: 'var(--text-faint)', fontSize: 13 }}>暂无数据</div>
}
