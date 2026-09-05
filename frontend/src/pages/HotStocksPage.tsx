import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, Flame, Minus, RefreshCw, TrendingUp } from 'lucide-react'
import { fetchHotStocks, type HotPeriod, type HotStock } from '../api/market'
import { StockLink } from '../components/stock/StockLink'
import { Card, EmptyState, PageHeader, SectionTitle, SkeletonRows } from '../components/ui'
import { cn } from '../lib/cn'

const PERIODS = [
  { key: 'day', label: '当日' },
  { key: 'hour', label: '小时榜' },
] as const

function fmtHeat(heat: number | null | undefined): string {
  if (heat === null || heat === undefined) return '--'
  if (heat >= 1e8) return `${(heat / 1e8).toFixed(2)}亿`
  if (heat >= 1e4) return `${(heat / 1e4).toFixed(1)}万`
  return `${heat.toFixed(0)}`
}

function RankTrend({ row }: { row: HotStock }) {
  const change = row.rank_change ?? 0
  const trend = row.rank_trend
  if (trend === 'up' || change > 0) {
    return (
      <span className="num inline-flex items-center gap-0.5 text-bull">
        <ArrowUp size={11} />
        {Math.abs(change)}
      </span>
    )
  }
  if (trend === 'down' || change < 0) {
    return (
      <span className="num inline-flex items-center gap-0.5 text-bear">
        <ArrowDown size={11} />
        {Math.abs(change)}
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-0.5 text-fg-muted">
      <Minus size={11} /> 持平
    </span>
  )
}

function HotTable({ rows }: { rows: HotStock[] }) {
  return (
    <table className="w-full border-collapse text-xs">
      <thead>
        <tr className="border-b border-line text-left text-2xs text-fg-muted">
          <th className="w-10 px-3 py-1.5 text-center font-medium">#</th>
          <th className="px-3 py-1.5 font-medium">个股</th>
          <th className="px-3 py-1.5 text-right font-medium">热度</th>
          <th className="px-3 py-1.5 text-right font-medium">排名变化</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <tr key={`${row.ts_code}-${index}`} className="border-t border-line/60 hover:bg-elevated/50">
            <td
              className={cn(
                'num px-3 py-1.5 text-center font-semibold',
                (row.rank ?? index + 1) <= 3 ? 'text-warning' : 'text-fg-muted',
              )}
            >
              {row.rank ?? index + 1}
            </td>
            <td className="px-3 py-1.5">
              <StockLink code={row.ts_code} name={row.name} />
            </td>
            <td className="num px-3 py-1.5 text-right text-fg-secondary">{fmtHeat(row.heat)}</td>
            <td className="px-3 py-1.5 text-right">
              <RankTrend row={row} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function HotStocksPage() {
  const [period, setPeriod] = useState<HotPeriod>('day')

  const hotQuery = useQuery({
    queryKey: ['market', 'hot-stocks', period],
    queryFn: () => fetchHotStocks(period),
    refetchInterval: 300_000,
  })

  const hot = hotQuery.data?.hot ?? []
  const skyrocket = hotQuery.data?.skyrocket ?? []

  return (
    <div className="tsp-root min-h-full">
      <PageHeader
        title="热股榜单"
        subtitle="同花顺热股榜与飙升榜（按市场关注度排序）· 5 分钟缓存"
        right={
          <div className="flex items-center gap-1.5">
            <div className="flex items-center gap-1">
              {PERIODS.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setPeriod(item.key)}
                  className={cn(
                    'rounded-btn px-2 py-0.5 text-xs transition-colors',
                    period === item.key
                      ? 'bg-accent/15 text-accent'
                      : 'text-fg-muted hover:bg-elevated hover:text-fg-secondary',
                  )}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={() => hotQuery.refetch()}
              className="inline-flex items-center gap-1.5 rounded-btn border border-line px-2.5 py-1 text-xs text-fg-secondary transition-colors hover:bg-elevated hover:text-fg-primary"
            >
              <RefreshCw size={12} className={hotQuery.isFetching ? 'animate-spin' : ''} /> 刷新
            </button>
          </div>
        }
      />

      {hotQuery.isError ? (
        <div className="p-1.5">
          <Card className="border-danger/30 bg-danger/5 px-4 py-3 text-xs text-danger">
            热股榜加载失败：{(hotQuery.error as Error)?.message ?? '未知错误'}
            <button type="button" className="ml-2 underline" onClick={() => hotQuery.refetch()}>
              重试
            </button>
          </Card>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-1.5 p-1.5 lg:grid-cols-2">
        <Card className="p-0">
          <SectionTitle
            icon={<Flame size={13} />}
            title="热股榜"
            hint={hot.length ? `Top ${hot.length}` : undefined}
          />
          {hotQuery.isLoading ? (
            <SkeletonRows rows={10} />
          ) : hot.length === 0 ? (
            <EmptyState icon={<Flame size={22} />} title="暂无热股数据" description="热榜每小时更新，稍后再试。" />
          ) : (
            <div className="max-h-[calc(100vh-12rem)] overflow-y-auto">
              <HotTable rows={hot} />
            </div>
          )}
        </Card>

        <Card className="p-0">
          <SectionTitle
            icon={<TrendingUp size={13} />}
            title="飙升榜"
            hint={skyrocket.length ? `Top ${skyrocket.length}` : undefined}
          />
          {hotQuery.isLoading ? (
            <SkeletonRows rows={10} />
          ) : skyrocket.length === 0 ? (
            <EmptyState icon={<TrendingUp size={22} />} title="暂无飙升数据" description="热度飙升名单每小时更新。" />
          ) : (
            <div className="max-h-[calc(100vh-12rem)] overflow-y-auto">
              <HotTable rows={skyrocket} />
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
