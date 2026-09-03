import { useEffect, useRef, useState } from 'react'
import {
  AreaSeries,
  CrosshairMode,
  LineStyle,
  createChart,
  type MouseEventParams,
  type Time,
} from 'lightweight-charts'
import type { DailyValue } from '../api/types'
import { useTheme } from '../theme/ThemeContext'
import { formatNumber, formatPercent, pctClass } from '../utils/format'

/** 回测资金曲线：面积图展示每日总资产（含现金+持仓） */
export default function EquityCurve({ dailyValues }: { dailyValues: DailyValue[] }) {
  const { palette } = useTheme()
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [legend, setLegend] = useState<{ value: number; pct: number } | null>(null)
  const initial = dailyValues.length > 0 ? dailyValues[0].total_value : 0

  useEffect(() => {
    const container = containerRef.current
    if (!container || dailyValues.length === 0) return
    const p = palette

    const chart = createChart(container, {
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
    })

    const series = chart.addSeries(
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
    series.setData(
      dailyValues
        .filter((d) => d.total_value !== null && !Number.isNaN(d.total_value))
        .map((d) => ({ time: String(d.date).slice(0, 10) as Time, value: d.total_value })),
    )
    // 基准线：初始资金
    series.createPriceLine({
      price: initial,
      color: p.zeroLine,
      lineWidth: 1,
      lineStyle: LineStyle.Dotted,
      axisLabelVisible: true,
      title: '初始资金',
    })

    if (dailyValues.length > 90) {
      chart.timeScale().setVisibleLogicalRange({ from: dailyValues.length - 90, to: dailyValues.length + 2 })
    } else {
      chart.timeScale().fitContent()
    }

    const update = (value: number | undefined) => {
      if (value === undefined) return
      const pct = initial ? (value - initial) / initial * 100 : 0
      setLegend({ value, pct })
    }

    const onCrosshairMove = (param: MouseEventParams<Time>) => {
      if (param.time === undefined || !param.point) return
      const point = param.seriesData.get(series) as { value?: number } | undefined
      update(point?.value)
    }
    chart.subscribeCrosshairMove(onCrosshairMove)

    const last = dailyValues[dailyValues.length - 1]
    if (last) update(last.total_value)

    return () => {
      chart.unsubscribeCrosshairMove(onCrosshairMove)
      chart.remove()
    }
  }, [dailyValues, palette, initial])

  return (
    <div className="chart-container" style={{ height: 320 }}>
      <div className="chart-legend main">
        {legend ? (
          <span>
            资产 ¥{formatNumber(legend.value, 2)}{' '}
            <span className={pctClass(legend.pct)}>{formatPercent(legend.pct)}</span>
          </span>
        ) : null}
      </div>
      <div ref={containerRef} style={{ height: '100%' }} />
    </div>
  )
}
