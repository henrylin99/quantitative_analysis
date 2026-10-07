import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BellRing, ListPlus, Search, Trash2 } from 'lucide-react'
import {
  addWatchlistItem,
  checkWatchlistAlerts,
  fetchQuotes,
  fetchTickerSearch,
  fetchWatchlist,
  fetchWatchlistAlerts,
  removeWatchlistItem,
  replaceWatchlist,
  updateWatchlistItem,
  type QuoteRow,
  type TickerSearchItem,
  type WatchlistItem,
} from '../api/market'
import { StockLink } from '../components/stock/StockLink'
import { Card, Delta, EmptyState, PageHeader, SectionTitle, SkeletonRows } from '../components/ui'
import { useDebouncedValue } from '../utils/hooks'

const STORAGE_KEY = 'qa-watchlist'
const DEFAULT_WATCHLIST = ['600000.SH', '000001.SZ', '300750.SZ', '601318.SH', '600519.SH']

function loadLocalCodes(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as string[]) : []
  } catch {
    return []
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
  const queryClient = useQueryClient()
  const [input, setInput] = useState('')
  const [showSuggestions, setShowSuggestions] = useState(false)
  const searchBoxRef = useRef<HTMLFormElement>(null)

  const listQuery = useQuery({ queryKey: ['watchlist'], queryFn: fetchWatchlist })
  const items = listQuery.data?.items ?? []
  const codes = items.map((x) => x.ts_code)
  const groups = [...new Set(items.map((x) => x.group).filter(Boolean))]

  // 首次加载：服务端为空时迁移 localStorage，再退到默认清单（各自只做一次）
  const migratedRef = useRef(false)
  useEffect(() => {
    if (listQuery.isLoading || migratedRef.current) return
    migratedRef.current = true
    if (items.length > 0) return
    const localCodes = loadLocalCodes()
    const seed = localCodes.length > 0 ? localCodes : DEFAULT_WATCHLIST
    if (localCodes.length > 0) {
      try {
        localStorage.removeItem(STORAGE_KEY)
      } catch {
        // 忽略
      }
    }
    replaceWatchlist(seed.map((c) => ({ ts_code: c })))
      .then(() => queryClient.invalidateQueries({ queryKey: ['watchlist'] }))
      .catch(() => undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listQuery.isLoading, items.length])

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['watchlist'] })

  const addMutation = useMutation({
    mutationFn: async (raw: string) => {
      const code = normalizeCode(raw)
      if (!code) throw new Error('未识别代码：支持 6 位数字、600000.SH，或输入名称搜索')
      await addWatchlistItem(code)
      return code
    },
    onSuccess: invalidate,
  })

  const removeMutation = useMutation({
    mutationFn: (code: string) => removeWatchlistItem(code),
    onSuccess: invalidate,
  })

  const updateMutation = useMutation({
    mutationFn: ({ code, patch }: { code: string; patch: Partial<WatchlistItem> }) =>
      updateWatchlistItem(code, patch),
    onSuccess: invalidate,
  })

  const quotesQuery = useQuery({
    queryKey: ['market', 'watchlist', codes.join(',')],
    queryFn: () => fetchQuotes(codes),
    refetchInterval: 5_000,
    enabled: codes.length > 0,
  })

  // 名称/代码模糊搜索联想（直接输入完整代码时不查，走 normalizeCode 直加）
  const debouncedInput = useDebouncedValue(input, 300)
  const keyword = debouncedInput.trim()
  const isDirectCode = Boolean(normalizeCode(keyword))
  const searchQuery = useQuery({
    queryKey: ['market', 'ticker-search', keyword],
    queryFn: () => fetchTickerSearch(keyword, 8),
    enabled: keyword.length >= 2 && !isDirectCode,
  })
  const suggestions = (searchQuery.data?.items ?? []).filter(
    (item: TickerSearchItem) => item.ts_code && !codes.includes(item.ts_code),
  )

  // 点击外部收起联想下拉
  useEffect(() => {
    const onClickOutside = (event: MouseEvent) => {
      if (searchBoxRef.current && !searchBoxRef.current.contains(event.target as Node)) {
        setShowSuggestions(false)
      }
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  const pickSuggestion = (item: TickerSearchItem) => {
    if (codes.includes(item.ts_code)) return
    addMutation.mutate(item.ts_code, { onError: () => {} })
    setInput('')
    setShowSuggestions(false)
  }

  const quotes = quotesQuery.data?.quotes ?? {}
  const rows = codes.map((code) => quotes[code]).filter(Boolean) as QuoteRow[]

  return (
    <div className="tsp-root min-h-full">
      <PageHeader
        title="自选行情"
        subtitle="扶摇实时快照 · 5s 自动刷新 · 分组 / 备注 / 价格提醒保存在服务端"
        right={
          <form
            ref={searchBoxRef}
            className="relative flex items-center gap-1.5"
            onSubmit={(event) => {
              event.preventDefault()
              if (!input.trim()) return
              setShowSuggestions(false)
              addMutation.mutate(input, {
                onSuccess: () => setInput(''),
                onError: () => {},
              })
            }}
          >
            <input
              value={input}
              onChange={(event) => {
                setInput(event.target.value)
                setShowSuggestions(true)
              }}
              onFocus={() => setShowSuggestions(true)}
              placeholder="代码或名称，如 600519 / 茅台"
              className="num w-48 rounded-input border border-line bg-elevated/50 px-2 py-1 text-xs outline-none placeholder:text-fg-muted focus:border-accent/60"
            />
            <button
              type="submit"
              className="inline-flex items-center gap-1 rounded-btn border border-accent/30 bg-accent/12 px-2.5 py-1 text-xs text-accent transition-colors hover:bg-accent/20"
            >
              <ListPlus size={12} /> 添加
            </button>
            {showSuggestions && keyword.length >= 2 && !isDirectCode ? (
              <div className="absolute right-0 top-full z-20 mt-1 w-72 overflow-hidden rounded-card border border-line bg-surface shadow-lg">
                {searchQuery.isLoading ? (
                  <div className="px-3 py-2 text-2xs text-fg-muted">搜索中…</div>
                ) : suggestions.length === 0 ? (
                  <div className="px-3 py-2 text-2xs text-fg-muted">
                    {searchQuery.isError ? '搜索失败，稍后再试' : '没有匹配的 A 股标的'}
                  </div>
                ) : (
                  <ul className="max-h-64 overflow-y-auto py-1">
                    {suggestions.map((item) => (
                      <li key={item.ts_code}>
                        <button
                          type="button"
                          onClick={() => pickSuggestion(item)}
                          className="flex w-full items-center justify-between px-3 py-1.5 text-left text-xs transition-colors hover:bg-elevated"
                        >
                          <span className="flex items-center gap-2">
                            <Search size={11} className="text-fg-muted" />
                            <span>{item.name ?? item.ts_code}</span>
                          </span>
                          <span className="num text-2xs text-fg-muted">{item.ts_code}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : null}
          </form>
        }
      />

      <div className="p-1.5">
        <Card className="p-0">
          <SectionTitle title="自选列表" hint={`${codes.length} 只 · 每日收盘后自动检查价格提醒`} />
          {addMutation.isError ? (
            <div className="mx-3 mb-2 rounded-input border border-danger/25 bg-danger/8 px-2 py-1 text-2xs text-danger">
              {(addMutation.error as Error).message}
            </div>
          ) : null}

          {codes.length === 0 ? (
            <EmptyState
              icon={<ListPlus size={22} />}
              title="还没有自选股"
              description="在右上角输入 6 位代码或名称搜索添加，例如 600519（贵州茅台）、300750（宁德时代）。"
            />
          ) : quotesQuery.isLoading || listQuery.isLoading ? (
            <SkeletonRows rows={codes.length} />
          ) : (
            <table className="w-full border-collapse text-xs">
              <thead>
                <tr className="border-b border-line text-left text-2xs text-fg-muted">
                  <th className="px-3 py-1.5 font-medium">代码</th>
                  <th className="px-3 py-1.5 font-medium">名称</th>
                  <th className="px-3 py-1.5 text-right font-medium">现价</th>
                  <th className="px-3 py-1.5 text-right font-medium">涨跌幅</th>
                  <th className="px-3 py-1.5 text-right font-medium">成交额</th>
                  <th className="px-3 py-1.5 font-medium">分组</th>
                  <th className="px-3 py-1.5 font-medium">备注</th>
                  <th className="px-3 py-1.5 font-medium">提醒 ≥ / ≤</th>
                  <th className="w-10 px-2 py-1.5" aria-label="操作" />
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const row = quotes[item.ts_code] as QuoteRow | undefined
                  return (
                    <tr key={item.ts_code} className="border-t border-line/60 hover:bg-elevated/50">
                      <td className="px-3 py-1.5">
                        <StockLink code={item.ts_code} name={row?.name ?? null} />
                      </td>
                      <td className="px-3 py-1.5 text-fg-secondary">
                        <StockLink code={item.ts_code} name={row?.name ?? null} showCode={false} />
                      </td>
                      <td className="num px-3 py-1.5 text-right">{row?.last_price ?? '--'}</td>
                      <td className="px-3 py-1.5 text-right">
                        <Delta value={row?.pct_chg ?? null} />
                      </td>
                      <td className="num px-3 py-1.5 text-right text-fg-secondary">{Yi(row?.turnover)}</td>
                      <td className="px-3 py-1.5">
                        <input
                          list="watchlist-groups"
                          defaultValue={item.group}
                          placeholder="默认"
                          className="w-20 rounded-input border border-line bg-elevated/50 px-1.5 py-0.5 text-2xs outline-none focus:border-accent/60"
                          onBlur={(e) => {
                            const v = e.target.value.trim() || '默认'
                            if (v !== item.group) updateMutation.mutate({ code: item.ts_code, patch: { group: v } })
                          }}
                        />
                      </td>
                      <td className="px-3 py-1.5">
                        <input
                          defaultValue={item.note}
                          placeholder="—"
                          className="w-28 rounded-input border border-line bg-elevated/50 px-1.5 py-0.5 text-2xs outline-none focus:border-accent/60"
                          onBlur={(e) => {
                            const v = e.target.value.trim()
                            if (v !== item.note) updateMutation.mutate({ code: item.ts_code, patch: { note: v } })
                          }}
                        />
                      </td>
                      <td className="px-3 py-1.5">
                        <div className="flex items-center gap-1">
                          <input
                            type="number"
                            defaultValue={item.alert_high ?? ''}
                            placeholder="高价"
                            step="any"
                            className="num w-16 rounded-input border border-line bg-elevated/50 px-1.5 py-0.5 text-2xs outline-none focus:border-accent/60"
                            onBlur={(e) => {
                              const v = e.target.value === '' ? null : Number(e.target.value)
                              if (v !== item.alert_high) updateMutation.mutate({ code: item.ts_code, patch: { alert_high: v } })
                            }}
                          />
                          <span className="text-2xs text-fg-muted">/</span>
                          <input
                            type="number"
                            defaultValue={item.alert_low ?? ''}
                            placeholder="低价"
                            step="any"
                            className="num w-16 rounded-input border border-line bg-elevated/50 px-1.5 py-0.5 text-2xs outline-none focus:border-accent/60"
                            onBlur={(e) => {
                              const v = e.target.value === '' ? null : Number(e.target.value)
                              if (v !== item.alert_low) updateMutation.mutate({ code: item.ts_code, patch: { alert_low: v } })
                            }}
                          />
                        </div>
                      </td>
                      <td className="px-2 py-1.5 text-right">
                        <button
                          type="button"
                          aria-label={`移除 ${item.ts_code}`}
                          onClick={() => removeMutation.mutate(item.ts_code)}
                          className="rounded-btn p-1 text-fg-muted transition-colors hover:bg-danger/12 hover:text-danger"
                        >
                          <Trash2 size={12} />
                        </button>
                      </td>
                    </tr>
                  )
                })}
                {rows.length < codes.length ? (
                  <tr className="border-t border-line/60">
                    <td colSpan={9} className="px-3 py-2 text-2xs text-fg-muted">
                      有 {codes.length - rows.length} 只暂无行情（可能已退市或代码有误）
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          )}
          <datalist id="watchlist-groups">
            {groups.map((g) => (
              <option key={g} value={g} />
            ))}
          </datalist>
        </Card>

        <WatchlistAlertsCard />
      </div>
    </div>
  )
}

function WatchlistAlertsCard() {
  const queryClient = useQueryClient()
  const alertsQuery = useQuery({ queryKey: ['watchlist-alerts'], queryFn: fetchWatchlistAlerts })
  const checkMutation = useMutation({
    mutationFn: checkWatchlistAlerts,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['watchlist-alerts'] }),
  })
  const alerts = alertsQuery.data?.alerts ?? []

  return (
    <Card className="mt-1.5 p-0">
      <SectionTitle
        title="价格提醒触发记录"
        hint="每日收盘数据就绪后自动检查（也可手动）"
        right={
          <button
            type="button"
            className="inline-flex items-center gap-1 rounded-btn border border-line px-2 py-1 text-2xs text-fg-secondary transition-colors hover:bg-elevated"
            disabled={checkMutation.isPending}
            onClick={() => checkMutation.mutate()}
          >
            <BellRing size={11} /> {checkMutation.isPending ? '检查中…' : '立即检查'}
          </button>
        }
      />
      <div className="px-3 pb-3">
        {alerts.length === 0 ? (
          <div className="py-3 text-2xs text-fg-muted">
            暂无触发记录。在上方表格给自选股设"提醒 ≥ / ≤"价格，收盘触发后会记录在这里（配置推送渠道后同步外推）。
          </div>
        ) : (
          <ul className="divide-y divide-line/60">
            {alerts
              .slice()
              .reverse()
              .slice(0, 20)
              .map((a, i) => (
                <li key={`${a.ts_code}-${a.kind}-${a.close_date}-${i}`} className="flex items-center gap-2 py-1.5 text-xs">
                  <span
                    className={`rounded-full px-1.5 py-0.5 text-2xs ${
                      a.kind === 'above' ? 'bg-danger/12 text-danger' : 'bg-success/12 text-success'
                    }`}
                  >
                    {a.kind === 'above' ? '破高位' : '破低位'}
                  </span>
                  <StockLink code={a.ts_code} name={null} />
                  <span className="text-fg-secondary">{a.message}</span>
                  <span className="ml-auto text-2xs text-fg-muted">{a.triggered_at}</span>
                </li>
              ))}
          </ul>
        )}
        {checkMutation.data && (
          <div className="mt-1 text-2xs text-fg-muted">
            最近检查：{checkMutation.data.checked} 只设提醒，触发 {checkMutation.data.triggered.length} 条
          </div>
        )}
      </div>
    </Card>
  )
}
