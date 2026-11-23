import { BookOpenCheck, Check, FileText, ListChecks, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import SlideCanvas from '../components/SlideCanvas'
import Stepper from '../components/Stepper'
import { Alert, Button, PageLoader } from '../components/ui'
import { useTemplates } from '../hooks/useTemplates'
import { api, errorMessage } from '../services/api'
import { formatBytes } from '../utils/format'

const PREVIEW_SLIDE = {
  id: 'p', type: 'content', title: 'Key Concepts',
  bullets: ['Concise, simplified bullet points', 'Definitions and examples from your PDF', 'Source page references on every slide'],
  source_pages: [3],
}

function KindCard({ active, onClick, icon: Icon, title, desc, range }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`relative flex w-full items-start gap-4 rounded-2xl border-2 p-5 text-left transition ${
        active
          ? 'border-brand-500 bg-brand-50/60 dark:bg-brand-950/30'
          : 'border-slate-200 bg-white hover:border-slate-300 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-slate-700'
      }`}
    >
      <span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${active ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-500 dark:bg-slate-800'}`}>
        <Icon className="h-5 w-5" />
      </span>
      <span className="flex-1">
        <span className="block font-bold text-slate-900 dark:text-white">{title}</span>
        <span className="mt-0.5 block text-sm text-slate-500">{desc}</span>
        <span className="mt-2 inline-block text-xs font-semibold text-brand-600 dark:text-brand-400">{range}</span>
      </span>
      <span className={`flex h-6 w-6 items-center justify-center rounded-full border-2 ${active ? 'border-brand-600 bg-brand-600 text-white' : 'border-slate-300 dark:border-slate-600'}`}>
        {active && <Check className="h-3.5 w-3.5" />}
      </span>
    </button>
  )
}

function Range({ label, value, min, max, onChange, disabled }) {
  return (
    <div className={disabled ? 'opacity-40' : ''}>
      <div className="flex items-center justify-between">
        <label className="label mb-0">{label}</label>
        <span className="rounded-lg bg-brand-50 px-2 py-0.5 text-sm font-bold text-brand-700 dark:bg-brand-950 dark:text-brand-300">{value} slides</span>
      </div>
      <input type="range" min={min} max={max} value={value} disabled={disabled} onChange={(e) => onChange(Number(e.target.value))} className="mt-3 w-full accent-brand-600" aria-label={label} />
      <div className="flex justify-between text-xs text-slate-400">
        <span>{min}</span>
        <span>{max}</span>
      </div>
    </div>
  )
}

export default function ConfigurePage() {
  const { documentId } = useParams()
  const navigate = useNavigate()
  const { templates } = useTemplates()
  const [doc, setDoc] = useState(null)
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [opts, setOpts] = useState({
    summary: true, detailed: true, template: 'modern_education', summary_slides: 12, detailed_slides: 24,
    audience: 'students', include_notes: true,
  })
  const set = (patch) => setOpts((o) => ({ ...o, ...patch }))

  useEffect(() => {
    api.getDocument(documentId).then(setDoc).catch((e) => setError(errorMessage(e, 'Document not found.')))
  }, [documentId])

  const submit = async () => {
    const kinds = [opts.summary && 'summary', opts.detailed && 'detailed'].filter(Boolean)
    if (!kinds.length) {
      setError('Select at least one presentation type.')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const job = await api.createJob({
        document_id: documentId, kinds, template: opts.template, summary_slides: opts.summary_slides,
        detailed_slides: opts.detailed_slides, audience: opts.audience, include_notes: opts.include_notes,
      })
      navigate(`/processing/${job.id}`)
    } catch (e) {
      setError(errorMessage(e))
      setSubmitting(false)
    }
  }

  if (!doc && !error) return <PageLoader label="Loading document…" />

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
      <Stepper current={1} />
      <div className="text-center">
        <h1 className="text-3xl font-extrabold text-slate-900 sm:text-4xl dark:text-white">Configure your presentations</h1>
        <p className="mt-3 text-slate-600 dark:text-slate-400">Choose what to generate and how it should look.</p>
      </div>

      {error && <Alert type="error" className="mx-auto mt-8 max-w-3xl">{error}</Alert>}

      {doc && (
        <div className="mt-10 grid gap-8 lg:grid-cols-[1fr_340px]">
          <div className="space-y-8">
            <section className="card p-6">
              <h2 className="text-lg font-bold text-slate-900 dark:text-white">1. Presentation type</h2>
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <KindCard active={opts.summary} onClick={() => set({ summary: !opts.summary })} icon={ListChecks} title="Summary" desc="Key concepts, simplified bullets, definitions and takeaways." range="Recommended 10–15 slides" />
                <KindCard active={opts.detailed} onClick={() => set({ detailed: !opts.detailed })} icon={BookOpenCheck} title="Detailed" desc="Topic-by-topic coverage with explanations, examples and processes." range="Recommended 20–30 slides" />
              </div>
              <div className="mt-6 grid gap-6 sm:grid-cols-2">
                <Range label="Summary length" value={opts.summary_slides} min={6} max={20} disabled={!opts.summary} onChange={(v) => set({ summary_slides: v })} />
                <Range label="Detailed length" value={opts.detailed_slides} min={12} max={40} disabled={!opts.detailed} onChange={(v) => set({ detailed_slides: v })} />
              </div>
              <p className="mt-4 text-xs text-slate-500">Slide counts are maximums. Short documents may produce fewer slides, so content is never padded.</p>
            </section>

            <section className="card p-6">
              <h2 className="text-lg font-bold text-slate-900 dark:text-white">2. Design template</h2>
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                {templates.map((t) => (
                  <button key={t.id} type="button" onClick={() => set({ template: t.id })} aria-pressed={opts.template === t.id}
                    className={`overflow-hidden rounded-2xl border-2 p-1.5 text-left transition ${opts.template === t.id ? 'border-brand-500 ring-4 ring-brand-500/15' : 'border-slate-200 hover:border-slate-300 dark:border-slate-800 dark:hover:border-slate-700'}`}>
                    <SlideCanvas slide={PREVIEW_SLIDE} index={3} total={12} template={t} docName={doc.original_filename} className="rounded-xl" />
                    <div className="flex items-center justify-between px-2 py-2.5">
                      <div>
                        <p className="text-sm font-semibold text-slate-900 dark:text-white">{t.name}</p>
                        <p className="text-xs text-slate-500">{t.font}</p>
                      </div>
                      <div className="flex gap-1">
                        {['primary', 'accent', 'surface'].map((k) => (
                          <span key={k} className="h-4 w-4 rounded-full border border-black/10" style={{ background: `#${t.colors[k]}` }} />
                        ))}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </section>

            <section className="card p-6">
              <h2 className="text-lg font-bold text-slate-900 dark:text-white">3. Options</h2>
              <div className="mt-4 grid gap-6 sm:grid-cols-2">
                <div>
                  <label className="label" htmlFor="audience">Audience</label>
                  <select id="audience" className="input" value={opts.audience} onChange={(e) => set({ audience: e.target.value })}>
                    <option value="students">Students</option>
                    <option value="educators">Educators</option>
                    <option value="general">General audience</option>
                  </select>
                </div>
                <label className="flex cursor-pointer items-center justify-between gap-4 rounded-xl border border-slate-200 px-4 py-3 dark:border-slate-700">
                  <span>
                    <span className="block text-sm font-medium text-slate-800 dark:text-slate-200">Speaker notes</span>
                    <span className="block text-xs text-slate-500">Add explanations to each slide's notes</span>
                  </span>
                  <input type="checkbox" checked={opts.include_notes} onChange={(e) => set({ include_notes: e.target.checked })} className="h-5 w-5 accent-brand-600" />
                </label>
              </div>
            </section>
          </div>

          <aside className="space-y-6 lg:sticky lg:top-24 lg:self-start">
            <div className="card p-6">
              <div className="flex items-center gap-3">
                <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-red-50 text-red-600 dark:bg-red-950/50 dark:text-red-400">
                  <FileText className="h-5 w-5" />
                </span>
                <div className="min-w-0">
                  <p className="truncate font-semibold text-slate-900 dark:text-white" title={doc.original_filename}>{doc.original_filename}</p>
                  <p className="text-xs text-slate-500">{formatBytes(doc.size_bytes)}</p>
                </div>
              </div>
              {doc.title && <p className="mt-4 text-sm text-slate-600 dark:text-slate-400">“{doc.title}”</p>}
              <dl className="mt-4 grid grid-cols-2 gap-3 text-center">
                {[['Pages', doc.page_count], ['Words', doc.word_count.toLocaleString()], ['Text pages', doc.text_pages], ['Empty pages', doc.empty_pages]].map(([k, v]) => (
                  <div key={k} className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/60">
                    <dt className="text-xs text-slate-500">{k}</dt>
                    <dd className="text-lg font-bold text-slate-900 dark:text-white">{v}</dd>
                  </div>
                ))}
              </dl>
              {doc.is_scanned && (
                <Alert type="warning" className="mt-4">This looks like a scanned PDF. Text will be read with OCR, so accuracy may vary.</Alert>
              )}
              {!doc.is_scanned && doc.empty_pages > 0 && (
                <Alert type="info" className="mt-4">{doc.empty_pages} page(s) have no readable text and will be reported, not skipped silently.</Alert>
              )}
            </div>
            <Button size="lg" className="w-full" icon={Sparkles} onClick={submit} loading={submitting} disabled={!opts.summary && !opts.detailed}>
              Generate presentations
            </Button>
          </aside>
        </div>
      )}
    </div>
  )
}
