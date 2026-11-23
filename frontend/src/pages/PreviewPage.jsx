import {
  ArrowDown, ArrowRight, ArrowUp, Check, ChevronLeft, ChevronRight, CloudOff, Download, GripVertical, Loader2,
  Plus, RefreshCw, Trash2,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import SlideCanvas from '../components/SlideCanvas'
import SlideEditor from '../components/SlideEditor'
import Stepper from '../components/Stepper'
import { Alert, Button, PageLoader } from '../components/ui'
import { useTemplates } from '../hooks/useTemplates'
import { api, errorMessage } from '../services/api'

const EDITABLE = ['type', 'title', 'subtitle', 'bullets', 'definitions', 'steps', 'comparison', 'notes']

function toPayload(slide) {
  const p = {}
  for (const k of EDITABLE) if (k in slide) p[k] = slide[k]
  p.bullets = (p.bullets || []).filter((b) => b.trim())
  p.steps = (p.steps || []).filter((b) => b.trim())
  p.definitions = (p.definitions || []).filter((d) => d.term.trim() && d.definition.trim())
  if (p.comparison) {
    p.comparison = { ...p.comparison, left: p.comparison.left.filter((x) => x.trim()), right: p.comparison.right.filter((x) => x.trim()) }
  }
  if (!p.title?.trim()) p.title = 'Untitled'
  return p
}

function withSectionNumbers(slides) {
  let n = 0
  return slides.map((s) => (s.type === 'section' ? { ...s, _sectionNo: ++n } : s))
}

export default function PreviewPage() {
  const { jobId } = useParams()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const { templates, byId } = useTemplates()

  const [job, setJob] = useState(null)
  const [pres, setPres] = useState(null)
  const [slides, setSlides] = useState([])
  const [selected, setSelected] = useState(0)
  const [error, setError] = useState(null)
  const [toast, setToast] = useState(null)
  const [saveState, setSaveState] = useState('saved') // saved | saving | error
  const [busy, setBusy] = useState(null) // 'regen' | 'delete' | 'download' | 'template' | 'add'
  const [dragId, setDragId] = useState(null)

  const pending = useRef(new Map())
  const timer = useRef(null)
  const presRef = useRef(null)
  useEffect(() => {
    presRef.current = pres
  }, [pres])

  const kind = params.get('kind')
  const current = job?.presentations.find((p) => p.kind === kind) || job?.presentations[0]

  const notify = useCallback((msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3000)
  }, [])

  // ---- loading ------------------------------------------------------------
  useEffect(() => {
    api.getJob(jobId).then((j) => {
      if (j.status !== 'completed') navigate(`/processing/${jobId}`, { replace: true })
      setJob(j)
    }).catch((e) => setError(errorMessage(e, 'Presentation not found.')))
  }, [jobId, navigate])

  useEffect(() => {
    if (!current) return
    api.getPresentation(current.id).then((p) => {
      setPres(p)
      setSlides(p.slides)
      setSelected(0)
    }).catch((e) => setError(errorMessage(e)))
  }, [current?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  // ---- autosave -----------------------------------------------------------
  const flush = useCallback(async () => {
    clearTimeout(timer.current)
    const p = presRef.current
    if (!p || pending.current.size === 0) return true
    const batch = [...pending.current.values()]
    pending.current.clear()
    setSaveState('saving')
    try {
      for (const s of batch) await api.updateSlide(p.id, s.id, toPayload(s))
      setSaveState(pending.current.size ? 'saving' : 'saved')
      return true
    } catch (e) {
      setSaveState('error')
      setError(errorMessage(e, 'Could not save your changes.'))
      return false
    }
  }, [])

  useEffect(() => {
    const warn = (e) => {
      if (pending.current.size) {
        e.preventDefault()
        e.returnValue = ''
      }
    }
    window.addEventListener('beforeunload', warn)
    return () => {
      window.removeEventListener('beforeunload', warn)
      flush()
    }
  }, [flush])

  const editSlide = (updated) => {
    setSlides((ss) => ss.map((s) => (s.id === updated.id ? updated : s)))
    pending.current.set(updated.id, updated)
    setSaveState('saving')
    clearTimeout(timer.current)
    timer.current = setTimeout(flush, 700)
  }

  // ---- slide operations ---------------------------------------------------
  const slide = slides[selected]
  const numbered = useMemo(() => withSectionNumbers(slides), [slides])

  const applyServer = (p, keepId) => {
    setPres(p)
    setSlides(p.slides)
    const idx = keepId ? p.slides.findIndex((s) => s.id === keepId) : -1
    setSelected(idx >= 0 ? idx : Math.min(selected, p.slides.length - 1))
  }

  const reorder = async (order, keepId) => {
    if (!(await flush())) return
    const byIdMap = Object.fromEntries(slides.map((s) => [s.id, s]))
    setSlides(order.map((id) => byIdMap[id]))
    setSelected(order.indexOf(keepId))
    try {
      applyServer(await api.reorderSlides(pres.id, order), keepId)
    } catch (e) {
      setError(errorMessage(e))
      applyServer(await api.getPresentation(pres.id), keepId)
    }
  }

  const move = (from, to) => {
    if (to < 0 || to >= slides.length || from === to) return
    const order = slides.map((s) => s.id)
    const [id] = order.splice(from, 1)
    order.splice(to, 0, id)
    reorder(order, id)
  }

  const remove = async () => {
    if (!slide || slides.length <= 1) return
    if (!window.confirm(`Delete slide ${selected + 1} “${slide.title}”?`)) return
    if (!(await flush())) return
    setBusy('delete')
    try {
      const p = await api.deleteSlide(pres.id, slide.id)
      applyServer(p)
      notify('Slide deleted')
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(null)
    }
  }

  const regenerate = async () => {
    if (!(await flush())) return
    setBusy('regen')
    try {
      const s = await api.regenerateSlide(pres.id, slide.id)
      setSlides((ss) => ss.map((x) => (x.id === s.id ? s : x)))
      notify('Slide regenerated from the source pages')
    } catch (e) {
      setError(errorMessage(e, 'Could not regenerate this slide.'))
    } finally {
      setBusy(null)
    }
  }

  const addSlide = async () => {
    if (!(await flush())) return
    setBusy('add')
    try {
      const p = await api.addSlide(pres.id, { type: 'content', title: 'New slide', bullets: ['Add your first point'] }, slide?.id)
      setPres(p)
      setSlides(p.slides)
      setSelected(selected + 1)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(null)
    }
  }

  const changeTemplate = async (template) => {
    if (!(await flush())) return
    setBusy('template')
    try {
      const p = await api.updatePresentation(pres.id, { template })
      setPres(p)
      notify(`Template changed to ${byId[template]?.name || template}`)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(null)
    }
  }

  const download = async () => {
    if (!(await flush())) return
    setBusy('download')
    try {
      const name = await api.downloadPresentation(pres.id)
      notify(`Downloaded ${name}`)
    } catch (e) {
      setError(errorMessage(e, 'Download failed.'))
    } finally {
      setBusy(null)
    }
  }

  // keyboard navigation (when not typing)
  useEffect(() => {
    const onKey = (e) => {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') setSelected((i) => Math.min(i + 1, slides.length - 1))
      if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') setSelected((i) => Math.max(i - 1, 0))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [slides.length])

  if (error && !job) return <div className="mx-auto max-w-xl p-12"><Alert type="error">{error}</Alert></div>
  if (!job || !pres || pres.id !== current?.id) return <PageLoader label="Loading presentation…" />

  const template = byId[pres.template]

  return (
    <div className="mx-auto max-w-[1600px] px-4 py-8 sm:px-6">
      <Stepper current={3} />

      {/* Toolbar */}
      <div className="card mb-5 flex flex-wrap items-center gap-3 p-3">
        <div className="flex rounded-xl bg-slate-100 p-1 dark:bg-slate-800" role="tablist">
          {job.presentations.map((p) => (
            <button key={p.id} role="tab" aria-selected={p.id === current.id}
              onClick={async () => { await flush(); setParams({ kind: p.kind }) }}
              className={`rounded-lg px-4 py-1.5 text-sm font-semibold capitalize transition ${p.id === current.id ? 'bg-white text-brand-700 shadow-sm dark:bg-slate-900 dark:text-brand-300' : 'text-slate-600 hover:text-slate-900 dark:text-slate-400'}`}>
              {p.kind} <span className="ml-1 text-xs opacity-60">{p.id === current.id ? slides.length : p.slide_count}</span>
            </button>
          ))}
        </div>
        <select aria-label="Template" className="input w-auto py-2" value={pres.template} disabled={busy === 'template'} onChange={(e) => changeTemplate(e.target.value)}>
          {templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
        <span className="flex items-center gap-1.5 text-xs text-slate-500" aria-live="polite">
          {saveState === 'saving' && <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Saving…</>}
          {saveState === 'saved' && <><Check className="h-3.5 w-3.5 text-emerald-500" /> All changes saved</>}
          {saveState === 'error' && <><CloudOff className="h-3.5 w-3.5 text-red-500" /> Not saved</>}
        </span>
        <div className="ml-auto flex flex-wrap gap-2">
          <Button variant="secondary" icon={Download} onClick={download} loading={busy === 'download'}>Download PPTX</Button>
          <Button onClick={async () => { await flush(); navigate(`/download/${jobId}`) }}>Finish <ArrowRight className="h-4 w-4" /></Button>
        </div>
      </div>

      {error && <Alert type="error" className="mb-4" onClose={() => setError(null)}>{error}</Alert>}
      {job.warnings?.length > 0 && (
        <Alert type="warning" className="mb-4" title="Notes about this conversion">
          <ul className="list-disc pl-4">{job.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
        </Alert>
      )}

      <div className="grid gap-5 lg:grid-cols-[220px_1fr] xl:grid-cols-[220px_1fr_400px]">
        {/* Thumbnails */}
        <aside className="card order-2 max-h-[75vh] overflow-y-auto p-3 lg:order-1" aria-label="Slides">
          <ol className="flex gap-3 overflow-x-auto lg:flex-col lg:overflow-visible">
            {numbered.map((s, i) => (
              <li key={s.id}
                draggable
                onDragStart={() => setDragId(s.id)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault()
                  const from = slides.findIndex((x) => x.id === dragId)
                  if (from >= 0) move(from, i)
                  setDragId(null)
                }}
                onDragEnd={() => setDragId(null)}
                className={`group w-40 shrink-0 lg:w-auto ${dragId === s.id ? 'opacity-40' : ''}`}>
                <button onClick={() => setSelected(i)} aria-current={i === selected} aria-label={`Slide ${i + 1}: ${s.title}`}
                  className={`flex w-full items-start gap-1.5 rounded-xl p-1.5 text-left transition ${i === selected ? 'bg-brand-50 ring-2 ring-brand-500 dark:bg-brand-950/50' : 'hover:bg-slate-100 dark:hover:bg-slate-800'}`}>
                  <span className="flex w-5 flex-col items-center pt-0.5 text-xs font-semibold text-slate-500">
                    {i + 1}
                    <GripVertical className="mt-1 h-3.5 w-3.5 cursor-grab opacity-0 group-hover:opacity-60" />
                  </span>
                  <div aria-hidden="true" className="pointer-events-none flex-1 overflow-hidden rounded-md border border-slate-200 dark:border-slate-700">
                    <SlideCanvas slide={s} index={i + 1} total={slides.length} template={template} docName={pres.document_name} />
                  </div>
                </button>
              </li>
            ))}
          </ol>
          <button onClick={addSlide} disabled={busy === 'add'} className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-xl border-2 border-dashed border-slate-300 py-2.5 text-sm font-medium text-slate-500 hover:border-brand-400 hover:text-brand-600 dark:border-slate-700">
            {busy === 'add' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} Add slide
          </button>
        </aside>

        {/* Main preview */}
        <section className="order-1 min-w-0 lg:order-2">
          {slide && (
            <>
              <div className="card overflow-hidden p-2 shadow-lg">
                <SlideCanvas slide={numbered[selected]} index={selected + 1} total={slides.length} template={template} docName={pres.document_name} className="rounded-xl" />
              </div>
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Button variant="secondary" size="sm" icon={ChevronLeft} disabled={selected === 0} onClick={() => setSelected(selected - 1)} aria-label="Previous slide" />
                  <span className="min-w-20 text-center text-sm font-semibold text-slate-600 dark:text-slate-300">
                    {selected + 1} / {slides.length}
                  </span>
                  <Button variant="secondary" size="sm" icon={ChevronRight} disabled={selected === slides.length - 1} onClick={() => setSelected(selected + 1)} aria-label="Next slide" />
                </div>
                <div className="flex flex-wrap items-center gap-1">
                  <Button variant="ghost" size="sm" icon={ArrowUp} disabled={selected === 0} onClick={() => move(selected, selected - 1)} aria-label="Move slide up">Move up</Button>
                  <Button variant="ghost" size="sm" icon={ArrowDown} disabled={selected === slides.length - 1} onClick={() => move(selected, selected + 1)} aria-label="Move slide down">Move down</Button>
                  <Button variant="ghost" size="sm" icon={RefreshCw} loading={busy === 'regen'}
                    disabled={slide.type === 'title' || !slide.source_pages?.length}
                    title={!slide.source_pages?.length ? 'Only slides with source pages can be regenerated' : 'Rewrite this slide from its source pages'}
                    onClick={regenerate}>Regenerate</Button>
                  <Button variant="danger" size="sm" icon={Trash2} loading={busy === 'delete'} disabled={slides.length <= 1} onClick={remove}>Delete</Button>
                </div>
              </div>
            </>
          )}
        </section>

        {/* Editor */}
        <aside className="card order-3 p-5 lg:col-span-2 xl:col-span-1 xl:max-h-[75vh] xl:overflow-y-auto" aria-label="Edit slide">
          <h2 className="mb-4 text-lg font-bold text-slate-900 dark:text-white">Edit slide {selected + 1}</h2>
          {slide && <SlideEditor key={slide.id} slide={slide} onChange={editSlide} />}
        </aside>
      </div>

      {toast && (
        <div className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 animate-fade-up rounded-xl bg-slate-900 px-4 py-3 text-sm font-medium text-white shadow-2xl dark:bg-white dark:text-slate-900" role="status">
          {toast.msg}
        </div>
      )}
    </div>
  )
}
