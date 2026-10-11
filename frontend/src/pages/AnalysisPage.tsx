import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { LineStyle } from 'lightweight-charts'
import { fetchStockHistory, fetchStockInfo } from '../api/stocks'
import {
  addWatchlistItem,
  fetchWatchlist,
  removeWatchlistItem,
  type WatchlistItem,
} from '../api/market'
import type { DailyBar, StockBasic } from '../api/types'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import CandleChart, { DOWN_COLOR, UP_COLOR } from '../charts/candle/CandleChart'
import {
  adx,
  atr,
  bollinger,
  candlePatterns,
  cci,
  divergence,
  donchian,
  ema,
  fibExtension,
  fibLevels,
  heikinAshi,
  ichimoku,
  mfi,
  macd,
  pivotLevels,
  priceCross,
  psar,
  rsi,
  sma,
  stochastic,
  superTrend,
  vwap,
} from '../charts/candle/indicators'

/** 输入规范化：转大写；6 位纯数字按首位补后缀（0/3→.SZ，6→.SH） */
function normalizeStockCode(raw: string): string {
  const value = raw.trim().toUpperCase()
  if (/^[0-9]{6}$/.test(value)) {
    const suffix = value.startsWith('0') || value.startsWith('3') ? '.SZ' : value.startsWith('6') ? '.SH' : ''
    return value + suffix
  }
  return value
}

/** 图表 bar：time 为 UTC 秒（lightweight-charts UTCTimestamp） */
interface KBar {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

const STOCK_CODE_RE = /^[0-9]{6}\.(SZ|SH)$/

const TFS = [
  { key: 'daily', label: '日线' },
  { key: 'weekly', label: '周线' },
]

const CHART_TYPES = [
  { key: 'candle', label: 'K线' },
  { key: 'bar', label: '柱状' },
  { key: 'line', label: '线形' },
  { key: 'area', label: '面积' },
]

// 可见区间预设（交易根数；null = 全部）
const RANGES = [
  { key: '3m', label: '3月', bars: 63 },
  { key: '6m', label: '6月', bars: 126 },
  { key: '1y', label: '1年', bars: 252 },
  { key: 'all', label: '全部', bars: null },
]

// 技术信号雷达强度 → 文案 / 颜色（A股红涨绿跌）
const ratingLabel = (s: number) => (s > 0.4 ? '强烈看涨' : s > 0.1 ? '看涨' : s < -0.4 ? '强烈看跌' : s < -0.1 ? '看跌' : '中性')
const ratingColor = (s: number) => (s > 0.1 ? UP_COLOR : s < -0.1 ? DOWN_COLOR : '#9aa6b2')

const MA_COLORS = ['#ffd166', '#4f93e7', '#c792ea']

/** 'YYYY-MM-DD' → UTC 秒 */
function dateToSec(s: string): number {
  return Math.floor(new Date(s.slice(0, 10) + 'T00:00:00Z').getTime() / 1000)
}

function toBars(rows: DailyBar[]): KBar[] {
  // API 倒序返回（最新在前），图表需要升序
  return [...rows]
    .reverse()
    .filter((r) => r.open != null && r.high != null && r.low != null && r.close != null)
    .map((r) => ({
      time: dateToSec(r.trade_date),
      open: r.open as number,
      high: r.high as number,
      low: r.low as number,
      close: r.close as number,
      volume: r.vol ?? 0,
    }))
}

/** 日线 → 周线重采样（按自然周聚合，time 取本周最后交易日） */
function resampleWeekly(bars: KBar[]): KBar[] {
  const out: KBar[] = []
  let cur: KBar | null = null
  let curKey = ''
  for (const b of bars) {
    const d = new Date(b.time * 1000)
    // 以周四所在年份+周序号作为周键（任意稳定锚点均可）
    const thursday = new Date(d)
    thursday.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7))
    const yearStart = new Date(Date.UTC(thursday.getUTCFullYear(), 0, 1))
    const week = Math.ceil(((thursday.getTime() - yearStart.getTime()) / 86400000 + 1) / 7)
    const key = `${thursday.getUTCFullYear()}-W${week}`
    if (!cur || key !== curKey) {
      if (cur) out.push(cur)
      cur = { ...b }
      curKey = key
    } else {
      cur.high = Math.max(cur.high, b.high)
      cur.low = Math.min(cur.low, b.low)
      cur.close = b.close
      cur.volume += b.volume
      cur.time = b.time
    }
  }
  if (cur) out.push(cur)
  return out
}

const fmtVolCn = (v: number | null) => {
  if (v == null) return '—'
  if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿手'
  if (v >= 1e4) return (v / 1e4).toFixed(1) + '万手'
  return String(Math.round(v)) + '手'
}

export default function AnalysisPage() {
  const [searchParams] = useSearchParams()
  const [symbol, setSymbol] = useState(() => normalizeStockCode(searchParams.get('stock') ?? '000001.SZ'))
  const [stockInput, setStockInput] = useState(() => normalizeStockCode(searchParams.get('stock') ?? '000001.SZ'))
  const [inputError, setInputError] = useState<string | null>(null)

  const [tf, setTf] = useState('daily')
  const [bars, setBars] = useState<KBar[]>([])
  const [stockInfo, setStockInfo] = useState<StockBasic | null>(null)
  const [loading, setLoading] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const [chartType, setChartType] = useState('candle')
  const [heikin, setHeikin] = useState(false) // 平均K：显示平滑，指标仍按原始价
  const [range, setRange] = useState<number | null>(126) // 默认显示 6 个月
  const [logScale, setLogScale] = useState(false)
  const [magnet, setMagnet] = useState(false)

  const [showMA, setShowMA] = useState(true)
  const [maType, setMaType] = useState('sma')
  const [maPeriods, setMaPeriods] = useState([5, 20, 60])
  const [showBB, setShowBB] = useState(false)
  const [showDC, setShowDC] = useState(false)
  const [showMACD, setShowMACD] = useState(false)
  const [showStoch, setShowStoch] = useState(false)
  const [showRSI, setShowRSI] = useState(false)
  const [showMFI, setShowMFI] = useState(false)
  const [showCCI, setShowCCI] = useState(false)
  const [showADX, setShowADX] = useState(false)
  const [showIchi, setShowIchi] = useState(false)
  const [showPSAR, setShowPSAR] = useState(false)
  const [showST, setShowST] = useState(false)
  const [showSignals, setShowSignals] = useState(true) // 信号：吞没/锤/星箭头
  const [showSR, setShowSR] = useState(false)
  const [showFib, setShowFib] = useState(false)
  const [showFibExt, setShowFibExt] = useState(false)
  const [showVP, setShowVP] = useState(false)
  const [showVWAP, setShowVWAP] = useState(false)

  const [showPos, setShowPos] = useState(false) // 持仓/风险回报模拟
  const [posEntry, setPosEntry] = useState('')
  const [posStop, setPosStop] = useState('')
  const [posTarget, setPosTarget] = useState('')
  const [posQty, setPosQty] = useState(100)
  const [posRisk, setPosRisk] = useState('')

  const [showDiv, setShowDiv] = useState(false) // 价格↔震荡指标背离
  const [divOsc, setDivOsc] = useState('rsi')

  const [showAlerts, setShowAlerts] = useState(false) // 价格告警（本页会话内）
  const [alerts, setAlerts] = useState<Array<{ id: string; price: number; dir: 'up' | 'down' }>>([])
  const [alertPrice, setAlertPrice] = useState('')
  const [alertDir, setAlertDir] = useState<'up' | 'down'>('up')

  const [showCP, setShowCP] = useState(false) // 蜡烛形态卡 + 全量形态箭头

  // 自选股（服务端持久化）
  const [favs, setFavs] = useState<string[]>([])
  useEffect(() => {
    fetchWatchlist()
      .then((r) => setFavs(r.items.map((i: WatchlistItem) => i.ts_code)))
      .catch(() => {})
  }, [])
  const isFav = favs.includes(symbol)
  const toggleFav = async () => {
    try {
      if (isFav) {
        await removeWatchlistItem(symbol)
        setFavs((prev) => prev.filter((s) => s !== symbol))
      } else {
        await addWatchlistItem(symbol)
        setFavs((prev) => [...prev, symbol])
      }
    } catch {
      /* 自选服务不可用时静默 */
    }
  }

  // 数据加载：symbol 变化即拉取（挂载时默认自动加载一次）
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setErrorMsg(null)
    setStockInput(symbol)
    fetchStockInfo(symbol)
      .then((info) => {
        if (!cancelled) setStockInfo(info)
      })
      .catch(() => {
        if (!cancelled) setStockInfo(null)
      })
    fetchStockHistory(symbol, 1000)
      .then((rows) => {
        if (!cancelled) setBars(toBars(rows))
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setBars([])
          setErrorMsg(e instanceof Error ? e.message : '行情数据加载失败，请确认数据已下载')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [symbol])

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault()
    const code = normalizeStockCode(stockInput)
    if (!STOCK_CODE_RE.test(code)) {
      setInputError('股票代码格式不正确，应为 000001.SZ 或 600000.SH')
      return
    }
    setInputError(null)
    setSymbol(code)
  }

  const allBars = useMemo(() => bars, [bars])
  // 周线视图：重采样后的序列
  const tfBars = useMemo(() => (tf === 'weekly' ? resampleWeekly(allBars) : allBars), [tf, allBars])
  // 可见窗口（S/R 与 Fib 按窗口计算，保证画在屏内）
  const viewBars = range == null || range >= tfBars.length ? tfBars : tfBars.slice(tfBars.length - range)
  const displayBars = heikin && tfBars.length ? heikinAshi(tfBars) : tfBars
  const last = tfBars.length ? tfBars[tfBars.length - 1] : null
  const prevBar = tfBars.length > 1 ? tfBars[tfBars.length - 2] : null
  const change = last && prevBar ? ((last.close - prevBar.close) / prevBar.close) * 100 : null

  // 一目/超趋/DC 叠加数据源（先于 overlays 声明，避免 TDZ）
  const ichiInfo = useMemo(() => (showIchi ? ichimoku(tfBars) : null), [showIchi, tfBars])
  const stInfo = useMemo(() => (showST ? superTrend(tfBars, 10, 3) : null), [showST, tfBars])
  const dcInfo = useMemo(() => (showDC ? donchian(tfBars, 20) : null), [showDC, tfBars])
  const dcNow = useMemo(() => {
    if (!dcInfo || !dcInfo.upper.length) return null
    return {
      upper: dcInfo.upper[dcInfo.upper.length - 1].value,
      lower: dcInfo.lower[dcInfo.lower.length - 1].value,
      mid: dcInfo.mid[dcInfo.mid.length - 1].value,
    }
  }, [dcInfo])
  const stNow = useMemo(() => {
    if (!stInfo) return null
    const u = stInfo.up.length ? stInfo.up[stInfo.up.length - 1] : null
    const d = stInfo.down.length ? stInfo.down[stInfo.down.length - 1] : null
    if (!u && !d) return null
    if (!d) return { dir: 1, value: u.value }
    if (!u) return { dir: -1, value: d.value }
    return u.time >= d.time ? { dir: 1, value: u.value } : { dir: -1, value: d.value }
  }, [stInfo])

  // 主图叠加：均线 + 布林 + DC + SAR + VWAP + 超趋 + 一目
  const overlays = useMemo(() => {
    const o: Array<{ color: string; lineWidth?: number; label: string; dots?: boolean; points: Array<{ time: number; value: number }> }> = []
    if (showMA) {
      const fn = maType === 'ema' ? ema : sma
      const tag = maType.toUpperCase()
      maPeriods.forEach((p, k) => {
        if (p > 0) o.push({ color: MA_COLORS[k], label: `${tag}${p}`, points: fn(tfBars, p) })
      })
    }
    if (showBB) {
      const bb = bollinger(tfBars, 20, 2)
      o.push({ color: 'rgba(79,147,231,0.55)', label: 'BOLL中', points: bb.middle })
      o.push({ color: 'rgba(239,83,80,0.45)', label: 'BOLL上', points: bb.upper })
      o.push({ color: 'rgba(38,166,154,0.45)', label: 'BOLL下', points: bb.lower })
    }
    if (showDC && dcInfo) {
      o.push({ color: 'rgba(149,117,205,0.55)', label: 'DC上', points: dcInfo.upper })
      o.push({ color: 'rgba(149,117,205,0.55)', label: 'DC下', points: dcInfo.lower })
      o.push({ color: 'rgba(149,117,205,0.3)', label: 'DC中', points: dcInfo.mid })
    }
    if (showPSAR) {
      const ps = psar(tfBars)
      o.push({ color: UP_COLOR, dots: true, label: 'SAR↑', points: ps.up })
      o.push({ color: DOWN_COLOR, dots: true, label: 'SAR↓', points: ps.down })
    }
    if (showVWAP) {
      o.push({ color: '#29b6f6', lineWidth: 1.5, label: 'VWAP', points: vwap(tfBars, false) })
    }
    if (showST && stInfo) {
      o.push({ color: UP_COLOR, lineWidth: 2, label: '超趋↑', points: stInfo.up })
      o.push({ color: DOWN_COLOR, lineWidth: 2, label: '超趋↓', points: stInfo.down })
    }
    if (showIchi && ichiInfo) {
      o.push({ color: '#ef5350', lineWidth: 1, label: '转换', points: ichiInfo.tenkan })
      o.push({ color: '#4f93e7', lineWidth: 2, label: '基准', points: ichiInfo.kijun })
      o.push({ color: '#26a69a', lineWidth: 1, label: '先行A', points: ichiInfo.spanA })
      o.push({ color: '#c792ea', lineWidth: 1, label: '先行B', points: ichiInfo.spanB })
    }
    return o
  }, [tfBars, showMA, maType, maPeriods, showBB, showDC, dcInfo, showPSAR, showVWAP, showST, stInfo, showIchi, ichiInfo])

  // ADX / MFI / CCI 当前值（副图与图例共用，保证数字与曲线一致）
  const adxInfo = useMemo(() => (showADX && tfBars.length > 28 ? adx(tfBars, 14) : null), [showADX, tfBars])
  const adxNow = useMemo(() => {
    if (!adxInfo) return null
    const lv = (arr: Array<{ value: number } | null>) => {
      for (let i = arr.length - 1; i >= 0; i--) {
        const it = arr[i]
        if (it != null && it.value != null) return it.value
      }
      return null
    }
    return { pdi: lv(adxInfo.plusDI), mdi: lv(adxInfo.minusDI), adx: lv(adxInfo.adx) }
  }, [adxInfo])
  const mfiInfo = useMemo(() => (showMFI ? mfi(tfBars, 14) : null), [showMFI, tfBars])
  const mfiNow = useMemo(() => {
    if (!mfiInfo || !mfiInfo.length) return null
    for (let i = mfiInfo.length - 1; i >= 0; i--) if (mfiInfo[i]?.value != null) return mfiInfo[i].value
    return null
  }, [mfiInfo])
  const cciInfo = useMemo(() => (showCCI ? cci(tfBars, 20) : null), [showCCI, tfBars])
  const cciNow = useMemo(() => {
    if (!cciInfo || !cciInfo.length) return null
    for (let i = cciInfo.length - 1; i >= 0; i--) if (cciInfo[i]?.value != null) return cciInfo[i].value
    return null
  }, [cciInfo])

  // 震荡指标副图（自上而下依次堆叠）
  const panes = useMemo(() => {
    const p: Array<{
      lines: Array<{ color: string; label: string; lineWidth?: number; points: Array<{ time: number; value: number }> }>
      hist?: { points: Array<{ time: number; value: number }> }
      refs?: Array<{ price: number; color: string }>
    }> = []
    if (showMACD) {
      const m = macd(tfBars)
      p.push({
        lines: [
          { color: '#4f93e7', label: 'DIF', points: m.macd },
          { color: '#ffd166', label: 'DEA', points: m.signal },
        ],
        hist: { points: m.hist },
        refs: [{ price: 0, color: 'rgba(255,255,255,0.2)' }],
      })
    }
    if (showStoch) {
      const st = stochastic(tfBars, 14, 3)
      p.push({
        lines: [
          { color: '#4f93e7', label: 'K', points: st.k },
          { color: '#ffd166', label: 'D', points: st.d },
        ],
        refs: [
          { price: 80, color: 'rgba(239,83,80,0.5)' },
          { price: 50, color: 'rgba(255,255,255,0.12)' },
          { price: 20, color: 'rgba(38,166,154,0.5)' },
        ],
      })
    }
    if (showRSI)
      p.push({
        lines: [{ color: '#b39ddb', label: 'RSI', points: rsi(tfBars, 14) }],
        refs: [
          { price: 70, color: 'rgba(239,83,80,0.5)' },
          { price: 30, color: 'rgba(38,166,154,0.5)' },
        ],
      })
    if (showMFI && mfiInfo)
      p.push({
        lines: [{ color: '#80deea', label: 'MFI', points: mfiInfo }],
        refs: [
          { price: 80, color: 'rgba(239,83,80,0.5)' },
          { price: 20, color: 'rgba(38,166,154,0.5)' },
        ],
      })
    if (showCCI && cciInfo)
      p.push({
        lines: [{ color: '#f06292', label: 'CCI', points: cciInfo }],
        refs: [
          { price: 100, color: 'rgba(239,83,80,0.5)' },
          { price: 0, color: 'rgba(255,255,255,0.12)' },
          { price: -100, color: 'rgba(38,166,154,0.5)' },
        ],
      })
    if (showADX && adxInfo) {
      p.push({
        lines: [
          { color: '#26a69a', label: '+DI', points: adxInfo.plusDI },
          { color: '#ef5350', label: '−DI', points: adxInfo.minusDI },
          { color: '#ffd166', lineWidth: 2, label: 'ADX', points: adxInfo.adx },
        ],
        refs: [
          { price: 25, color: 'rgba(255,193,7,0.45)' },
          { price: 20, color: 'rgba(255,255,255,0.10)' },
        ],
      })
    }
    return p
  }, [tfBars, showMACD, showStoch, showRSI, showMFI, mfiInfo, showCCI, cciInfo, showADX, adxInfo])

  // 持仓模拟（做多）：入场/止损/止盈 → 风险回报
  const posCalc = useMemo(() => {
    const pf = (v: string) => {
      const n = +v
      return v !== '' && Number.isFinite(n) ? n : null
    }
    const e = pf(posEntry), s = pf(posStop), t = pf(posTarget)
    const q = Number.isFinite(posQty) && posQty > 0 ? posQty : null
    if (e == null || s == null || t == null) return null
    const risk = e - s
    const reward = t - e
    return {
      e, s, t, q: q ?? 0,
      rr: risk !== 0 ? reward / risk : null,
      riskY: risk * (q ?? 0),
      rewardY: reward * (q ?? 0),
      lossPct: e ? s / e - 1 : 0,
      gainPct: e ? t / e - 1 : 0,
    }
  }, [posEntry, posStop, posTarget, posQty])

  const posAtrVal = useMemo(() => {
    const s = atr(tfBars, 14)
    return s.length ? s[s.length - 1].value : null
  }, [tfBars])

  // 水平价位线：S/R + Fib + Fib扩 + 持仓价位 + 告警
  const priceLines = useMemo(
    () => [
      ...(showSR ? pivotLevels(viewBars) : []),
      ...(showFib ? fibLevels(viewBars) : []),
      ...(showFibExt ? fibExtension(viewBars) : []),
      ...(posCalc
        ? [
            { price: posCalc.e, color: '#4f93e7', lineStyle: LineStyle.Solid, lineWidth: 1, title: '入场' },
            { price: posCalc.s, color: DOWN_COLOR, lineStyle: LineStyle.Solid, lineWidth: 1, title: '止损' },
            { price: posCalc.t, color: UP_COLOR, lineStyle: LineStyle.Solid, lineWidth: 1, title: '止盈' },
          ]
        : []),
      ...(showAlerts
        ? alerts.map((a) => ({
            price: a.price,
            color: a.dir === 'up' ? UP_COLOR : DOWN_COLOR,
            lineStyle: LineStyle.Dashed,
            lineWidth: 1,
            title: `告警 ${a.dir === 'up' ? '↑' : '↓'}`,
          }))
        : []),
    ],
    [viewBars, showSR, showFib, showFibExt, posCalc, showAlerts, alerts]
  )

  // 告警触发状态：历史收盘价穿越即标记
  const alertRows = useMemo(
    () => alerts.map((a) => ({ ...a, crossed: priceCross(tfBars, a.price, a.dir) as number | boolean })),
    [alerts, tfBars]
  )
  const addAlert = () => {
    const p = parseFloat(alertPrice)
    if (!Number.isFinite(p) || p <= 0) return
    setAlerts((prev) => [...prev, { id: `${Date.now()}-${Math.random()}`, price: p, dir: alertDir }])
    setAlertPrice('')
  }
  const removeAlert = (id: string) => setAlerts((prev) => prev.filter((a) => a.id !== id))

  // 区间统计（随可见窗口变化）
  const rangeStats = useMemo(() => {
    if (viewBars.length < 2) return null
    const rets: number[] = []
    for (let i = 1; i < viewBars.length; i++) {
      const r = viewBars[i].close / viewBars[i - 1].close - 1
      if (Number.isFinite(r)) rets.push(r)
    }
    const mean = rets.reduce((a, b) => a + b, 0) / (rets.length || 1)
    const variance = rets.reduce((a, b) => a + (b - mean) ** 2, 0) / (rets.length || 1)
    const close = viewBars.map((b) => b.close)
    return {
      periodRet: close[close.length - 1] / close[0] - 1,
      annVol: Math.sqrt(variance) * Math.sqrt(252),
      high: Math.max(...viewBars.map((b) => b.high)),
      low: Math.min(...viewBars.map((b) => b.low)),
      avgVol: viewBars.reduce((a, b) => a + (b.volume || 0), 0) / viewBars.length,
      n: viewBars.length,
    }
  }, [viewBars])

  // 技术信号雷达：各指标对最新一根 K 投票（+1/-1/0），聚合为 -1..1 强度
  const rating = useMemo(() => {
    if (tfBars.length < 60) return null
    const lastClose = tfBars[tfBars.length - 1].close
    const lv = (arr: Array<{ value: number } | null>) => {
      for (let i = arr.length - 1; i >= 0; i--) {
        const it = arr[i]
        if (it != null && it.value != null) return it.value
      }
      return null
    }
    const votes: Array<{ label: string; vote: number }> = []
    for (const p of [20, 50, 200]) {
      if (tfBars.length > p) {
        const sv = lv(sma(tfBars, p))
        if (sv != null) votes.push({ label: `价vs MA${p}`, vote: lastClose > sv ? 1 : -1 })
      }
    }
    if (tfBars.length > 50) {
      const e20 = lv(ema(tfBars, 20)), e50 = lv(ema(tfBars, 50))
      if (e20 != null && e50 != null) votes.push({ label: 'EMA20/50', vote: e20 > e50 ? 1 : -1 })
    }
    const M = macd(tfBars)
    const mv = lv(M.macd), ms = lv(M.signal)
    if (mv != null && ms != null) votes.push({ label: 'MACD', vote: mv > ms ? 1 : -1 })
    const rv = lv(rsi(tfBars, 14))
    if (rv != null) votes.push({ label: 'RSI14', vote: rv > 55 ? 1 : rv < 45 ? -1 : 0 })
    const ST = stochastic(tfBars, 14, 3)
    const k = lv(ST.k), d = lv(ST.d)
    if (k != null && d != null) votes.push({ label: 'KDJ', vote: k > d ? 1 : -1 })
    const buy = votes.filter((x) => x.vote > 0).length
    const sell = votes.filter((x) => x.vote < 0).length
    const neutral = votes.filter((x) => x.vote === 0).length
    return { votes, buy, sell, neutral, score: votes.length ? (buy - sell) / votes.length : 0 }
  }, [tfBars])

  // 价格↔震荡指标背离
  const divInfo = useMemo(() => {
    const events = divergence(tfBars, { osc: divOsc })
    const bull = events.filter((e: { type: string }) => e.type === 'bull').length
    const bear = events.filter((e: { type: string }) => e.type === 'bear').length
    return { events, bull, bear, latest: events.length ? events[events.length - 1] : null }
  }, [tfBars, divOsc])
  const divMarkers = useMemo(
    () =>
      showDiv
        ? divInfo.events.map((e: { bTime: number; type: string }) => ({
            time: e.bTime,
            position: e.type === 'bull' ? 'belowBar' : 'aboveBar',
            color: e.type === 'bull' ? UP_COLOR : DOWN_COLOR,
            shape: e.type === 'bull' ? 'arrowUp' : 'arrowDown',
            text: e.type === 'bull' ? '底背' : '顶背',
          }))
        : [],
    [divInfo, showDiv]
  )

  // 蜡烛反转形态（客户端由 OHLC 计算）
  const cpInfo = useMemo(() => candlePatterns(tfBars), [tfBars])
  // 信号 = 吞没/锤/星（截图风格的方向箭头）
  const signalMarkers = useMemo(
    () => [
      ...cpInfo.hammer.map((p: { time: number }) => ({ time: p.time, position: 'belowBar', color: UP_COLOR, shape: 'arrowUp', text: '锤' })),
      ...cpInfo.bullEngulf.map((p: { time: number }) => ({ time: p.time, position: 'belowBar', color: UP_COLOR, shape: 'arrowUp', text: '吞' })),
      ...cpInfo.shootingStar.map((p: { time: number }) => ({ time: p.time, position: 'aboveBar', color: DOWN_COLOR, shape: 'arrowDown', text: '星' })),
      ...cpInfo.bearEngulf.map((p: { time: number }) => ({ time: p.time, position: 'aboveBar', color: DOWN_COLOR, shape: 'arrowDown', text: '吞' })),
    ],
    [cpInfo]
  )
  // 形态 = 全量形态箭头（含三兵/三鸦/光头光脚/十字）
  const cpMarkers = useMemo(
    () => [
      ...signalMarkers,
      ...cpInfo.threeSoldiers.map((p: { time: number }) => ({ time: p.time, position: 'belowBar', color: UP_COLOR, shape: 'arrowUp', text: '兵' })),
      ...cpInfo.threeCrows.map((p: { time: number }) => ({ time: p.time, position: 'aboveBar', color: DOWN_COLOR, shape: 'arrowDown', text: '鸦' })),
      ...cpInfo.marubozu.map((p: { time: number; dir: number }) => ({
        time: p.time, position: p.dir > 0 ? 'belowBar' : 'aboveBar',
        color: p.dir > 0 ? UP_COLOR : DOWN_COLOR, shape: p.dir > 0 ? 'arrowUp' : 'arrowDown', text: '强',
      })),
      ...cpInfo.doji.map((p: { time: number }) => ({ time: p.time, position: 'aboveBar', color: '#9aa6b2', shape: 'circle', text: '十' })),
    ],
    [signalMarkers, cpInfo]
  )
  const chartPatterns = useMemo(() => {
    const all = showCP ? [...cpMarkers, ...divMarkers] : showSignals ? [...signalMarkers, ...divMarkers] : [...divMarkers]
    all.sort((a, b) => (a.time || 0) - (b.time || 0))
    return all
  }, [showCP, showSignals, cpMarkers, signalMarkers, divMarkers])

  // 打开持仓模拟且三档全空时，按最新收盘价预填（入场=最新，止损=-5%，止盈=+10%）
  useEffect(() => {
    if (showPos && last && posEntry === '' && posStop === '' && posTarget === '') {
      setPosEntry(last.close.toFixed(2))
      setPosStop((last.close * 0.95).toFixed(2))
      setPosTarget((last.close * 1.1).toFixed(2))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showPos, last])

  const fmtDate = (t: number) => new Date(t * 1000).toISOString().slice(0, 10)

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>技术分析</h2>
          <p className="desc">K线详情 · lightweight-charts v5 · 多指标叠加/副图 · 形态/背离/告警/持仓模拟</p>
        </div>
      </div>

      {/* 工具栏 */}
      <div className="panel">
        <div className="panel-body kbar">
          <form className="kbar-row" onSubmit={handleSubmit}>
            <input
              type="text"
              className={`kinput ${inputError ? 'kinput-err' : ''}`}
              placeholder="000001.SZ"
              maxLength={9}
              value={stockInput}
              onChange={(e) => setStockInput(e.target.value.toUpperCase())}
              onBlur={() => {
                const code = normalizeStockCode(stockInput)
                setStockInput(code)
                setInputError(STOCK_CODE_RE.test(code) ? null : '股票代码格式不正确，应为 000001.SZ 或 600000.SH')
              }}
              style={{ width: 120, fontWeight: 700 }}
            />
            <button type="submit" className="kbtn primary" disabled={loading}>
              {loading ? '加载中…' : '分析'}
            </button>
          </form>
          <button
            type="button"
            className={`kbtn ${isFav ? 'active' : ''}`}
            onClick={toggleFav}
            title={isFav ? '移出自选' : '加入自选'}
            style={{ fontSize: 15, lineHeight: 1 }}
          >
            {isFav ? '★' : '☆'}
          </button>
          <span className="kmuted">{stockInfo?.name ?? ''}</span>
          <div className="kgroup">
            {CHART_TYPES.map((c) => (
              <button key={c.key} className={`kbtn ${chartType === c.key ? 'active' : ''}`} onClick={() => setChartType(c.key)}>
                {c.label}
              </button>
            ))}
          </div>
          <div className="kgroup">
            {TFS.map((t) => (
              <button key={t.key} className={`kbtn ${tf === t.key ? 'active' : ''}`} onClick={() => setTf(t.key)}>
                {t.label}
              </button>
            ))}
          </div>
          {(
            [
              ['MA', showMA, setShowMA, '均线叠加'],
              ['BOLL', showBB, setShowBB, '布林带'],
              ['DC', showDC, setShowDC, 'Donchian 通道：N 根最高/最低包络（突破/破位）'],
              ['MACD', showMACD, setShowMACD, 'MACD 副图'],
              ['KDJ', showStoch, setShowStoch, 'KDJ 随机指标副图'],
              ['RSI', showRSI, setShowRSI, 'RSI 副图'],
              ['MFI', showMFI, setShowMFI, 'MFI 资金流量：成交量加权 RSI（>80 超买/<20 超卖）'],
              ['CCI', showCCI, setShowCCI, 'CCI 通道指标（>+100 强势/<-100 弱势）'],
              ['ADX', showADX, setShowADX, 'ADX/DMI 趋势强度副图'],
              ['一目', showIchi, setShowIchi, '一目均衡四线'],
              ['SAR', showPSAR, setShowPSAR, '抛物线 SAR'],
              ['超趋', showST, setShowST, 'SuperTrend：ATR 波动止损线，翻转即转势'],
              ['信号', showSignals, setShowSignals, '吞没/锤子/流星形态箭头'],
              ['支撑/阻力', showSR, setShowSR, '自动 pivot 支撑/阻力价位线'],
              ['Fib', showFib, setShowFib, '斐波那契回撤水平线'],
              ['Fib扩', showFibExt, setShowFibExt, '斐波那契扩展盈利目标'],
              ['量能分布', showVP, setShowVP, '按价位的成交量分布 + POC + 70% 价值区'],
              ['VWAP', showVWAP, setShowVWAP, '成交量加权均价（日线=累计）'],
            ] as Array<[string, boolean, (v: boolean) => void, string]>
          ).map(([label, val, set, title]) => (
            <label key={label} className="kchk" title={title}>
              <input type="checkbox" checked={val} onChange={(e) => set(e.target.checked)} /> {label}
            </label>
          ))}
          <div className="kgroup">
            {RANGES.map((r) => (
              <button key={r.key} className={`kbtn ${range === r.bars ? 'active' : ''}`} onClick={() => setRange(r.bars)}>
                {r.label}
              </button>
            ))}
          </div>
          <label className="kchk">
            <input type="checkbox" checked={logScale} onChange={(e) => setLogScale(e.target.checked)} /> 对数
          </label>
          <label className="kchk">
            <input type="checkbox" checked={magnet} onChange={(e) => setMagnet(e.target.checked)} /> 磁吸
          </label>
          <label className="kchk" title="平均K（Heikin-Ashi）：平滑后看趋势；指标/价位线仍按原始价计算">
            <input type="checkbox" checked={heikin} onChange={(e) => setHeikin(e.target.checked)} /> 平均K
          </label>
          <button className={`kbtn ${showPos ? 'active' : ''}`} onClick={() => setShowPos((v) => !v)} title="持仓/风险回报模拟（入场·止损·止盈）">
            持仓
          </button>
          <button className={`kbtn ${showDiv ? 'active' : ''}`} onClick={() => setShowDiv((v) => !v)} title="价格↔震荡指标背离（看涨/看跌）">
            背离
          </button>
          <button className={`kbtn ${showAlerts ? 'active' : ''}`} onClick={() => setShowAlerts((v) => !v)} title="价格告警（上穿/下穿价位，虚线画在图上）">
            告警
          </button>
          <button className={`kbtn ${showCP ? 'active' : ''}`} onClick={() => setShowCP((v) => !v)} title="蜡烛图反转形态（锤子/流星/吞没/三兵/三鸦等）">
            形态
          </button>
          {last && (
            <span className="klast">
              {symbol} <b>{last.close?.toFixed(2)}</b>{' '}
              <span style={{ color: (change ?? 0) >= 0 ? UP_COLOR : DOWN_COLOR }}>
                {(change ?? 0) >= 0 ? '+' : ''}
                {change?.toFixed(2)}%
              </span>
              <span className="kmuted"> · {tfBars.length} 根</span>
            </span>
          )}
          {inputError && <span className="kneg" style={{ fontSize: 12 }}>{inputError}</span>}
        </div>
      </div>

      {/* 均线参数行 */}
      {showMA && !loading && (
        <div className="panel">
          <div className="panel-body kbar">
            <span className="kmuted">均线</span>
            <div className="kgroup">
              <button className={`kbtn ${maType === 'sma' ? 'active' : ''}`} onClick={() => setMaType('sma')}>SMA</button>
              <button className={`kbtn ${maType === 'ema' ? 'active' : ''}`} onClick={() => setMaType('ema')}>EMA</button>
            </div>
            {maPeriods.map((p, k) => (
              <label key={k} className="kchk">
                P{k + 1}
                <input
                  type="number"
                  min={1}
                  max={500}
                  value={p}
                  className="kinput"
                  style={{ width: 56 }}
                  onChange={(e) => setMaPeriods((prev) => prev.map((v, i) => (i === k ? Math.max(1, +e.target.value || 1) : v)))}
                />
              </label>
            ))}
          </div>
        </div>
      )}

      {/* 主图 */}
      {loading ? (
        <div className="panel">
          <div className="panel-body">
            <Loading text="加载行情数据..." />
          </div>
        </div>
      ) : errorMsg ? (
        <div className="panel">
          <div className="panel-body">
            <ErrorState message={errorMsg} onRetry={() => setSymbol((s) => s)} />
          </div>
        </div>
      ) : tfBars.length ? (
        <div className="panel">
          <div className="panel-body">
            <CandleChart
              bars={displayBars}
              patterns={chartPatterns}
              overlays={overlays}
              panes={panes}
              priceLines={priceLines}
              height={460}
              showVP={showVP}
              title={`${symbol}${stockInfo?.name ? ' · ' + stockInfo.name : ''}`}
              chartType={chartType}
              range={range}
              logScale={logScale}
              magnet={magnet}
              divergence={showDiv ? divInfo.events : []}
            />
            <div className="kmuted" style={{ fontSize: 11, marginTop: 6, display: 'flex', flexWrap: 'wrap', gap: 10 }}>
              {showMA &&
                maPeriods.map((p, k) => (
                  <span key={k} style={{ color: MA_COLORS[k] }}>
                    ●{maType.toUpperCase()}
                    {p}
                  </span>
                ))}
              {showBB && <span>●BOLL(20,2)</span>}
              {showDC && dcNow != null && (
                <span style={{ color: 'rgba(149,117,205,0.9)' }}>
                  ●DC(20) 上{dcNow.upper.toFixed(2)} 下{dcNow.lower.toFixed(2)} 宽{(((dcNow.upper - dcNow.lower) / dcNow.mid) * 100).toFixed(1)}%
                </span>
              )}
              {showMACD && <span>●MACD(12,26,9)</span>}
              {showStoch && <span>●KDJ(14,3)</span>}
              {showRSI && <span style={{ color: '#b39ddb' }}>●RSI(14)</span>}
              {showMFI && mfiNow != null && (
                <span style={{ color: '#80deea' }}>
                  ●MFI(14) {mfiNow.toFixed(1)}
                  {mfiNow >= 80 ? ' 资金超买' : mfiNow <= 20 ? ' 资金超卖' : ''}
                </span>
              )}
              {showCCI && cciNow != null && (
                <span style={{ color: '#f06292' }}>
                  ●CCI(20) {cciNow.toFixed(1)}
                  {cciNow >= 100 ? ' 强势' : cciNow <= -100 ? ' 弱势' : ''}
                </span>
              )}
              {showADX && adxNow && adxNow.adx != null && (
                <span>
                  <span style={{ color: '#26a69a' }}>●+DI {adxNow.pdi?.toFixed(1) ?? '—'}</span>
                  <span style={{ color: '#ef5350' }}> ●−DI {adxNow.mdi?.toFixed(1) ?? '—'}</span>
                  <span style={{ color: '#ffd166' }}> ●ADX {adxNow.adx.toFixed(1)}</span>
                  <span className="kmuted">（{adxNow.adx >= 25 ? '强趋势' : adxNow.adx >= 20 ? '酝酿中' : '无趋势'}）</span>
                </span>
              )}
              {showST && stNow && (
                <span style={{ color: stNow.dir > 0 ? UP_COLOR : DOWN_COLOR }}>
                  ●超趋 {stNow.dir > 0 ? '↑多头' : '↓空头'} {stNow.value != null ? stNow.value.toFixed(2) : ''}（ATR(10)×3，翻转即转势）
                </span>
              )}
              {showSR && <span>---支撑/阻力（自动 pivot）</span>}
              {showFib && <span style={{ color: '#ab47bc' }}>---Fib 回撤（0–100%）</span>}
              {showFibExt && <span style={{ color: '#ffc107' }}>---Fib扩（↑1.272/1.618/2.618×）</span>}
              {showVP && <span style={{ color: '#64b5f6' }}>▌量能分布 + POC + 70% 价值区</span>}
              {showVWAP && <span style={{ color: '#29b6f6' }}>●VWAP（累计）</span>}
              {showIchi && ichiInfo && (
                <span>
                  <span style={{ color: '#ef5350' }}>●转换(9)</span> <span style={{ color: '#4f93e7' }}>●基准(26)</span>{' '}
                  <span style={{ color: '#26a69a' }}>●先行A</span> <span style={{ color: '#c792ea' }}>●先行B(52)</span>
                </span>
              )}
              {showDiv && (
                <span>
                  <span style={{ color: UP_COLOR }}>— 看涨背离</span> <span style={{ color: DOWN_COLOR }}>— 看跌背离</span>（{divOsc === 'macd' ? 'MACD柱' : 'RSI'}）
                </span>
              )}
              {showSignals && <span><span style={{ color: UP_COLOR }}>▲看涨形态</span> <span style={{ color: DOWN_COLOR }}>▼看跌形态</span></span>}
              {heikin && <span style={{ color: '#ff9800' }}>●平均K（显示已平滑，指标仍按原始价）</span>}
              {!showMA && !showBB && !showDC && !showMACD && !showStoch && !showRSI && !showMFI && !showCCI && !showADX && !showIchi && !showPSAR && !showST && !showSR && !showFib && !showFibExt && !showVP && !showVWAP && !showDiv && !showSignals && (
                <span>{heikin ? '平均K · ' : ''}纯 K 线 · 勾选上方指标叠加</span>
              )}
            </div>
            {rangeStats && (
              <div className="kstats">
                <div className="kstat">
                  <div className="kmuted" style={{ fontSize: 11 }}>区间涨幅</div>
                  <div className={(rangeStats.periodRet >= 0 ? 'pos' : 'neg') + ' kv'}>{(rangeStats.periodRet * 100).toFixed(2)}%</div>
                </div>
                <div className="kstat">
                  <div className="kmuted" style={{ fontSize: 11 }}>年化波动</div>
                  <div className="kv">{(rangeStats.annVol * 100).toFixed(1)}%</div>
                </div>
                <div className="kstat">
                  <div className="kmuted" style={{ fontSize: 11 }}>区间最高</div>
                  <div className="kv">{rangeStats.high.toFixed(2)}</div>
                </div>
                <div className="kstat">
                  <div className="kmuted" style={{ fontSize: 11 }}>区间最低</div>
                  <div className="kv">{rangeStats.low.toFixed(2)}</div>
                </div>
                <div className="kstat">
                  <div className="kmuted" style={{ fontSize: 11 }}>日均量</div>
                  <div className="kv">{fmtVolCn(rangeStats.avgVol)}</div>
                </div>
                <div className="kstat">
                  <div className="kmuted" style={{ fontSize: 11 }}>窗口</div>
                  <div className="kv kmuted">{rangeStats.n} 根</div>
                </div>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="panel">
          <div className="panel-body">
            <EmptyState icon="📉" text="该标的暂无行情数据，请先在数据管理页下载日线数据" />
          </div>
        </div>
      )}

      {/* 持仓模拟 */}
      {showPos && (
        <div className="panel">
          <div className="panel-body">
            <h6 className="panel-title">
              持仓模拟（做多）<span className="chip">入场/止损/止盈价位线 + 风险回报</span>
            </h6>
            <div className="kbar" style={{ flexWrap: 'wrap', gap: 10 }}>
              <label className="kchk">
                入场
                <input type="number" className="kinput" style={{ width: 84 }} value={posEntry} onChange={(e) => setPosEntry(e.target.value)} />
              </label>
              <label className="kchk">
                止损
                <input type="number" className="kinput" style={{ width: 84 }} value={posStop} onChange={(e) => setPosStop(e.target.value)} />
              </label>
              <label className="kchk">
                止盈
                <input type="number" className="kinput" style={{ width: 84 }} value={posTarget} onChange={(e) => setPosTarget(e.target.value)} />
              </label>
              <label className="kchk">
                股数
                <input type="number" min={0} className="kinput" style={{ width: 76 }} value={posQty} onChange={(e) => setPosQty(+e.target.value)} />
              </label>
              {posAtrVal != null && (
                <>
                  <span className="kmuted">ATR(14) <b>{posAtrVal.toFixed(2)}</b></span>
                  <button
                    className="kbtn"
                    onClick={() => {
                      const e = +posEntry
                      if (e > 0 && Number.isFinite(e)) setPosStop((e - 1.5 * posAtrVal).toFixed(2))
                    }}
                    title="止损 = 入场 − 1.5×ATR（波动止损）"
                  >
                    用 1.5×ATR 设止损
                  </button>
                  <label className="kchk">
                    风险￥
                    <input type="number" min={0} className="kinput" style={{ width: 96 }} value={posRisk} onChange={(e) => setPosRisk(e.target.value)} placeholder="按止损定仓" />
                  </label>
                  {(() => {
                    const e = +posEntry, s = +posStop, r = +posRisk
                    const sizing = Number.isFinite(e) && Number.isFinite(s) && Number.isFinite(r) && r > 0 && e !== s ? Math.floor(r / Math.abs(e - s)) : null
                    return sizing != null && sizing > 0 ? (
                      <span>
                        建议 <b>{sizing.toLocaleString()}</b> 股
                        <button className="kbtn" style={{ marginLeft: 6 }} onClick={() => setPosQty(sizing)}>应用</button>
                      </span>
                    ) : (
                      <span className="kmuted">填风险￥ → 按入场/止损算股数</span>
                    )
                  })()}
                </>
              )}
            </div>
            {posCalc ? (
              <div className="kstats" style={{ marginTop: 8 }}>
                <div className="kstat">
                  <div className="kmuted" style={{ fontSize: 11 }}>风险回报</div>
                  <div className={'kv ' + (posCalc.rr != null ? ((posCalc.rr as number) >= 2 ? 'pos' : (posCalc.rr as number) < 1 ? 'neg' : '') : '')}>
                    {posCalc.rr != null ? (posCalc.rr as number).toFixed(2) + 'R' : '—'}
                  </div>
                </div>
                <div className="kstat">
                  <div className="kmuted" style={{ fontSize: 11 }}>止损亏损</div>
                  <div className="kv neg">{(posCalc.lossPct * 100).toFixed(2)}% · ¥{posCalc.riskY.toFixed(0)}</div>
                </div>
                <div className="kstat">
                  <div className="kmuted" style={{ fontSize: 11 }}>止盈盈利</div>
                  <div className="kv pos">+{(posCalc.gainPct * 100).toFixed(2)}% · ¥{posCalc.rewardY.toFixed(0)}</div>
                </div>
                <div className="kstat">
                  <div className="kmuted" style={{ fontSize: 11 }}>名义价值</div>
                  <div className="kv kmuted">¥{(posCalc.e * posCalc.q).toFixed(0)}</div>
                </div>
              </div>
            ) : (
              <div className="kmuted" style={{ marginTop: 8 }}>输入入场/止损/止盈价位以计算风险回报。</div>
            )}
          </div>
        </div>
      )}

      {/* 技术信号雷达 */}
      {rating && (
        <div className="panel">
          <div className="panel-body">
            <h6 className="panel-title">
              技术信号雷达 · <span style={{ color: ratingColor(rating.score) }}>{ratingLabel(rating.score)}</span>
              <span className="kmuted" style={{ fontSize: 12, fontWeight: 400 }}>
                {' '}· 综合 {rating.score.toFixed(2)} · 买 {rating.buy} / 中 {rating.neutral} / 卖 {rating.sell}
              </span>
            </h6>
            <div style={{ position: 'relative', height: 12, borderRadius: 6, background: `linear-gradient(90deg, ${DOWN_COLOR}, #4a5a66 45%, #6b4a55 55%, ${UP_COLOR})`, marginTop: 4 }}>
              <div
                style={{
                  position: 'absolute',
                  left: `calc(${((rating.score + 1) / 2) * 100}% - 2px)`,
                  top: -3, width: 4, height: 18, background: '#fff', borderRadius: 2, boxShadow: '0 0 4px rgba(0,0,0,0.7)',
                }}
              />
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 10 }}>
              {rating.votes.map((v, i) => (
                <span
                  key={i}
                  style={{
                    fontSize: 11, padding: '2px 8px', borderRadius: 10,
                    background: v.vote > 0 ? 'rgba(239,83,80,0.15)' : v.vote < 0 ? 'rgba(38,166,154,0.15)' : 'rgba(154,166,178,0.12)',
                    color: v.vote > 0 ? UP_COLOR : v.vote < 0 ? DOWN_COLOR : '#9aa6b2',
                    border: `1px solid ${v.vote > 0 ? 'rgba(239,83,80,0.4)' : v.vote < 0 ? 'rgba(38,166,154,0.4)' : 'rgba(154,166,178,0.3)'}`,
                  }}
                >
                  {v.label} {v.vote > 0 ? '▲' : v.vote < 0 ? '▼' : '–'}
                </span>
              ))}
            </div>
            <div className="kmuted" style={{ fontSize: 12, marginTop: 8 }}>由 MA/EMA/MACD/RSI/KDJ 各投一票（±1/0）聚合，随周期/窗口重算。</div>
          </div>
        </div>
      )}

      {/* 背离检测 */}
      {showDiv && (
        <div className="panel">
          <div className="panel-body">
            <h6 className="panel-title">
              背离检测
              <span className="kmuted" style={{ fontSize: 12, fontWeight: 400 }}>
                {' '}· 价格 ↔ {divOsc === 'macd' ? 'MACD柱' : 'RSI(14)'} · <span className="pos">看涨 {divInfo.bull}</span> / <span className="neg">看跌 {divInfo.bear}</span>
                {divInfo.latest ? ` · 最近 ${fmtDate(divInfo.latest.bTime)}` : ''}
              </span>
              <select value={divOsc} onChange={(e) => setDivOsc(e.target.value)} className="kinput" style={{ marginLeft: 8, maxWidth: 110 }}>
                <option value="rsi">RSI</option>
                <option value="macd">MACD柱</option>
              </select>
            </h6>
            {divInfo.events.length ? (
              <div style={{ maxHeight: 200, overflow: 'auto', marginTop: 6 }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>类型</th>
                      <th>确认日</th>
                      <th className="num">价位（前→后）</th>
                      <th className="num">{divOsc === 'macd' ? 'MACD' : 'RSI'}（前→后）</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...divInfo.events].reverse().map((e, i) => (
                      <tr key={i}>
                        <td className={e.type === 'bull' ? 'pos' : 'neg'}>{e.type === 'bull' ? '看涨 ▲' : '看跌 ▼'}</td>
                        <td>{fmtDate(e.bTime)}</td>
                        <td className="num">
                          {(e.aPrice as number).toFixed(2)} → {(e.bPrice as number).toFixed(2)}
                        </td>
                        <td className="num">
                          {(e.aOsc as number).toFixed(1)} → {(e.bOsc as number).toFixed(1)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="kmuted" style={{ marginTop: 8 }}>当前窗口无明显常规背离（价格与{divOsc === 'macd' ? 'MACD柱' : 'RSI'}同向）。</div>
            )}
            <div className="kmuted" style={{ fontSize: 12, marginTop: 8 }}>
              看涨=价格更低的低点但震荡指标更高的低点（下行动能减弱）；看跌反之。摇摆点以 5/5 根窗口判定，故最近 5 根不出信号；连线画在主图上。
            </div>
          </div>
        </div>
      )}

      {/* 价格告警 */}
      {showAlerts && (
        <div className="panel">
          <div className="panel-body">
            <h6 className="panel-title">
              价格告警 · {symbol}
              <span className="kmuted" style={{ fontSize: 12, fontWeight: 400 }}>· 价位虚线画在图上 · 历史收盘价穿越即标记已触发（本页会话内有效）</span>
            </h6>
            <div className="kbar" style={{ flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
              <input
                type="number"
                className="kinput"
                style={{ width: 100 }}
                value={alertPrice}
                onChange={(e) => setAlertPrice(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') addAlert()
                }}
                placeholder="价位"
              />
              <select value={alertDir} onChange={(e) => setAlertDir(e.target.value as 'up' | 'down')} className="kinput" style={{ maxWidth: 96 }}>
                <option value="up">上穿 ↑</option>
                <option value="down">下穿 ↓</option>
              </select>
              <button className="kbtn" onClick={addAlert}>添加告警</button>
              {last && (
                <button className="kbtn" onClick={() => setAlertPrice(last.close.toFixed(2))} title="用最新收盘价填充">
                  在最新价
                </button>
              )}
              <span className="kmuted" style={{ fontSize: 12, marginLeft: 'auto' }}>
                {alertRows.filter((a) => a.crossed).length}/{alertRows.length} 已触发
              </span>
            </div>
            {alertRows.length ? (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>方向</th>
                    <th className="num">价位</th>
                    <th>状态</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {alertRows.map((a) => (
                    <tr key={a.id}>
                      <td className={a.dir === 'up' ? 'pos' : 'neg'}>{a.dir === 'up' ? '↑ 上穿' : '↓ 下穿'}</td>
                      <td className="num">{a.price.toFixed(2)}</td>
                      <td className={a.crossed ? 'pos' : 'kmuted'}>{a.crossed ? `已触发 ${fmtDate(a.crossed as number)}` : '监控中'}</td>
                      <td>
                        <button className="kbtn" onClick={() => removeAlert(a.id)} style={{ padding: '0 6px' }}>×</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="kmuted">尚无告警。输入价位选方向后添加；虚线画在主图（红=上穿/绿=下穿），历史已收盘穿越即标记触发日期。</div>
            )}
          </div>
        </div>
      )}

      {/* 蜡烛形态 */}
      {showCP && (
        <div className="panel">
          <div className="panel-body">
            <h6 className="panel-title">
              蜡烛形态 · {symbol}
              <span className="kmuted" style={{ fontSize: 12, fontWeight: 400 }}>
                {' '}· <span className="pos">锤子 {cpInfo.hammer.length}</span> · <span className="neg">流星 {cpInfo.shootingStar.length}</span>
                · <span className="pos">看涨吞没 {cpInfo.bullEngulf.length}</span> · <span className="neg">看跌吞没 {cpInfo.bearEngulf.length}</span>
                · <span className="pos">三兵 {cpInfo.threeSoldiers.length}</span> · <span className="neg">三鸦 {cpInfo.threeCrows.length}</span>
                · 光头光脚 {cpInfo.marubozu.length} · 十字 {cpInfo.doji.length}
              </span>
            </h6>
            <div className="kmuted" style={{ fontSize: 12 }}>
              单/双/三根形态，客户端由 OHLC 计算。锤子=长下影·小实体（看涨）、流星=长上影·小实体（看跌）、吞没=当前实体完全包住前一根（反向）、三兵/三鸦=三连阳/阴且每根开盘在前根实体内（强反转）、光头光脚=实体占满整根（强动量）、十字=开收几乎相等（犹豫）。箭头画在主图（红▲=看涨/绿▼=看跌），形态密度反映震荡程度，需结合趋势/位置确认。
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
