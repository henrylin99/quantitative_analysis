import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export type ThemeMode = 'dark' | 'light'

/** lightweight-charts 需要具体色值，不能吃 CSS 变量；两套调色板随主题切换，图表组件依赖 palette 重建 */
export interface ChartPalette {
  text: string
  gridVert: string
  gridHorz: string
  border: string
  crosshair: string
  labelBg: string
  up: string
  down: string
  upSoft: string
  downSoft: string
  accent: string
  amber: string
  teal: string
  violet: string
  zeroLine: string
}

const DARK: ChartPalette = {
  text: '#93a0b8',
  gridVert: 'rgba(148, 163, 184, 0.08)',
  gridHorz: 'rgba(148, 163, 184, 0.12)',
  border: '#2a3650',
  crosshair: '#64748b',
  labelBg: '#334155',
  up: '#f87171',
  down: '#4ade80',
  upSoft: 'rgba(248, 113, 113, 0.7)',
  downSoft: 'rgba(74, 222, 128, 0.7)',
  accent: '#818cf8',
  amber: '#fbbf24',
  teal: '#34d399',
  violet: '#a78bfa',
  zeroLine: '#475569',
}

const LIGHT: ChartPalette = {
  text: '#5b6577',
  gridVert: 'rgba(15, 23, 42, 0.06)',
  gridHorz: 'rgba(15, 23, 42, 0.1)',
  border: '#d7dde9',
  crosshair: '#94a3b8',
  labelBg: '#475569',
  up: '#dc2626',
  down: '#16a34a',
  upSoft: 'rgba(220, 38, 38, 0.65)',
  downSoft: 'rgba(22, 163, 74, 0.65)',
  accent: '#6366f1',
  amber: '#d97706',
  teal: '#0d9488',
  violet: '#7c3aed',
  zeroLine: '#94a3b8',
}

interface ThemeCtx {
  mode: ThemeMode
  toggle: () => void
  palette: ChartPalette
}

const Ctx = createContext<ThemeCtx>({ mode: 'dark', toggle: () => {}, palette: DARK })

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>('dark')

  useEffect(() => {
    const root = document.documentElement
    root.setAttribute('data-theme', mode)
    root.setAttribute('data-bs-theme', mode)
  }, [mode])

  const value = useMemo<ThemeCtx>(
    () => ({
      mode,
      toggle: () => setMode((m) => (m === 'dark' ? 'light' : 'dark')),
      palette: mode === 'dark' ? DARK : LIGHT,
    }),
    [mode],
  )

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useTheme(): ThemeCtx {
  return useContext(Ctx)
}
