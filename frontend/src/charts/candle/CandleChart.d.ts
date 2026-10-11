import type { ComponentType } from 'react'

export interface KBar {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface OverlayLine {
  color: string
  lineWidth?: number
  label?: string
  dots?: boolean
  points: Array<{ time: number; value: number }>
}

export interface PaneSpec {
  lines?: Array<{ color: string; label?: string; lineWidth?: number; points: Array<{ time: number; value: number }> }>
  hist?: { points: Array<{ time: number; value: number }> }
  refs?: Array<{ price: number; color: string }>
}

export interface PriceLineSpec {
  price: number
  color: string
  lineWidth?: number
  lineStyle?: number
  title?: string
}

export interface DivEvent {
  type: 'bull' | 'bear'
  aTime: number
  aPrice: number
  bTime: number
  bPrice: number
}

export interface PatternMarker {
  time: number
  position: string
  color: string
  shape: string
  text: string
}

interface CandleChartProps {
  bars?: KBar[]
  patterns?: PatternMarker[]
  overlays?: OverlayLine[]
  panes?: PaneSpec[]
  priceLines?: PriceLineSpec[]
  showVolume?: boolean
  showVP?: boolean
  height?: number
  title?: string
  chartType?: string
  logScale?: boolean
  magnet?: boolean
  range?: number | null
  divergence?: DivEvent[]
}

declare const CandleChart: ComponentType<CandleChartProps>
export default CandleChart

export declare const UP_COLOR: string
export declare const DOWN_COLOR: string
