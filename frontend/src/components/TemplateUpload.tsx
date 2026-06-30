import { useEffect, useRef, useState } from 'react'
import { api, type TemplateInfo } from '../api/client'

interface Props {
  customer: string
  onCustomerChange: (c: string) => void
}

/**
 * 고객사 출력양식 등록 — 고객사 FMEA 양식(.xlsx/.xlsm)을 올리면
 * 컬럼 매핑을 자동 인식해 등록한다. 같은 고객사로 생성하면 FMEA가 그 양식으로 출력된다.
 */
export default function TemplateUpload({ customer, onCustomerChange }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File>()
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [templates, setTemplates] = useState<TemplateInfo[]>([])

  const refresh = () => api.listTemplates().then(r => setTemplates(r.templates)).catch(() => {})
  useEffect(() => { refresh() }, [])

  const handleUpload = async () => {
    setError(''); setMessage('')
    if (!customer.trim()) { setError('고객사명을 먼저 입력해주세요.'); return }
    if (!file) { setError('양식 파일을 선택해주세요.'); return }
    setBusy(true)
    try {
      const res = await api.uploadTemplate(file, customer.trim())
      setMessage(res.message)
      setFile(undefined)
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : '양식 등록 실패')
    } finally {
      setBusy(false)
    }
  }

  const handleDelete = async (c: string) => {
    try { await api.deleteTemplate(c); await refresh() } catch { /* ignore */ }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div className="input-group" style={{ marginBottom: 0 }}>
        <label className="input-label">고객사명</label>
        <input
          className="input"
          value={customer}
          onChange={e => onCustomerChange(e.target.value)}
          placeholder="예) 현대자동차 / MTK"
        />
      </div>

      <div
        className={`upload-zone ${file ? 'has-file' : ''}`}
        onClick={() => inputRef.current?.click()}
      >
        <div className="upload-icon">{file ? '✅' : '📋'}</div>
        <div className="upload-label">{file ? file.name : '고객사 FMEA 양식 업로드 (선택)'}</div>
        {!file && <div className="upload-hint">이 양식 그대로 FMEA 출력 (.xlsx/.xlsm)</div>}
        <input
          ref={inputRef}
          type="file"
          accept=".xlsx,.xlsm"
          style={{ display: 'none' }}
          onChange={e => { const f = e.target.files?.[0]; if (f) { setFile(f); setError(''); setMessage('') } }}
        />
      </div>

      {file && (
        <button className="btn btn-primary btn-sm" onClick={handleUpload} disabled={busy}>
          {busy ? '분석 중...' : '양식 등록'}
        </button>
      )}

      {message && (
        <div style={{ padding: '8px 10px', background: '#ecfdf5', borderRadius: 6, fontSize: 11, color: '#047857' }}>
          ✅ {message}
        </div>
      )}
      {error && (
        <div style={{ padding: '8px 10px', background: '#fef2f2', borderRadius: 6, fontSize: 11, color: '#b91c1c' }}>
          {error}
        </div>
      )}

      {templates.length > 0 && (
        <div style={{ marginTop: 4 }}>
          <div style={{ fontSize: 11, color: '#64748b', marginBottom: 4 }}>등록된 양식</div>
          {templates.map(t => (
            <div
              key={t.profile_file}
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                       padding: '6px 8px', background: '#f8fafc', borderRadius: 6, fontSize: 11, marginBottom: 4 }}
            >
              <span style={{ color: '#334155' }}>
                📋 <b>{t.customer}</b>
                <span style={{ color: '#94a3b8' }}> · {t.detected_fields.length}개 컬럼</span>
              </span>
              <button
                onClick={() => handleDelete(t.customer)}
                style={{ border: 'none', background: 'none', color: '#ef4444', cursor: 'pointer', fontSize: 11 }}
                title="삭제"
              >
                삭제
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
