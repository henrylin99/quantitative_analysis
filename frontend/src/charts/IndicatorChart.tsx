import { useEffect, useMemo, useRef, useState } from 'react'
import {
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type MouseEventParams,
  type Time,
  type WhitespaceData,
} from 'lightweight-charts'
import type { DailyBar, FactorRow } from '../api/types'
import {
  ACCENT_COLOR,
  AMBER_COLOR,
  DOWN_COLOR,
  UP_COLOR,
  buildFactorMap,
  sortByTradeDateAsc,
  timeKey,
  toLinePoints,
} from './chartData'
import { formatNumber } from '../utils/format'

export type IndicatorType = 'macd' | 'kdj' | 'rsi' | 'boll'

export const INDICATOR_TITLES: Record<IndicatorType, string> = {
  macd: '📈 MACD指标',
  kdj: '📊 KDJ指标',
  rsi: '📉 RSI指标',
  boll: '📊 布林带指标',
}

function baseOptions() {
  return {
    autoSize: true,
    layout: { background: { color: 'transparent' }, textColor: '#94a3b8', fontSize: 11 },
    grid: {
      vertLines: { color: 'rgba(51, 65, 85, 0.25)' },
      horzLines: { color: 'rgba(51, 65, 85, 0.35)' },
    },
    crosshair: {
      mode: CrosshairMode.Normal,
      vertLine: { color: '#64748b', width: 1 as const, style: LineStyle.Dashed, labelBackgroundColor: '#334155' },
      horzLine: { color: '#64748b', width: 1 as const, style: LineStyle.Dashed, labelBackgroundColor: '#334155' },
    },
    rightPriceScale: { borderColor: '#334155' },
    timeScale: { borderColor: '#334155', rightOffset: 2 },
    localization: { locale: 'zh-CN' },
  }
}

function applyInitialZoom(chart: IChartApi, count: number) {
  if (count > 90) {
    chart.timeScale().setVisibleLogicalRange({ from: count - 90, to: count + 2 })
  } else {
    chart.timeScale().fitContent()
  }
}

interface LegendItem {
  label: string
  value: string
}

interface SeriesSpec {
  series: ISeriesApi<'Line'> | ISeriesApi<'Histogram'>
  label: string
  last: number | null
  decimals: number
}

function addLine(
  chart: IChartApi,
  data: (WhitespaceData<Time> | LineData<Time>)[],
  opts: { color: string; width?: 1 | 2 | 3 | 4; dashed?: boolean; precision?: number },
): ISeriesApi<'Line'> {
  const precision = opts.precision == null ? 2 : opts.precision
  const s = chart.addSeries(
    LineSeries,
    {
      color: opts.color,
      lineWidth: opts.width ?? 1,
      lineStyle: opts.dashed ? LineStyle.Dashed : LineStyle.Solid,
      priceFormat: { type: 'price', precision, minMove: Math.pow(10, -precision) },
      lastValueVisible: false,
      priceLineVisible: false,
    },
    0,
  )
  s.setData(data)
  return s
}

function addLevelLine(series: ISeriesApi<'Line'>, price: number, color: string, title: string) {
  series.createPriceLine({
    price,
    color,
    lineWidth: 1,
    lineStyle: LineStyle.Dashed,
    axisLabelVisible: true,
    title,
  })
}

interface IndicatorChartProps {
  indicator: IndicatorType
  history: DailyBar[] | null
  factors: FactorRow[] | null
}

export default function IndicatorChart({ indicator, history, factors }: IndicatorChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const lastTimeRef = useRef<string | null>(null)
  const specsRef = useRef<SeriesSpec[]>([])
  const [legend, setLegend] = useState<LegendItem[]>([])

  const ascHistory = useMemo(() => sortByTradeDateAsc(history ?? []), [history])
  const ascFactors = useMemo(() => sortByTradeDateAsc(factors ?? []), [factors])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const chart = createChart(container, baseOptions())
    const specs: SeriesSpec[] = []
    specsRef.current = specs
    lastTimeRef.current = null

    const register = (series: SeriesSpec['series'], label: string, last: number | null, decimals: number) => {
      specs.push({ series, label, last, decimals })
    }

    if (indicator === 'macd') {
      const hist = chart.addSeries(
        HistogramSeries,
        { priceFormat: { type: 'price', precision: 4, minMove: 0.0001 }, lastValueVisible: false, priceLineVisible: false },
        0,
      )
      const histData: (WhitespaceData<Time> | HistogramData<Time>)[] = []
      let lastMacd: number | null = null
      for (const row of ascFactors) {
        const time = String(row.trade_date).slice(0, 10) as Time
        if (row.macd === null || row.macd === undefined || Number.isNaN(row.macd)) {
          histData.push({ time })
        } else {
          lastMacd = row.macd
          histData.push({ time, value: row.macd, color: row.macd >= 0 ? 'rgba(248,113,113,0.7)' : 'rgba(74,222,128,0.7)' })
        }
      }
      hist.setData(histData)
      hist.createPriceLine({
        price: 0,
        color: '#475569',
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        axisLabelVisible: false,
        title: '',
      })
      const dif = addLine(chart, toLinePoints(ascFactors, (r) => r.macd_dif), { color: ACCENT_COLOR, precision: 4 })
      const dea = addLine(chart, toLinePoints(ascFactors, (r) => r.macd_dea), { color: AMBER_COLOR, precision: 4 })
      register(hist, 'MACD', lastMacd, 4)
      register(dif, 'DIF', null, 4)
      register(dea, 'DEA', null, 4)
    } else if (indicator === 'kdj') {
      const k = addLine(chart, toLinePoints(ascFactors, (r) => r.kdj_k), { color: ACCENT_COLOR })
      const d = addLine(chart, toLinePoints(ascFactors, (r) => r.kdj_d), { color: '#34d399' })
      const j = addLine(chart, toLinePoints(ascFactors, (r) => r.kdj_j), { color: AMBER_COLOR })
      addLevelLine(k, 80, UP_COLOR, '超买')
      addLevelLine(k, 20, DOWN_COLOR, '超卖')
      register(k, 'K', null, 2)
      register(d, 'D', null, 2)
      register(j, 'J', null, 2)
    } else if (indicator === 'rsi') {
      const r6 = addLine(chart, toLinePoints(ascFactors, (r) => r.rsi_6), { color: AMBER_COLOR })
      const r12 = addLine(chart, toLinePoints(ascFactors, (r) => r.rsi_12), { color: '#a78bfa' })
      const r24 = addLine(chart, toLinePoints(ascFactors, (r) => r.rsi_24), { color: ACCENT_COLOR })
      addLevelLine(r6, 70, UP_COLOR, '超买')
      addLevelLine(r6, 30, DOWN_COLOR, '超卖')
      register(r6, 'RSI6', null, 2)
      register(r12, 'RSI12', null, 2)
      register(r24, 'RSI24', null, 2)
    } else {
      // 布林带：以 history 为时间轴，因子按日期对齐，缺口输出 whitespace
      const factorMap = buildFactorMap(factors ?? [])
      const aligned = ascHistory.map((bar) => factorMap.get(String(bar.trade_date).slice(0, 10)))
      const closeData = toLinePoints(ascHistory, (b) => b.close)
      const upperData: (WhitespaceData<Time> | LineData<Time>)[] = []
      const midData: (WhitespaceData<Time> | LineData<Time>)[] = []
      const lowerData: (WhitespaceData<Time> | LineData<Time>)[] = []
      ascHistory.forEach((bar, i) => {
        const time = String(bar.trade_date).slice(0, 10) as Time
        const row = aligned[i]
        const push = (arr: (WhitespaceData<Time> | LineData<Time>)[], v: number | null | undefined) => {
          if (v === null || v === undefined || Number.isNaN(v)) arr.push({ time })
          else arr.push({ time, value: v })
        }
        push(upperData, row?.boll_upper)
        push(midData, row?.boll_mid)
        push(lowerData, row?.boll_lower)
      })
      const close = addLine(chart, closeData, { color: ACCENT_COLOR, width: 2 })
      const upper = addLine(chart, upperData, { color: UP_COLOR, dashed: true })
      const mid = addLine(chart, midData, { color: AMBER_COLOR })
      const lower = addLine(chart, lowerData, { color: DOWN_COLOR, dashed: true })
      register(close, '收盘', null, 2)
      register(upper, '上轨', null, 2)
      register(mid, '中轨', null, 2)
      register(lower, '下轨', null, 2)
    }

    applyInitialZoom(chart, indicator === 'boll' ? ascHistory.length : ascFactors.length)

    const onCrosshairMove = (param: MouseEventParams<Time>) => {
      if (param.time === undefined) return
      const key = timeKey(param.time)
      if (!key || key === lastTimeRef.current) return
      lastTimeRef.current = key
      setLegend(
        specs.map((spec) => {
          const point = param.seriesData.get(spec.series) as { value?: number } | undefined
          const value = point && typeof point.value === 'number' ? point.value : spec.last
          return { label: spec.label, value: formatNumber(value ?? null, spec.decimals) }
        }),
      )
    }
    chart.subscribeCrosshairMove(onCrosshairMove)

    // 默认显示最后一根
    const lastTime = (indicator === 'boll' ? ascHistory[ascHistory.length - 1]?.trade_date : ascFactors[ascFactors.length - 1]?.trade_date) as
      | string
      | undefined
    if (lastTime) {
      lastTimeRef.current = String(lastTime).slice(0, 10)
      setLegend(
        specs.map((spec) => {
          const dataPoints = spec.series.data()
          const lastPoint = dataPoints.length > 0 ? (dataPoints[dataPoints.length - 1] as { value?: number }) : undefined
          const value = typeof lastPoint?.value === 'number' ? lastPoint.value : spec.last
          return { label: spec.label, value: formatNumber(value ?? null, spec.decimals) }
        }),
      )
    }

    return () => {
      chart.unsubscribeCrosshairMove(onCrosshairMove)
      chart.remove()
    }
  }, [indicator, ascHistory, ascFactors])

  return (
    <div className="chart-container indicator">
      <div className="chart-legend">
        {legend.map((item) => (
          <span key={item.label} style={{ marginRight: 10 }}>
            {item.label} {item.value}
          </span>
        ))}
      </div>
      <div ref={containerRef} className="chart-target" />
    </div>
  )
}
