import { useEffect, useState } from 'react'
import {
  fetchAlertPushConfig,
  fetchDailyAlerts,
  fetchMarketBrief,
  testAlertPush,
  updateAlertPushConfig,
} from '../api/trial'
import type {
  AlertPushChannel,
  AlertPushConfig,
  BriefIndustryRow,
  BriefStockRow,
  DailyAlertRecord,
} from '../api/trial'
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
      <DailyAlertsPanel />
    </div>
  )
}

const ALERT_LEVEL_COLORS: Record<string, string> = {
  warn: '#e8684a',
  info: '#94a3b8',
}

function DailyAlertsPanel() {
  const [records, setRecords] = useState<DailyAlertRecord[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [scanning, setScanning] = useState(false)
  const [showPush, setShowPush] = useState(false)

  const load = (refresh = false) => {
    if (refresh) setScanning(true)
    fetchDailyAlerts(refresh)
      .then((d) => setRecords(d.records))
      .catch((e) => setError(e instanceof Error ? e.message : '预警记录加载失败'))
      .finally(() => setScanning(false))
  }

  useEffect(() => {
    load()
  }, [])

  return (
    <div className="panel mt-3">
      <div className="panel-head d-flex justify-content-between align-items-center flex-wrap gap-2">
        <h6 className="panel-title">
          <span className="kicker" style={{ background: '#e8684a' }} />
          每日预警记录
        </h6>
        <div className="d-flex align-items-center gap-2">
          <span className="text-faint" style={{ fontSize: 11.5 }}>
            每日收盘后自动扫描（regime 翻转 / 筹码信号新增 / 行业轮动榜首）
          </span>
          <button type="button" className={`btn btn-sm ${showPush ? 'btn-primary' : 'btn-outline-secondary'}`} onClick={() => setShowPush((s) => !s)}>
            推送设置
          </button>
          <button type="button" className="btn btn-outline-secondary btn-sm" disabled={scanning} onClick={() => load(true)}>
            {scanning ? '扫描中…' : '立即扫描'}
          </button>
        </div>
      </div>
      {showPush && <AlertPushSettings />}
      <div className="panel-body tight">
        {error && <ErrorState message={error} />}
        {!error && records == null && <Loading text="预警记录加载中..." />}
        {!error && records && records.length === 0 && (
          <EmptyState icon="🔕" text="暂无预警记录（首个交易日收盘后自动生成）" />
        )}
        {!error && records && records.length > 0 && (
          <table className="data-table">
            <thead>
              <tr>
                <th>日期</th>
                <th>预警</th>
                <th>指数 regime</th>
                <th className="num">信号数</th>
              </tr>
            </thead>
            <tbody>
              {records.slice().reverse().map((r) => (
                <tr key={r.scan_date}>
                  <td style={{ whiteSpace: 'nowrap' }}>{r.scan_date}</td>
                  <td>
                    {(r.alerts ?? []).map((a, i) => (
                      <div key={i} className="d-flex align-items-start gap-1" style={{ fontSize: 12 }}>
                        <span
                          className="badge"
                          style={{ background: ALERT_LEVEL_COLORS[a.level] ?? '#94a3b8', color: '#fff', flexShrink: 0 }}
                        >
                          {a.level === 'warn' ? '预警' : '动态'}
                        </span>
                        <span>{a.message}</span>
                      </div>
                    ))}
                  </td>
                  <td>
                    {(r.regime ?? []).map((x) => (
                      <span key={x.code} className="me-2" style={{ fontSize: 12 }}>
                        {x.name}·{x.regime}
                      </span>
                    ))}
                  </td>
                  <td className="num">
                    {r.signals?.stats
                      ? `${r.signals.stats.counts.squeeze}/${r.signals.stats.counts.resonance}/${r.signals.stats.counts.divergence}`
                      : '--'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

const PUSH_CHANNEL_TYPES: Array<{
  value: AlertPushChannel['type']
  label: string
  param: 'send_key' | 'url'
  placeholder: string
}> = [
  { value: 'serverchan', label: 'Server酱', param: 'send_key', placeholder: 'SendKey（sctapi.ftqq.com 获取）' },
  { value: 'wecom_webhook', label: '企业微信机器人', param: 'url', placeholder: '群机器人 Webhook 地址' },
  { value: 'dingtalk_webhook', label: '钉钉机器人', param: 'url', placeholder: '群机器人 Webhook 地址' },
  { value: 'webhook', label: '自定义 Webhook', param: 'url', placeholder: '接收 JSON POST 的 URL' },
]

function AlertPushSettings() {
  const [cfg, setCfg] = useState<AlertPushConfig | null>(null)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)

  useEffect(() => {
    fetchAlertPushConfig()
      .then(setCfg)
      .catch((e) => setMsg(e instanceof Error ? e.message : '推送配置加载失败'))
  }, [])

  if (!cfg) return <Loading text="推送配置加载中..." />

  const save = () => {
    setSaving(true)
    setMsg(null)
    updateAlertPushConfig(cfg)
      .then((c) => {
        setCfg(c)
        setMsg('已保存')
      })
      .catch((e) => setMsg(e instanceof Error ? e.message : '保存失败'))
      .finally(() => setSaving(false))
  }

  const test = () => {
    setTesting(true)
    setMsg(null)
    testAlertPush()
      .then((r) =>
        setMsg(
          r.ok
            ? '测试推送已发送，请查收'
            : `测试失败：${r.results?.map((x) => `${x.type}: ${x.message}`).join('；') || r.message || '未知错误'}`,
        ),
      )
      .catch((e) => setMsg(e instanceof Error ? e.message : '测试失败'))
      .finally(() => setTesting(false))
  }

  const setChannel = (i: number, patch: Partial<AlertPushChannel>) =>
    setCfg({ ...cfg, channels: cfg.channels.map((c, j) => (j === i ? { ...c, ...patch } : c)) })

  return (
    <div style={{ borderBottom: '1px solid rgba(148,163,184,0.25)', padding: '10px 14px' }}>
      <div className="d-flex gap-3 flex-wrap align-items-center">
        <label className="d-flex gap-1 align-items-center" style={{ fontSize: 13 }}>
          <input type="checkbox" checked={cfg.enabled} onChange={(e) => setCfg({ ...cfg, enabled: e.target.checked })} />
          启用出站推送
        </label>
        <label className="d-flex gap-1 align-items-center" style={{ fontSize: 13 }}>
          <span className="text-faint">推送级别</span>
          <select
            value={cfg.min_level}
            onChange={(e) => setCfg({ ...cfg, min_level: e.target.value as AlertPushConfig['min_level'] })}
          >
            <option value="info">每日推送（含"无变化"动态）</option>
            <option value="warn">仅预警（regime 翻转等）</option>
          </select>
        </label>
        <button type="button" className="btn btn-primary btn-sm" disabled={saving} onClick={save}>
          {saving ? '保存中…' : '保存配置'}
        </button>
        <button type="button" className="btn btn-outline-secondary btn-sm" disabled={testing || cfg.channels.length === 0} onClick={test}>
          {testing ? '发送中…' : '发送测试'}
        </button>
        {msg && (
          <span className="text-faint" style={{ fontSize: 12 }}>
            {msg}
          </span>
        )}
      </div>
      <div className="mt-2">
        {cfg.channels.map((ch, i) => {
          const meta = PUSH_CHANNEL_TYPES.find((t) => t.value === ch.type)
          const paramValue = meta?.param === 'send_key' ? (ch.send_key ?? '') : (ch.url ?? '')
          return (
            <div key={i} className="d-flex gap-2 align-items-center mb-1" style={{ fontSize: 13 }}>
              <select
                value={ch.type}
                onChange={(e) => {
                  const t = PUSH_CHANNEL_TYPES.find((x) => x.value === e.target.value)
                  if (t) setChannel(i, { type: t.value, url: undefined, send_key: undefined })
                }}
              >
                {PUSH_CHANNEL_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
              <input
                style={{ flex: 1, minWidth: 260 }}
                placeholder={meta?.placeholder}
                value={paramValue}
                onChange={(e) =>
                  setChannel(i, meta?.param === 'send_key' ? { send_key: e.target.value } : { url: e.target.value })
                }
              />
              <button
                type="button"
                className="btn btn-outline-secondary btn-sm"
                onClick={() => setCfg({ ...cfg, channels: cfg.channels.filter((_, j) => j !== i) })}
              >
                删除
              </button>
            </div>
          )
        })}
        <button
          type="button"
          className="btn btn-outline-secondary btn-sm"
          onClick={() => setCfg({ ...cfg, channels: [...cfg.channels, { type: 'serverchan', send_key: '' }] })}
        >
          + 添加渠道
        </button>
      </div>
      <div className="text-faint mt-1" style={{ fontSize: 11 }}>
        每日扫描落盘后自动推送（企业微信/钉钉为 markdown 摘要，自定义 Webhook 收到完整 JSON）。
      </div>
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
