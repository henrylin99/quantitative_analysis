import { NavLink, Route, Routes } from 'react-router-dom'
import StocksPage from './pages/StocksPage'
import AnalysisPage from './pages/AnalysisPage'
import ScreenPage from './pages/ScreenPage'
import BacktestPage from './pages/BacktestPage'
import HomePage from './pages/HomePage'

/** 旧版 Flask 前端地址：开发态 Vite 与 Flask 不同端口，直接指向 5000；构建产物由 Flask 同源托管时为空串 */
export const OLD_SITE_BASE = import.meta.env.DEV ? 'http://127.0.0.1:5000' : ''

export default function App() {
  return (
    <>
      <nav className="navbar navbar-expand-lg navbar-financial fixed-top">
        <div className="container-fluid">
          <NavLink className="navbar-brand" to="/">
            📈 量化分析系统 <span className="badge text-bg-primary">React</span>
          </NavLink>
          <button
            className="navbar-toggler"
            type="button"
            data-bs-toggle="collapse"
            data-bs-target="#main-nav"
            aria-controls="main-nav"
            aria-expanded="false"
            aria-label="切换导航"
          >
            <span className="navbar-toggler-icon" />
          </button>
          <div className="collapse navbar-collapse" id="main-nav">
            <ul className="navbar-nav me-auto">
              <li className="nav-item">
                <NavLink className="nav-link" to="/" end>
                  首页
                </NavLink>
              </li>
              <li className="nav-item">
                <NavLink className="nav-link" to="/stocks">
                  股票列表
                </NavLink>
              </li>
              <li className="nav-item">
                <NavLink className="nav-link" to="/analysis">
                  技术分析
                </NavLink>
              </li>
              <li className="nav-item">
                <NavLink className="nav-link" to="/screen">
                  选股筛选
                </NavLink>
              </li>
              <li className="nav-item">
                <NavLink className="nav-link" to="/backtest">
                  回测验证
                </NavLink>
              </li>
            </ul>
            <span className="navbar-text">
              <a className="btn btn-outline-light btn-sm" href={`${OLD_SITE_BASE}/`}>
                打开旧版
              </a>
            </span>
          </div>
        </div>
      </nav>
      <main className="main-content">
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
