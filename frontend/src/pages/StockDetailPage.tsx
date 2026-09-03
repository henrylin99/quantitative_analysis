import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import EChart from '../charts/EChart'
import { useTheme } from '../theme/ThemeContext'
import {
  fetchStockCompany,
  fetchStockCyq,
  fetchStockFinancials,
  fetchStockMoneyflow,
  type CyqRow,
  type FinancialStatements,
  type MoneyflowRow,
} from '../api/stockExtra'
import { fetchStockFactors, fetchStockHistory, fetchStockInfo } from '../api/stocks'
import type { DailyBar, FactorRow, StockBasic } from '../api/types'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { formatNumber, formatPercent, pctClass } from '../utils/format'

const TABS = [
  { key: 'history', label: '历史数据' },
  { key: 'factors', label: '技术因子' },
  { key: 'moneyflow', label: '资金流向' },
  { key: 'cyq', label: '筹码分布' },
  { key: 'financials', label: '财务数据' },
  { key: 'company', label: '公司信息' },
] as const

type TabKey = (typeof TABS)[number]['key']

const FINANCIAL_FIELD_META: Record<string, [string, string, 'monetary' | 'eps'][]> = {
  balance_sheet: [
    ['total_assets', '总资产', 'monetary'],
    ['total_cur_assets', '流动资产合计', 'monetary'],
    ['money_cap', '货币资金', 'monetary'],
    ['accounts_receiv', '应收账款', 'monetary'],
    ['inventories', '存货', 'monetary'],
    ['fix_assets', '固定资产', 'monetary'],
    ['intan_assets', '无形资产', 'monetary'],
    ['goodwill', '商誉', 'monetary'],
    ['total_liab', '总负债', 'monetary'],
    ['total_cur_liab', '流动负债合计', 'monetary'],
    ['st_borr', '短期借款', 'monetary'],
    ['lt_borr', '长期借款', 'monetary'],
    ['total_hldr_eqy_inc_min_int', '所有者权益合计', 'monetary'],
    ['total_share', '总股本', 'monetary'],
    ['undistr_porfit', '未分配利润', 'monetary'],
    ['surplus_rese', '盈余公积', 'monetary'],
  ],
  income_statement: [
    ['total_revenue', '营业总收入', 'monetary'],
    ['revenue', '营业收入', 'monetary'],
    ['total_cogs', '营业总成本', 'monetary'],
    ['oper_cost', '营业成本', 'monetary'],
    ['sell_exp', '销售费用', 'monetary'],
    ['admin_exp', '管理费用', 'monetary'],
    ['fin_exp', '财务费用', 'monetary'],
    ['rd_exp', '研发费用', 'monetary'],
    ['operate_profit', '营业利润', 'monetary'],
    ['total_profit', '利润总额', 'monetary'],
    ['income_tax', '所得税', 'monetary'],
    ['n_income', '净利润', 'monetary'],
    ['n_income_attr_p', '归属净利润', 'monetary'],
    ['basic_eps', '基本每股收益', 'eps'],
    ['diluted_eps', '稀释每股收益', 'eps'],
  ],
  cash_flow: [
    ['n_cashflow_act', '经营活动现金流净额', 'monetary'],
    ['c_inf_fr_operate_a', '经营活动现金流入小计', 'monetary'],
    ['st_cash_out_act', '经营活动现金流出小计', 'monetary'],
    ['n_cashflow_inv_act', '投资活动现金流净额', 'monetary'],
    ['stot_inflows_inv_act', '投资活动现金流入小计', 'monetary'],
    ['stot_out_inv_act', '投资活动现金流出小计', 'monetary'],
    ['n_cash_flows_fnc_act', '筹资活动现金流净额', 'monetary'],
    ['stot_cash_in_fnc_act', '筹资活动现金流入小计', 'monetary'],
    ['stot_cashout_fnc_act', '筹资活动现金流出小计', 'monetary'],
    ['n_incr_cash_cash_equ', '现金及等价物净增加额', 'monetary'],
    ['c_cash_equ_end_period', '期末现金及等价物余额', 'monetary'],
  ],
}

const COMPANY_FIELD_LABELS: Record<string, string> = {
  ts_code: 'TS代码',
  com_name: '公司全称',
  com_id: '统一社会信用代码',
  exchange: '交易所',
  chairman: '法人代表',
  manager: '总经理',
  secretary: '董秘',
  reg_capital: '注册资本',
  setup_date: '注册日期',
  province: '所在省份',
  city: '所在城市',
  introduction: '公司介绍',
  website: '公司主页',
  email: '电子邮件',
  office: '办公室',
  employees: '员工人数',
  main_business: '主要业务及产品',
  business_scope: '经营范围',
}

function sortByDateAsc<T extends { trade_date: string }>(rows: T[]): T[] {
  return [...rows].sort((a, b) => a.trade_date.localeCompare(b.trade_date))
}

function fmtMoneyWan(value: unknown): string {
  const n = Number(value)
  if (value === null || value === undefined || Number.isNaN(n)) return '--'
  return `${formatNumber(n / 10000, 2)} 万`
}

function MetricCard({ label, value, hint, valueClass }: { label: string; value: string; hint?: string; valueClass?: string }) {
  return (
    <div className="stat">
      <div className={`stat-value ${valueClass ?? ''}`} style={{ fontSize: 20 }}>
        {value}
      </div>
      <div className="stat-label">{label}</div>
      {hint && <div className="sub">{hint}</div>}
    </div>
  )
}

export default function StockDetailPage() {
  const { tsCode = '' } = useParams()
  const { palette } = useTheme()

  const [info, setInfo] = useState<StockBasic | null>(null)
  const [activeTab, setActiveTab] = useState<TabKey>('history')

  // 各 tab 独立的数据/加载/错误状态（切回已加载 tab 会重新拉取，与旧版行为一致）
  const [historyLimit, setHistoryLimit] = useState(60)
  const [history, setHistory] = useState<DailyBar[] | null>(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState<string | null>(null)

  const [factors, setFactors] = useState<FactorRow[] | null>(null)
  const [factorsLoading, setFactorsLoading] = useState(false)
  const [factorsError, setFactorsError] = useState<string | null>(null)

  const [moneyflow, setMoneyflow] = useState<MoneyflowRow[] | null>(null)
  const [mfLoading, setMfLoading] = useState(false)
  const [mfError, setMfError] = useState<string | null>(null)

  const [cyq, setCyq] = useState<CyqRow[] | null>(null)
  const [cyqLoading, setCyqLoading] = useState(false)
  const [cyqError, setCyqError] = useState<string | null>(null)

  const [financials, setFinancials] = useState<FinancialStatements | null>(null)
  const [finLoading, setFinLoading] = useState(false)
  const [finError, setFinError] = useState<string | null>(null)

  const [company, setCompany] = useState<Record<string, unknown> | null>(null)
  const [comLoading, setComLoading] = useState(false)
  const [comError, setComError] = useState<string | null>(null)

  useEffect(() => {
    setInfo(null)
    fetchStockInfo(tsCode).then(setInfo).catch(() => setInfo(null))
  }, [tsCode])

  useEffect(() => {
    if (activeTab !== 'history') return
    setHistoryLoading(true)
    setHistoryError(null)
    fetchStockHistory(tsCode, historyLimit)
      .then(setHistory)
      .catch((e) => setHistoryError(e instanceof Error ? e.message : '历史数据加载失败'))
      .finally(() => setHistoryLoading(false))
  }, [activeTab, tsCode, historyLimit])

  useEffect(() => {
    if (activeTab !== 'factors') return
    setFactorsLoading(true)
    setFactorsError(null)
    fetchStockFactors(tsCode, 20)
      .then(setFactors)
      .catch((e) => setFactorsError(e instanceof Error ? e.message : '技术因子加载失败'))
      .finally(() => setFactorsLoading(false))
  }, [activeTab, tsCode])

  useEffect(() => {
    if (activeTab !== 'moneyflow') return
    setMfLoading(true)
    setMfError(null)
    fetchStockMoneyflow(tsCode, 20)
      .then(setMoneyflow)
      .catch((e) => setMfError(e instanceof Error ? e.message : '资金流向加载失败'))
      .finally(() => setMfLoading(false))
  }, [activeTab, tsCode])

  useEffect(() => {
    if (activeTab !== 'cyq') return
    setCyqLoading(true)
    setCyqError(null)
    fetchStockCyq(tsCode, 20)
      .then(setCyq)
      .catch((e) => setCyqError(e instanceof Error ? e.message : '筹码数据加载失败'))
      .finally(() => setCyqLoading(false))
  }, [activeTab, tsCode])

  useEffect(() => {
    if (activeTab !== 'financials') return
    setFinLoading(true)
    setFinError(null)
    fetchStockFinancials(tsCode)
      .then(setFinancials)
      .catch((e) => setFinError(e instanceof Error ? e.message : '财务数据加载失败'))
      .finally(() => setFinLoading(false))
  }, [activeTab, tsCode])

  useEffect(() => {
    if (activeTab !== 'company') return
    setComLoading(true)
    setComError(null)
    fetchStockCompany(tsCode)
      .then(setCompany)
      .catch((e) => setComError(e instanceof Error ? e.message : '公司信息加载失败'))
      .finally(() => setComLoading(false))
  }, [activeTab, tsCode])

  const latestClose = history && history.length > 0 ? history[0].close : null

  // —— 技术因子图（DIF/DEA/MACD 左轴；RSI/KDJ 右轴 0-100） ——
  const factorChartOption = useMemo(() => {
    if (!factors || factors.length === 0) return null
    const asc = sortByDateAsc(factors)
    const dates = asc.map((r) => r.trade_date.slice(0, 10))
    const line = (field: keyof FactorRow, name: string, yAxisIndex = 0) => ({
      name,
      type: 'line' as const,
      yAxisIndex,
      showSymbol: false,
      connectNulls: false,
      data: asc.map((r) => {
        const v = r[field]
        return typeof v === 'number' && !Number.isNaN(v) ? v : null
      }),
    })
    const macdBar = {
      name: 'MACD',
      type: 'bar' as const,
      yAxisIndex: 0,
      data: asc.map((r) =>
        typeof r.macd === 'number' && !Number.isNaN(r.macd)
          ? { value: r.macd, itemStyle: { color: r.macd >= 0 ? palette.upSoft : palette.downSoft } }
          : null,
      ),
    }
    return {
      dataZoom: [
        { type: 'inside', start: 30, end: 100 },
        { type: 'slider', start: 30, end: 100, height: 18, bottom: 6 },
      ],
      legend: { type: 'scroll', top: 0 },
      grid: { left: 56, right: 52, top: 34, bottom: 52 },
      tooltip: { trigger: 'axis' },
      yAxis: [{ type: 'value' }, { type: 'value', min: 0, max: 100 }],
      xAxis: { type: 'category', data: dates, boundaryGap: false },
      series: [
        line('macd_dif', 'DIF'),
        line('macd_dea', 'DEA'),
        macdBar,
        line('rsi_6', 'RSI6', 1),
        line('rsi_12', 'RSI12', 1),
        line('kdj_k', 'KDJ-K', 1),
        line('kdj_d', 'KDJ-D', 1),
      ],
    }
  }, [factors, palette])

  // —— 资金流：最新一日分单买卖对撞 + 净流入趋势 ——
  const mfAsc = useMemo(() => (moneyflow ? sortByDateAsc(moneyflow) : null), [moneyflow])
  const mfLatest = mfAsc && mfAsc.length > 0 ? mfAsc[mfAsc.length - 1] : null

  const mfBarOption = useMemo(() => {
    if (!mfLatest) return null
    const cats = ['特大单', '大单', '中单', '小单']
    const buy = [mfLatest.buy_elg_amount, mfLatest.buy_lg_amount, mfLatest.buy_md_amount, mfLatest.buy_sm_amount]
    const sell = [mfLatest.sell_elg_amount, mfLatest.sell_lg_amount, mfLatest.sell_md_amount, mfLatest.sell_sm_amount]
    return {
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => `${formatNumber(Math.abs(Number(v)), 2)} 万` },
      legend: { top: 0 },
      grid: { left: 64, right: 16, top: 34, bottom: 26 },
      xAxis: { type: 'category', data: cats },
      yAxis: { type: 'value' },
      series: [
        {
          name: '买入',
          type: 'bar',
          itemStyle: { color: palette.up },
          data: buy.map((v) => (v == null ? null : Math.abs(v))),
        },
        {
          name: '卖出',
          type: 'bar',
          itemStyle: { color: palette.down },
          data: sell.map((v) => (v == null ? null : -Math.abs(v))),
        },
      ],
    }
  }, [mfLatest, palette])

  const netflowOption = useMemo(() => {
    if (!mfAsc || mfAsc.length === 0) return null
    return {
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => `${formatNumber(Number(v), 2)} 万` },
      grid: { left: 64, right: 16, top: 20, bottom: 26 },
      xAxis: { type: 'category', data: mfAsc.map((r) => r.trade_date.slice(0, 10)), boundaryGap: false },
      yAxis: { type: 'value', axisLabel: { formatter: '{value}万' } },
      series: [
        {
          name: '主力净流入',
          type: 'line',
          smooth: true,
          showSymbol: false,
          lineStyle: { color: palette.accent },
          areaStyle: { color: palette.accent, opacity: 0.18 },
          data: mfAsc.map((r) => r.net_mf_amount),
        },
      ],
    }
  }, [mfAsc, palette])

  // 资金形态指标（口径与旧版一致）
  const mfStats = useMemo(() => {
    if (!mfLatest) return null
    const buys = [mfLatest.buy_elg_amount, mfLatest.buy_lg_amount, mfLatest.buy_md_amount, mfLatest.buy_sm_amount]
    const buySum = buys.reduce<number>((acc, v) => acc + (v ?? 0), 0)
    const lgPct = buySum > 0 && mfLatest.buy_lg_amount != null ? (mfLatest.buy_lg_amount / buySum) * 100 : null
    const elgPct = buySum > 0 && mfLatest.buy_elg_amount != null ? (mfLatest.buy_elg_amount / buySum) * 100 : null
    const mainNet =
      (mfLatest.buy_elg_amount ?? 0) + (mfLatest.buy_lg_amount ?? 0) - (mfLatest.sell_elg_amount ?? 0) - (mfLatest.sell_lg_amount ?? 0)
    return { lgPct, elgPct, mainNet }
  }, [mfLatest])

  // —— 筹码：成本分位曲线 + 胜率 ——
  const cyqAsc = useMemo(() => (cyq ? sortByDateAsc(cyq) : null), [cyq])

  const costOption = useMemo(() => {
    if (!cyqAsc || cyqAsc.length === 0) return null
    const dates = cyqAsc.map((r) => r.trade_date.slice(0, 10))
    const mk = (field: keyof CyqRow, name: string, color: string, width = 1, dashed = false) => ({
      name,
      type: 'line' as const,
      showSymbol: false,
      connectNulls: false,
      lineStyle: { color, width, type: dashed ? ('dashed' as const) : ('solid' as const) },
      itemStyle: { color },
      data: cyqAsc.map((r) => {
        const v = r[field]
        return typeof v === 'number' && !Number.isNaN(v) ? v : null
      }),
    })
    return {
      tooltip: { trigger: 'axis' },
      legend: { top: 0 },
      grid: { left: 60, right: 16, top: 34, bottom: 26 },
      xAxis: { type: 'category', data: dates, boundaryGap: false },
      yAxis: { type: 'value', scale: true },
      series: [
        mk('cost_5pct', '5%分位', palette.down),
        mk('cost_15pct', '15%分位', '#22d3ee'),
        mk('cost_50pct', '50%分位', palette.accent, 2),
        mk('cost_85pct', '85%分位', '#fbbf24'),
        mk('cost_95pct', '95%分位', palette.up),
        mk('weight_avg', '加权平均', '#f472b6', 1, true),
      ],
    }
  }, [cyqAsc, palette])

  const winnerOption = useMemo(() => {
    if (!cyqAsc || cyqAsc.length === 0) return null
    return {
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => `${formatNumber(Number(v), 2)}%` },
      grid: { left: 56, right: 16, top: 20, bottom: 26 },
      xAxis: { type: 'category', data: cyqAsc.map((r) => r.trade_date.slice(0, 10)), boundaryGap: false },
      yAxis: { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%' } },
      series: [
        {
          name: '胜率',
          type: 'line',
          showSymbol: false,
          lineStyle: { color: palette.teal },
          areaStyle: { color: palette.teal, opacity: 0.18 },
          markLine: {
            silent: true,
            symbol: 'none',
            lineStyle: { type: 'dashed', color: palette.amber },
            data: [{ yAxis: 50, label: { formatter: '50%', color: palette.amber } }],
          },
          data: cyqAsc.map((r) => r.winner_rate),
        },
      ],
    }
  }, [cyqAsc, palette])

  const cyqStats = useMemo(() => {
    const latest = cyqAsc && cyqAsc.length > 0 ? cyqAsc[cyqAsc.length - 1] : null
    if (!latest) return null
    const concentration =
      latest.cost_95pct != null && latest.cost_5pct != null && latest.cost_50pct
        ? ((latest.cost_95pct - latest.cost_5pct) / latest.cost_50pct) * 100
        : null
    const position =
      latestClose != null && latest.cost_5pct != null && latest.cost_95pct != null && latest.cost_95pct !== latest.cost_5pct
        ? ((latestClose - latest.cost_5pct) / (latest.cost_95pct - latest.cost_5pct)) * 100
        : null
    return { latest, concentration, position }
  }, [cyqAsc, latestClose])

  const tabBodyLoading = { history: historyLoading, factors: factorsLoading, moneyflow: mfLoading, cyq: cyqLoading, financials: finLoading, company: comLoading }[activeTab]
  const tabBodyError = { history: historyError, factors: factorsError, moneyflow: mfError, cyq: cyqError, financials: finError, company: comError }[activeTab]

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>个股详情</h2>
          <p className="desc">
            <code>{tsCode}</code> · 行情 / 因子 / 资金 / 筹码 / 财务 / 公司资料
          </p>
        </div>
      </div>

      {/* 基本信息 + 快速操作 */}
      <div className="panel">
        <div className="panel-body d-flex align-items-center justify-content-between flex-wrap gap-3">
          {info ? (
            <div>
              <span style={{ fontSize: 19, fontWeight: 750 }}>{info.name}</span>
              <code style={{ marginLeft: 10 }}>{info.ts_code}</code>
              <span className={`badge ms-2 ${info.ts_code.endsWith('.SH') ? 'bg-danger' : 'bg-success'}`}>
                {info.ts_code.endsWith('.SH') ? '上海' : '深圳'}
              </span>
              <div className="d-flex gap-2 mt-2 flex-wrap">
                <span className="chip">行业 · {info.industry ?? '--'}</span>
                <span className="chip">地域 · {info.area ?? '--'}</span>
                <span className="chip">上市 · {info.list_date ?? '--'}</span>
              </div>
            </div>
          ) : (
            <div>
              <span style={{ fontSize: 19, fontWeight: 750 }}>{tsCode}</span>
              <span className="chip ms-2">基本信息加载失败，可继续查看分 Tab 数据</span>
            </div>
          )}
          <div className="d-flex gap-2">
            <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => window.alert('已加入自选股（演示功能）')}>
              ☆ 自选
            </button>
            <Link className="btn btn-outline-primary btn-sm" to={`/analysis?stock=${tsCode}`}>
              📈 技术分析
            </Link>
            <Link className="btn btn-outline-primary btn-sm" to={`/backtest?stock=${tsCode}`}>
              🧪 策略回测
            </Link>
          </div>
        </div>
      </div>

      {/* 六 Tab */}
      <div className="seg mb-3" role="group" style={{ flexWrap: 'wrap' }}>
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            className={`seg-item ${activeTab === tab.key ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {tabBodyLoading && <Loading text="加载中..." />}
      {tabBodyError && <ErrorState message={tabBodyError} onRetry={() => setActiveTab((t) => t)} />}

      {/* 历史数据 */}
      {activeTab === 'history' && !tabBodyLoading && !tabBodyError && (
        <div className="panel">
          <div className="panel-head">
            <h6 className="panel-title">
              <span className="kicker" />
              历史数据
              <span className="chip">展示最新 20 条</span>
            </h6>
            <div className="seg" role="group">
              {[30, 60, 120].map((n) => (
                <button key={n} type="button" className={`seg-item ${historyLimit === n ? 'active' : ''}`} onClick={() => setHistoryLimit(n)}>
                  {n}天
                </button>
              ))}
            </div>
          </div>
          <div className="panel-body tight table-container" style={{ maxHeight: 520 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>日期</th>
                  <th className="num">开盘</th>
                  <th className="num">最高</th>
                  <th className="num">最低</th>
                  <th className="num">收盘</th>
                  <th className="num">成交量(万手)</th>
                  <th className="num">成交额(万)</th>
                  <th className="num">涨跌幅</th>
                </tr>
              </thead>
              <tbody>
                {(history ?? []).slice(0, 20).map((row) => (
                  <tr key={row.trade_date}>
                    <td>{row.trade_date}</td>
                    <td className="num">{formatNumber(row.open, 2)}</td>
                    <td className="num" style={{ color: palette.up }}>
                      {formatNumber(row.high, 2)}
                    </td>
                    <td className="num" style={{ color: palette.down }}>
                      {formatNumber(row.low, 2)}
                    </td>
                    <td className="num" style={{ fontWeight: 650 }}>
                      {formatNumber(row.close, 2)}
                    </td>
                    <td className="num">{formatNumber((row.vol ?? 0) / 10000, 1)}</td>
                    <td className="num">{formatNumber((row.amount ?? 0) / 10, 0)}</td>
                    <td className={`num ${pctClass(row.pct_chg)}`}>{formatPercent(row.pct_chg)}</td>
                  </tr>
                ))}
                {history && history.length === 0 && (
                  <tr>
                    <td colSpan={8}>
                      <EmptyState icon="📭" text="暂无历史数据" />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 技术因子 */}
      {activeTab === 'factors' && !tabBodyLoading && !tabBodyError && (
        <>
          <div className="panel">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                技术指标趋势
              </h6>
            </div>
            <div className="panel-body">
              {factorChartOption ? <EChart option={factorChartOption} height={420} /> : <EmptyState icon="📉" text="暂无因子数据" />}
            </div>
          </div>
          <div className="panel">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                因子明细
                <span className="chip">{(factors ?? []).slice(0, 20).length} 条</span>
              </h6>
            </div>
            <div className="panel-body tight table-container" style={{ maxHeight: 460 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>日期</th>
                    <th className="num">收盘</th>
                    <th className="num">DIF</th>
                    <th className="num">DEA</th>
                    <th className="num">MACD</th>
                    <th className="num">KDJ-K</th>
                    <th className="num">KDJ-D</th>
                    <th className="num">KDJ-J</th>
                    <th className="num">RSI6</th>
                    <th className="num">RSI12</th>
                    <th className="num">RSI24</th>
                    <th className="num">BOLL上</th>
                    <th className="num">BOLL中</th>
                    <th className="num">BOLL下</th>
                    <th className="num">CCI</th>
                  </tr>
                </thead>
                <tbody>
                  {(factors ?? []).slice(0, 20).map((row) => (
                    <tr key={row.trade_date}>
                      <td>{row.trade_date}</td>
                      <td className="num">{formatNumber(row.close, 2)}</td>
                      <td className="num">{formatNumber(row.macd_dif, 4)}</td>
                      <td className="num">{formatNumber(row.macd_dea, 4)}</td>
                      <td className={`num ${pctClass(row.macd)}`}>{formatNumber(row.macd, 4)}</td>
                      <td className="num">{formatNumber(row.kdj_k, 2)}</td>
                      <td className="num">{formatNumber(row.kdj_d, 2)}</td>
                      <td className={`num ${row.kdj_j != null ? (row.kdj_j > 80 ? 'text-up' : row.kdj_j < 20 ? 'text-down' : '') : ''}`}>
                        {formatNumber(row.kdj_j, 2)}
                      </td>
                      <td className={`num ${row.rsi_6 != null ? (row.rsi_6 > 70 ? 'text-up' : row.rsi_6 < 30 ? 'text-down' : '') : ''}`}>
                        {formatNumber(row.rsi_6, 2)}
                      </td>
                      <td className="num">{formatNumber(row.rsi_12, 2)}</td>
                      <td className="num">{formatNumber(row.rsi_24, 2)}</td>
                      <td className="num">{formatNumber(row.boll_upper, 2)}</td>
                      <td className="num">{formatNumber(row.boll_mid, 2)}</td>
                      <td className="num">{formatNumber(row.boll_lower, 2)}</td>
                      <td className={`num ${row.cci != null ? (row.cci > 100 ? 'text-up' : row.cci < -100 ? 'text-down' : '') : ''}`}>
                        {formatNumber(row.cci, 2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* 资金流向 */}
      {activeTab === 'moneyflow' && !tabBodyLoading && !tabBodyError && (
        <>
          {mfStats && mfLatest && (
            <div className="stat-grid">
              <MetricCard label="主力净流入（万）" value={formatNumber(mfStats.mainNet, 2)} valueClass={pctClass(mfStats.mainNet)} />
              <MetricCard label="大单买入占比" value={formatNumber(mfStats.lgPct, 1) + '%'} />
              <MetricCard label="特大单买入占比" value={formatNumber(mfStats.elgPct, 1) + '%'} />
              <MetricCard label="当日净流入（万）" value={formatNumber(mfLatest.net_mf_amount, 2)} valueClass={pctClass(mfLatest.net_mf_amount)} />
            </div>
          )}
          <div className="row g-3">
            <div className="col-lg-8">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    分单资金买卖对比（{mfLatest ? mfLatest.trade_date : '--'}，万元）
                  </h6>
                </div>
                <div className="panel-body">
                  {mfBarOption ? <EChart option={mfBarOption} height={320} /> : <EmptyState icon="💸" text="暂无资金流数据" />}
                </div>
              </div>
            </div>
            <div className="col-lg-4">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    净流入趋势
                  </h6>
                </div>
                <div className="panel-body">
                  {netflowOption ? <EChart option={netflowOption} height={320} /> : <EmptyState icon="📉" text="暂无数据" />}
                </div>
              </div>
            </div>
          </div>
          <div className="panel">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                资金流明细
                <span className="chip">最新 {(moneyflow ?? []).slice(0, 20).length} 条 · 万元</span>
              </h6>
            </div>
            <div className="panel-body tight table-container" style={{ maxHeight: 440 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>日期</th>
                    <th className="num">净流入</th>
                    <th className="num">特大买</th>
                    <th className="num">特大卖</th>
                    <th className="num">大单买</th>
                    <th className="num">大单卖</th>
                    <th className="num">中单买</th>
                    <th className="num">中单卖</th>
                    <th className="num">小单买</th>
                    <th className="num">小单卖</th>
                  </tr>
                </thead>
                <tbody>
                  {[...(moneyflow ?? [])].slice(0, 20).map((row) => (
                    <tr key={row.trade_date}>
                      <td>{row.trade_date}</td>
                      <td className={`num ${pctClass(row.net_mf_amount)}`}>{formatNumber(row.net_mf_amount, 2)}</td>
                      <td className="num">{formatNumber(row.buy_elg_amount, 2)}</td>
                      <td className="num">{formatNumber(row.sell_elg_amount, 2)}</td>
                      <td className="num">{formatNumber(row.buy_lg_amount, 2)}</td>
                      <td className="num">{formatNumber(row.sell_lg_amount, 2)}</td>
                      <td className="num">{formatNumber(row.buy_md_amount, 2)}</td>
                      <td className="num">{formatNumber(row.sell_md_amount, 2)}</td>
                      <td className="num">{formatNumber(row.buy_sm_amount, 2)}</td>
                      <td className="num">{formatNumber(row.sell_sm_amount, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* 筹码分布 */}
      {activeTab === 'cyq' && !tabBodyLoading && !tabBodyError && (
        <>
          {cyqStats && (
            <div className="stat-grid">
              <MetricCard
                label="胜率（最新）"
                value={formatNumber(cyqStats.latest.winner_rate, 1) + '%'}
                valueClass={cyqStats.latest.winner_rate != null && cyqStats.latest.winner_rate >= 50 ? 'text-up' : 'text-down'}
              />
              <MetricCard label="筹码集中度" value={formatNumber(cyqStats.concentration, 1) + '%'} hint="(95%分位−5%分位)/50%分位" />
              <MetricCard label="价格相对位置" value={formatNumber(cyqStats.position, 1) + '%'} hint="最新收盘价在成本区间分位" />
              <MetricCard label="加权平均成本" value={formatNumber(cyqStats.latest.weight_avg, 2)} />
            </div>
          )}
          <div className="row g-3">
            <div className="col-lg-7">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    成本分位曲线
                  </h6>
                </div>
                <div className="panel-body">
                  {costOption ? <EChart option={costOption} height={320} /> : <EmptyState icon="🎲" text="暂无筹码数据" />}
                </div>
              </div>
            </div>
            <div className="col-lg-5">
              <div className="panel h-100">
                <div className="panel-head">
                  <h6 className="panel-title">
                    <span className="kicker" />
                    胜率变化
                  </h6>
                </div>
                <div className="panel-body">
                  {winnerOption ? <EChart option={winnerOption} height={320} /> : <EmptyState icon="📉" text="暂无数据" />}
                </div>
              </div>
            </div>
          </div>
          <div className="panel">
            <div className="panel-head">
              <h6 className="panel-title">
                <span className="kicker" />
                筹码明细
                <span className="chip">最新 {(cyq ?? []).slice(0, 20).length} 条</span>
              </h6>
            </div>
            <div className="panel-body tight table-container" style={{ maxHeight: 440 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>日期</th>
                    <th className="num">5%分位</th>
                    <th className="num">15%分位</th>
                    <th className="num">50%分位</th>
                    <th className="num">85%分位</th>
                    <th className="num">95%分位</th>
                    <th className="num">加权平均</th>
                    <th className="num">胜率%</th>
                  </tr>
                </thead>
                <tbody>
                  {[...(cyq ?? [])].slice(0, 20).map((row) => (
                    <tr key={row.trade_date}>
                      <td>{row.trade_date}</td>
                      <td className="num">{formatNumber(row.cost_5pct, 2)}</td>
                      <td className="num">{formatNumber(row.cost_15pct, 2)}</td>
                      <td className="num">{formatNumber(row.cost_50pct, 2)}</td>
                      <td className="num">{formatNumber(row.cost_85pct, 2)}</td>
                      <td className="num">{formatNumber(row.cost_95pct, 2)}</td>
                      <td className="num">{formatNumber(row.weight_avg, 2)}</td>
                      <td className="num">{formatNumber(row.winner_rate, 1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* 财务数据 */}
      {activeTab === 'financials' && !tabBodyLoading && !tabBodyError && (
        <>
          {financials && (financials.balance_sheet || financials.income_statement || financials.cash_flow) ? (
            <div className="row g-3">
              {(
                [
                  ['balance_sheet', '资产负债表'],
                  ['income_statement', '利润表'],
                  ['cash_flow', '现金流量表'],
                ] as const
              ).map(([key, title]) => {
                const row = financials[key]
                const meta = FINANCIAL_FIELD_META[key]
                return (
                  <div className="col-lg-4" key={key}>
                    <div className="panel h-100">
                      <div className="panel-head">
                        <h6 className="panel-title">
                          <span className="kicker" />
                          {title}
                        </h6>
                        <span className="chip">报告期 {String(row?.end_date ?? '--')}</span>
                      </div>
                      <div className="panel-body tight table-container" style={{ maxHeight: 520 }}>
                        <table className="data-table kv-table">
                          <tbody>
                            {meta.map(([field, label, kind]) => (
                              <tr key={field}>
                                <td style={{ width: '55%' }}>{label}</td>
                                <td className="num">
                                  {kind === 'eps' ? `${formatNumber(Number(row?.[field]), 2)} 元` : fmtMoneyWan(row?.[field])}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <EmptyState icon="🏦" text="暂无财务数据" />
          )}
        </>
      )}

      {/* 公司信息 */}
      {activeTab === 'company' && !tabBodyLoading && !tabBodyError && (
        <div className="panel">
          <div className="panel-head">
            <h6 className="panel-title">
              <span className="kicker" />
              公司信息
            </h6>
          </div>
          <div className="panel-body tight table-container">
            {company && Object.keys(company).length > 0 ? (
              <table className="data-table kv-table">
                <tbody>
                  {Object.entries(company).map(([key, value]) => (
                    <tr key={key}>
                      <td style={{ width: 220 }}>{COMPANY_FIELD_LABELS[key] ?? key}</td>
                      <td style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                        {value === null || value === undefined || value === '' ? '--' : String(value)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <EmptyState icon="🏢" text="暂无公司信息" />
            )}
          </div>
        </div>
      )}
    </div>
  )
}
