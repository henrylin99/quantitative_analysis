import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ListPlus, Trash2 } from 'lucide-react'
import { fetchQuotes, type QuoteRow } from '../api/market'
import { StockLink } from '../components/stock/StockLink'
import { Card, Delta, EmptyState, PageHeader, SectionTitle, SkeletonRows } from '../components/ui'

const STORAGE_KEY = 'qa-watchlist'
const DEFAULT_WATCHLIST = ['600000.SH', '000001.SZ', '300750.SZ', '601318.SH', '600519.SH']

function loadWatchlist(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_WATCHLIST
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as string[]) : DEFAULT_WATCHLIST
  } catch {
    return DEFAULT_WATCHLIST
  }
}

function normalizeCode(input: string): string | null {
  const text = input.trim().toUpperCase()
  if (/^\d{6}\.(SH|SZ|BJ)$/.test(text)) return text
  if (/^\d{6}$/.test(text)) {
    // 按常见规则推断后缀：6 开头沪市，8/4 开头北交所，其余深市
    if (text.startsWith('6')) return `${text}.SH`
    if (text.startsWith('8') || text.startsWith('4')) return `${text}.BJ`
    return `${text}.SZ`
  }
  return null
}

function Yi(amount: number | null | undefined): string {
  if (amount === null || amount === undefined) return '--'
  const value = amount / 1e8
  return value >= 100 ? `${value.toFixed(1)}亿` : `${value.toFixed(2)}亿`
}

export default function WatchlistPage() {
  const [codes, setCodes] = useState<string[]>(loadWatchlist)
  const [input, setInput] = useState('')

  const persist = (next: string[]) => {
    setCodes(next)
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    } catch {
      // 忽略持久化失败
    }
  }

  const quotesQuery = useQuery({
    queryKey: ['market', 'watchlist', codes],
    queryFn: () => fetchQuotes(codes),
    refetchInterval: 5_000,
    enabled: codes.length > 0,
  })

  const addMutation = useMutation({
    mutationFn: async (raw: string) => {
      const code = normalizeCode(raw)
      if (!code) throw new Error('代码格式应为 6 位数字或 600000.SH 形式')
      if (codes.includes(code)) throw new Error(`${code} 已在自选中`)
      persist([...codes, code])
      return code
    },
  })

  const quotes = quotesQuery.data?.quotes ?? {}
  const rows = codes.map((code) => quotes[code]).filter(Boolean) as QuoteRow[]

  return (
    <div className="tsp-root min-h-full">
      <PageHeader
        title="自选行情"
        subtitle="扶摇实时快照 · 5s 自动刷新 · 分组保存在本地浏览器"
        right={
          <form
            className="flex items-center gap-1.5"
            onSubmit={(event) => {
              event.preventDefault()
              if (!input.trim()) return
              addMutation.mutate(input, {
                onSuccess: () => setInput(''),
                onError: () => {},
              })
            }}
          >
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="输入代码，如 600519"
              className="num w-40 rounded-input border border-line bg-elevated/50 px-2 py-1 text-xs outline-none placeholder:text-fg-muted focus:border-accent/60"
            />
            <button
              type="submit"
              className="inline-flex items-center gap-1 rounded-btn border border-accent/30 bg-accent/12 px-2.5 py-1 text-xs text-accent transition-colors hover:bg-accent/20"
            >
              <ListPlus size={12} /> 添加
            </button>
          </form>
        }
      />

      <div className="p-1.5">
        <Card className="p-0">
          <SectionTitle title="自选列表" hint={`${codes.length} 只`} />
          {addMutation.isError ? (
            <div className="mx-3 mb-2 rounded-input border border-danger/25 bg-danger/8 px-2 py-1 text-2xs text-danger">
              {(addMutation.error as Error).message}
            </div>
          ) : null}

          {codes.length === 0 ? (
            <EmptyState
              icon={<ListPlus size={22} />}
              title="还没有自选股"
              description="在右上角输入 6 位代码添加，例如 600519（贵州茅台）、300750（宁德时代）。"
            />
          ) : quotesQuery.isLoading ? (
            <SkeletonRows rows={codes.length} />
          ) : (
            <table className="w-full border-collapse text-xs">
              <thead>
                <tr className="border-b border-line text-left text-2xs text-fg-muted">
                  <th className="px-3 py-1.5 font-medium">代码</th>
                  <th className="px-3 py-1.5 font-medium">名称</th>
                  <th className="px-3 py-1.5 text-right font-medium">现价</th>
                  <th className="px-3 py-1.5 text-right font-medium">涨跌幅</th>
                  <th className="px-3 py-1.5 text-right font-medium">涨跌</th>
                  <th className="px-3 py-1.5 text-right font-medium">成交额</th>
                  <th className="w-10 px-2 py-1.5" aria-label="操作" />
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.ts_code} className="border-t border-line/60 hover:bg-elevated/50">
                    <td className="px-3 py-1.5">
                      <StockLink code={row.ts_code} name={row.name} />
                    </td>
                    <td className="px-3 py-1.5 text-fg-secondary">
                      <StockLink code={row.ts_code} name={row.name} showCode={false} />
                    </td>
                    <td className="num px-3 py-1.5 text-right">{row.last_price ?? '--'}</td>
                    <td className="px-3 py-1.5 text-right">
                      <Delta value={row.pct_chg} />
                    </td>
                    <td className="px-3 py-1.5 text-right">
                      <Delta value={row.change} suffix="" digits={2} />
                    </td>
                    <td className="num px-3 py-1.5 text-right text-fg-secondary">{Yi(row.turnover)}</td>
                    <td className="px-2 py-1.5 text-right">
                      <button
                        type="button"
                        aria-label={`移除 ${row.ts_code}`}
                        onClick={() => persist(codes.filter((code) => code !== row.ts_code))}
                        className="rounded-btn p-1 text-fg-muted transition-colors hover:bg-danger/12 hover:text-danger"
                      >
                        <Trash2 size={12} />
                      </button>
                    </td>
                  </tr>
                ))}
                {rows.length < codes.length ? (
                  <tr className="border-t border-line/60">
                    <td colSpan={7} className="px-3 py-2 text-2xs text-fg-muted">
                      有 {codes.length - rows.length} 只暂无行情（可能已退市或代码有误）
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          )}
        </Card>
      </div>
    </div>
  )
}
