import { useEffect, useMemo, useState } from 'react'
import {
  createModel,
  deleteModel,
  fetchFactors,
  fetchModelDetail,
  fetchModels,
  fetchTrainJob,
  fetchTrainingDateRange,
  predictModel,
  startTraining,
  type FactorDef,
  type ModelDef,
  type ModelDetail,
  type ModelPrediction,
  type TrainJob,
} from '../api/mlFactor'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { downloadCsv, formatDateTime, formatNumber } from '../utils/format'

const MODEL_TYPES = ['linear_regression', 'random_forest', 'xgboost', 'lightgbm', 'neural_network']
const TARGET_TYPES = [
  ['return_1d', '次日收益'],
  ['return_5d', '5日收益'],
  ['return_20d', '20日收益'],
  ['ranking', '排名'],
] as const

type Dialog = null | { kind: 'create' } | { kind: 'detail'; model: ModelDetail } | { kind: 'predict'; model: ModelDef } | { kind: 'train'; model: ModelDef; jobId: string }

const STATUS_BADGE: Record<string, string> = {
  trained: 'text-bg-success',
  training: 'text-bg-warning',
  draft: 'text-bg-secondary',
  failed: 'text-bg-danger',
}

export default function MlModelsPage() {
  const [models, setModels] = useState<ModelDef[]>([])
  const [factors, setFactors] = useState<FactorDef[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [dialog, setDialog] = useState<Dialog>(null)

  // create form
  const [form, setForm] = useState({ model_id: '', model_name: '', model_type: 'lightgbm', target_type: 'return_5d' })
  const [selectedFactors, setSelectedFactors] = useState<Set<string>>(new Set())
  const [createMsg, setCreateMsg] = useState<string | null>(null)

  // train dialog
  const [trainStart, setTrainStart] = useState('')
  const [trainEnd, setTrainEnd] = useState('')
  const [job, setJob] = useState<TrainJob | null>(null)
  const [trainErr, setTrainErr] = useState<string | null>(null)

  // predict dialog
  const [predDate, setPredDate] = useState('')
  const [predTop, setPredTop] = useState(50)
  const [predictions, setPredictions] = useState<ModelPrediction[] | null>(null)
  const [predBusy, setPredBusy] = useState(false)
  const [predErr, setPredErr] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    setError(null)
    Promise.all([fetchModels(), fetchFactors()])
      .then(([m, f]) => {
        setModels(m.models ?? [])
        setFactors(f.factors ?? [])
      })
      .catch((e) => setError(e instanceof Error ? e.message : '加载失败'))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  // 训练任务 1s 轮询
  useEffect(() => {
    if (!dialog || dialog.kind !== 'train' || !dialog.jobId) return
    let stop = false
    const timer = setInterval(async () => {
      try {
        const r = await fetchTrainJob(dialog.jobId)
        if (stop) return
        setJob(r.job)
        if (['success', 'failed'].includes(r.job.status)) {
          clearInterval(timer)
        }
      } catch {
        clearInterval(timer)
      }
    }, 1000)
    return () => {
      stop = true
      clearInterval(timer)
    }
  }, [dialog])

  const openTrain = async (model: ModelDef) => {
    const range = await fetchTrainingDateRange(model.model_id)
    const end = new Date()
    end.setDate(end.getDate() - 2)
    setTrainStart(range?.start_date ?? '')
    setTrainEnd(range?.end_date ?? end.toISOString().slice(0, 10))
    setJob(null)
    setTrainErr(null)
    setDialog({ kind: 'train', model, jobId: '' })
  }

  const submitTrain = async () => {
    if (!dialog || dialog.kind !== 'train') return
    setTrainErr(null)
    try {
      const r = await startTraining({ model_id: dialog.model.model_id, start_date: trainStart, end_date: trainEnd })
      setDialog({ ...dialog, jobId: r.job_id })
      if (r.date_range_adjusted && r.start_date) setTrainStart(r.start_date)
      if (r.date_range_adjusted && r.end_date) setTrainEnd(r.end_date)
    } catch (e) {
      setTrainErr(e instanceof Error ? e.message : '提交失败')
    }
  }

  const openPredict = (model: ModelDef) => {
    setPredDate(new Date().toISOString().slice(0, 10))
    setPredictions(null)
    setPredErr(null)
    setDialog({ kind: 'predict', model })
  }

  const runPredict = async () => {
    if (!dialog || dialog.kind !== 'predict') return
    setPredBusy(true)
    setPredErr(null)
    try {
      const r = await predictModel({ model_id: dialog.model.model_id, trade_date: predDate, ts_codes: null })
      const sorted = [...(r.predictions ?? [])].sort((a, b) => b.predicted_return - a.predicted_return).slice(0, predTop)
      setPredictions(sorted)
    } catch (e) {
      setPredErr(e instanceof Error ? e.message : '预测失败')
    } finally {
      setPredBusy(false)
    }
  }

  const exportPredictions = () => {
    if (!predictions) return
    downloadCsv(
      `预测结果_${dialog && dialog.kind === 'predict' ? dialog.model.model_id : ''}_${predDate}.csv`,
      ['排名', '代码', '预测收益率(%)', '概率分数(%)', '预测日期'],
      predictions.map((p, i) => [
        i + 1,
        p.ts_code,
        (p.predicted_return * 100).toFixed(3),
        p.probability_score != null ? (p.probability_score * 100).toFixed(1) : '',
        p.trade_date,
      ]),
    )
  }

  const handleCreate = async () => {
    setCreateMsg(null)
    try {
      const r = await createModel({
        model_id: form.model_id,
        model_name: form.model_name,
        model_type: form.model_type,
        target_type: form.target_type,
        factor_list: [...selectedFactors],
      })
      setCreateMsg(r.success ? `创建成功：${r.message ?? form.model_id}` : (r.error ?? '创建失败'))
      if (r.success) load()
    } catch (e) {
      setCreateMsg(e instanceof Error ? e.message : '创建失败')
    }
  }

  const handleDelete = async (model: ModelDef) => {
    if (!window.confirm(`确认删除模型 ${model.model_name}（${model.model_id}）？`)) return
    try {
      await deleteModel(model.model_id)
      load()
    } catch (e) {
      window.alert(e instanceof Error ? e.message : '删除失败')
    }
  }

  const openDetail = async (model: ModelDef) => {
    try {
      const detail = await fetchModelDetail(model.model_id)
      setDialog({ kind: 'detail', model: detail })
    } catch (e) {
      window.alert(e instanceof Error ? e.message : '详情加载失败')
    }
  }

  const stats = useMemo(
    () => ({
      total: models.length,
      trained: models.filter((m) => m.status === 'trained').length,
      training: models.filter((m) => m.status === 'training').length,
      active: models.filter((m) => m.status !== 'draft' && m.status !== 'failed').length,
    }),
    [models],
  )

  const rankBadge = (i: number) => (i < 5 ? 'text-bg-success' : i < 20 ? 'text-bg-primary' : i < 50 ? 'text-bg-warning' : 'text-bg-secondary')

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>模型管理</h2>
          <p className="desc">模型定义、异步训练（进度与日志）、预测与导出</p>
        </div>
        <button type="button" className="btn btn-primary btn-sm" onClick={() => {
          setForm({ model_id: '', model_name: '', model_type: 'lightgbm', target_type: 'return_5d' })
          setSelectedFactors(new Set())
          setCreateMsg(null)
          setDialog({ kind: 'create' })
        }}>
          + 创建新模型
        </button>
      </div>

      <div className="stat-grid">
        <div className="stat">
          <div className="stat-value">{stats.total}</div>
          <div className="stat-label">总模型数</div>
        </div>
        <div className="stat">
          <div className="stat-value">{stats.trained}</div>
          <div className="stat-label">已训练</div>
        </div>
        <div className="stat">
          <div className="stat-value">{stats.training}</div>
          <div className="stat-label">训练中</div>
        </div>
        <div className="stat">
          <div className="stat-value">{stats.active}</div>
          <div className="stat-label">活跃</div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <h6 className="panel-title">
            <span className="kicker" />
            模型列表
            <span className="chip">{models.length} 个</span>
          </h6>
          <button type="button" className="btn btn-outline-secondary btn-sm" onClick={load}>
            ⟳ 刷新
          </button>
        </div>
        <div className="panel-body tight table-container">
          {loading && <Loading text="加载模型..." />}
          {error && <ErrorState message={error} onRetry={load} />}
          {!loading && !error && (
            <table className="data-table">
              <thead>
                <tr>
                  <th>模型 ID</th>
                  <th>名称</th>
                  <th>类型</th>
                  <th>预测目标</th>
                  <th>状态</th>
                  <th className="num">准确率</th>
                  <th>创建时间</th>
                  <th className="num">操作</th>
                </tr>
              </thead>
              <tbody>
                {models.map((m) => (
                  <tr key={m.model_id}>
                    <td>
                      <code>{m.model_id}</code>
                    </td>
                    <td style={{ fontWeight: 600 }}>{m.model_name}</td>
                    <td>{m.model_type}</td>
                    <td>{TARGET_TYPES.find(([v]) => v === m.target_type)?.[1] ?? m.target_type}</td>
                    <td>
                      <span className={`badge ${STATUS_BADGE[m.status] ?? 'text-bg-secondary'}`}>{m.status}</span>
                    </td>
                    <td className="num">{m.accuracy != null ? `${(m.accuracy * 100).toFixed(1)}%` : '--'}</td>
                    <td>{formatDateTime(m.created_at)}</td>
                    <td className="num" style={{ whiteSpace: 'nowrap' }}>
                      <button type="button" className="btn btn-outline-secondary btn-sm me-1" onClick={() => openDetail(m)}>
                        查看
                      </button>
                      <button type="button" className="btn btn-outline-primary btn-sm me-1" onClick={() => openTrain(m)}>
                        训练
                      </button>
                      <button type="button" className="btn btn-outline-primary btn-sm me-1" onClick={() => openPredict(m)}>
                        预测
                      </button>
                      <button type="button" className="btn btn-outline-danger btn-sm" onClick={() => handleDelete(m)}>
                        删除
                      </button>
                    </td>
                  </tr>
                ))}
                {models.length === 0 && (
                  <tr>
                    <td colSpan={8}>
                      <EmptyState icon="🤖" text="暂无模型，点击右上角创建" />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* 创建模型 */}
      {dialog?.kind === 'create' && (
        <Modal title="创建新模型" onClose={() => setDialog(null)}>
          <div className="row g-3">
            <div className="col-md-6">
              <label className="form-label">模型 ID</label>
              <input type="text" className="form-control" value={form.model_id} onChange={(e) => setForm({ ...form, model_id: e.target.value })} />
            </div>
            <div className="col-md-6">
              <label className="form-label">模型名称</label>
              <input type="text" className="form-control" value={form.model_name} onChange={(e) => setForm({ ...form, model_name: e.target.value })} />
            </div>
            <div className="col-md-6">
              <label className="form-label">模型类型</label>
              <select className="form-select" value={form.model_type} onChange={(e) => setForm({ ...form, model_type: e.target.value })}>
                {MODEL_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-md-6">
              <label className="form-label">预测目标</label>
              <select className="form-select" value={form.target_type} onChange={(e) => setForm({ ...form, target_type: e.target.value })}>
                {TARGET_TYPES.map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-12">
              <label className="form-label">选择因子（已选 {selectedFactors.size}）</label>
              <div className="p-2 rounded" style={{ maxHeight: 220, overflowY: 'auto', background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
                {factors.map((f) => (
                  <label key={f.factor_id} className="d-inline-flex align-items-center gap-1 me-3 py-1" style={{ fontSize: 13, cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      className="form-check-input mt-0"
                      checked={selectedFactors.has(f.factor_id)}
                      onChange={() =>
                        setSelectedFactors((prev) => {
                          const next = new Set(prev)
                          if (next.has(f.factor_id)) next.delete(f.factor_id)
                          else next.add(f.factor_id)
                          return next
                        })
                      }
                    />
                    {f.factor_id}
                  </label>
                ))}
              </div>
            </div>
          </div>
          {createMsg && <div className="alert-note mt-3">{createMsg}</div>}
          <div className="modal-footer mt-3 d-flex justify-content-end gap-2">
            <button type="button" className="btn btn-outline-secondary" onClick={() => setDialog(null)}>
              关闭
            </button>
            <button type="button" className="btn btn-primary" onClick={handleCreate}>
              创建
            </button>
          </div>
        </Modal>
      )}

      {/* 模型详情 */}
      {dialog?.kind === 'detail' && (
        <Modal title={`模型详情 · ${dialog.model.model_name}`} large onClose={() => setDialog(null)}>
          <div className="row g-3 mb-3">
            <InfoCell label="模型 ID" value={dialog.model.model_id} />
            <InfoCell label="类型 / 目标" value={`${dialog.model.model_type} · ${dialog.model.target_type}`} />
            <InfoCell label="状态" value={dialog.model.status} />
            <InfoCell label="模型文件" value={dialog.model.model_file_exists ? '存在' : '不存在'} />
            <InfoCell label="预测总数" value={String(dialog.model.prediction_summary?.total_predictions ?? 0)} />
            <InfoCell label="最近交易日" value={dialog.model.prediction_summary?.latest_trade_date ?? '--'} />
          </div>
          <div className="side-group-label">因子列表</div>
          <div className="d-flex gap-1 flex-wrap mb-3">
            {(dialog.model.factor_list ?? []).map((f) => (
              <span className="chip" key={f}>
                {f}
              </span>
            ))}
          </div>
          <div className="side-group-label">最近预测</div>
          <div className="table-container" style={{ maxHeight: 260 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>日期</th>
                  <th>代码</th>
                  <th className="num">预测收益</th>
                  <th className="num">rank_score</th>
                </tr>
              </thead>
              <tbody>
                {(dialog.model.recent_predictions ?? []).map((p, i) => (
                  <tr key={`${p.ts_code}-${i}`}>
                    <td>{p.trade_date}</td>
                    <td>
                      <code>{p.ts_code}</code>
                    </td>
                    <td className="num">{formatNumber(p.predicted_return, 4)}</td>
                    <td className="num">{p.rank_score != null ? formatNumber(p.rank_score, 4) : '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Modal>
      )}

      {/* 训练进度 */}
      {dialog?.kind === 'train' && (
        <Modal title={`训练模型 · ${dialog.model.model_name}`} onClose={() => setDialog(null)}>
          <div className="row g-3 mb-2">
            <div className="col-md-6">
              <label className="form-label">开始日期</label>
              <input type="date" className="form-control" value={trainStart} onChange={(e) => setTrainStart(e.target.value)} />
            </div>
            <div className="col-md-6">
              <label className="form-label">结束日期</label>
              <input type="date" className="form-control" value={trainEnd} onChange={(e) => setTrainEnd(e.target.value)} />
            </div>
          </div>
          <button type="button" className="btn btn-primary mb-3" disabled={!!dialog.jobId} onClick={submitTrain}>
            {dialog.jobId ? '训练已提交' : '开始训练'}
          </button>
          {trainErr && <ErrorState message={trainErr} />}
          {job && (
            <>
              <div className="d-flex align-items-center gap-2 mb-2">
                <span className={`badge ${job.status === 'success' ? 'text-bg-success' : job.status === 'failed' ? 'text-bg-danger' : 'text-bg-primary'}`}>
                  {job.status === 'queued' ? '排队中' : job.status === 'running' ? '训练中' : job.status}
                </span>
                <span className="chip">{job.progress}%</span>
                {job.step && <span className="chip">{job.step}</span>}
              </div>
              <div className="progress mb-2" style={{ height: 8 }}>
                <div className="progress-bar progress-bar-striped progress-bar-animated" style={{ width: `${job.progress}%` }} />
              </div>
              {job.logs && job.logs.length > 0 && (
                <pre style={{ maxHeight: 200, overflow: 'auto', fontSize: 11.5, background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8, padding: 10 }}>
                  {job.logs.join('\n')}
                </pre>
              )}
              {job.status === 'success' && job.result?.metrics && (
                <div className="row g-2 mt-2">
                  <InfoCell label="训练样本数" value={String(job.result.metrics.sample_count ?? '--')} />
                  <InfoCell label="验证 R²" value={job.result.metrics.test_r2 != null ? formatNumber(job.result.metrics.test_r2, 4) : '--'} />
                  <InfoCell label="训练 R²" value={job.result.metrics.train_r2 != null ? formatNumber(job.result.metrics.train_r2, 4) : '--'} />
                  <InfoCell label="因子数" value={String(job.result.metrics.feature_count ?? '--')} />
                </div>
              )}
              {job.status === 'failed' && <ErrorState message={job.error ?? '训练失败'} />}
            </>
          )}
        </Modal>
      )}

      {/* 预测 */}
      {dialog?.kind === 'predict' && (
        <Modal title={`预测 · ${dialog.model.model_name}`} large onClose={() => setDialog(null)}>
          <div className="row g-3 align-items-end mb-3">
            <div className="col-md-4">
              <label className="form-label">预测日期</label>
              <input type="date" className="form-control" value={predDate} onChange={(e) => setPredDate(e.target.value)} />
            </div>
            <div className="col-md-4">
              <label className="form-label">显示数量</label>
              <select className="form-select" value={predTop} onChange={(e) => setPredTop(Number(e.target.value))}>
                {[20, 50, 100, 200].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-md-4">
              <button type="button" className="btn btn-primary w-100" disabled={predBusy} onClick={runPredict}>
                {predBusy ? '预测中…' : '开始预测'}
              </button>
            </div>
          </div>
          {predErr && <ErrorState message={predErr} />}
          {predictions && (
            <>
              <div className="d-flex align-items-center gap-2 mb-2 flex-wrap">
                <span className="chip">共 {predictions.length} 条</span>
                <span className="chip">
                  最高预测收益{' '}
                  {predictions.length > 0 ? `${(predictions[0].predicted_return * 100).toFixed(3)}%` : '--'}
                </span>
                <button type="button" className="btn btn-outline-primary btn-sm ms-auto" onClick={exportPredictions}>
                  导出 CSV ↓
                </button>
              </div>
              <div className="table-container" style={{ maxHeight: 380 }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>排名</th>
                      <th>代码</th>
                      <th className="num">预测收益率</th>
                      <th className="num">概率分数</th>
                      <th>预测日期</th>
                    </tr>
                  </thead>
                  <tbody>
                    {predictions.map((p, i) => (
                      <tr key={p.ts_code}>
                        <td>
                          <span className={`badge ${rankBadge(i)}`}>{i + 1}</span>
                        </td>
                        <td>
                          <code>{p.ts_code}</code>
                        </td>
                        <td className="num" style={{ color: p.predicted_return >= 0 ? 'var(--up, #f87171)' : 'var(--down, #4ade80)' }}>
                          {(p.predicted_return * 100).toFixed(3)}%
                        </td>
                        <td className="num">{p.probability_score != null ? `${(p.probability_score * 100).toFixed(1)}%` : '--'}</td>
                        <td>{p.trade_date}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </Modal>
      )}
    </div>
  )
}

function Modal({ title, children, onClose, large }: { title: string; children: React.ReactNode; onClose: () => void; large?: boolean }) {
  return (
    <div className="modal d-block" style={{ background: 'rgba(0,0,0,0.45)' }} onClick={onClose}>
      <div className={`modal-dialog ${large ? 'modal-xl' : ''} modal-dialog-scrollable`} onClick={(e) => e.stopPropagation()}>
        <div className="modal-content" style={{ background: 'var(--surface)', color: 'var(--text)' }}>
          <div className="modal-header">
            <h5 className="modal-title">{title}</h5>
            <button type="button" className="btn-close" onClick={onClose} />
          </div>
          <div className="modal-body">{children}</div>
        </div>
      </div>
    </div>
  )
}

function InfoCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="col-md-4 col-6">
      <div className="stat" style={{ padding: '8px 12px' }}>
        <div className="stat-value" style={{ fontSize: 15 }}>
          {value}
        </div>
        <div className="stat-label">{label}</div>
      </div>
    </div>
  )
}
