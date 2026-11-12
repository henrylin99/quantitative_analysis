import { useEffect, useRef, useState } from 'react'
import EChart from '../../charts/EChart'
import {
  compareStrategyRuns,
  fetchBacktestRunMetrics,
  fetchRunEquityCurve,
  fetchStrategyHistory,
  forkStrategyVersion,
  runStrategyByName,
  type EquityPoint,
  type RunCompareRow,
  type SavedStrategy,
  type StrategyHistory,
} from '../../api/ai'

/**
 * 策略面板组件（AI 工作台侧栏卡片与 /ml-factor/strategies 管理页共用）：
 * 查看等价 DSL / 配置 JSON、调参重跑（overrides + run 对比）、
 * 版本历史（演进 + 回测记录 + 净值叠加图）、派生新版本（编辑=升版，版本不可变）。
 */

export const fmt = (v: unknown, digits = 3): string =>
  typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : '-'

export const fmtPct = (v: unknown): string =>
  typeof v === 'number' && Number.isFinite(v) ? `${(v * 100).toFixed(1)}%` : '-'

/** 因子加权 → 等价 DSL（rank 加权合成，负权重=反向） */
export function equivalentDsl(s: SavedStrategy): string | null {
  const eng = s.strategy_config?.engine_config
  if (!eng || eng.selection_method === 'dsl_rule') return null
  const factors = eng.factor_list ?? []
  if (factors.length === 0) return null
  const weights = eng.weights ?? {}
  const terms = factors.map((f) => {
    const w = weights[f]
    if (w == null) return `rank(${f})`
    if (w < 0) return `-(${Math.abs(w)} * rank(${f}))`
    return w === 1 ? `rank(${f})` : `${w} * rank(${f})`
  })
  return terms.join(' + ')
}

export function DslView({ text }: { text: string }) {
  return (
    <div
      className="font-monospace"
      style={{
        fontSize: 10.5,
        wordBreak: 'break-all',
        background: 'var(--surface-3, rgba(0,0,0,0.15))',
        border: '1px solid var(--border)',
        borderRadius: 6,
        padding: '4px 8px',
        whiteSpace: 'pre-wrap',
      }}
    >
      {text}
    </div>
  )
}

export function CompareTable({ rows, warning }: { rows: RunCompareRow[]; warning?: string | null }) {
  return (
    <div style={{ fontSize: 10.5, overflowX: 'auto' }}>
      {warning && <div style={{ color: '#e0a800', marginBottom: 4 }}>⚠️ {warning}</div>}
      <table className="table table-sm mb-0" style={{ fontSize: 10.5 }}>
        <thead>
          <tr>
            <th>run</th><th>区间</th><th>总收益</th><th>年化</th><th>夏普</th>
            <th>最大回撤</th><th>胜率</th><th>交易数</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.run_id}>
              <td>#{r.run_id}</td>
              <td>{r.start_date}~{r.end_date}</td>
              <td>{fmtPct(r.total_return)}</td>
              <td>{fmtPct(r.annualized_return)}</td>
              <td>{fmt(r.sharpe_ratio, 2)}</td>
              <td>{fmtPct(r.max_drawdown)}</td>
              <td>{fmtPct(r.win_rate)}</td>
              <td>{r.total_trades ?? '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** 多 run 策略净值叠加图（对比时自动渲染） */
export function EquityOverlay({ runs }: { runs: { run_id: number; label?: string }[] }) {
  const [series, setSeries] = useState<{ runId: number; points: EquityPoint[] }[]>([])
  useEffect(() => {
    let alive = true
    Promise.all(
      runs.map(async (r) => ({ runId: r.run_id, points: await fetchRunEquityCurve(r.run_id) })),
    ).then((s) => {
      if (alive) setSeries(s)
    })
    return () => {
      alive = false
    }
  }, [runs.map((r) => r.run_id).join(',')]) // eslint-disable-line react-hooks/exhaustive-deps

  const withData = series.filter((s) => s.points.length > 0)
  if (withData.length === 0) return null
  // 日期轴取最长序列；各序列按日期对齐（缺日补 null）
  const dates = [...new Set(withData.flatMap((s) => s.points.map((p) => p.date)))].sort()
  const option = {
    grid: { left: 48, right: 16, top: 32, bottom: 28 },
    legend: { top: 0, type: 'scroll' as const },
    tooltip: { trigger: 'axis' as const },
    xAxis: { type: 'category' as const, data: dates },
    yAxis: { type: 'value' as const, scale: true },
    series: withData.map((s) => {
      const byDate = new Map(s.points.map((p) => [p.date, p.portfolio ?? null]))
      return {
        name: `run#${s.runId}`,
        type: 'line' as const,
        showSymbol: false,
        connectNulls: true,
        lineWidth: 1.5,
        data: dates.map((d) => byDate.get(d) ?? null),
      }
    }),
  }
  return (
    <div>
      <div style={{ fontSize: 11, color: 'var(--text-faint)', marginBottom: 4 }}>策略净值叠加（均从 1 起步）：</div>
      <EChart option={option} height={260} />
    </div>
  )
}

export const inputStyle: React.CSSProperties = {
  fontSize: 11,
  padding: '2px 6px',
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  borderRadius: 4,
  color: 'inherit',
  width: '100%',
}

export const actionBtn = 'btn btn-outline-primary btn-sm'
export const actionBtnStyle: React.CSSProperties = { fontSize: 11, padding: '1px 8px' }

// ---------- 查看：等价 DSL + 配置 JSON ----------

export function ViewPanel({ strategy, isDsl }: { strategy: SavedStrategy; isDsl: boolean }) {
  const eng = strategy.strategy_config?.engine_config
  const equiv = equivalentDsl(strategy)
  const weights = eng?.weights ?? {}
  return (
    <div className="mt-2 d-flex flex-column gap-1">
      {isDsl ? (
        <>
          <div style={{ fontSize: 11, color: 'var(--text-faint)' }}>DSL 规则：</div>
          {eng?.dsl?.filter && <DslView text={`filter: ${eng.dsl.filter}`} />}
          <DslView text={`order_by: ${eng?.dsl?.order_by ?? ''}`} />
        </>
      ) : (
        <>
          <div style={{ fontSize: 11, color: 'var(--text-faint)' }}>
            因子与权重（负值=反向）：
            {(eng?.factor_list ?? []).map((f) => ` ${f}${weights[f] != null ? `(${weights[f]})` : ''}`).join('、') || '-'}
          </div>
          {equiv && (
            <>
              <div style={{ fontSize: 11, color: 'var(--text-faint)' }}>等价 DSL 表示：</div>
              <DslView text={`order_by: ${equiv}`} />
            </>
          )}
        </>
      )}
      <details style={{ fontSize: 10.5 }}>
        <summary style={{ color: 'var(--text-faint)', cursor: 'pointer' }}>配置 JSON（原文）</summary>
        <DslView text={JSON.stringify(strategy.strategy_config, null, 2)} />
      </details>
    </div>
  )
}

// ---------- 调参重跑：overrides → 轮询 → 自动对比 ----------

export function RerunPanel({
  strategy,
  onAskAi,
}: {
  strategy: SavedStrategy
  onAskAi: (prompt: string) => void
}) {
  const eng = strategy.strategy_config?.engine_config
  const params = strategy.strategy_config?.params ?? {}
  const isDsl = eng?.selection_method === 'dsl_rule'
  const [topN, setTopN] = useState(String(eng?.top_n ?? 50))
  const [startDate, setStartDate] = useState(params.start_date ?? '')
  const [endDate, setEndDate] = useState(params.end_date ?? '')
  const [weights, setWeights] = useState<Record<string, string>>(() => {
    const w = eng?.weights ?? {}
    const out: Record<string, string> = {}
    for (const f of eng?.factor_list ?? []) out[f] = w[f] != null ? String(w[f]) : '1'
    return out
  })
  const [runId, setRunId] = useState<number | null>(null)
  const [status, setStatus] = useState('')
  const [metrics, setMetrics] = useState<Record<string, number> | null>(null)
  const [compare, setCompare] = useState<{ rows: RunCompareRow[]; range_warning?: string | null } | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const timerRef = useRef<number | null>(null)
  useEffect(() => () => { if (timerRef.current) window.clearInterval(timerRef.current) }, [])

  const submit = async () => {
    setErr(null)
    setCompare(null)
    setMetrics(null)
    setBusy(true)
    const overrides: Record<string, unknown> = { top_n: Number(topN) || undefined }
    if (startDate) overrides.start_date = startDate.replace(/-/g, '')
    if (endDate) overrides.end_date = endDate.replace(/-/g, '')
    if (!isDsl) {
      const w: Record<string, number> = {}
      for (const [f, v] of Object.entries(weights)) {
        const n = Number(v)
        if (Number.isFinite(n)) w[f] = n
      }
      if (Object.keys(w).length) overrides.weights = w
    }
    try {
      const run = await runStrategyByName(strategy.name, overrides)
      setRunId(run.run_id)
      setStatus('queued')
      let tries = 0
      timerRef.current = window.setInterval(async () => {
        tries += 1
        const { fetchBacktestRunStatus } = await import('../../api/ai')
        const st = await fetchBacktestRunStatus(run.run_id)
        if (!st) return
        setStatus(st.status ?? '')
        if (st.status === 'succeeded' || st.status === 'failed' || tries > 100) {
          if (timerRef.current) window.clearInterval(timerRef.current)
          setBusy(false)
          if (st.status === 'succeeded') {
            setMetrics(await fetchBacktestRunMetrics(run.run_id))
            // 自动与最近一次成功 run 对比
            const h = await fetchStrategyHistory(strategy.name)
            const done = (h?.runs ?? []).filter((r) => r.status === 'succeeded' && r.run_id !== run.run_id)
            if (done.length > 0) {
              const cmp = await compareStrategyRuns([done[0].run_id, run.run_id])
              if (cmp) setCompare({ rows: cmp.runs, range_warning: cmp.range_warning })
            }
          } else if (st.error) {
            setErr(st.error)
          }
        }
      }, 3000)
    } catch (e) {
      setBusy(false)
      setErr(e instanceof Error ? e.message : '提交失败')
    }
  }

  return (
    <div className="mt-2 p-2 rounded d-flex flex-column gap-2" style={{ background: 'var(--surface-2)', border: '1px dashed var(--border)' }}>
      <div className="d-flex gap-2 flex-wrap" style={{ fontSize: 11 }}>
        <label>top N <input style={{ ...inputStyle, width: 70 }} value={topN} onChange={(e) => setTopN(e.target.value)} /></label>
        <label>开始 <input style={{ ...inputStyle, width: 95 }} placeholder="YYYYMMDD" value={startDate} onChange={(e) => setStartDate(e.target.value)} /></label>
        <label>结束 <input style={{ ...inputStyle, width: 95 }} placeholder="YYYYMMDD" value={endDate} onChange={(e) => setEndDate(e.target.value)} /></label>
      </div>
      {!isDsl && (
        <div className="d-flex gap-2 flex-wrap" style={{ fontSize: 11 }}>
          {(eng?.factor_list ?? []).map((f) => (
            <label key={f}>{f}{' '}
              <input style={{ ...inputStyle, width: 60 }} value={weights[f] ?? '1'}
                onChange={(e) => setWeights({ ...weights, [f]: e.target.value })} />
            </label>
          ))}
          <span style={{ color: 'var(--text-faint)' }}>（负权重=反向）</span>
        </div>
      )}
      {isDsl && (
        <div style={{ fontSize: 10.5, color: 'var(--text-faint)' }}>
          DSL 规则不变（改规则请用「派生新版本」）；此处仅调整 top N 与回测区间
        </div>
      )}
      <div className="d-flex gap-2 align-items-center">
        <button type="button" className="btn btn-primary btn-sm" style={{ fontSize: 11 }} disabled={busy} onClick={submit}>
          {busy ? '运行中…' : '提交重跑'}
        </button>
        {runId != null && <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>run #{runId} · {status}</span>}
      </div>
      {err && <div style={{ fontSize: 11, color: '#e07676' }}>{err}</div>}
      {metrics && (
        <div style={{ fontSize: 11 }}>
          总收益 {fmtPct(metrics.total_return)} · 年化 {fmtPct(metrics.annualized_return)} · 夏普{' '}
          {fmt(metrics.sharpe_ratio, 2)} · 最大回撤 {fmtPct(metrics.max_drawdown)}
        </div>
      )}
      {compare && <CompareTable rows={compare.rows} warning={compare.range_warning} />}
      {runId != null && !busy && (
        <button type="button" className={actionBtn} style={actionBtnStyle}
          onClick={() => onAskAi(`详细分析回测 run #${runId}（策略「${strategy.name}」调参重跑）的持仓与收益归因`)}>
          让 AI 深入分析此结果
        </button>
      )}
    </div>
  )
}

// ---------- 版本历史：版本轨迹 + 回测记录 + 对比 ----------

export function HistoryPanel({ name }: { name: string }) {
  const [history, setHistory] = useState<StrategyHistory | null>(null)
  const [compare, setCompare] = useState<{ rows: RunCompareRow[]; range_warning?: string | null } | null>(null)
  const [sel, setSel] = useState<number[]>([])
  useEffect(() => {
    fetchStrategyHistory(name).then(setHistory)
  }, [name])

  const runs = history?.runs ?? []
  const toggleSel = (id: number) =>
    setSel((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id].slice(-6)))

  const doCompare = async () => {
    const c = await compareStrategyRuns(sel)
    if (c) setCompare({ rows: c.runs, range_warning: c.range_warning })
  }

  return (
    <div className="mt-2 d-flex flex-column gap-2" style={{ fontSize: 10.5 }}>
      <div>
        <div style={{ color: 'var(--text-faint)' }}>版本轨迹（{(history?.versions ?? []).length} 个）：</div>
        {(history?.versions ?? []).map((v) => (
          <div key={v.id} style={{ fontSize: 10.5 }}>
            v{v.version}{v.is_latest ? '（最新）' : ''} · {v.created_at?.slice(0, 16).replace('T', ' ')}
            {v.description ? ` · ${v.description}` : ''}
            {v.strategy_config?.meta?.derived_from ? ` · 派生自 v${v.strategy_config.meta.derived_from.version}` : ''}
          </div>
        ))}
      </div>
      <div>
        <div style={{ color: 'var(--text-faint)' }}>回测记录（勾选 2~6 个对比）：</div>
        <table className="table table-sm mb-1" style={{ fontSize: 10.5 }}>
          <thead>
            <tr>
              <th />
              <th>run</th><th>v</th><th>区间</th><th>状态</th><th>总收益</th><th>夏普</th><th>回撤</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.run_id}>
                <td>
                  <input type="checkbox" checked={sel.includes(r.run_id)} onChange={() => toggleSel(r.run_id)} />
                </td>
                <td>#{r.run_id}</td>
                <td>{r.strategy_version != null ? `v${r.strategy_version}` : '-'}</td>
                <td>{r.start_date}~{r.end_date}</td>
                <td>{r.status}</td>
                <td>{fmtPct(r.total_return)}</td>
                <td>{fmt(r.sharpe_ratio, 2)}</td>
                <td>{fmtPct(r.max_drawdown)}</td>
              </tr>
            ))}
            {runs.length === 0 && (
              <tr><td colSpan={8} style={{ color: 'var(--text-faint)' }}>暂无回测记录</td></tr>
            )}
          </tbody>
        </table>
        <button
          type="button"
          className={actionBtn}
          style={actionBtnStyle}
          disabled={sel.length < 2}
          onClick={doCompare}
        >
          对比选中（{sel.length}）
        </button>
      </div>
      {compare && <CompareTable rows={compare.rows} warning={compare.range_warning} />}
      {compare && <EquityOverlay runs={compare.rows.map((r) => ({ run_id: r.run_id }))} />}
    </div>
  )
}

// ---------- 派生新版本：预填表单 → fork 保存 v+1 ----------

export function ForkPanel({
  strategy,
  isDsl,
  onChanged,
}: {
  strategy: SavedStrategy
  isDsl: boolean
  onChanged: () => void
}) {
  const eng = strategy.strategy_config?.engine_config
  const params = strategy.strategy_config?.params ?? {}
  const [description, setDescription] = useState('')
  const [topN, setTopN] = useState(String(eng?.top_n ?? 50))
  const [startDate, setStartDate] = useState(params.start_date ?? '')
  const [endDate, setEndDate] = useState(params.end_date ?? '')
  const [weights, setWeights] = useState<Record<string, string>>(() => {
    const w = eng?.weights ?? {}
    const out: Record<string, string> = {}
    for (const f of eng?.factor_list ?? []) out[f] = w[f] != null ? String(w[f]) : '1'
    return out
  })
  const [dslFilter, setDslFilter] = useState(eng?.dsl?.filter ?? '')
  const [dslOrderBy, setDslOrderBy] = useState(eng?.dsl?.order_by ?? '')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)

  const submit = async () => {
    setBusy(true)
    setErr(null)
    setMsg(null)
    const edits: Record<string, unknown> = { top_n: Number(topN) || undefined }
    if (startDate) edits.start_date = startDate.replace(/-/g, '')
    if (endDate) edits.end_date = endDate.replace(/-/g, '')
    if (isDsl) {
      edits.dsl_filter = dslFilter
      edits.dsl_order_by = dslOrderBy
    } else {
      const w: Record<string, number> = {}
      for (const [f, v] of Object.entries(weights)) {
        const n = Number(v)
        if (Number.isFinite(n)) w[f] = n
      }
      edits.weights = w
    }
    try {
      const r = await forkStrategyVersion(strategy.name, strategy.version, edits, description)
      if (r.success && r.strategy) {
        setMsg(`已保存为新版本 v${r.strategy.version}（v${strategy.version} 保留不变）`)
        onChanged()
      } else {
        setErr('保存失败')
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : '保存失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mt-2 p-2 rounded d-flex flex-column gap-2" style={{ background: 'var(--surface-2)', border: '1px dashed var(--border)' }}>
      <div style={{ fontSize: 10.5, color: 'var(--text-faint)' }}>
        以 v{strategy.version} 为底稿修改，保存为 v{strategy.version + 1}（版本不可变，历史保留）
      </div>
      <div className="d-flex gap-2 flex-wrap" style={{ fontSize: 11 }}>
        <label>版本说明 <input style={{ ...inputStyle, width: 160 }} placeholder="这次改了什么" value={description} onChange={(e) => setDescription(e.target.value)} /></label>
        <label>top N <input style={{ ...inputStyle, width: 70 }} value={topN} onChange={(e) => setTopN(e.target.value)} /></label>
        <label>开始 <input style={{ ...inputStyle, width: 95 }} placeholder="YYYYMMDD" value={startDate} onChange={(e) => setStartDate(e.target.value)} /></label>
        <label>结束 <input style={{ ...inputStyle, width: 95 }} placeholder="YYYYMMDD" value={endDate} onChange={(e) => setEndDate(e.target.value)} /></label>
      </div>
      {isDsl ? (
        <div className="d-flex flex-column gap-1" style={{ fontSize: 11 }}>
          <label>filter（布尔，可空）
            <textarea style={{ ...inputStyle, fontFamily: 'monospace' }} rows={2} value={dslFilter} onChange={(e) => setDslFilter(e.target.value)} />
          </label>
          <label>order_by（数值，必填）
            <textarea style={{ ...inputStyle, fontFamily: 'monospace' }} rows={2} value={dslOrderBy} onChange={(e) => setDslOrderBy(e.target.value)} />
          </label>
        </div>
      ) : (
        <div className="d-flex gap-2 flex-wrap" style={{ fontSize: 11 }}>
          {(eng?.factor_list ?? []).map((f) => (
            <label key={f}>{f}{' '}
              <input style={{ ...inputStyle, width: 60 }} value={weights[f] ?? '1'}
                onChange={(e) => setWeights({ ...weights, [f]: e.target.value })} />
            </label>
          ))}
          <span style={{ color: 'var(--text-faint)' }}>（负权重=反向）</span>
        </div>
      )}
      <div className="d-flex gap-2 align-items-center">
        <button type="button" className="btn btn-primary btn-sm" style={{ fontSize: 11 }} disabled={busy} onClick={submit}>
          {busy ? '保存中…' : `保存为 v${strategy.version + 1}`}
        </button>
        {msg && <span style={{ fontSize: 11, color: '#5bbf7a' }}>{msg}</span>}
        {err && <span style={{ fontSize: 11, color: '#e07676' }}>{err}</span>}
      </div>
    </div>
  )
}
