/** 数字格式化：千分位 + 固定小数位，空值显示 -- */
export function formatNumber(value: number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '--'
  return value.toLocaleString('zh-CN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

/** 百分比格式化（输入已是百分数值，如 2.35 表示 +2.35%）：带符号两位小数 */
export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '--'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}%`
}

/** 涨跌值红涨绿跌 class（A股口径：正=红） */
export function pctClass(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value) || value === 0) return ''
  return value > 0 ? 'text-up' : 'text-down'
}

/** 本地日期 YYYY-MM-DD */
export function toLocalDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** 金额自适应：≥1亿 显示「x.xx亿」、≥1万 显示「x.xx万」，否则两位小数（输入为万口径原值时不换算） */
export function formatAmount(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '--'
  const abs = Math.abs(value)
  if (abs >= 1e8) return `${(value / 1e8).toFixed(2)}亿`
  if (abs >= 1e4) return `${(value / 1e4).toFixed(2)}万`
  return value.toFixed(2)
}

/** YYYYMMDD → YYYY-MM-DD（已是标准格式则原样返回） */
export function formatTradeDate(value: string | null | undefined): string {
  if (!value) return '--'
  const s = String(value)
  return /^\d{8}$/.test(s) ? `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}` : s
}

/** 时间戳/ISO 字符串 → YYYY-MM-DD HH:mm:ss */
export function formatDateTime(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '--'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

/** CSV 下载（带 BOM，Excel 兼容） */
export function downloadCsv(filename: string, headers: string[], rows: (string | number | null | undefined)[][]) {
  const escape = (v: string | number | null | undefined) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const csv = '\uFEFF' + headers.join(',') + '\n' + rows.map((r) => r.map(escape).join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
