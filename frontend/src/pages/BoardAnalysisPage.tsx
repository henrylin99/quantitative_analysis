import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Layers, RefreshCw, Search, TrendingUp } from 'lucide-react'
import {
  fetchBoardConstituents,
  fetchBoards,
  fetchIndustryRotation,
  type IndustryRotationData,
  type ThsBoardRow,
} from '../api/market'
import EChart from '../charts/EChart'
import { StockLink } from '../components/stock/StockLink'
import { Card, Delta, EmptyState, PageHeader, SectionTitle, SkeletonRows } from '../components/ui'
import { cn } from '../lib/cn'

function yi(amount: number | null | undefined): string {
  if (amount === null || amount === undefined) return '--'
  const value = amount / 1e8
  return value >= 100 ? `${value.toFixed(0)}亿` : `${value.toFixed(2)}亿`
}

interface BoardAnalysisPageProps {
  tag: 'industry' | 'cn_concept'
  title: string
  subtitle: string
}

/** 行业/概念分析共用页：板块涨跌排行 + 选中板块的成分股行情 */
export default function BoardAnalysisPage({ tag, title, subtitle }: BoardAnalysisPageProps) {
  const [keyword, setKeyword] = useState('')
  const [selected, setSelected] = useState<ThsBoardRow | null>(null)

  const boardsQuery = useQuery({
    queryKey: ['market', 'boards', tag],
    queryFn: () => fetchBoards(tag),
    refetchInterval: 60_000,
  })

  const constituentsQuery = useQuery({
    queryKey: ['market', 'board-constituents', selected?.thscode],
    queryFn: () => fetchBoardConstituents(selected!.thscode),
    enabled: Boolean(selected?.thscode),
  })

  const items = boardsQuery.data?.items ?? []
  const filtered = useMemo(() => {
    const text = keyword.trim().toLowerCase()
    if (!text) return items
    return items.filter(
      (row) =>
        (row.name ?? '').toLowerCase().includes(text) ||
        row.thscode.toLowerCase().includes(text),
    )
  }, [items, keyword])

  return (
    <div className="tsp-root min-h-full">
      <PageHeader
        title={title}
        subtitle={subtitle}
        right={
          <button
            type="button"
            onClick={() => boardsQuery.refetch()}
            className="inline-flex items-center gap-1.5 rounded-btn border border-line px-2.5 py-1 text-xs text-fg-secondary transition-colors hover:bg-elevated hover:text-fg-primary"
          >
            <RefreshCw size={12} className={boardsQuery.isFetching ? 'animate-spin' : ''} /> 刷新
          </button>
        }
      />

      <div className="grid grid-cols-1 gap-1.5 p-1.5 xl:grid-cols-[26rem_1fr]">
        {/* 左列：板块排行 */}
        <Card className="p-0">
          <SectionTitle
            icon={<Layers size={13} />}
            title="板块涨跌排行"
            hint={`${filtered.length}/${items.length} 个板块`}
            right={
              <div className="flex items-center gap-1 rounded-input border border-line bg-elevated/50 px-1.5 py-0.5">
                <Search size={11} className="text-fg-muted" />
                <input
                  value={keyword}
                  onChange={(event) => setKeyword(event.target.value)}
                  placeholder="搜索板块"
                  className="w-24 bg-transparent text-2xs outline-none placeholder:text-fg-muted"
                />
              </div>
            }
          />
          {boardsQuery.isLoading ? (
            <SkeletonRows rows={10} />
          ) : boardsQuery.isError ? (
            <EmptyState
              title="板块数据加载失败"
              description={(boardsQuery.error as Error)?.message}
              action={
                <button
                  type="button"
                  className="rounded-btn border border-line px-2.5 py-1 text-xs text-fg-secondary hover:bg-elevated"
                  onClick={() => boardsQuery.refetch()}
                >
                  重试
                </button>
              }
            />
          ) : filtered.length === 0 ? (
            <EmptyState title="没有匹配的板块" description="换个关键词试试。" />
          ) : (
            <div className="max-h-[calc(100vh-12rem)] overflow-y-auto">
              <table className="w-full border-collapse text-xs">
                <thead className="sticky top-0 z-10 bg-surface">
                  <tr className="border-b border-line text-left text-2xs text-fg-muted">
                    <th className="w-8 px-2 py-1.5 text-center font-medium">#</th>
                    <th className="px-2 py-1.5 font-medium">板块</th>
                    <th className="px-2 py-1.5 text-right font-medium">涨跌幅</th>
                    <th className="px-2 py-1.5 text-right font-medium">成交额</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((row, index) => (
                    <tr
                      key={row.thscode}
                      onClick={() => setSelected(row)}
                      className={cn(
                        'cursor-pointer border-t border-line/60 transition-colors hover:bg-elevated/60',
                        selected?.thscode === row.thscode && 'bg-accent/8',
                      )}
                    >
                      <td className="num px-2 py-1.5 text-center text-2xs text-fg-muted">{index + 1}</td>
                      <td className="px-2 py-1.5">
                        <div className="font-medium">{row.name ?? row.thscode}</div>
                        <div className="num text-2xs text-fg-muted">{row.thscode}</div>
                      </td>
                      <td className="px-2 py-1.5 text-right">
                        <Delta value={row.pct_chg} />
                      </td>
                      <td className="num px-2 py-1.5 text-right text-fg-secondary">{yi(row.turnover_yuan)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* 右列：选中板块成分股 */}
        <Card className="p-0">
          <SectionTitle
            title={selected ? `${selected.name ?? selected.thscode} · 成分股` : '成分股'}
            hint={
              constituentsQuery.data?.total != null
                ? `${constituentsQuery.data.total} 只 · 点击板块查看`
                : '点击左侧板块查看成分股'
            }
          />
          {!selected ? (
            <EmptyState
              icon={<Layers size={22} />}
              title="选择一个板块"
              description="在左侧点击任意板块，查看其成分股与实时行情。"
            />
          ) : constituentsQuery.isLoading ? (
            <SkeletonRows rows={10} />
          ) : constituentsQuery.isError ? (
            <EmptyState
              title="成分股加载失败"
              description={(constituentsQuery.error as Error)?.message}
              action={
                <button
                  type="button"
                  className="rounded-btn border border-line px-2.5 py-1 text-xs text-fg-secondary hover:bg-elevated"
                  onClick={() => constituentsQuery.refetch()}
                >
                  重试
                </button>
              }
            />
          ) : (
            <div className="max-h-[calc(100vh-12rem)] overflow-y-auto px-0.5 pb-0.5">
              <table className="w-full border-collapse text-xs">
                <thead className="sticky top-0 z-10 bg-surface">
                  <tr className="border-b border-line text-left text-2xs text-fg-muted">
                    <th className="px-3 py-1.5 font-medium">个股</th>
                    <th className="px-3 py-1.5 text-right font-medium">现价</th>
                    <th className="px-3 py-1.5 text-right font-medium">涨跌幅</th>
                    <th className="px-3 py-1.5 text-right font-medium">成交额</th>
                  </tr>
                </thead>
                <tbody>
                  {(constituentsQuery.data?.items ?? []).map((row, index) => (
                    <tr key={`${row.ts_code}-${index}`} className="border-t border-line/60 hover:bg-elevated/50">
                      <td className="px-3 py-1.5">
                        <StockLink code={row.ts_code} name={row.name} />
                      </td>
                      <td className="num px-3 py-1.5 text-right">{row.last_price ?? '--'}</td>
                      <td className="px-3 py-1.5 text-right">
                        <Delta value={row.pct_chg} />
                      </td>
                      <td className="num px-3 py-1.5 text-right text-fg-secondary">{yi(row.amount_yuan)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {tag === 'industry' && <RotationCard />}
    </div>
  )
}

function RotationCard() {
  const rotationQuery = useQuery({
    queryKey: ['trial', 'industry-rotation'],
    queryFn: () => fetchIndustryRotation(),
    staleTime: 30 * 60_000,
    retry: 1,
  })

  const navOption = useMemo(() => {
    const data: IndustryRotationData | undefined = rotationQuery.data
    if (!data?.nav_chart) return null
    const palette = ['#4f8ef7', '#22c55e', '#f59e0b', '#a855f7', '#14b8a6']
    const mk = (group: 'top' | 'bottom', dash: boolean) =>
      Object.entries(data.nav_chart[group]).map(([name, values], i) => ({
        name: `${group === 'top' ? '↑' : '↓'} ${name}`,
        type: 'line',
        showSymbol: false,
        data: values,
        lineStyle: { width: 1.4, type: dash ? 'dashed' : 'solid' },
        itemStyle: { color: palette[i % palette.length] },
      }))
    return {
      textStyle: { color: '#94a3b8' },
      tooltip: { trigger: 'axis' },
      legend: { top: 0, textStyle: { color: '#94a3b8', fontSize: 10 } },
      grid: { left: 56, right: 16, top: 44, bottom: 28 },
      xAxis: { type: 'category', data: data.nav_chart.dates },
      yAxis: { type: 'value', scale: true },
      series: [...mk('top', false), ...mk('bottom', true)],
    }
  }, [rotationQuery.data])

  const flowCell = (v: number | null) =>
    v == null ? (
      '--'
    ) : (
      <span className={v > 0 ? 'text-emerald-500' : 'text-rose-500'}>
        {(v / 1e4).toFixed(2)}亿
      </span>
    )

  return (
    <Card className="mt-1.5 p-0">
      <SectionTitle
        icon={<TrendingUp size={13} />}
        title="行业轮动评分（本地日频 · Tushare 行业口径）"
        hint={
          rotationQuery.data
            ? `${rotationQuery.data.meta.eval_start} ~ ${rotationQuery.data.meta.eval_end} · ${rotationQuery.data.meta.n_industries} 个行业 · 每小时缓存`
            : '计算中…'
        }
      />
      {rotationQuery.isLoading ? (
        <SkeletonRows rows={6} />
      ) : rotationQuery.isError ? (
        <EmptyState
          title="行业轮动评分加载失败"
          description={(rotationQuery.error as Error)?.message}
          action={
            <button
              type="button"
              className="rounded-btn border border-line px-2.5 py-1 text-xs text-fg-secondary hover:bg-elevated"
              onClick={() => rotationQuery.refetch()}
            >
              重试
            </button>
          }
        />
      ) : rotationQuery.data ? (
        <div className="grid grid-cols-1 gap-3 p-2 xl:grid-cols-[1fr_32rem]">
          <div className="max-h-[26rem] overflow-y-auto">
            <table className="w-full border-collapse text-xs">
              <thead className="sticky top-0 z-10 bg-surface">
                <tr className="border-b border-line text-left text-2xs text-fg-muted">
                  <th className="w-8 px-2 py-1.5 text-center font-medium">#</th>
                  <th className="px-2 py-1.5 font-medium">行业</th>
                  <th className="px-2 py-1.5 text-right font-medium">成分</th>
                  <th className="px-2 py-1.5 text-right font-medium">20日动量</th>
                  <th className="px-2 py-1.5 text-right font-medium">5日主力净额</th>
                  <th className="px-2 py-1.5 text-right font-medium">20日主力净额</th>
                  <th className="px-2 py-1.5 text-right font-medium">PE中位</th>
                  <th className="px-2 py-1.5 text-right font-medium">PE历史分位</th>
                  <th className="px-2 py-1.5 text-right font-medium">总分</th>
                </tr>
              </thead>
              <tbody>
                {rotationQuery.data.rows.map((row) => (
                  <tr key={row.industry} className="border-t border-line/60 hover:bg-elevated/50">
                    <td className="num px-2 py-1.5 text-center text-2xs text-fg-muted">{row.rank}</td>
                    <td className="px-2 py-1.5 font-medium">{row.industry}</td>
                    <td className="num px-2 py-1.5 text-right text-fg-secondary">{row.n_members}</td>
                    <td className="num px-2 py-1.5 text-right">
                      <Delta value={row.mom_20d} />
                    </td>
                    <td className="num px-2 py-1.5 text-right">{flowCell(row.flow_5d)}</td>
                    <td className="num px-2 py-1.5 text-right">{flowCell(row.flow_20d)}</td>
                    <td className="num px-2 py-1.5 text-right text-fg-secondary">{row.pe_med ?? '--'}</td>
                    <td className="num px-2 py-1.5 text-right text-fg-secondary">
                      {row.pe_hist_pct != null ? `${(row.pe_hist_pct * 100).toFixed(0)}%` : '--'}
                    </td>
                    <td
                      className={cn(
                        'num px-2 py-1.5 text-right font-semibold',
                        row.total_score > 0 ? 'text-emerald-500' : 'text-rose-500',
                      )}
                    >
                      {row.total_score.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div>
            {navOption ? (
              <EChart option={navOption} height={340} />
            ) : (
              <EmptyState title="暂无净值数据" />
            )}
            <p className="px-2 pb-2 text-2xs leading-relaxed text-fg-muted">
              {rotationQuery.data.score_formula}。实线为评分最高 5 行业，虚线为最低 5 行业（成分股等权累计净值）。
            </p>
          </div>
        </div>
      ) : null}
    </Card>
  )
}
