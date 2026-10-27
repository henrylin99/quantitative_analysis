// 个股风险 7 个 Tab 的共享小工具：时间归一化、数字格式化、请求适配与客户端排序。
// 只做展示层辅助，纯函数为主（请求适配除外）。
import { fetchUsAnalytics } from '../../api/usAnalytics'

export const SQRT252 = Math.sqrt(252)

/** 'YYYY-MM-DD'（或带时刻的字符串）→ unix 秒（当日 00:00 UTC）；数字原样透传。 */
export function toTime(t) {
  if (t == null) return null
  if (typeof t === 'number') return t
  const day = String(t).slice(0, 10)
  const ms = Date.parse(`${day}T00:00:00Z`)
  return Number.isFinite(ms) ? Math.floor(ms / 1000) : null
}

/**
 * 后端序列 [{time, value}] → 图表数据 [{time, value}]。
 * time 统一归一为 unix 秒；value 为 null/NaN/Infinity 的点跳过。
 * 传 key 时从对象字段取值（如 {time, beta} → toLine(s, 'beta')）。
 */
export function toLine(series, key) {
  return (series || [])
    .map((p) => {
      const raw = key == null ? p.value : p[key]
      const v = num(raw)
      const t = toTime(p.time)
      return t != null && v != null ? { time: t, value: v } : null
    })
    .filter(Boolean)
}

/** 对齐给定序列时间轴的恒定参考线（β=1 / Sharpe=0 / z=±2 / 均值线等）。 */
export function flatLine(series, value) {
  return (series || [])
    .map((p) => ({ time: toTime(p.time), value }))
    .filter((p) => p.time != null)
}

// ---------------------------------------------------------------- 格式化 ----

export const num = (v) => (v == null || !Number.isFinite(+v) ? null : +v)
/** 固定小数位 */
export const fmt = (v, digits = 2) => (num(v) == null ? '—' : num(v).toFixed(digits))
/** 带符号（+0.85 / -1.20），无量纲矩、比率类 */
export const signed = (v, digits = 2) => (num(v) == null ? '—' : (v >= 0 ? '+' : '') + v.toFixed(digits))
/** 小数 → 百分数（1 位） */
export const pct1 = (v) => (num(v) == null ? '—' : (v * 100).toFixed(1) + '%')
/** 小数 → 百分数（0 位，分位/占比用） */
export const pct0 = (v) => (num(v) == null ? '—' : (v * 100).toFixed(0) + '%')
/** 回撤深度（后端为正数幅度，0.22 = 22%）显示为负百分数 -22.0% */
export const depthPct = (v) => (num(v) == null ? '—' : '-' + (Math.abs(v) * 100).toFixed(1) + '%')
/** 日波动 → 年化百分数（×√252） */
export const volAnnual = (v) => (num(v) == null ? '—' : (v * SQRT252 * 100).toFixed(1) + '%')
/** 相关系数 3 位（可负，不加 +） */
export const fixed3 = (v) => (num(v) == null ? '—' : v.toFixed(3))
export const days = (v) => (num(v) == null ? '—' : `${Math.round(v)} 日`)
export const yesno = (v) => (v == null ? '—' : v ? '是' : '否')
/** AR(1) 半衰期：无回归 / 极慢 / n 天 */
export const hlLabel = (v) => {
  const x = num(v)
  if (x == null) return '无回归'
  if (x >= 1000) return '>1000天'
  return `${x.toFixed(1)}天`
}
/** Amihud 冲击（每 $1B）：自适应小数位 */
export const il3 = (v) => {
  const x = num(v)
  if (x == null) return '—'
  if (Math.abs(x) >= 1) return x.toFixed(2)
  if (Math.abs(x) >= 0.01) return x.toFixed(3)
  return x.toFixed(4)
}
/** 美元成交额 → $B / $M */
export const dvol = (v) => {
  const x = num(v)
  if (x == null) return '—'
  const b = x / 1e9
  return b >= 1 ? `$${b.toFixed(2)}B` : `$${(x / 1e6).toFixed(0)}M`
}

// ------------------------------------------------------------ 请求适配 ----

// 后端 us-analytics 路由以裸 payload 返回（无 {code,message,data} 信封），
// 标准信封解包在这种响应上会误判失败。先走标准封装，首次失败后记住裸模式
// 并直接 GET /api/us-analytics（两种响应形状都兼容）。
let bareMode = false

export async function riskFetch(path, params) {
  if (!bareMode) {
    try {
      return await fetchUsAnalytics(path, params)
    } catch (err) {
      bareMode = true
    }
  }
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params || {})) {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v))
  }
  const url = `/api/us-analytics${path}${qs.toString() ? `?${qs.toString()}` : ''}`
  const resp = await fetch(url)
  if (!resp.ok) throw new Error(`请求失败（HTTP ${resp.status}）`)
  const json = await resp.json()
  if (json && typeof json === 'object' && json.code === 200 && 'data' in json) return json.data
  return json
}

// ------------------------------------------------------------ 客户端排序 ----

/** 表格客户端排序：字符串按 localeCompare，布尔按 false<true，数值空值垫底。 */
export function sortRows(rows, key, dir) {
  const arr = [...(rows || [])]
  arr.sort((a, b) => {
    const av = a ? a[key] : undefined
    const bv = b ? b[key] : undefined
    if (typeof av === 'string' || typeof bv === 'string') {
      const d = String(av).localeCompare(String(bv))
      return dir === 'asc' ? d : -d
    }
    if (typeof av === 'boolean' || typeof bv === 'boolean') {
      const d = av === bv ? 0 : av ? 1 : -1
      return dir === 'asc' ? d : -d
    }
    const diff = (av ?? -Infinity) - (bv ?? -Infinity)
    return dir === 'asc' ? diff : -diff
  })
  return arr
}

/** 两条 series 按时间对齐相除（如 有效下注数 ÷ 单因子上界 = 聚集比）。 */
export function ratioLine(numSeries, denSeries) {
  const den = new Map((denSeries || []).map((p) => [p.time, num(p.value)]))
  return (numSeries || [])
    .map((p) => {
      const a = num(p.value)
      const b = den.get(toTime(p.time))
      return a != null && b ? { time: toTime(p.time), value: a / b } : null
    })
    .filter(Boolean)
}

/** 序列标准化为均值 0 / 标准差 1（流动性-波动 nexus 叠加用，量纲不同无法直接同图）。 */
export function zScoreLine(series) {
  const vs = (series || []).map((p) => p.value).filter((v) => v != null)
  if (vs.length < 2) return []
  const m = vs.reduce((s, v) => s + v, 0) / vs.length
  const sd = Math.sqrt(vs.reduce((s, v) => s + (v - m) ** 2, 0) / vs.length) || 1
  return series
    .map((p) => (p.value == null ? null : { time: p.time, value: (p.value - m) / sd }))
    .filter(Boolean)
}
