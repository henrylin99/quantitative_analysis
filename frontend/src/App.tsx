import { NavLink, Route, Routes } from 'react-router-dom'
import { ThemeProvider, useTheme } from './theme/ThemeContext'
import StocksPage from './pages/StocksPage'
import AnalysisPage from './pages/AnalysisPage'
import ScreenPage from './pages/ScreenPage'
import BacktestPage from './pages/BacktestPage'
import HomePage from './pages/HomePage'

/** 旧版 Flask 前端地址：开发态 Vite 与 Flask 不同端口，直接指向 5000；构建产物由 Flask 同源托管时为空串 */
export const OLD_SITE_BASE = import.meta.env.DEV ? 'http://127.0.0.1:5000' : ''

const NAV_ITEMS = [
  { to: '/', label: '首页', icon: '🏠', end: true },
  { to: '/stocks', label: '股票列表', icon: '📋', end: false },
  { to: '/analysis', label: '技术分析', icon: '📈', end: false },
  { to: '/screen', label: '选股筛选', icon: '🔍', end: false },
  { to: '/backtest', label: '回测验证', icon: '🧪', end: false },
]

function Shell() {
  const { mode, toggle } = useTheme()
  return (
    <>
      <aside className="app-sidebar">
        <NavLink className="brand" to="/">
          <span className="brand-mark">Q</span>
          <span className="brand-text">
            量化分析终端
            <small>REACT EDITION</small>
          </span>
        </NavLink>
        <nav className="side-nav">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className="side-link">
              <span className="ico">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <button type="button" className="theme-toggle" onClick={toggle}>
            <span className="ico">{mode === 'dark' ? '☀️' : '🌙'}</span>
            {mode === 'dark' ? '浅色模式' : '深色模式'}
          </button>
          <a className="btn-ghost" href={`${OLD_SITE_BASE}/`}>
            <span className="ico">↗</span> 旧版
          </a>
        </div>
      </aside>
      <div className="app-body">
        <main className="app-main">
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/stocks" element={<StocksPage />} />
            <Route path="/analysis" element={<AnalysisPage />} />
            <Route path="/screen" element={<ScreenPage />} />
            <Route path="/backtest" element={<BacktestPage />} />
          </Routes>
        </main>
      </div>
    </>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <Shell />
    </ThemeProvider>
  )
}
