import { useEffect, useRef, useState } from 'react'
import { fetchTickerSearch, type TickerSearchItem } from '../api/market'
import { useDebouncedValue } from '../utils/hooks'

/** 6 位代码归一化（600000.SH 直用；裸 6 位按交易所规则推断后缀） */
function normalizeCode(input: string): string | null {
  const text = input.trim().toUpperCase()
  if (/^\d{6}\.(SH|SZ|BJ)$/.test(text)) return text
  if (/^\d{6}$/.test(text)) {
    if (text.startsWith('6')) return `${text}.SH`
    if (text.startsWith('8') || text.startsWith('4')) return `${text}.BJ`
    return `${text}.SZ`
  }
  return null
}

const BOX: React.CSSProperties = {
  position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 30, marginTop: 4,
  background: 'var(--surface-2)', border: '1px solid var(--border-strong)',
  borderRadius: 'var(--radius-sm)', boxShadow: '0 10px 28px rgba(2, 6, 23, 0.35)', overflow: 'hidden',
}
const ROW: React.CSSProperties = {
  display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, width: '100%',
  padding: '7px 12px', background: 'transparent', border: 'none', color: 'var(--text)',
  textAlign: 'left', fontSize: 13, cursor: 'pointer',
}
const HINT: React.CSSProperties = { padding: '7px 12px', color: 'var(--text-faint)', fontSize: 12 }

/**
 * 股票代码/名称搜索选择器：≥2 字符防抖联想，裸 6 位代码直接可用。
 * 受控：value 为 ts_code（空串表示未选），选中后以 chip 展示可更换。
 */
export default function StockPicker({
  value,
  name,
  onPick,
  onClear,
}: {
  value: string
  name: string
  onPick: (tsCode: string, stockName: string) => void
  onClear: () => void
}) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<TickerSearchItem[]>([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState(false)
  const boxRef = useRef<HTMLDivElement>(null)
  const debounced = useDebouncedValue(query, 300)
  const direct = normalizeCode(query)

  useEffect(() => {
    const keyword = debounced.trim()
    if (keyword.length < 2 || normalizeCode(keyword)) {
      setItems([])
      setLoading(false)
      return
    }
    let alive = true
    setLoading(true)
    setLoadError(false)
    fetchTickerSearch(keyword, 8)
      .then((r) => {
        if (alive) setItems(r.items.filter((x) => x.ts_code && x.ts_code !== value))
      })
      .catch(() => {
        if (alive) {
          setItems([])
          setLoadError(true)
        }
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [debounced, value])

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  const pick = (tsCode: string, stockName: string) => {
    onPick(tsCode, stockName)
    setQuery('')
    setOpen(false)
  }

  const dropdownOpen = open && query.trim().length >= 2

  if (value) {
    return (
      <div className="d-flex align-items-center gap-2">
        <span className="chip">{name ? `${name} · ${value}` : value}</span>
        <button type="button" className="btn btn-outline-secondary btn-sm" onClick={onClear}>
          更换
        </button>
      </div>
    )
  }

  return (
    <div ref={boxRef} style={{ position: 'relative' }}>
      <input
        type="text"
        className="form-control"
        value={query}
        placeholder="代码或名称，如 600519 / 贵州茅台"
        autoComplete="off"
        onChange={(e) => {
          setQuery(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key !== 'Enter' || !dropdownOpen) return
          e.preventDefault()
          if (direct) pick(direct, '')
          else if (items.length > 0) pick(items[0].ts_code, items[0].name ?? '')
        }}
      />
      {dropdownOpen && (
        <div style={BOX}>
          {direct && (
            <button type="button" style={ROW} onClick={() => pick(direct, '')}>
              <span>直接使用 {direct}</span>
              <span className="num" style={{ color: 'var(--text-faint)', fontSize: 11 }}>
                不经检索
              </span>
            </button>
          )}
          {loading ? (
            <div style={HINT}>搜索中…</div>
          ) : items.length === 0 && !direct ? (
            <div style={HINT}>
              {loadError ? '检索服务暂不可用，可直接输入 6 位代码' : '没有匹配的 A 股标的'}
            </div>
          ) : (
            items.map((item) => (
              <button
                key={item.ts_code}
                type="button"
                style={ROW}
                onClick={() => pick(item.ts_code, item.name ?? '')}
              >
                <span>{item.name}</span>
                <span className="num" style={{ color: 'var(--text-faint)' }}>
                  {item.ts_code}
                </span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}
