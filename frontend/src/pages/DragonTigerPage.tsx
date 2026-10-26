import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Flame, Ticket } from 'lucide-react'
import {
  fetchAuctionBenchmark,
  fetchDragonTiger,
  fetchEventResearch,
  type DragonTigerStock,
  type DragonTigerForwardSummary,
} from '../api/market'
import { StockLink } from '../components/stock/StockLink'
import { Badge, Card, Delta, EmptyState, KpiCell, PageHeader, SectionTitle, SkeletonRows } from '../components/ui'
import { cn } from '../lib/cn'

const BOARDS = [
  { key: 'all', label: '全部' },
  { key: 'org', label: '机构榜' },
  { key: 'hot_money', label: '游资榜' },
] as const

type BoardKey = (typeof BOARDS)[number]['key']

function fmtWan(value: unknown): string {
  const num = typeof value === 'number' || typeof value === 'string' ? Number(value) : NaN
  if (Number.isNaN(num)) return '--'
  const yi = num / 1e8
  if (Math.abs(yi) >= 1) return `${yi.toFixed(2)}亿`
  const wan = num / 1e4
  return `${wan.toFixed(0)}万`
}

function pickStockItems(payload: Record<string, unknown> | undefined, board: BoardKey): DragonTigerStock[] {
  if (!payload) return []
  if (board === 'org') return (payload.org_items as DragonTigerStock[]) ?? []
  if (board === 'hot_money') return (payload.hot_money_items as DragonTigerStock[]) ?? []
  return (payload.stock_items as DragonTigerStock[]) ?? []
}

function reasonOf(row: DragonTigerStock): string {
  if (row.limit_reason) return String(row.limit_reason)
  const concepts = (row.concept_list ?? []).map((item) => item?.name).filter(Boolean)
  return concepts.join(' / ')
}

/** 上榜后 N 日分组统计卡（净买额中位数分组，本地事件归档） */
function ForwardGroupCells({ label, summary }: { label: string; summary?: DragonTigerForwardSummary }) {
  if (!summary) return null
  return (
    <>
      <KpiCell label={`${label}·样本`} value={summary.n} tone="neutral" />
      <KpiCell
        label={`${label}·N日均收`}
        value={summary.avg_fwd_ret != null ? `${(summary.avg_fwd_ret * 100).toFixed(2)}%` : '—'}
        tone={(summary.avg_fwd_ret ?? 0) >= 0 ? 'bull' : 'bear'}
      />
      <KpiCell
        label={`${label}·超额`}
        value={summary.avg_excess != null ? `${(summary.avg_excess * 100).toFixed(2)}%` : '—'}
        sub="vs 沪深300"
        tone={(summary.avg_excess ?? 0) >= 0 ? 'bull' : 'bear'}
      />
    </>
  )
}

export default function DragonTigerPage() {
  const [board, setBoard] = useState<BoardKey>('all')
  const [date, setDate] = useState('')

  const dragonQuery = useQuery({
    queryKey: ['market', 'dragon-tiger', board, date],
    queryFn: () => fetchDragonTiger(board, date || undefined),
  })
  const auctionQuery = useQuery({
    queryKey: ['market', 'auction', date],
    queryFn: () => fetchAuctionBenchmark(date || undefined),
  })
  const researchQuery = useQuery({
    queryKey: ['market', 'event-research', 'dragon'],
    queryFn: () => fetchEventResearch(5),
    staleTime: 600_000,
  })

  const payload = dragonQuery.data as Record<string, unknown> | undefined
  const stocks = pickStockItems(payload, board)
  const tradeDate = (payload?.trade_date as string) ?? ''
  const auctionItems = auctionQuery.data?.item ?? []

  return (
    <div className="app-root min-h-full">
      <PageHeader
        title="龙虎榜与竞价风向标"
        subtitle={
          tradeDate
            ? `榜单日期 ${tradeDate} · 扶摇特色数据（当日数据缓存）`
            : '扶摇特色数据 · 当日数据缓存'
        }
        right={
          <input
            type="date"
            value={date}
            max={new Date().toISOString().slice(0, 10)}
            onChange={(event) => setDate(event.target.value)}
            className="num rounded-input border border-line bg-elevated/50 px-2 py-1 text-xs outline-none focus:border-accent/60"
          />
        }
      />

      <div className="space-y-1.5 p-1.5">
        {/* 榜单卡 */}
        <Card className="p-0">
          <SectionTitle
            icon={<Flame size={13} />}
            title="龙虎榜"
            right={
              <div className="flex items-center gap-1">
                {BOARDS.map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => setBoard(item.key)}
                    className={cn(
                      'rounded-btn px-2 py-0.5 text-xs transition-colors',
                      board === item.key
                        ? 'bg-accent/15 text-accent'
                        : 'text-fg-muted hover:bg-elevated hover:text-fg-secondary',
                    )}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            }
          />

          {dragonQuery.isLoading ? (
            <SkeletonRows rows={8} />
          ) : dragonQuery.isError ? (
            <EmptyState
              title="榜单加载失败"
              description={(dragonQuery.error as Error)?.message}
              action={
                <button
                  type="button"
                  className="rounded-btn border border-line px-2.5 py-1 text-xs text-fg-secondary hover:bg-elevated"
                  onClick={() => dragonQuery.refetch()}
                >
                  重试
                </button>
              }
            />
          ) : stocks.length === 0 ? (
            <EmptyState
              icon={<Flame size={22} />}
              title="暂无榜单数据"
              description="当日龙虎榜尚未发布，或所选日期无上榜个股。"
            />
          ) : (
            <table className="w-full border-collapse text-xs">
              <thead>
                <tr className="border-b border-line text-left text-2xs text-fg-muted">
                  <th className="px-3 py-1.5 font-medium">代码</th>
                  <th className="px-3 py-1.5 font-medium">名称</th>
                  <th className="px-3 py-1.5 text-right font-medium">涨跌幅</th>
                  <th className="px-3 py-1.5 text-right font-medium">龙虎榜净买</th>
                  <th className="px-3 py-1.5 text-right font-medium">买入额</th>
                  <th className="px-3 py-1.5 text-right font-medium">卖出额</th>
                  <th className="px-3 py-1.5 font-medium">上榜原因 / 概念</th>
                </tr>
              </thead>
              <tbody>
                {stocks.map((row, index) => (
                  <tr key={`${row.thscode}-${index}`} className="border-t border-line/60 hover:bg-elevated/50">
                    <td className="px-3 py-1.5">
                      {row.thscode ? <StockLink code={row.thscode} name={row.name} /> : '--'}
                    </td>
                    <td className="px-3 py-1.5 text-fg-secondary">
                      {row.thscode ? (
                        <StockLink code={row.thscode} name={row.name} showCode={false} />
                      ) : (
                        row.name ?? '--'
                      )}
                    </td>
                    <td className="px-3 py-1.5 text-right">
                      <Delta value={typeof row.change === 'number' ? row.change * 100 : null} />
                    </td>
                    <td className="num px-3 py-1.5 text-right">
                      <span
                        className={cn(
                          'num',
                          (row.net_value ?? 0) > 0 ? 'text-bull' : (row.net_value ?? 0) < 0 ? 'text-bear' : 'text-fg-muted',
                        )}
                      >
                        {fmtWan(row.net_value)}
                      </span>
                    </td>
                    <td className="num px-3 py-1.5 text-right text-fg-secondary">{fmtWan(row.buy_value)}</td>
                    <td className="num px-3 py-1.5 text-right text-fg-secondary">{fmtWan(row.sell_value)}</td>
                    <td className="max-w-[18rem] truncate px-3 py-1.5 text-fg-muted">{reasonOf(row) || '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        {/* 上榜后 N 日超额（事件归档研究） */}
        <Card>
          <SectionTitle
            icon={<Flame size={13} />}
            title="上榜后 5 日表现（净买额分组）"
            hint={researchQuery.data?.dragon_tiger.note ?? '本地事件归档 · T 日收盘入场（乐观上界）'}
          />
          {researchQuery.isLoading ? (
            <SkeletonRows rows={3} />
          ) : researchQuery.data?.dragon_tiger && !researchQuery.data.dragon_tiger.error ? (
            <div className="grid grid-cols-3 gap-1.5 p-3 md:grid-cols-6">
              <ForwardGroupCells label="净买高" summary={researchQuery.data.dragon_tiger.net_buy_high} />
              <ForwardGroupCells label="净买低" summary={researchQuery.data.dragon_tiger.net_buy_low} />
            </div>
          ) : (
            <EmptyState
              title="上榜后统计暂不可用"
              description={researchQuery.data?.dragon_tiger?.error ?? '事件归档积累中（含出场窗口需约 2 周）'}
            />
          )}
        </Card>

        {/* 竞价风向标 */}
        <Card className="p-0">
          <SectionTitle
            icon={<Ticket size={13} />}
            title="盘前竞价短线风向标"
            hint={auctionQuery.data?.date ? `日期 ${auctionQuery.data.date}` : '当日'}
          />
          {auctionQuery.isLoading ? (
            <SkeletonRows rows={3} />
          ) : auctionItems.length === 0 ? (
            <EmptyState
              icon={<Ticket size={20} />}
              title="今日暂无风向标"
              description="竞价风向标每个交易日盘前更新（每日约 5~6 只），当日非盘前时段可能为空，可选择历史日期查看。"
            />
          ) : (
            <div className="grid grid-cols-1 gap-1.5 p-3 md:grid-cols-2 xl:grid-cols-3">
              {auctionItems.map((item, index) => (
                <div
                  key={`${item.thscode}-${index}`}
                  className="flex items-center justify-between rounded-card border border-line bg-elevated/40 px-3 py-2"
                >
                  <div>
                    <div className="num text-xs text-fg-muted">{item.thscode}</div>
                    <div className="text-sm font-medium">
                      {item.thscode ? (
                        <StockLink code={item.thscode} name={item.name ?? item.ticker} showCode={false} />
                      ) : (
                        item.name ?? '--'
                      )}
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {(item.tags ?? []).map((tag) => (
                        <Badge key={tag} tone="accent">
                          {tag}
                        </Badge>
                      ))}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-2xs text-fg-muted">竞价涨幅</div>
                    <Delta value={item.auction_pct} className="text-base font-semibold" />
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
