import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import {
  BookOpen,
  ChevronLeft,
  ChevronRight,
  FileText,
  RefreshCw,
  Search,
} from 'lucide-react'
import {
  REPORT_CATEGORIES,
  fetchReportContent,
  fetchResearchReports,
  toTsCode,
  type ReportCategory,
  type ResearchReport,
} from '../api/research'
import { StockLink } from '../components/stock/StockLink'
import { Badge, Card, EmptyState, Modal, PageHeader, SkeletonRows } from '../components/ui'
import { cn } from '../lib/cn'

const PAGE_SIZE = 20

function defaultBegin(): string {
  return new Date(Date.now() - 90 * 86_400_000).toISOString().slice(0, 10)
}

function ratingTone(rating?: string | null): 'bull' | 'bear' | 'neutral' {
  if (!rating) return 'neutral'
  if (/买入|增持|推荐|强于/.test(rating)) return 'bull'
  if (/卖出|减持|回避/.test(rating)) return 'bear'
  return 'neutral'
}

const dateInputClass =
  'num rounded-input border border-line bg-elevated/50 px-2 py-1 text-xs outline-none focus:border-accent/60'

export default function ResearchReportsPage() {
  const [category, setCategory] = useState<ReportCategory>('industry')
  const [begin, setBegin] = useState(defaultBegin)
  const [end, setEnd] = useState(() => new Date().toISOString().slice(0, 10))
  const [page, setPage] = useState(1)
  const [codeInput, setCodeInput] = useState('')
  const [appliedCode, setAppliedCode] = useState('')
  const [reading, setReading] = useState<ResearchReport | null>(null)

  const query = useQuery({
    queryKey: ['research', 'reports', category, begin, end, page, appliedCode],
    queryFn: () =>
      fetchResearchReports({
        category,
        begin,
        end,
        page,
        size: PAGE_SIZE,
        code: category === 'stock' ? appliedCode : undefined,
      }),
    // 个股类别必须等代码提交后才发请求，否则后端必然 400
    enabled: category !== 'stock' || appliedCode.trim().length > 0,
    placeholderData: keepPreviousData,
  })

  // 研报正文：打开弹窗才拉取；PDF 内容发布后不变，缓存后不再重取
  const contentQuery = useQuery({
    queryKey: [
      'research',
      'content',
      reading?.info_code ?? `${reading?.category}:${reading?.encode_url}`,
    ],
    queryFn: () =>
      fetchReportContent({
        info_code: reading?.info_code,
        category: reading?.category,
        encode: reading?.encode_url,
      }),
    enabled: reading !== null,
    staleTime: Infinity,
  })

  const payload = query.data
  const items = payload?.items ?? []
  // 个股类别未提交代码：不发请求（enabled 门控），也不回供上一类别的占位数据
  const awaitingCode = category === 'stock' && appliedCode.trim().length === 0
  const totalPages =
    payload && payload.pages > 0
      ? payload.pages
      : Math.max(1, Math.ceil((payload?.total ?? 0) / PAGE_SIZE))

  const pickCategory = (key: ReportCategory) => {
    setCategory(key)
    setPage(1)
  }
  const shiftPage = (delta: number) => {
    setPage((current) => Math.min(totalPages, Math.max(1, current + delta)))
  }

  return (
    <div className="tsp-root min-h-full">
      <PageHeader
        title="研报中心"
        subtitle={
          payload && !awaitingCode
            ? `东方财富研报 · ${payload.begin} ~ ${payload.end} · 共 ${payload.total} 篇 · 10 分钟缓存`
            : '东方财富研报 · 行业 / 个股 / 策略 / 宏观 / 新股 · 10 分钟缓存'
        }
        right={
          <button
            type="button"
            onClick={() => query.refetch()}
            className="inline-flex items-center gap-1.5 rounded-btn border border-line px-2.5 py-1 text-xs text-fg-secondary transition-colors hover:bg-elevated hover:text-fg-primary"
          >
            <RefreshCw size={12} className={query.isFetching ? 'animate-spin' : ''} /> 刷新
          </button>
        }
      />

      {/* 筛选栏：类别 Tab + 日期区间 + 个股代码 */}
      <div className="flex flex-wrap items-center gap-2 p-1.5 pb-0">
        <div className="flex items-center gap-1">
          {REPORT_CATEGORIES.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => pickCategory(item.key)}
              className={cn(
                'rounded-btn px-2 py-0.5 text-xs transition-colors',
                category === item.key
                  ? 'bg-accent/15 text-accent'
                  : 'text-fg-muted hover:bg-elevated hover:text-fg-secondary',
              )}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1.5">
          <input
            type="date"
            value={begin}
            max={end}
            onChange={(event) => {
              setBegin(event.target.value)
              setPage(1)
            }}
            className={dateInputClass}
          />
          <span className="text-2xs text-fg-muted">至</span>
          <input
            type="date"
            value={end}
            min={begin}
            max={new Date().toISOString().slice(0, 10)}
            onChange={(event) => {
              setEnd(event.target.value)
              setPage(1)
            }}
            className={dateInputClass}
          />
        </div>
        {category === 'stock' ? (
          <form
            className="flex items-center gap-1"
            onSubmit={(event) => {
              event.preventDefault()
              setAppliedCode(codeInput.trim())
              setPage(1)
            }}
          >
            <input
              value={codeInput}
              onChange={(event) => setCodeInput(event.target.value)}
              placeholder="股票代码，如 600519"
              className={cn(dateInputClass, 'w-44 placeholder:text-fg-muted/60')}
            />
            <button
              type="submit"
              className="inline-flex items-center gap-1 rounded-btn border border-line px-2 py-1 text-xs text-fg-secondary transition-colors hover:bg-elevated hover:text-fg-primary"
            >
              <Search size={12} /> 查询
            </button>
          </form>
        ) : null}
      </div>

      {query.isError ? (
        <div className="p-1.5">
          <Card className="border-danger/30 bg-danger/5 px-4 py-3 text-xs text-danger">
            研报加载失败：{(query.error as Error)?.message ?? '未知错误'}
            <button type="button" className="ml-2 underline" onClick={() => query.refetch()}>
              重试
            </button>
          </Card>
        </div>
      ) : null}

      <div className="p-1.5">
        <Card className="p-0">
          {query.isLoading && !awaitingCode ? (
            <SkeletonRows rows={12} />
          ) : awaitingCode || items.length === 0 ? (
            <EmptyState
              icon={<FileText size={22} />}
              title="暂无研报"
              description={
                awaitingCode
                  ? '输入 6 位股票代码查询该个股的研报。'
                  : '所选类别与日期区间内没有研报，可放宽区间后重试。'
              }
            />
          ) : (
            <>
              <table className="w-full border-collapse text-xs">
                <thead>
                  <tr className="border-b border-line text-left text-2xs text-fg-muted">
                    <th className="w-24 px-3 py-1.5 font-medium">发布日期</th>
                    <th className="px-3 py-1.5 font-medium">标题</th>
                    <th className="w-36 px-3 py-1.5 font-medium">个股</th>
                    <th className="w-24 px-3 py-1.5 font-medium">机构</th>
                    <th className="w-24 px-3 py-1.5 font-medium">行业</th>
                    <th className="w-16 px-3 py-1.5 font-medium">评级</th>
                    <th className="w-36 px-3 py-1.5 font-medium">研究员</th>
                    <th className="w-12 px-3 py-1.5 text-center font-medium">正文</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((row, index) => {
                    const tsCode = toTsCode(row.stock_code)
                    return (
                      <tr
                        key={`${row.info_code ?? row.encode_url ?? index}-${index}`}
                        className="border-t border-line/60 hover:bg-elevated/50"
                      >
                        <td className="num whitespace-nowrap px-3 py-1.5 text-fg-muted">
                          {row.publish_date ?? '--'}
                        </td>
                        <td className="max-w-[28rem] px-3 py-1.5">
                          <div className="flex items-start gap-1.5">
                            <a
                              href={row.detail_url}
                              target="_blank"
                              rel="noreferrer"
                              title={row.title}
                              className="line-clamp-1 min-w-0 flex-1 text-fg-primary transition-colors hover:text-accent"
                            >
                              {row.title || '--'}
                            </a>
                            {row.pdf_url ? (
                              <a
                                href={row.pdf_url}
                                target="_blank"
                                rel="noreferrer"
                                title="打开 PDF 原文"
                                className="mt-px shrink-0 text-fg-muted transition-colors hover:text-accent"
                              >
                                <FileText size={11} />
                              </a>
                            ) : null}
                          </div>
                        </td>
                        <td className="px-3 py-1.5">
                          {tsCode ? (
                            <StockLink code={tsCode} name={row.stock_name} />
                          ) : (
                            <span className="text-fg-muted">--</span>
                          )}
                        </td>
                        <td className="truncate px-3 py-1.5 text-fg-secondary">{row.org_name ?? '--'}</td>
                        <td className="truncate px-3 py-1.5 text-fg-secondary">
                          {row.industry_name ?? '--'}
                        </td>
                        <td className="px-3 py-1.5">
                          {row.rating ? (
                            <Badge tone={ratingTone(row.rating)} className="whitespace-nowrap">
                              {row.rating}
                            </Badge>
                          ) : (
                            <span className="text-fg-muted">--</span>
                          )}
                        </td>
                        <td className="truncate px-3 py-1.5 text-fg-muted">{row.researchers ?? '--'}</td>
                        <td className="px-3 py-1.5 text-center">
                          <button
                            type="button"
                            title="查看研报正文"
                            onClick={() => setReading(row)}
                            className="rounded-btn p-1 text-fg-muted transition-colors hover:bg-elevated hover:text-accent"
                          >
                            <BookOpen size={13} />
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              <div className="flex items-center justify-between border-t border-line px-3 py-2">
                <span className="num text-2xs text-fg-muted">
                  第 {payload?.page ?? 1} / {totalPages} 页 · 共 {payload?.total ?? 0} 篇
                  {payload?.stale ? ' · 数据为过期缓存' : ''}
                </span>
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    disabled={(payload?.page ?? 1) <= 1}
                    onClick={() => shiftPage(-1)}
                    className="inline-flex items-center gap-0.5 rounded-btn border border-line px-2 py-1 text-xs text-fg-secondary transition-colors hover:bg-elevated disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <ChevronLeft size={12} /> 上一页
                  </button>
                  <button
                    type="button"
                    disabled={(payload?.page ?? 1) >= totalPages}
                    onClick={() => shiftPage(1)}
                    className="inline-flex items-center gap-0.5 rounded-btn border border-line px-2 py-1 text-xs text-fg-secondary transition-colors hover:bg-elevated disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    下一页 <ChevronRight size={12} />
                  </button>
                </div>
              </div>
            </>
          )}
        </Card>
      </div>

      {/* 研报正文弹窗 */}
      <Modal
        open={reading !== null}
        onClose={() => setReading(null)}
        title={<span className="line-clamp-1 pr-2">{reading?.title ?? '研报正文'}</span>}
        width="max-w-3xl"
      >
        {reading ? (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2 text-2xs text-fg-muted">
              <span className="num">{reading.publish_date ?? '--'}</span>
              <span>{reading.org_name ?? ''}</span>
              {reading.rating ? <Badge tone={ratingTone(reading.rating)}>{reading.rating}</Badge> : null}
              {reading.industry_name ? <Badge>{reading.industry_name}</Badge> : null}
              <span className="flex-1" />
              <a
                href={reading.detail_url}
                target="_blank"
                rel="noreferrer"
                className="underline-offset-2 transition-colors hover:text-accent hover:underline"
              >
                东财原页
              </a>
              <a
                href={contentQuery.data?.pdf_url ?? reading.pdf_url ?? undefined}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 underline-offset-2 transition-colors hover:text-accent hover:underline"
              >
                <FileText size={11} /> PDF 原文
              </a>
            </div>

            {contentQuery.isLoading ? (
              <SkeletonRows rows={12} />
            ) : contentQuery.isError ? (
              <Card className="border-danger/30 bg-danger/5 px-4 py-3 text-xs text-danger">
                正文提取失败：{(contentQuery.error as Error)?.message ?? '未知错误'}
                <button type="button" className="ml-2 underline" onClick={() => contentQuery.refetch()}>
                  重试
                </button>
              </Card>
            ) : contentQuery.data?.image_only ? (
              <EmptyState
                icon={<FileText size={22} />}
                title="该研报为图片型（扫描版）"
                description="没有可提取的文字层，请打开 PDF 原文阅读。"
              />
            ) : (
              <div className="space-y-4">
                {contentQuery.data?.pages.map((pg) => (
                  <section key={pg.page}>
                    {contentQuery.data && contentQuery.data.total_pages > 3 ? (
                      <div className="mb-1.5 border-b border-line/60 pb-1 text-right text-2xs text-fg-muted">
                        第 {pg.page} 页
                      </div>
                    ) : null}
                    {pg.text
                      .split('\n')
                      .filter((line) => line.trim())
                      .map((line, i) => (
                        <p key={i} className="text-xs leading-relaxed text-fg-secondary">
                          {line}
                        </p>
                      ))}
                  </section>
                ))}
                {contentQuery.data ? (
                  <div className="num border-t border-line pt-2 text-2xs text-fg-muted">
                    共 {contentQuery.data.total_pages} 页 · 约 {contentQuery.data.total_chars} 字
                    {contentQuery.data.truncated ? ' · 内容过长已截断，完整请看 PDF 原文' : ''}
                  </div>
                ) : null}
              </div>
            )}
          </div>
        ) : null}
      </Modal>
    </div>
  )
}
