interface Options {
  pfmea: boolean
  cp: boolean
  work_standard: boolean
  inspection: boolean
}

interface Props {
  options: Options
  onChange: (options: Options) => void
  disabled?: boolean
}

const DOCS = [
  { key: 'pfmea', label: 'PFMEA', dep: null },
  { key: 'cp', label: '관리계획서 (CP)', dep: 'pfmea' },
  { key: 'work_standard', label: '작업표준서', dep: 'cp' },
  { key: 'inspection', label: '자주검사항목', dep: 'cp' },
] as const

// 선택 조합별 예상 시간·비용
const ESTIMATES: Record<string, { time: string; cost: string }> = {
  'pfmea': { time: '~35초', cost: '$0.06' },
  'pfmea,cp': { time: '~53초', cost: '$0.08' },
  'pfmea,cp,work_standard': { time: '~68초', cost: '$0.10' },
  'pfmea,cp,inspection': { time: '~68초', cost: '$0.10' },
  'pfmea,cp,work_standard,inspection': { time: '~80초', cost: '$0.12' },
}

function getEstimate(opts: Options) {
  const selected = Object.entries(opts)
    .filter(([, v]) => v)
    .map(([k]) => k)
    .sort()
    .join(',')
  return ESTIMATES[selected] || { time: '~80초', cost: '$0.12' }
}

export default function GenerationOptions({ options, onChange, disabled }: Props) {
  const toggle = (key: keyof Options) => {
    if (disabled) return
    const next = { ...options, [key]: !options[key] }

    // 의존성 자동 보정
    if (next.cp && !next.pfmea) next.pfmea = true
    if (next.work_standard && !next.cp) { next.cp = true; next.pfmea = true }
    if (next.inspection && !next.cp) { next.cp = true; next.pfmea = true }
    // 비활성화 전파
    if (!next.pfmea) { next.cp = false; next.work_standard = false; next.inspection = false }
    if (!next.cp) { next.work_standard = false; next.inspection = false }

    onChange(next)
  }

  const estimate = getEstimate(options)
  const selectedCount = Object.values(options).filter(Boolean).length

  return (
    <div>
      <div className="options-grid">
        {DOCS.map(doc => {
          const checked = options[doc.key]
          return (
            <div
              key={doc.key}
              className={`option-item ${checked ? 'checked' : ''} ${disabled ? 'disabled' : ''}`}
              onClick={() => toggle(doc.key)}
            >
              <input
                type="checkbox"
                className="option-checkbox"
                checked={checked}
                readOnly
              />
              <div>
                <div className="option-label">{doc.label}</div>
                {doc.dep && (
                  <div className="option-dep">{doc.dep === 'pfmea' ? 'PFMEA 필요' : 'CP 필요'}</div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      <div className="cost-estimate">
        <span>
          {selectedCount}종 선택 · 예상 {estimate.time}
        </span>
        <span style={{ color: '#e07000', fontWeight: 600 }}>
          ≈ {estimate.cost}
        </span>
      </div>
    </div>
  )
}
