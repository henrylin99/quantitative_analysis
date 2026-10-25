import { useMemo, useState } from 'react'
import EChart from '../charts/EChart'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { useTheme } from '../theme/ThemeContext'
import { fetchCorrelation, type CorrelationResult } from '../api/insights'
import { formatNumber, pctClass } from '../utils/format'

interface PickedStock {
  ts_code: string
  name: string
}

export default function CorrelationPage() {
  const { palette } = useTheme()
  const [picked, setPicked] = useState<PickedStock[]>([
    { ts_code: '000001.SZ', name: '平安银行' },
    { ts_code: '600519.SH', name: '贵州茅台' },
    { ts_code: '300750.SZ', name: '宁德时代' },
  ])
  const [input, setInput] = useState('')
  const [days, setDays] = useState(120)
  const [result, setResult] = useState<CorrelationResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = () => {
    if (picked.length < 2) {
      setError('至少选择 2 只股票')
      return
    }
    setLoading(true)
    setError(null)
    fetchCorrelation(picked.map((p) => p.ts_code), days)
      .then(setResult)
      .catch((e) => {
        setError(e instanceof Error ? e.message : '相关性计算失败')
        setResult(null)
      })
      .finally(() => setLoading(false))
  }

  const addStock = () => {
    const text = input.trim().toUpperCase()
    const m = text.match(/^(\d{6})$/)
    const code = m
      ? m[1].startsWith('6') ? `${m[1]}.SH` : m[1].startsWith('8') || m[1].startsWith('4') ? `${m[1]}.BJ` : `${m[1]}.SZ`
      : /^\d{6}\.(SH|SZ|BJ)$/.test(text) ? text : null
    if (!code) {
      setError('请输入 6 位股票代码')
      return
    }
    if (picked.some((p) => p.ts_code === code)) {
      setInput('')
      return
    }
    if (picked.length >= 12) {
      setError('最多 12 只')
      return
    }
    setError(null)
    setPicked([...picked, { ts_code: code, name: '' }])
    setInput('')
  }

  const removeStock = (code: string) => setPicked(picked.filter((p) => p.ts_code !== code))

  const heatOption = useMemo(() => {
    if (!result || result.error) return null
    const n = result.codes.length
    const data: [number, number, number][] = []
    result.corr_matrix.forEach((row, i) =>
      row.forEach((v, j) => data.push([j, i, v])),
    )
    return {
      tooltip: { position: 'top' },
      grid: { left: 90, right: 24, top: 24, bottom: 76 },
      xAxis: { type: 'category', data: result.codes, axisLabel: { rotate: 45, fontSize: 10 } },
      yAxis: { type: 'category', data: result.codes, axisLabel: { fontSize: 10 } },
      visualMap: {
        min: -1, max: 1, calculable: true,
        orient: 'horizontal', left: 'center', bottom: 0,
        inRange: { color: [palette.down, '#f8fafc', palette.up] },
      },
      series: [
        {
          type: 'heatmap' as const,
          data,
          label: { show: n <= 8, fontSize: 10, formatter: (p: { data: [number, number, number] }) => p.data[2].toFixed(2) },
        },
      ],
    }
  }, [result, palette])

  const navOption = useMemo(() => {
    if (!result || result.error || !result.nav.length) return null
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: 56, right: 16, top: 20, bottom: 26 },
      xAxis: { type: 'category', data: result.nav.map((p) => p.date), boundaryGap: false },
      yAxis: { type: 'value', scale: true },
      series: [
        {
          name: '等权组合净值',
          type: 'line' as const,
          showSymbol: false,
          lineStyle: { color: palette.accent },
          areaStyle: { color: palette.accent, opacity: 0.15 },
          data: result.nav.map((p) => p.value),
        },
      ],
    }
  }, [result, palette])

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>组合相关性</h2>
          <p className="desc">自选组合日收益相关性矩阵 + 等权净值 + 风险贡献分解（后复权口径）</p>
        </div>
        {result && !result.error && result.avg_corr != null && (
          <span className="chip">平均相关系数 {result.avg_corr}</span>
        )}
      </div>

      <div className="panel mb-3">
        <div className="panel-body">
          <div className="d-flex gap-2 align-items-center flex-wrap">
            {picked.map((p) => (
              <span className="chip" key={p.ts_code}>
                {p.name ? `${p.name} · ` : ''}{p.ts_code}
                <button
                  type="button"
                  className="btn btn-link btn-sm p-0 ms-1"
                  style={{ color: 'inherit', textDecoration: 'none' }}
                  onClick={() => removeStock(p.ts_code)}
                >
                  ✕
                </button>
              </span>
            ))}
            {picked.length < 12 && (
              <span className="d-flex gap-2 align-items-center">
                <input
                  type="text"
                  className="form-control form-control-sm"
                  style={{ width: 140 }}
                  placeholder="加代码如 601318"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && addStock()}
                />
                <button type="button" className="btn btn-outline-secondary btn-sm" onClick={addStock}>
                  添加
                </button>
              </span>
            )}
            <span className="d-flex gap-2 align-items-center ms-auto">
              <div className="seg" role="group">
                {[60, 120, 250].map((n) => (
                  <button key={n} type="button" className={`seg-item ${days === n ? 'active' : ''}`} onClick={() => setDays(n)}>
                    {n}日
                  </button>
                ))}
              </div>
              <button type="button" className="btn btn-primary btn-sm" onClick={run} disabled={loading}>
                计算相关性
              </button>
            </span>
          </div>
        </div>
      </div>

      {error && <ErrorState message={error} onRetry={run} />}
      {loading && <Loading />}
      {!loading && !error && (!result || result.error) && <EmptyState icon="🧩" text={result?.error ?? '添加至少 2 只股票后计算'} />}

      {!loading && !error && result && !result.error && (
        <div className="row g-3">
          <div className="col-lg-7">
            <div className="panel h-100">
              <div className="panel-head">
                <h6 className="panel-title">
                  <span className="kicker" />
                  相关性矩阵（{result.start_date} ~ {result.end_date}，{result.days} 个交易日）
                </h6>
              </div>
              <div className="panel-body">
                <EChart option={heatOption!} height={Math.max(320, result.codes.length * 48 + 100)} />
              </div>
            </div>
          </div>
          <div className="col-lg-5">
            <div className="panel h-100">
              <div className="panel-head">
                <h6 className="panel-title">
                  <span className="kicker" />
                  等权组合净值
                </h6>
              </div>
              <div className="panel-body">
                <EChart option={navOption!} height={Math.max(320, result.codes.length * 48 + 100)} />
              </div>
            </div>
          </div>
          <div className="col-12">
            <div className="panel">
              <div className="panel-head">
                <h6 className="panel-title">
                  <span className="kicker" />
                  单票风险收益与风险贡献
                </h6>
              </div>
              <div className="panel-body tight table-container" style={{ maxHeight: 460 }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>股票</th>
                      <th className="num">区间收益%</th>
                      <th className="num">年化波动%</th>
                      <th className="num">夏普</th>
                      <th className="num">最大回撤%</th>
                      <th className="num">风险贡献%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.stats.map((row) => (
                      <tr key={row.ts_code}>
                        <td>
                          {row.name ?? '--'} <code style={{ fontSize: 11 }}>{row.ts_code}</code>
                        </td>
                        <td className={`num ${pctClass(row.cum_return)}`}>{formatNumber(row.cum_return, 2)}</td>
                        <td className="num">{formatNumber(row.ann_vol, 2)}</td>
                        <td className="num">{formatNumber(row.sharpe, 2)}</td>
                        <td className="num text-down">{formatNumber(row.max_drawdown, 2)}</td>
                        <td className="num">{formatNumber(row.risk_contrib, 1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
