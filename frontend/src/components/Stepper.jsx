import { Check } from 'lucide-react'

const STEPS = ['Upload', 'Configure', 'Process', 'Preview & edit', 'Download']

export default function Stepper({ current = 0 }) {
  return (
    <ol className="mx-auto mb-10 flex max-w-3xl items-center" aria-label="Progress">
      {STEPS.map((label, i) => {
        const done = i < current
        const active = i === current
        return (
          <li key={label} className={`flex items-center ${i < STEPS.length - 1 ? 'flex-1' : ''}`}>
            <div className="flex flex-col items-center gap-1.5">
              <span
                className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold transition ${
                  done
                    ? 'bg-brand-600 text-white'
                    : active
                      ? 'bg-brand-600 text-white ring-4 ring-brand-500/20'
                      : 'bg-slate-200 text-slate-500 dark:bg-slate-800 dark:text-slate-400'
                }`}
                aria-current={active ? 'step' : undefined}
              >
                {done ? <Check className="h-4 w-4" /> : i + 1}
              </span>
              <span className={`hidden text-xs font-medium sm:block ${active ? 'text-brand-700 dark:text-brand-300' : 'text-slate-500'}`}>
                {label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div className={`mx-2 mb-0 h-0.5 flex-1 rounded sm:mb-5 ${done ? 'bg-brand-600' : 'bg-slate-200 dark:bg-slate-800'}`} />
            )}
          </li>
        )
      })}
    </ol>
  )
}
