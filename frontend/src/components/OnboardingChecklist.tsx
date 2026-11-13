import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Activity, BookOpen, Brain, Check, ChevronRight, CircleDot, Database, Search,
  Settings, Star, X, type LucideIcon,
} from 'lucide-react'
import { fetchInitStatus } from '../api/dataJobs'
import { fetchAiSessions } from '../api/ai'
import { fetchWatchlist } from '../api/market'
import type { SystemSettings } from '../api/settings'
import { readOnboardingState, setOnboardingDismissed } from '../lib/onboarding'

interface ChecklistTask {
  key: string
  icon: LucideIcon
  title: string
  desc: string
  /** true=已完成；false/null=未完成（null 含 API 失败的未知态，与首页横幅静默口径一致） */
  done: boolean | null
  /** 去完成的目标路由；onOpenSettings 场景为 null */
  to: string | null
}

const DONE_GREEN = '#22c55e'

export function OnboardingChecklist({
  settings,
  onOpenSettings,
}: {
  settings: SystemSettings | null
  onOpenSettings: () => void
}) {
  const [dismissed, setDismissed] = useState(() => readOnboardingState().dismissed)
  const [initOk, setInitOk] = useState<boolean | null>(null)
  const [watchlistOk, setWatchlistOk] = useState<boolean | null>(null)
  const [aiOk, setAiOk] = useState<boolean | null>(null)

  useEffect(() => {
    // 数据初始化：parquet 资产健康检查
    fetchInitStatus()
      .then((d) => setInitOk(Boolean(d.status?.database?.ok)))
      .catch(() => setInitOk(null))
    // 自选股与 AI 会话有服务端痕迹即视为完成
    fetchWatchlist()
      .then((d) => setWatchlistOk((d.items?.length ?? 0) > 0))
      .catch(() => setWatchlistOk(null))
    fetchAiSessions()
      .then((sessions) => setAiOk(sessions.length > 0))
      .catch(() => setAiOk(null))
  }, [])

  const state = readOnboardingState()
  const tasks: ChecklistTask[] = [
    { key: 'tutorial', icon: BookOpen, title: '阅读使用教程', desc: '图文快速了解每个页面能做什么', done: Boolean(state.visits['/tutorial']), to: '/tutorial' },
    { key: 'settings', icon: Settings, title: '配置数据源', desc: 'Tushare / 扶摇 / 大模型密钥，配置一次即可', done: settings ? settings.all_configured : null, to: null },
    { key: 'init', icon: Database, title: '完成数据初始化', desc: '一键建库下载行情、财务与因子数据', done: initOk, to: '/data-management' },
    { key: 'browse', icon: Activity, title: '浏览股票行情', desc: '股票列表与专业 K 线分析页', done: Boolean(state.visits['/stocks'] || state.visits['/analysis']), to: '/stocks' },
    { key: 'screen', icon: Search, title: '试一次选股筛选', desc: '多条件组合筛出目标股票', done: Boolean(state.visits['/screen']), to: '/screen' },
    { key: 'watchlist', icon: Star, title: '添加自选股', desc: '关注的股票加入自选，每日预警盯盘', done: watchlistOk, to: '/market/watchlist' },
    { key: 'ai', icon: Brain, title: '体验 AI 工作台', desc: '自然语言查数、选股与策略研究', done: aiOk, to: '/ai-workbench' },
  ]

  const doneCount = tasks.filter((t) => t.done === true).length
  const allDone = doneCount === tasks.length

  const collapse = () => {
    setOnboardingDismissed(true)
    setDismissed(true)
  }
  const expand = () => {
    setOnboardingDismissed(false)
    setDismissed(false)
  }

  // 收起后只在首页留一个小入口，不打扰
  if (dismissed) {
    return (
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
        <button className="btn btn-ghost" onClick={expand} title="重新展开新手引导">
          📖 新手引导 {doneCount}/{tasks.length}
        </button>
      </div>
    )
  }

  return (
    <div className="panel" style={{ marginTop: 18 }} role="region" aria-label="新手引导">
      <div className="panel-head" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <h6 className="panel-title" style={{ flex: 1 }}>
          <span className="kicker" />
          {allDone ? '🎉 新手引导全部完成' : '新手引导'}
          <span className="text-sm opacity-75" style={{ marginLeft: 10, fontWeight: 400 }}>
            {doneCount}/{tasks.length}
          </span>
        </h6>
        <button className="btn btn-ghost" onClick={collapse} title="收起，之后可从首页重新展开">
          <X size={15} aria-hidden /> 收起
        </button>
      </div>
      <div style={{ padding: '0 18px 6px' }}>
        <div style={{ height: 4, borderRadius: 2, background: 'var(--accent-soft)', overflow: 'hidden' }}>
          <div
            style={{
              height: '100%',
              width: `${(doneCount / tasks.length) * 100}%`,
              borderRadius: 2,
              background: 'linear-gradient(135deg, var(--accent), var(--accent-2))',
              transition: 'width 0.3s ease',
            }}
          />
        </div>
      </div>
      <div className="panel-body" style={{ paddingTop: 8 }}>
        {allDone ? (
          <div className="alert-note">
            基本功能都已上手 🎉 更进阶的能力（因子研究、数据洞察、模拟盘）随时在左侧菜单探索，
            或到 <Link to="/tutorial">使用教程</Link> 查阅各页面的详细说明。
          </div>
        ) : (
          <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
            {tasks.map((t) => {
              const done = t.done === true
              return (
                <li
                  key={t.key}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    padding: '8px 4px',
                    opacity: done ? 0.55 : 1,
                    borderBottom: '1px solid var(--border, rgba(128,128,128,0.15))',
                  }}
                >
                  <span
                    style={{
                      width: 30,
                      height: 30,
                      borderRadius: 8,
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                      background: done ? 'rgba(34,197,94,0.14)' : 'var(--accent-soft)',
                      color: done ? DONE_GREEN : 'var(--accent)',
                    }}
                    aria-hidden
                  >
                    {done ? <Check size={17} strokeWidth={2.4} /> : <t.icon size={16} strokeWidth={1.9} />}
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: 13.5 }}>
                      {t.title}
                      {t.done === false && (
                        <span className="text-sm opacity-60" style={{ marginLeft: 8, fontWeight: 400 }}>
                          <CircleDot size={11} style={{ verticalAlign: -1 }} /> 待完成
                        </span>
                      )}
                    </div>
                    <div className="text-sm opacity-75" style={{ marginTop: 2 }}>{t.desc}</div>
                  </div>
                  {!done && t.to && (
                    <Link className="btn btn-outline-primary btn-sm" to={t.to} style={{ flexShrink: 0 }}>
                      去完成 <ChevronRight size={13} style={{ verticalAlign: -2 }} />
                    </Link>
                  )}
                  {!done && !t.to && (
                    <button className="btn btn-outline-primary btn-sm" onClick={onOpenSettings} style={{ flexShrink: 0 }}>
                      立即配置 <ChevronRight size={13} style={{ verticalAlign: -2 }} />
                    </button>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}
