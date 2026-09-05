import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from '../../lib/cn'

/**
 * 新版卡片（1px 边框分层，暗色不用阴影）。
 * 统一公式：rounded-card border bg-surface + hover 微亮。
 */
export function Card({ className, children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'rounded-card border border-line bg-surface/80 backdrop-blur-sm',
        'transition-colors duration-150 ease-smooth hover:bg-surface',
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  )
}

/** 区块标题：accent 渐变竖条 + 图标 + 右侧提示 */
export function SectionTitle({
  icon,
  title,
  hint,
  right,
  className,
}: {
  icon?: ReactNode
  title: ReactNode
  hint?: ReactNode
  right?: ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex items-center justify-between gap-2 px-3 py-2', className)}>
      <div className="flex min-w-0 items-center gap-2">
        <span className="h-3.5 w-[3px] shrink-0 rounded-full bg-gradient-to-b from-accent to-accent/30" />
        {icon ? <span className="text-fg-muted">{icon}</span> : null}
        <span className="truncate text-sm font-semibold">{title}</span>
        {hint ? <span className="num text-2xs text-fg-muted">{hint}</span> : null}
      </div>
      {right ? <div className="shrink-0 text-xs text-fg-muted">{right}</div> : null}
    </div>
  )
}

/** 页头：细线下边框 + 标题 + 副标题 + 右侧操作槽 */
export function PageHeader({
  title,
  subtitle,
  right,
}: {
  title: ReactNode
  subtitle?: ReactNode
  right?: ReactNode
}) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
      <div className="min-w-0">
        <h1 className="truncate text-lg font-semibold leading-tight">{title}</h1>
        {subtitle ? <div className="mt-0.5 truncate text-xs text-fg-muted">{subtitle}</div> : null}
      </div>
      {right ? <div className="flex shrink-0 items-center gap-2">{right}</div> : null}
    </div>
  )
}

/** 半透明同色 pill 徽章 */
export function Badge({
  tone = 'neutral',
  className,
  children,
}: {
  tone?: 'neutral' | 'accent' | 'bull' | 'bear' | 'warning' | 'danger'
  className?: string
  children: ReactNode
}) {
  const tones: Record<string, string> = {
    neutral: 'bg-elevated text-fg-secondary border-line',
    accent: 'bg-accent/12 text-accent border-accent/25',
    bull: 'bg-bull/12 text-bull border-bull/25',
    bear: 'bg-bear/12 text-bear border-bear/25',
    warning: 'bg-warning/12 text-warning border-warning/25',
    danger: 'bg-danger/12 text-danger border-danger/25',
  }
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-1.5 py-px text-2xs leading-4',
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}

/** 涨跌着色数字（A 股口径：红涨绿跌），接受百分数数值；带箭头时省略负号 */
export function Delta({
  value,
  suffix = '%',
  digits = 2,
  arrow = true,
  className,
}: {
  value: number | null | undefined
  suffix?: string
  digits?: number
  arrow?: boolean
  className?: string
}) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return <span className={cn('num text-fg-muted', className)}>--</span>
  }
  const tone = value > 0 ? 'text-bull' : value < 0 ? 'text-bear' : 'text-fg-muted'
  const sign = value > 0 ? '+' : ''
  const prefix = arrow ? (value > 0 ? '▲' : value < 0 ? '▼' : '') : sign
  const magnitude = arrow && value < 0 ? Math.abs(value) : value
  return (
    <span className={cn('num', tone, className)}>
      {prefix}
      {magnitude.toFixed(digits)}
      {suffix}
    </span>
  )
}

/** KPI 统计格：11px 标签 + mono 数值 + 副标 */
export function KpiCell({
  label,
  value,
  sub,
  tone,
}: {
  label: ReactNode
  value: ReactNode
  sub?: ReactNode
  tone?: 'bull' | 'bear' | 'accent' | 'neutral'
}) {
  const toneClass =
    tone === 'bull'
      ? 'text-bull'
      : tone === 'bear'
        ? 'text-bear'
        : tone === 'accent'
          ? 'text-accent'
          : 'text-fg-primary'
  return (
    <div className="rounded-card border border-line bg-elevated/50 px-2.5 py-2">
      <div className="text-2xs text-fg-muted">{label}</div>
      <div className={cn('num mt-0.5 text-lg font-semibold leading-6', toneClass)}>{value}</div>
      {sub ? <div className="num text-2xs text-fg-muted">{sub}</div> : null}
    </div>
  )
}

/** 加载骨架行 */
export function SkeletonRows({ rows = 6, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn('space-y-1.5 p-3', className)}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-4 animate-pulse rounded-sm bg-elevated" style={{ opacity: 1 - i * 0.12 }} />
      ))}
    </div>
  )
}
