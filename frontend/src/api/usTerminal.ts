/**
 * 美股工作台（K线终端/热力图/备选图表/组合分析）数据适配层。
 *
 * 后端数据源是雅虎财经离线快照（/api/us-stock/*）：日线历史（us_history.parquet，
 * 每票约 500 根）+ 截面快照（us_snapshot.parquet）。这里把后端行结构转换成
 * TradingView 风格前端库需要的 bars（time 为 UTC 秒）。
 */
import { fetchUsStocks, fetchUsStockHistory } from './usStock'
import type { UsStockRow, UsHistoryBar } from './usStock'

export interface TvBar {
  time: number // unix 秒（当日 00:00 UTC）
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface TvMarker {
  time: number
  position: 'aboveBar' | 'belowBar'
  color: string
  shape: 'arrowUp' | 'arrowDown' | 'circle'
  text: string
}

export interface UsSymbolItem {
  symbol: string
  name: string
}

const SEC_PER_DAY = 86400

/** "2024-10-17" → unix 秒（当日 00:00 UTC，保证 % 86400 === 0 使图例显示日期） */
export function dayToTime(day: string): number {
  return Math.floor(Date.parse(`${day}T00:00:00Z`) / 1000)
}

/** 后端历史行 → lightweight-charts bars */
export function toBars(rows: UsHistoryBar[]): TvBar[] {
  const out: TvBar[] = []
  for (const r of rows) {
    const o = Number(r.open)
    const h = Number(r.high)
    const l = Number(r.low)
    const c = Number(r.close)
    if (!Number.isFinite(o) || !Number.isFinite(h) || !Number.isFinite(l) || !Number.isFinite(c)) continue
    out.push({ time: dayToTime(String(r.day)), open: o, high: h, low: l, close: c, volume: Number(r.volume) || 0 })
  }
  return out
}

/** 拉取一只美股的日线 bars（range ∈ 3m/6m/1y/2y，默认 2y ≈ 500 根） */
export async function fetchUsBars(symbol: string, range = '2y'): Promise<TvBar[]> {
  const data = await fetchUsStockHistory(symbol, range)
  return toBars(data.bars || [])
}

/** 全部美股 {symbol, name} 列表（快照截面，≤500 只） */
export async function fetchUsSymbols(): Promise<UsSymbolItem[]> {
  const data = await fetchUsStocks({ limit: 500 })
  return (data.rows || []).map((r) => ({ symbol: r.symbol, name: r.name || r.symbol }))
}

/** 全部美股快照原始行（热力图/基本面面板用，字段为小数比率） */
export async function fetchUsSnapshotRows(): Promise<UsStockRow[]> {
  const data = await fetchUsStocks({ limit: 500 })
  return data.rows || []
}

// 日线形态标志 → 图表箭头标记（后端 history 已带 0/1 形态列，客户端直接映射）
const PATTERN_MARKERS: Array<{ key: string; text: string; up: boolean }> = [
  { key: 'pattern_hammer', text: '锤', up: true },
  { key: 'pattern_shooting_star', text: '星', up: false },
  { key: 'pattern_bullish_engulfing', text: '吞', up: true },
  { key: 'pattern_bearish_engulfing', text: '吞', up: false },
  { key: 'pattern_three_white_soldiers', text: '兵', up: true },
  { key: 'pattern_three_black_crows', text: '鸦', up: false },
  { key: 'pattern_volume_breakout', text: '突', up: true },
]

/** 由日线形态标志生成主图标记（Doji 用圆点） */
export function markersFromBars(rows: UsHistoryBar[]): TvMarker[] {
  const out: TvMarker[] = []
  for (const r of rows) {
    const time = dayToTime(String(r.day))
    for (const m of PATTERN_MARKERS) {
      if (Number(r[m.key]) === 1) {
        out.push({
          time,
          position: m.up ? 'belowBar' : 'aboveBar',
          color: m.up ? '#26a69a' : '#ef5350',
          shape: m.up ? 'arrowUp' : 'arrowDown',
          text: m.text,
        })
      }
    }
    if (Number(r.pattern_doji) === 1) {
      out.push({ time, position: 'aboveBar', color: '#9aa6b2', shape: 'circle', text: '十' })
    }
  }
  return out
}

/** 日线 → 周线（按 ISO 周， OHLCV 聚合，时间取本周最后一根交易日） */
export function toWeekly(bars: TvBar[]): TvBar[] {
  const out: TvBar[] = []
  let cur: TvBar | null = null
  let curKey: string | null = null
  const keyOf = (t: number) => {
    const d = new Date(t * 1000)
    const dow = (d.getUTCDay() + 6) % 7 // 周一=0
    const monday = new Date(d)
    monday.setUTCDate(d.getUTCDate() - dow)
    return monday.toISOString().slice(0, 10)
  }
  for (const b of bars) {
    const k = keyOf(b.time)
    if (!cur || k !== curKey) {
      if (cur) out.push(cur)
      cur = { ...b }
      curKey = k
    } else {
      cur.high = Math.max(cur.high, b.high)
      cur.low = Math.min(cur.low, b.low)
      cur.close = b.close
      cur.volume = (cur.volume || 0) + (b.volume || 0)
    }
  }
  if (cur) out.push(cur)
  return out
}

export { SEC_PER_DAY }
