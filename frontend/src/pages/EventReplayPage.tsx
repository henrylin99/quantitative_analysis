import { useEffect, useMemo, useState } from 'react'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import {
  fetchEventDates,
  fetchEventReplay,
  type EventDatesResult,
  type EventReplayResult,
  type EventSectionKey,
} from '../api/insights'

const SECTION_ORDER: EventSectionKey[] = ['limit_up', 'limit_down', 'limit_break', 'ladder', 'dragon_tiger', 'mood']

const SECTION_COLS: Record<EventSectionKey, { key: string; label: string }[]> = {
  limit_up: [
    { key: 'thscode', label: '代码' }, { key: 'name', label: '名称' },
    { key: 'price_change_ratio_pct', label: '涨跌幅%' }, { key: 'continue_day_cnt', label: '连板数' },
    { key: 'seal_money', label: '封单' }, { key: 'limit_up_time', label: '封板时间' },
    { key: 'limit_up_reason', label: '涨停原因' },
  ],
  limit_down: [
    { key: 'thscode', label: '代码' }, { key: 'name', label: '名称' },
    { key: 'price_change_ratio_pct', label: '涨跌幅%' }, { key: 'first_limit_time', label: '首次跌停' },
  ],
  limit_break: [
    { key: 'thscode', label: '代码' }, { key: 'name', label: '名称' },
    { key: 'price_change_ratio_pct', label: '涨跌幅%' }, { key: 'open_times', label: '打开次数' },
  ],
  ladder: [
    { key: 'board_num', label: '连板高度' }, { key: 'thscode', label: '代码' }, { key: 'name', label: '名称' },
    { key: 'sign_level', label: '标记' }, { key: 'seal_nextday', label: '次日封板' },
  ],
  dragon_tiger: [
    { key: 'thscode', label: '代码' }, { key: 'name', label: '名称' },
    { key: 'change', label: '涨跌幅%' }, { key: 'net_value', label: '净买额' },
    { key: 'hot_money_net_value', label: '游资净额' }, { key: 'limit_reason', label: '上榜原因' },
  ],
  mood: [
    { key: 'limit_up_count', label: '涨停数' }, { key: 'limit_down_count', label: '跌停数' },
    { key: 'break_count', label: '炸板数' }, { key: 'break_rate', label: '炸板率' },
    { key: 'max_streak', label: '最高连板' },
  ],
}

function fmt(v: unknown): string {
  if (v === null || v === undefined || v === '') return '--'
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(2)
  return String(v)
}

export default function EventReplayPage() {
  const [dates, setDates] = useState<EventDatesResult | null>(null)
  const [selected, setSelected] = useState('')
  const [replay, setReplay] = useState<EventReplayResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchEventDates()
      .then((d) => {
        setDates(d)
        const all = Object.values(d).flatMap((v) => v.dates)
        const latest = all.sort()[all.length - 1]
        if (latest) setSelected(latest)
      })
      .catch((e) => setError(e instanceof Error ? e.message : '事件档案加载失败'))
  }, [])

  useEffect(() => {
    if (!selected) return
    setLoading(true)
    setError(null)
    fetchEventReplay(selected)
      .then(setReplay)
      .catch((e) => {
        setError(e instanceof Error ? e.message : '复盘数据加载失败')
        setReplay(null)
      })
      .finally(() => setLoading(false))
  }, [selected])

  const allDates = useMemo(() => {
    const set = new Set<string>()
    Object.values(dates ?? {}).forEach((v) => v.dates.forEach((d) => set.add(d)))
    return Array.from(set).sort().reverse()
  }, [dates])

  const typeCoverage = (d: string) =>
    SECTION_ORDER.filter((t) => dates?.[t]?.dates.includes(d)).length

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>事件复盘</h2>
          <p className="desc">历史交易日的涨停/跌停/炸板/连板天梯/龙虎榜全景回看（事件档案 2026-10 起，随每日归档积累）</p>
        </div>
      </div>

      <div className="panel mb-3">
        <div className="panel-body d-flex gap-2 flex-wrap align-items-center">
          <span className="text-faint" style={{ fontSize: 13 }}>归档日期</span>
          {allDates.length === 0 && <span className="text-faint" style={{ fontSize: 13 }}>暂无归档</span>}
          {allDates.slice(0, 24).map((d) => (
            <button
              key={d}
              type="button"
              className={`btn btn-sm ${selected === d ? 'btn-primary' : 'btn-outline-secondary'}`}
              onClick={() => setSelected(d)}
              title={`覆盖 ${typeCoverage(d)} 类事件`}
            >
              {d.slice(4, 6)}/{d.slice(6)}
            </button>
          ))}
        </div>
      </div>

      {error && <ErrorState message={error} onRetry={() => setSelected(selected)} />}
      {loading && <Loading />}
      {!loading && !error && (!replay || replay.error) && <EmptyState icon="📅" text={replay?.error ?? '选择日期查看事件全景'} />}

      {!loading && !error && replay && !replay.error && (
        <>
          {SECTION_ORDER
            .filter((t) => replay.sections[t])
            .map((t) => {
              const sec = replay.sections[t]!
              const cols = SECTION_COLS[t]
              return (
                <div className="panel mb-3" key={t}>
                  <div className="panel-head">
                    <h6 className="panel-title">
                      <span className="kicker" />
                      {sec.label}
                      <span className="chip">{sec.count} 条</span>
                    </h6>
                  </div>
                  <div className="panel-body tight table-container" style={{ maxHeight: 420 }}>
                    <table className="data-table">
                      <thead>
                        <tr>
                          {cols.map((c) => (
                            <th key={c.key} className={c.key.includes('value') || c.key.includes('money') || c.key === 'change' ? 'num' : ''}>
                              {c.label}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {sec.rows.map((row, i) => (
                          <tr key={i}>
                            {cols.map((c) => (
                              <td key={c.key} className={c.key.includes('value') || c.key.includes('money') || c.key === 'change' ? 'num' : ''}>
                                {fmt(row[c.key])}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )
            })}
        </>
      )}
    </div>
  )
}
