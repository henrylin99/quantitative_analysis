import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AreaSeries,
  CandlestickSeries,
  CrosshairMode,
  HistogramSeries,
  LineStyle,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type MouseEventParams,
  type Time,
} from 'lightweight-charts'
import type { DailyBar } from '../api/types'
import { formatNumber, formatPercent, pctClass } from '../utils/format'
import { toCandleBars, toVolumeBars, toLinePoints, timeKey, UP_COLOR, DOWN_COLOR, ACCENT_COLOR } from './chartData'

export type MainChartView = 'price' | 'volume'
export type MainChartType = 'candlestick' | 'line'

interface LegendData {
  open?: number | null
  high?: number | null
  low?: number | null
  close?: number | null
  pct?: number | null
  vol?: number | null
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
  title: string,
  color: string,
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

interface MainChartProps {
  view: MainChartView
  chartType: MainChartType
  history: DailyBar[] | null
}

export default function MainChart({ view, chartType, history }: MainChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const barMapRef = useRef<Map<string, LegendData>>(new Map())
  const lastTimeRef = useRef<string | null>(null)
  const [legend, setLegend] = useState<LegendData | null>(null)

  // 主图与指标图都直接消费 API 原始数组，这里统一转升序
  const bars = useMemo(() => toCandleBars(history ?? []), [history])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const chart = createChart(container, baseOptions())
    chartRef.current = chart
    const barMap = new Map<string, LegendData>()
    barMapRef.current = barMap
    lastTimeRef.current = null

    if (view === 'volume') {
      // 成交量视图：单窗格柱状
      const series = chart.addSeries(
        HistogramSeries,
        {
          priceFormat: { type: 'volume' },
          lastValueVisible: false,
          priceLineVisible: false,
        },
        0,
      )
      series.setData(toVolumeBars(history ?? []))
      for (const bar of bars) barMap.set(bar.time, { vol: bar.vol })
    } else {
      const priceSeries =
        chartType === 'line'
          ? chart.addSeries(
              AreaSeries,
              {
                lineColor: ACCENT_COLOR,
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
                upColor: UP_COLOR,
                downColor: DOWN_COLOR,
                borderUpColor: UP_COLOR,
                borderDownColor: DOWN_COLOR,
                wickUpColor: UP_COLOR,
                wickDownColor: DOWN_COLOR,
                priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
              },
              0,
            )

      const candleBars = bars
      if (chartType === 'line') {
        priceSeries.setData(toLinePoints(history ?? [], (b) => b.close))
        const closes = candleBars.map((b) => b.close)
        if (closes.length > 0) {
          addLevelLine(priceSeries, Math.max(...closes), `最高 ${Math.max(...closes).toFixed(2)}`, UP_COLOR)
          addLevelLine(priceSeries, Math.min(...closes), `最低 ${Math.min(...closes).toFixed(2)}`, DOWN_COLOR)
        }
      } else {
        priceSeries.setData(candleBars)
        const highs = candleBars.map((b) => b.high)
        const lows = candleBars.map((b) => b.low)
        if (highs.length > 0) {
          addLevelLine(priceSeries, Math.max(...highs), `最高 ${Math.max(...highs).toFixed(2)}`, UP_COLOR)
          addLevelLine(priceSeries, Math.min(...lows), `最低 ${Math.min(...lows).toFixed(2)}`, DOWN_COLOR)
        }
      }

      // 副图：成交量（pane 1，高度 110）
      const volumeSeries = chart.addSeries(
        HistogramSeries,
        { priceFormat: { type: 'volume' }, lastValueVisible: false, priceLineVisible: false },
        1,
      )
      volumeSeries.setData(toVolumeBars(history ?? []))
      const volumePane = chart.panes()[1]
      if (volumePane) volumePane.setHeight(110)

      for (const bar of candleBars) {
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

    applyInitialZoom(chart, bars.length)

    const updateLegend = (time: unknown) => {
      const key = timeKey(time)
      if (!key || key === lastTimeRef.current) return
      const bar = barMap.get(key)
      if (bar) {
        lastTimeRef.current = key
        setLegend(bar)
      }
    }

    const onCrosshairMove = (param: MouseEventParams<Time>) => {
      if (param.time === undefined) return
      updateLegend(param.time)
    }
    chart.subscribeCrosshairMove(onCrosshairMove)

    // 默认显示最后一根
    const lastBar = bars.length > 0 ? barMap.get(bars[bars.length - 1].time) : undefined
    if (lastBar) {
      lastTimeRef.current = bars[bars.length - 1].time
      setLegend(lastBar)
    }

    return () => {
      chart.unsubscribeCrosshairMove(onCrosshairMove)
      chart.remove()
      chartRef.current = null
    }
  }, [view, chartType, history, bars])

  return (
    <div className="chart-container">
      <div className="chart-legend">
        {view === 'volume' ? (
          <span>量 {formatNumber((legend?.vol ?? 0) / 10000, 2)} 万手</span>
        ) : legend ? (
          <span>
            开 {formatNumber(legend.open)} 高 {formatNumber(legend.high)} 低 {formatNumber(legend.low)}{' '}
            <span className={pctClass(legend.pct)}>收 {formatNumber(legend.close)}</span>{' '}
            <span className={pctClass(legend.pct)}>{formatPercent(legend.pct)}</span> 量{' '}
            {formatNumber((legend.vol ?? 0) / 10000, 2)} 万手
          </span>
        ) : null}
      </div>
      <div ref={containerRef} className="chart-target" />
    </div>
  )
}
