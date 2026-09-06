import { NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { lazy, Suspense, useEffect, type ReactNode } from 'react'
import {
  Activity, BookOpen, Bot, Brain, Briefcase, Coins, Compass, Crosshair, Database, Dna,
  ExternalLink, Factory, FileText, Flag, Flame, FlaskConical, HeartPulse, Home,
  LayoutDashboard, LayoutGrid, Layers, Lightbulb, List, Medal, MessageSquare, Moon,
  Newspaper, PieChart, Plug, Radar, Radio, Search, Shield, Star, Sun, Timer,
  TrendingUp, Trophy, Zap,
  type LucideIcon,
} from 'lucide-react'
import { ThemeProvider, useTheme } from './theme/ThemeContext'

// 全部页面按路由 lazy 分割：echarts / lightweight-charts 等重组件随页面 chunk 加载，首屏只拉入口
const HomePage = lazy(() => import('./pages/HomePage'))
const StocksPage = lazy(() => import('./pages/StocksPage'))
const AnalysisPage = lazy(() => import('./pages/AnalysisPage'))
const ScreenPage = lazy(() => import('./pages/ScreenPage'))
const BacktestPage = lazy(() => import('./pages/BacktestPage'))
const StockDetailPage = lazy(() => import('./pages/StockDetailPage'))
const FeatureIntroPage = lazy(() => import('./pages/FeatureIntroPage'))
const HeatmapPage = lazy(() => import('./pages/HeatmapPage'))
const PatternScreenPage = lazy(() => import('./pages/PatternScreenPage'))
const MoneyflowPage = lazy(() => import('./pages/MoneyflowPage'))
const MarketBriefPage = lazy(() => import('./pages/MarketBriefPage'))
const FinancialHealthPage = lazy(() => import('./pages/FinancialHealthPage'))
const StockRadarPage = lazy(() => import('./pages/StockRadarPage'))
const StockPanoramaPage = lazy(() => import('./pages/StockPanoramaPage'))
const DataManagementPage = lazy(() => import('./pages/DataManagementPage'))
const MlFactorIndexPage = lazy(() => import('./pages/MlFactorIndexPage'))
const MlModelsPage = lazy(() => import('./pages/MlModelsPage'))
const MlScoringPage = lazy(() => import('./pages/MlScoringPage'))
const MlPortfolioPage = lazy(() => import('./pages/MlPortfolioPage'))
const MlAnalysisPage = lazy(() => import('./pages/MlAnalysisPage'))
const MlBacktestPage = lazy(() => import('./pages/MlBacktestPage'))
const RtIndicatorsPage = lazy(() => import('./pages/RtIndicatorsPage'))
const RtSignalsPage = lazy(() => import('./pages/RtSignalsPage'))
const RtMonitorPage = lazy(() => import('./pages/RtMonitorPage'))
const RtRiskPage = lazy(() => import('./pages/RtRiskPage'))
const RtReportsPage = lazy(() => import('./pages/RtReportsPage'))
const RtWebsocketPage = lazy(() => import('./pages/RtWebsocketPage'))
const AiWorkbenchPage = lazy(() => import('./pages/AiWorkbenchPage'))
const Text2SqlPage = lazy(() => import('./pages/Text2SqlPage'))

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
  icon: LucideIcon
  end?: boolean
}

interface NavGroup {
  label: string
  items: NavLeaf[]
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: '概览',
    items: [{ to: '/', label: '首页', icon: Home, end: true }],
  },
  {
    label: '核心分析',
    items: [
      { to: '/stocks', label: '股票列表', icon: List },
      { to: '/analysis', label: '技术分析', icon: Activity },
      { to: '/screen', label: '选股筛选', icon: Search },
      { to: '/backtest', label: '策略回测', icon: FlaskConical },
    ],
  },
  {
    label: '多因子模型',
    items: [
      { to: '/ml-factor', label: '因子管理', icon: Dna, end: true },
      { to: '/ml-factor/models', label: '模型管理', icon: Bot },
      { to: '/ml-factor/scoring', label: '股票评分', icon: Medal },
      { to: '/ml-factor/portfolio', label: '投资组合', icon: Briefcase },
      { to: '/ml-factor/analysis', label: '分析报告', icon: PieChart },
      { to: '/ml-factor/backtest', label: '组合回测', icon: Flag },
    ],
  },
  {
    label: '实时分析',
    items: [
      { to: '/realtime-analysis/indicators', label: '技术指标', icon: Timer },
      { to: '/realtime-analysis/signals', label: '交易信号', icon: Zap },
      { to: '/realtime-analysis/monitor', label: '实时监控', icon: Radio },
      { to: '/realtime-analysis/risk', label: '风险管理', icon: Shield },
      { to: '/realtime-analysis/reports', label: '报告管理', icon: FileText },
      { to: '/realtime-analysis/websocket', label: '推送管理', icon: Plug },
    ],
  },
  {
    label: '市场',
    items: [
      { to: '/market/dashboard', label: '市场看板', icon: LayoutDashboard },
      { to: '/market/watchlist', label: '自选行情', icon: Star },
      { to: '/market/limit-up', label: '连板天梯', icon: Flame },
      { to: '/market/hot', label: '热股榜单', icon: TrendingUp },
      { to: '/market/concepts', label: '概念分析', icon: Lightbulb },
      { to: '/market/industries', label: '行业分析', icon: Factory },
      { to: '/market/dragon-tiger', label: '龙虎榜', icon: Trophy },
    ],
  },
  {
    label: '数据',
    items: [
      { to: '/data-management', label: '数据管理', icon: Database },
      { to: '/datasources', label: '数据源中心', icon: Compass },
    ],
  },
  {
    label: '试用工具',
    items: [
      { to: '/heatmap', label: '板块热力图', icon: LayoutGrid },
      { to: '/pattern-screen', label: '形态选股', icon: Crosshair },
      { to: '/moneyflow', label: '资金流统计', icon: Coins },
      { to: '/market-brief', label: '市场简报', icon: Newspaper },
      { to: '/financial-health', label: '财务健康', icon: HeartPulse },
      { to: '/stock-radar', label: '个股雷达', icon: Radar },
      { to: '/stock-panorama', label: '个股全景', icon: Layers },
      { to: '/feature-intro', label: '功能介绍', icon: BookOpen },
    ],
  },
  {
    label: 'AI 助手',
    items: [
      { to: '/ai-workbench', label: 'AI 工作台', icon: Brain },
      { to: '/text2sql', label: '智能查数', icon: MessageSquare },
    ],
  },
]

/** 路由切换后回到页首，避免长列表页跳转后停留在旧滚动位置 */
function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])
  return null
}

/** lazy 路由 chunk 加载期间的占位，避免整片空白 */
function RouteFallback() {
  return (
    <div className="route-fallback" role="status">
      <div className="spinner-border spinner-fit" aria-hidden />
      <span className="visually-hidden">加载中...</span>
    </div>
  )
}

function LazyRoute({ children }: { children: ReactNode }) {
  return <Suspense fallback={<RouteFallback />}>{children}</Suspense>
}

function Shell() {
  const { mode, toggle } = useTheme()
  return (
    <>
      <ScrollToTop />
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
                  <span className="ico">
                    <item.icon size={15} strokeWidth={1.8} aria-hidden />
                  </span>
                  {item.label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-foot">
          <button type="button" className="theme-toggle" onClick={toggle}>
            <span className="ico">{mode === 'dark' ? <Sun size={15} strokeWidth={1.8} aria-hidden /> : <Moon size={15} strokeWidth={1.8} aria-hidden />}</span>
            {mode === 'dark' ? '浅色模式' : '深色模式'}
          </button>
          <a className="btn-ghost" href={`${OLD_SITE_BASE}/`}>
            <span className="ico">
              <ExternalLink size={14} strokeWidth={1.8} aria-hidden />
            </span>{' '}
            旧版
          </a>
        </div>
      </aside>
      <div className="app-body">
        <main className="app-main">
          <Routes>
            <Route path="/" element={<LazyRoute><HomePage /></LazyRoute>} />
            <Route path="/stocks" element={<LazyRoute><StocksPage /></LazyRoute>} />
            <Route path="/stock/:tsCode" element={<LazyRoute><StockDetailPage /></LazyRoute>} />
            <Route path="/analysis" element={<LazyRoute><AnalysisPage /></LazyRoute>} />
            <Route path="/screen" element={<LazyRoute><ScreenPage /></LazyRoute>} />
            <Route path="/backtest" element={<LazyRoute><BacktestPage /></LazyRoute>} />
            <Route path="/heatmap" element={<LazyRoute><HeatmapPage /></LazyRoute>} />
            <Route path="/pattern-screen" element={<LazyRoute><PatternScreenPage /></LazyRoute>} />
            <Route path="/moneyflow" element={<LazyRoute><MoneyflowPage /></LazyRoute>} />
            <Route path="/market-brief" element={<LazyRoute><MarketBriefPage /></LazyRoute>} />
            <Route path="/financial-health" element={<LazyRoute><FinancialHealthPage /></LazyRoute>} />
            <Route path="/stock-radar" element={<LazyRoute><StockRadarPage /></LazyRoute>} />
            <Route path="/stock-panorama" element={<LazyRoute><StockPanoramaPage /></LazyRoute>} />
            <Route path="/feature-intro" element={<LazyRoute><FeatureIntroPage /></LazyRoute>} />
            <Route path="/data-management" element={<LazyRoute><DataManagementPage /></LazyRoute>} />
            <Route
              path="/market/dashboard"
              element={
                <LazyRoute>
                  <MarketDashboardPage />
                </LazyRoute>
              }
            />
            <Route
              path="/market/watchlist"
              element={
                <LazyRoute>
                  <WatchlistPage />
                </LazyRoute>
              }
            />
            <Route
              path="/market/dragon-tiger"
              element={
                <LazyRoute>
                  <DragonTigerPage />
                </LazyRoute>
              }
            />
            <Route
              path="/market/limit-up"
              element={
                <LazyRoute>
                  <LimitUpLadderPage />
                </LazyRoute>
              }
            />
            <Route
              path="/market/hot"
              element={
                <LazyRoute>
                  <HotStocksPage />
                </LazyRoute>
              }
            />
            <Route
              path="/market/concepts"
              element={
                <LazyRoute>
                  <ConceptAnalysisPage />
                </LazyRoute>
              }
            />
            <Route
              path="/market/industries"
              element={
                <LazyRoute>
                  <IndustryAnalysisPage />
                </LazyRoute>
              }
            />
            <Route
              path="/datasources"
              element={
                <LazyRoute>
                  <DataSourceCenterPage />
                </LazyRoute>
              }
            />
            <Route path="/ml-factor" element={<LazyRoute><MlFactorIndexPage /></LazyRoute>} />
            <Route path="/ml-factor/models" element={<LazyRoute><MlModelsPage /></LazyRoute>} />
            <Route path="/ml-factor/scoring" element={<LazyRoute><MlScoringPage /></LazyRoute>} />
            <Route path="/ml-factor/portfolio" element={<LazyRoute><MlPortfolioPage /></LazyRoute>} />
            <Route path="/ml-factor/analysis" element={<LazyRoute><MlAnalysisPage /></LazyRoute>} />
            <Route path="/ml-factor/backtest" element={<LazyRoute><MlBacktestPage /></LazyRoute>} />
            <Route path="/realtime-analysis/indicators" element={<LazyRoute><RtIndicatorsPage /></LazyRoute>} />
            <Route path="/realtime-analysis/signals" element={<LazyRoute><RtSignalsPage /></LazyRoute>} />
            <Route path="/realtime-analysis/monitor" element={<LazyRoute><RtMonitorPage /></LazyRoute>} />
            <Route path="/realtime-analysis/risk" element={<LazyRoute><RtRiskPage /></LazyRoute>} />
            <Route path="/realtime-analysis/reports" element={<LazyRoute><RtReportsPage /></LazyRoute>} />
            <Route path="/realtime-analysis/websocket" element={<LazyRoute><RtWebsocketPage /></LazyRoute>} />
            <Route path="/ai-workbench" element={<LazyRoute><AiWorkbenchPage /></LazyRoute>} />
            <Route path="/text2sql" element={<LazyRoute><Text2SqlPage /></LazyRoute>} />
            <Route path="*" element={<LazyRoute><HomePage /></LazyRoute>} />
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
