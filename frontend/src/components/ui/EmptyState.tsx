import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'

/** 空态：图标 + 标题 + 引导文案（+ 可选动作） */
export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode
  title: ReactNode
  description?: ReactNode
  action?: ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex flex-col items-center justify-center gap-1.5 px-6 py-10 text-center', className)}>
      {icon ? <div className="text-fg-muted opacity-70">{icon}</div> : null}
      <div className="text-sm font-medium">{title}</div>
      {description ? <div className="max-w-sm text-xs leading-5 text-fg-muted">{description}</div> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  )
}
