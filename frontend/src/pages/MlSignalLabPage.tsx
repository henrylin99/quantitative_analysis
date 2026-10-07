import { Fragment, useEffect, useMemo, useState } from 'react'
import EChart from '../charts/EChart'
import { useTheme } from '../theme/ThemeContext'
import {
  compareModels,
  fetchChipSignalBacktest,
  fetchChipSignals,
  fetchModelSnapshots,
  fetchModels,
  fetchPortfolios,
  fetchScreeningList,
  runPortfolioAttribution,
  runPredictionTracking,
  type AttributionResult,
  type ChipSignalBacktestResult,
  type ChipSignalRow,
  type ModelCompareRow,
  type ModelSnapshot,
  type PredictionTrackResult,
} from '../api/mlFactor'
import { ErrorState, Loading } from '../components/StateViews'
import { formatNumber, formatPercent, pctClass } from '../utils/format'

type Status = 'idle' | 'running' | 'done' | 'failed'
type TabKey = 'predictions' | 'attribution' | 'models' | 'chip'

const TABS: Array<{ key: TabKey; label: string }> = [
  { key: 'predictions', label: '预测跟踪' },
  { key: 'attribution', label: '组合归因' },
  { key: 'models', label: '模型对比' },
  { key: 'chip', label: '筹码信号' },
]

const fmtPct = (v: number | null | undefined) => formatPercent(v == null ? v : v * 100)

export default function MlSignalLabPage() {
  const { palette } = useTheme()
  const [activeTab, setActiveTab] = useState<TabKey>('predictions')
  return (
    <div>
      <div className="page-head">
        <div>
          <h2>信号实验室</h2>
          <p className="desc">预测信号滚动跟踪 · 组合因子暴露归因 · 模型训练快照对比 · 筹码截面信号</p>
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
      {activeTab === 'predictions' && <PredictionsTab palette={palette} />}
      {activeTab === 'attribution' && <AttributionTab palette={palette} />}
      {activeTab === 'models' && <ModelsTab />}
      {activeTab === 'chip' && <ChipTab />}
    </div>
  )
}

type Palette = ReturnType<typeof useTheme>['palette']

// ================= 预测跟踪 =================

function PredictionsTab({ palette }: { palette: Palette }) {
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<PredictionTrackResult | null>(null)
  const [selected, setSelected] = useState<string>('')

  const submit = async () => {
    setStatus('running')
    setError(null)
    try {
      const r = await runPredictionTracking({ horizons: [1, 5, 10], top_n: 50 })
      setResult(r)
      setSelected(r.model_ids[0] ?? '')
      setStatus('done')
    } catch (e) {
      setError(e instanceof Error ? e.message : '预测跟踪失败')
      setStatus('failed')
    }
  }

  const model = result?.models[selected]
  const icSeries = useMemo(() => model?.ic_series ?? [], [model])

  const icOption = useMemo(() => {
    if (icSeries.length === 0) return null
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: 60, right: 20, top: 20, bottom: 28 },
      xAxis: { type: 'category', data: icSeries.map((p) => p.date), boundaryGap: false },
      yAxis: { type: 'value' },
      series: [
        {
          type: 'bar',
          data: icSeries.map((p) => ({
            value: p.ic,
            itemStyle: { color: p.ic >= 0 ? palette.teal : '#e8684a' },
          })),
          name: '日 IC',
        },
      ],
    }
  }, [icSeries, palette])

  const topOption = useMemo(() => {
    const s = model?.top_n_series ?? []
    if (s.length === 0) return null
    return {
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => fmtPct(v) },
      legend: { top: 0 },
      grid: { left: 60, right: 20, top: 34, bottom: 28 },
      xAxis: { type: 'category', data: s.map((p) => p.date), boundaryGap: false },
      yAxis: { type: 'value', axisLabel: { formatter: (v: number) => `${(v * 100).toFixed(1)}%` } },
      series: [
        {
          name: 'top-N 收益',
          type: 'line',
          showSymbol: false,
          data: s.map((p) => p.top_return),
          itemStyle: { color: palette.accent },
        },
        {
          name: '基准（全截面）',
          type: 'line',
          showSymbol: false,
          data: s.map((p) => p.universe_return),
          itemStyle: { color: '#999' },
        },
      ],
    }
  }, [model, palette])

  const consistencyOption = useMemo(() => {
    const s = result?.model_consistency.series ?? []
    if (s.length === 0) return null
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: 60, right: 20, top: 20, bottom: 28 },
      xAxis: { type: 'category', data: s.map((p) => p.date), boundaryGap: false },
      yAxis: { type: 'value', min: -1, max: 1 },
      series: [
        {
          type: 'line',
          showSymbol: false,
          data: s.map((p) => p.mean_corr),
          itemStyle: { color: palette.violet },
        },
      ],
    }
  }, [result, palette])

  return (
    <div>
      <div className="panel mb-3">
        <div className="panel-body d-flex gap-2 align-items-center">
          <div className="flex-fill text-faint" style={{ fontSize: 12 }}>
            全部模型的沉淀预测：逐日预测 IC、top-N 前向实现收益、信号 horizon 衰减、多模型一致性（无日期时后端自动取全部预测）。
          </div>
          <button type="button" className="btn btn-primary" disabled={status === 'running'} onClick={submit}>
            {status === 'running' ? '跟踪中…' : '运行预测跟踪'}
          </button>
        </div>
      </div>

      {error && <ErrorState message={error} />}
      {status === 'running' && <Loading text="预测跟踪运行中..." />}

      {result && status === 'done' && (
        <div className="row g-3">
          <div className="col-12 d-flex gap-2 flex-wrap">
            {result.model_ids.map((mid) => (
              <button
                key={mid}
                type="button"
                className={`btn btn-sm ${selected === mid ? 'btn-primary' : 'btn-outline-secondary'}`}
                onClick={() => setSelected(mid)}
              >
                {mid}
              </button>
            ))}
          </div>

          {model && !model.error && (
            <>
              <div className="col-12">
                <div className="stat-grid">
                  <div className="stat">
                    <div className="stat-value">{model.summary.n_dates}</div>
                    <div className="stat-label">预测交易日</div>
                  </div>
                  <div className="stat">
                    <div className="stat-value">
                      {model.summary.spread_mean != null ? fmtPct(model.summary.spread_mean) : '--'}
                    </div>
                    <div className="stat-label">top−bottom 日均价差</div>
                  </div>
                  <div className="stat">
                    <div className="stat-value">
                      {model.summary.spread_win_rate != null ? fmtPct(model.summary.spread_win_rate) : '--'}
                    </div>
                    <div className="stat-label">价差胜率</div>
                  </div>
                  <div className="stat">
                    <div className="stat-value">
                      {model.summary.top_excess_ir != null ? formatNumber(model.summary.top_excess_ir, 2) : '--'}
                    </div>
                    <div className="stat-label">超额信息比</div>
                  </div>
                </div>
              </div>
              <div className="col-xl-6">
                <div className="panel h-100">
                  <div className="panel-head">
                    <h6 className="panel-title">
                      <span className="kicker" />
                      {selected} 逐日预测 IC
                    </h6>
                  </div>
                  <div className="panel-body">{icOption ? <EChart option={icOption} height={300} /> : null}</div>
                </div>
              </div>
              <div className="col-xl-6">
                <div className="panel h-100">
                  <div className="panel-head">
                    <h6 className="panel-title">
                      <span className="kicker" />
                      top-N 实现收益 vs 基准（{model.summary.base_horizon}d 前向）
                    </h6>
                  </div>
                  <div className="panel-body">{topOption ? <EChart option={topOption} height={300} /> : null}</div>
                </div>
              </div>
              <div className="col-xl-5">
                <div className="panel h-100">
                  <div className="panel-head">
                    <h6 className="panel-title">
                      <span className="kicker" />
                      IC 衰减（horizon）
                    </h6>
                  </div>
                  <div className="panel-body tight table-container" style={{ maxHeight: 240 }}>
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Horizon</th>
                          <th className="num">IC</th>
                          <th className="num">ICIR</th>
                          <th className="num">正率</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(model.ic_by_horizon).map(([h, v]) => (
                          <tr key={h}>
                            <td>
                              <code>{h}d</code>
                            </td>
                            <td className={`num ${v.ic_mean != null ? pctClass(v.ic_mean) : ''}`}>
                              {v.ic_mean != null ? formatNumber(v.ic_mean, 4) : '--'}
                            </td>
                            <td className="num">{v.ic_ir != null ? formatNumber(v.ic_ir, 2) : '--'}</td>
                            <td className="num">{v.ic_positive_ratio != null ? fmtPct(v.ic_positive_ratio) : '--'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
              <div className="col-xl-7">
                <div className="panel h-100">
                  <div className="panel-head">
                    <h6 className="panel-title">
                      <span className="kicker" />
                      多模型一致性（同日预测截面秩相关）
                    </h6>
                  </div>
                  <div className="panel-body">{consistencyOption ? <EChart option={consistencyOption} height={280} /> : <div className="text-faint">仅一个模型，无一致性曲线</div>}</div>
                </div>
              </div>
            </>
          )}
          {model?.error && <div className="col-12 text-faint">{model.error}</div>}
        </div>
      )}
    </div>
  )
}

// ================= 组合归因 =================

function AttributionTab({ palette }: { palette: Palette }) {
  const [portfolios, setPortfolios] = useState<Array<{ portfolio_id: string; name?: string }>>([])
  const [portfolioId, setPortfolioId] = useState('')
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<AttributionResult | null>(null)

  useEffect(() => {
    fetchPortfolios()
      .then((r) => {
        const list = (r.portfolios ?? []) as Array<{ portfolio_id: string; name?: string }>
        setPortfolios(list)
        if (list.length > 0) setPortfolioId(list[0].portfolio_id)
      })
      .catch(() => undefined)
  }, [])

  const submit = async () => {
    if (!portfolioId) {
      setError('请选择组合')
      return
    }
    setStatus('running')
    setError(null)
    try {
      // 默认用体检 accepted 白名单（后端在无指定时自动回退到高覆盖因子）
      const accepted = await fetchScreeningList({ status: 'accepted' })
        .then((r) => (r.records ?? []).map((x) => x.factor_id))
        .catch(() => [] as string[])
      const r = await runPortfolioAttribution(portfolioId, {
        factor_ids: accepted.length >= 2 ? accepted : undefined,
      })
      setResult(r)
      setStatus('done')
    } catch (e) {
      setError(e instanceof Error ? e.message : '组合归因失败')
      setStatus('failed')
    }
  }

  const contribOption = useMemo(() => {
    if (!result) return null
    const entries = Object.entries(result.attribution).sort(
      (a, b) => Math.abs(b[1].contribution_annualized) - Math.abs(a[1].contribution_annualized),
    )
    return {
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => fmtPct(v) },
      grid: { left: 120, right: 24, top: 12, bottom: 28 },
      xAxis: { type: 'value', axisLabel: { formatter: (v: number) => `${(v * 100).toFixed(0)}%` } },
      yAxis: { type: 'category', data: entries.map((e) => e[0]).reverse() },
      series: [
        {
          type: 'bar',
          data: entries.map(([, v]) => ({
            value: v.contribution_annualized,
            itemStyle: { color: v.contribution_annualized >= 0 ? palette.teal : '#e8684a' },
          })),
        },
      ],
    }
  }, [result, palette])

  return (
    <div>
      <div className="panel mb-3">
        <div className="panel-body">
          <div className="row g-2 align-items-end">
            <div className="col-md-4">
              <label className="form-label">组合</label>
              <select className="form-select" value={portfolioId} onChange={(e) => setPortfolioId(e.target.value)}>
                {portfolios.length === 0 && <option value="">（无组合）</option>}
                {portfolios.map((p) => (
                  <option key={p.portfolio_id} value={p.portfolio_id}>
                    {p.portfolio_id}
                    {p.name ? ` · ${p.name}` : ''}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-md-3">
              <button type="button" className="btn btn-primary w-100" disabled={status === 'running'} onClick={submit}>
                {status === 'running' ? '归因中…' : '运行风格归因'}
              </button>
            </div>
            <div className="col-12 text-faint" style={{ fontSize: 12 }}>
              组合日收益对因子收益率（逐日截面 Fama-MacBeth 回归）做多元回归：风格画像 + 各因子贡献的年化收益；因子集默认取体检 accepted 白名单。
            </div>
          </div>
        </div>
      </div>

      {error && <ErrorState message={error} />}
      {status === 'running' && <Loading text="组合归因运行中..." />}

      {result && status === 'done' && (
        <div className="row g-3">
          <div className="col-12">
            <div className="stat-grid">
              <div className="stat">
                <div className="stat-value">{fmtPct(result.portfolio_summary.annualized_return)}</div>
                <div className="stat-label">组合年化收益</div>
              </div>
              <div className="stat">
                <div className="stat-value">{fmtPct(result.alpha_annualized)}</div>
                <div className="stat-label">年化 Alpha（残差）</div>
              </div>
              <div className="stat">
                <div className="stat-value">
                  {result.r_squared != null ? formatNumber(result.r_squared, 3) : '--'}
                </div>
                <div className="stat-label">R²（因子解释度）</div>
              </div>
              <div className="stat">
                <div className="stat-value">{result.n_positions}</div>
                <div className="stat-label">持仓数</div>
              </div>
            </div>
          </div>
          <div className="col-xl-7">
            <div className="panel h-100">
              <div className="panel-head">
                <h6 className="panel-title">
                  <span className="kicker" />
                  风格贡献（年化）
                </h6>
              </div>
              <div className="panel-body">{contribOption ? <EChart option={contribOption} height={320} /> : null}</div>
            </div>
          </div>
          <div className="col-xl-5">
            <div className="panel h-100">
              <div className="panel-head">
                <h6 className="panel-title">
                  <span className="kicker" />
                  因子暴露明细
                </h6>
              </div>
              <div className="panel-body tight table-container" style={{ maxHeight: 340 }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>因子</th>
                      <th className="num">beta</th>
                      <th className="num">t 值</th>
                      <th className="num">年化贡献</th>
                      <th className="num">当前暴露(z)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(result.attribution)
                      .sort((a, b) => Math.abs(b[1].contribution_annualized) - Math.abs(a[1].contribution_annualized))
                      .map(([f, v]) => (
                        <tr key={f}>
                          <td>
                            <code>{f}</code>
                          </td>
                          <td className="num">{formatNumber(v.beta, 2)}</td>
                          <td className="num">{v.t_stat != null ? formatNumber(v.t_stat, 1) : '--'}</td>
                          <td className={`num ${pctClass(v.contribution_annualized)}`}>
                            {fmtPct(v.contribution_annualized)}
                          </td>
                          <td className="num">
                            {result.current_exposure[f] != null ? formatNumber(result.current_exposure[f], 2) : '--'}
                          </td>
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

// ================= 模型对比 =================

function ModelsTab() {
  const [models, setModels] = useState<Array<{ model_id: string; model_name?: string }>>([])
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [snapshots, setSnapshots] = useState<ModelSnapshot[]>([])
  const [compareRows, setCompareRows] = useState<ModelCompareRow[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    fetchModels()
      .then((r) => {
        const list = (r.models ?? []) as Array<{ model_id: string; model_name?: string }>
        setModels(list)
        if (list.length > 0) {
          setSelectedIds([list[0].model_id])
          loadSnapshots(list[0].model_id)
        }
      })
      .catch(() => undefined)
  }, [])

  const loadSnapshots = (modelId: string) => {
    fetchModelSnapshots(modelId)
      .then((r) => setSnapshots(r.records ?? []))
      .catch(() => setSnapshots([]))
  }

  const toggle = (mid: string) => {
    setSelectedIds((prev) => (prev.includes(mid) ? prev.filter((x) => x !== mid) : [...prev, mid]))
  }

  const runCompare = async () => {
    if (selectedIds.length === 0) return
    setBusy(true)
    setError(null)
    try {
      const r = await compareModels(selectedIds)
      setCompareRows(r.models ?? [])
    } catch (e) {
      setError(e instanceof Error ? e.message : '模型对比失败')
    } finally {
      setBusy(false)
    }
  }

  const metricKeys = useMemo(() => {
    const keys = new Set<string>()
    for (const row of compareRows) {
      if (row.metrics) Object.keys(row.metrics).forEach((k) => keys.add(k))
    }
    return [...keys]
  }, [compareRows])

  const metricVal = (v: unknown) => {
    const n = Number(v)
    return Number.isFinite(n) ? formatNumber(n, 4) : String(v ?? '--')
  }

  return (
    <div>
      <div className="panel mb-3">
        <div className="panel-body">
          <div className="d-flex gap-3 flex-wrap align-items-center">
            {models.map((m) => (
              <label key={m.model_id} className="d-flex gap-1 align-items-center" style={{ fontSize: 13 }}>
                <input
                  type="checkbox"
                  checked={selectedIds.includes(m.model_id)}
                  onChange={() => toggle(m.model_id)}
                />
                <code>{m.model_id}</code>
                {m.model_name ? <span className="text-faint">{m.model_name}</span> : null}
              </label>
            ))}
            <button type="button" className="btn btn-primary btn-sm" disabled={busy || selectedIds.length === 0} onClick={runCompare}>
              {busy ? '对比中…' : '对比最新训练快照'}
            </button>
          </div>
          <div className="text-faint mt-2" style={{ fontSize: 12 }}>
            每次训练成功后自动保存快照（超参 + 因子集 + 数据窗口 + 指标）；勾选模型后按各自最新快照并排对比。
            下方为当前选中首个模型的快照轨迹（点击其它模型名称切换查看）。
          </div>
        </div>
      </div>

      {error && <ErrorState message={error} />}

      {compareRows.length > 0 && (
        <div className="panel mb-3">
          <div className="panel-head">
            <h6 className="panel-title">
              <span className="kicker" />
              A/B 对比（最新快照）
            </h6>
          </div>
          <div className="panel-body tight table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>模型</th>
                  <th>类型</th>
                  <th>训练时间</th>
                  <th>训练窗口</th>
                  <th className="num">特征数</th>
                  {metricKeys.map((k) => (
                    <th key={k} className="num">
                      {k}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {compareRows.map((row) => (
                  <tr key={row.model_id}>
                    <td>
                      <code>{row.model_id}</code>
                      {row.error ? <span className="text-faint">（{row.error}）</span> : null}
                    </td>
                    <td>{row.model_type ?? '--'}</td>
                    <td className="text-faint">{row.trained_at ?? '--'}</td>
                    <td className="text-faint" style={{ fontSize: 12 }}>
                      {row.train_window?.[0] ?? '?'} ~ {row.train_window?.[1] ?? '?'}
                    </td>
                    <td className="num">{row.n_factors}</td>
                    {metricKeys.map((k) => (
                      <td key={k} className="num">
                        {row.metrics ? metricVal(row.metrics[k]) : '--'}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {snapshots.length > 0 && (
        <div className="panel">
          <div className="panel-head">
            <h6 className="panel-title">
              <span className="kicker" />
              {snapshots[0].model_id} 训练快照轨迹（{snapshots.length} 次）
            </h6>
          </div>
          <div className="panel-body tight table-container" style={{ maxHeight: 420 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>训练时间</th>
                  <th>数据窗口</th>
                  <th className="num">特征数</th>
                  <th>因子集</th>
                  <th>超参</th>
                  <th>指标</th>
                </tr>
              </thead>
              <tbody>
                {snapshots.map((s) => (
                  <tr key={s.snapshot_id}>
                    <td>
                      <code>{s.snapshot_id}</code>
                    </td>
                    <td className="text-faint">{s.created_at}</td>
                    <td className="text-faint" style={{ fontSize: 12 }}>
                      {s.train_start_date ?? '?'} ~ {s.train_end_date ?? '?'}
                    </td>
                    <td className="num">{(s.factor_list ?? []).length}</td>
                    <td className="text-faint" style={{ fontSize: 11, maxWidth: 220 }}>
                      {(s.factor_list ?? []).join(', ')}
                    </td>
                    <td className="text-faint" style={{ fontSize: 11, maxWidth: 200 }}>
                      {JSON.stringify(s.model_params ?? {})}
                    </td>
                    <td className="text-faint" style={{ fontSize: 11, maxWidth: 200 }}>
                      {JSON.stringify(s.metrics ?? {})}
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

// ================= 筹码信号 =================

interface ChipSignalResultView {
  stats: {
    scan_date: string
    universe: number
    conc_threshold: number
    counts: { squeeze: number; resonance: number; divergence: number }
  }
  definitions: Record<string, string>
  squeeze: ChipSignalRow[]
  resonance: ChipSignalRow[]
  divergence: ChipSignalRow[]
}

function ChipTab() {
  const [result, setResult] = useState<ChipSignalResultView | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const load = (refresh = false) => {
    if (refresh) setRefreshing(true)
    fetchChipSignals(refresh)
      .then(setResult)
      .catch((e) => setError(e instanceof Error ? e.message : '筹码信号加载失败'))
      .finally(() => {
        setLoading(false)
        setRefreshing(false)
      })
  }

  useEffect(() => {
    load()
  }, [])

  if (loading) return <Loading text="筹码信号扫描中..." />
  if (error) return <ErrorState message={error} />
  if (!result) return null

  const { stats } = result

  const mkPanel = (
    key: 'squeeze' | 'resonance' | 'divergence',
    title: string,
    desc: string,
    tone: string,
  ) => (
    <div className="panel">
      <div className="panel-head d-flex justify-content-between align-items-center flex-wrap gap-2">
        <h6 className="panel-title">
          <span className="kicker" style={{ background: tone }} />
          {title}
          <span className="chip ms-2">{result[key].length}</span>
        </h6>
        <span className="text-faint" style={{ fontSize: 11.5, maxWidth: 640 }}>{desc}</span>
      </div>
      <div className="panel-body tight table-container" style={{ maxHeight: 380 }}>
        {result[key].length === 0 ? (
          <div className="text-faint">今日无该类信号</div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>股票</th>
                <th className="num">现价</th>
                <th className="num">5日涨幅</th>
                <th className="num">获利盘</th>
                <th className="num">获利盘5日变化</th>
                <th className="num">筹码集中度</th>
                <th className="num">成本乖离</th>
                <th className="num">主力5日净额(万)</th>
                <th className="num">量能比</th>
              </tr>
            </thead>
            <tbody>
              {result[key].map((row: ChipSignalRow) => (
                <tr key={row.ts_code}>
                  <td>
                    <code>{row.ts_code}</code>
                    <span className="ms-1">{row.name ?? ''}</span>
                  </td>
                  <td className="num">{formatNumber(row.close, 2)}</td>
                  <td className={`num ${pctClass((row.pct_5d ?? 0) / 100)}`}>
                    {row.pct_5d != null ? `${row.pct_5d}%` : '--'}
                  </td>
                  <td className="num">{row.winner_rate}%</td>
                  <td className="num">{row.winner_chg_5d != null ? `+${row.winner_chg_5d}` : '--'}</td>
                  <td className="num">{formatNumber(row.conc, 4)}</td>
                  <td className="num">{row.cost_dev != null ? `${row.cost_dev}%` : '--'}</td>
                  <td className={`num ${row.main_net_5d != null && row.main_net_5d < 0 ? 'text-danger' : 'text-success'}`}>
                    {row.main_net_5d != null ? formatNumber(row.main_net_5d, 0) : '--'}
                  </td>
                  <td className="num">{row.vol_ratio != null ? formatNumber(row.vol_ratio, 2) : '--'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )

  return (
    <div>
      <div className="stat-grid mb-3">
        <div className="stat">
          <div className="stat-value">{stats.scan_date}</div>
          <div className="stat-label">扫描截面</div>
        </div>
        <div className="stat">
          <div className="stat-value">{stats.universe}</div>
          <div className="stat-label">覆盖股票数</div>
        </div>
        <div className="stat">
          <div className="stat-value">{stats.counts.squeeze}</div>
          <div className="stat-label">挤压蓄势</div>
        </div>
        <div className="stat">
          <div className="stat-value">{stats.counts.resonance}</div>
          <div className="stat-label">多头共振</div>
        </div>
        <div className="stat">
          <div className="stat-value">{stats.counts.divergence}</div>
          <div className="stat-label">背离预警</div>
        </div>
        <div className="stat d-flex align-items-center">
          <button type="button" className="btn btn-outline-secondary btn-sm" disabled={refreshing} onClick={() => load(true)}>
            {refreshing ? '刷新中…' : '重新扫描'}
          </button>
        </div>
      </div>
      <div className="d-flex flex-column gap-3">
        {mkPanel('squeeze', '筹码挤压蓄势', result.definitions.squeeze ?? '', 'var(--accent, #4f8ef7)')}
        {mkPanel('resonance', '资金×筹码多头共振', result.definitions.resonance ?? '', '#22c55e')}
        {mkPanel('divergence', '量价资金背离预警', result.definitions.divergence ?? '', '#e8684a')}
      </div>
      <ChipBacktestPanel />
    </div>
  )
}

const BT_COLORS: Record<string, string> = {
  squeeze: '#4f8ef7',
  resonance: '#22c55e',
  divergence: '#e8684a',
}

const HORIZONS = [5, 10, 20] as const

function ChipBacktestPanel() {
  const { palette } = useTheme()
  const [data, setData] = useState<ChipSignalBacktestResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [horizon, setHorizon] = useState<(typeof HORIZONS)[number]>(20)

  const load = (refresh = false) => {
    if (refresh) {
      setRefreshing(true)
      setLoading(true)
    }
    fetchChipSignalBacktest(12, refresh)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : '信号回测加载失败'))
      .finally(() => {
        setLoading(false)
        setRefreshing(false)
      })
  }

  useEffect(() => {
    load()
  }, [])

  const chartOption = useMemo(() => {
    if (!data) return null
    const key = `h${horizon}`
    const series: Record<string, unknown>[] = Object.keys(data.signals).map((name) => ({
      name: data.signals[name].label,
      type: 'line',
      showSymbol: false,
      connectNulls: false,
      data: data.nav_series[name]?.[key]?.nav ?? [],
      lineStyle: { width: 1.6 },
      itemStyle: { color: BT_COLORS[name] },
    }))
    const uni = Object.keys(data.signals)[0]
    if (uni) {
      series.push({
        name: '全市场等权',
        type: 'line',
        showSymbol: false,
        data: data.nav_series[uni]?.[key]?.uni_nav ?? [],
        lineStyle: { width: 1.2, type: 'dashed' },
        itemStyle: { color: palette.border },
      })
    }
    return {
      textStyle: { color: palette.text },
      tooltip: { trigger: 'axis' },
      legend: { top: 0, textStyle: { color: palette.text, fontSize: 11 } },
      grid: { left: 56, right: 16, top: 30, bottom: 28 },
      xAxis: { type: 'category', data: data.nav_series.squeeze?.[key]?.dates ?? [] },
      yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: palette.gridHorz } } },
      series,
    }
  }, [data, horizon, palette])

  if (loading) return <Loading text="信号历史回测计算中（约 15s，服务端缓存 1 小时）..." />
  if (error) return <ErrorState message={error} />
  if (!data) return null

  const fmtBp = (v: number | null) => (v == null ? '--' : `${(v / 100).toFixed(2)}%`)
  const tCell = (v: number | null) =>
    v == null ? (
      '--'
    ) : (
      <span className={v >= 2 ? 'text-success' : v <= -2 ? 'text-danger' : ''}>
        {v.toFixed(2)}
      </span>
    )

  return (
    <div className="panel mt-3">
      <div className="panel-head d-flex justify-content-between align-items-center flex-wrap gap-2">
        <h6 className="panel-title">
          <span className="kicker" style={{ background: '#a855f7' }} />
          信号有效性回测（近 12 个月）
        </h6>
        <div className="d-flex align-items-center gap-2">
          <span className="text-faint" style={{ fontSize: 11.5 }}>
            {data.meta.start} ~ {data.meta.end} · {data.meta.n_days} 个截面 ·
            T+1 开盘入场、T+1+H 开盘出场 · 超额基准为全市场等权
          </span>
          <div className="seg">
            {HORIZONS.map((h) => (
              <button
                key={h}
                type="button"
                className={`seg-item ${horizon === h ? 'active' : ''}`}
                onClick={() => setHorizon(h)}
              >
                {h}日
              </button>
            ))}
          </div>
          <button
            type="button"
            className="btn btn-outline-secondary btn-sm"
            disabled={refreshing}
            onClick={() => load(true)}
          >
            {refreshing ? '重算中…' : '重算'}
          </button>
        </div>
      </div>
      <div className="panel-body tight">
        <table className="data-table">
          <thead>
            <tr>
              <th>信号</th>
              <th className="num">触发数</th>
              {HORIZONS.map((h) => (
                <Fragment key={h}>
                  <th className="num" colSpan={3}>
                    {h}日持有
                  </th>
                </Fragment>
              ))}
            </tr>
            <tr>
              <th></th>
              <th className="num"></th>
              {HORIZONS.map((h) => (
                <Fragment key={h}>
                  <th className="num">平均收益</th>
                  <th className="num">超额</th>
                  <th className="num">t值</th>
                </Fragment>
              ))}
            </tr>
          </thead>
          <tbody>
            {Object.entries(data.signals).map(([name, sig]) => {
              const totalEvents = HORIZONS.reduce(
                (acc, h) => acc + (sig.horizons[`h${h}`]?.n_events ?? 0),
                0,
              )
              return (
                <tr key={name}>
                  <td>
                    <span className="kicker" style={{ background: BT_COLORS[name] }} />
                    {sig.label}
                  </td>
                  <td className="num">{totalEvents > 0 ? totalEvents : '--'}</td>
                  {HORIZONS.map((h) => {
                    const st = sig.horizons[`h${h}`]
                    return (
                      <Fragment key={h}>
                        <td className="num">{fmtBp(st?.mean_ret_bp ?? null)}</td>
                        <td className={`num ${(st?.excess_bp ?? 0) < 0 ? 'text-danger' : (st?.excess_bp ?? 0) > 0 ? 'text-success' : ''}`}>
                          {fmtBp(st?.excess_bp ?? null)}
                        </td>
                        <td className="num">{tCell(st?.excess_t ?? null)}</td>
                      </Fragment>
                    )
                  })}
                </tr>
              )
            })}
          </tbody>
        </table>
        {!data.meta.has_moneyflow && (
          <div className="text-faint mt-2">⚠️ 无资金流数据，共振/背离信号无法计算</div>
        )}
        {chartOption && <EChart option={chartOption} height={320} />}
      </div>
    </div>
  )
}
