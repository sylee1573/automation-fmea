import { useRef, useState } from 'react'

interface Props {
  label: string
  accept: string
  hint: string
  icon: string
  onFile: (file: File) => void
  file?: File
}

function DropZone({ label, accept, hint, icon, onFile, file }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const f = e.dataTransfer.files[0]
    if (f) onFile(f)
  }

  return (
    <div
      className={`upload-zone ${dragOver ? 'drag-over' : ''} ${file ? 'has-file' : ''}`}
      onClick={() => inputRef.current?.click()}
      onDragOver={e => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
    >
      <div className="upload-icon">{file ? '✅' : icon}</div>
      <div className="upload-label">{file ? file.name : label}</div>
      {!file && <div className="upload-hint">{hint}</div>}
      {file && (
        <div className="upload-hint" style={{ color: '#15803d' }}>
          {(file.size / 1024).toFixed(1)} KB
        </div>
      )}
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        style={{ display: 'none' }}
        onChange={e => { const f = e.target.files?.[0]; if (f) onFile(f) }}
      />
    </div>
  )
}

interface FileUploadProps {
  onFilesChange: (drawing?: File, processSheet?: File, pfd?: File) => void
}

export default function FileUpload({ onFilesChange }: FileUploadProps) {
  const [drawing, setDrawing] = useState<File>()
  const [processSheet, setProcessSheet] = useState<File>()
  const [pfd, setPfd] = useState<File>()

  const handleDrawing = (f: File) => {
    setDrawing(f)
    onFilesChange(f, processSheet, pfd)
  }

  const handleProcessSheet = (f: File) => {
    setProcessSheet(f)
    onFilesChange(drawing, f, pfd)
  }

  const handlePfd = (f: File) => {
    setPfd(f)
    onFilesChange(drawing, processSheet, f)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <DropZone
        label="도면 PDF 업로드"
        accept=".pdf"
        hint="클릭하거나 드래그하여 업로드 (PDF)"
        icon="📄"
        onFile={handleDrawing}
        file={drawing}
      />
      <DropZone
        label="공정흐름도(PFD) 업로드 (선택)"
        accept=".xlsx,.xls"
        hint="PFMEA 공정 단계 자동 인식 (Excel)"
        icon="🔄"
        onFile={handlePfd}
        file={pfd}
      />
      <DropZone
        label="공정검토서 업로드 (선택)"
        accept=".xlsx,.xls"
        hint="클릭하거나 드래그하여 업로드 (Excel)"
        icon="📊"
        onFile={handleProcessSheet}
        file={processSheet}
      />
    </div>
  )
}
