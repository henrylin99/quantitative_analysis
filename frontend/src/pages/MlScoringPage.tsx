import { useEffect, useState } from 'react'
import {
  fetchModels,
  fetchScoringLatestTradeDate,
  scoreFactorBased,
  scoreMlBased,
  type ScoreTopStock,
} from '../api/mlFactor'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { formatNumber } from '../utils/format'

const FACTOR_LIST = ['momentum_5d', 'money_flow_strength', 'momentum_20d']
const WEIGHTS = { momentum_5d: 0.4, money_flow_strength: 0.3, momentum_20d: 0.3 }

export default function MlScoringPage() {
  const [tradeDate, setTradeDate] = useState('')
  const [method, setMethod] = useState<'factor_based' | 'ml_based'>('factor_based')
  const [topN, setTopN] = useState(50)
  const [rows, setRows] = useState<ScoreTopStock[] | null>(null)
  const [total, setTotal] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [modelCount, setModelCount] = useState<number | null>(null)
  const [usedFallback, setUsedFallback] = useState(false)

  useEffect(() => {
    fetchScoringLatestTradeDate()
      .then((r) => setTradeDate(r.latest_trade_date ?? ''))
      .catch(() => setTradeDate(''))
    fetchModels()
      .then((r) => setModelCount((r.models ?? []).length))
      .catch(() => setModelCount(null))
  }, [])

  const runScoring = async () => {
    if (!tradeDate) {
      setError('交易日期不可为空')
      return
    }
    setLoading(true)
    setError(null)
    try {
      // 因子库按 YYYYMMDD 索引，latest-trade-date 返回 YYYY-MM-DD，需规范化
      const compactDate = tradeDate.replace(/-/g, '')
      if (method === 'factor_based') {
        let r: Awaited<ReturnType<typeof scoreFactorBased>>
        try {
          // 先按预设因子组合（与旧版口径一致）
          r = await scoreFactorBased({ trade_date: compactDate, factor_list: FACTOR_LIST, weights: WEIGHTS, method: 'factor_weight', top_n: topN })
          setUsedFallback(false)
        } catch {
          // 预设因子在当日可能无数据（如仅有财务类因子入库），回退为全部可用因子等权
          r = await scoreFactorBased({ trade_date: compactDate, method: 'equal_weight', top_n: topN })
          setUsedFallback(true)
        }
        setRows(r.top_stocks ?? [])
        setTotal(r.total_stocks ?? null)
      } else {
        const models = await fetchModels()
        const ids = (models.models ?? []).map((m) => m.model_id)
        if (ids.length === 0) throw new Error('暂无可用模型，请先在「模型管理」中训练模型')
        const r = await scoreMlBased({ trade_date: compactDate, model_ids: ids, top_n: topN, ensemble_method: 'average' })
        setRows(r.top_stocks ?? [])
        setTotal(null)
        setUsedFallback(false)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '评分失败')
      setRows(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>股票评分</h2>
          <p className="desc">因子加权打分 / 多模型集成打分 · Top-N 排名</p>
        </div>
      </div>

      <div className="panel">
        <div className="panel-body">
          <div className="row g-3 align-items-end">
            <div className="col-lg-3 col-md-6">
              <label className="form-label">交易日期</label>
              <input type="date" className="form-control" value={tradeDate} onChange={(e) => setTradeDate(e.target.value)} />
            </div>
            <div className="col-lg-3 col-md-6">
              <label className="form-label">评分方法</label>
              <select className="form-select" value={method} onChange={(e) => setMethod(e.target.value as 'factor_based' | 'ml_based')}>
                <option value="factor_based">因子加权打分</option>
                <option value="ml_based">ML 模型集成打分</option>
              </select>
            </div>
            <div className="col-lg-3 col-md-6">
              <label className="form-label">显示数量</label>
              <select className="form-select" value={topN} onChange={(e) => setTopN(Number(e.target.value))}>
                {[50, 100, 200, 500].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-lg-3 col-md-6">
              <button type="button" className="btn btn-primary w-100" disabled={loading} onClick={runScoring}>
                {loading ? '计算中…' : '⭐ 计算评分'}
              </button>
            </div>
          </div>
          {method === 'factor_based' && (
            <div className="hint mt-2" style={{ fontSize: 12, color: 'var(--text-faint)' }}>
              因子组合：momentum_5d (40%) + money_flow_strength (30%) + momentum_20d (30%)
              {modelCount != null && ` · 可用模型 ${modelCount} 个`}
            </div>
          )}
        </div>
      </div>

      {loading && <Loading text="评分计算中（读取因子库并排名）..." />}
      {error && <ErrorState message={error} onRetry={runScoring} />}

      {rows && !loading && !error && (
        <div className="panel">
          <div className="panel-head">
            <h6 className="panel-title">
              <span className="kicker" />
              评分结果
              <span className="chip">Top {rows.length}{total != null ? ` · 共评分 ${total} 只` : ''}</span>
              {usedFallback && <span className="alert-note py-1">预设因子当日无数据，已回退为全部可用因子等权</span>}
            </h6>
          </div>
          <div className="panel-body tight table-container" style={{ maxHeight: 620 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>排名</th>
                  <th>代码</th>
                  <th>名称</th>
                  <th className="num">评分</th>
                  <th style={{ width: 180 }}>量纲</th>
                  <th className="num">百分位</th>
                  <th>行业</th>
                  <th>地区</th>
                  {method === 'ml_based' && <th className="num">预测收益</th>}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => {
                  const score = method === 'factor_based' ? r.composite_score : r.ensemble_score
                  return (
                    <tr key={r.ts_code}>
                      <td>
                        <span className={`badge ${i < 10 ? 'text-bg-success' : i < 50 ? 'text-bg-primary' : i < 100 ? 'text-bg-warning' : 'text-bg-secondary'}`}>
                          {r.rank ?? i + 1}
                        </span>
                      </td>
                      <td>
                        <code>{r.ts_code}</code>
                      </td>
                      <td style={{ fontWeight: 600 }}>{r.name ?? r.symbol ?? '--'}</td>
                      <td className="num">{formatNumber(score, 3)}</td>
                      <td>
                        <div className="progress" style={{ height: 6 }}>
                          <div className="progress-bar" style={{ width: `${Math.max(2, Math.min(100, (score ?? 0) * 20))}%` }} />
                        </div>
                      </td>
                      <td className="num">{r.percentile_rank != null ? `${formatNumber(r.percentile_rank, 1)}%` : '--'}</td>
                      <td>{r.industry ?? '--'}</td>
                      <td>{r.area ?? '--'}</td>
                      {method === 'ml_based' && (
                        <td className="num">{r.predicted_return != null ? `${(r.predicted_return * 100).toFixed(3)}%` : '--'}</td>
                      )}
                    </tr>
                  )
                })}
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={9}>
                      <EmptyState icon="⭐" text="没有评分结果" />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!rows && !loading && !error && (
        <EmptyState icon="⭐" text="选择日期与评分方法，点击「计算评分」" />
      )}
    </div>
  )
}
