import { useEffect, useMemo, useState } from 'react'
import EChart from '../charts/EChart'
import { useTheme } from '../theme/ThemeContext'
import { fetchMoneyflowStats, type MoneyflowStatRow } from '../api/trial'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { formatNumber, pctClass } from '../utils/format'

export default function MoneyflowPage() {
  const { palette } = useTheme()
  const [data, setData] = useState<Awaited<ReturnType<typeof fetchMoneyflowStats>> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    setError(null)
    fetchMoneyflowStats()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : '数据加载失败'))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  // 行业主力动向：大单净额 bar + 特大单净额 bar + 主力净流入 line（万元）
  const option = useMemo(() => {
    if (!data || data.industry_rows.length === 0) return null
    const rows = data.industry_rows
    const bar = (field: 'lg_net_amount' | 'elg_net_amount', name: string, pos: string, neg: string) => ({
      name,
      type: 'bar' as const,
      barMaxWidth: 16,
      itemStyle: { color: (p: { value: number }) => (p.value >= 0 ? pos : neg) },
      data: rows.map((r) => r[field]),
    })
    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v: number) => `${formatNumber(Number(v), 2)} 万` },
      legend: { top: 0 },
      grid: { left: 64, right: 24, top: 40, bottom: 92 },
      xAxis: { type: 'category', data: rows.map((r) => r.industry), axisLabel: { rotate: 28, fontSize: 10.5 } },
      yAxis: { type: 'value', axisLabel: { formatter: '{value}' } },
      series: [
        bar('lg_net_amount', '大单净额', '#38bdf8', '#f97316'),
        bar('elg_net_amount', '特大单净额', palette.down, palette.up),
        {
          name: '主力净流入',
          type: 'line' as const,
          smooth: true,
          symbolSize: 7,
          lineStyle: { color: '#f59e0b' },
          itemStyle: { color: '#f59e0b' },
          data: rows.map((r) => r.net_mf_amount),
        },
      ],
    }
  }, [data, palette])

  const StockTable = ({ rows, title }: { rows: MoneyflowStatRow[]; title: string }) => (
    <div className="panel h-100">
      <div className="panel-head">
        <h6 className="panel-title">
          <span className="kicker" />
          {title}
          <span className="chip">{rows.length} 只</span>
        </h6>
      </div>
      <div className="panel-body tight table-container" style={{ maxHeight: 520 }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>代码</th>
              <th>名称</th>
              <th>行业</th>
              <th className="num">净流入(万)</th>
              <th className="num">大单净额(万)</th>
              <th className="num">特大单净额(万)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.ts_code}>
                <td>
                  <code>{r.ts_code}</code>
                </td>
                <td style={{ fontWeight: 600 }}>{r.name}</td>
                <td>
                  <span className="chip" style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {r.industry}
                  </span>
                </td>
                <td className={`num ${pctClass(r.net_mf_amount)}`}>{formatNumber(r.net_mf_amount, 2)}</td>
                <td className={`num ${pctClass(r.lg_net_amount)}`}>{formatNumber(r.lg_net_amount, 2)}</td>
                <td className={`num ${pctClass(r.elg_net_amount)}`}>{formatNumber(r.elg_net_amount, 2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>资金流统计</h2>
          <p className="desc">
            主力资金（净额/大单/特大单）行业与个股统计 · 交易日 <code>{data?.summary.trade_date ?? '--'}</code>
          </p>
        </div>
      </div>

      {loading && <Loading text="统计全市场主力资金..." />}
      {error && <ErrorState message={error} onRetry={load} />}

      {data && !loading && !error && (
        <>
          <div className="stat-grid">
            <div className="stat">
              <div className="stat-value">{formatNumber(data.summary.stock_count, 0)}</div>
              <div className="stat-label">覆盖股票</div>
            </div>
            <div className="stat">
              <div className="stat-value">{formatNumber(data.summary.industry_count, 0)}</div>
              <div className="stat-label">行业数量</div>
            </div>
            <div className="stat">
              <div className={`stat-value ${pctClass(data.summary.total_net_mf_amount)}`}>
                {formatNumber(data.summary.total_net_mf_amount / 10000, 2)} 亿
              </div>
              <div className="stat-label">主力净流入合计</div>
            </div>
            <div className="stat">
              <div className="stat-value" style={{ fontSize: 18 }}>
                <span className="delta up">↑{data.summary.positive_stock_count}</span>{' '}
                <span className="delta down">↓{data.summary.negative_stock_count}</span>
              </div>
              <div className="stat-label">净流入 / 净流出家数</div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                行业主力动向
                <span className="chip">单位：万元</span>
              </h6>
            </div>
            <div className="panel-body">
              {option ? <EChart option={option} height={520} /> : <EmptyState icon="💰" text="暂无行业数据" />}
            </div>
          </div>

          <div className="row g-3">
            <div className="col-lg-6">
              <StockTable rows={data.top_inflow} title="主力净流入 Top 20" />
            </div>
            <div className="col-lg-6">
              <StockTable rows={data.bottom_outflow} title="主力净流出 Bottom 20" />
            </div>
          </div>
        </>
      )}
    </div>
  )
}
