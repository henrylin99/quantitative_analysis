import { useEffect, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { cn } from '../../lib/cn'

/**
 * 无依赖模态原语（参考 tick-stock-panel Modal 模式）：
 * ESC 关闭、点击遮罩关闭、焦点陷阱、aria 属性。
 */
export function Modal({
  open,
  onClose,
  title,
  children,
  width = 'max-w-2xl',
}: {
  open: boolean
  onClose: () => void
  title: ReactNode
  children: ReactNode
  width?: string
}) {
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onClose()
        return
      }
      if (event.key === 'Tab' && panelRef.current) {
        // 简易焦点陷阱：Tab 循环限制在面板内
        const focusables = panelRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        )
        if (focusables.length === 0) return
        const first = focusables[0]
        const last = focusables[focusables.length - 1]
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault()
          last.focus()
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault()
          first.focus()
        }
      }
    }
    document.addEventListener('keydown', onKey, true)
    return () => document.removeEventListener('keydown', onKey, true)
  }, [open, onClose])

  if (!open) return null

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-4 pt-[8vh]"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        className={cn(
          'w-full rounded-dialog border border-line bg-surface shadow-xl',
          'animate-[modal-in_.16s_ease-smooth]',
          width,
        )}
      >
        <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
          <div className="text-sm font-semibold">{title}</div>
          <button
            type="button"
            aria-label="关闭"
            onClick={onClose}
            className="rounded-btn p-1 text-fg-muted transition-colors hover:bg-elevated hover:text-fg-primary"
          >
            <X size={15} />
          </button>
        </div>
        <div className="max-h-[72vh] overflow-y-auto p-4">{children}</div>
      </div>
    </div>,
    document.body,
  )
}
