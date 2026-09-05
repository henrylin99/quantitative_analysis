import { useQuery } from '@tanstack/react-query'
import { CircleCheck, CircleX, Database, KeyRound, RefreshCw } from 'lucide-react'
import { fetchSourceStatus, type SourceStatus } from '../api/market'
import { Badge, Card, PageHeader, SectionTitle, SkeletonRows } from '../components/ui'
import { cn } from '../lib/cn'

interface SourceMeta {
  key: keyof Omit<SourceStatus, 'checked_at'>
  name: string
  description: string
  roles: string[]
}

const SOURCES: SourceMeta[] = [
  {
    key: 'tushare',
    name: 'Tushare',
    description: '历史估值、技术因子、资金流、筹码分布等日频数据的既有主干源。',
    roles: ['daily_basic', 'stk_factor', 'moneyflow', 'cyq_perf', 'trade_calendar', '股票元数据'],
  },
  {
    key: 'fuyao',
    name: '扶摇（同花顺）',
    description: '全市场日K dump、实时快照、财务三表、龙虎榜与竞价风向标；免费 key 可用。',
    roles: ['daily_history（可选）', 'financial（可选）', '实时行情', '龙虎榜/风向标'],
  },
  {
    key: 'tickflow',
    name: 'TickFlow',
    description: 'free 档仅支持单标的日K与少量实时行情（约 5rpm），定位为校验兜底源，勿用于批量任务。',
    roles: ['校验兜底'],
  },
]

function StatusBadge({ status }: { status: SourceStatus['fuyao'] & Partial<SourceStatus['tickflow']> }) {
  if ('tier' in status && status.configured) {
    if (status.tier === 'paid') return <Badge tone="accent">付费档</Badge>
    if (status.tier === 'free') return <Badge tone="warning">免费档</Badge>
  }
  if (status.configured) {
    if ('ok' in status) {
      return status.ok ? (
        <Badge tone="bull">
          <CircleCheck size={10} /> 可用
        </Badge>
      ) : (
        <Badge tone="danger">
          <CircleX size={10} /> 异常
        </Badge>
      )
    }
    return (
      <Badge tone="bull">
        <CircleCheck size={10} /> 已配置
      </Badge>
    )
  }
  return <Badge tone="neutral">未配置</Badge>
}

export default function DataSourceCenterPage() {
  const statusQuery = useQuery({
    queryKey: ['datasources', 'status'],
    queryFn: () => fetchSourceStatus(),
    refetchInterval: 300_000,
  })
  const status = statusQuery.data

  return (
    <div className="tsp-root min-h-full">
      <PageHeader
        title="数据源中心"
        subtitle="三个数据源的配置状态与健康探测 · 与数据管理页（任务执行）互补"
        right={
          <button
            type="button"
            onClick={() => statusQuery.refetch()}
            className="inline-flex items-center gap-1.5 rounded-btn border border-line px-2.5 py-1 text-xs text-fg-secondary transition-colors hover:bg-elevated hover:text-fg-primary"
          >
            <RefreshCw size={12} className={statusQuery.isFetching ? 'animate-spin' : ''} /> 重新探测
          </button>
        }
      />

      <div className="space-y-1.5 p-1.5">
        <div className="grid grid-cols-1 gap-1.5 lg:grid-cols-3">
          {SOURCES.map((source) => {
            const sourceStatus = status?.[source.key]
            return (
              <Card key={source.key} className="p-0">
                <SectionTitle
                  icon={<Database size={13} />}
                  title={source.name}
                  right={
                    sourceStatus ? (
                      <StatusBadge status={sourceStatus as SourceStatus['fuyao']} />
                    ) : (
                      <span className="text-2xs text-fg-muted">探测中…</span>
                    )
                  }
                />
                <div className="space-y-2 px-3 pb-3">
                  <p className="text-xs leading-5 text-fg-secondary">{source.description}</p>
                  <div className="flex flex-wrap gap-1">
                    {source.roles.map((role) => (
                      <span key={role} className="rounded-full border border-line bg-elevated/60 px-1.5 py-px text-2xs text-fg-secondary">
                        {role}
                      </span>
                    ))}
                  </div>
                  {'error' in (sourceStatus ?? {}) && (sourceStatus as SourceStatus['fuyao']).error ? (
                    <div className="rounded-input border border-danger/25 bg-danger/8 px-2 py-1.5 text-2xs leading-4 text-danger">
                      {(sourceStatus as SourceStatus['fuyao']).error}
                    </div>
                  ) : null}
                </div>
              </Card>
            )
          })}
        </div>

        <Card className="p-0">
          <SectionTitle
            icon={<KeyRound size={13} />}
            title="数据集 → 生产者"
            hint="同一张 Parquet 表可有多个可选生产者"
          />
          {statusQuery.isLoading ? (
            <SkeletonRows rows={5} />
          ) : (
            <table className="w-full border-collapse text-xs">
              <thead>
                <tr className="border-b border-line text-left text-2xs text-fg-muted">
                  <th className="px-3 py-1.5 font-medium">数据集</th>
                  <th className="px-3 py-1.5 font-medium">可用生产者</th>
                  <th className="px-3 py-1.5 font-medium">说明</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ['日线行情 daily_history', 'tushare / fuyao', '扶摇走全市场 dump，适合初始化与快速回补'],
                  ['财务三表', 'tushare(VIP) / fuyao', '两源按报告期合并共存，互不覆盖'],
                  ['股票清单 stock_basic', 'tushare / fuyao', '行业与退市股元数据以 tushare 为准'],
                  ['日线指标 daily_basic', 'tushare', '扶摇估值仅有当日快照，无历史'],
                  ['技术因子 / 资金流 / 筹码', 'tushare', '扶摇与 TickFlow 不提供'],
                  ['实时行情 / 龙虎榜 / 风向标', 'fuyao', '免费 key 即可用'],
                ].map(([dataset, producers, note]) => (
                  <tr key={dataset} className={cn('border-t border-line/60 hover:bg-elevated/50')}>
                    <td className="px-3 py-1.5">{dataset}</td>
                    <td className="px-3 py-1.5 text-fg-secondary">{producers}</td>
                    <td className="px-3 py-1.5 text-fg-muted">{note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card className="px-3 py-2 text-2xs leading-5 text-fg-muted">
          凭证通过项目根目录 .env 管理：TUSHARE_TOKEN / FUYAO_API_KEY / TICKFLOW_API_KEY，互不影响；
          任一数据源不可用不影响其余数据源的下载作业。
        </Card>
      </div>
    </div>
  )
}
