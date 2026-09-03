import type { DailyBar, FactorRow } from '../api/types'

export type ChartPoint = { time: string }

/** 后端历史/因子数组为 trade_date 倒序（最新在前），图表消费前统一转升序（与旧版 localeCompare 归一化一致） */
export function sortByTradeDateAsc<T extends { trade_date: string }>(rows: T[]): T[] {
  return [...rows].sort((a, b) => String(a.trade_date).localeCompare(String(b.trade_date)))
}

/** trade_date 前 10 位作为对齐键（'YYYY-MM-DD'） */
export function dateKey(tradeDate: unknown): string {
  return String(tradeDate ?? '').slice(0, 10)
}

/** 十字光标回调里的 time 可能是 BusinessDay 对象，转回 'YYYY-MM-DD' 字符串 */
export function timeKey(time: unknown): string {
  if (typeof time === 'string') return time.slice(0, 10)
  const bd = time as { year?: number; month?: number; day?: number } | null
  if (bd && typeof bd.year === 'number' && typeof bd.month === 'number' && typeof bd.day === 'number') {
    return `${bd.year}-${String(bd.month).padStart(2, '0')}-${String(bd.day).padStart(2, '0')}`
  }
  return String(time ?? '')
}

function hasValue(v: number | null | undefined): v is number {
  return v !== null && v !== undefined && !Number.isNaN(v)
}

/** 折线点位：空值输出 whitespace 点 {time}（不补 0），按日期键去重。内部强制升序（对应旧版 getChronological 归一化契约） */
export function toLinePoints<T>(
  rows: T[],
  pick: (row: T) => number | null | undefined,
): (ChartPoint & { value: number })[] {
  const sorted = sortByTradeDateAsc(rows as (T & { trade_date: string })[])
  const out: (ChartPoint & { value: number })[] = []
  const seen = new Set<string>()
  for (const row of sorted) {
    const time = dateKey((row as { trade_date?: unknown }).trade_date)
    if (!time || seen.has(time)) continue
    seen.add(time)
    const value = pick(row)
    if (hasValue(value)) out.push({ time, value })
  }
  return out
}

export interface CandleBar {
  time: string
  open: number
  high: number
  low: number
  close: number
  vol: number | null
  pct_chg: number | null
}

export function toCandleBars(rows: DailyBar[]): CandleBar[] {
  const out: CandleBar[] = []
  const seen = new Set<string>()
  for (const row of sortByTradeDateAsc(rows)) {
    const time = dateKey(row.trade_date)
    if (!time || seen.has(time)) continue
    if (!hasValue(row.open) || !hasValue(row.high) || !hasValue(row.low) || !hasValue(row.close)) continue
    seen.add(time)
    out.push({
      time,
      open: row.open,
      high: row.high,
      low: row.low,
      close: row.close,
      vol: hasValue(row.vol) ? row.vol : null,
      pct_chg: hasValue(row.pct_chg) ? row.pct_chg : null,
    })
  }
  return out
}

export interface VolumeBar {
  time: string
  value: number
  color: string
}

/** 成交量柱：涨跌着色（A股红涨绿跌），颜色随主题传入 */
export function toVolumeBars(rows: DailyBar[], upColor: string, downColor: string): VolumeBar[] {
  const out: VolumeBar[] = []
  const seen = new Set<string>()
  for (const row of sortByTradeDateAsc(rows)) {
    const time = dateKey(row.trade_date)
    if (!time || seen.has(time)) continue
    seen.add(time)
    const vol = hasValue(row.vol) ? row.vol : 0
    const pct = hasValue(row.pct_chg) ? row.pct_chg : null
    out.push({
      time,
      value: vol,
      color: pct !== null && pct < 0 ? downColor : upColor,
    })
  }
  return out
}

/** 因子按日期键建 Map，供 BOLL 等按 history 时间轴对齐 */
export function buildFactorMap(rows: FactorRow[]): Map<string, FactorRow> {
  const map = new Map<string, FactorRow>()
  for (const row of rows) {
    const key = dateKey(row.trade_date)
    if (key && !map.has(key)) map.set(key, row)
  }
  return map
}

export function lastValueOf<T>(rows: T[], pick: (row: T) => number | null | undefined): number | null {
  for (let i = rows.length - 1; i >= 0; i--) {
    const v = pick(rows[i])
    if (hasValue(v)) return v
  }
  return null
}
