import { useEffect, useMemo, useState } from 'react'
import EChart from '../charts/EChart'
import { useTheme } from '../theme/ThemeContext'
import { fetchFactors, runQuantilePortfolioBacktest, type QuantilePortfolioResult } from '../api/mlFactor'
import { ErrorState, Loading } from '../components/StateViews'
import { addDaysLocal, formatNumber, formatPercent, pctClass, toLocalDate } from '../utils/format'

type Status = 'idle' | 'running' | 'done' | 'failed'

/** 后端收益为比率（0.05=5%），formatPercent 期望百分数值（5），先 ×100 */
const fmtPct = (v: number | null | undefined) => formatPercent(v == null ? v : v * 100)

// 分组折线配色循环（palette 只有少量语义色，分组多时循环取）
const GROUP_COLORS = ['#5b8ff9', '#61ddaa', '#f6bd16', '#7262fd', '#78d3f8', '#9661bc', '#f6903d', '#008685']

export default function MlFactorLabPage() {
  const { palette } = useTheme()
  const [factors, setFactors] = useState<{ factor_id: string; factor_name: string }[]>([])
  const [factorId, setFactorId] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [holdingDays, setHoldingDays] = useState(20)
  const [nQuantiles, setNQuantiles] = useState(5)
  const [costBps, setCostBps] = useState('10')

  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<QuantilePortfolioResult | null>(null)

  useEffect(() => {
    const end = new Date()
    setEndDate(toLocalDate(end))
    setStartDate(addDaysLocal(end, -365))
    fetchFactors()
      .then((r) => {
        const list = (r.factors ?? []).filter((f) => f.is_active)
        setFactors(list)
        if (list.length > 0) setFactorId(list[0].factor_id)
      })
      .catch(() => undefined)
  }, [])

  const quickRange = (days: number) => {
    const end = new Date()
    setEndDate(toLocalDate(end))
    setStartDate(addDaysLocal(end, -days))
  }

  const submit = async () => {
    setError(null)
    if (!factorId) {
      setError('请选择因子')
      return
    }
    if (!startDate || !endDate || startDate >= endDate) {
      setError('请设置有效的起止日期（开始 < 结束）')
      return
    }
    setStatus('running')
    setResult(null)
    try {
      const r = await runQuantilePortfolioBacktest({
        factor_id: factorId,
        start_date: startDate,
        end_date: endDate,
        holding_days: holdingDays,
        n_quantiles: nQuantiles,
        cost_bps: Number(costBps) || 0,
      })
      setResult(r)
      setStatus('done')
    } catch (e) {
      setError(e instanceof Error ? e.message : '回测失败')
      setStatus('failed')
    }
  }

  const groupIds = useMemo(() => {
    if (!result) return []
    return Object.keys(result.nav).sort()
  }, [result])

  const navOption = useMemo(() => {
    if (!result || groupIds.length === 0) return null
    const x = result.periods.map((p) => p.signal_date)
    const series = groupIds.map((g, i) => ({
      name: `${g}（因子${i === 0 ? '最低' : i === groupIds.length - 1 ? '最高' : `第${i + 1}档`}）`,
      type: 'line' as const,
      showSymbol: false,
      data: result.nav[g],
      lineStyle: { width: 1.5 },
      itemStyle: { color: GROUP_COLORS[i % GROUP_COLORS.length] },
    }))
    series.push({
      name: '多空（最高−最低）',
      type: 'line',
      showSymbol: false,
      data: result.nav_long_short,
      lineStyle: { width: 2.5 },
      itemStyle: { color: palette.accent },
    })
    return {
      tooltip: { trigger: 'axis' },
      legend: { top: 0, type: 'scroll' },
      grid: { left: 60, right: 20, top: 34, bottom: 28 },
      xAxis: { type: 'category', data: x, boundaryGap: false },
      yAxis: { type: 'value', scale: true, axisLabel: { formatter: (v: number) => v.toFixed(2) } },
      series,
    }
  }, [result, groupIds, palette])

  const spreadOption = useMemo(() => {
    if (!result || result.periods.length === 0) return null
    const pts = result.periods
      .map((p) => [p.signal_date, p.long_short_return]) as Array<[string, number | null]>
    return {
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => fmtPct(v) },
      grid: { left: 60, right: 20, top: 20, bottom: 28 },
      xAxis: { type: 'category', data: pts.map((p) => p[0]) },
      yAxis: { type: 'value', axisLabel: { formatter: (v: number) => `${(v * 100).toFixed(1)}%` } },
      series: [
        {
          type: 'bar',
          data: pts.map((p) => ({
            value: p[1],
            itemStyle: { color: p[1] != null && p[1] >= 0 ? palette.teal : '#e8684a' },
          })),
        },
      ],
    }
  }, [result, palette])

  const ls = result?.long_short_summary

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>因子实验室</h2>
          <p className="desc">分位组合净值回测：非重叠调仓分组净值 · 多空曲线 · 换手与交易成本</p>
        </div>
      </div>

      <div className="panel mb-3">
        <div className="panel-body">
          <div className="row g-2 align-items-end">
            <div className="col-md-3">
              <label className="form-label">因子</label>
              <select className="form-select" value={factorId} onChange={(e) => setFactorId(e.target.value)}>
                {factors.map((f) => (
                  <option key={f.factor_id} value={f.factor_id}>
                    {f.factor_id} · {f.factor_name}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-md-2">
              <label className="form-label">开始日期</label>
              <input type="date" className="form-control" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            </div>
            <div className="col-md-2">
              <label className="form-label">结束日期</label>
              <input type="date" className="form-control" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
            </div>
            <div className="col-6 col-md-1">
              <label className="form-label">分组</label>
              <input
                type="number"
                className="form-control"
                min={2}
                max={10}
                value={nQuantiles}
                onChange={(e) => setNQuantiles(Number(e.target.value) || 5)}
              />
            </div>
            <div className="col-6 col-md-1">
              <label className="form-label">持有天数</label>
              <input
                type="number"
                className="form-control"
                min={1}
                max={120}
                value={holdingDays}
                onChange={(e) => setHoldingDays(Number(e.target.value) || 20)}
              />
            </div>
            <div className="col-6 col-md-1">
              <label className="form-label">单边费率(bps)</label>
              <input type="number" className="form-control" min={0} step="1" value={costBps} onChange={(e) => setCostBps(e.target.value)} />
            </div>
            <div className="col-6 col-md-2 d-flex gap-2">
              <button type="button" className="btn btn-primary flex-fill" disabled={status === 'running'} onClick={submit}>
                {status === 'running' ? '回测中…' : '运行回测'}
              </button>
            </div>
          </div>
          <div className="mt-2 d-flex gap-2">
            {[
              [90, '近3个月'],
              [180, '近半年'],
              [365, '近1年'],
              [730, '近2年'],
            ].map(([d, label]) => (
              <button key={d} type="button" className="btn btn-outline-secondary btn-sm" onClick={() => quickRange(d as number)}>
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && <ErrorState message={error} />}
      {status === 'running' && <Loading text="分位组合回测运行中..." />}

      {result && status === 'done' && (
        <>
          <div className="stat-grid">
            <div className="stat">
              <div className="stat-value">{result.n_periods}</div>
              <div className="stat-label">完整调仓期数</div>
            </div>
            <div className="stat">
              <div className="stat-value">{ls ? fmtPct(ls.annualized_return) : '--'}</div>
              <div className="stat-label">多空年化收益</div>
            </div>
            <div className="stat">
              <div className="stat-value">{ls ? formatNumber(ls.sharpe, 2) : '--'}</div>
              <div className="stat-label">多空夏普</div>
            </div>
            <div className="stat">
              <div className="stat-value">{ls ? fmtPct(ls.max_drawdown) : '--'}</div>
              <div className="stat-label">多空最大回撤</div>
            </div>
            <div className="stat">
              <div className="stat-value">{ls ? fmtPct(ls.win_rate) : '--'}</div>
              <div className="stat-label">多空胜率</div>
            </div>
          </div>

          <div className="text-faint mb-3" style={{ fontSize: 12 }}>
            信号日收盘分桶 → T+1 收盘成交，非重叠持有 {result.holding_days} 个交易日；末个信号日无完整持有期已剔除。
            区间 {result.first_signal_date} ~ {result.last_signal_date}，单边费率 {result.cost_bps} bps（按换手扣双边）。
          </div>

          <div className="row g-3">
            <div className="col-12">
              <div className="panel">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    分组净值曲线
                  </h6>
                </div>
                <div className="panel-body">{navOption ? <EChart option={navOption} height={340} /> : null}</div>
              </div>
            </div>
            <div className="col-xl-7">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    逐期多空收益
                  </h6>
                </div>
                <div className="panel-body">{spreadOption ? <EChart option={spreadOption} height={280} /> : null}</div>
              </div>
            </div>
            <div className="col-xl-5">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    分组绩效汇总
                  </h6>
                </div>
                <div className="panel-body tight table-container" style={{ maxHeight: 312 }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>分组</th>
                        <th className="num">年化收益</th>
                        <th className="num">夏普</th>
                        <th className="num">最大回撤</th>
                        <th className="num">平均换手</th>
                      </tr>
                    </thead>
                    <tbody>
                      {groupIds.map((g) => {
                        const s = result.groups_summary[g]
                        return (
                          <tr key={g}>
                            <td>
                              <code>{g}</code>
                            </td>
                            <td className={`num ${pctClass(s?.annualized_return)}`}>
                              {s ? fmtPct(s.annualized_return) : '--'}
                            </td>
                            <td className="num">{s ? formatNumber(s.sharpe, 2) : '--'}</td>
                            <td className="num">{s ? fmtPct(s.max_drawdown) : '--'}</td>
                            <td className="num">{result.avg_turnover[g] != null ? formatNumber(result.avg_turnover[g], 2) : '--'}</td>
                          </tr>
                        )
                      })}
                      <tr>
                        <td>
                          <code>多空</code>
                        </td>
                        <td className={`num ${pctClass(ls?.annualized_return)}`}>{ls ? fmtPct(ls.annualized_return) : '--'}</td>
                        <td className="num">{ls ? formatNumber(ls.sharpe, 2) : '--'}</td>
                        <td className="num">{ls ? fmtPct(ls.max_drawdown) : '--'}</td>
                        <td className="num">—</td>
                      </tr>
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
