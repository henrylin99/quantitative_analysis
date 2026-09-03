import { NavLink, Route, Routes } from 'react-router-dom'
import StocksPage from './pages/StocksPage'
import AnalysisPage from './pages/AnalysisPage'
import ScreenPage from './pages/ScreenPage'
import BacktestPage from './pages/BacktestPage'
import HomePage from './pages/HomePage'

/** 旧版 Flask 前端地址：开发态 Vite 与 Flask 不同端口，直接指向 5000；构建产物由 Flask 同源托管时为空串 */
export const OLD_SITE_BASE = import.meta.env.DEV ? 'http://127.0.0.1:5000' : ''

const NAV_ITEMS = [
  { to: '/', label: '首页', end: true },
  { to: '/stocks', label: '股票列表', end: false },
  { to: '/analysis', label: '技术分析', end: false },
  { to: '/screen', label: '选股筛选', end: false },
  { to: '/backtest', label: '回测验证', end: false },
]

export default function App() {
  return (
    <>
      <header className="app-topbar">
        <div className="topbar-inner">
          <NavLink className="brand" to="/">
            <span className="brand-mark">Q</span>
            <span className="brand-text">
              量化分析终端
              <small>REACT EDITION</small>
            </span>
          </NavLink>
          <nav className="topnav">
            {NAV_ITEMS.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end} className="topnav-link">
                {item.label}
              </NavLink>
            ))}
          </nav>
          <a className="btn-ghost" href={`${OLD_SITE_BASE}/`}>
            旧版 ↗
          </a>
        </div>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/stocks" element={<StocksPage />} />
          <Route path="/analysis" element={<AnalysisPage />} />
          <Route path="/screen" element={<ScreenPage />} />
          <Route path="/backtest" element={<BacktestPage />} />
        </Routes>
      </main>
    </>
  )
}
