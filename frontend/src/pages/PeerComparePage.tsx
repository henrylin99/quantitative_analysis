import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import EChart from '../charts/EChart'
import StockPicker from '../components/StockPicker'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { useTheme } from '../theme/ThemeContext'
import { fetchPeerCompare, type PeerCompareResult } from '../api/insights'
import { formatNumber, pctClass } from '../utils/format'

export default function PeerComparePage() {
  const { palette } = useTheme()
  const [searchParams] = useSearchParams()
  const [tsCode, setTsCode] = useState(() => searchParams.get('stock') || '000001.SZ')
  const [stockName, setStockName] = useState('平安银行')
  const [picking, setPicking] = useState(false)
  const [result, setResult] = useState<PeerCompareResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!tsCode) return
    setLoading(true)
    setError(null)
    fetchPeerCompare(tsCode)
      .then(setResult)
      .catch((e) => {
        setError(e instanceof Error ? e.message : '同业对比加载失败')
        setResult(null)
      })
      .finally(() => setLoading(false))
  }, [tsCode])

  const trendOption = useMemo(() => {
    if (!result || result.error || !result.trend?.years?.length) return null
    const t = result.trend
    const mk = (name: string, data: (number | null)[], color: string) => ({
      name,
      type: 'bar' as const,
      itemStyle: { color },
      data,
    })
    return {
      tooltip: { trigger: 'axis' },
      legend: { top: 0 },
      grid: { left: 56, right: 16, top: 34, bottom: 26 },
      xAxis: { type: 'category', data: t.years },
      yAxis: [
        { type: 'value', name: '营收(亿)' },
        { type: 'value', name: '净利(亿)', splitLine: { show: false } },
      ],
      series: [
        { ...mk(`${result.name ?? tsCode} 营收`, t.stock_revenue, palette.accent) },
        { ...mk('行业中位营收', t.median_revenue, '#94a3b8'), barGap: '-60%', itemStyle: { color: 'rgba(148,163,184,0.35)' } },
        { ...mk(`${result.name ?? tsCode} 净利`, t.stock_n_income, palette.up), yAxisIndex: 1 },
      ],
    }
  }, [result, palette, tsCode])

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>财务同业对比</h2>
          <p className="desc">同行业最新年报核心指标横向对比 + 近 5 年营收/净利趋势（对比按总市值取前 15 家）</p>
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
      {loading && <Loading text="同业财报汇总中..." />}
      {!loading && !error && (!result || result.error) && <EmptyState icon="🏢" text={result?.error ?? '选择股票开始对比'} />}

      {!loading && !error && result && !result.error && (
        <>
          <div className="panel mb-3">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                {result.industry} · {result.year} 年报同业对比
                <span className="chip">{result.peers.length} 家 · 金额单位亿元</span>
              </h6>
            </div>
            <div className="panel-body tight table-container" style={{ maxHeight: 520 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>公司</th>
                    <th className="num">营收(亿)</th>
                    <th className="num">净利(亿)</th>
                    <th className="num">营收YoY%</th>
                    <th className="num">净利YoY%</th>
                    <th className="num">净利率%</th>
                    <th className="num">ROE%</th>
                    <th className="num">资产负债率%</th>
                    <th className="num">经营现金流/净利</th>
                  </tr>
                </thead>
                <tbody>
                  {result.peers.map((row) => (
                    <tr key={row.ts_code} style={row.is_target ? { background: 'var(--surface-3)' } : undefined}>
                      <td style={{ fontWeight: row.is_target ? 700 : undefined }}>
                        {row.name ?? '--'} <code style={{ fontSize: 11 }}>{row.ts_code}</code>
                      </td>
                      <td className="num">{formatNumber(row.revenue, 1)}</td>
                      <td className="num">{formatNumber(row.n_income, 2)}</td>
                      <td className={`num ${pctClass(row.rev_yoy)}`}>{formatNumber(row.rev_yoy, 1)}</td>
                      <td className={`num ${pctClass(row.ni_yoy)}`}>{formatNumber(row.ni_yoy, 1)}</td>
                      <td className="num">{formatNumber(row.net_margin, 1)}</td>
                      <td className="num">{formatNumber(row.roe, 1)}</td>
                      <td className="num">{formatNumber(row.debt_ratio, 1)}</td>
                      <td className="num">{formatNumber(row.ocf_ni, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {trendOption && (
            <div className="panel">
              <div className="panel-head">
                <h6 className="panel-title">
                  <span className="kicker" />
                  营收 / 净利趋势 vs 行业中位数
                </h6>
              </div>
              <div className="panel-body">
                <EChart option={trendOption} height={340} />
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
