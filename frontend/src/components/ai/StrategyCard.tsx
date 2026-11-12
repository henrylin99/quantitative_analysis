import { useState } from 'react'
import type { SavedStrategy } from '../../api/ai'
import { ViewPanel, RerunPanel, ForkPanel, HistoryPanel } from './strategyPanels'

/**
 * 已存策略卡片（AI 工作台侧栏轻量入口）。
 * 完整管理界面见 /ml-factor/strategies 策略管理页；面板组件两边共用。
 */

type PanelMode = 'view' | 'rerun' | 'fork' | 'history'

export default function StrategyCard({
  strategy,
  onAskAi,
  onChanged,
  onDelete,
}: {
  strategy: SavedStrategy
  onAskAi: (prompt: string) => void
  onChanged: () => void
  onDelete: (name: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState<PanelMode>('view')
  const eng = strategy.strategy_config?.engine_config
  const isDsl = eng?.selection_method === 'dsl_rule'

  const setPanel = (m: PanelMode) => {
    setMode(m)
    setOpen(true)
  }

  return (
    <details
      className="p-2 rounded"
      style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
    >
      <summary style={{ fontSize: 12.5, cursor: 'pointer' }} className="d-flex align-items-center gap-1">
        <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {strategy.name}
        </span>
        <span className="badge text-bg-secondary" style={{ fontSize: 10 }}>v{strategy.version}</span>
        <span className="badge text-bg-info" style={{ fontSize: 10 }}>{isDsl ? 'DSL' : '因子'}</span>
        {strategy.run_count != null && (
          <span style={{ fontSize: 10, color: 'var(--text-faint)' }}>· {strategy.run_count} 跑</span>
        )}
        <button
          type="button"
          className="btn p-0 border-0 text-faint"
          style={{ fontSize: 11 }}
          title="删除策略（全部版本）"
          onClick={(e) => {
            e.preventDefault()
            if (window.confirm(`删除策略「${strategy.name}」的全部版本？`)) onDelete(strategy.name)
          }}
        >
          ×
        </button>
      </summary>

      <div style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>
        {strategy.description && <div>{strategy.description}</div>}
        <div className="mt-1">
          持仓 top {eng?.top_n ?? '-'} · 基准 {eng?.benchmark_index ?? '-'} ·{' '}
          {strategy.strategy_config?.params?.rebalance_frequency ?? 'monthly'} 调仓
        </div>
      </div>

      <div className="d-flex gap-1 flex-wrap mt-1">
        <button type="button" className="btn btn-outline-primary btn-sm" style={{ fontSize: 11, padding: '1px 8px' }}
          onClick={() => onAskAi(`回测策略「${strategy.name}」，并把结果与沪深300基准对比`)}>
          ▶ 回测
        </button>
        <button type="button" className="btn btn-outline-primary btn-sm" style={{ fontSize: 11, padding: '1px 8px' }}
          onClick={() => setPanel(mode === 'rerun' ? 'view' : 'rerun')}>
          ⚙ 调参重跑
        </button>
        <button type="button" className="btn btn-outline-primary btn-sm" style={{ fontSize: 11, padding: '1px 8px' }}
          onClick={() => setPanel(mode === 'history' ? 'view' : 'history')}>
          🕘 版本历史
        </button>
        <button type="button" className="btn btn-outline-primary btn-sm" style={{ fontSize: 11, padding: '1px 8px' }}
          onClick={() => setPanel(mode === 'fork' ? 'view' : 'fork')}>
          ✎ 派生新版本
        </button>
        <button type="button" className="btn btn-outline-primary btn-sm" style={{ fontSize: 11, padding: '1px 8px' }}
          onClick={() => onAskAi(`帮我优化策略「${strategy.name}」：先看它当前的配置与回测表现，提出改进候选并验证对比，经我确认后再保存新版本`)}>
          🤖 AI 优化
        </button>
      </div>

      {open && mode === 'view' && <ViewPanel strategy={strategy} isDsl={!!isDsl} />}
      {open && mode === 'rerun' && <RerunPanel strategy={strategy} onAskAi={onAskAi} />}
      {open && mode === 'fork' && <ForkPanel strategy={strategy} isDsl={!!isDsl} onChanged={onChanged} />}
      {open && mode === 'history' && <HistoryPanel name={strategy.name} />}
    </details>
  )
}
