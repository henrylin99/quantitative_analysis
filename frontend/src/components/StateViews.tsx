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
      <span>⚠️ {message}</span>
      {onRetry && (
        <button type="button" className="btn btn-outline-secondary btn-sm" onClick={onRetry}>
          重试
        </button>
      )}
    </div>
  )
}

interface EmptyStateProps {
  text?: string
  icon?: string
}

export function EmptyState({ text = '暂无数据', icon = '📭' }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <span className="icon">{icon}</span>
      <div className="hint">{text}</div>
    </div>
  )
}
