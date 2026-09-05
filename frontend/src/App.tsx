import { NavLink, Route, Routes } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { ThemeProvider, useTheme } from './theme/ThemeContext'
import StocksPage from './pages/StocksPage'
import AnalysisPage from './pages/AnalysisPage'
import ScreenPage from './pages/ScreenPage'
import BacktestPage from './pages/BacktestPage'
import HomePage from './pages/HomePage'
import StockDetailPage from './pages/StockDetailPage'
import FeatureIntroPage from './pages/FeatureIntroPage'
import HeatmapPage from './pages/HeatmapPage'
import PatternScreenPage from './pages/PatternScreenPage'
import MoneyflowPage from './pages/MoneyflowPage'
import MarketBriefPage from './pages/MarketBriefPage'
import FinancialHealthPage from './pages/FinancialHealthPage'
import StockRadarPage from './pages/StockRadarPage'
import StockPanoramaPage from './pages/StockPanoramaPage'
import DataManagementPage from './pages/DataManagementPage'
import MlFactorIndexPage from './pages/MlFactorIndexPage'
import MlModelsPage from './pages/MlModelsPage'
import MlScoringPage from './pages/MlScoringPage'
import MlPortfolioPage from './pages/MlPortfolioPage'
import MlAnalysisPage from './pages/MlAnalysisPage'
import MlBacktestPage from './pages/MlBacktestPage'
import RtIndicatorsPage from './pages/RtIndicatorsPage'
import RtSignalsPage from './pages/RtSignalsPage'
import RtMonitorPage from './pages/RtMonitorPage'
import RtRiskPage from './pages/RtRiskPage'
import RtReportsPage from './pages/RtReportsPage'
import RtWebsocketPage from './pages/RtWebsocketPage'
import AiWorkbenchPage from './pages/AiWorkbenchPage'
import Text2SqlPage from './pages/Text2SqlPage'

// 新版设计体系页面（tailwind token 体系），lazy 分割不增加旧页面首屏
const MarketDashboardPage = lazy(() => import('./pages/MarketDashboardPage'))
const WatchlistPage = lazy(() => import('./pages/WatchlistPage'))
const DragonTigerPage = lazy(() => import('./pages/DragonTigerPage'))
const LimitUpLadderPage = lazy(() => import('./pages/LimitUpLadderPage'))
const HotStocksPage = lazy(() => import('./pages/HotStocksPage'))
const ConceptAnalysisPage = lazy(() => import('./pages/ConceptAnalysisPage'))
const IndustryAnalysisPage = lazy(() => import('./pages/IndustryAnalysisPage'))
const DataSourceCenterPage = lazy(() => import('./pages/DataSourceCenterPage'))

/** 旧版 Flask 前端地址：开发态 Vite 与 Flask 不同端口，直接指向 5000；构建产物由 Flask 同源托管时为空串 */
export const OLD_SITE_BASE = import.meta.env.DEV ? 'http://127.0.0.1:5000' : ''

interface NavLeaf {
  to: string
  label: string
  icon: string
  end?: boolean
}

interface NavGroup {
  label: string
  items: NavLeaf[]
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: '概览',
    items: [{ to: '/', label: '首页', icon: '🏠', end: true }],
  },
  {
    label: '核心分析',
    items: [
      { to: '/stocks', label: '股票列表', icon: '📋' },
      { to: '/analysis', label: '技术分析', icon: '📈' },
      { to: '/screen', label: '选股筛选', icon: '🔍' },
      { to: '/backtest', label: '策略回测', icon: '🧪' },
    ],
  },
  {
    label: '多因子模型',
    items: [
      { to: '/ml-factor', label: '因子管理', icon: '🧬', end: true },
      { to: '/ml-factor/models', label: '模型管理', icon: '🤖' },
      { to: '/ml-factor/scoring', label: '股票评分', icon: '⭐' },
      { to: '/ml-factor/portfolio', label: '投资组合', icon: '💼' },
      { to: '/ml-factor/analysis', label: '分析报告', icon: '📊' },
      { to: '/ml-factor/backtest', label: '组合回测', icon: '🏁' },
    ],
  },
  {
    label: '实时分析',
    items: [
      { to: '/realtime-analysis/indicators', label: '技术指标', icon: '⏱️' },
      { to: '/realtime-analysis/signals', label: '交易信号', icon: '🚦' },
      { to: '/realtime-analysis/monitor', label: '实时监控', icon: '📡' },
      { to: '/realtime-analysis/risk', label: '风险管理', icon: '🛡️' },
      { to: '/realtime-analysis/reports', label: '报告管理', icon: '📄' },
      { to: '/realtime-analysis/websocket', label: '推送管理', icon: '🔌' },
    ],
  },
  {
    label: '市场',
    items: [
      { to: '/market/dashboard', label: '市场看板', icon: '📊' },
      { to: '/market/watchlist', label: '自选行情', icon: '⭐' },
      { to: '/market/limit-up', label: '连板天梯', icon: '🔥' },
      { to: '/market/hot', label: '热股榜单', icon: '📈' },
      { to: '/market/concepts', label: '概念分析', icon: '💡' },
      { to: '/market/industries', label: '行业分析', icon: '🏭' },
      { to: '/market/dragon-tiger', label: '龙虎榜', icon: '🐉' },
    ],
  },
  {
    label: '数据',
    items: [
      { to: '/data-management', label: '数据管理', icon: '🗄️' },
      { to: '/datasources', label: '数据源中心', icon: '🧭' },
    ],
  },
  {
    label: '试用工具',
    items: [
      { to: '/heatmap', label: '板块热力图', icon: '🔥' },
      { to: '/pattern-screen', label: '形态选股', icon: '🎯' },
      { to: '/moneyflow', label: '资金流统计', icon: '💰' },
      { to: '/market-brief', label: '市场简报', icon: '📰' },
      { to: '/financial-health', label: '财务健康', icon: '❤️' },
      { to: '/stock-radar', label: '个股雷达', icon: '🛰️' },
      { to: '/stock-panorama', label: '个股全景', icon: '🗂️' },
      { to: '/feature-intro', label: '功能介绍', icon: '📖' },
    ],
  },
  {
    label: 'AI 助手',
    items: [
      { to: '/ai-workbench', label: 'AI 工作台', icon: '🧠' },
      { to: '/text2sql', label: '智能查数', icon: '💬' },
    ],
  },
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
          {NAV_GROUPS.map((group) => (
            <div className="side-group" key={group.label}>
              <div className="side-group-label">{group.label}</div>
              {group.items.map((item) => (
                <NavLink key={item.to} to={item.to} end={item.end} className="side-link">
                  <span className="ico">{item.icon}</span>
                  {item.label}
                </NavLink>
              ))}
            </div>
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
            <Route path="/stock/:tsCode" element={<StockDetailPage />} />
            <Route path="/analysis" element={<AnalysisPage />} />
            <Route path="/screen" element={<ScreenPage />} />
            <Route path="/backtest" element={<BacktestPage />} />
            <Route path="/heatmap" element={<HeatmapPage />} />
            <Route path="/pattern-screen" element={<PatternScreenPage />} />
            <Route path="/moneyflow" element={<MoneyflowPage />} />
            <Route path="/market-brief" element={<MarketBriefPage />} />
            <Route path="/financial-health" element={<FinancialHealthPage />} />
            <Route path="/stock-radar" element={<StockRadarPage />} />
            <Route path="/stock-panorama" element={<StockPanoramaPage />} />
            <Route path="/feature-intro" element={<FeatureIntroPage />} />
            <Route path="/data-management" element={<DataManagementPage />} />
            <Route
              path="/market/dashboard"
              element={
                <Suspense fallback={null}>
                  <MarketDashboardPage />
                </Suspense>
              }
            />
            <Route
              path="/market/watchlist"
              element={
                <Suspense fallback={null}>
                  <WatchlistPage />
                </Suspense>
              }
            />
            <Route
              path="/market/dragon-tiger"
              element={
                <Suspense fallback={null}>
                  <DragonTigerPage />
                </Suspense>
              }
            />
            <Route
              path="/market/limit-up"
              element={
                <Suspense fallback={null}>
                  <LimitUpLadderPage />
                </Suspense>
              }
            />
            <Route
              path="/market/hot"
              element={
                <Suspense fallback={null}>
                  <HotStocksPage />
                </Suspense>
              }
            />
            <Route
              path="/market/concepts"
              element={
                <Suspense fallback={null}>
                  <ConceptAnalysisPage />
                </Suspense>
              }
            />
            <Route
              path="/market/industries"
              element={
                <Suspense fallback={null}>
                  <IndustryAnalysisPage />
                </Suspense>
              }
            />
            <Route
              path="/datasources"
              element={
                <Suspense fallback={null}>
                  <DataSourceCenterPage />
                </Suspense>
              }
            />
            <Route path="/ml-factor" element={<MlFactorIndexPage />} />
            <Route path="/ml-factor/models" element={<MlModelsPage />} />
            <Route path="/ml-factor/scoring" element={<MlScoringPage />} />
            <Route path="/ml-factor/portfolio" element={<MlPortfolioPage />} />
            <Route path="/ml-factor/analysis" element={<MlAnalysisPage />} />
            <Route path="/ml-factor/backtest" element={<MlBacktestPage />} />
            <Route path="/realtime-analysis/indicators" element={<RtIndicatorsPage />} />
            <Route path="/realtime-analysis/signals" element={<RtSignalsPage />} />
            <Route path="/realtime-analysis/monitor" element={<RtMonitorPage />} />
            <Route path="/realtime-analysis/risk" element={<RtRiskPage />} />
            <Route path="/realtime-analysis/reports" element={<RtReportsPage />} />
            <Route path="/realtime-analysis/websocket" element={<RtWebsocketPage />} />
            <Route path="/ai-workbench" element={<AiWorkbenchPage />} />
            <Route path="/text2sql" element={<Text2SqlPage />} />
            <Route path="*" element={<HomePage />} />
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
