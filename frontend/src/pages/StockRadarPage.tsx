import { useEffect, useState } from 'react'
import EChart from '../charts/EChart'
import { fetchStockRadar } from '../api/trial'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { formatNumber } from '../utils/format'

export default function StockRadarPage() {
  const [input, setInput] = useState('000001.SZ,600000.SH')
  const [tsCodes, setTsCodes] = useState('000001.SZ,600000.SH')
  const [data, setData] = useState<Awaited<ReturnType<typeof fetchStockRadar>> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchStockRadar(tsCodes)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : '生成对比失败'))
      .finally(() => setLoading(false))
  }, [tsCodes])

  const option = data
    ? {
        legend: { top: 0 },
        radar: {
          indicator: data.radar_axes,
          radius: '68%',
          axisName: { color: 'inherit' },
        },
        series: [
          {
            type: 'radar' as const,
            symbolSize: 6,
            areaStyle: { opacity: 0.12 },
            lineStyle: { width: 2 },
            data: data.radar_series.map((s) => ({ name: `${s.name} (${s.ts_code})`, value: s.value })),
          },
        ],
      }
    : null

  const scoreCell = (v: number | null) => (
    <td className="num">
      {v == null ? (
        '--'
      ) : (
        <span
          className="badge"
          style={{
            background: 'var(--surface-2)',
            color: 'var(--text)',
            border: '1px solid var(--border)',
            fontWeight: 650,
          }}
        >
          {v.toFixed(2)}
        </span>
      )}
    </td>
  )

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>个股对比雷达图</h2>
          <p className="desc">
            2-4 只股票 · 估值/成长/技术/资金四维标准化对比 · 交易日 <code>{data?.summary.trade_date ?? '--'}</code>
          </p>
        </div>
      </div>

      <div className="row g-3">
        <div className="col-lg-4">
          <div className="panel h-100">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                输入股票
              </h6>
            </div>
            <div className="panel-body">
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  setTsCodes(input)
                }}
              >
                <input
                  type="text"
                  className="form-control"
                  placeholder="000001.SZ,000002.SZ,300750.SZ"
                  value={input}
                  onChange={(e) => setInput(e.target.value.toUpperCase())}
                />
                <div className="form-text" style={{ color: 'var(--text-faint)' }}>
                  英文逗号分隔，2-4 只；PE/PB 越低得分越高，MACD 按 z-score 标准化。
                </div>
                <button type="submit" className="btn btn-primary w-100 mt-3" disabled={loading}>
                  {loading ? '计算中…' : '生成对比'}
                </button>
              </form>
            </div>
          </div>
        </div>
        <div className="col-lg-8">
          <div className="panel h-100">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                四维对比雷达
                {data && <span className="chip">{data.summary.stock_count} 只 · {data.summary.trade_date}</span>}
              </h6>
            </div>
            <div className="panel-body">
              {loading && <Loading text="标准化计算中..." />}
              {!loading && error && <ErrorState message={error} />}
              {!loading && !error && option && data && data.radar_series.length > 0 && <EChart option={option} height={460} />}
              {!loading && !error && (!data || data.radar_series.length === 0) && <EmptyState icon="🛰️" text="暂无对比数据" />}
            </div>
          </div>
        </div>
      </div>

      {data && data.stock_rows.length > 0 && (
        <div className="panel">
          <div className="panel-head">
            <h6 className="panel-title">
              <span className="kicker" />
              维度明细
            </h6>
          </div>
          <div className="panel-body tight table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>代码</th>
                  <th>名称</th>
                  <th>行业</th>
                  <th className="num">估值</th>
                  <th className="num">成长</th>
                  <th className="num">技术</th>
                  <th className="num">资金</th>
                  <th className="num">PE(TTM)</th>
                  <th className="num">PB</th>
                  <th className="num">营收</th>
                  <th className="num">净利</th>
                  <th className="num">RSI6</th>
                  <th className="num">MACD</th>
                  <th className="num">换手率%</th>
                  <th className="num">主力净流入(万)</th>
                  <th className="num">量比</th>
                </tr>
              </thead>
              <tbody>
                {data.stock_rows.map((r) => (
                  <tr key={r.ts_code}>
                    <td>
                      <code>{r.ts_code}</code>
                    </td>
                    <td style={{ fontWeight: 600 }}>{r.name}</td>
                    <td>{r.industry ?? '--'}</td>
                    {scoreCell(r.valuation_score)}
                    {scoreCell(r.growth_score)}
                    {scoreCell(r.technical_score)}
                    {scoreCell(r.moneyflow_score)}
                    <td className="num">{formatNumber(r.pe_ttm, 2)}</td>
                    <td className="num">{formatNumber(r.pb, 2)}</td>
                    <td className="num">{formatNumber(r.fin_revenue, 0)}</td>
                    <td className="num">{formatNumber(r.fin_n_income, 0)}</td>
                    <td className="num">{formatNumber(r.rsi_6, 2)}</td>
                    <td className="num">{formatNumber(r.macd, 4)}</td>
                    <td className="num">{formatNumber(r.turnover_rate, 2)}</td>
                    <td className="num">{formatNumber(r.net_mf_amount, 0)}</td>
                    <td className="num">{formatNumber(r.volume_ratio, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
