import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import {
  fetchMfDivergence,
  fetchMfStreaks,
  type MfDivergenceResult,
  type MfStreaksResult,
} from '../api/insights'
import { formatNumber, pctClass } from '../utils/format'

export default function MoneyflowInsightsPage() {
  const [days, setDays] = useState(20)
  const [minStreak, setMinStreak] = useState(3)
  const [streaks, setStreaks] = useState<MfStreaksResult | null>(null)
  const [divergence, setDivergence] = useState<MfDivergenceResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    Promise.all([fetchMfStreaks(days, minStreak, 20), fetchMfDivergence(days, 20)])
      .then(([s, d]) => {
        setStreaks(s)
        setDivergence(d)
      })
      .catch((e) => setError(e instanceof Error ? e.message : '资金流数据加载失败'))
      .finally(() => setLoading(false))
  }, [days, minStreak])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>资金流深历史</h2>
          <p className="desc">主力资金连续净流入排行 + 量价背离筛选（moneyflow 2025-10 起，单位万元）</p>
        </div>
      </div>

      <div className="panel mb-3">
        <div className="panel-body d-flex align-items-center gap-3 flex-wrap">
          <div className="d-flex align-items-center gap-2">
            <span className="text-faint" style={{ fontSize: 13 }}>观察窗口</span>
            <div className="seg" role="group">
              {[10, 20, 40, 60].map((n) => (
                <button key={n} type="button" className={`seg-item ${days === n ? 'active' : ''}`} onClick={() => setDays(n)}>
                  {n}日
                </button>
              ))}
            </div>
          </div>
          <div className="d-flex align-items-center gap-2">
            <span className="text-faint" style={{ fontSize: 13 }}>最少连续天数</span>
            <div className="seg" role="group">
              {[2, 3, 5].map((n) => (
                <button key={n} type="button" className={`seg-item ${minStreak === n ? 'active' : ''}`} onClick={() => setMinStreak(n)}>
                  {n}天
                </button>
              ))}
            </div>
          </div>
          <button type="button" className="btn btn-primary btn-sm" onClick={load} disabled={loading}>
            刷新
          </button>
        </div>
      </div>

      {error && <ErrorState message={error} onRetry={load} />}
      {loading && <Loading text="统计中...（全市场资金流扫描，首次约 10-20 秒）" />}

      {!loading && !error && (
        <div className="row g-3">
          {/* 连续净流入 */}
          <div className="col-lg-6">
            <div className="panel h-100">
              <div className="panel-head">
                <h6 className="panel-title">
                  <span className="kicker" />
                  连续净流入排行
                  <span className="chip">{streaks?.stocks.length ?? 0} 只 · 截至 {streaks?.end_date ?? '--'}</span>
                </h6>
              </div>
              <div className="panel-body tight table-container" style={{ maxHeight: 520 }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>股票</th>
                      <th className="num">连续天数</th>
                      <th className="num">累计净流入(万)</th>
                      <th className="num">最新收盘</th>
                      <th className="num">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(streaks?.stocks ?? []).map((row) => (
                      <tr key={row.ts_code}>
                        <td>
                          {row.name ?? '--'} <code style={{ fontSize: 11 }}>{row.ts_code}</code>
                        </td>
                        <td className="num" style={{ fontWeight: 650 }}>{row.streak}</td>
                        <td className="num text-up">{formatNumber(row.cum_amount, 0)}</td>
                        <td className="num">{formatNumber(row.close, 2)}</td>
                        <td className="num">
                          <Link className="btn btn-outline-primary btn-sm" to={`/stock/${row.ts_code}`}>详情</Link>
                        </td>
                      </tr>
                    ))}
                    {(streaks?.stocks ?? []).length === 0 && (
                      <tr>
                        <td colSpan={5}><EmptyState icon="💸" text={`${days} 日内没有连续 ≥${minStreak} 天净流入的股票`} /></td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* 量价背离 */}
          <div className="col-lg-6">
            <div className="panel h-100">
              <div className="panel-head">
                <h6 className="panel-title">
                  <span className="kicker" />
                  量价背离（价跌 + 主力净流入）
                  <span className="chip">{divergence?.stocks.length ?? 0} 只 · 截至 {divergence?.end_date ?? '--'}</span>
                </h6>
              </div>
              <div className="panel-body tight table-container" style={{ maxHeight: 520 }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>股票</th>
                      <th className="num">区间涨跌%</th>
                      <th className="num">累计净流入(万)</th>
                      <th className="num">最新收盘</th>
                      <th className="num">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(divergence?.stocks ?? []).map((row) => (
                      <tr key={row.ts_code}>
                        <td>
                          {row.name ?? '--'} <code style={{ fontSize: 11 }}>{row.ts_code}</code>
                        </td>
                        <td className={`num ${pctClass(row.pct)}`}>{formatNumber(row.pct, 2)}</td>
                        <td className="num text-up">{formatNumber(row.cum_net, 0)}</td>
                        <td className="num">{formatNumber(row.close, 2)}</td>
                        <td className="num">
                          <Link className="btn btn-outline-primary btn-sm" to={`/stock/${row.ts_code}`}>详情</Link>
                        </td>
                      </tr>
                    ))}
                    {(divergence?.stocks ?? []).length === 0 && (
                      <tr>
                        <td colSpan={5}><EmptyState icon="🔄" text={`${days} 日内无量价背离标的`} /></td>
                      </tr>
                    )}
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
