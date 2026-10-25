import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import EChart from '../charts/EChart'
import StockPicker from '../components/StockPicker'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { useTheme } from '../theme/ThemeContext'
import { fetchThermometer, fetchValuation, type ThermometerResult, type ValuationResult } from '../api/insights'
import { formatNumber } from '../utils/format'

const METRICS = [
  { key: 'pe_ttm', label: 'PE(TTM)' },
  { key: 'pb', label: 'PB' },
  { key: 'dv_ttm', label: '股息率%' },
  { key: 'turnover_rate', label: '换手率%' },
] as const

type MetricKey = (typeof METRICS)[number]['key']

export default function ValuationPage() {
  const { palette } = useTheme()
  const [searchParams] = useSearchParams()
  const [tsCode, setTsCode] = useState(() => searchParams.get('stock') || '000001.SZ')
  const [stockName, setStockName] = useState('平安银行')
  const [picking, setPicking] = useState(false)
  const [metric, setMetric] = useState<MetricKey>('pe_ttm')
  const [valuation, setValuation] = useState<ValuationResult | null>(null)
  const [vLoading, setVLoading] = useState(false)
  const [vError, setVError] = useState<string | null>(null)
  const [thermo, setThermo] = useState<ThermometerResult | null>(null)
  const [tError, setTError] = useState<string | null>(null)

  useEffect(() => {
    fetchThermometer()
      .then(setThermo)
      .catch((e) => setTError(e instanceof Error ? e.message : '温度计加载失败'))
  }, [])

  useEffect(() => {
    if (!tsCode) return
    setVLoading(true)
    setVError(null)
    fetchValuation(tsCode)
      .then(setValuation)
      .catch((e) => {
        setVError(e instanceof Error ? e.message : '估值数据加载失败')
        setValuation(null)
      })
      .finally(() => setVLoading(false))
  }, [tsCode])

  // 单票：估值 + 价格双轴
  const stockOption = useMemo(() => {
    if (!valuation || valuation.error || !valuation.series[metric]) return null
    const pts = valuation.series[metric]
    return {
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 16, bottom: 4 }],
      legend: { top: 0 },
      grid: { left: 56, right: 56, top: 32, bottom: 48 },
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: pts.map((p) => p.date), boundaryGap: false },
      yAxis: [
        { type: 'value', scale: true, name: METRICS.find((m) => m.key === metric)?.label },
        { type: 'value', scale: true, name: '收盘价', splitLine: { show: false } },
      ],
      series: [
        {
          name: METRICS.find((m) => m.key === metric)?.label,
          type: 'line' as const,
          showSymbol: false,
          itemStyle: { color: palette.accent },
          data: pts.map((p) => p.value),
        },
        {
          name: '收盘价',
          type: 'line' as const,
          yAxisIndex: 1,
          showSymbol: false,
          lineStyle: { width: 1, opacity: 0.5 },
          itemStyle: { color: palette.teal },
          data: valuation.prices.map((p) => p.value),
        },
      ],
    }
  }, [valuation, metric, palette])

  // 温度计：市场中位 PE + 扩张分位（右轴 0-100）+ 上证指数（归一 100，隐藏）
  const thermoOption = useMemo(() => {
    if (!thermo || thermo.error || !thermo.series.length) return null
    const s = thermo.series
    const idxMap = new Map((thermo.index_series ?? []).map((p) => [p.date, p.value]))
    const idxVals = (thermo.index_series ?? []).filter((p) => p.value != null).map((p) => p.value as number)
    const base = idxVals.length ? idxVals[0] : 1
    return {
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 16, bottom: 4 }],
      legend: { top: 0 },
      grid: { left: 56, right: 56, top: 32, bottom: 48 },
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: s.map((r) => r.date), boundaryGap: false },
      yAxis: [
        { type: 'value', scale: true, name: '中位PE' },
        { type: 'value', min: 0, max: 100, name: '分位%', splitLine: { show: false } },
      ],
      series: [
        {
          name: '全市场中位PE(TTM)',
          type: 'line' as const,
          showSymbol: false,
          itemStyle: { color: palette.accent },
          data: s.map((r) => r.pe),
        },
        {
          name: 'PE扩张分位%',
          type: 'line' as const,
          yAxisIndex: 1,
          showSymbol: false,
          itemStyle: { color: palette.amber },
          markLine: {
            silent: true,
            symbol: 'none',
            data: [
              { yAxis: 80, lineStyle: { type: 'dashed', color: palette.up }, label: { formatter: '80% 高估' } },
              { yAxis: 20, lineStyle: { type: 'dashed', color: palette.down }, label: { formatter: '20% 低估' } },
            ],
          },
          data: s.map((r) => r.pe_pct),
        },
        {
          name: '上证指数(归一)',
          type: 'line' as const,
          showSymbol: false,
          lineStyle: { width: 1, opacity: 0.45 },
          itemStyle: { color: palette.teal },
          data: s.map((r) => (idxMap.has(r.date) && idxMap.get(r.date) != null ? Math.round(((idxMap.get(r.date) as number) / base) * 1000) / 10 : null)),
        },
      ],
    }
  }, [thermo, palette])

  const pctColor = (v: number | null | undefined) =>
    v == null ? '' : v >= 80 ? 'text-up' : v <= 20 ? 'text-down' : ''

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>估值分位</h2>
          <p className="desc">单票估值历史分位 + 全市场估值温度计（daily_basic 2024 年起）</p>
        </div>
      </div>

      {/* 市场温度计 */}
      <div className="panel mb-3">
        <div className="panel-head d-flex justify-content-between align-items-center flex-wrap gap-2">
          <h6 className="panel-title">
            <span className="kicker" />
            市场估值温度计
          </h6>
          {thermo && !thermo.error && (
            <span className="text-faint" style={{ fontSize: 12 }}>
              {thermo.latest.date} · 中位PE {formatNumber(thermo.latest.pe, 2)} · 扩张分位 {formatNumber(thermo.latest.pe_pct, 1)}%
            </span>
          )}
        </div>
        <div className="panel-body">
          {tError ? (
            <ErrorState message={tError} onRetry={() => window.location.reload()} />
          ) : !thermo ? (
            <Loading />
          ) : thermo.error ? (
            <EmptyState icon="🌡️" text={thermo.error} />
          ) : (
            <EChart option={thermoOption!} height={360} />
          )}
        </div>
      </div>

      {/* 单票估值 */}
      <div className="panel">
        <div className="panel-head">
          <div style={{ minWidth: 260 }}>
            <StockPicker
              value={picking ? '' : tsCode}
              name={stockName}
              onPick={(c, n) => {
                setTsCode(c)
                setStockName(n)
                setPicking(false)
              }}
              onClear={() => setPicking(true)}
            />
          </div>
          <div className="seg" role="group">
            {METRICS.map((m) => (
              <button
                key={m.key}
                type="button"
                className={`seg-item ${metric === m.key ? 'active' : ''}`}
                onClick={() => setMetric(m.key)}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>
        <div className="panel-body">
          {vError ? (
            <ErrorState message={vError} onRetry={() => setTsCode(tsCode)} />
          ) : vLoading ? (
            <Loading />
          ) : !valuation || valuation.error ? (
            <EmptyState icon="📈" text={valuation?.error ?? '选择股票查看估值历史'} />
          ) : (
            <>
              <div className="stat-grid mb-3">
                {METRICS.map((m) => (
                  <div className="stat" key={m.key}>
                    <div className={`stat-value ${pctColor(valuation.percentiles[m.key])}`} style={{ fontSize: 20 }}>
                      {formatNumber(valuation.percentiles[m.key], 1)}%
                    </div>
                    <div className="stat-label">{m.label} 历史分位</div>
                    <div className="sub">当前 {formatNumber(valuation.current[m.key], 2) ?? '--'}</div>
                  </div>
                ))}
              </div>
              <div className="text-faint mb-2" style={{ fontSize: 12 }}>
                {valuation.name ?? valuation.ts_code} · {valuation.start_date} ~ {valuation.end_date} · 分位按全历史（2024 起）
              </div>
              <EChart option={stockOption!} height={380} />
            </>
          )}
        </div>
      </div>
    </div>
  )
}
