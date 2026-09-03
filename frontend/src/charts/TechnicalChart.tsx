import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AreaSeries,
  CandlestickSeries,
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
import { useTheme, type ChartPalette } from '../theme/ThemeContext'
import { buildFactorMap, sortByTradeDateAsc, timeKey, toCandleBars, toLinePoints, toVolumeBars } from './chartData'
import { formatNumber, formatPercent, pctClass } from '../utils/format'

export type MainChartView = 'price' | 'volume'
export type MainChartType = 'candlestick' | 'line'
export type IndicatorType = 'macd' | 'kdj' | 'rsi'

export const INDICATOR_LABELS: Record<IndicatorType, string> = {
  macd: 'MACD',
  kdj: 'KDJ',
  rsi: 'RSI',
}

/** 窗格高度（price 视图：主图+成交量+指标；volume 视图：成交量+指标） */
const PRICE_H = 340
const VOL_H = 100
const IND_H = 190

interface LegendData {
  open?: number | null
  high?: number | null
  low?: number | null
  close?: number | null
  pct?: number | null
  vol?: number | null
}

interface IndicatorLegendItem {
  label: string
  value: string
}

interface SeriesSpec {
  series: ISeriesApi<'Line'> | ISeriesApi<'Histogram'>
  label: string
  last: number | null
  decimals: number
}

function baseOptions(p: ChartPalette) {
  return {
    autoSize: true,
    layout: { background: { color: 'transparent' }, textColor: p.text, fontSize: 11 },
    grid: {
      vertLines: { color: p.gridVert },
      horzLines: { color: p.gridHorz },
    },
    crosshair: {
      mode: CrosshairMode.Normal,
      vertLine: { color: p.crosshair, width: 1 as const, style: LineStyle.Dashed, labelBackgroundColor: p.labelBg },
      horzLine: { color: p.crosshair, width: 1 as const, style: LineStyle.Dashed, labelBackgroundColor: p.labelBg },
    },
    rightPriceScale: { borderColor: p.border },
    timeScale: { borderColor: p.border, rightOffset: 2 },
    localization: { locale: 'zh-CN' },
  }
}

/** 数据 >90 根时初始显示最近 90 根（右留 2 格），否则全量展示 */
function applyInitialZoom(chart: IChartApi, count: number) {
  if (count > 90) {
    chart.timeScale().setVisibleLogicalRange({ from: count - 90, to: count + 2 })
  } else {
    chart.timeScale().fitContent()
  }
}

function addLevelLine(
  series: ISeriesApi<'Line'> | ISeriesApi<'Candlestick'> | ISeriesApi<'Area'>,
  price: number,
  color: string,
  title: string,
) {
  series.createPriceLine({
    price,
    color,
    lineWidth: 1,
    lineStyle: LineStyle.Dashed,
    axisLabelVisible: true,
    title,
  })
}

function addLine(
  chart: IChartApi,
  data: (WhitespaceData<Time> | LineData<Time>)[],
  paneIndex: number,
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
    paneIndex,
  )
  s.setData(data)
  return s
}

interface TechnicalChartProps {
  view: MainChartView
  chartType: MainChartType
  indicator: IndicatorType
  bollOverlay: boolean
  history: DailyBar[] | null
  factors: FactorRow[] | null
}

export default function TechnicalChart({ view, chartType, indicator, bollOverlay, history, factors }: TechnicalChartProps) {
  const { palette } = useTheme()
  const containerRef = useRef<HTMLDivElement | null>(null)
  const lastTimeRef = useRef<string | null>(null)
  const indSpecsRef = useRef<SeriesSpec[]>([])
  const [mainLegend, setMainLegend] = useState<LegendData | null>(null)
  const [indLegend, setIndLegend] = useState<IndicatorLegendItem[]>([])

  const bars = useMemo(() => toCandleBars(history ?? []), [history])
  const ascFactors = useMemo(() => sortByTradeDateAsc(factors ?? []), [factors])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const p = palette

    const chart = createChart(container, baseOptions(p))
    const barMap = new Map<string, LegendData>()
    const indSpecs: SeriesSpec[] = []
    indSpecsRef.current = indSpecs
    lastTimeRef.current = null

    const registerIndicator = (series: SeriesSpec['series'], label: string, decimals: number) => {
      indSpecs.push({ series, label, last: null, decimals })
    }

    // —— 主窗格：价格或成交量 ——
    if (view === 'volume') {
      const volMain = chart.addSeries(
        HistogramSeries,
        { priceFormat: { type: 'volume' }, lastValueVisible: false, priceLineVisible: false },
        0,
      )
      volMain.setData(toVolumeBars(history ?? [], p.upSoft, p.downSoft))
      for (const bar of bars) barMap.set(bar.time, { vol: bar.vol })
    } else {
      const priceSeries =
        chartType === 'line'
          ? chart.addSeries(
              AreaSeries,
              {
                lineColor: p.accent,
                topColor: 'rgba(129, 140, 248, 0.30)',
                bottomColor: 'rgba(129, 140, 248, 0.02)',
                lineWidth: 2,
                priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
              },
              0,
            )
          : chart.addSeries(
              CandlestickSeries,
              {
                upColor: p.up,
                downColor: p.down,
                borderUpColor: p.up,
                borderDownColor: p.down,
                wickUpColor: p.up,
                wickDownColor: p.down,
                priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
              },
              0,
            )

      if (chartType === 'line') {
        priceSeries.setData(toLinePoints(history ?? [], (b) => b.close))
        const closes = bars.map((b) => b.close)
        if (closes.length > 0) {
          addLevelLine(priceSeries, Math.max(...closes), p.up, `最高 ${Math.max(...closes).toFixed(2)}`)
          addLevelLine(priceSeries, Math.min(...closes), p.down, `最低 ${Math.min(...closes).toFixed(2)}`)
        }
      } else {
        priceSeries.setData(bars)
        const highs = bars.map((b) => b.high)
        const lows = bars.map((b) => b.low)
        if (highs.length > 0) {
          addLevelLine(priceSeries, Math.max(...highs), p.up, `最高 ${Math.max(...highs).toFixed(2)}`)
          addLevelLine(priceSeries, Math.min(...lows), p.down, `最低 ${Math.min(...lows).toFixed(2)}`)
        }
      }

      // 布林带主图叠加（按日期对齐因子，缺口 whitespace）
      if (bollOverlay) {
        const factorMap = buildFactorMap(factors ?? [])
        const upper: (WhitespaceData<Time> | LineData<Time>)[] = []
        const mid: (WhitespaceData<Time> | LineData<Time>)[] = []
        const lower: (WhitespaceData<Time> | LineData<Time>)[] = []
        for (const bar of bars) {
          const time = bar.time as Time
          const row = factorMap.get(bar.time)
          const push = (arr: (WhitespaceData<Time> | LineData<Time>)[], v: number | null | undefined) => {
            if (v === null || v === undefined || Number.isNaN(v)) arr.push({ time })
            else arr.push({ time, value: v })
          }
          push(upper, row?.boll_upper)
          push(mid, row?.boll_mid)
          push(lower, row?.boll_lower)
        }
        addLine(chart, upper, 0, { color: p.up, dashed: true })
        addLine(chart, mid, 0, { color: p.amber })
        addLine(chart, lower, 0, { color: p.down, dashed: true })
      }

      // 副窗格：成交量
      const volumeSeries = chart.addSeries(
        HistogramSeries,
        { priceFormat: { type: 'volume' }, lastValueVisible: false, priceLineVisible: false },
        1,
      )
      volumeSeries.setData(toVolumeBars(history ?? [], p.upSoft, p.downSoft))

      for (const bar of bars) {
        barMap.set(bar.time, {
          open: bar.open,
          high: bar.high,
          low: bar.low,
          close: bar.close,
          pct: bar.pct_chg,
          vol: bar.vol,
        })
      }
    }

    // —— 指标窗格 ——
    if (indicator === 'macd') {
      const paneIdx = view === 'price' ? 2 : 1
      const hist = chart.addSeries(
        HistogramSeries,
        { priceFormat: { type: 'price', precision: 4, minMove: 0.0001 }, lastValueVisible: false, priceLineVisible: false },
        paneIdx,
      )
      const histData: (WhitespaceData<Time> | HistogramData<Time>)[] = []
      for (const row of ascFactors) {
        const time = String(row.trade_date).slice(0, 10) as Time
        if (row.macd === null || row.macd === undefined || Number.isNaN(row.macd)) {
          histData.push({ time })
        } else {
          histData.push({ time, value: row.macd, color: row.macd >= 0 ? p.upSoft : p.downSoft })
        }
      }
      hist.setData(histData)
      hist.createPriceLine({
        price: 0,
        color: p.zeroLine,
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        axisLabelVisible: false,
        title: '',
      })
      const dif = addLine(chart, toLinePoints(ascFactors, (r) => r.macd_dif), paneIdx, { color: p.accent, precision: 4 })
      const dea = addLine(chart, toLinePoints(ascFactors, (r) => r.macd_dea), paneIdx, { color: p.amber, precision: 4 })
      registerIndicator(hist, 'MACD', 4)
      registerIndicator(dif, 'DIF', 4)
      registerIndicator(dea, 'DEA', 4)
    } else if (indicator === 'kdj') {
      const paneIdx = view === 'price' ? 2 : 1
      const k = addLine(chart, toLinePoints(ascFactors, (r) => r.kdj_k), paneIdx, { color: p.accent })
      const d = addLine(chart, toLinePoints(ascFactors, (r) => r.kdj_d), paneIdx, { color: p.teal })
      const j = addLine(chart, toLinePoints(ascFactors, (r) => r.kdj_j), paneIdx, { color: p.amber })
      addLevelLine(k, 80, p.up, '超买')
      addLevelLine(k, 20, p.down, '超卖')
      registerIndicator(k, 'K', 2)
      registerIndicator(d, 'D', 2)
      registerIndicator(j, 'J', 2)
    } else {
      const paneIdx = view === 'price' ? 2 : 1
      const r6 = addLine(chart, toLinePoints(ascFactors, (r) => r.rsi_6), paneIdx, { color: p.amber })
      const r12 = addLine(chart, toLinePoints(ascFactors, (r) => r.rsi_12), paneIdx, { color: p.violet })
      const r24 = addLine(chart, toLinePoints(ascFactors, (r) => r.rsi_24), paneIdx, { color: p.accent })
      addLevelLine(r6, 70, p.up, '超买')
      addLevelLine(r6, 30, p.down, '超卖')
      registerIndicator(r6, 'RSI6', 2)
      registerIndicator(r12, 'RSI12', 2)
      registerIndicator(r24, 'RSI24', 2)
    }

    // —— 窗格高度 ——
    const panes = chart.panes()
    if (view === 'price') {
      panes[0]?.setHeight(PRICE_H)
      panes[1]?.setHeight(VOL_H)
      panes[2]?.setHeight(IND_H)
    } else {
      panes[0]?.setHeight(PRICE_H)
      panes[1]?.setHeight(IND_H)
    }

    applyInitialZoom(chart, bars.length)

    // —— 十字光标：单实例内所有窗格联动，一次订阅同时驱动两个图例 ——
    const onCrosshairMove = (param: MouseEventParams<Time>) => {
      if (param.time === undefined) return
      const key = timeKey(param.time)
      if (!key || key === lastTimeRef.current) return
      lastTimeRef.current = key
      const bar = barMap.get(key)
      if (bar) setMainLegend(bar)
      setIndLegend(
        indSpecs.map((spec) => {
          const point = param.seriesData.get(spec.series) as { value?: number } | undefined
          const value = point && typeof point.value === 'number' ? point.value : spec.last
          return { label: spec.label, value: formatNumber(value ?? null, spec.decimals) }
        }),
      )
    }
    chart.subscribeCrosshairMove(onCrosshairMove)

    // 默认显示最后一根
    const lastBar = bars.length > 0 ? barMap.get(bars[bars.length - 1].time) : undefined
    if (lastBar) {
      lastTimeRef.current = bars[bars.length - 1].time
      setMainLegend(lastBar)
    }
    setIndLegend(
      indSpecs.map((spec) => {
        const points = spec.series.data()
        const lastPoint = points.length > 0 ? (points[points.length - 1] as { value?: number }) : undefined
        const value = typeof lastPoint?.value === 'number' ? lastPoint.value : spec.last
        return { label: spec.label, value: formatNumber(value ?? null, spec.decimals) }
      }),
    )

    return () => {
      chart.unsubscribeCrosshairMove(onCrosshairMove)
      chart.remove()
    }
  }, [view, chartType, indicator, bollOverlay, history, factors, bars, ascFactors, palette])

  const containerHeight = view === 'price' ? PRICE_H + VOL_H + IND_H + 12 : PRICE_H + IND_H + 8
  const indicatorLegendTop = view === 'price' ? PRICE_H + VOL_H + 22 : PRICE_H + 22

  return (
    <div className="chart-container" style={{ height: containerHeight }}>
      <div className="chart-legend main">
        {view === 'volume' ? (
          <span>量 {formatNumber((mainLegend?.vol ?? 0) / 10000, 2)} 万手</span>
        ) : mainLegend ? (
          <span>
            开 {formatNumber(mainLegend.open)} 高 {formatNumber(mainLegend.high)} 低 {formatNumber(mainLegend.low)}{' '}
            <span className={pctClass(mainLegend.pct)}>收 {formatNumber(mainLegend.close)}</span>{' '}
            <span className={pctClass(mainLegend.pct)}>{formatPercent(mainLegend.pct)}</span> 量{' '}
            {formatNumber((mainLegend.vol ?? 0) / 10000, 2)} 万手
          </span>
        ) : null}
      </div>
      <div className="chart-legend" style={{ top: indicatorLegendTop }}>
        {indLegend.map((item) => (
          <span key={item.label}>
            {item.label} {item.value}
          </span>
        ))}
      </div>
      <div ref={containerRef} style={{ height: '100%' }} />
    </div>
  )
}
