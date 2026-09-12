import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, Flame, History, LineChart, Minus, RefreshCw, TrendingUp } from 'lucide-react'
import {
  fetchHotStockHistory,
  fetchHotStockRankTrend,
  fetchHotStocks,
  type HotPeriod,
  type HotStock,
  type RankTrendPoint,
} from '../api/market'
import { StockLink } from '../components/stock/StockLink'
import { Card, EmptyState, PageHeader, SectionTitle, SkeletonRows } from '../components/ui'
import { cn } from '../lib/cn'

const PERIODS = [
  { key: 'day', label: '当日' },
  { key: 'hour', label: '小时榜' },
  { key: 'history', label: '历史排行' },
] as const

type ViewKey = (typeof PERIODS)[number]['key']

function fmtHeat(heat: number | null | undefined): string {
  if (heat === null || heat === undefined) return '--'
  if (heat >= 1e8) return `${(heat / 1e8).toFixed(2)}亿`
  if (heat >= 1e4) return `${(heat / 1e4).toFixed(1)}万`
  return `${heat.toFixed(0)}`
}

/** 本地日期 yyyy-MM-dd（toISOString 会按 UTC 偏移，东八区会差一天） */
function fmtLocalDate(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}

function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00`)
  d.setDate(d.getDate() + days)
  return fmtLocalDate(d)
}

/** date input 的 yyyy-MM-dd → 后端 YYYYMMDD 口径 */
function toYmd(iso: string): string {
  return iso.replace(/-/g, '')
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

/** 排名走势迷你折线：排名越小越好，纵轴反转（第 1 名在最上方） */
function RankTrendChart({ points }: { points: RankTrendPoint[] }) {
  if (points.length === 0) return null
  const w = 320
  const h = 120
  const pad = 10
  const ranks = points.map((p) => p.rank)
  const min = Math.min(...ranks)
  const max = Math.max(...ranks)
  const span = Math.max(1, max - min)
  const coords = points.map((p, i) => {
    const x = points.length === 1 ? w / 2 : pad + (i / (points.length - 1)) * (w - pad * 2)
    const y = pad + ((p.rank - min) / span) * (h - pad * 2)
    return { x, y }
  })
  return (
    <div className="px-3 pb-3">
      <div className="text-accent">
        <svg viewBox={`0 0 ${w} ${h}`} className="w-full">
          <polyline
            points={coords.map((c) => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ')}
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinejoin="round"
          />
          {coords.map((c, i) => (
            <circle key={i} cx={c.x.toFixed(1)} cy={c.y.toFixed(1)} r="2.5" fill="currentColor" />
          ))}
        </svg>
      </div>
      <div className="num flex justify-between text-2xs text-fg-muted">
        <span>{points[0].date}</span>
        <span>
          最好第 {min} 名 / 最差第 {max} 名
        </span>
        <span>{points[points.length - 1].date}</span>
      </div>
    </div>
  )
}

const TREND_WINDOW_DAYS = 29 // 近 30 个自然日（含 end）

function HistoryView() {
  const [date, setDate] = useState('')
  const [selected, setSelected] = useState<{ code: string; name?: string } | null>(null)

  const historyQuery = useQuery({
    queryKey: ['market', 'hot-stock-history', date],
    queryFn: () => fetchHotStockHistory(date ? toYmd(date) : undefined),
  })

  // 走势窗口：所选日期（默认今天）往前 30 个自然日
  const endDay = date || fmtLocalDate(new Date())
  const startDay = addDays(endDay, -TREND_WINDOW_DAYS)

  const trendQuery = useQuery({
    queryKey: ['market', 'hot-stock-rank-trend', selected?.code, startDay, endDay],
    queryFn: () => fetchHotStockRankTrend(selected!.code, toYmd(startDay), toYmd(endDay)),
    enabled: !!selected,
  })

  const items = historyQuery.data?.items ?? []

  return (
    <div className="grid grid-cols-1 gap-1.5 lg:grid-cols-2">
      <Card className="p-0">
        <SectionTitle
          icon={<History size={13} />}
          title="历史热股排行"
          hint={historyQuery.data ? `${historyQuery.data.date} · Top ${items.length}` : undefined}
          right={
            <input
              type="date"
              value={date}
              max={fmtLocalDate(new Date())}
              onChange={(event) => setDate(event.target.value)}
              className="num rounded-input border border-line bg-elevated/50 px-2 py-1 text-xs outline-none focus:border-accent/60"
            />
          }
        />
        {historyQuery.isLoading ? (
          <SkeletonRows rows={10} />
        ) : historyQuery.isError ? (
          <EmptyState
            title="历史排行加载失败"
            description={(historyQuery.error as Error)?.message}
            action={
              <button
                type="button"
                className="rounded-btn border border-line px-2.5 py-1 text-xs text-fg-secondary hover:bg-elevated"
                onClick={() => historyQuery.refetch()}
              >
                重试
              </button>
            }
          />
        ) : items.length === 0 ? (
          <EmptyState
            icon={<History size={22} />}
            title="所选日期无数据"
            description="历史排行只保留一年内数据，换个日期试试。"
          />
        ) : (
            <div className="max-h-[calc(100vh-12rem)] overflow-y-auto">
              <table className="w-full border-collapse text-xs">
                <thead>
                  <tr className="border-b border-line text-left text-2xs text-fg-muted">
                    <th className="w-10 px-3 py-1.5 text-center font-medium">#</th>
                    <th className="px-3 py-1.5 font-medium">个股</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((row, index) => (
                    <tr
                      key={`${row.ts_code}-${index}`}
                      onClick={() => setSelected({ code: row.ts_code, name: row.name ?? undefined })}
                      className={cn(
                        'cursor-pointer border-t border-line/60 hover:bg-elevated/50',
                        selected?.code === row.ts_code && 'bg-accent/5',
                      )}
                    >
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
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
        )}
      </Card>

      <Card className="p-0">
        <SectionTitle
          icon={<LineChart size={13} />}
          title="个股排名走势"
          hint={selected ? `${selected.name ?? selected.code} · 近 30 天` : '点击左侧个股查看'}
        />
        {!selected ? (
          <EmptyState
            icon={<LineChart size={22} />}
            title="未选择个股"
            description="点击左侧榜单中的个股，查看近 30 天热榜排名走势。"
          />
        ) : trendQuery.isLoading ? (
          <SkeletonRows rows={6} />
        ) : trendQuery.isError ? (
          <EmptyState
            title="走势加载失败"
            description={(trendQuery.error as Error)?.message}
            action={
              <button
                type="button"
                className="rounded-btn border border-line px-2.5 py-1 text-xs text-fg-secondary hover:bg-elevated"
                onClick={() => trendQuery.refetch()}
              >
                重试
              </button>
            }
          />
        ) : (trendQuery.data?.points?.length ?? 0) === 0 ? (
          <EmptyState title="窗口内无上榜记录" description="该股在所选窗口未进入过热榜。" />
        ) : (
          <RankTrendChart points={trendQuery.data!.points} />
        )}
      </Card>
    </div>
  )
}

export default function HotStocksPage() {
  const [view, setView] = useState<ViewKey>('day')

  const hotQuery = useQuery({
    queryKey: ['market', 'hot-stocks', view],
    queryFn: () => fetchHotStocks(view as HotPeriod),
    enabled: view !== 'history',
    refetchInterval: 300_000,
  })

  const hot = hotQuery.data?.hot ?? []
  const skyrocket = hotQuery.data?.skyrocket ?? []

  return (
    <div className="tsp-root min-h-full">
      <PageHeader
        title="热股榜单"
        subtitle="同花顺热股榜 / 飙升榜 / 历史排行（按市场关注度排序）"
        right={
          <div className="flex items-center gap-1.5">
            <div className="flex items-center gap-1">
              {PERIODS.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setView(item.key)}
                  className={cn(
                    'rounded-btn px-2 py-0.5 text-xs transition-colors',
                    view === item.key
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

      {view !== 'history' && hotQuery.isError ? (
        <div className="p-1.5">
          <Card className="border-danger/30 bg-danger/5 px-4 py-3 text-xs text-danger">
            热股榜加载失败：{(hotQuery.error as Error)?.message ?? '未知错误'}
            <button type="button" className="ml-2 underline" onClick={() => hotQuery.refetch()}>
              重试
            </button>
          </Card>
        </div>
      ) : null}

      {view === 'history' ? (
        <div className="p-1.5">
          <HistoryView />
        </div>
      ) : (
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
      )}
    </div>
  )
}
