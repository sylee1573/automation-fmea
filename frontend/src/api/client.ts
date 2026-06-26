const BASE = ''  // Vite proxy handles /setup, /upload, etc.

export interface SetupStatus {
  configured: boolean
}

export interface UploadResponse {
  session_id: string
  summary: string
  part_name: string
  part_number: string
}

export interface GenerateResponse {
  task_id: string
}

export interface ProgressEvent {
  type: 'progress' | 'done' | 'error' | 'heartbeat'
  step?: string
  status?: string
  rows?: number
  h_count?: number
  files?: string[]
  issues?: string[]
  session_id?: string
  message?: string
  [key: string]: unknown
}

export const api = {
  // ── 설정 ───────────────────────────────────────────────────
  getSetupStatus: (): Promise<SetupStatus> =>
    fetch(`${BASE}/setup/status`).then(r => r.json()),

  saveApiKey: (key: string): Promise<{ ok: boolean }> => {
    const form = new FormData()
    form.append('api_key', key)
    return fetch(`${BASE}/setup/apikey`, { method: 'POST', body: form }).then(r => r.json())
  },

  deleteApiKey: (): Promise<{ ok: boolean }> =>
    fetch(`${BASE}/setup/apikey`, { method: 'DELETE' }).then(r => r.json()),

  // ── 업로드 ─────────────────────────────────────────────────
  uploadFiles: (drawing?: File, processSheet?: File, pfd?: File): Promise<UploadResponse> => {
    const form = new FormData()
    if (drawing) form.append('drawing', drawing)
    if (pfd) form.append('pfd', pfd)
    if (processSheet) form.append('process_sheet', processSheet)
    return fetch(`${BASE}/upload`, { method: 'POST', body: form }).then(r => r.json())
  },

  updateSession: (
    sessionId: string,
    fields: { part_name?: string; part_number?: string; customer?: string; process_type?: string },
  ): Promise<{ ok: boolean }> => {
    const form = new FormData()
    form.append('session_id', sessionId)
    Object.entries(fields).forEach(([k, v]) => { if (v) form.append(k, v) })
    return fetch(`${BASE}/session/update`, { method: 'POST', body: form }).then(r => r.json())
  },

  // ── 생성 ───────────────────────────────────────────────────
  startGeneration: (
    sessionId: string,
    options: { pfmea: boolean; cp: boolean; work_standard: boolean; inspection: boolean },
  ): Promise<GenerateResponse> => {
    const form = new FormData()
    form.append('session_id', sessionId)
    form.append('pfmea', String(options.pfmea))
    form.append('cp', String(options.cp))
    form.append('work_standard', String(options.work_standard))
    form.append('inspection', String(options.inspection))
    return fetch(`${BASE}/generate`, { method: 'POST', body: form }).then(r => {
      if (!r.ok) return r.json().then(e => { throw new Error(e.detail || '생성 요청 실패') })
      return r.json()
    })
  },

  streamProgress: (taskId: string): EventSource =>
    new EventSource(`${BASE}/stream/${taskId}`),

  downloadUrl: (sessionId: string, filename: string): string =>
    `${BASE}/download/${sessionId}/${filename}`,

  // ── 챗봇 ───────────────────────────────────────────────────
  chat: (message: string, sessionId: string): EventSource => {
    const form = new FormData()
    form.append('message', message)
    form.append('session_id', sessionId)
    // EventSource doesn't support POST; use fetch + stream instead
    // Returns an abort controller so caller can cancel
    throw new Error('use chatStream instead')
  },

  chatStream: async (
    message: string,
    sessionId: string,
    onChunk: (text: string) => void,
    onDone: () => void,
    onError: (msg: string) => void,
  ): Promise<void> => {
    const form = new FormData()
    form.append('message', message)
    form.append('session_id', sessionId)

    let resp: Response
    try {
      resp = await fetch(`${BASE}/chat`, { method: 'POST', body: form })
    } catch {
      onError('서버에 연결할 수 없습니다')
      return
    }

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: '알 수 없는 오류' }))
      onError(err.detail || '챗봇 오류')
      return
    }

    const reader = resp.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const event = JSON.parse(line.slice(6))
          if (event.type === 'text') onChunk(event.content)
          else if (event.type === 'done') onDone()
        } catch { /* skip malformed */ }
      }
    }
    onDone()
  },
}
