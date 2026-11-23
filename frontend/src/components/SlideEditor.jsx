import { ArrowDown, ArrowUp, Network, Plus, Trash2 } from 'lucide-react'
import { SLIDE_TYPE_LABELS, pageLabel } from '../utils/format'

function ListEditor({ label, items, onChange, placeholder, max = 8, rows = 2 }) {
  const update = (i, v) => onChange(items.map((x, j) => (j === i ? v : x)))
  const remove = (i) => onChange(items.filter((_, j) => j !== i))
  const move = (i, d) => {
    const next = [...items]
    const [it] = next.splice(i, 1)
    next.splice(i + d, 0, it)
    onChange(next)
  }
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <span className="label mb-0">{label}</span>
        <span className="text-xs text-slate-400">
          {items.length}/{max}
        </span>
      </div>
      <div className="space-y-2">
        {items.map((it, i) => (
          <div key={i} className="group flex gap-1.5">
            <textarea
              value={it}
              rows={rows}
              onChange={(e) => update(i, e.target.value)}
              className="input resize-y py-2 leading-snug"
              placeholder={placeholder}
              aria-label={`${label} ${i + 1}`}
            />
            <div className="flex flex-col gap-0.5">
              <button type="button" disabled={i === 0} onClick={() => move(i, -1)} className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-30 dark:hover:bg-slate-800" aria-label={`Move ${label} item ${i + 1} up`}>
                <ArrowUp className="h-3.5 w-3.5" />
              </button>
              <button type="button" disabled={i === items.length - 1} onClick={() => move(i, 1)} className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-30 dark:hover:bg-slate-800" aria-label={`Move ${label} item ${i + 1} down`}>
                <ArrowDown className="h-3.5 w-3.5" />
              </button>
              <button type="button" onClick={() => remove(i)} className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950" aria-label={`Remove ${label} item ${i + 1}`}>
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        ))}
      </div>
      {items.length < max && (
        <button type="button" onClick={() => onChange([...items, ''])} className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-brand-600 hover:text-brand-700 dark:text-brand-400">
          <Plus className="h-4 w-4" /> Add item
        </button>
      )}
    </div>
  )
}

function DiagramEditor({ diagram, onChange, onRemove }) {
  const nodes = diagram.nodes || []
  const setNode = (i, patch) => onChange({ ...diagram, nodes: nodes.map((n, j) => (j === i ? { ...n, ...patch } : n)) })
  const max = diagram.kind === 'timeline' ? 7 : 6
  const KIND = { mindmap: 'Concept map', timeline: 'Roadmap', cycle: 'Cycle', flow: 'Flow' }
  return (
    <div className="rounded-xl border border-brand-200 bg-brand-50/40 p-3 dark:border-brand-900 dark:bg-brand-950/20">
      <div className="mb-2 flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-sm font-semibold text-brand-700 dark:text-brand-300">
          <Network className="h-4 w-4" /> {KIND[diagram.kind]} diagram
        </span>
        {onRemove && (
          <button type="button" onClick={onRemove} className="text-xs font-medium text-slate-500 hover:text-red-600">Remove diagram</button>
        )}
      </div>
      {diagram.kind === 'mindmap' && (
        <input className="input mb-2 font-semibold" value={diagram.center || ''} maxLength={120} placeholder="Central idea"
          aria-label="Diagram centre" onChange={(e) => onChange({ ...diagram, center: e.target.value })} />
      )}
      <div className="space-y-2">
        {nodes.map((n, i) => (
          <div key={i} className="flex gap-1.5">
            <div className="flex-1 space-y-1">
              <input className="input py-2" value={n.label} maxLength={80} aria-label={`Diagram node ${i + 1}`}
                onChange={(e) => setNode(i, { label: e.target.value })} />
              {diagram.kind === 'timeline' && (
                <input className="input py-1.5 text-xs" value={n.detail || ''} maxLength={200} placeholder="Short description (optional)"
                  aria-label={`Diagram node ${i + 1} description`} onChange={(e) => setNode(i, { detail: e.target.value })} />
              )}
            </div>
            <button type="button" onClick={() => onChange({ ...diagram, nodes: nodes.filter((_, j) => j !== i) })}
              className="self-start rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950" aria-label={`Remove diagram node ${i + 1}`}>
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
      {nodes.length < max && (
        <button type="button" onClick={() => onChange({ ...diagram, nodes: [...nodes, { label: 'New idea' }] })}
          className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-brand-600 hover:text-brand-700 dark:text-brand-400">
          <Plus className="h-4 w-4" /> Add node
        </button>
      )}
    </div>
  )
}

export default function SlideEditor({ slide, onChange }) {
  const set = (patch) => onChange({ ...slide, ...patch })
  const t = slide.type
  const cmp = slide.comparison || { left_title: 'A', right_title: 'B', left: [], right: [] }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="rounded-full bg-slate-100 px-2.5 py-1 font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          {SLIDE_TYPE_LABELS[t] || t}
        </span>
        {slide.source_pages?.length > 0 && (
          <span className="rounded-full bg-brand-50 px-2.5 py-1 font-semibold text-brand-700 dark:bg-brand-950 dark:text-brand-300">
            Source: {pageLabel(slide.source_pages)}
          </span>
        )}
      </div>

      <div>
        <label className="label" htmlFor="slide-title">Slide title</label>
        <input id="slide-title" className="input font-semibold" value={slide.title} maxLength={300} onChange={(e) => set({ title: e.target.value })} />
      </div>

      {(t === 'title' || t === 'section') && (
        <div>
          <label className="label" htmlFor="slide-subtitle">Subtitle</label>
          <input id="slide-subtitle" className="input" value={slide.subtitle || ''} maxLength={400} onChange={(e) => set({ subtitle: e.target.value })} />
        </div>
      )}

      {['content', 'example', 'takeaways', 'conclusion'].includes(t) && (
        <ListEditor label="Bullet points" items={slide.bullets || []} max={t === 'takeaways' ? 6 : 7} placeholder="Write a concise point…" onChange={(bullets) => set({ bullets })} />
      )}

      {t === 'process' && (
        <>
          <label className="flex cursor-pointer items-center justify-between rounded-xl border border-slate-200 px-3 py-2.5 text-sm dark:border-slate-700">
            <span>
              <span className="block font-medium text-slate-800 dark:text-slate-200">Show as a cycle</span>
              <span className="block text-xs text-slate-500">Arrange steps in a loop instead of a left-to-right flow</span>
            </span>
            <input type="checkbox" className="h-5 w-5 accent-brand-600" checked={slide.diagram?.kind === 'cycle'}
              onChange={(e) => set({ diagram: { kind: e.target.checked ? 'cycle' : 'flow', nodes: [] } })} />
          </label>
          <ListEditor label="Process steps" items={slide.steps || []} max={6} placeholder="Describe this step…" onChange={(steps) => set({ steps })} />
        </>
      )}

      {t === 'diagram' && slide.diagram && (
        <DiagramEditor diagram={slide.diagram} onChange={(diagram) => set({ diagram })} />
      )}

      {t === 'content' && slide.diagram?.kind === 'mindmap' && (
        <DiagramEditor diagram={slide.diagram} onChange={(diagram) => set({ diagram })} onRemove={() => set({ diagram: null })} />
      )}
      {t === 'content' && !slide.diagram && (
        <button type="button" onClick={() => set({ diagram: { kind: 'mindmap', center: slide.title, nodes: [{ label: 'Key idea 1' }, { label: 'Key idea 2' }, { label: 'Key idea 3' }] }, bullets: (slide.bullets || []).slice(0, 4) })}
          className="inline-flex items-center gap-1.5 rounded-lg border border-dashed border-brand-300 px-3 py-2 text-sm font-medium text-brand-600 hover:bg-brand-50 dark:border-brand-800 dark:text-brand-400 dark:hover:bg-brand-950/40">
          <Network className="h-4 w-4" /> Add concept map
        </button>
      )}

      {t === 'definition' && (
        <div>
          <span className="label">Definitions</span>
          <div className="space-y-3">
            {(slide.definitions || []).map((d, i) => (
              <div key={i} className="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
                <div className="flex gap-2">
                  <input className="input font-semibold" value={d.term} placeholder="Term" aria-label={`Term ${i + 1}`}
                    onChange={(e) => set({ definitions: slide.definitions.map((x, j) => (j === i ? { ...x, term: e.target.value } : x)) })} />
                  <button type="button" onClick={() => set({ definitions: slide.definitions.filter((_, j) => j !== i) })} className="rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950" aria-label="Remove definition">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
                <textarea className="input mt-2 resize-y" rows={3} value={d.definition} placeholder="Definition" aria-label={`Definition ${i + 1}`}
                  onChange={(e) => set({ definitions: slide.definitions.map((x, j) => (j === i ? { ...x, definition: e.target.value } : x)) })} />
              </div>
            ))}
          </div>
          {(slide.definitions || []).length < 4 && (
            <button type="button" onClick={() => set({ definitions: [...(slide.definitions || []), { term: 'New term', definition: 'Definition' }] })} className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-brand-600 hover:text-brand-700 dark:text-brand-400">
              <Plus className="h-4 w-4" /> Add definition
            </button>
          )}
        </div>
      )}

      {t === 'comparison' && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
          {['left', 'right'].map((side) => (
            <div key={side} className="space-y-2">
              <input className="input font-semibold" value={cmp[`${side}_title`]} aria-label={`${side} column title`}
                onChange={(e) => set({ comparison: { ...cmp, [`${side}_title`]: e.target.value } })} />
              <ListEditor label={side === 'left' ? 'Left column' : 'Right column'} items={cmp[side]} max={5}
                onChange={(items) => set({ comparison: { ...cmp, [side]: items } })} />
            </div>
          ))}
        </div>
      )}

      <div>
        <label className="label" htmlFor="slide-notes">Speaker notes</label>
        <textarea id="slide-notes" className="input resize-y text-sm" rows={4} value={slide.notes || ''} maxLength={6000} onChange={(e) => set({ notes: e.target.value })} placeholder="Notes for the presenter (included in the PPTX)" />
      </div>
    </div>
  )
}
