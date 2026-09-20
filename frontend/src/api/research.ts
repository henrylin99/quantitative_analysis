import { apiGet } from './client'

// ================= 研报中心 /api/research（东方财富研报，信封 {code,message,data}） =================

export type ReportCategory = 'industry' | 'stock' | 'strategy' | 'macro' | 'new_stock'

export const REPORT_CATEGORIES: { key: ReportCategory; label: string }[] = [
  { key: 'industry', label: '行业研报' },
  { key: 'stock', label: '个股研报' },
  { key: 'strategy', label: '策略报告' },
  { key: 'macro', label: '宏观研究' },
  { key: 'new_stock', label: '新股研报' },
]

/** 研报条目（后端已归一化；jg 类无 info_code/pdf_url） */
export interface ResearchReport {
  category: ReportCategory
  info_code?: string | null
  encode_url?: string | null
  title: string
  stock_code?: string | null
  stock_name?: string | null
  org_name?: string | null
  publish_date: string | null
  industry_name?: string | null
  rating?: string | null
  researchers?: string | null
  pages?: number | null
  detail_url: string
  pdf_url?: string | null
}

export interface ResearchReportsPayload {
  category: ReportCategory
  category_label?: string
  begin: string
  end: string
  page: number
  size: number
  total: number
  pages: number
  items: ResearchReport[]
  cached?: boolean
  stale?: boolean
}

export interface ResearchReportQuery {
  category: ReportCategory
  /** YYYY-MM-DD（date input 原生格式，后端转 YYYYMMDD） */
  begin?: string
  end?: string
  page?: number
  size?: number
  /** 仅 stock 类别：600519 或 600519.SH 均可 */
  code?: string
}

export function fetchResearchReports(query: ResearchReportQuery) {
  return apiGet<ResearchReportsPayload>('/research/reports', {
    category: query.category,
    begin: query.begin ? query.begin.replace(/-/g, '') : undefined,
    end: query.end ? query.end.replace(/-/g, '') : undefined,
    page: query.page,
    size: query.size,
    code: query.code || undefined,
  })
}

// ================= 研报正文 /api/research/content =================

export interface ReportContentPage {
  page: number
  text: string
}

/** 研报正文（后端下载 PDF + PyMuPDF 提取；策略/宏观由详情页解析出附件链接） */
export interface ReportContent {
  info_code: string
  pdf_url: string
  total_pages: number
  total_chars: number
  /** 图片型（扫描/截图，无文字层），仅可打开 PDF 阅读 */
  image_only: boolean
  /** 超长截断（完整内容请打开 PDF） */
  truncated: boolean
  pages: ReportContentPage[]
}

export function fetchReportContent(query: {
  info_code?: string | null
  category?: ReportCategory
  encode?: string | null
}) {
  // info_code 优先；策略/宏观（列表无 info_code）才走 category+encode
  const params = query.info_code
    ? { info_code: query.info_code }
    : { category: query.category, encode: query.encode || undefined }
  return apiGet<ReportContent>('/research/content', params)
}

/** 6 位东财代码 → ts_code（详情页路由用）：6 开头沪、0/3 开头深、其余北交所 */
export function toTsCode(code?: string | null): string | null {
  if (!code) return null
  const c = code.trim()
  if (!/^\d{6}$/.test(c)) return null
  if (c.startsWith('6')) return `${c}.SH`
  if (c.startsWith('0') || c.startsWith('3')) return `${c}.SZ`
  return `${c}.BJ`
}
