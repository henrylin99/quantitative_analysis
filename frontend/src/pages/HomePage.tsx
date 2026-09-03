import { Link } from 'react-router-dom'
import { OLD_SITE_BASE } from '../App'

const features = [
  { to: '/stocks', icon: '📋', title: '股票列表', desc: '全市场股票浏览，行业地域筛选与关键字搜索' },
  { to: '/analysis', icon: '📈', title: '技术分析', desc: 'lightweight-charts v5 专业 K 线，MACD / KDJ / RSI / 布林带' },
  { to: '/screen', icon: '🔍', title: '选股筛选', desc: '估值、市值、技术指标多条件组合，支持模板与导出' },
  { to: '/backtest', icon: '🧪', title: '回测验证', desc: '均线 / MACD / KDJ / RSI / 布林带五类策略历史回测' },
]

export default function HomePage() {
  return (
    <div>
      <div className="hero">
        <h1>量化分析终端</h1>
        <p>前后端分离版 · 与旧版共用同一套 /api 数据服务 · A 股行情与策略研究</p>
      </div>
      <div className="tile-grid">
        {features.map((f) => (
          <Link className="tile" to={f.to} key={f.to}>
            <span className="icon">{f.icon}</span>
            <h3>{f.title}</h3>
            <p>{f.desc}</p>
          </Link>
        ))}
      </div>
      <div className="empty-state" style={{ paddingTop: 40 }}>
        <div className="hint">
          多因子模型、实时分析、AI 工作台等旧版功能未迁移，
          <a href={`${OLD_SITE_BASE}/`} target="_blank" rel="noreferrer">
            打开旧版 ↗
          </a>
        </div>
      </div>
    </div>
  )
}
