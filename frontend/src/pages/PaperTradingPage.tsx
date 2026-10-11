import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { NotebookPen, Play, RefreshCw } from 'lucide-react'
import EChart from '../charts/EChart'
import {
  fetchPaperAlignment,
  fetchPaperHistory,
  fetchPaperStatus,
  resetPaperAccount,
  runPaperDaily,
  type PaperNavPoint,
  type PaperOrder,
  type PaperPosition,
  type PaperTrade,
} from '../api/paperTrading'
import { StockLink } from '../components/stock/StockLink'
import { Badge, Card, Delta, KpiCell, PageHeader, SectionTitle } from '../components/ui'

function fmtMoney(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '--'
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 0 })
}

function OrderTable({ orders }: { orders: PaperOrder[] }) {
  if (!orders.length) return <p className="px-1 py-3 text-xs text-fg-muted">当前无挂单</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-line text-left text-fg-muted">
            <th className="px-3 py-1.5 font-medium">代码</th>
            <th className="px-3 py-1.5 font-medium">方向</th>
            <th className="px-3 py-1.5 font-medium">信号日</th>
            <th className="px-3 py-1.5 font-medium">信号收盘</th>
            <th className="px-3 py-1.5 font-medium">目标金额</th>
            <th className="px-3 py-1.5 font-medium">理由</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((o) => (
            <tr key={o.order_id} className="border-b border-line/50">
              <td className="px-3 py-1.5"><StockLink code={o.ts_code} /></td>
              <td className="px-3 py-1.5">
                <Badge tone={o.side === 'buy' ? 'bull' : 'bear'}>
                  {o.side === 'buy' ? '买入' : '卖出'}
                </Badge>
              </td>
              <td className="num px-3 py-1.5">{o.signal_date}</td>
              <td className="num px-3 py-1.5">{o.signal_close ?? '--'}</td>
              <td className="num px-3 py-1.5">{fmtMoney(o.target_value)}</td>
              <td className="px-3 py-1.5 text-fg-secondary">{o.reason ?? '--'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function PositionTable({ positions }: { positions: PaperPosition[] }) {
  if (!positions.length) return <p className="px-1 py-3 text-xs text-fg-muted">当前无持仓</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-line text-left text-fg-muted">
            <th className="px-3 py-1.5 font-medium">代码</th>
            <th className="px-3 py-1.5 font-medium">数量</th>
            <th className="px-3 py-1.5 font-medium">成本</th>
            <th className="px-3 py-1.5 font-medium">现价</th>
            <th className="px-3 py-1.5 font-medium">市值</th>
            <th className="px-3 py-1.5 font-medium">盈亏</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => (
            <tr key={p.ts_code} className="border-b border-line/50">
              <td className="px-3 py-1.5"><StockLink code={p.ts_code} /></td>
              <td className="num px-3 py-1.5">{p.qty}</td>
              <td className="num px-3 py-1.5">{p.avg_cost.toFixed(3)}</td>
              <td className="num px-3 py-1.5">{p.last_close.toFixed(3)}</td>
              <td className="num px-3 py-1.5">{fmtMoney(p.market_value)}</td>
              <td className="num px-3 py-1.5">
                <span className={p.pnl >= 0 ? 'text-bull' : 'text-bear'}>
                  {fmtMoney(p.pnl)}（{(p.pnl_pct ?? 0) * 100 > 0 ? '+' : ''}
                  {((p.pnl_pct ?? 0) * 100).toFixed(2)}%）
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TradeTable({ trades }: { trades: PaperTrade[] }) {
  if (!trades.length) return <p className="px-1 py-3 text-xs text-fg-muted">暂无成交流水</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-line text-left text-fg-muted">
            <th className="px-3 py-1.5 font-medium">日期</th>
            <th className="px-3 py-1.5 font-medium">代码</th>
            <th className="px-3 py-1.5 font-medium">方向</th>
            <th className="px-3 py-1.5 font-medium">数量</th>
            <th className="px-3 py-1.5 font-medium">成交价</th>
            <th className="px-3 py-1.5 font-medium">信号收盘价差</th>
            <th className="px-3 py-1.5 font-medium">成本</th>
          </tr>
        </thead>
        <tbody>
          {[...trades].reverse().map((t) => (
            <tr key={t.trade_id} className="border-b border-line/50">
              <td className="num px-3 py-1.5">{t.date}</td>
              <td className="px-3 py-1.5"><StockLink code={t.ts_code} /></td>
              <td className="px-3 py-1.5">
                <Badge tone={t.side === 'buy' ? 'bull' : 'bear'}>
                  {t.side === 'buy' ? '买入' : '卖出'}
                </Badge>
              </td>
              <td className="num px-3 py-1.5">{t.qty}</td>
              <td className="num px-3 py-1.5">{t.price}</td>
              <td className="px-3 py-1.5">
                <Delta value={t.price_gap !== null ? t.price_gap * 100 : null} />
              </td>
              <td className="num px-3 py-1.5">{t.costs.total_cost.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function NavChart({ navHistory }: { navHistory: PaperNavPoint[] }) {
  if (navHistory.length < 2) {
    return <p className="px-1 py-6 text-center text-xs text-fg-muted">盯市净值不足两日，待运行累积</p>
  }
  // 模拟盘 vs 信号篮子（回测同口径）两条归一化净值
  let paperIdx = 1
  let basketIdx = 1
  const dates: string[] = []
  const paperNav: number[] = []
  const basketNav: number[] = []
  for (const row of navHistory) {
    dates.push(row.date)
    paperIdx *= 1 + row.paper_ret
    paperNav.push(Number(paperIdx.toFixed(6)))
    if (row.basket_ret !== null) basketIdx *= 1 + row.basket_ret
    basketNav.push(Number(basketIdx.toFixed(6)))
  }
  const option = {
    grid: { left: 48, right: 16, top: 32, bottom: 28 },
    tooltip: { trigger: 'axis' as const },
    legend: { data: ['模拟盘净值', '信号篮子（回测口径）'], top: 0 },
    xAxis: { type: 'category' as const, data: dates },
    yAxis: { type: 'value' as const, scale: true },
    series: [
      { name: '模拟盘净值', type: 'line' as const, data: paperNav, showSymbol: false },
      { name: '信号篮子（回测口径）', type: 'line' as const, data: basketNav, showSymbol: false, lineStyle: { type: 'dashed' as const } },
    ],
  }
  return <EChart option={option} height={280} />
}

export default function PaperTradingPage() {
  const queryClient = useQueryClient()
  const [resetCash, setResetCash] = useState('1000000')
  const [resetTopN, setResetTopN] = useState('10')
  const [resetOpen, setResetOpen] = useState(false)

  const statusQuery = useQuery({
    queryKey: ['paper-trading', 'status'],
    queryFn: fetchPaperStatus,
    refetchInterval: 120_000,
  })
  const historyQuery = useQuery({
    queryKey: ['paper-trading', 'history'],
    queryFn: () => fetchPaperHistory(300),
    staleTime: 300_000,
  })
  const alignmentQuery = useQuery({
    queryKey: ['paper-trading', 'alignment'],
    queryFn: fetchPaperAlignment,
    staleTime: 300_000,
  })

  const runMutation = useMutation({
    mutationFn: runPaperDaily,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['paper-trading'] })
    },
  })
  const resetMutation = useMutation({
    mutationFn: () => resetPaperAccount(Number(resetCash), Number(resetTopN)),
    onSuccess: () => {
      setResetOpen(false)
      queryClient.invalidateQueries({ queryKey: ['paper-trading'] })
    },
  })

  const st = statusQuery.data
  const alignment = alignmentQuery.data

  return (
    <div className="tsp-root min-h-full">
      <PageHeader
        title="模拟盘 Paper Trading"
        subtitle={
          st
            ? `虚拟账户 ${st.account_id} · 建于 ${st.created_at} · 纯虚拟记账无券商接口 · 每日 18:30 信号 → 次日开盘成交`
            : '加载中…'
        }
        right={
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => runMutation.mutate()}
              disabled={runMutation.isPending}
              className="inline-flex items-center gap-1.5 rounded-btn border border-line px-2.5 py-1 text-xs text-fg-secondary transition-colors hover:bg-elevated hover:text-fg-primary disabled:opacity-50"
            >
              <Play size={12} /> {runMutation.isPending ? '运行中…' : '手动运行一轮'}
            </button>
            <button
              type="button"
              onClick={() => statusQuery.refetch()}
              className="inline-flex items-center gap-1.5 rounded-btn border border-line px-2.5 py-1 text-xs text-fg-secondary transition-colors hover:bg-elevated hover:text-fg-primary"
            >
              <RefreshCw size={12} className={statusQuery.isFetching ? 'animate-spin' : ''} /> 刷新
            </button>
          </div>
        }
      />

      <div className="space-y-1.5 p-1.5">
        {statusQuery.isError ? (
          <Card className="p-4 text-xs text-danger">加载失败：{(statusQuery.error as Error).message}</Card>
        ) : null}

        {/* KPI 行 */}
        <div className="grid grid-cols-2 gap-1.5 md:grid-cols-3 xl:grid-cols-6">
          <KpiCell label="净值" value={st ? fmtMoney(st.nav) : '--'} sub={st ? `初始 ${fmtMoney(st.initial_cash)}` : ''} tone="accent" />
          <KpiCell
            label="累计盈亏"
            value={st ? `${fmtMoney(st.total_pnl)}` : '--'}
            sub={st ? <Delta value={st.total_pnl_pct * 100} /> : undefined}
            tone={st && st.total_pnl >= 0 ? 'bull' : 'bear'}
          />
          <KpiCell label="现金" value={st ? fmtMoney(st.cash) : '--'} />
          <KpiCell label="持仓数" value={st ? `${st.positions.length} / 目标 ${st.top_n}` : '--'} />
          <KpiCell label="待执行单" value={st ? `${st.pending_orders.length} 笔` : '--'} sub={st ? `信号日 ${st.last_signal_date ?? '--'}` : ''} />
          <KpiCell
            label="成交/过期"
            value={st ? `${st.stats.filled} / ${st.stats.expired}` : '--'}
            sub={st ? `过期含停牌/涨跌停 3 日未成` : ''}
          />
        </div>

        {/* 净值 vs 信号篮子 */}
        <Card>
          <SectionTitle title="盯市净值 vs 信号篮子（回测口径）" />
          <div className="px-1.5 pb-1.5">
            <NavChart navHistory={historyQuery.data?.nav_history ?? []} />
          </div>
        </Card>

        {/* 对齐报告 */}
        {alignment ? (
          <Card>
            <SectionTitle title="对齐报告（跟踪误差归因）" />
            <div className="grid grid-cols-2 gap-1.5 px-3 pb-3 md:grid-cols-4 xl:grid-cols-7">
              <KpiCell label="盯市天数" value={alignment.n_days} />
              <KpiCell label="模拟盘累计" value={alignment.paper_cum_ret !== null ? `${(alignment.paper_cum_ret * 100).toFixed(2)}%` : '--'} />
              <KpiCell label="篮子累计" value={alignment.basket_cum_ret !== null ? `${(alignment.basket_cum_ret * 100).toFixed(2)}%` : '--'} />
              <KpiCell label="日跟踪误差" value={alignment.tracking_error_daily !== null ? `${(alignment.tracking_error_daily * 100).toFixed(3)}%` : '--'} />
              <KpiCell label="净值相关性" value={alignment.nav_corr !== null ? alignment.nav_corr.toFixed(3) : '--'} />
              <KpiCell
                label="买/卖成交价差"
                value={
                  alignment.attribution.avg_buy_fill_gap !== null || alignment.attribution.avg_sell_fill_gap !== null
                    ? `${((alignment.attribution.avg_buy_fill_gap ?? 0) * 100).toFixed(2)}% / ${((alignment.attribution.avg_sell_fill_gap ?? 0) * 100).toFixed(2)}%`
                    : '--'
                }
              />
              <KpiCell label="成本拖累" value={`${(alignment.attribution.cost_drag_pct * 100).toFixed(3)}%`} sub={`${alignment.attribution.n_trades} 笔成交`} />
            </div>
            <p className="px-3 pb-2 text-2xs text-fg-muted">{alignment.note}</p>
          </Card>
        ) : null}

        {/* 待执行单 */}
        <Card>
          <SectionTitle title="待执行单（次日开盘虚拟成交）" />
          <OrderTable orders={st?.pending_orders ?? []} />
        </Card>

        {/* 持仓 */}
        <Card>
          <SectionTitle title="当前持仓" />
          <PositionTable positions={st?.positions ?? []} />
        </Card>

        {/* 流水 */}
        <Card>
          <SectionTitle title="成交流水" />
          <TradeTable trades={historyQuery.data?.trades ?? []} />
        </Card>

        {/* 重置 */}
        <Card>
          <SectionTitle title="账户重置" />
          <div className="flex flex-wrap items-center gap-2 px-3 pb-3">
            {!resetOpen ? (
              <button
                type="button"
                onClick={() => setResetOpen(true)}
                className="inline-flex items-center gap-1.5 rounded-btn border border-line px-2.5 py-1 text-xs text-fg-secondary transition-colors hover:bg-elevated hover:text-fg-primary"
              >
                <NotebookPen size={12} /> 重置虚拟账户…
              </button>
            ) : (
              <>
                <label className="flex items-center gap-1 text-xs text-fg-secondary">
                  初始现金
                  <input
                    value={resetCash}
                    onChange={(e) => setResetCash(e.target.value)}
                    className="num w-28 rounded-input border border-line bg-elevated/50 px-2 py-1 text-xs outline-none focus:border-accent/60"
                  />
                </label>
                <label className="flex items-center gap-1 text-xs text-fg-secondary">
                  Top N
                  <input
                    value={resetTopN}
                    onChange={(e) => setResetTopN(e.target.value)}
                    className="num w-16 rounded-input border border-line bg-elevated/50 px-2 py-1 text-xs outline-none focus:border-accent/60"
                  />
                </label>
                <button
                  type="button"
                  onClick={() => resetMutation.mutate()}
                  disabled={resetMutation.isPending}
                  className="rounded-btn border border-danger/50 bg-danger/10 px-2.5 py-1 text-xs text-danger transition-colors hover:bg-danger/20 disabled:opacity-50"
                >
                  {resetMutation.isPending ? '重置中…' : '确认重置（清空持仓/流水）'}
                </button>
                <button
                  type="button"
                  onClick={() => setResetOpen(false)}
                  className="rounded-btn border border-line px-2.5 py-1 text-xs text-fg-secondary"
                >
                  取消
                </button>
                {resetMutation.isError ? (
                  <span className="text-xs text-danger">{(resetMutation.error as Error).message}</span>
                ) : null}
              </>
            )}
          </div>
        </Card>
      </div>
    </div>
  )
}
