import { useEffect, useMemo, useState } from 'react'
import EChart from '../charts/EChart'
import { useTheme } from '../theme/ThemeContext'
import { fetchFinancialHealth } from '../api/trial'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { formatNumber } from '../utils/format'

/** 总分 badge 六档配色（0 灰 → 5 红） */
const SCORE_COLORS = ['#94a3b8', '#38bdf8', '#34d399', '#fbbf24', '#fb923c', '#ef4444']

export default function FinancialHealthPage() {
  const { palette } = useTheme()
  const [data, setData] = useState<Awaited<ReturnType<typeof fetchFinancialHealth>> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    setError(null)
    fetchFinancialHealth()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : '数据加载失败'))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const pieOption = useMemo(() => {
    if (!data) return null
    return {
      tooltip: { trigger: 'item', formatter: '{b}: {c} 只 ({d}%)' },
      legend: { bottom: 0 },
      series: [
        {
          type: 'pie' as const,
          radius: ['38%', '68%'],
          itemStyle: { borderRadius: 8 },
          label: { formatter: '{b}\n{d}%' },
          data: data.score_distribution.map((d) => ({
            name: d.label,
            value: d.count,
            itemStyle: { color: SCORE_COLORS[d.score] ?? palette.accent },
          })),
        },
      ],
    }
  }, [data, palette])

  const rules = [
    ['毛利率', '> 30%', 'fin_gross_margin'],
    ['净利率', '> 10%', 'fin_net_margin'],
    ['经营现金流', '> 0', 'fin_n_cashflow_act'],
    ['资产负债率', '< 60%', 'fin_debt_ratio'],
    ['ROE', '> 10%', 'fin_n_income_attr_p / fin_total_hldr_eqy'],
  ]

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>财务健康度评分卡</h2>
          <p className="desc">
            五条财务规则 0-5 分 · 交易日 <code>{data?.summary.trade_date ?? '--'}</code>
          </p>
        </div>
      </div>

      {loading && <Loading text="全市场财务体检中..." />}
      {error && <ErrorState message={error} onRetry={load} />}

      {data && !loading && !error && (
        <>
          <div className="stat-grid">
            <div className="stat">
              <div className="stat-value">{formatNumber(data.summary.stock_count, 0)}</div>
              <div className="stat-label">覆盖股票</div>
            </div>
            <div className="stat">
              <div className="stat-value">{formatNumber(data.summary.avg_score, 2)}</div>
              <div className="stat-label">平均得分</div>
              <div className="sub">
                最高 {data.summary.max_score} · 最低 {data.summary.min_score}
              </div>
            </div>
            <div className="stat">
              <div className="stat-value">{data.summary.full_score_count}</div>
              <div className="stat-label">满分股票</div>
            </div>
            <div className="stat">
              <div className="stat-value">{data.summary.qualified_count}</div>
              <div className="stat-label">3 分及以上</div>
            </div>
          </div>

          <div className="row g-3">
            <div className="col-lg-6">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    评分分布
                  </h6>
                </div>
                <div className="panel-body">{pieOption ? <EChart option={pieOption} height={400} /> : <EmptyState icon="📊" text="暂无数据" />}</div>
              </div>
            </div>
            <div className="col-lg-6">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    评分规则
                  </h6>
                </div>
                <div className="panel-body tight table-container">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>项目</th>
                        <th>条件</th>
                        <th>字段</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rules.map(([item, cond, field]) => (
                        <tr key={item}>
                          <td style={{ fontWeight: 600 }}>{item}</td>
                          <td style={{ color: palette.up }}>{cond}</td>
                          <td>
                            <code style={{ fontSize: 11.5 }}>{field}</code>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                全市场财务健康度排名
                <span className="chip">TOP {data.scored_rows.length}</span>
              </h6>
            </div>
            <div className="panel-body tight table-container" style={{ maxHeight: 560 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>排名</th>
                    <th>代码</th>
                    <th>名称</th>
                    <th>行业</th>
                    <th className="num">总分</th>
                    <th className="num">毛利率</th>
                    <th className="num">净利率</th>
                    <th className="num">经营现金流</th>
                    <th className="num">资产负债率</th>
                    <th className="num">ROE</th>
                  </tr>
                </thead>
                <tbody>
                  {data.scored_rows.map((r, i) => (
                    <tr key={r.ts_code}>
                      <td>{i + 1}</td>
                      <td>
                        <code>{r.ts_code}</code>
                      </td>
                      <td style={{ fontWeight: 600 }}>{r.name}</td>
                      <td>{r.industry}</td>
                      <td className="num">
                        <span
                          className="badge"
                          style={{ background: SCORE_COLORS[r.health_score] ?? '#94a3b8', color: '#fff' }}
                        >
                          {r.health_score}
                        </span>
                      </td>
                      <td className={`num ${r.fin_gross_margin != null && r.fin_gross_margin > 30 ? 'text-up' : ''}`}>
                        {formatNumber(r.fin_gross_margin, 2)}%
                      </td>
                      <td className={`num ${r.fin_net_margin != null && r.fin_net_margin > 10 ? 'text-up' : ''}`}>
                        {formatNumber(r.fin_net_margin, 2)}%
                      </td>
                      <td className={`num ${r.fin_n_cashflow_act != null && r.fin_n_cashflow_act > 0 ? 'text-up' : 'text-down'}`}>
                        {formatNumber(r.fin_n_cashflow_act, 2)}
                      </td>
                      <td className={`num ${r.fin_debt_ratio != null && r.fin_debt_ratio < 0.6 ? 'text-up' : 'text-down'}`}>
                        {formatNumber(r.fin_debt_ratio != null ? r.fin_debt_ratio * 100 : null, 2)}%
                      </td>
                      <td className={`num ${r.roe_ratio != null && r.roe_ratio > 0.1 ? 'text-up' : ''}`}>
                        {formatNumber(r.roe_ratio != null ? r.roe_ratio * 100 : null, 2)}%
                      </td>
                    </tr>
                  ))}
                  {data.scored_rows.length === 0 && (
                    <tr>
                      <td colSpan={10}>
                        <EmptyState icon="❤️" text="暂无评分数据" />
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
