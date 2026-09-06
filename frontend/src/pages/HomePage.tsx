import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Activity, Brain, Crosshair, Database, Dna, FlaskConical, HeartPulse, Layers,
  LayoutGrid, List, Newspaper, Radar, Radio, Search,
  type LucideIcon,
} from 'lucide-react'
import { fetchAreas, fetchIndustries, fetchStocks } from '../api/stocks'

interface FeatureTile {
  to: string
  icon: LucideIcon
  title: string
  desc: string
}

const coreFeatures: FeatureTile[] = [
  { to: '/stocks', icon: List, title: '股票列表', desc: '全市场股票浏览，行业地域筛选与关键字搜索' },
  { to: '/analysis', icon: Activity, title: '技术分析', desc: 'lightweight-charts v5 专业 K 线，MACD / KDJ / RSI / 布林带' },
  { to: '/screen', icon: Search, title: '选股筛选', desc: '估值、市值、技术指标多条件组合，支持模板与导出' },
  { to: '/backtest', icon: FlaskConical, title: '回测验证', desc: '均线 / MACD / KDJ / RSI / 布林带五类策略历史回测' },
]

const toolFeatures: FeatureTile[] = [
  { to: '/heatmap', icon: LayoutGrid, title: '板块热力图', desc: '行业市值与涨跌幅分布，点击下钻个股' },
  { to: '/pattern-screen', icon: Crosshair, title: '形态选股', desc: 'K 线形态 / 量价 / 动量标签组合选股' },
  { to: '/market-brief', icon: Newspaper, title: '每日市场简报', desc: '自动生成晨会简报，一键复制全文' },
  { to: '/financial-health', icon: HeartPulse, title: '财务健康度', desc: '五条规则 0-5 分财务体检评分卡' },
  { to: '/stock-radar', icon: Radar, title: '个股雷达', desc: '2-4 只股票估值/成长/技术/资金四维对比' },
  { to: '/stock-panorama', icon: Layers, title: '个股全景', desc: '单只股票最新交易日全维度快照' },
]

const aiFeatures: FeatureTile[] = [
  { to: '/ml-factor', icon: Dna, title: '多因子模型', desc: '因子 / 模型 / 评分 / 组合 / 分析 / 回测全流程' },
  { to: '/realtime-analysis/monitor', icon: Radio, title: '实时分析', desc: '分钟级行情监控、信号生成与风险管理' },
  { to: '/ai-workbench', icon: Brain, title: 'AI 工作台', desc: '大模型对话查数、工具调用、会话持久化' },
  { to: '/data-management', icon: Database, title: '数据管理', desc: '日频任务调度、大宽表构建、分钟数据同步' },
]

export default function HomePage() {
  const [totalStocks, setTotalStocks] = useState<number | null>(null)
  const [industries, setIndustries] = useState<number | null>(null)
  const [areas, setAreas] = useState<number | null>(null)

  useEffect(() => {
    fetchStocks({ page_size: 1 })
      .then((d) => setTotalStocks(d.total))
      .catch(() => setTotalStocks(null))
    fetchIndustries()
      .then((d) => setIndustries(d.length))
      .catch(() => setIndustries(null))
    fetchAreas()
      .then((d) => setAreas(d.length))
      .catch(() => setAreas(null))
  }, [])

  const tileGroup = (title: string, items: FeatureTile[]) => (
    <>
      <h6 className="panel-title" style={{ margin: '26px 0 12px' }}>
        <span className="kicker" />
        {title}
      </h6>
      <div className="tile-grid">
        {items.map((f) => (
          <Link className="tile" to={f.to} key={f.to}>
            <span className="icon">
              <f.icon size={20} strokeWidth={1.8} aria-hidden />
            </span>
            <h3>{f.title}</h3>
            <p>{f.desc}</p>
          </Link>
        ))}
      </div>
    </>
  )

  return (
    <div>
      <div className="hero hero-command">
        <div className="hero-eyebrow"><span className="status-dot" /> MARKET INTELLIGENCE · A 股研究工作台</div>
        <div className="hero-copy">
          <div>
            <h1>量化分析终端</h1>
            <p>从行情浏览、因子研究到策略回测，在一个工作台完成投资决策。</p>
          </div>
          <div className="hero-actions">
            <Link className="btn btn-primary" to="/stocks">开始分析 <span aria-hidden>→</span></Link>
            <Link className="btn btn-outline-primary" to="/screen">选股筛选</Link>
          </div>
        </div>
        <div className="hero-meta">
          <span><strong>实时</strong> 数据接口</span>
          <span><strong>7</strong> 个数据域</span>
          <span><strong>24/7</strong> 策略研究</span>
        </div>
      </div>

      <div className="stat-grid">
        <div className="stat">
          <div className="stat-value accent-number">{totalStocks ?? '--'}</div>
          <div className="stat-label">股票总数</div>
          <div className="sub">全市场覆盖</div>
        </div>
        <div className="stat">
          <div className="stat-value">{industries ?? '--'}</div>
          <div className="stat-label">行业数量</div>
          <div className="sub">行业分类</div>
        </div>
        <div className="stat">
          <div className="stat-value">{areas ?? '--'}</div>
          <div className="stat-label">地域数量</div>
          <div className="sub">地域分类</div>
        </div>
        <div className="stat">
          <div className="stat-value">7</div>
          <div className="stat-label">数据表</div>
          <div className="sub">研究数据域</div>
        </div>
      </div>

      {tileGroup('核心功能', coreFeatures)}
      {tileGroup('试用工具', toolFeatures)}
      {tileGroup('进阶能力', aiFeatures)}
    </div>
  )
}
