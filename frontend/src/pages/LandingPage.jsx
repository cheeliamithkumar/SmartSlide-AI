import {
  ArrowRight, BookOpenCheck, Brain, FileSearch, FileText, Layers, ListChecks, Lock, PencilLine, ScanText,
  Sparkles, Upload, Wand2, Download, Check,
} from 'lucide-react'
import SlideCanvas from '../components/SlideCanvas'
import { Badge, Button } from '../components/ui'
import { useTemplates } from '../hooks/useTemplates'

const DEMO_SLIDES = [
  { id: 'a', type: 'title', title: 'Photosynthesis: How Plants Make Food', subtitle: 'Summary Presentation • Key concepts from 8 topics', source_pages: [] },
  { id: 'b', type: 'process', title: 'The Calvin Cycle', steps: ['RuBisCO combines CO₂ with RuBP.', 'The product splits into two 3-carbon molecules.', 'ATP and NADPH convert them into G3P.', 'G3P is recycled to regenerate RuBP.'], source_pages: [2] },
  { id: 'c', type: 'definition', title: 'Important Definitions', definitions: [
    { term: 'Chloroplast', definition: 'An organelle found in plant cells where photosynthesis takes place.' },
    { term: 'Photolysis', definition: 'The splitting of water molecules using light energy.' },
    { term: 'RuBisCO', definition: 'An enzyme that catalyses the first step of carbon fixation.' },
  ], source_pages: [1, 2] },
]

const FEATURES = [
  { icon: Brain, title: 'AI that understands', text: 'Identifies topics, key concepts, definitions, examples and processes, then simplifies them without inventing facts.' },
  { icon: Layers, title: 'Two presentations at once', text: 'A crisp 10–15 slide Summary and a thorough 20–30 slide Detailed deck, organised topic by topic.' },
  { icon: PencilLine, title: 'Fully editable output', text: 'Native PowerPoint text, shapes, tables and diagrams. Not screenshots of PDF pages.' },
  { icon: FileSearch, title: 'Traceable to the source', text: 'Every slide cites the PDF pages it came from, so you can verify and study further.' },
  { icon: ScanText, title: 'Handles scanned PDFs', text: 'Built-in OCR reads scanned pages, and empty or unreadable pages are reported, never silently dropped.' },
  { icon: Lock, title: 'Private by design', text: 'Documents are never public and are deleted automatically after processing.' },
]

const STEPS = [
  { icon: Upload, title: 'Upload your PDF', text: 'Drag and drop lecture notes, textbook chapters or study guides.' },
  { icon: Wand2, title: 'Choose your style', text: 'Pick Summary, Detailed or both, a design template and slide counts.' },
  { icon: PencilLine, title: 'Review & edit', text: 'Preview every slide, edit text, reorder, remove or regenerate slides.' },
  { icon: Download, title: 'Download PPTX', text: 'Get polished, editable PowerPoint files ready to present.' },
]

function HeroVisual() {
  const { byId } = useTemplates()
  return (
    <div className="relative mx-auto w-full max-w-xl lg:max-w-none">
      <div className="absolute -inset-8 -z-10 rounded-full bg-gradient-to-tr from-brand-400/30 via-violet-400/20 to-fuchsia-300/30 blur-3xl" />
      <div className="relative">
        <div className="card overflow-hidden p-2 shadow-2xl shadow-brand-900/10">
          <SlideCanvas slide={DEMO_SLIDES[0]} index={1} total={12} template={byId.modern_education} docName="photosynthesis.pdf" className="rounded-xl" />
        </div>
        <div className="card absolute -bottom-14 -right-6 hidden w-[44%] animate-float [animation-delay:1.5s] overflow-hidden p-1.5 shadow-xl sm:block">
          <SlideCanvas slide={DEMO_SLIDES[1]} index={6} total={12} template={byId.modern_education} docName="photosynthesis.pdf" className="rounded-lg" />
        </div>
        <div className="card absolute -right-4 -top-10 hidden w-[42%] overflow-hidden p-1.5 shadow-xl animate-float sm:block">
          <SlideCanvas slide={DEMO_SLIDES[2]} index={9} total={12} template={byId.modern_education} docName="photosynthesis.pdf" className="rounded-lg" />
        </div>
      </div>
    </div>
  )
}

function TemplateShowcase() {
  const { templates } = useTemplates()
  if (!templates.length) return null
  return (
    <section className="mx-auto max-w-7xl px-4 py-20 sm:px-6">
      <div className="mx-auto max-w-2xl text-center">
        <Badge>Templates</Badge>
        <h2 className="mt-3 text-3xl font-extrabold text-slate-900 sm:text-4xl dark:text-white">Four professional designs</h2>
        <p className="mt-3 text-slate-600 dark:text-slate-400">Switch templates at any time, even after generation. Your edits are kept.</p>
      </div>
      <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {templates.map((t) => (
          <div key={t.id} className="card overflow-hidden p-2 transition hover:-translate-y-1 hover:shadow-lg">
            <SlideCanvas slide={DEMO_SLIDES[2]} index={4} total={12} template={t} docName="notes.pdf" className="rounded-lg" />
            <div className="p-3">
              <p className="font-semibold text-slate-900 dark:text-white">{t.name}</p>
              <p className="mt-1 text-xs text-slate-500">{t.description}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

export default function LandingPage() {
  return (
    <>
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 -z-10 bg-[radial-gradient(ellipse_at_top,_var(--color-brand-100),_transparent_60%)] dark:bg-[radial-gradient(ellipse_at_top,_rgba(79,70,229,0.18),_transparent_60%)]" />
        <div className="mx-auto grid max-w-7xl items-center gap-16 px-4 pt-16 pb-24 sm:px-6 lg:grid-cols-2 lg:pt-24">
          <div className="animate-fade-up">
            <Badge className="mb-5">
              <Sparkles className="h-3.5 w-3.5" /> AI-powered PDF → PowerPoint
            </Badge>
            <h1 className="text-4xl font-extrabold leading-[1.1] text-slate-900 sm:text-5xl lg:text-6xl dark:text-white">
              Turn any study PDF into <span className="gradient-text">smart, editable slides</span>
            </h1>
            <p className="mt-6 max-w-xl text-lg leading-relaxed text-slate-600 dark:text-slate-400">
              SmartSlide AI reads your lecture notes and textbooks, simplifies the hard parts and builds beautiful
              Summary and Detailed PowerPoint presentations in minutes.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button to="/upload" size="lg">
                Convert a PDF <ArrowRight className="h-4 w-4" />
              </Button>
              <Button to="/#how" variant="secondary" size="lg" onClick={() => document.getElementById('how')?.scrollIntoView()}>
                See how it works
              </Button>
            </div>
            <ul className="mt-8 flex flex-wrap gap-x-6 gap-y-2 text-sm text-slate-600 dark:text-slate-400">
              {['No sign-up required', 'Editable .pptx files', 'Source page references'].map((x) => (
                <li key={x} className="flex items-center gap-1.5">
                  <Check className="h-4 w-4 text-emerald-500" /> {x}
                </li>
              ))}
            </ul>
          </div>
          <HeroVisual />
        </div>
      </section>

      {/* Features */}
      <section id="features" className="scroll-mt-20 border-y border-slate-200/70 bg-white py-20 dark:border-slate-800 dark:bg-slate-900/40">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <div className="mx-auto max-w-2xl text-center">
            <Badge>Features</Badge>
            <h2 className="mt-3 text-3xl font-extrabold text-slate-900 sm:text-4xl dark:text-white">Built for students and educators</h2>
            <p className="mt-3 text-slate-600 dark:text-slate-400">Everything you need to go from dense reading material to a clear presentation.</p>
          </div>
          <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <div key={title} className="card p-6 transition hover:-translate-y-0.5 hover:shadow-md">
                <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-brand-950 dark:text-brand-300">
                  <Icon className="h-5 w-5" />
                </span>
                <h3 className="mt-4 text-lg font-bold text-slate-900 dark:text-white">{title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-400">{text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="mx-auto max-w-7xl scroll-mt-20 px-4 py-20 sm:px-6">
        <div className="mx-auto max-w-2xl text-center">
          <Badge>How it works</Badge>
          <h2 className="mt-3 text-3xl font-extrabold text-slate-900 sm:text-4xl dark:text-white">From PDF to presentation in four steps</h2>
        </div>
        <div className="mt-12 grid gap-6 md:grid-cols-4">
          {STEPS.map(({ icon: Icon, title, text }, i) => (
            <div key={title} className="relative text-center">
              <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500 to-violet-600 text-white shadow-lg shadow-brand-500/30">
                <Icon className="h-6 w-6" />
              </span>
              <p className="mt-4 text-xs font-bold uppercase tracking-wider text-brand-600 dark:text-brand-400">Step {i + 1}</p>
              <h3 className="mt-1 text-lg font-bold text-slate-900 dark:text-white">{title}</h3>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Two decks */}
      <section className="bg-white py-20 dark:bg-slate-900/40">
        <div className="mx-auto grid max-w-5xl gap-6 px-4 sm:px-6 md:grid-cols-2">
          {[
            { icon: ListChecks, name: 'Summary Presentation', slides: '10–15 slides', points: ['Most important concepts only', 'Paragraphs become concise bullets', 'Key definitions & takeaways', 'Perfect for revision'] },
            { icon: BookOpenCheck, name: 'Detailed Presentation', slides: '20–30 slides', points: ['Preserves important information', 'Organised section by section', 'Definitions, examples & processes', 'Perfect for teaching'] },
          ].map(({ icon: Icon, name, slides, points }) => (
            <div key={name} className="card p-8">
              <div className="flex items-center justify-between">
                <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand-600 text-white">
                  <Icon className="h-6 w-6" />
                </span>
                <Badge>{slides}</Badge>
              </div>
              <h3 className="mt-5 text-2xl font-bold text-slate-900 dark:text-white">{name}</h3>
              <ul className="mt-4 space-y-2.5">
                {points.map((p) => (
                  <li key={p} className="flex items-center gap-2 text-slate-600 dark:text-slate-400">
                    <Check className="h-4 w-4 text-emerald-500" /> {p}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <TemplateShowcase />

      {/* CTA */}
      <section className="px-4 pb-24 sm:px-6">
        <div className="relative mx-auto max-w-5xl overflow-hidden rounded-3xl bg-gradient-to-br from-brand-600 via-violet-600 to-fuchsia-600 px-8 py-14 text-center text-white shadow-2xl shadow-brand-600/30">
          <FileText className="absolute -left-6 -top-6 h-40 w-40 rotate-12 opacity-10" />
          <h2 className="text-3xl font-extrabold sm:text-4xl">Ready to build your next presentation?</h2>
          <p className="mx-auto mt-3 max-w-xl text-brand-100">Upload a PDF and get two editable PowerPoint decks in minutes.</p>
          <Button to="/upload" size="lg" variant="secondary" className="mt-8 border-0">
            Start converting <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      </section>
    </>
  )
}
