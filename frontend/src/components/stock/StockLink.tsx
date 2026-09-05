import { Link } from 'react-router-dom'
import { cn } from '../../lib/cn'

interface StockLinkProps {
  /** ts_code 形式（600000.SH）或同花顺 thscode */
  code: string
  name?: string | null
  /** 显示的文本；默认 `名称 代码`，传 showCode=false 只显示名称 */
  showCode?: boolean
  className?: string
}

/** 个股链接：跳转到既有详情页 /stock/:tsCode（悬停显主题色，下划线由下划线偏移衬托） */
export function StockLink({ code, name, showCode = true, className }: StockLinkProps) {
  const label = name || code
  return (
    <Link
      to={`/stock/${encodeURIComponent(code)}`}
      title={`查看 ${label} 详情`}
      className={cn(
        'group inline-flex items-baseline gap-1.5 rounded-sm transition-colors hover:text-accent',
        className,
      )}
    >
      {showCode ? <span className="num text-fg-muted group-hover:text-accent/80">{code}</span> : null}
      <span className={cn(showCode && 'text-fg-secondary')}>{name ?? ''}</span>
      {!showCode && !name ? <span className="num">{code}</span> : null}
    </Link>
  )
}
