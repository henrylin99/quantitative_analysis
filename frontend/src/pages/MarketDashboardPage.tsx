import { useQuery } from '@tanstack/react-query'
import { Activity, AlertTriangle, ArrowDownRight, ArrowUpRight, RefreshCw, TrendingUp } from 'lucide-react'
import { Link } from 'react-router-dom'
import { fetchDashboard, fetchIndices, type BoardRow } from '../api/market'
import { Card, Delta, KpiCell, PageHeader, SectionTitle, SkeletonRows } from '../components/ui'
import { cn } from '../lib/cn'

function yi(amountYuan: number | null | undefined): string {
  if (amountYuan === null || amountYuan === undefined) return '--'
  const value = amountYuan / 1e8
  return value >= 100 ? `${value.toFixed(0)}亿` : `${value.toFixed(2)}亿`
}

const INDEX_NAMES: Record<string, string> = {
  '000001.SH': '上证指数',
  '399001.SZ': '深证成指',
  '399006.SZ': '创业板指',
  '000300.SH': '沪深300',
}

function BoardTable({ rows, metric }: { rows: BoardRow[]; metric: 'pct' | 'amount' }) {
  return (
    <table className="w-full border-collapse text-xs">
      <tbody>
        {rows.map((row) => (
          <tr key={row.ts_code} className="border-t border-line/60 first:border-t-0 hover:bg-elevated/60">
            <td className="px-3 py-1.5">
              <span className="num">{row.ts_code}</span>
              {row.name ? <span className="ml-1.5 text-fg-secondary">{row.name}</span> : null}
            </td>
            <td className="num px-2 py-1.5 text-right text-fg-secondary">{row.price ?? '--'}</td>
            <td className="px-3 py-1.5 text-right">
              {metric === 'pct' ? (
                <Delta value={row.pct_chg} />
              ) : (
                <span className="num text-fg-secondary">{yi(row.amount_yuan)}</span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function MarketDashboardPage() {
  const dashboardQuery = useQuery({
    queryKey: ['market', 'dashboard'],
    queryFn: fetchDashboard,
    refetchInterval: 30_000,
  })
  const indexQuery = useQuery({
    queryKey: ['market', 'indices'],
    queryFn: () => fetchIndices(),
    refetchInterval: 30_000,
  })

  const data = dashboardQuery.data
  const indices = indexQuery.data?.indices ?? []
  const breadth = data?.breadth
  const maxDist = Math.max(1, ...(data?.distribution ?? []).map((d) => d.count))

  return (
    <div className="tsp-root min-h-full">
      <PageHeader
        title="市场看板"
        subtitle={
          data?.source === 'local_parquet'
            ? `实时源不可用 · 展示本地数据 ${data.as_of ?? ''}`
            : data?.server_ts
              ? `扶摇实时快照 · ${new Date(data.server_ts).toLocaleTimeString('zh-CN', { hour12: false })}`
              : '扶摇实时快照 · 30s 自动刷新'
        }
        right={
          <>
            {data?.degraded ? (
              <span className="inline-flex items-center gap-1 rounded-full border border-warning/25 bg-warning/12 px-2 py-0.5 text-2xs text-warning">
                <AlertTriangle size={11} /> 降级模式
              </span>
            ) : null}
            <button
              type="button"
              onClick={() => dashboardQuery.refetch()}
              className="inline-flex items-center gap-1.5 rounded-btn border border-line px-2.5 py-1 text-xs text-fg-secondary transition-colors hover:bg-elevated hover:text-fg-primary"
            >
              <RefreshCw size={12} className={dashboardQuery.isFetching ? 'animate-spin' : ''} /> 刷新
            </button>
          </>
        }
      />

      <div className="space-y-1.5 p-1.5">
        {/* 指数 ticker 行 */}
        <div className="grid grid-cols-2 gap-1.5 md:grid-cols-4">
          {(indices.length
            ? indices
            : [null, null, null, null]
          ).map((quote, i) => (
            <Card key={quote?.ts_code ?? `idx-${i}`} className="px-3 py-2">
              {quote ? (
                <>
                  <div className="text-xs text-fg-muted">{INDEX_NAMES[quote.ts_code] ?? quote.ts_code}</div>
                  <div className="mt-0.5 flex items-baseline justify-between">
                    <span className="num text-base font-semibold">{quote.last_price?.toFixed(2) ?? '--'}</span>
                    <Delta value={quote.pct_chg} />
                  </div>
                </>
              ) : (
                <div className="h-10 animate-pulse rounded-sm bg-elevated" />
              )}
            </Card>
          ))}
        </div>

        {dashboardQuery.isError ? (
          <Card className="border-danger/30 bg-danger/5 px-4 py-3 text-xs text-danger">
            看板加载失败：{(dashboardQuery.error as Error)?.message ?? '未知错误'}
            <button type="button" className="ml-2 underline" onClick={() => dashboardQuery.refetch()}>
              重试
            </button>
          </Card>
        ) : null}

        {/* 市场宽度 KPI 行 */}
        <div className="grid grid-cols-3 gap-1.5 md:grid-cols-6">
          {breadth ? (
            <>
              <KpiCell label="上涨" value={breadth.up} tone="bull" sub={`${((breadth.up / (breadth.total || 1)) * 100).toFixed(1)}%`} />
              <KpiCell label="下跌" value={breadth.down} tone="bear" sub={`${((breadth.down / (breadth.total || 1)) * 100).toFixed(1)}%`} />
              <KpiCell label="平盘" value={breadth.flat} />
              <KpiCell label="涨停(近)" value={breadth.limit_up} tone="bull" />
              <KpiCell label="跌停(近)" value={breadth.limit_down} tone="bear" />
              <KpiCell label="总成交" value={yi(data?.total_amount_yuan)} />
            </>
          ) : (
            Array.from({ length: 6 }).map((_, i) => <KpiCell key={i} label="—" value="—" />)
          )}
        </div>

        <div className="grid grid-cols-1 gap-1.5 xl:grid-cols-[1fr_20rem]">
          {/* 左列：分布 + 榜单 */}
          <div className="space-y-1.5">
            <Card>
              <SectionTitle icon={<Activity size={13} />} title="涨跌分布" hint="涨幅区间 · 家数" />
              <div className="space-y-1 px-3 pb-3">
                {(data?.distribution ?? []).map((bucket) => {
                  const negative = bucket.bucket.startsWith('<') || bucket.bucket.startsWith('-')
                  return (
                    <div key={bucket.bucket} className="flex items-center gap-2">
                      <span className="num w-20 shrink-0 text-2xs text-fg-muted">{bucket.bucket}</span>
                      <div className="h-3 flex-1 overflow-hidden rounded-sm bg-elevated/60">
                        <div
                          className={cn('h-full rounded-sm', negative ? 'bg-bear/70' : 'bg-bull/70')}
                          style={{ width: `${(bucket.count / maxDist) * 100}%` }}
                        />
                      </div>
                      <span className="num w-10 shrink-0 text-right text-2xs">{bucket.count}</span>
                    </div>
                  )
                })}
                {dashboardQuery.isLoading ? <SkeletonRows rows={5} /> : null}
              </div>
            </Card>

            <div className="grid grid-cols-1 gap-1.5 lg:grid-cols-3">
              <Card>
                <SectionTitle icon={<ArrowUpRight size={13} />} title="涨幅榜" />
                {dashboardQuery.isLoading ? (
                  <SkeletonRows rows={6} />
                ) : (
                  <BoardTable rows={data?.top_gainers ?? []} metric="pct" />
                )}
              </Card>
              <Card>
                <SectionTitle icon={<ArrowDownRight size={13} />} title="跌幅榜" />
                {dashboardQuery.isLoading ? (
                  <SkeletonRows rows={6} />
                ) : (
                  <BoardTable rows={data?.top_losers ?? []} metric="pct" />
                )}
              </Card>
              <Card>
                <SectionTitle icon={<TrendingUp size={13} />} title="成交额榜" />
                {dashboardQuery.isLoading ? (
                  <SkeletonRows rows={6} />
                ) : (
                  <BoardTable rows={data?.top_amount ?? []} metric="amount" />
                )}
              </Card>
            </div>
          </div>

          {/* 右列 aside */}
          <div className="space-y-1.5">
            <Card>
              <SectionTitle title="龙虎榜" hint="最近发布" />
              <div className="px-3 pb-3 text-xs leading-6 text-fg-secondary">
                <p>机构/游资席位龙虎榜与盘前竞价风向标。</p>
                <Link to="/market/dragon-tiger" className="text-accent hover:underline">
                  → 前往龙虎榜页查看
                </Link>
              </div>
            </Card>
            <Card>
              <SectionTitle title="数据源状态" />
              <div className="px-3 pb-3 text-xs leading-6 text-fg-secondary">
                <p>tushare / 扶摇 / TickFlow 的配置与健康探测。</p>
                <Link to="/datasources" className="text-accent hover:underline">
                  → 数据源中心
                </Link>
              </div>
            </Card>
          </div>
        </div>
      </div>
    </div>
  )
}
