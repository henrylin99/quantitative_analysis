import { useEffect, useMemo, useState } from 'react'
import EChart from '../charts/EChart'
import { useTheme } from '../theme/ThemeContext'
import { fetchHeatmap, type HeatmapSector, type HeatmapStock } from '../api/trial'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { formatNumber, formatPercent, pctClass } from '../utils/format'

type SortMode = 'pct' | 'mv'

/** 红涨绿跌：|pct|≥6% 封顶线性插值，0 为灰 */
function pctColor(p: { up: string; down: string }, pct: number): string {
  const clamp = (v: number) => Math.max(0, Math.min(6, Math.abs(v))) / 6
  const hex = (c: string) => [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16))
  const mix = (a: string, b: string, t: number) => {
    const ca = hex(a)
    const cb = hex(b)
    return `rgb(${ca.map((v, i) => Math.round(v + (cb[i] - v) * t)).join(',')})`
  }
  if (pct > 0) return mix('#bdc3c7', p.up, clamp(pct))
  if (pct < 0) return mix('#bdc3c7', p.down, clamp(pct))
  return '#bdc3c7'
}

export default function HeatmapPage() {
  const { palette } = useTheme()
  const [data, setData] = useState<{ sectors: HeatmapSector[]; stocks: HeatmapStock[]; trade_date: string } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sortMode, setSortMode] = useState<SortMode>('pct')
  const [selected, setSelected] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    setError(null)
    fetchHeatmap()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : '数据加载失败，请确认 data/data.parquet 是否存在'))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const option = useMemo(() => {
    if (!data) return null
    const nodes = [...data.sectors]
      .map((s) => ({
        name: s.name,
        value: sortMode === 'pct' ? Math.max(Math.abs(s.avg_pct_chg), 0.01) : s.total_mv,
        sector: s,
      }))
      .sort((a, b) => b.value - a.value)
    return {
      tooltip: {
        formatter: (p: { data?: { sector: HeatmapSector } }) => {
          const s = p.data?.sector
          if (!s) return ''
          return [
            `<b>${s.name}</b>`,
            `加权涨跌：${formatPercent(s.avg_pct_chg)}`,
            `涨/跌家数：${s.up_count} / ${s.down_count}（共 ${s.stock_count} 只）`,
            `净流入：${formatNumber(s.net_mf_amount / 10000, 2)} 亿`,
          ].join('<br/>')
        },
      },
      series: [
        {
          type: 'treemap' as const,
          roam: false,
          nodeClick: false,
          breadcrumb: { show: false },
          width: '100%',
          height: '88%',
          top: 8,
          itemStyle: { borderColor: 'rgba(0,0,0,0.35)', gapWidth: 2 },
          label: { show: true, formatter: '{b}\n{c}' },
          upperLabel: { show: false },
          data: nodes.map((n) => ({
            name: n.name,
            value: n.value,
            sector: n.sector,
            itemStyle: { color: pctColor(palette, n.sector.avg_pct_chg) },
            label: { formatter: `${n.name}\n${formatPercent(n.sector.avg_pct_chg)}` },
          })),
        },
      ],
    }
  }, [data, sortMode, palette])

  const detailStocks = useMemo(() => {
    if (!data || !selected) return []
    return data.stocks.filter((s) => s.industry === selected)
  }, [data, selected])

  const selectedSector = data?.sectors.find((s) => s.name === selected)

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>板块热力图</h2>
          <p className="desc">
            行业市值与涨跌幅分布 · 交易日 <code>{data?.trade_date ?? '--'}</code>
          </p>
        </div>
        <div className="d-flex align-items-center gap-2 flex-wrap">
          <div className="seg" role="group">
            <button type="button" className={`seg-item ${sortMode === 'pct' ? 'active' : ''}`} onClick={() => setSortMode('pct')}>
              涨跌幅排序
            </button>
            <button type="button" className={`seg-item ${sortMode === 'mv' ? 'active' : ''}`} onClick={() => setSortMode('mv')}>
              市值排序
            </button>
          </div>
          <div
            className="d-flex align-items-center gap-1"
            style={{ fontSize: 11.5, color: 'var(--text-faint)' }}
            aria-hidden
          >
            跌
            <span
              style={{
                width: 90,
                height: 8,
                borderRadius: 4,
                display: 'inline-block',
                background: `linear-gradient(90deg, ${palette.down}, #bdc3c7, ${palette.up})`,
              }}
            />
            涨
          </div>
        </div>
      </div>

      {loading && <Loading text="读取大宽表并聚合行业..." />}
      {error && <ErrorState message={error} onRetry={load} />}

      {data && !loading && !error && (
        <>
          <div className="panel">
            <div className="panel-body">
              {option ? (
                <EChart
                  option={option}
                  height={560}
                  onClick={(p) => {
                    const name = (p as { name?: string }).name
                    if (name) setSelected((prev) => (prev === name ? null : name))
                  }}
                />
              ) : (
                <EmptyState icon="🔥" text="暂无板块数据" />
              )}
            </div>
          </div>

          {selected && selectedSector && (
            <div className="panel">
              <div className="panel-head">
                <h6 className="panel-title">
                  <span className="kicker" />
                  {selected}
                  <span className="chip">{detailStocks.length} 只</span>
                  <span className={`delta ${selectedSector.avg_pct_chg >= 0 ? 'up' : 'down'}`}>
                    加权 {formatPercent(selectedSector.avg_pct_chg)}
                  </span>
                </h6>
                <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => setSelected(null)}>
                  关闭 ×
                </button>
              </div>
              <div className="panel-body tight table-container" style={{ maxHeight: 480 }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>名称</th>
                      <th className="num">涨跌幅</th>
                      <th className="num">收盘价</th>
                      <th className="num">总市值(亿)</th>
                      <th className="num">净流入(万)</th>
                      <th className="num">换手率</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detailStocks.map((s) => (
                      <tr key={s.ts_code}>
                        <td style={{ fontWeight: 600 }}>{s.name}</td>
                        <td className={`num ${pctClass(s.pct_chg)}`}>{formatPercent(s.pct_chg)}</td>
                        <td className="num">{formatNumber(s.close, 2)}</td>
                        <td className="num">{formatNumber((s.total_mv ?? 0) / 10000, 2)}</td>
                        <td className={`num ${pctClass(s.net_mf_amount)}`}>{formatNumber(s.net_mf_amount, 0)}</td>
                        <td className="num">{formatNumber(s.turnover_rate, 2)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          <div className="empty-state" style={{ paddingTop: 12 }}>
            <div className="hint">提示：点击板块方块下钻查看个股明细，再次点击关闭。</div>
          </div>
        </>
      )}
    </div>
  )
}
