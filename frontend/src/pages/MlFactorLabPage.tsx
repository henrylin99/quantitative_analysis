import { useEffect, useMemo, useState } from 'react'
import EChart from '../charts/EChart'
import { useTheme } from '../theme/ThemeContext'
import {
  fetchFactors,
  fetchQualityReport,
  fetchScreeningList,
  runFactorScreening,
  runIcDecayAnalysis,
  runQuantilePortfolioBacktest,
  setScreeningStatus,
  type IcDecayResult,
  type QuantilePortfolioResult,
  type QualityReport,
  type ScreeningMetrics,
  type ScreeningRecord,
} from '../api/mlFactor'
import { ErrorState, Loading } from '../components/StateViews'
import { addDaysLocal, formatNumber, formatPercent, pctClass, toLocalDate } from '../utils/format'

type Status = 'idle' | 'running' | 'done' | 'failed'
type TabKey = 'backtest' | 'ic' | 'screening' | 'quality'

const TABS: Array<{ key: TabKey; label: string }> = [
  { key: 'backtest', label: '分位回测' },
  { key: 'ic', label: 'IC 衰减' },
  { key: 'screening', label: '因子体检' },
  { key: 'quality', label: '质量监控' },
]

/** 后端收益为比率（0.05=5%），formatPercent 期望百分数值（5），先 ×100 */
const fmtPct = (v: number | null | undefined) => formatPercent(v == null ? v : v * 100)

// 分组折线配色循环（palette 只有少量语义色，分组多时循环取）
const GROUP_COLORS = ['#5b8ff9', '#61ddaa', '#f6bd16', '#7262fd', '#78d3f8', '#9661bc', '#f6903d', '#008685']

export default function MlFactorLabPage() {
  const { palette } = useTheme()
  const [activeTab, setActiveTab] = useState<TabKey>('backtest')
  const [factors, setFactors] = useState<{ factor_id: string; factor_name: string }[]>([])
  const [factorId, setFactorId] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')

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

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>因子实验室</h2>
          <p className="desc">分位组合回测 · IC 衰减 · 因子体检与生命周期 · 数据质量监控</p>
        </div>
      </div>

      <div className="seg mb-3" role="group" style={{ flexWrap: 'wrap' }}>
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            className={`seg-item ${activeTab === tab.key ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'backtest' && (
        <BacktestTab
          factors={factors}
          factorId={factorId}
          setFactorId={setFactorId}
          startDate={startDate}
          endDate={endDate}
          setStartDate={setStartDate}
          setEndDate={setEndDate}
          quickRange={quickRange}
          palette={palette}
        />
      )}
      {activeTab === 'ic' && (
        <IcDecayTab
          factors={factors}
          factorId={factorId}
          setFactorId={setFactorId}
          startDate={startDate}
          endDate={endDate}
          quickRange={quickRange}
          palette={palette}
        />
      )}
      {activeTab === 'screening' && (
        <ScreeningTab
          startDate={startDate}
          endDate={endDate}
          quickRange={quickRange}
        />
      )}
      {activeTab === 'quality' && <QualityTab palette={palette} />}
    </div>
  )
}

type TabShared = {
  factors: { factor_id: string; factor_name: string }[]
  factorId: string
  setFactorId: (v: string) => void
  startDate: string
  endDate: string
  quickRange: (days: number) => void
  palette: ReturnType<typeof useTheme>['palette']
}

function FactorSelect({ factors, factorId, setFactorId }: Pick<TabShared, 'factors' | 'factorId' | 'setFactorId'>) {
  return (
    <select className="form-select" value={factorId} onChange={(e) => setFactorId(e.target.value)}>
      {factors.map((f) => (
        <option key={f.factor_id} value={f.factor_id}>
          {f.factor_id} · {f.factor_name}
        </option>
      ))}
    </select>
  )
}

// ================= 分位回测 =================

function BacktestTab(props: TabShared & { setStartDate: (v: string) => void; setEndDate: (v: string) => void }) {
  const { palette } = props
  const [holdingDays, setHoldingDays] = useState(20)
  const [nQuantiles, setNQuantiles] = useState(5)
  const [costBps, setCostBps] = useState('10')
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<QuantilePortfolioResult | null>(null)

  const submit = async () => {
    setError(null)
    if (!props.factorId) {
      setError('请选择因子')
      return
    }
    if (!props.startDate || !props.endDate || props.startDate >= props.endDate) {
      setError('请设置有效的起止日期（开始 < 结束）')
      return
    }
    setStatus('running')
    setResult(null)
    try {
      const r = await runQuantilePortfolioBacktest({
        factor_id: props.factorId,
        start_date: props.startDate,
        end_date: props.endDate,
        holding_days: holdingDays,
        n_quantiles: nQuantiles,
        cost_bps: Number(costBps) || 0,
        cost_bps_list: [0, 5, 10, 15, 20],
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
      <div className="panel mb-3">
        <div className="panel-body">
          <div className="row g-2 align-items-end">
            <div className="col-md-3">
              <label className="form-label">因子</label>
              <FactorSelect factors={props.factors} factorId={props.factorId} setFactorId={props.setFactorId} />
            </div>
            <div className="col-md-2">
              <label className="form-label">开始日期</label>
              <input type="date" className="form-control" value={props.startDate} onChange={(e) => props.setStartDate(e.target.value)} />
            </div>
            <div className="col-md-2">
              <label className="form-label">结束日期</label>
              <input type="date" className="form-control" value={props.endDate} onChange={(e) => props.setEndDate(e.target.value)} />
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
              <button key={d} type="button" className="btn btn-outline-secondary btn-sm" onClick={() => props.quickRange(d as number)}>
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
                            <td className={`num ${pctClass(s?.annualized_return)}`}>{s ? fmtPct(s.annualized_return) : '--'}</td>
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

            {/* 成本敏感性 */}
            <div className="col-xl-5">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    成本敏感性（多空年化）
                  </h6>
                </div>
                <div className="panel-body tight table-container" style={{ maxHeight: 260 }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>单边费率(bps)</th>
                        <th className="num">年化收益</th>
                        <th className="num">夏普</th>
                        <th className="num">胜率</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(result.cost_sensitivity ?? {})
                        .sort((a, b) => Number(a[0]) - Number(b[0]))
                        .map(([cost, s]) => (
                          <tr key={cost}>
                            <td>
                              <code>{cost}</code>
                            </td>
                            <td className={`num ${pctClass(s.annualized_return)}`}>{fmtPct(s.annualized_return)}</td>
                            <td className="num">{formatNumber(s.sharpe, 2)}</td>
                            <td className="num">{fmtPct(s.win_rate)}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* 分年拆解 */}
            <div className="col-xl-7">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    分年拆解（多空）
                  </h6>
                </div>
                <div className="panel-body tight table-container" style={{ maxHeight: 260 }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>年份</th>
                        <th className="num">期数</th>
                        <th className="num">年化收益</th>
                        <th className="num">夏普</th>
                        <th className="num">最大回撤</th>
                        <th className="num">胜率</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(result.yearly_breakdown ?? {}).map(([year, y]) => (
                        <tr key={year}>
                          <td>
                            <code>{year}</code>
                          </td>
                          <td className="num">{y.n_periods}</td>
                          <td className={`num ${pctClass(y.long_short.annualized_return)}`}>
                            {fmtPct(y.long_short.annualized_return)}
                          </td>
                          <td className="num">{formatNumber(y.long_short.sharpe, 2)}</td>
                          <td className="num">{fmtPct(y.long_short.max_drawdown)}</td>
                          <td className="num">{fmtPct(y.long_short.win_rate)}</td>
                        </tr>
                      ))}
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

// ================= IC 衰减 =================

function IcDecayTab(props: TabShared) {
  const { palette } = props
  const [rollingWindow, setRollingWindow] = useState(20)
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<IcDecayResult | null>(null)

  const submit = async () => {
    setError(null)
    if (!props.factorId) {
      setError('请选择因子')
      return
    }
    setStatus('running')
    setResult(null)
    try {
      const r = await runIcDecayAnalysis({
        factor_id: props.factorId,
        start_date: props.startDate || undefined,
        end_date: props.endDate || undefined,
        forward_periods: [1, 5, 10, 20],
        rolling_window: rollingWindow,
      })
      setResult(r)
      setStatus('done')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'IC 衰减分析失败')
      setStatus('failed')
    }
  }

  const horizonOption = useMemo(() => {
    if (!result) return null
    const horizons = Object.keys(result.ic_by_horizon).sort((a, b) => Number(a) - Number(b))
    return {
      tooltip: { trigger: 'axis' },
      legend: { top: 0 },
      grid: { left: 60, right: 20, top: 34, bottom: 28 },
      xAxis: { type: 'category', data: horizons.map((h) => `${h}d`) },
      yAxis: { type: 'value' },
      series: [
        {
          name: 'IC 均值',
          type: 'bar',
          data: horizons.map((h) => result.ic_by_horizon[h].ic_mean ?? 0),
          itemStyle: { color: palette.accent },
        },
        {
          name: 'ICIR',
          type: 'line',
          data: horizons.map((h) => result.ic_by_horizon[h].ic_ir ?? 0),
          itemStyle: { color: palette.teal },
        },
      ],
    }
  }, [result, palette])

  const rollingOption = useMemo(() => {
    if (!result || result.rolling_ic.length === 0) return null
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: 60, right: 20, top: 20, bottom: 28 },
      xAxis: { type: 'category', data: result.rolling_ic.map((p) => p.date), boundaryGap: false },
      yAxis: { type: 'value' },
      series: [
        {
          type: 'line',
          showSymbol: false,
          data: result.rolling_ic.map((p) => p.rolling_ic),
          itemStyle: { color: palette.accent },
          areaStyle: { color: palette.accent, opacity: 0.1 },
          markLine: {
            silent: true,
            symbol: 'none',
            data: [{ yAxis: 0 }],
            lineStyle: { type: 'dashed', color: '#999' },
          },
        },
      ],
    }
  }, [result, palette])

  return (
    <div>
      <div className="panel mb-3">
        <div className="panel-body">
          <div className="row g-2 align-items-end">
            <div className="col-md-3">
              <label className="form-label">因子</label>
              <FactorSelect factors={props.factors} factorId={props.factorId} setFactorId={props.setFactorId} />
            </div>
            <div className="col-md-2">
              <label className="form-label">开始日期</label>
              <input type="date" className="form-control" value={props.startDate} disabled title="沿用分位回测 Tab 的日期设置" />
            </div>
            <div className="col-md-2">
              <label className="form-label">结束日期</label>
              <input type="date" className="form-control" value={props.endDate} disabled title="沿用分位回测 Tab 的日期设置" />
            </div>
            <div className="col-6 col-md-2">
              <label className="form-label">滚动窗口(日)</label>
              <input
                type="number"
                className="form-control"
                min={2}
                value={rollingWindow}
                onChange={(e) => setRollingWindow(Number(e.target.value) || 20)}
              />
            </div>
            <div className="col-6 col-md-3">
              <button type="button" className="btn btn-primary w-100" disabled={status === 'running'} onClick={submit}>
                {status === 'running' ? '分析中…' : '运行 IC 衰减分析'}
              </button>
              <div className="text-faint mt-1" style={{ fontSize: 11 }}>
                区间沿用顶部快捷按钮设置，前向期固定 1/5/10/20d
              </div>
            </div>
          </div>
        </div>
      </div>

      {error && <ErrorState message={error} />}
      {status === 'running' && <Loading text="IC 衰减分析运行中..." />}

      {result && status === 'done' && (
        <div className="row g-3">
          <div className="col-12">
            <div className="stat-grid">
              <div className="stat">
                <div className="stat-value">
                  {result.ic_half_life_days != null ? `${formatNumber(result.ic_half_life_days, 1)} 天` : '—'}
                </div>
                <div className="stat-label">IC 半衰期</div>
              </div>
              <div className="stat">
                <div className="stat-value">{Object.keys(result.ic_by_horizon).length}</div>
                <div className="stat-label">前向期数</div>
              </div>
              <div className="stat">
                <div className="stat-value">
                  {result.rolling_ic.length > 0
                    ? formatNumber(result.rolling_ic[result.rolling_ic.length - 1].rolling_ic, 4)
                    : '--'}
                </div>
                <div className="stat-label">最新滚动 IC</div>
              </div>
            </div>
          </div>
          <div className="col-xl-5">
            <div className="panel h-100">
              <div className="panel-head">
                <h6 className="panel-title">
                  <span className="kicker" />
                  IC vs 前向天数
                </h6>
              </div>
              <div className="panel-body">{horizonOption ? <EChart option={horizonOption} height={300} /> : null}</div>
            </div>
          </div>
          <div className="col-xl-7">
            <div className="panel h-100">
              <div className="panel-head">
                <h6 className="panel-title">
                  <span className="kicker" />
                  滚动 IC（{result.rolling_window} 日均值）
                </h6>
              </div>
              <div className="panel-body">{rollingOption ? <EChart option={rollingOption} height={300} /> : null}</div>
            </div>
          </div>
          <div className="col-12">
            <div className="panel">
              <div className="panel-head">
                <h6 className="panel-title">
                  <span className="kicker" />
                  分年 IC 稳定性
                </h6>
              </div>
              <div className="panel-body tight table-container">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>年份</th>
                      {result.forward_periods.map((h) => (
                        <th key={h} className="num">
                          {h}d IC
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(result.yearly_ic).map(([year, row]) => (
                      <tr key={year}>
                        <td>
                          <code>{year}</code>
                        </td>
                        {result.forward_periods.map((h) => {
                          const v = row[String(h)]
                          return (
                            <td key={h} className={`num ${v != null ? pctClass(v) : ''}`}>
                              {v != null ? formatNumber(v, 4) : '--'}
                            </td>
                          )
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ================= 因子体检 =================

function ScreeningTab(props: { startDate: string; endDate: string; quickRange: (days: number) => void }) {
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState<string | null>(null)
  const [records, setRecords] = useState<ScreeningRecord[]>([])
  const [busyId, setBusyId] = useState<string | null>(null)

  const loadRecords = () => {
    fetchScreeningList()
      .then((r) => setRecords(r.records ?? []))
      .catch(() => undefined)
  }
  useEffect(loadRecords, [])

  const submit = async () => {
    setStatus('running')
    setError(null)
    try {
      await runFactorScreening({
        start_date: props.startDate || undefined,
        end_date: props.endDate || undefined,
        forward_period: 5,
        sample_stride: 5,
      })
      loadRecords()
      setStatus('done')
    } catch (e) {
      setError(e instanceof Error ? e.message : '因子体检失败')
      setStatus('failed')
    }
  }

  const updateStatus = async (factorId: string, newStatus: string) => {
    setBusyId(factorId)
    try {
      await setScreeningStatus({ factor_id: factorId, status: newStatus })
      loadRecords()
    } catch {
      /* 状态更新失败不阻塞 */
    } finally {
      setBusyId(null)
    }
  }

  const rows = useMemo(() => {
    const byId = new Map<string, { rec: ScreeningRecord; m: ScreeningMetrics }>()
    for (const rec of records) {
      const prev = byId.get(rec.factor_id)
      if (!prev || String(prev.rec.screened_at) < String(rec.screened_at)) {
        byId.set(rec.factor_id, { rec, m: rec.metrics ?? {} })
      }
    }
    return [...byId.values()].sort(
      (a, b) => Math.abs(b.m.ic_mean ?? 0) - Math.abs(a.m.ic_mean ?? 0),
    )
  }, [records])

  return (
    <div>
      <div className="panel mb-3">
        <div className="panel-body">
          <div className="d-flex gap-2 align-items-end flex-wrap">
            <div>
              <label className="form-label">体检区间</label>
              <div className="text-faint" style={{ fontSize: 12 }}>
                {props.startDate} ~ {props.endDate}（沿用顶部设置，未设日期时后端默认最近两年）
              </div>
            </div>
            <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => props.quickRange(365)}>
              近1年
            </button>
            <button type="button" className="btn btn-primary" disabled={status === 'running'} onClick={submit}>
              {status === 'running' ? '体检中（分钟级）…' : '一键批量体检全部活跃因子'}
            </button>
          </div>
          <div className="text-faint mt-2" style={{ fontSize: 12 }}>
            指标：5 日前向 IC / ICIR / 分层单调性 / 秩自相关（换手代理）/ 覆盖数 / 共线性。结论入库后状态为 evaluated，可手动 accept / reject，
            accepted 白名单可喂 ML 特征选择。
          </div>
        </div>
      </div>

      {error && <ErrorState message={error} />}
      {status === 'running' && <Loading text="批量体检运行中（220 因子约数分钟）..." />}

      {rows.length > 0 && (
        <div className="panel">
          <div className="panel-head">
            <h6 className="panel-title">
              <span className="kicker" />
              体检报告（{rows.length} 因子，按 |IC| 降序）
            </h6>
          </div>
          <div className="panel-body tight table-container" style={{ maxHeight: 560 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>因子</th>
                  <th>状态</th>
                  <th className="num">IC</th>
                  <th className="num">ICIR</th>
                  <th className="num">t 值</th>
                  <th className="num">单调性</th>
                  <th className="num">秩自相关</th>
                  <th className="num">覆盖</th>
                  <th>最相关因子</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(({ rec, m }) => (
                  <tr key={rec.factor_id}>
                    <td>
                      <code>{rec.factor_id}</code>
                    </td>
                    <td>
                      <span
                        className={`badge ${rec.status === 'accepted' ? 'bg-success' : rec.status === 'rejected' ? 'bg-danger' : 'bg-secondary'}`}
                      >
                        {rec.status}
                      </span>
                    </td>
                    <td className={`num ${m.ic_mean != null ? pctClass(m.ic_mean) : ''}`}>
                      {m.ic_mean != null ? formatNumber(m.ic_mean, 4) : m.error ?? '--'}
                    </td>
                    <td className="num">{m.ic_ir != null ? formatNumber(m.ic_ir, 2) : '--'}</td>
                    <td className="num">{m.t_stat != null ? formatNumber(m.t_stat, 2) : '--'}</td>
                    <td className="num">{m.monotonicity != null ? formatNumber(m.monotonicity, 2) : '--'}</td>
                    <td className="num">{m.rank_autocorr != null ? formatNumber(m.rank_autocorr, 2) : '--'}</td>
                    <td className="num">{m.avg_coverage != null ? Math.round(m.avg_coverage) : '--'}</td>
                    <td className="text-faint" style={{ fontSize: 12 }}>
                      {m.most_correlated ? `${m.most_correlated} (${formatNumber(m.max_abs_corr ?? 0, 2)})` : '--'}
                    </td>
                    <td>
                      <div className="d-flex gap-1">
                        <button
                          type="button"
                          className="btn btn-outline-success btn-sm"
                          disabled={busyId === rec.factor_id || rec.status === 'accepted'}
                          onClick={() => updateStatus(rec.factor_id, 'accepted')}
                        >
                          ✓
                        </button>
                        <button
                          type="button"
                          className="btn btn-outline-danger btn-sm"
                          disabled={busyId === rec.factor_id || rec.status === 'rejected'}
                          onClick={() => updateStatus(rec.factor_id, 'rejected')}
                        >
                          ✕
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

// ================= 质量监控 =================

function QualityTab({ palette }: { palette: ReturnType<typeof useTheme>['palette'] }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [report, setReport] = useState<QualityReport | null>(null)

  const load = () => {
    setLoading(true)
    setError(null)
    fetchQualityReport(60)
      .then(setReport)
      .catch((e) => setError(e instanceof Error ? e.message : '质量报告加载失败'))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const coverageOption = useMemo(() => {
    if (!report) return null
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: 60, right: 20, top: 20, bottom: 40 },
      xAxis: {
        type: 'category',
        data: report.coverage_trend.partitions,
        axisLabel: { rotate: 45, fontSize: 10 },
      },
      yAxis: { type: 'value', name: '覆盖中位数' },
      series: [
        {
          type: 'line',
          showSymbol: false,
          data: report.coverage_trend.coverage_median,
          itemStyle: { color: palette.accent },
        },
      ],
    }
  }, [report, palette])

  return (
    <div>
      <div className="panel mb-3">
        <div className="panel-body d-flex gap-2 align-items-center">
          <div className="flex-fill">
            <div className="text-faint" style={{ fontSize: 12 }}>
              {report
                ? `扫描最近 ${report.scanned_partitions} 个分区（${report.first_partition} ~ ${report.last_partition}），报警 ${report.n_alerts} 条`
                : '按分区扫描覆盖数/均值/方差，检测覆盖骤降、因子缺席、均值漂移与分区缺口'}
            </div>
          </div>
          <button type="button" className="btn btn-primary" onClick={load} disabled={loading}>
            {loading ? '扫描中…' : '重新扫描'}
          </button>
        </div>
      </div>

      {error && <ErrorState message={error} onRetry={load} />}
      {loading && !report && <Loading text="质量扫描运行中..." />}

      {report && (
        <div className="row g-3">
          {report.partition_gaps.length > 0 && (
            <div className="col-12">
              <div className="panel">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    分区完整性
                  </h6>
                </div>
                <div className="panel-body">
                  {report.partition_gaps.map((g) => (
                    <div key={g.type} className="mb-2">
                      <span className="badge bg-warning text-dark">{g.type}</span>{' '}
                      <span className="text-faint" style={{ fontSize: 12 }}>
                        {g.detail}
                        {g.dates && g.dates.length > 0 ? `（如 ${g.dates.slice(0, 5).join(', ')}）` : ''}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
          <div className="col-xl-6">
            <div className="panel h-100">
              <div className="panel-head">
                <h6 className="panel-title">
                  <span className="kicker" />
                  截面覆盖中位数时序
                </h6>
              </div>
              <div className="panel-body">{coverageOption ? <EChart option={coverageOption} height={320} /> : null}</div>
            </div>
          </div>
          <div className="col-xl-6">
            <div className="panel h-100">
              <div className="panel-head">
                <h6 className="panel-title">
                  <span className="kicker" />
                  报警（{report.n_alerts}）
                </h6>
              </div>
              <div className="panel-body tight table-container" style={{ maxHeight: 340 }}>
                {report.alerts.length === 0 ? (
                  <div className="text-faint p-2">无报警</div>
                ) : (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>类型</th>
                        <th>因子</th>
                        <th>说明</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.alerts.map((a, i) => (
                        <tr key={i}>
                          <td>
                            <span className="badge bg-warning text-dark">{a.type}</span>
                          </td>
                          <td>
                            <code>{a.factor_id ?? '-'}</code>
                          </td>
                          <td className="text-faint" style={{ fontSize: 12 }}>
                            {a.detail}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
