import { useEffect, useState } from 'react'
import { api, type ProgressEvent } from './api/client'
import ApiKeySetup from './components/ApiKeySetup'
import ChatInterface from './components/ChatInterface'
import FileUpload from './components/FileUpload'
import GenerationOptions from './components/GenerationOptions'
import ProgressBar, { buildInitialSteps, type ProgressStep } from './components/ProgressBar'

type AppState = 'idle' | 'uploading' | 'ready' | 'generating' | 'done' | 'error'

interface GenOptions {
  pfmea: boolean
  cp: boolean
  work_standard: boolean
  inspection: boolean
}

export default function App() {
  const [configured, setConfigured] = useState<boolean | null>(null)
  const [showApiSetup, setShowApiSetup] = useState(false)

  const [appState, setAppState] = useState<AppState>('idle')
  const [sessionId, setSessionId] = useState('')
  const [summary, setSummary] = useState('')
  const [partName, setPartName] = useState('')
  const [partNumber, setPartNumber] = useState('')
  const [customer, setCustomer] = useState('')

  const [options, setOptions] = useState<GenOptions>({
    pfmea: true, cp: true, work_standard: true, inspection: true,
  })

  const [steps, setSteps] = useState<ProgressStep[]>([])
  const [downloadFiles, setDownloadFiles] = useState<string[]>([])
  const [issues, setIssues] = useState<string[]>([])
  const [errorMsg, setErrorMsg] = useState('')

  // ── 초기화 ───────────────────────────────────────────────────
  useEffect(() => {
    api.getSetupStatus().then(s => setConfigured(s.configured)).catch(() => setConfigured(false))
  }, [])

  if (configured === null) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', color: '#64748b' }}>
        로딩 중...
      </div>
    )
  }

  // ── 파일 업로드 ──────────────────────────────────────────────
  const handleFiles = async (drawing?: File, processSheet?: File) => {
    if (!drawing && !processSheet) return
    setAppState('uploading')
    setSummary('')
    setSessionId('')

    try {
      const result = await api.uploadFiles(drawing, processSheet)
      setSessionId(result.session_id)
      setSummary(result.summary)
      setPartName(result.part_name || '')
      setPartNumber(result.part_number || '')
      setAppState('ready')
    } catch {
      setErrorMsg('파일 업로드 실패. 서버 연결을 확인해주세요.')
      setAppState('error')
    }
  }

  // ── 생성 시작 ────────────────────────────────────────────────
  const handleGenerate = async () => {
    if (!sessionId) {
      setErrorMsg('먼저 파일을 업로드해주세요')
      return
    }

    // 부품 정보 업데이트
    if (partName || partNumber || customer) {
      await api.updateSession(sessionId, { part_name: partName, part_number: partNumber, customer })
    }

    let taskId: string
    try {
      const res = await api.startGeneration(sessionId, options)
      taskId = res.task_id
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : '생성 요청 실패')
      return
    }

    setAppState('generating')
    setSteps(buildInitialSteps(options))
    setDownloadFiles([])
    setIssues([])
    setErrorMsg('')

    const es = api.streamProgress(taskId)

    es.onmessage = (e: MessageEvent) => {
      try {
        const event: ProgressEvent = JSON.parse(e.data)
        handleProgressEvent(event, es)
      } catch { /* skip */ }
    }

    es.onerror = () => {
      setErrorMsg('스트리밍 연결 오류')
      setAppState('error')
      es.close()
    }
  }

  const handleProgressEvent = (event: ProgressEvent, es: EventSource) => {
    if (event.type === 'progress') {
      const { step, status } = event
      setSteps(prev => prev.map(s => {
        if (s.key !== step) return s
        let detail = ''
        if (status === 'completed' && event.rows !== undefined) {
          detail = `${event.rows}개 항목 생성됨`
          if (event.h_count) detail += ` (H: ${event.h_count}건)`
        } else if (status === 'retry') {
          detail = `불일치 ${event.issue_count}건 재시도 중...`
        } else if (status === 'warning') {
          detail = `${event.issue_count}건 불일치 (담당자 확인 필요)`
        } else if (status === 'started') {
          detail = '생성 중...'
        }
        return {
          ...s,
          status: status === 'completed' ? 'completed'
            : status === 'started' || status === 'retry' ? 'running'
            : status === 'warning' ? 'warning'
            : s.status,
          detail,
        }
      }))
    } else if (event.type === 'done') {
      setDownloadFiles(event.files ?? [])
      setIssues(event.issues ?? [])
      setAppState('done')
      es.close()
    } else if (event.type === 'error') {
      setErrorMsg(event.message ?? '알 수 없는 오류')
      setAppState('error')
      es.close()
    }
  }

  const handleReset = () => {
    setAppState('idle')
    setSessionId('')
    setSummary('')
    setPartName('')
    setPartNumber('')
    setCustomer('')
    setSteps([])
    setDownloadFiles([])
    setIssues([])
    setErrorMsg('')
  }

  // ── 렌더 ─────────────────────��──────────────────────────────
  return (
    <div className="app">
      {/* API 키 설정 모달 */}
      {(!configured || showApiSetup) && (
        <ApiKeySetup onConfigured={() => { setConfigured(true); setShowApiSetup(false) }} />
      )}

      {/* 헤더 */}
      <header className="header">
        <div>
          <div className="header-title">표준류 자동생성 시스템</div>
          <div className="header-subtitle">FMEA · CP · 작업표준서 · 자주검사항목</div>
        </div>
        <div className="header-actions">
          <span
            className={`api-badge ${configured ? 'configured' : ''}`}
            onClick={() => setShowApiSetup(true)}
            title="API 키 설정"
          >
            {configured ? '🔑 API 연결됨' : '⚠️ API 키 설정'}
          </span>
        </div>
      </header>

      {/* 메인 레이아웃 */}
      <div className="main-layout">
        {/* ── 왼쪽 패널: 설정 ── */}
        <aside className="left-panel">
          <div style={{ flex: 1, overflowY: 'auto' }}>

            {/* 파일 업로드 */}
            <div className="panel-section">
              <div className="panel-section-title">파일 업로드</div>
              <FileUpload onFilesChange={handleFiles} />
              {appState === 'uploading' && (
                <p style={{ fontSize: 12, color: '#2563eb', marginTop: 8 }}>파일 분석 중...</p>
              )}
              {summary && (
                <div style={{ marginTop: 8, padding: '8px 10px', background: '#f8fafc', borderRadius: 6, fontSize: 12, color: '#475569', whiteSpace: 'pre-line' }}>
                  {summary}
                </div>
              )}
            </div>

            {/* 부품 정보 */}
            {(appState === 'ready' || appState === 'done') && (
              <div className="panel-section">
                <div className="panel-section-title">부품 정보</div>
                <div className="part-info-grid">
                  <div className="input-group" style={{ marginBottom: 0 }}>
                    <label className="input-label">부품명</label>
                    <input className="input" value={partName} onChange={e => setPartName(e.target.value)} placeholder="예) 프런트 브래킷" />
                  </div>
                  <div className="input-group" style={{ marginBottom: 0 }}>
                    <label className="input-label">부품번호</label>
                    <input className="input" value={partNumber} onChange={e => setPartNumber(e.target.value)} placeholder="예) FSB-001" />
                  </div>
                </div>
                <div className="input-group" style={{ marginTop: 8, marginBottom: 0 }}>
                  <label className="input-label">고객사</label>
                  <input className="input" value={customer} onChange={e => setCustomer(e.target.value)} placeholder="예) 현대자동차" />
                </div>
              </div>
            )}

            {/* 생성 옵션 */}
            <div className="panel-section">
              <div className="panel-section-title">생성할 문서</div>
              <GenerationOptions
                options={options}
                onChange={setOptions}
                disabled={appState === 'generating'}
              />
            </div>
          </div>

          {/* 생성 버튼 */}
          <div style={{ padding: 16, borderTop: '1px solid #f0f2f5' }}>
            {appState === 'done' ? (
              <button className="btn btn-outline" style={{ width: '100%' }} onClick={handleReset}>
                새 문서 생성
              </button>
            ) : (
              <button
                className="btn btn-generate"
                onClick={handleGenerate}
                disabled={appState === 'generating' || appState === 'uploading' || !configured}
              >
                {appState === 'generating' ? '생성 중...' : '표준류 생성하기'}
              </button>
            )}
            {errorMsg && (
              <p style={{ color: '#dc2626', fontSize: 12, marginTop: 8, textAlign: 'center' }}>
                {errorMsg}
              </p>
            )}
          </div>
        </aside>

        {/* ── 오른쪽 패널: 진행상황 + 챗봇 ── */}
        <main className="right-panel">
          {/* 진행상황 */}
          {(appState === 'generating' || appState === 'done') && steps.length > 0 && (
            <div style={{ padding: 16, borderBottom: '1px solid #e2e8f0' }}>
              <ProgressBar steps={steps} />

              {/* 다운로드 */}
              {appState === 'done' && downloadFiles.length > 0 && (
                <div className="download-panel" style={{ marginTop: 12 }}>
                  <div className="download-title">✅ 생성 완료 — Excel 다운로드</div>
                  <div className="download-list">
                    {downloadFiles.map(filename => (
                      <div key={filename} className="download-item">
                        <span className="download-filename">📥 {filename}</span>
                        <a
                          href={api.downloadUrl(sessionId, filename)}
                          download={filename}
                          className="btn btn-primary btn-sm"
                        >
                          다운로드
                        </a>
                      </div>
                    ))}
                  </div>
                  {issues.length > 0 && (
                    <div className="issue-list">
                      <div className="issue-title">⚠️ 정합성 미해결 항목 (담당자 확인 필요)</div>
                      {issues.map((issue, i) => (
                        <div key={i} className="issue-item">• {issue}</div>
                      ))}
                    </div>
                  )}
                  <div style={{ marginTop: 10, padding: '8px 10px', background: '#eff6ff', borderRadius: 6, fontSize: 11, color: '#1e40af' }}>
                    ℹ️ 이 문서는 AI가 생성한 초안입니다. 반드시 담당 엔지니어가 검토·승인 후 사용하십시오.
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 챗봇 */}
          <div style={{ flex: 1, minHeight: 0 }}>
            <ChatInterface sessionId={sessionId} />
          </div>
        </main>
      </div>
    </div>
  )
}
