import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  deleteSavedStrategy,
  fetchSavedStrategies,
  type SavedStrategy,
} from '../api/ai'
import { EmptyState } from '../components/StateViews'
import {
  ForkPanel,
  HistoryPanel,
  RerunPanel,
  ViewPanel,
} from '../components/ai/strategyPanels'

/**
 * 策略管理页（/ml-factor/strategies）：AI 工作台 save_strategy 产出一等公民视图。
 * 左列策略清单（搜索/按最近表现排序），右区选中策略详情——概览 / 版本历史 /
 * 调参重跑 / 派生编辑 四个 tab；面板组件与 AI 工作台侧栏共用。
 */

type Tab = 'view' | 'history' | 'rerun' | 'fork'

const TABS: { key: Tab; label: string }[] = [
  { key: 'view', label: '概览' },
  { key: 'history', label: '版本历史' },
  { key: 'rerun', label: '调参重跑' },
  { key: 'fork', label: '派生编辑' },
]

function StrategyListItem({
  s,
  active,
  onSelect,
}: {
  s: SavedStrategy
  active: boolean
  onSelect: () => void
}) {
  const eng = s.strategy_config?.engine_config
  const isDsl = eng?.selection_method === 'dsl_rule'
  return (
    <div
      className={`p-2 rounded side-link ${active ? 'active' : ''}`}
      style={{
        background: active ? undefined : 'var(--surface-2)',
        border: '1px solid var(--border)',
        cursor: 'pointer',
      }}
      onClick={onSelect}
    >
      <div className="d-flex align-items-center gap-2">
        <span style={{ flex: 1, fontWeight: 600, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {s.name}
        </span>
        <span className="badge text-bg-secondary" style={{ fontSize: 10 }}>v{s.version}</span>
        <span className="badge text-bg-info" style={{ fontSize: 10 }}>{isDsl ? 'DSL' : '因子'}</span>
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-faint)' }}>
        {s.description ? `${s.description.slice(0, 30)}${s.description.length > 30 ? '…' : ''} · ` : ''}
        top {eng?.top_n ?? '-'}
        {s.run_count != null && ` · ${s.run_count} 跑`}
      </div>
    </div>
  )
}

export default function StrategiesPage() {
  const navigate = useNavigate()
  const [strategies, setStrategies] = useState<SavedStrategy[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('view')
  const [query, setQuery] = useState('')

  const refresh = () => {
    fetchSavedStrategies().then((list) => {
      setStrategies(list)
      if (list.length > 0 && !list.some((s) => s.name === selected)) {
        setSelected((prev) => prev ?? list[0].name)
      }
    })
  }
  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const filtered = useMemo(
    () => strategies.filter((s) => s.name.toLowerCase().includes(query.trim().toLowerCase())),
    [strategies, query],
  )
  const current = strategies.find((s) => s.name === selected) ?? null
  const isDsl = current?.strategy_config?.engine_config?.selection_method === 'dsl_rule'

  const removeStrategy = async (name: string) => {
    if (!window.confirm(`删除策略「${name}」的全部版本？`)) return
    try {
      await deleteSavedStrategy(name)
      setSelected((prev) => (prev === name ? null : prev))
      refresh()
    } catch (e) {
      window.alert(e instanceof Error ? e.message : '删除失败')
    }
  }

  return (
    <div className="row g-3">
      <div className="col-lg-4">
        <div className="panel">
          <div className="panel-head">
            <h6 className="panel-title">
              <span className="kicker" />
              策略清单
              <span className="chip">{strategies.length}</span>
            </h6>
          </div>
          <div className="panel-body d-flex flex-column gap-2">
            <input
              className="form-control form-control-sm"
              style={{ fontSize: 12 }}
              placeholder="搜索策略名…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            {filtered.map((s) => (
              <StrategyListItem
                key={`${s.name}-${s.version}`}
                s={s}
                active={s.name === selected}
                onSelect={() => {
                  setSelected(s.name)
                  setTab('view')
                }}
              />
            ))}
            {filtered.length === 0 && (
              <EmptyState icon="🎯" text={strategies.length === 0 ? '暂无策略：在 AI 工作台说「把这个策略保存为 xx」' : '无匹配策略'} />
            )}
            <div style={{ fontSize: 11, color: 'var(--text-faint)' }}>
              策略由 <Link to="/ai-workbench">AI 工作台</Link> 保存产出；本页做版本管理与调参迭代。
            </div>
          </div>
        </div>
      </div>

      <div className="col-lg-8">
        <div className="panel">
          {current ? (
            <>
              <div className="panel-head flex-wrap">
                <div className="d-flex align-items-center gap-2 me-auto">
                  <h6 className="panel-title mb-0">
                    <span className="kicker" />
                    {current.name}
                  </h6>
                  <span className="badge text-bg-secondary">v{current.version}</span>
                  <span className={`badge ${isDsl ? 'text-bg-info' : 'text-bg-primary'}`}>{isDsl ? 'DSL 规则' : '因子加权'}</span>
                </div>
                <button
                  type="button"
                  className="btn btn-outline-danger btn-sm"
                  style={{ fontSize: 11 }}
                  onClick={() => removeStrategy(current.name)}
                >
                  删除策略族
                </button>
              </div>
              <div className="panel-body">
                <div className="mb-3" style={{ fontSize: 12, color: 'var(--text-faint)' }}>
                  {current.description && <div>{current.description}</div>}
                  <div>
                    持仓 top {current.strategy_config?.engine_config?.top_n ?? '-'} · 基准{' '}
                    {current.strategy_config?.engine_config?.benchmark_index ?? '-'} ·{' '}
                    {current.strategy_config?.params?.rebalance_frequency ?? 'monthly'} 调仓
                    {current.strategy_config?.params?.start_date && (
                      <> · {current.strategy_config.params.start_date}~{current.strategy_config.params.end_date}</>
                    )}
                    {current.run_count != null && <> · 回测 {current.run_count} 次</>}
                  </div>
                </div>

                <ul className="nav nav-tabs mb-3" style={{ fontSize: 12.5 }}>
                  {TABS.map((t) => (
                    <li className="nav-item" key={t.key}>
                      <button
                        type="button"
                        className={`nav-link ${tab === t.key ? 'active' : ''}`}
                        style={{ cursor: 'pointer', fontSize: 12.5 }}
                        onClick={() => setTab(t.key)}
                      >
                        {t.label}
                      </button>
                    </li>
                  ))}
                </ul>

                {tab === 'view' && <ViewPanel strategy={current} isDsl={isDsl} />}
                {tab === 'history' && <HistoryPanel key={current.name} name={current.name} />}
                {tab === 'rerun' && (
                  <RerunPanel
                    key={current.name}
                    strategy={current}
                    onAskAi={(prompt) => {
                      /* 管理页无对话区：跳 AI 工作台并自动发起该提问 */
                      navigate('/ai-workbench', { state: { prompt } })
                    }}
                  />
                )}
                {tab === 'fork' && (
                  <ForkPanel key={`${current.name}-${current.version}`} strategy={current} isDsl={isDsl} onChanged={refresh} />
                )}
              </div>
            </>
          ) : (
            <div className="panel-body">
              <EmptyState icon="👈" text="从左侧选择一个策略查看详情" />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
