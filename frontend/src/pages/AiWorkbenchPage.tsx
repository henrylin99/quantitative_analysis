import { useEffect, useMemo, useRef, useState } from 'react'
import type React from 'react'
import { fetchAiMessages, fetchAiSessions, fetchAiStatus, streamAiChat, deleteAiSession, type AiMessage, type AiSession, type AiStatus } from '../api/ai'
import { EmptyState } from '../components/StateViews'
import { formatDateTime } from '../utils/format'

interface ToolCallView {
  callId: string
  name: string
  args: Record<string, unknown>
  ok?: boolean
  result?: unknown
  durationMs?: number
  running: boolean
}

interface ChatItem {
  role: 'user' | 'assistant'
  content: string
  tools?: ToolCallView[]
}

const QUICK_QUESTIONS = ['今天市场整体表现如何？', '查看 000001.SZ 最新行情', '帮我算一下近5日涨幅前列的股票', '构建大宽表', '现在有哪些自定义因子？', '创业板今天的成交额']

/** 轻量 markdown 渲染：代码块/行内代码/粗体/表格/换行（与旧版口径一致） */
function renderMarkdown(text: string): React.ReactElement {
  const blocks: React.ReactElement[] = []
  const parts = text.split(/```/)
  parts.forEach((part, idx) => {
    if (idx % 2 === 1) {
      const [maybeLang, ...rest] = part.split('\n')
      const code = rest.join('\n') || maybeLang
      blocks.push(
        <pre key={`code-${idx}`} style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8, padding: '10px 12px', overflowX: 'auto', fontSize: 12.5, margin: '8px 0' }}>
          <code>{code}</code>
        </pre>,
      )
      return
    }
    // 表格（简化：连续 | 行）
    const lines = part.split('\n')
    const tableLines = lines.filter((l) => l.trim().startsWith('|') && l.trim().endsWith('|'))
    if (tableLines.length >= 2) {
      const parse = (l: string) => l.trim().slice(1, -1).split('|').map((c) => c.trim())
      const head = parse(tableLines[0])
      const body = tableLines.slice(1).filter((l) => !/^\|[\s:|-]+\|$/.test(l.trim())).map(parse)
      blocks.push(
        <div key={`tbl-${idx}`} className="table-container" style={{ margin: '8px 0', maxHeight: 260 }}>
          <table className="data-table">
            <thead>
              <tr>
                {head.map((h, i) => (
                  <th key={i}>{inline(h)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {body.map((row, ri) => (
                <tr key={ri}>
                  {row.map((c, ci) => (
                    <td key={ci}>{inline(c)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      )
      const rest = lines.filter((l) => !tableLines.includes(l)).join('\n')
      if (rest.trim()) blocks.push(<p key={`txt-${idx}`} style={{ margin: '6px 0', whiteSpace: 'pre-wrap' }}>{inline(rest)}</p>)
      return
    }
    if (part.trim()) blocks.push(<p key={`txt-${idx}`} style={{ margin: '6px 0', whiteSpace: 'pre-wrap' }}>{inline(part)}</p>)
  })
  return <>{blocks}</>
}

function inline(text: string): React.ReactElement {
  const html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/`([^`]+)`/g, '<code style="background:var(--surface-2);padding:1px 5px;border-radius:4px;font-size:0.92em">$1</code>')
  return <span dangerouslySetInnerHTML={{ __html: html }} />
}

export default function AiWorkbenchPage() {
  const [status, setStatus] = useState<AiStatus | null>(null)
  const [allowActions, setAllowActions] = useState(() => localStorage.getItem('aiAllowActions') === '1')
  const [sessions, setSessions] = useState<AiSession[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [items, setItems] = useState<ChatItem[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [streamText, setStreamText] = useState('')
  const [errorHint, setErrorHint] = useState<string | null>(null)
  const abortRef = useRef<((reason?: string) => void) | null>(null)
  const chatEndRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    localStorage.setItem('aiAllowActions', allowActions ? '1' : '0')
  }, [allowActions])

  const refreshMeta = () => {
    fetchAiStatus().then(setStatus)
    fetchAiSessions().then(setSessions)
  }
  useEffect(refreshMeta, [])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [items, streamText])

  const openSession = async (id: string) => {
    setSessionId(id)
    setErrorHint(null)
    setStreamText('')
    try {
      const msgs: AiMessage[] = await fetchAiMessages(id)
      const chat: ChatItem[] = []
      let current: ChatItem | null = null
      for (const m of msgs) {
        if (m.role === 'user') {
          if (current) chat.push(current)
          current = { role: 'assistant', content: '', tools: [] }
          chat.push({ role: 'user', content: m.content })
        } else if (m.role === 'tool' && current) {
          current.tools = current.tools ?? []
          current.tools.push({
            callId: `h-${current.tools.length}`,
            name: m.tool_name ?? 'tool',
            args: m.tool_args ?? {},
            ok: m.tool_ok,
            result: m.tool_result,
            durationMs: m.duration_ms,
            running: false,
          })
        } else if (m.role === 'assistant') {
          if (!current) current = { role: 'assistant', content: '', tools: [] }
          current.content += (current.content ? '\n' : '') + m.content
        }
      }
      if (current) chat.push(current)
      setItems(chat)
    } catch {
      setItems([])
    }
  }

  const newChat = () => {
    setSessionId(null)
    setItems([])
    setStreamText('')
    setErrorHint(null)
  }

  const removeSession = async (id: string) => {
    try {
      await deleteAiSession(id)
      if (sessionId === id) newChat()
      refreshMeta()
    } catch {
      // 删除失败静默
    }
  }

  const send = (text?: string) => {
    const message = (text ?? input).trim()
    if (!message || streaming) return
    setInput('')
    setErrorHint(null)
    setItems((prev) => [...prev, { role: 'user', content: message }])
    setStreaming(true)
    setStreamText('')
    let assistant = ''
    const tools: ToolCallView[] = []

    const abort = streamAiChat(
      { session_id: sessionId, message, allow_actions: allowActions },
      {
        onSession: (id) => {
          if (!sessionId) setSessionId(id)
        },
        onToken: (content) => {
          assistant += content
          setStreamText(assistant)
        },
        onToolCall: (name, args, callId) => {
          tools.push({ callId, name, args, running: true })
          setStreamText(assistant)
        },
        onToolResult: (callId, ok, result, durationMs) => {
          const tool = tools.find((t) => t.callId === callId)
          if (tool) {
            tool.ok = ok
            tool.result = result
            tool.durationMs = durationMs
            tool.running = false
          }
        },
        onDone: () => {
          setItems((prev) => [...prev, { role: 'assistant', content: assistant, tools: [...tools] }])
          setStreamText('')
          setStreaming(false)
          refreshMeta()
        },
        onError: (msg) => {
          setErrorHint(msg)
          if (assistant.trim() || tools.length > 0) {
            setItems((prev) => [...prev, { role: 'assistant', content: assistant, tools: [...tools] }])
          }
          setStreamText('')
          setStreaming(false)
          refreshMeta()
        },
      },
    )
    abortRef.current = abort
  }

  const stop = () => {
    abortRef.current?.('user-stop')
    setStreaming(false)
    if (streamText.trim() || items.length >= 0) {
      setItems((prev) => [...prev, { role: 'assistant', content: streamText + '\n\n（已停止生成）' }])
      setStreamText('')
    }
  }

  const statusChips = useMemo(
    () => [
      { label: `模型 · ${status?.llm.configured ? (status.llm.model ?? '已配置') : '未配置'}`, ok: status?.llm.configured },
      { label: `Tushare · ${status?.tushare_token_configured ? '已配置' : '未配置'}`, ok: status?.tushare_token_configured },
      { label: `宽表 · ${status?.wide_table.exists ? (status.wide_table.wide_table_date ?? '存在') : '缺失'}`, ok: status?.wide_table.exists },
    ],
    [status],
  )

  return (
    <div className="row g-3">
      {/* 会话列表 */}
      <div className="col-lg-3">
        <div className="panel h-100">
          <div className="panel-head">
            <h6 className="panel-title">
              <span className="kicker" />
              会话
            </h6>
            <button type="button" className="btn btn-outline-primary btn-sm" onClick={newChat}>
              + 新对话
            </button>
          </div>
          <div className="panel-body d-flex flex-column gap-2" style={{ maxHeight: 620, overflowY: 'auto' }}>
            {sessions.map((s) => (
              <div
                key={s.id}
                className={`p-2 rounded d-flex align-items-center gap-2 ${sessionId === s.id ? 'side-link active' : ''}`}
                style={{ background: sessionId === s.id ? undefined : 'var(--surface-2)', border: '1px solid var(--border)', cursor: 'pointer' }}
                onClick={() => openSession(s.id)}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.title}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-faint)' }}>{formatDateTime(s.updated_at)}</div>
                </div>
                <button
                  type="button"
                  className="btn btn-outline-danger btn-sm"
                  onClick={(e) => {
                    e.stopPropagation()
                    removeSession(s.id)
                  }}
                >
                  ×
                </button>
              </div>
            ))}
            {sessions.length === 0 && <EmptyState icon="💬" text="暂无历史会话" />}
          </div>
        </div>
      </div>

      {/* 聊天区 */}
      <div className="col-lg-9">
        <div className="panel h-100">
          <div className="panel-head flex-wrap">
            <div className="d-flex gap-2 flex-wrap">
              {statusChips.map((c) => (
                <span key={c.label} className={`badge ${c.ok ? 'text-bg-success' : 'text-bg-warning'}`} style={{ fontSize: 11 }}>
                  {c.label}
                </span>
              ))}
            </div>
            <label className="d-flex align-items-center gap-2" style={{ fontSize: 12.5, cursor: 'pointer' }}>
              <input type="checkbox" className="form-check-input mt-0" checked={allowActions} onChange={(e) => setAllowActions(e.target.checked)} />
              操作模式（允许执行数据任务）
            </label>
          </div>
          <div className="panel-body d-flex flex-column" style={{ height: 560 }}>
            {errorHint && <div className="alert-note mb-2">⚠️ {errorHint}</div>}
            <div className="flex-grow-1" style={{ overflowY: 'auto', paddingRight: 4 }}>
              {items.length === 0 && !streaming && (
                <>
                  <EmptyState icon="🧠" text="向 AI 助手提问，支持查数据、更新数据、算因子等工具调用" />
                  <div className="d-flex gap-2 flex-wrap justify-content-center mt-2">
                    {QUICK_QUESTIONS.map((q) => (
                      <button key={q} type="button" className="chip" style={{ cursor: 'pointer' }} onClick={() => send(q)}>
                        {q}
                      </button>
                    ))}
                  </div>
                </>
              )}
              {items.map((item, i) => (
                <div key={i} className={`d-flex mb-3 ${item.role === 'user' ? 'justify-content-end' : 'justify-content-start'}`}>
                  <div
                    className="p-3 rounded"
                    style={{
                      maxWidth: '86%',
                      background: item.role === 'user' ? 'linear-gradient(135deg, var(--accent), var(--accent-2))' : 'var(--surface-2)',
                      color: item.role === 'user' ? '#fff' : 'var(--text)',
                      border: item.role === 'user' ? 'none' : '1px solid var(--border)',
                      fontSize: 13.5,
                    }}
                  >
                    {item.role === 'assistant' && (item.tools?.length ?? 0) > 0 && (
                      <div className="d-flex flex-column gap-1 mb-2">
                        {item.tools!.map((t) => (
                          <details key={t.callId} className="p-2 rounded" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
                            <summary style={{ fontSize: 12.5, cursor: 'pointer' }}>
                              🛠 {t.name}{' '}
                              {t.running ? <span className="badge text-bg-primary">执行中…</span> : t.ok ? <span className="badge text-bg-success">成功</span> : <span className="badge text-bg-danger">失败</span>}
                              {t.durationMs != null && <span style={{ color: 'var(--text-faint)' }}> · {t.durationMs}ms</span>}
                            </summary>
                            <pre style={{ fontSize: 11, maxHeight: 160, overflow: 'auto', whiteSpace: 'pre-wrap' }}>{JSON.stringify(t.args, null, 2)}</pre>
                            {t.result !== undefined && <pre style={{ fontSize: 11, maxHeight: 200, overflow: 'auto', whiteSpace: 'pre-wrap' }}>{JSON.stringify(t.result, null, 2)}</pre>}
                          </details>
                        ))}
                      </div>
                    )}
                    {renderMarkdown(item.content)}
                  </div>
                </div>
              ))}
              {streaming && (
                <div className="d-flex justify-content-start mb-3">
                  <div className="p-3 rounded" style={{ maxWidth: '86%', background: 'var(--surface-2)', border: '1px solid var(--border)', fontSize: 13.5 }}>
                    {(items[items.length - 1]?.role === 'user') && streamText === '' && items[items.length - 1] && null}
                    {streamText ? renderMarkdown(streamText) : <span className="blinking">▍思考中…</span>}
                    {streamText && <span className="blinking">▍</span>}
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>
            <div className="d-flex gap-2 mt-2">
              <textarea
                className="form-control"
                rows={2}
                placeholder="输入问题…（Ctrl/Cmd + Enter 发送）"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') send()
                }}
              />
              {streaming ? (
                <button type="button" className="btn btn-outline-danger" onClick={stop}>
                  ⏹ 停止
                </button>
              ) : (
                <button type="button" className="btn btn-primary" onClick={() => send()} disabled={!input.trim()}>
                  发送
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
