import { BookOpenCheck, CheckCircle2, Download, ListChecks, PencilLine, Upload } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import Stepper from '../components/Stepper'
import { Alert, Button, PageLoader } from '../components/ui'
import { useTemplates } from '../hooks/useTemplates'
import { api, errorMessage } from '../services/api'

export default function DownloadPage() {
  const { jobId } = useParams()
  const { byId } = useTemplates()
  const [job, setJob] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(null)
  const [done, setDone] = useState({})

  useEffect(() => {
    api.getJob(jobId).then(setJob).catch((e) => setError(errorMessage(e, 'Presentation not found.')))
  }, [jobId])

  const download = async (p) => {
    setBusy(p.id)
    setError(null)
    try {
      await api.downloadPresentation(p.id)
      setDone((d) => ({ ...d, [p.id]: true }))
    } catch (e) {
      setError(errorMessage(e, 'Download failed.'))
    } finally {
      setBusy(null)
    }
  }

  if (!job && !error) return <PageLoader />

  return (
    <div className="mx-auto max-w-4xl px-4 py-12 sm:px-6">
      <Stepper current={4} />
      <div className="text-center">
        <span className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-400">
          <CheckCircle2 className="h-9 w-9" />
        </span>
        <h1 className="mt-5 text-3xl font-extrabold text-slate-900 sm:text-4xl dark:text-white">Your presentations are ready</h1>
        <p className="mt-3 text-slate-600 dark:text-slate-400">Download editable .pptx files that open in PowerPoint, Keynote and Google Slides.</p>
      </div>

      {error && <Alert type="error" className="mt-8">{error}</Alert>}

      {job && (
        <div className="mt-10 grid gap-6 sm:grid-cols-2">
          {job.presentations.map((p) => {
            const Icon = p.kind === 'summary' ? ListChecks : BookOpenCheck
            return (
              <div key={p.id} className="card flex flex-col p-6">
                <div className="flex items-center gap-3">
                  <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand-600 text-white"><Icon className="h-6 w-6" /></span>
                  <div>
                    <p className="font-bold capitalize text-slate-900 dark:text-white">{p.kind} presentation</p>
                    <p className="text-sm text-slate-500">{p.slide_count} slides • {byId[p.template]?.name || p.template}</p>
                  </div>
                </div>
                <p className="mt-4 line-clamp-2 flex-1 text-sm text-slate-600 dark:text-slate-400">{p.title}</p>
                <div className="mt-6 flex gap-2">
                  <Button className="flex-1" icon={done[p.id] ? CheckCircle2 : Download} loading={busy === p.id} onClick={() => download(p)}>
                    {done[p.id] ? 'Download again' : 'Download .pptx'}
                  </Button>
                  <Button variant="secondary" icon={PencilLine} to={`/preview/${jobId}?kind=${p.kind}`} aria-label={`Edit ${p.kind}`} />
                </div>
              </div>
            )
          })}
        </div>
      )}

      <div className="mt-12 flex flex-col items-center gap-3">
        <Button variant="secondary" icon={Upload} to="/upload">Convert another PDF</Button>
        <p className="text-xs text-slate-500">Files are removed from our server automatically after 24 hours.</p>
      </div>
    </div>
  )
}
