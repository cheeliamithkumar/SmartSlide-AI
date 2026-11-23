import { Brain, Check, FileSearch, LayoutTemplate, Presentation, RotateCcw, Shapes } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Stepper from '../components/Stepper'
import { Alert, Button } from '../components/ui'
import { api, errorMessage } from '../services/api'

const STAGES = [
  { key: 'extracting', label: 'Extracting text', icon: FileSearch },
  { key: 'analyzing', label: 'Understanding content', icon: Brain },
  { key: 'structuring', label: 'Finding key takeaways', icon: Shapes },
  { key: 'composing', label: 'Designing slides', icon: LayoutTemplate },
  { key: 'rendering', label: 'Building PowerPoint', icon: Presentation },
]
const ORDER = ['queued', ...STAGES.map((s) => s.key), 'completed']

export default function ProcessingPage() {
  const { jobId } = useParams()
  const navigate = useNavigate()
  const [job, setJob] = useState(null)
  const [error, setError] = useState(null)
  const failures = useRef(0)

  useEffect(() => {
    let alive = true
    let timer
    const poll = async () => {
      try {
        const j = await api.getJob(jobId)
        if (!alive) return
        failures.current = 0
        setJob(j)
        if (j.status === 'completed') {
          timer = setTimeout(() => navigate(`/preview/${jobId}`, { replace: true }), 900)
          return
        }
        if (j.status === 'failed') return
      } catch (e) {
        failures.current += 1
        if (e.response?.status === 404 || failures.current > 5) {
          setError(errorMessage(e, 'Lost connection to the server.'))
          return
        }
      }
      timer = setTimeout(poll, 1000)
    }
    poll()
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [jobId, navigate])

  const stageIdx = job ? ORDER.indexOf(job.stage === 'failed' ? 'queued' : job.stage) : 0
  const progress = Math.round(job?.progress || 0)
  const failed = job?.status === 'failed'

  return (
    <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
      <Stepper current={2} />
      <div className="card overflow-hidden">
        <div className="bg-gradient-to-br from-brand-600 via-violet-600 to-fuchsia-600 px-8 py-10 text-center text-white">
          <div className="relative mx-auto h-28 w-28">
            <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90">
              <circle cx="50" cy="50" r="44" stroke="rgba(255,255,255,0.2)" strokeWidth="8" fill="none" />
              <circle cx="50" cy="50" r="44" stroke="white" strokeWidth="8" fill="none" strokeLinecap="round"
                strokeDasharray={2 * Math.PI * 44} strokeDashoffset={2 * Math.PI * 44 * (1 - progress / 100)}
                className="transition-all duration-700" />
            </svg>
            <span className="absolute inset-0 flex items-center justify-center text-2xl font-extrabold">{progress}%</span>
          </div>
          <h1 className="mt-5 text-2xl font-extrabold">
            {failed ? 'Conversion failed' : job?.status === 'completed' ? 'Your presentations are ready!' : 'Creating your presentations…'}
          </h1>
          <p className="mt-2 text-brand-100" aria-live="polite">{job?.message || 'Starting…'}</p>
        </div>

        <div className="p-8">
          {(error || failed) && (
            <Alert type="error" title="We couldn't finish this conversion" className="mb-6">
              {error || job?.error}
            </Alert>
          )}
          <ol className="space-y-4">
            {STAGES.map(({ key, label, icon: Icon }) => {
              const idx = ORDER.indexOf(key)
              const done = stageIdx > idx || job?.status === 'completed'
              const active = stageIdx === idx && !failed
              return (
                <li key={key} className="flex items-center gap-4">
                  <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition ${
                    done ? 'bg-emerald-500 text-white' : active ? 'bg-brand-600 text-white shadow-lg shadow-brand-600/30' : 'bg-slate-100 text-slate-400 dark:bg-slate-800'}`}>
                    {done ? <Check className="h-5 w-5" /> : <Icon className={`h-5 w-5 ${active ? 'animate-pulse' : ''}`} />}
                  </span>
                  <span className={`font-medium ${done || active ? 'text-slate-900 dark:text-white' : 'text-slate-400'}`}>{label}</span>
                  {active && <span className="ml-auto text-xs font-semibold text-brand-600 dark:text-brand-400">In progress</span>}
                </li>
              )
            })}
          </ol>
          {(failed || error) && (
            <div className="mt-8 flex flex-wrap justify-center gap-3">
              {job && <Button variant="secondary" icon={RotateCcw} to={`/configure/${job.document_id}`}>Try different settings</Button>}
              <Button to="/upload">Upload another PDF</Button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
