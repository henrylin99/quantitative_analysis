interface LoadingProps {
  text?: string
}

export function Loading({ text = '加载中...' }: LoadingProps) {
  return (
    <div className="text-center py-5">
      <div className="spinner-border text-primary" role="status">
        <span className="visually-hidden">{text}</span>
      </div>
      <div className="mt-2 text-secondary">{text}</div>
    </div>
  )
}

interface ErrorStateProps {
  message: string
  onRetry?: () => void
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div className="alert alert-danger-financial alert d-flex align-items-center justify-content-between" role="alert">
      <span>⚠️ {message}</span>
      {onRetry && (
        <button type="button" className="btn btn-outline-light btn-sm" onClick={onRetry}>
          重试
        </button>
      )}
    </div>
  )
}

export function EmptyState({ text = '暂无数据' }: LoadingProps) {
  return <div className="empty-state">{text}</div>
}
