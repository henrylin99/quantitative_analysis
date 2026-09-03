import { useEffect, useState } from 'react'
import { fetchMarketBrief } from '../api/trial'
import type { BriefIndustryRow, BriefStockRow } from '../api/trial'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { formatNumber, formatPercent, pctClass } from '../utils/format'

export default function MarketBriefPage() {
  const [data, setData] = useState<Awaited<ReturnType<typeof fetchMarketBrief>> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const load = () => {
    setLoading(true)
    setError(null)
    fetchMarketBrief()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : '数据加载失败'))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const copyBrief = async () => {
    if (!data?.brief_text) return
    try {
      await navigator.clipboard.writeText(data.brief_text)
    } catch {
      const ta = document.createElement('textarea')
      ta.value = data.brief_text
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>每日市场简报</h2>
          <p className="desc">
            全市场截面自动生成 · 交易日 <code>{data?.summary.trade_date ?? '--'}</code>
          </p>
        </div>
      </div>

      {loading && <Loading text="读取大宽表生成简报..." />}
      {error && <ErrorState message={error} onRetry={load} />}

      {data && !loading && !error && (
        <>
          <div className="stat-grid">
            <div className="stat">
              <div className="stat-value">
                <span className="delta up">↑{data.summary.advance_count}</span>{' '}
                <span className="delta down">↓{data.summary.decline_count}</span>
              </div>
              <div className="stat-label">上涨 / 下跌（平 {data.summary.flat_count}）</div>
            </div>
            <div className="stat">
              <div className="stat-value">
                <span className="delta up">{data.summary.limit_up_count}</span> /{' '}
                <span className="delta down">{data.summary.limit_down_count}</span>
              </div>
              <div className="stat-label">涨停 / 跌停</div>
            </div>
            <div className="stat">
              <div className="stat-value">{formatNumber(data.summary.turnover_total / 10000, 2)} 亿</div>
              <div className="stat-label">全市场成交额</div>
            </div>
            <div className="stat">
              <div className="stat-value">{formatNumber(data.summary.stock_count, 0)}</div>
              <div className="stat-label">覆盖股票</div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                结构化简报
              </h6>
              <button type="button" className="btn btn-outline-primary btn-sm" onClick={copyBrief}>
                {copied ? '✓ 已复制' : '复制全文'}
              </button>
            </div>
            <div className="panel-body">
              {data.brief_text ? (
                <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit', fontSize: 13.5, lineHeight: 1.9, margin: 0 }}>
                  {data.brief_text}
                </pre>
              ) : (
                <EmptyState icon="📰" text="今日简报为空" />
              )}
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                成交额 TOP10
              </h6>
            </div>
            <div className="panel-body tight table-container">
              <StockAmountTable rows={data.top_amount} />
            </div>
          </div>

          <div className="row g-3">
            <div className="col-lg-6">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    行业涨幅 TOP10
                  </h6>
                </div>
                <div className="panel-body tight table-container">
                  <IndustryTable rows={data.industry_top} />
                </div>
              </div>
            </div>
            <div className="col-lg-6">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    行业跌幅 TOP10
                  </h6>
                </div>
                <div className="panel-body tight table-container">
                  <IndustryTable rows={data.industry_bottom} />
                </div>
              </div>
            </div>
          </div>

          <div className="row g-3">
            <div className="col-lg-7">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    主力净流入 TOP5
                  </h6>
                </div>
                <div className="panel-body tight table-container">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>排名</th>
                        <th>名称</th>
                        <th>行业</th>
                        <th className="num">净流入(万)</th>
                        <th className="num">涨跌幅</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.top_mf.map((r, i) => (
                        <tr key={r.ts_code}>
                          <td>{i + 1}</td>
                          <td style={{ fontWeight: 600 }}>{r.name}</td>
                          <td>{r.industry}</td>
                          <td className={`num ${pctClass(r.net_mf_amount)}`}>{formatNumber(r.net_mf_amount, 2)}</td>
                          <td className={`num ${pctClass(r.pct_chg)}`}>{formatPercent(r.pct_chg)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
            <div className="col-lg-5">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    特殊形态统计
                  </h6>
                </div>
                <div className="panel-body">
                  <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)' }}>
                    <div className="stat">
                      <div className="stat-value" style={{ fontSize: 20 }}>{data.special_stats.first_limit_count}</div>
                      <div className="stat-label">首板</div>
                    </div>
                    <div className="stat">
                      <div className="stat-value" style={{ fontSize: 20 }}>{data.special_stats.multi_limit_count}</div>
                      <div className="stat-label">连板</div>
                    </div>
                    <div className="stat">
                      <div className="stat-value" style={{ fontSize: 20 }}>{data.special_stats.bullish_engulfing_count}</div>
                      <div className="stat-label">阳包阴</div>
                    </div>
                    <div className="stat">
                      <div className="stat-value" style={{ fontSize: 20 }}>
                        <span className="delta up">{data.special_stats.limit_up_count}</span>/
                        <span className="delta down">{data.special_stats.limit_down_count}</span>
                      </div>
                      <div className="stat-label">涨停/跌停</div>
                    </div>
                  </div>
                  <div className="alert-note mt-2">
                    连续上涨：2 连及以上 <b>{data.special_stats.consec_up_2p_count}</b> 只 · 3 连及以上{' '}
                    <b>{data.special_stats.consec_up_3p_count}</b> 只 · 5 连及以上{' '}
                    <b>{data.special_stats.consec_up_5p_count}</b> 只
                  </div>
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function StockAmountTable({ rows }: { rows: BriefStockRow[] }) {
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>代码</th>
          <th>名称</th>
          <th>行业</th>
          <th className="num">成交额(亿)</th>
          <th className="num">涨跌幅</th>
          <th className="num">主力净流入(亿)</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.ts_code}>
            <td>
              <code>{r.ts_code}</code>
            </td>
            <td style={{ fontWeight: 600 }}>{r.name}</td>
            <td>{r.industry}</td>
            <td className="num">{formatNumber(r.amount / 10000, 2)}</td>
            <td className={`num ${pctClass(r.pct_chg)}`}>{formatPercent(r.pct_chg)}</td>
            <td className={`num ${pctClass(r.net_mf_amount)}`}>{formatNumber(r.net_mf_amount / 10000, 2)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function IndustryTable({ rows }: { rows: BriefIndustryRow[] }) {
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>排名</th>
          <th>行业</th>
          <th className="num">平均涨跌幅</th>
          <th className="num">上涨/下跌</th>
          <th className="num">成交额(亿)</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={r.industry}>
            <td>{i + 1}</td>
            <td style={{ fontWeight: 600 }}>{r.industry}</td>
            <td className={`num ${pctClass(r.avg_pct_chg)}`}>{formatPercent(r.avg_pct_chg)}</td>
            <td className="num">
              <span className="delta up">{r.advance_count}</span>/<span className="delta down">{r.decline_count}</span>
            </td>
            <td className="num">{formatNumber(r.total_amount / 10000, 2)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
