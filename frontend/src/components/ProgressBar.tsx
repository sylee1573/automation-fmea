export type StepStatus = 'pending' | 'running' | 'completed' | 'warning' | 'error' | 'skipped'

export interface ProgressStep {
  key: string
  label: string
  status: StepStatus
  detail?: string
}

interface Props {
  steps: ProgressStep[]
}

const STEP_ICON: Record<StepStatus, string> = {
  pending: '○',
  running: '◎',
  completed: '✓',
  warning: '⚠',
  error: '✗',
  skipped: '—',
}

export default function ProgressBar({ steps }: Props) {
  const visible = steps.filter(s => s.status !== 'skipped')
  if (!visible.length) return null

  return (
    <div className="progress-container">
      <div className="progress-title">생성 진행상황</div>
      <div className="progress-steps">
        {visible.map(step => (
          <div key={step.key} className="progress-step">
            <div className={`step-icon ${step.status}`}>
              {STEP_ICON[step.status]}
            </div>
            <div className="step-info">
              <div className="step-name">{step.label}</div>
              {step.detail && <div className="step-detail">{step.detail}</div>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── 초기 스텝 생성 헬퍼 ──────────────────────────────────────────────────────
export function buildInitialSteps(options: {
  pfmea: boolean
  cp: boolean
  work_standard: boolean
  inspection: boolean
}): ProgressStep[] {
  return [
    {
      key: 'FMEA',
      label: 'PFMEA 생성',
      status: options.pfmea ? 'pending' : 'skipped',
    },
    {
      key: 'CP',
      label: '관리계획서 (CP) 생성',
      status: options.cp ? 'pending' : 'skipped',
    },
    {
      key: '작업표준서',
      label: '작업표준서 생성',
      status: options.work_standard ? 'pending' : 'skipped',
    },
    {
      key: '자주검사',
      label: '자주검사항목 생성',
      status: options.inspection ? 'pending' : 'skipped',
    },
    {
      key: '정합성',
      label: '정합성 검증',
      status: 'pending',
    },
    {
      key: 'Excel',
      label: 'Excel 파일 생성',
      status: 'pending',
    },
  ]
}
