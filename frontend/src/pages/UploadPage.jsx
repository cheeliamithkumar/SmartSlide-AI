import { CloudUpload, FileText, ShieldCheck, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Stepper from '../components/Stepper'
import { Alert, Button } from '../components/ui'
import { api, errorMessage } from '../services/api'
import { formatBytes } from '../utils/format'

export default function UploadPage() {
  const navigate = useNavigate()
  const inputRef = useRef(null)
  const [file, setFile] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [progress, setProgress] = useState(0)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState(null)
  const [limits, setLimits] = useState({ max_upload_mb: 25, max_pages: 300 })
  const [directUpload, setDirectUpload] = useState(false)

  useEffect(() => {
    api
      .health()
      .then((h) => {
        if (h.limits) setLimits(h.limits)
        setDirectUpload(Boolean(h.direct_upload))
      })
      .catch(() => {})
  }, [])

  const choose = (f) => {
    setError(null)
    if (!f) return
    if (!/\.pdf$/i.test(f.name) && f.type !== 'application/pdf') {
      setError('Please choose a PDF file.')
      return
    }
    if (f.size > limits.max_upload_mb * 1024 * 1024) {
      setError(`This file is ${formatBytes(f.size)}. The maximum size is ${limits.max_upload_mb} MB.`)
      return
    }
    if (f.size === 0) {
      setError('This file is empty.')
      return
    }
    setFile(f)
  }

  const onDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    choose(e.dataTransfer.files?.[0])
  }

  const upload = async () => {
    if (!file) return
    setUploading(true)
    setError(null)
    setProgress(0)
    try {
      const doc = await api.uploadDocument(file, setProgress, { directUpload })
      navigate(`/configure/${doc.id}`)
    } catch (err) {
      setError(errorMessage(err, 'Upload failed. Please try again.'))
      setUploading(false)
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
      <Stepper current={0} />
      <div className="text-center">
        <h1 className="text-3xl font-extrabold text-slate-900 sm:text-4xl dark:text-white">Upload your PDF</h1>
        <p className="mt-3 text-slate-600 dark:text-slate-400">Lecture notes, textbook chapters, study guides or research papers.</p>
      </div>

      <div
        role="button"
        tabIndex={0}
        aria-label="Upload PDF. Drag and drop or press Enter to browse."
        onClick={() => !uploading && inputRef.current?.click()}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && !uploading && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`group mt-10 flex cursor-pointer flex-col items-center justify-center rounded-3xl border-2 border-dashed px-6 py-16 text-center transition-all duration-200 ${
          dragging
            ? 'scale-[1.01] border-brand-500 bg-brand-50 dark:bg-brand-950/40'
            : 'border-slate-300 bg-white hover:border-brand-400 hover:bg-brand-50/40 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-brand-600 dark:hover:bg-brand-950/20'
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          className="hidden"
          onChange={(e) => {
            choose(e.target.files?.[0])
            e.target.value = ''
          }}
        />
        <span className={`flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500 to-violet-600 text-white shadow-lg shadow-brand-500/30 transition-transform ${dragging ? 'scale-110' : 'group-hover:scale-105'}`}>
          <CloudUpload className="h-8 w-8" />
        </span>
        <p className="mt-5 text-lg font-semibold text-slate-900 dark:text-white">
          {dragging ? 'Drop your PDF here' : 'Drag & drop your PDF here'}
        </p>
        <p className="mt-1 text-sm text-slate-500">
          or <span className="font-semibold text-brand-600 dark:text-brand-400">browse files</span>
        </p>
        <p className="mt-4 text-xs text-slate-400">
          PDF only • up to {limits.max_upload_mb} MB • up to {limits.max_pages} pages
        </p>
      </div>

      {error && (
        <Alert type="error" className="mt-6" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {file && (
        <div className="card mt-6 flex items-center gap-4 p-4 animate-fade-up">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-red-50 text-red-600 dark:bg-red-950/50 dark:text-red-400">
            <FileText className="h-6 w-6" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate font-semibold text-slate-900 dark:text-white">{file.name}</p>
            <p className="text-sm text-slate-500">{formatBytes(file.size)}</p>
            {uploading && (
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                <div className="h-full rounded-full bg-brand-600 transition-all" style={{ width: `${progress}%` }} />
              </div>
            )}
          </div>
          {!uploading && (
            <button onClick={() => setFile(null)} className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800" aria-label="Remove file">
              <X className="h-5 w-5" />
            </button>
          )}
        </div>
      )}

      <div className="mt-8 flex flex-col items-center gap-4">
        <Button size="lg" onClick={upload} disabled={!file} loading={uploading} className="w-full sm:w-auto">
          {uploading ? (progress < 100 ? `Uploading… ${progress}%` : 'Analyzing PDF…') : 'Upload & continue'}
        </Button>
        <p className="flex items-center gap-1.5 text-xs text-slate-500">
          <ShieldCheck className="h-4 w-4 text-emerald-500" /> Your file stays private and is deleted automatically.
        </p>
      </div>
    </div>
  )
}
