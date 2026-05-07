import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'

interface Message {
  role: 'user' | 'assistant' | 'system'
  content: string
}

interface Props {
  sessionId: string
}

const QUICK_PROMPTS = [
  '업로드된 도면을 요약해줘',
  '전체 4종 생성해줘',
  'AP=H 항목 목록을 보여줘',
  'FMEA와 CP를 다시 설명해줘',
]

export default function ChatInterface({ sessionId }: Props) {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'system',
      content: '안녕하세요! 표준류 자동생성 시스템입니다. 도면(PDF)과 공정검토서(Excel)를 업로드하고 생성 버튼을 눌러주세요. 궁금한 점은 여기서 질문하세요.',
    },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const send = async (text: string) => {
    const msg = text.trim()
    if (!msg || loading) return

    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: msg }])
    setLoading(true)

    let assistantMsg = ''
    setMessages(prev => [...prev, { role: 'assistant', content: '...' }])

    await api.chatStream(
      msg,
      sessionId,
      chunk => {
        assistantMsg += chunk
        setMessages(prev => {
          const updated = [...prev]
          updated[updated.length - 1] = { role: 'assistant', content: assistantMsg }
          return updated
        })
      },
      () => {
        setLoading(false)
      },
      errMsg => {
        setMessages(prev => {
          const updated = [...prev]
          updated[updated.length - 1] = { role: 'system', content: `오류: ${errMsg}` }
          return updated
        })
        setLoading(false)
      },
    )
  }

  return (
    <div className="chat-panel">
      <div className="chat-messages">
        {messages.map((m, i) => (
          <div key={i} className={`chat-message ${m.role}`}>
            {m.content}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* 빠른 입력 */}
      <div style={{ padding: '6px 12px', display: 'flex', gap: 6, flexWrap: 'wrap', borderTop: '1px solid #f0f2f5' }}>
        {QUICK_PROMPTS.map(p => (
          <button
            key={p}
            className="btn btn-outline btn-sm"
            onClick={() => send(p)}
            disabled={loading}
            style={{ fontSize: 11 }}
          >
            {p}
          </button>
        ))}
      </div>

      <div className="chat-input-area">
        <textarea
          className="chat-input"
          placeholder="메시지를 입력하세요... (Shift+Enter 줄바꿈, Enter 전송)"
          value={input}
          rows={2}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              send(input)
            }
          }}
          disabled={loading}
        />
        <button
          className="btn btn-primary"
          onClick={() => send(input)}
          disabled={loading || !input.trim()}
          style={{ height: 52 }}
        >
          전송
        </button>
      </div>
    </div>
  )
}
