import {
  AlertTriangle, Bot, Brain, CircleCheck, ClipboardList, Coins, Compass, Crosshair,
  Database, Dna, Factory, FileText, Flame, Inbox, MessageSquare, Newspaper, PieChart,
  Puzzle, Radio, Receipt, Satellite, Search, Shield, Signal, Thermometer,
  TrendingDown, Zap, type LucideIcon,
} from 'lucide-react'

interface LoadingProps {
  text?: string
}

export function Loading({ text = '加载中...' }: LoadingProps) {
  return (
    <div className="text-center py-5" style={{ color: 'var(--text-dim)', fontSize: 13 }}>
      <div className="spinner-border spinner-fit text-primary" role="status">
        <span className="visually-hidden">{text}</span>
      </div>
      <div className="mt-2">{text}</div>
    </div>
  )
}

export function TableSkeleton({ rows = 8 }: LoadingProps & { rows?: number }) {
  return (
    <div>
      {Array.from({ length: rows }).map((_, i) => (
        <div className="skeleton-row" key={i} style={{ width: `${94 - (i % 4) * 7}%` }} />
      ))}
    </div>
  )
}

interface ErrorStateProps {
  message: string
  onRetry?: () => void
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div className="alert-error" role="alert">
      <span className="alert-error-msg">
        <AlertTriangle size={15} strokeWidth={1.8} aria-hidden />
        {message}
      </span>
      {onRetry && (
        <button type="button" className="btn btn-outline-secondary btn-sm" onClick={onRetry}>
          重试
        </button>
      )}
    </div>
  )
}

/** 旧页面仍以 emoji 字面量传 icon（如 icon="🔥"）；统一解析为 SVG 线性图标 */
const EMOJI_ICONS: Record<string, LucideIcon> = {
  '🗃️': Database,
  '🧩': Puzzle,
  '🔍': Search,
  '🎯': Crosshair,
  '📡': Radio,
  '🏭': Factory,
  '🌡️': Thermometer,
  '📊': PieChart,
  '🔥': Flame,
  '📉': TrendingDown,
  '📋': ClipboardList,
  '⚡': Zap,
  '🛰️': Satellite,
  '💰': Coins,
  '🤖': Bot,
  '🚦': Signal,
  '🧬': Dna,
  '🧾': Receipt,
  '💬': MessageSquare,
  '🧠': Brain,
  '🛡️': Shield,
  '✅': CircleCheck,
  '📰': Newspaper,
  '🧭': Compass,
  '📄': FileText,
  '📭': Inbox,
}

function EmptyIcon({ icon }: { icon: string }) {
  const Named = EMOJI_ICONS[icon] ?? (EMOJI_ICONS['📭'] as LucideIcon)
  return <Named size={34} strokeWidth={1.4} aria-hidden />
}

interface EmptyStateProps {
  text?: string
  icon?: string
}

export function EmptyState({ text = '暂无数据', icon = '📭' }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <span className="icon">
        <EmptyIcon icon={icon} />
      </span>
      <div className="hint">{text}</div>
    </div>
  )
}
