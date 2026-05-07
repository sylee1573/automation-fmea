import { useState } from 'react'
import { api } from '../api/client'

interface Props {
  onConfigured: () => void
}

export default function ApiKeySetup({ onConfigured }: Props) {
  const [key, setKey] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSave = async () => {
    if (!key.trim()) {
      setError('API 키를 입력해주세요')
      return
    }
    if (!key.startsWith('sk-ant-')) {
      setError('올바른 Anthropic API 키를 입력해주세요 (sk-ant- 로 시작)')
      return
    }
    setLoading(true)
    setError('')
    try {
      const result = await api.saveApiKey(key.trim())
      if (result.ok) {
        onConfigured()
      } else {
        setError('저장 실패. 다시 시도해주세요.')
      }
    } catch {
      setError('서버 연결 오류. 백엔드가 실행 중인지 확인해주세요.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="setup-overlay">
      <div className="setup-modal">
        <div className="setup-logo">⚙️</div>
        <h1 className="setup-title">표준류 자동생성 시스템</h1>
        <p className="setup-desc">
          시작하기 전에 Anthropic API 키를 입력해주세요.<br />
          API 키는 이 기기에만 암호화되어 저장됩니다.
        </p>

        <div style={{ marginBottom: 16 }}>
          <p className="setup-step">Anthropic 계정 생성: console.anthropic.com</p>
          <p className="setup-step">API Keys 메뉴에서 새 키 생성</p>
          <p className="setup-step">아래에 붙여넣기 (sk-ant-api03-... 형식)</p>
        </div>

        <div className="input-group">
          <label className="input-label">Anthropic API 키</label>
          <input
            type="password"
            className="input"
            placeholder="sk-ant-api03-..."
            value={key}
            onChange={e => setKey(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleSave() }}
            autoFocus
          />
          {error && (
            <p style={{ color: '#dc2626', fontSize: 12, marginTop: 4 }}>{error}</p>
          )}
        </div>

        <button
          className="btn btn-primary"
          style={{ width: '100%', padding: '10px' }}
          onClick={handleSave}
          disabled={loading}
        >
          {loading ? '저장 중...' : '저장하고 시작하기'}
        </button>

        <div className="setup-notice">
          ⚠️ <strong>법인 Anthropic API 계정</strong>을 사용해야 합니다.
          개인 계정(Free/Pro/Max) 키는 데이터 보호 정책이 다릅니다.
          고객사 CSR에 외부 AI 시스템 사용 제한이 있을 수 있으므로
          사전에 확인 후 사용하세요.
        </div>
      </div>
    </div>
  )
}
