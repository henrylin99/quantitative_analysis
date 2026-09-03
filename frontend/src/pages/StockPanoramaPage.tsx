import { useEffect, useState } from 'react'
import EChart from '../charts/EChart'
import { fetchStockPanorama } from '../api/trial'
import type { PanoramaMetric } from '../api/trial'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { formatNumber, formatPercent, pctClass } from '../utils/format'

const TABS = [
  { key: 'status', label: '市场快照' },
  { key: 'financial', label: '估值与财务' },
  { key: 'technical', label: '技术面' },
  { key: 'moneyflow', label: '资金面' },
  { key: 'flags', label: '形态标签' },
] as const

type TabKey = (typeof TABS)[number]['key']

export default function StockPanoramaPage() {
  const [input, setInput] = useState('000001.SZ')
  const [tsCode, setTsCode] = useState('000001.SZ')
  const [data, setData] = useState<Awaited<ReturnType<typeof fetchStockPanorama>> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<TabKey>('status')

  const load = (code: string) => {
    setLoading(true)
    setError(null)
    fetchStockPanorama(code)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : '加载失败'))
      .finally(() => setLoading(false))
  }
  // 首屏拉取；切换股票由表单提交触发
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => load(tsCode), [])

  const radarOption = data
    ? {
        radar: { indicator: data.radar_chart.labels.map((n) => ({ name: n, max: 1 })), radius: '68%' },
        series: [
          {
            type: 'radar' as const,
            symbolSize: 7,
            areaStyle: { opacity: 0.16 },
            data: [{ name: data.overview?.name ?? tsCode, value: data.radar_chart.values }],
          },
        ],
      }
    : null

  const metricGrid = (rows: PanoramaMetric[]) => (
    <div className="row g-2">
      {rows.map((m) => {
        const num = typeof m.value === 'number' ? m.value : null
        const isSigned = num != null && !['涨跌额', '成交量', '成交额'].includes(m.label)
        const cls = isSigned && num !== 0 ? (num > 0 ? 'text-up' : 'text-down') : ''
        return (
          <div className="col-md-6" key={m.label}>
            <div className="stat" style={{ padding: '10px 14px' }}>
              <div className={`stat-value ${cls}`} style={{ fontSize: 17 }}>
                {typeof m.value === 'number' ? formatNumber(m.value, 2) : (m.value ?? '--')}
              </div>
              <div className="stat-label">{m.label}</div>
            </div>
          </div>
        )
      })}
    </div>
  )

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>个股全景展示</h2>
          <p className="desc">
            最新交易日全维度快照 · 数据日期 <code>{data?.latest_trade_date ?? '--'}</code>
          </p>
        </div>
      </div>

      <div className="row g-3">
        <div className="col-lg-3">
          <div className="panel h-100">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                快速切换
              </h6>
            </div>
            <div className="panel-body">
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  const code = input.trim().toUpperCase()
                  setTsCode(code)
                  load(code)
                }}
              >
                <input
                  type="text"
                  className="form-control"
                  placeholder="000001.SZ"
                  value={input}
                  onChange={(e) => setInput(e.target.value.toUpperCase())}
                />
                <button type="submit" className="btn btn-primary w-100 mt-3" disabled={loading}>
                  查看全景
                </button>
              </form>
            </div>
          </div>
        </div>

        <div className="col-lg-9">
          <div className="panel h-100">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                市场快照
              </h6>
              {data?.overview && <span className="chip">最新交易日 {data.overview.trade_date}</span>}
            </div>
            <div className="panel-body">
              {loading && <Loading text="读取全景数据..." />}
              {!loading && error && <ErrorState message={error} onRetry={() => load(tsCode)} />}
              {!loading && !error && data?.overview && (
                <>
                  <div className="d-flex align-items-baseline gap-2 flex-wrap mb-3">
                    <span style={{ fontSize: 20, fontWeight: 750 }}>{data.overview.name}</span>
                    <code>{data.overview.ts_code}</code>
                    <span className="chip">{data.overview.industry}</span>
                    <span className="chip">{data.overview.area}</span>
                  </div>
                  <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
                    <div className="stat">
                      <div className="stat-value" style={{ fontSize: 20 }}>
                        {formatNumber(data.overview.close, 2)}
                      </div>
                      <div className="stat-label">收盘价</div>
                    </div>
                    <div className="stat">
                      <div className="stat-value" style={{ fontSize: 20 }}>
                        <span className={`delta ${pctClass(data.overview.pct_chg) === '' ? 'flat' : data.overview.pct_chg! > 0 ? 'up' : 'down'}`}>
                          {formatPercent(data.overview.pct_chg)}
                        </span>
                      </div>
                      <div className="stat-label">涨跌幅</div>
                    </div>
                    <div className="stat">
                      <div className="stat-value" style={{ fontSize: 20 }}>{formatNumber(data.overview.amount, 0)}</div>
                      <div className="stat-label">成交额(万)</div>
                    </div>
                    <div className="stat">
                      <div className="stat-value" style={{ fontSize: 20 }}>
                        {formatNumber(data.overview.pe_ttm, 2)} / {formatNumber(data.overview.pb, 2)}
                      </div>
                      <div className="stat-label">PE(TTM) / PB</div>
                    </div>
                    <div className="stat">
                      <div className="stat-value" style={{ fontSize: 20 }}>
                        {formatNumber(data.overview.ps_ttm, 2)} / {formatNumber(data.overview.dv_ttm, 2)}
                      </div>
                      <div className="stat-label">PS(TTM) / 股息率</div>
                    </div>
                  </div>
                </>
              )}
              {!loading && !error && (!data || !data.overview) && <EmptyState icon="🗂️" text="输入股票代码查看全景" />}
            </div>
          </div>
        </div>
      </div>

      {data?.overview && !loading && !error && (
        <div className="row g-3 mt-0">
          <div className="col-lg-5">
            <div className="panel h-100">
              <div className="panel-head">
                <h6 className="panel-title">
                  <span className="kicker" />
                  四维全景雷达
                  <span className="chip">全市场分位标准化</span>
                </h6>
              </div>
              <div className="panel-body">{radarOption ? <EChart option={radarOption} height={420} /> : <EmptyState icon="🛰️" text="暂无数据" />}</div>
            </div>
          </div>
          <div className="col-lg-7">
            <div className="panel h-100">
              <div className="panel-head">
                <div className="seg" role="group" style={{ flexWrap: 'wrap' }}>
                  {TABS.map((t) => (
                    <button key={t.key} type="button" className={`seg-item ${tab === t.key ? 'active' : ''}`} onClick={() => setTab(t.key)}>
                      {t.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="panel-body">
                {tab === 'status' && metricGrid(data.status_panel)}
                {tab === 'financial' && metricGrid(data.financial_panel)}
                {tab === 'technical' && metricGrid(data.technical_panel)}
                {tab === 'moneyflow' && metricGrid(data.moneyflow_panel)}
                {tab === 'flags' && (
                  <div className="d-flex gap-2 flex-wrap">
                    <span className="chip">首板 · {data.special_flags.pattern_first_limit}</span>
                    <span className="chip">连板 · {data.special_flags.pattern_multi_limit}</span>
                    <span className="chip">阳包阴 · {data.special_flags.pattern_bullish_engulfing}</span>
                    <span className="chip">连续上涨 · {data.special_flags.consec_up_days} 天</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {data?.overview && !loading && !error && (
        <div className="panel">
          <div className="panel-head">
            <h6 className="panel-title">
              <span className="kicker" />
              关键数据明细
            </h6>
          </div>
          <div className="panel-body tight table-container">
            <table className="data-table">
              <tbody>
                {data.detail_rows.map((m) => (
                  <tr key={m.label}>
                    <td style={{ width: 220 }}>{m.label}</td>
                    <td className="num">
                      {typeof m.value === 'number' ? formatNumber(m.value, 2) : (m.value ?? '--')}
                    </td>
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
