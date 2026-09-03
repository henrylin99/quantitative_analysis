import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { BarChart, GaugeChart, HeatmapChart, PieChart, RadarChart, TreemapChart } from 'echarts/charts'
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useTheme, type ChartPalette } from '../theme/ThemeContext'

echarts.use([
  BarChart,
  GaugeChart,
  HeatmapChart,
  PieChart,
  RadarChart,
  TreemapChart,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapComponent,
  CanvasRenderer,
])

/** 按当前主题派生的 ECharts 基础样式，与旧版 financial 主题观感对齐 */
export function echartsTheme(p: ChartPalette) {
  return {
    textStyle: { color: p.text, fontFamily: 'inherit' },
    color: [p.accent, p.violet, p.teal, p.amber, '#22d3ee', p.up, '#a78bfa', '#34d399'],
    backgroundColor: 'transparent',
    tooltip: {
      backgroundColor: p.labelBg,
      borderColor: p.border,
      textStyle: { color: p.text, fontSize: 12 },
    },
    categoryAxis: {
      axisLine: { lineStyle: { color: p.border } },
      axisLabel: { color: p.text },
      splitLine: { show: false },
    },
    valueAxis: {
      axisLine: { show: false },
      axisLabel: { color: p.text },
      splitLine: { lineStyle: { color: p.gridHorz } },
    },
    legend: { textStyle: { color: p.text } },
  }
}

interface EChartProps {
  option: Record<string, unknown> | null
  height?: number
  onClick?: (params: Record<string, unknown>) => void
  /** 变化时调用 chart.resize（父容器尺寸变化场景） */
  onReady?: (chart: echarts.ECharts) => void
}

/** ECharts React 薄封装：主题切换时整图重建（option 内引用 palette 即可联动重绘） */
export default function EChart({ option, height = 360, onClick, onReady }: EChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)
  const onClickRef = useRef(onClick)
  onClickRef.current = onClick
  const { palette } = useTheme()

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const chart = echarts.init(el)
    chart.on('click', (params) => onClickRef.current?.(params as unknown as Record<string, unknown>))
    chartRef.current = chart
    onReady?.(chart)
    const onResize = () => chart.resize()
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      chart.dispose()
      chartRef.current = null
    }
    // palette 变化时重建实例，保证主题切换后颜色全部刷新
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [palette])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart || !option) return
    chart.setOption({ ...echartsTheme(palette), ...option } as never, { notMerge: true })
  }, [option, palette])

  return <div ref={containerRef} style={{ width: '100%', height }} />
}
