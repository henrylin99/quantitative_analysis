import { Link } from 'react-router-dom'
import { OLD_SITE_BASE } from '../App'

const features = [
  { to: '/stocks', icon: '📋', title: '股票列表', desc: '浏览所有股票信息，支持按行业、地域筛选' },
  { to: '/analysis', icon: '📈', title: '技术分析', desc: 'lightweight-charts v5 K线图，MACD/KDJ/RSI/BOLL 全指标' },
  { to: '/screen', icon: '🔍', title: '选股筛选', desc: '估值、市值、技术指标多条件组合选股' },
  { to: '/backtest', icon: '🧪', title: '回测验证', desc: '单股票策略回测：均线/MACD/KDJ/RSI/布林带' },
]

export default function HomePage() {
  return (
    <div className="container-fluid px-4">
      <div className="text-center py-4">
        <h3>量化分析系统</h3>
        <p className="text-secondary">React 前端（前后端分离版）· 与旧版共用同一套 /api 接口</p>
      </div>
      <div className="row g-3">
        {features.map((f) => (
          <div className="col-md-6 col-xl-3" key={f.to}>
            <Link to={f.to} className="text-decoration-none">
              <div className="card metric-card h-100">
                <div className="card-body">
                  <div className="fs-3">{f.icon}</div>
                  <div className="metric-value">{f.title}</div>
                  <div className="metric-label">{f.desc}</div>
                </div>
              </div>
            </Link>
          </div>
        ))}
      </div>
      <div className="text-center mt-4 text-secondary">
        旧版功能（多因子模型、实时分析、AI 工作台等）未迁移，可
        <a href={`${OLD_SITE_BASE}/`} target="_blank" rel="noreferrer">
          打开旧版
        </a>
        使用。
      </div>
    </div>
  )
}
