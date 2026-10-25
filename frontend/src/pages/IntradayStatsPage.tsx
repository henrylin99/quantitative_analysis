import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import EChart from '../charts/EChart'
import StockPicker from '../components/StockPicker'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { useTheme } from '../theme/ThemeContext'
import { fetchIntraday, type IntradayResult } from '../api/insights'
import { formatNumber } from '../utils/format'

export default function IntradayStatsPage() {
  const { palette } = useTheme()
  const [searchParams] = useSearchParams()
  const [tsCode, setTsCode] = useState(() => searchParams.get('stock') || '000001.SZ')
  const [stockName, setStockName] = useState('平安银行')
  const [picking, setPicking] = useState(false)
  const [result, setResult] = useState<IntradayResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!tsCode) return
    setLoading(true)
    setError(null)
    fetchIntraday(tsCode)
      .then(setResult)
      .catch((e) => {
        setError(e instanceof Error ? e.message : '日内统计加载失败')
        setResult(null)
      })
      .finally(() => setLoading(false))
  }, [tsCode])

  const volOption = useMemo(() => {
    if (!result || result.error || !result.volume_profile.length) return null
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: 64, right: 16, top: 20, bottom: 40 },
      xAxis: { type: 'category', data: result.volume_profile.map((p) => p.time), axisLabel: { rotate: 45, fontSize: 10 } },
      yAxis: { type: 'value', name: '均量(手)' },
      series: [
        {
          name: '时段平均成交量',
          type: 'bar' as const,
          itemStyle: { color: palette.accent },
          data: result.volume_profile.map((p) => p.avg_vol),
        },
      ],
    }
  }, [result, palette])

  const scatterOption = useMemo(() => {
    if (!result || result.error || !result.scatter.length) return null
    return {
      tooltip: {
        formatter: (p: { data: [number, number, string] }) => `${p.data[2]}<br/>隔夜 ${p.data[0]}% · 日内 ${p.data[1]}%`,
      },
      grid: { left: 56, right: 24, top: 24, bottom: 40 },
      xAxis: { type: 'value', name: '隔夜%', axisLine: { show: true } },
      yAxis: { type: 'value', name: '日内%' },
      series: [
        {
          type: 'scatter' as const,
          symbolSize: 7,
          itemStyle: { color: palette.accent, opacity: 0.75 },
          data: result.scatter
            .filter((r) => r.overnight != null)
            .map((r) => [r.overnight as number, r.intraday, r.date] as [number, number, string]),
        },
      ],
    }
  }, [result, palette])

  const StatCard = ({ label, agg }: { label: string; agg: { mean: number | null; std: number | null; win_rate: number | null } }) => (
    <div className="stat">
      <div className="stat-value" style={{ fontSize: 20 }}>
        {formatNumber(agg.mean, 3)}%
      </div>
      <div className="stat-label">{label} 日均</div>
      <div className="sub">胜率 {formatNumber(agg.win_rate, 1)}% · 波动 {formatNumber(agg.std, 2)}%</div>
    </div>
  )

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>历史日内统计</h2>
          <p className="desc">5 分钟 K 线的日内结构：成交量分布 / 隔夜-日内拆分 / 尾盘动量（分钟数据 2026-04 起）</p>
        </div>
      </div>

      <div className="panel mb-3">
        <div className="panel-body" style={{ maxWidth: 360 }}>
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
      </div>

      {error && <ErrorState message={error} onRetry={() => setTsCode(tsCode)} />}
      {loading && <Loading text="分钟数据聚合中..." />}
      {!loading && !error && (!result || result.error) && <EmptyState icon="⏱️" text={result?.error ?? '选择股票查看日内统计'} />}

      {!loading && !error && result && !result.error && (
        <>
          <div className="stat-grid mb-3">
            <StatCard label="隔夜(昨收→开盘)" agg={result.overnight} />
            <StatCard label="日内(开盘→收盘)" agg={result.intraday} />
            <StatCard label="尾盘30分钟" agg={result.tail30} />
            <div className="stat">
              <div className="stat-value" style={{ fontSize: 20 }}>{result.days}</div>
              <div className="stat-label">统计交易日</div>
              <div className="sub">{result.start_date} ~ {result.end_date}</div>
            </div>
          </div>
          <div className="row g-3">
            <div className="col-lg-7">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    日内成交量分布（各 5 分钟时段均量）
                  </h6>
                </div>
                <div className="panel-body">
                  <EChart option={volOption!} height={340} />
                </div>
              </div>
            </div>
            <div className="col-lg-5">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    隔夜 vs 日内收益（每日一点）
                  </h6>
                </div>
                <div className="panel-body">
                  <EChart option={scatterOption!} height={340} />
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
