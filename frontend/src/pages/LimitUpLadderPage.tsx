import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Flame, RefreshCw } from 'lucide-react'
import {
  fetchLimitUpLadder,
  fetchLimitUpPool,
  type LimitUpStock,
} from '../api/market'
import { StockLink } from '../components/stock/StockLink'
import { Badge, Card, Delta, EmptyState, KpiCell, PageHeader, SectionTitle, SkeletonRows } from '../components/ui'
import { cn } from '../lib/cn'

function yi(amount: number | null | undefined): string {
  if (amount === null || amount === undefined) return '--'
  const value = amount / 1e8
  return value >= 100 ? `${value.toFixed(1)}亿` : `${value.toFixed(2)}亿`
}

/** 连板数字 → 梯队色（越高越热） */
function ladderTone(cnt: number | undefined): string {
  if (!cnt) return 'text-fg-muted'
  if (cnt >= 5) return 'text-danger font-semibold'
  if (cnt >= 3) return 'text-warning font-medium'
  return 'text-fg-primary'
}

function ladderBadgeTone(cnt: number | undefined): 'danger' | 'warning' | 'bull' | 'neutral' {
  if (!cnt) return 'neutral'
  if (cnt >= 3) return 'danger'
  if (cnt === 2) return 'warning'
  return 'bull'
}

function LadderMatrix({ days }: { days: { date: string | null; counts: Record<string, number>; highest: number; total: number }[] }) {
  const boardCols = ['2', '3', '4', '5', '6', '7']
  const visible = days.slice(0, 15) // 最近 15 个交易日，横向可读
  const maxCell = Math.max(1, ...visible.flatMap((d) => boardCols.map((k) => d.counts[k] ?? 0)))
  return (
    <div className="overflow-x-auto px-3 pb-3">
      <table className="w-full min-w-[34rem] border-collapse text-xs">
        <thead>
          <tr className="border-b border-line text-left text-2xs text-fg-muted">
            <th className="px-2 py-1.5 font-medium">日期</th>
            {boardCols.map((k) => (
              <th key={k} className="px-2 py-1.5 text-center font-medium">
                {k === '7' ? '7板+' : `${k}板`}
              </th>
            ))}
            <th className="px-2 py-1.5 text-right font-medium">合计</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((day) => (
            <tr key={day.date ?? ''} className="border-t border-line/60">
              <td className="num px-2 py-1 text-fg-secondary">{day.date ?? '--'}</td>
              {boardCols.map((k) => {
                const count = day.counts[k] ?? 0
                return (
                  <td key={k} className="px-1 py-1 text-center">
                    {count > 0 ? (
                      <span
                        className={cn('num inline-block min-w-6 rounded-sm px-1 py-0.5', ladderTone(k === '7' ? 7 : Number(k)))}
                        style={{ backgroundColor: `color-mix(in srgb, currentColor ${Math.round((count / maxCell) * 22 + 6)}%, transparent)` }}
                      >
                        {count}
                      </span>
                    ) : (
                      <span className="text-fg-muted/40">·</span>
                    )}
                  </td>
                )
              })}
              <td className="num px-2 py-1 text-right text-fg-secondary">{day.total}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function PoolTable({ items }: { items: LimitUpStock[] }) {
  return (
    <table className="w-full border-collapse text-xs">
      <thead>
        <tr className="border-b border-line text-left text-2xs text-fg-muted">
          <th className="px-3 py-1.5 font-medium">梯队</th>
          <th className="px-3 py-1.5 font-medium">个股</th>
          <th className="px-3 py-1.5 text-right font-medium">现价</th>
          <th className="px-3 py-1.5 text-right font-medium">涨幅</th>
          <th className="px-3 py-1.5 font-medium">首次涨停</th>
          <th className="px-3 py-1.5 text-right font-medium">封单额</th>
          <th className="px-3 py-1.5 font-medium">涨停原因</th>
        </tr>
      </thead>
      <tbody>
        {items.map((row, index) => (
          <tr key={`${row.ts_code}-${index}`} className="border-t border-line/60 hover:bg-elevated/50">
            <td className="px-3 py-1.5">
              <Badge tone={ladderBadgeTone(row.continue_day_cnt)}>{row.continue_day_text ?? '首板'}</Badge>
            </td>
            <td className="px-3 py-1.5">
              <StockLink code={row.ts_code} name={row.name} />
              {row.is_st ? <span className="ml-1 text-2xs text-danger">ST</span> : null}
              {row.is_new ? <span className="ml-1 text-2xs text-accent">新</span> : null}
            </td>
            <td className="num px-3 py-1.5 text-right">{row.last_price ?? '--'}</td>
            <td className="px-3 py-1.5 text-right">
              <Delta value={row.pct_chg} />
            </td>
            <td className="num px-3 py-1.5 text-fg-secondary">{row.limit_up_time ?? '--'}</td>
            <td className="num px-3 py-1.5 text-right text-fg-secondary">{yi(row.seal_money)}</td>
            <td className="max-w-[16rem] truncate px-3 py-1.5 text-fg-muted" title={row.reason ?? ''}>
              {row.reason ?? '--'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function LimitUpLadderPage() {
  const [date, setDate] = useState('')

  const ladderQuery = useQuery({
    queryKey: ['market', 'limit-up-ladder'],
    queryFn: fetchLimitUpLadder,
    refetchInterval: 300_000,
  })
  const poolQuery = useQuery({
    queryKey: ['market', 'limit-up-pool', date],
    queryFn: () => fetchLimitUpPool(date || undefined),
    refetchInterval: date ? false : 60_000,
  })

  const pool = poolQuery.data
  const items = pool?.items ?? []
  const highest = Math.max(0, ...items.map((row) => row.continue_day_cnt ?? 0))
  const ladderCount = items.filter((row) => (row.continue_day_cnt ?? 0) >= 2).length

  return (
    <div className="tsp-root min-h-full">
      <PageHeader
        title="连板天梯"
        subtitle={
          pool?.date
            ? `涨停池日期 ${pool.date} · 扶摇特色数据${pool.stale ? '（降级缓存）' : ''}`
            : '扶摇涨停池与连板天梯 · 60s 自动刷新'
        }
        right={
          <div className="flex items-center gap-1.5">
            <input
              type="date"
              value={date}
              max={new Date().toISOString().slice(0, 10)}
              onChange={(event) => setDate(event.target.value)}
              className="num rounded-input border border-line bg-elevated/50 px-2 py-1 text-xs outline-none focus:border-accent/60"
            />
            <button
              type="button"
              onClick={() => {
                poolQuery.refetch()
                ladderQuery.refetch()
              }}
              className="inline-flex items-center gap-1.5 rounded-btn border border-line px-2.5 py-1 text-xs text-fg-secondary transition-colors hover:bg-elevated hover:text-fg-primary"
            >
              <RefreshCw size={12} className={poolQuery.isFetching ? 'animate-spin' : ''} /> 刷新
            </button>
          </div>
        }
      />

      <div className="space-y-1.5 p-1.5">
        {/* KPI 行 */}
        <div className="grid grid-cols-2 gap-1.5 md:grid-cols-4">
          <KpiCell label="涨停家数" value={pool?.total ?? '—'} tone="bull" />
          <KpiCell label="最高连板" value={highest ? `${highest}板` : '—'} tone={highest >= 4 ? 'bull' : 'neutral'} />
          <KpiCell label="连板家数" value={ladderCount || '—'} sub="≥2板" tone="accent" />
          <KpiCell label="两板及以上占比" value={pool?.total ? `${((ladderCount / pool.total) * 100).toFixed(0)}%` : '—'} />
        </div>

        {/* 天梯矩阵 */}
        <Card>
          <SectionTitle
            icon={<Flame size={13} />}
            title="连板天梯矩阵"
            hint="近 15 个交易日 · 各梯队家数"
          />
          {ladderQuery.isLoading ? (
            <SkeletonRows rows={6} />
          ) : ladderQuery.isError ? (
            <EmptyState
              title="天梯加载失败"
              description={(ladderQuery.error as Error)?.message}
              action={
                <button
                  type="button"
                  className="rounded-btn border border-line px-2.5 py-1 text-xs text-fg-secondary hover:bg-elevated"
                  onClick={() => ladderQuery.refetch()}
                >
                  重试
                </button>
              }
            />
          ) : (
            <LadderMatrix days={ladderQuery.data?.days ?? []} />
          )}
        </Card>

        {/* 涨停池 */}
        <Card className="p-0">
          <SectionTitle title="涨停池" hint={pool?.total != null ? `${pool.total} 只 · 连板数降序` : undefined} />
          {poolQuery.isLoading ? (
            <SkeletonRows rows={8} />
          ) : poolQuery.isError ? (
            <EmptyState
              title="涨停池加载失败"
              description={(poolQuery.error as Error)?.message}
              action={
                <button
                  type="button"
                  className="rounded-btn border border-line px-2.5 py-1 text-xs text-fg-secondary hover:bg-elevated"
                  onClick={() => poolQuery.refetch()}
                >
                  重试
                </button>
              }
            />
          ) : items.length === 0 ? (
            <EmptyState
              icon={<Flame size={22} />}
              title="所选日期无涨停数据"
              description="可能是非交易日，换一个日期试试。"
            />
          ) : (
            <PoolTable items={items} />
          )}
        </Card>
      </div>
    </div>
  )
}
