import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { Coins, Layers, LineChart as LineIcon, PieChart as PieIcon, Search, TrendingUp, Users, Wallet } from 'lucide-react'
import {
  FUND_CODE_RE,
  FUND_PERIOD_KEYS,
  fetchFundAssetAllocation,
  fetchFundDividends,
  fetchFundHistory,
  fetchFundHolders,
  fetchFundHoldings,
  fetchFundIndustryAllocation,
  fetchFundNav,
  fetchFundPerformance,
  fetchFundProfile,
  fetchFundSnapshot,
  isOnShelfFund,
  todayYmd,
  ymdDaysAgo,
  type FundHistoryPoint,
  type FundNavPoint,
} from '../api/funds'
import EChart from '../charts/EChart'
import { StockLink } from '../components/stock/StockLink'
import { Badge, Card, Delta, EmptyState, KpiCell, PageHeader, SectionTitle, SkeletonRows } from '../components/ui'
import { cn } from '../lib/cn'

// 常用基金快捷入口（ETF/LOF/场外各覆盖几只）
const PRESETS = [
  { code: '510300.SH', label: '沪深300ETF' },
  { code: '510500.SH', label: '中证500ETF' },
  { code: '512880.SH', label: '券商ETF' },
  { code: '513100.SH', label: '纳指ETF' },
  { code: '159915.SZ', label: '创业板ETF' },
  { code: '161725.SZ', label: '白酒LOF' },
] as const

const HISTORY_RANGES = [
  { key: '3m', label: '近3月', days: 92 },
  { key: '1y', label: '近1年', days: 365 },
  { key: '3y', label: '近3年', days: 365 * 3 },
  { key: '5y', label: '近5年', days: 365 * 5 },
] as const

type HistoryRangeKey = (typeof HISTORY_RANGES)[number]['key']

function numOf(v: unknown): number | null {
  if (v === null || v === undefined || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

function fmtNum(v: unknown, digits = 2): string {
  const n = numOf(v)
  return n === null ? '--' : n.toFixed(digits)
}

/** 元 → 亿/万元（快照成交额、持仓市值） */
function fmtAmount(v: unknown): string {
  const n = numOf(v)
  if (n === null) return '--'
  if (Math.abs(n) >= 1e8) return `${(n / 1e8).toFixed(2)}亿`
  if (Math.abs(n) >= 1e4) return `${(n / 1e4).toFixed(0)}万`
  return n.toFixed(0)
}

function fmtScale(v: unknown): string {
  const n = numOf(v)
  if (n === null) return '--'
  // profile.fund_scale 实测单位为元，统一展示为亿
  return `${(n / 1e8).toFixed(2)}亿`
}

function queryErrorOf(error: unknown): string {
  return (error as Error)?.message ?? '请求失败'
}

interface ChartSpec {
  isNav: boolean
  queryFn: () => Promise<unknown>
  pick: (payload: unknown) => [string, number][]
}

/** 图表数据：场内基金用前复权收盘价，场外基金用复权净值序列 */
function chartSeries(thscode: string, rangeKey: HistoryRangeKey): ChartSpec {
  const days = HISTORY_RANGES.find((r) => r.key === rangeKey)?.days ?? 365
  if (isOnShelfFund(thscode)) {
    return {
      isNav: false,
      queryFn: () => fetchFundHistory(thscode, ymdDaysAgo(days), todayYmd()),
      pick: (payload: unknown) => {
        const items = (payload as { items?: FundHistoryPoint[] })?.items ?? []
        return items
          .filter((row) => row.date && numOf(row.close_price) !== null)
          .map((row) => [row.date as string, numOf(row.close_price) as number] as [string, number])
      },
    }
  }
  // 场外基金无场内行情：nav range 与按钮窗口近似对应（fyear≈5年）
  const navRange = ({ '3m': 'hyear', '1y': 'year', '3y': 'tyear', '5y': 'fyear' } as const)[rangeKey]
  return {
    isNav: true,
    queryFn: () => fetchFundNav(thscode, navRange),
    pick: (payload: unknown) => {
      const items = (payload as FundNavPoint[]) ?? []
      return items
        .filter((row) => row.nav_date_ymd && numOf(row.adj_nav ?? row.unit_nav) !== null)
        .map(
          (row) =>
            [row.nav_date_ymd as string, numOf(row.adj_nav ?? row.unit_nav) as number] as [string, number],
        )
    },
  }
}

export default function FundCenterPage() {
  // thscode 由路由参数驱动（/fund/:thscode），可从列表页/URL 直达
  const { thscode = '' } = useParams<{ thscode: string }>()
  const navigate = useNavigate()
  const [codeInput, setCodeInput] = useState(thscode)
  const [historyRange, setHistoryRange] = useState<HistoryRangeKey>('1y')

  useEffect(() => {
    setCodeInput(thscode)
  }, [thscode])

  const enabled = FUND_CODE_RE.test(thscode)
  const onShelf = isOnShelfFund(thscode)

  const profileQuery = useQuery({
    queryKey: ['fund', 'profile', thscode],
    queryFn: () => fetchFundProfile(thscode),
    enabled,
  })
  const perfQuery = useQuery({
    queryKey: ['fund', 'performance', thscode],
    queryFn: () => fetchFundPerformance(thscode),
    enabled,
  })
  const holdingsQuery = useQuery({
    queryKey: ['fund', 'holdings', thscode],
    queryFn: () => fetchFundHoldings(thscode),
    enabled,
  })
  const holdersQuery = useQuery({
    queryKey: ['fund', 'holders', thscode],
    queryFn: () => fetchFundHolders(thscode),
    enabled,
  })
  const dividendsQuery = useQuery({
    queryKey: ['fund', 'dividends', thscode],
    queryFn: () => fetchFundDividends(thscode),
    enabled,
  })
  const assetQuery = useQuery({
    queryKey: ['fund', 'asset-allocation', thscode],
    queryFn: () => fetchFundAssetAllocation(thscode),
    enabled,
  })
  const industryQuery = useQuery({
    queryKey: ['fund', 'industry-allocation', thscode],
    queryFn: () => fetchFundIndustryAllocation(thscode),
    enabled,
  })
  const snapshotQuery = useQuery({
    queryKey: ['fund', 'snapshot', thscode],
    queryFn: () => fetchFundSnapshot(thscode),
    enabled: enabled && onShelf,
  })

  const chartSpec = useMemo(() => chartSeries(thscode, historyRange), [thscode, historyRange])
  const chartQuery = useQuery({
    queryKey: ['fund', 'chart', thscode, historyRange],
    queryFn: chartSpec.queryFn,
    enabled,
  })

  const profile = profileQuery.data
  const holdings = holdingsQuery.data
  const returns = perfQuery.data?.returns ?? {}
  const drawdowns = perfQuery.data?.drawdowns ?? {}
  const navLatest = perfQuery.data?.nav_latest ?? {}
  const snapshot = snapshotQuery.data
  // 上游对部分基金（如指数 ETF）回撤字段返回全 0，视为无回撤数据
  const hasDrawdown = FUND_PERIOD_KEYS.some((p) => (numOf(drawdowns[p.key]) ?? 0) !== 0)

  // 行业配置只展示最新报告期，按占比降序
  const industryRows = useMemo(() => {
    const rows = industryQuery.data ?? []
    const latest = rows.reduce(
      (acc, row) => (row.report_period && (!acc || row.report_period > acc) ? row.report_period : acc),
      '',
    )
    return rows
      .filter((row) => !latest || row.report_period === latest)
      .sort((a, b) => (numOf(b.ratio_pct) ?? 0) - (numOf(a.ratio_pct) ?? 0))
  }, [industryQuery.data])

  const assetRows = useMemo(() => {
    // 上游部分期次为占位行（仅 other 有残值），且 report_date 常缺失，按实质配置项剔除
    const rows = (assetQuery.data ?? []).filter(
      (row) =>
        (numOf(row.stock_ratio_pct) ?? 0) +
          (numOf(row.bond_ratio_pct) ?? 0) +
          (numOf(row.deposit_ratio_pct) ?? 0) >
        0,
    )
    return rows.slice(0, 8)
  }, [assetQuery.data])

  const dividendRows = useMemo(() => {
    const rows = [...(dividendsQuery.data?.items ?? [])]
    rows.sort((a, b) => (b.ex_dividend_date_ms_ymd ?? '').localeCompare(a.ex_dividend_date_ms_ymd ?? ''))
    return rows.slice(0, 10)
  }, [dividendsQuery.data])

  const chartOption = useMemo(() => {
    const points = chartQuery.data ? chartSpec.pick(chartQuery.data) : []
    if (points.length === 0) return null
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: 8, right: 8, top: 24, bottom: 40, containLabel: true },
      xAxis: { type: 'category', data: points.map(([d]) => d), boundaryGap: false },
      yAxis: { type: 'value', scale: true },
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 16, bottom: 6 }],
      series: [
        {
          name: chartSpec.isNav ? '复权净值' : '前复权收盘价',
          type: 'line',
          showSymbol: false,
          smooth: true,
          data: points.map(([, v]) => v),
          lineStyle: { width: 1.5 },
          areaStyle: { opacity: 0.08 },
        },
      ],
    }
  }, [chartQuery.data, chartSpec])

  function submitCode(next?: string) {
    const code = (next ?? codeInput).trim().toUpperCase()
    if (!FUND_CODE_RE.test(code)) return
    navigate(`/fund/${encodeURIComponent(code)}`)
  }

  const anyLoading = profileQuery.isLoading || perfQuery.isLoading

  return (
    <div className="tsp-root min-h-full">
      <PageHeader
        title="基金中心"
        subtitle={
          enabled
            ? `${thscode} · 扶摇同花顺基金数据（实时调用，含缓存）`
            : '扶摇同花顺基金数据 · 输入基金代码查询（如 510300.SH / 161725.SZ / 025480.OF）'
        }
        right={
          <form
            className="flex items-center gap-1"
            onSubmit={(event) => {
              event.preventDefault()
              submitCode()
            }}
          >
            <input
              value={codeInput}
              onChange={(event) => setCodeInput(event.target.value)}
              placeholder="基金代码"
              className={cn(
                'num rounded-input border bg-elevated/50 px-2 py-1 text-xs outline-none focus:border-accent/60',
                codeInput && !FUND_CODE_RE.test(codeInput.trim().toUpperCase())
                  ? 'border-danger/60'
                  : 'border-line',
              )}
              style={{ width: 120 }}
            />
            <button
              type="submit"
              className="rounded-btn border border-line px-2 py-1 text-xs text-fg-secondary hover:bg-elevated"
              title="查询"
            >
              <Search size={13} />
            </button>
          </form>
        }
      />

      <div className="space-y-1.5 p-1.5">
        {!enabled ? (
          <Card className="p-0">
            <EmptyState
              icon={<Wallet size={22} />}
              title="输入基金代码开始查询"
              description="支持 ETF / LOF（场内行情与净值）和场外基金（净值与业绩）。"
              action={
                <div className="flex flex-wrap justify-center gap-1">
                  {PRESETS.map((preset) => (
                    <button
                      key={preset.code}
                      type="button"
                      onClick={() => submitCode(preset.code)}
                      className="rounded-btn border border-line px-2.5 py-1 text-xs text-fg-secondary hover:bg-elevated"
                    >
                      {preset.label} <span className="num text-fg-muted">{preset.code}</span>
                    </button>
                  ))}
                </div>
              }
            />
          </Card>
        ) : (
          <>
            {/* 基本资料 */}
            <Card className="p-0">
              <SectionTitle
                icon={<PieIcon size={13} />}
                title={profile?.fund_name ?? thscode}
                right={
                  <div className="flex items-center gap-1">
                    <Badge tone={onShelf ? 'accent' : 'neutral'}>{onShelf ? '场内' : '场外'}</Badge>
                    <Badge tone="neutral">{thscode}</Badge>
                  </div>
                }
              />
              {profileQuery.isLoading ? (
                <SkeletonRows rows={3} />
              ) : profileQuery.isError ? (
                <EmptyState title="基金资料加载失败" description={queryErrorOf(profileQuery.error)} />
              ) : (
                <div className="grid grid-cols-2 gap-1.5 p-3 md:grid-cols-3 xl:grid-cols-6">
                  <KpiCell
                    label="单位净值"
                    value={fmtNum(navLatest.unit_nav ?? profile?.unit_nav, 4)}
                    sub={navLatest.nav_date_ymd ? `截至 ${navLatest.nav_date_ymd}` : undefined}
                  />
                  <KpiCell label="基金规模" value={fmtScale(profile?.fund_scale)} sub="最新披露" />
                  <KpiCell label="成立日期" value={<span className="text-base">{profile?.estab_date_ymd ?? '--'}</span>} />
                  <KpiCell label="基金管理人" value={<span className="text-base">{profile?.mgmt_name ?? '--'}</span>} />
                  <KpiCell label="基金经理" value={<span className="text-base">{profile?.manager_name ?? '--'}</span>} />
                  <KpiCell
                    label="场内最新价"
                    value={onShelf ? fmtNum(snapshot?.last_price, 3) : '--'}
                    sub={
                      onShelf && snapshot ? (
                        <Delta value={numOf(snapshot.price_change_ratio_pct)} arrow={false} />
                      ) : (
                        '仅 ETF/LOF'
                      )
                    }
                  />
                </div>
              )}
            </Card>

            {/* 业绩与回撤 */}
            <Card className="p-0">
              <SectionTitle
                icon={<TrendingUp size={13} />}
                title="业绩与回撤"
                hint="区间收益为百分数原值；同类排名来自同花顺同类分组"
              />
              {perfQuery.isLoading ? (
                <SkeletonRows rows={6} />
              ) : perfQuery.isError ? (
                <EmptyState title="业绩数据加载失败" description={queryErrorOf(perfQuery.error)} />
              ) : (
                <>
                  <div className="grid grid-cols-2 gap-1.5 px-3 pt-3 md:grid-cols-4">
                    <KpiCell
                      label="今年以来收益"
                      value={<Delta value={numOf(returns.return_nowyear)} arrow={false} />}
                      tone={(numOf(returns.return_nowyear) ?? 0) >= 0 ? 'bull' : 'bear'}
                    />
                    <KpiCell
                      label="近1年收益"
                      value={<Delta value={numOf(returns.return_year)} arrow={false} />}
                      tone={(numOf(returns.return_year) ?? 0) >= 0 ? 'bull' : 'bear'}
                    />
                    <KpiCell
                      label="成立以来收益"
                      value={<Delta value={numOf(returns.return_now)} arrow={false} />}
                      tone={(numOf(returns.return_now) ?? 0) >= 0 ? 'bull' : 'bear'}
                    />
                    <KpiCell
                      label="成立以来最大回撤"
                      value={
                        hasDrawdown ? (
                          <span className="text-bear">{fmtNum(drawdowns.now)}%</span>
                        ) : (
                          <span className="text-fg-muted">--</span>
                        )
                      }
                      sub={hasDrawdown ? `今年以来 ${fmtNum(drawdowns.nowyear)}%` : '暂无回撤数据'}
                    />
                  </div>
                  <table className="mt-2 w-full border-collapse text-xs">
                    <thead>
                      <tr className="border-y border-line text-left text-2xs text-fg-muted">
                        <th className="px-3 py-1.5 font-medium">区间</th>
                        <th className="px-3 py-1.5 text-right font-medium">区间收益</th>
                        <th className="px-3 py-1.5 text-right font-medium">同类平均</th>
                        <th className="px-3 py-1.5 text-right font-medium">同类排名</th>
                        {hasDrawdown && <th className="px-3 py-1.5 text-right font-medium">最大回撤</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {FUND_PERIOD_KEYS.map((period) => {
                        const ret = numOf(returns[`return_${period.key}`])
                        const peer = numOf(returns[`peer_average_${period.key}`])
                        const rank = numOf(returns[`rank_${period.key}`])
                        const rankTotal = numOf(returns[`rank_total_${period.key}`])
                        const dd = numOf(drawdowns[period.key])
                        if (ret === null && peer === null && rank === null && dd === null) return null
                        return (
                          <tr key={period.key} className="border-t border-line/60 hover:bg-elevated/50">
                            <td className="px-3 py-1.5 text-fg-secondary">{period.label}</td>
                            <td className="px-3 py-1.5 text-right">
                              <Delta value={ret} arrow={false} />
                            </td>
                            <td className="num px-3 py-1.5 text-right text-fg-muted">
                              {peer === null ? '--' : peer.toFixed(2)}
                            </td>
                            <td className="num px-3 py-1.5 text-right text-fg-secondary">
                              {rank !== null && rankTotal !== null ? `${rank.toFixed(0)} / ${rankTotal.toFixed(0)}` : '--'}
                            </td>
                            {hasDrawdown && (
                              <td className="px-3 py-1.5 text-right text-bear">{dd === null ? '--' : dd.toFixed(2)}</td>
                            )}
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </>
              )}
            </Card>

            {/* 净值走势 */}
            <Card className="p-0">
              <SectionTitle
                icon={<LineIcon size={13} />}
                title={onShelf ? '场内价格走势' : '净值走势'}
                hint={onShelf ? 'ETF 前复权日线（扶摇历史行情）' : '复权净值（无场内行情）'}
                right={
                  <div className="flex items-center gap-1">
                    {HISTORY_RANGES.map((range) => (
                      <button
                        key={range.key}
                        type="button"
                        onClick={() => setHistoryRange(range.key)}
                        className={cn(
                          'rounded-btn px-2 py-0.5 text-xs transition-colors',
                          historyRange === range.key
                            ? 'bg-accent/15 text-accent'
                            : 'text-fg-muted hover:bg-elevated hover:text-fg-secondary',
                        )}
                      >
                        {range.label}
                      </button>
                    ))}
                  </div>
                }
              />
              {chartQuery.isLoading ? (
                <SkeletonRows rows={6} />
              ) : chartQuery.isError ? (
                <EmptyState title="走势数据加载失败" description={queryErrorOf(chartQuery.error)} />
              ) : chartOption === null ? (
                <EmptyState title="暂无走势数据" description="该区间内没有净值或行情数据。" />
              ) : (
                <div className="p-2">
                  <EChart option={chartOption} height={320} />
                </div>
              )}
            </Card>

            {/* 重仓持仓 */}
            <Card className="p-0">
              <SectionTitle
                icon={<PieIcon size={13} />}
                title="重仓持仓"
                hint="定期报告披露，不代表实时持仓"
                right={
                  holdingsQuery.data?.summary ? (
                    <div className="flex flex-wrap items-center gap-1">
                      {numOf(holdings?.summary.total_stock_ratio_pct) !== null && (
                        <Badge tone="accent">股票(前十) {fmtNum(holdings?.summary.total_stock_ratio_pct, 1)}%</Badge>
                      )}
                      {numOf(holdings?.summary.total_bond_ratio_pct) !== null && (
                        <Badge tone="neutral">债券 {fmtNum(holdings?.summary.total_bond_ratio_pct, 1)}%</Badge>
                      )}
                      {(numOf(holdings?.summary.concentration_ratio) ?? 0) > 0 && (
                        <Badge tone="neutral">集中度 {fmtNum(holdings?.summary.concentration_ratio, 1)}</Badge>
                      )}
                      {holdings?.summary.main_industry ? (
                        <Badge tone="neutral">主要行业 {String(holdings?.summary.main_industry)}</Badge>
                      ) : null}
                    </div>
                  ) : undefined
                }
              />
              {holdingsQuery.isLoading ? (
                <SkeletonRows rows={6} />
              ) : holdingsQuery.isError ? (
                <EmptyState title="持仓数据加载失败" description={queryErrorOf(holdingsQuery.error)} />
              ) : (holdings?.items.length ?? 0) === 0 ? (
                <EmptyState title="暂无持仓数据" description="该基金可能尚未披露定期报告持仓。" />
              ) : (
                <table className="w-full border-collapse text-xs">
                  <thead>
                    <tr className="border-y border-line text-left text-2xs text-fg-muted">
                      <th className="px-3 py-1.5 font-medium">#</th>
                      <th className="px-3 py-1.5 font-medium">名称</th>
                      <th className="px-3 py-1.5 font-medium">代码</th>
                      <th className="px-3 py-1.5 font-medium">类型</th>
                      <th className="px-3 py-1.5 text-right font-medium">占净值比</th>
                      <th className="px-3 py-1.5 text-right font-medium">持仓市值</th>
                      <th className="px-3 py-1.5 text-right font-medium">报告期增减</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(holdings?.items ?? []).map((row, index) => (
                      <tr key={`${row.thscode ?? row.ticker}-${index}`} className="border-t border-line/60 hover:bg-elevated/50">
                        <td className="num px-3 py-1.5 text-fg-muted">{row.investment_rank ?? index + 1}</td>
                        <td className="px-3 py-1.5 text-fg-secondary">{row.stock_name ?? '--'}</td>
                        <td className="px-3 py-1.5">
                          {row.asset_type === 'stock' && row.thscode ? (
                            <StockLink code={row.thscode} name={row.stock_name} showCode={false} />
                          ) : (
                            <span className="num text-fg-muted">{row.thscode ?? row.ticker ?? '--'}</span>
                          )}
                        </td>
                        <td className="px-3 py-1.5">
                          <Badge tone={row.asset_type === 'stock' ? 'accent' : 'neutral'}>
                            {row.asset_type === 'stock' ? '股票' : row.asset_type === 'bond' ? '债券' : '基金'}
                          </Badge>
                        </td>
                        <td className="num px-3 py-1.5 text-right">{fmtNum(row.hold_ratio)}%</td>
                        <td className="num px-3 py-1.5 text-right text-fg-secondary">{fmtAmount(row.position_capital)}</td>
                        <td className="px-3 py-1.5 text-right">
                          <Delta value={numOf(row.period_increase_rate_pct)} arrow={false} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>

            <div className="grid grid-cols-1 gap-1.5 xl:grid-cols-2">
              {/* 持有人结构 */}
              <Card className="p-0">
                <SectionTitle icon={<Users size={13} />} title="持有人结构" hint="机构/个人占比与前十大持有人" />
                {holdersQuery.isLoading ? (
                  <SkeletonRows rows={4} />
                ) : holdersQuery.isError ? (
                  <EmptyState title="持有人数据加载失败" description={queryErrorOf(holdersQuery.error)} />
                ) : holdersQuery.data && holdersQuery.data.structure.length > 0 ? (
                  <div className="p-3">
                    <table className="w-full border-collapse text-xs">
                      <thead>
                        <tr className="border-b border-line text-left text-2xs text-fg-muted">
                          <th className="px-2 py-1.5 font-medium">口径</th>
                          <th className="px-2 py-1.5 text-right font-medium">机构占比</th>
                          <th className="px-2 py-1.5 text-right font-medium">个人占比</th>
                          <th className="px-2 py-1.5 text-right font-medium">户数</th>
                          <th className="px-2 py-1.5 font-medium">报告期</th>
                        </tr>
                      </thead>
                      <tbody>
                        {holdersQuery.data.structure.map((row, index) => (
                          <tr key={index} className="border-t border-line/60">
                            <td className="px-2 py-1.5 text-fg-secondary">
                              {row.merge_scope === 'merged' ? '合并' : '分部门'}
                            </td>
                            <td className="num px-2 py-1.5 text-right">{fmtNum(row.ins_position, 1)}%</td>
                            <td className="num px-2 py-1.5 text-right">{fmtNum(row.psnl_rate, 1)}%</td>
                            <td className="num px-2 py-1.5 text-right text-fg-secondary">
                              {row.holder_amount !== undefined ? Number(row.holder_amount).toLocaleString() : '--'}
                            </td>
                            <td className="num px-2 py-1.5 text-fg-muted">{row.report_date_ms_ymd ?? '--'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {holdersQuery.data.top.length > 0 ? (
                      <div className="mt-2 border-t border-line pt-2">
                        <div className="mb-1 text-2xs text-fg-muted">前十大持有人</div>
                        <div className="flex flex-wrap gap-1">
                          {holdersQuery.data.top.map((row, index) => (
                            <Badge key={index} tone="neutral">
                              {row.holder_name ?? '--'} {fmtNum(row.hold_rate_pct, 2)}%
                            </Badge>
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <EmptyState title="暂无持有人数据" description="半年度报告披露，可能尚未更新。" />
                )}
              </Card>

              {/* 资产配置 + 行业配置 */}
              <Card className="p-0">
                <SectionTitle icon={<Layers size={13} />} title="资产与行业配置" hint="定期报告披露" />
                {assetQuery.isLoading || industryQuery.isLoading ? (
                  <SkeletonRows rows={4} />
                ) : industryRows.length === 0 && assetRows.length === 0 ? (
                  <EmptyState title="暂无配置数据" />
                ) : (
                  <div className="grid grid-cols-1 gap-2 p-3 md:grid-cols-2">
                    {assetRows.length > 0 ? (
                      <div>
                        <div className="mb-1 text-2xs text-fg-muted">资产配置（最近 {assetRows.length} 期，最新在前）</div>
                        <table className="w-full border-collapse text-2xs">
                          <thead>
                            <tr className="border-b border-line text-left text-fg-muted">
                              <th className="py-1 font-medium">期次</th>
                              <th className="py-1 text-right font-medium">股票</th>
                              <th className="py-1 text-right font-medium">债券</th>
                              <th className="py-1 text-right font-medium">存款</th>
                            </tr>
                          </thead>
                          <tbody>
                            {assetRows.map((row, index) => (
                              <tr key={index} className="border-t border-line/60">
                                <td className="num py-1">{index === 0 ? '最新' : `T-${index}`}</td>
                                <td className="num py-1 text-right">{fmtNum(row.stock_ratio_pct, 1)}</td>
                                <td className="num py-1 text-right">{fmtNum(row.bond_ratio_pct, 1)}</td>
                                <td className="num py-1 text-right text-fg-muted">{fmtNum(row.deposit_ratio_pct, 1)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : null}
                    {industryRows.length > 0 ? (
                      <div>
                        <div className="mb-1 text-2xs text-fg-muted">
                          行业配置（{industryRows[0]?.report_period ?? ''}）
                        </div>
                        <div className="space-y-1">
                          {industryRows.slice(0, 8).map((row, index) => {
                            const ratio = numOf(row.ratio_pct) ?? 0
                            return (
                              <div key={index} className="flex items-center gap-2">
                                <span className="w-20 shrink-0 truncate text-2xs text-fg-secondary">
                                  {row.industry_name ?? '--'}
                                </span>
                                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-elevated">
                                  <div
                                    className="h-full rounded-full bg-accent/60"
                                    style={{ width: `${Math.min(100, ratio * 2)}%` }}
                                  />
                                </div>
                                <span className="num w-12 shrink-0 text-right text-2xs text-fg-muted">
                                  {ratio.toFixed(1)}%
                                </span>
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    ) : null}
                  </div>
                )}
              </Card>
            </div>

            {/* 分红记录 */}
            <Card className="p-0">
              <SectionTitle
                icon={<Coins size={13} />}
                title="分红记录"
                hint={
                  dividendsQuery.data?.dividend_count
                    ? `累计 ${dividendsQuery.data.dividend_count} 次（显示最近 ${dividendRows.length} 次）`
                    : undefined
                }
              />
              {dividendsQuery.isLoading ? (
                <SkeletonRows rows={3} />
              ) : dividendsQuery.isError ? (
                <EmptyState title="分红数据加载失败" description={queryErrorOf(dividendsQuery.error)} />
              ) : dividendRows.length === 0 ? (
                <EmptyState title="暂无分红记录" />
              ) : (
                <table className="w-full border-collapse text-xs">
                  <thead>
                    <tr className="border-y border-line text-left text-2xs text-fg-muted">
                      <th className="px-3 py-1.5 font-medium">除息日</th>
                      <th className="px-3 py-1.5 text-right font-medium">每10份分红(税前)</th>
                      <th className="px-3 py-1.5 text-right font-medium">每10份分红(税后)</th>
                      <th className="px-3 py-1.5 font-medium">权益登记日</th>
                      <th className="px-3 py-1.5 font-medium">派息日</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dividendRows.map((row, index) => (
                      <tr key={index} className="border-t border-line/60 hover:bg-elevated/50">
                        <td className="num px-3 py-1.5">{row.ex_dividend_date_ms_ymd ?? '--'}</td>
                        <td className="num px-3 py-1.5 text-right">{fmtNum(row.per_ten_cash_before_tax, 3)}</td>
                        <td className="num px-3 py-1.5 text-right text-fg-secondary">
                          {fmtNum(row.per_ten_cash_after_tax, 3)}
                        </td>
                        <td className="num px-3 py-1.5 text-fg-muted">{row.registration_date_ms_ymd ?? '--'}</td>
                        <td className="num px-3 py-1.5 text-fg-muted">{row.payment_date_ms_ymd ?? '--'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>

            <div className="pb-2 text-center text-2xs text-fg-muted">
              {anyLoading ? '数据加载中…' : '数据来源：扶摇（同花顺金融数据）· 持仓与配置来自定期报告披露'}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
