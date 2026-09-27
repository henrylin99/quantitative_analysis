import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { List, Search, Wallet } from 'lucide-react'
import {
  FUND_ASSET_TYPE_LABELS,
  fetchFundSearch,
  type FundAssetType,
} from '../api/funds'
import { Badge, Card, EmptyState, PageHeader, SectionTitle, SkeletonRows } from '../components/ui'
import { cn } from '../lib/cn'

/** 默认视图：自动检索一次「ETF」展示 15 只场内基金，无需用户先输入 */
const DEFAULT_QUERY = 'ETF'
const DEFAULT_FILTER: AssetFilterKey = 'fund-etf'

/** 常用基金快捷入口（点击直达基金中心详情页） */
const PRESETS = [
  { code: '510300.SH', label: '沪深300ETF' },
  { code: '510500.SH', label: '中证500ETF' },
  { code: '512880.SH', label: '券商ETF' },
  { code: '513100.SH', label: '纳指ETF' },
  { code: '159915.SZ', label: '创业板ETF' },
  { code: '161725.SZ', label: '白酒LOF' },
] as const

const ASSET_FILTERS = [
  { key: '', label: '全部' },
  { key: 'fund-etf', label: 'ETF' },
  { key: 'fund-lof', label: 'LOF' },
  { key: 'fund-otc', label: '场外' },
] as const

type AssetFilterKey = (typeof ASSET_FILTERS)[number]['key']

export default function FundsListPage() {
  const [query, setQuery] = useState('')
  const [submitted, setSubmitted] = useState(DEFAULT_QUERY)
  const [assetFilter, setAssetFilter] = useState<AssetFilterKey>(DEFAULT_FILTER)

  // 默认视图固定 15 只；用户主动检索后放宽到 30
  const isDefaultView = submitted === DEFAULT_QUERY && assetFilter === DEFAULT_FILTER
  const limit = isDefaultView ? 15 : 30

  const searchQuery = useQuery({
    queryKey: ['fund', 'search', submitted, assetFilter, limit],
    queryFn: () =>
      fetchFundSearch(
        submitted,
        (assetFilter || undefined) as FundAssetType | undefined,
        limit,
      ),
    enabled: submitted.length > 0,
  })

  const items = searchQuery.data?.items ?? []

  return (
    <div className="tsp-root min-h-full">
      <PageHeader
        title="基金列表"
        subtitle="扶摇同花顺基金检索 · 默认展示 15 只场内 ETF · 点击基金代码或名称进入基金中心"
        right={
          <form
            className="flex items-center gap-1"
            onSubmit={(event) => {
              event.preventDefault()
              const next = query.trim()
              setSubmitted(next || DEFAULT_QUERY)
            }}
          >
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="基金名称或代码"
              className="num rounded-input border border-line bg-elevated/50 px-2 py-1 text-xs outline-none focus:border-accent/60"
              style={{ width: 150 }}
            />
            <button
              type="submit"
              className="rounded-btn border border-line px-2 py-1 text-xs text-fg-secondary hover:bg-elevated"
              title="搜索"
            >
              <Search size={13} />
            </button>
          </form>
        }
      />

      <div className="space-y-1.5 p-1.5">
        {/* 快捷入口 */}
        <Card className="p-3">
          <div className="mb-2 flex items-center gap-1 text-2xs text-fg-muted">
            <Wallet size={12} /> 常用基金
          </div>
          <div className="flex flex-wrap gap-1">
            {PRESETS.map((preset) => (
              <Link
                key={preset.code}
                to={`/fund/${preset.code}`}
                className="rounded-btn border border-line px-2.5 py-1 text-xs text-fg-secondary transition-colors hover:bg-elevated hover:text-accent"
              >
                {preset.label} <span className="num text-fg-muted">{preset.code}</span>
              </Link>
            ))}
          </div>
        </Card>

        {/* 检索结果 */}
        <Card className="p-0">
          <SectionTitle
            icon={<List size={13} />}
            title={isDefaultView ? '默认列表' : `检索：${submitted}`}
            hint="支持名称/代码模糊匹配；场外基金（.OF）无场内行情"
            right={
              <div className="flex items-center gap-1">
                {ASSET_FILTERS.map((filter) => (
                  <button
                    key={filter.key}
                    type="button"
                    onClick={() => setAssetFilter(filter.key)}
                    className={cn(
                      'rounded-btn px-2 py-0.5 text-xs transition-colors',
                      assetFilter === filter.key
                        ? 'bg-accent/15 text-accent'
                        : 'text-fg-muted hover:bg-elevated hover:text-fg-secondary',
                    )}
                  >
                    {filter.label}
                  </button>
                ))}
              </div>
            }
          />

          {!submitted ? (
            <EmptyState
              icon={<Search size={22} />}
              title="输入基金名称或代码开始检索"
              description="如「沪深300」「白酒」「510300」「天弘」，或直接点击上方常用基金。"
            />
          ) : searchQuery.isLoading ? (
            <SkeletonRows rows={8} />
          ) : searchQuery.isError ? (
            <EmptyState
              title="检索失败"
              description={(searchQuery.error as Error)?.message}
              action={
                <button
                  type="button"
                  className="rounded-btn border border-line px-2.5 py-1 text-xs text-fg-secondary hover:bg-elevated"
                  onClick={() => searchQuery.refetch()}
                >
                  重试
                </button>
              }
            />
          ) : items.length === 0 ? (
            <EmptyState
              title="没有匹配的基金"
              description={`未找到与「${submitted}」匹配的基金，可尝试更换关键词或放宽类型筛选。`}
            />
          ) : (
            <table className="w-full border-collapse text-xs">
              <thead>
                <tr className="border-b border-line text-left text-2xs text-fg-muted">
                  <th className="px-3 py-1.5 font-medium">代码</th>
                  <th className="px-3 py-1.5 font-medium">名称</th>
                  <th className="px-3 py-1.5 font-medium">类型</th>
                  <th className="px-3 py-1.5 font-medium">交易所</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => (
                  <tr key={row.thscode} className="border-t border-line/60 hover:bg-elevated/50">
                    <td className="px-3 py-1.5">
                      <Link
                        to={`/fund/${encodeURIComponent(row.thscode)}`}
                        title={`进入 ${row.name ?? row.thscode} 详情`}
                        className="num text-accent hover:underline"
                      >
                        {row.thscode}
                      </Link>
                    </td>
                    <td className="px-3 py-1.5">
                      <Link
                        to={`/fund/${encodeURIComponent(row.thscode)}`}
                        className="text-fg-secondary transition-colors hover:text-accent"
                      >
                        {row.name ?? '--'}
                      </Link>
                    </td>
                    <td className="px-3 py-1.5">
                      <Badge
                        tone={
                          row.asset_type === 'fund-etf'
                            ? 'accent'
                            : row.asset_type === 'fund-lof'
                              ? 'neutral'
                              : 'neutral'
                        }
                      >
                        {FUND_ASSET_TYPE_LABELS[row.asset_type ?? ''] ?? row.asset_type ?? '--'}
                      </Badge>
                    </td>
                    <td className="px-3 py-1.5 text-fg-muted">{row.exchange ?? '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>
    </div>
  )
}
