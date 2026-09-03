import { useEffect, useMemo, useRef, useState } from 'react'
import EChart from '../charts/EChart'
import { useTheme } from '../theme/ThemeContext'
import {
  fetchMonitorAnomalies,
  fetchMonitorOverview,
  fetchMonitorQuotes,
  fetchMonitorSectors,
  fetchMonitorSentiment,
  fetchMonitorTopMovers,
  type MonitorAnomaly,
  type MonitorQuote,
} from '../api/realtime'
import { EmptyState, ErrorState } from '../components/StateViews'
import { formatNumber, formatPercent, pctClass } from '../utils/format'

const PERIODS = ['5min', '15min', '30min']
const ANOMALY_PRESETS = [
  { label: '轻度', change: 3.0, volume: 2.0 },
  { label: '中度', change: 5.0, volume: 3.0 },
  { label: '重度', change: 8.0, volume: 5.0 },
]

function QuoteRows({ rows, valueField }: { rows: MonitorQuote[]; valueField: 'change_pct' | 'volume' }) {
  return (
    <tbody>
      {rows.map((q) => (
        <tr key={q.ts_code}>
          <td>
            <code>{q.ts_code}</code>
          </td>
          <td style={{ fontWeight: 600 }}>{q.name}</td>
          <td className="num">{formatNumber(q.current_price, 2)}</td>
          {valueField === 'change_pct' ? (
            <td className={`num ${pctClass(q.change_pct)}`}>{formatPercent(q.change_pct)}</td>
          ) : (
            <td className="num">{formatNumber(q.volume, 0)}</td>
          )}
          <td className="num">{q.volume_ratio != null ? formatNumber(q.volume_ratio, 2) : '--'}</td>
        </tr>
      ))}
    </tbody>
  )
}

export default function RtMonitorPage() {
  const { palette } = useTheme()
  const [overview, setOverview] = useState<Awaited<ReturnType<typeof fetchMonitorOverview>>>(null)
  const [period, setPeriod] = useState('5min')
  const [quotes, setQuotes] = useState<MonitorQuote[]>([])
  const [sectorHours, setSectorHours] = useState(4)
  const [sectors, setSectors] = useState<Awaited<ReturnType<typeof fetchMonitorSectors>>>(null)
  const [sentiment, setSentiment] = useState<Awaited<ReturnType<typeof fetchMonitorSentiment>>>(null)
  const [anomalyPreset, setAnomalyPreset] = useState(1)
  const [anomalies, setAnomalies] = useState<MonitorAnomaly[]>([])
  const [movers, setMovers] = useState<Awaited<ReturnType<typeof fetchMonitorTopMovers>>>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [lastError, setLastError] = useState<string | null>(null)
  const [lastLoad, setLastLoad] = useState<string>('--')
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  const loadAll = async () => {
    try {
      const [ov, qt, sc, sn, an, mv] = await Promise.all([
        fetchMonitorOverview(),
        fetchMonitorQuotes(period, 20),
        fetchMonitorSectors(sectorHours),
        fetchMonitorSentiment(sectorHours),
        fetchMonitorAnomalies(ANOMALY_PRESETS[anomalyPreset].change, ANOMALY_PRESETS[anomalyPreset].volume),
        fetchMonitorTopMovers(10),
      ])
      setOverview(ov)
      setQuotes(qt?.quotes ?? [])
      setSectors(sc)
      setSentiment(sn)
      setAnomalies(an?.anomalies ?? [])
      setMovers(mv)
      setLastError(null)
    } catch (e) {
      setLastError(e instanceof Error ? e.message : '监控数据加载失败')
    }
    setLastLoad(new Date().toLocaleTimeString('zh-CN'))
  }

  useEffect(() => {
    loadAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period, sectorHours, anomalyPreset])

  useEffect(() => {
    if (timer.current) clearInterval(timer.current)
    if (autoRefresh) {
      timer.current = setInterval(loadAll, 30_000)
    }
    return () => {
      if (timer.current) clearInterval(timer.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh, period, sectorHours, anomalyPreset])

  const sectorOption = useMemo(() => {
    const list = sectors?.sectors ?? []
    if (list.length === 0) return null
    const top = [...list].sort((a, b) => b.avg_change_pct - a.avg_change_pct).slice(0, 10).reverse()
    return {
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => `${formatNumber(Number(v), 2)}%` },
      grid: { left: 80, right: 30, top: 10, bottom: 24 },
      xAxis: { type: 'value', axisLabel: { formatter: '{value}%' } },
      yAxis: { type: 'category', data: top.map((s) => s.sector_name) },
      series: [
        {
          type: 'bar',
          data: top.map((s) => ({
            value: s.avg_change_pct,
            itemStyle: { color: s.avg_change_pct >= 0 ? palette.up : palette.down },
          })),
        },
      ],
    }
  }, [sectors, palette])

  const gaugeOption = useMemo(() => {
    if (!sentiment) return null
    const score = sentiment.sentiment_score ?? 50
    return {
      series: [
        {
          type: 'gauge',
          min: 0,
          max: 100,
          startAngle: 200,
          endAngle: -20,
          progress: { show: true, width: 14, itemStyle: { color: score >= 60 ? palette.up : score <= 40 ? palette.down : palette.amber } },
          axisLine: { lineStyle: { width: 14, color: [[1, palette.border]] } },
          axisTick: { show: false },
          splitLine: { show: false },
          axisLabel: { color: palette.text, distance: 20, fontSize: 10 },
          pointer: { show: false },
          anchor: { show: false },
          detail: {
            valueAnimation: true,
            fontSize: 30,
            offsetCenter: [0, '10%'],
            formatter: '{value}',
            color: palette.text,
          },
          data: [{ value: Math.round(score) }],
        },
      ],
    }
  }, [sentiment, palette])

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>实时监控</h2>
          <p className="desc">
            分钟级行情监控大盘 · 最近刷新 <code>{lastLoad}</code>
          </p>
        </div>
        <div className="d-flex align-items-center gap-2">
          <label className="d-flex align-items-center gap-2" style={{ fontSize: 13, cursor: 'pointer' }}>
            <input type="checkbox" className="form-check-input mt-0" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} />
            自动刷新（30s）
          </label>
          <button type="button" className="btn btn-outline-secondary btn-sm" onClick={loadAll}>
            ⟳ 刷新
          </button>
        </div>
      </div>

      {lastError && <ErrorState message={lastError} onRetry={loadAll} />}

      <div className="stat-grid">
        <div className="stat">
          <div className="stat-value">{formatNumber(overview?.total_stocks ?? null, 0)}</div>
          <div className="stat-label">股票总数</div>
        </div>
        <div className="stat">
          <div className="stat-value">{formatNumber(overview?.active_stocks ?? null, 0)}</div>
          <div className="stat-label">活跃股票</div>
        </div>
        <div className="stat">
          <div className="stat-value">{formatNumber(overview?.today_records ?? null, 0)}</div>
          <div className="stat-label">今日记录</div>
        </div>
        <div className="stat">
          <div className="stat-value" style={{ fontSize: 16 }}>{String(overview?.data_delay ?? '--')}</div>
          <div className="stat-label">数据延迟</div>
        </div>
      </div>

      <div className="row g-3">
        <div className="col-lg-5">
          <div className="panel h-100">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                实时行情
                <span className="chip">{quotes.length} 只</span>
              </h6>
              <div className="seg" role="group">
                {PERIODS.map((p) => (
                  <button key={p} type="button" className={`seg-item ${period === p ? 'active' : ''}`} onClick={() => setPeriod(p)}>
                    {p}
                  </button>
                ))}
              </div>
            </div>
            <div className="panel-body tight table-container" style={{ maxHeight: 380 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>代码</th>
                    <th>名称</th>
                    <th className="num">现价</th>
                    <th className="num">涨跌幅</th>
                    <th className="num">量比</th>
                  </tr>
                </thead>
                <QuoteRows rows={quotes} valueField="change_pct" />
              </table>
              {quotes.length === 0 && <EmptyState icon="📡" text="暂无行情数据" />}
            </div>
          </div>
        </div>

        <div className="col-lg-7">
          <div className="panel h-100">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                板块表现
              </h6>
              <div className="seg" role="group">
                {[1, 4, 24].map((h) => (
                  <button key={h} type="button" className={`seg-item ${sectorHours === h ? 'active' : ''}`} onClick={() => setSectorHours(h)}>
                    {h}小时
                  </button>
                ))}
              </div>
            </div>
            <div className="panel-body">{sectorOption ? <EChart option={sectorOption} height={330} /> : <EmptyState icon="🏭" text="暂无板块数据" />}</div>
          </div>
        </div>

        <div className="col-lg-4">
          <div className="panel h-100">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                市场情绪
                {sentiment && <span className="chip">{sentiment.market_status}</span>}
              </h6>
            </div>
            <div className="panel-body">
              {gaugeOption ? (
                <EChart option={gaugeOption} height={220} />
              ) : (
                <EmptyState icon="🌡️" text="暂无情绪数据" />
              )}
              {sentiment && (
                <div className="d-flex justify-content-between flex-wrap gap-2" style={{ fontSize: 12.5, color: 'var(--text-dim)' }}>
                  <span>
                    上涨 <b className="delta up">{sentiment.rising_stocks}</b>
                  </span>
                  <span>
                    下跌 <b className="delta down">{sentiment.falling_stocks}</b>
                  </span>
                  <span>
                    平均涨幅 <b className={pctClass(sentiment.avg_change_pct)}>{formatPercent(sentiment.avg_change_pct)}</b>
                  </span>
                  <span>
                    波动率 <b>{formatNumber(sentiment.volatility, 2)}</b>
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="col-lg-8">
          <div className="panel h-100">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                异动股票
              </h6>
              <div className="seg" role="group">
                {ANOMALY_PRESETS.map((p, i) => (
                  <button key={p.label} type="button" className={`seg-item ${anomalyPreset === i ? 'active' : ''}`} onClick={() => setAnomalyPreset(i)}>
                    {p.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="panel-body tight table-container" style={{ maxHeight: 300 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>代码</th>
                    <th>名称</th>
                    <th className="num">现价</th>
                    <th className="num">涨跌幅</th>
                    <th>异动类型</th>
                    <th className="num">异动分</th>
                  </tr>
                </thead>
                <tbody>
                  {anomalies.map((a) => (
                    <tr key={a.ts_code}>
                      <td>
                        <code>{a.ts_code}</code>
                      </td>
                      <td style={{ fontWeight: 600 }}>{a.name}</td>
                      <td className="num">{formatNumber(a.current_price, 2)}</td>
                      <td className={`num ${pctClass(a.change_pct)}`}>{formatPercent(a.change_pct)}</td>
                      <td>
                        <span className="chip">{a.anomaly_types?.join('、')}</span>
                      </td>
                      <td className="num">{formatNumber(a.anomaly_score, 1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {anomalies.length === 0 && <EmptyState icon="🎯" text="当前阈值下无异动" />}
            </div>
          </div>
        </div>

        <div className="col-12">
          <div className="row g-3">
            {(
              [
                ['涨幅榜', movers?.top_gainers ?? [], 'change_pct'],
                ['跌幅榜', movers?.top_losers ?? [], 'change_pct'],
                ['活跃榜', movers?.most_active ?? [], 'volume'],
              ] as const
            ).map(([title, rows, field]) => (
              <div className="col-lg-4" key={title}>
                <div className="panel h-100">
                  <div className="panel-head">
                    <h6 className="panel-title">
                      <span className="kicker" />
                      {title}
                    </h6>
                  </div>
                  <div className="panel-body tight table-container" style={{ maxHeight: 320 }}>
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>代码</th>
                          <th>名称</th>
                          <th className="num">现价</th>
                          <th className="num">{field === 'change_pct' ? '涨跌幅' : '成交量'}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((q) => (
                          <tr key={q.ts_code}>
                            <td>
                              <code>{q.ts_code}</code>
                            </td>
                            <td style={{ fontWeight: 600 }}>{q.name}</td>
                            <td className="num">{formatNumber(q.current_price, 2)}</td>
                            <td className={`num ${field === 'change_pct' ? pctClass(q.change_pct) : ''}`}>
                              {field === 'change_pct' ? formatPercent(q.change_pct) : formatNumber(q.volume, 0)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {rows.length === 0 && <EmptyState icon="📊" text="暂无数据" />}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
