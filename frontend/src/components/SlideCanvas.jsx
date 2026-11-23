import { ArrowRight } from 'lucide-react'
import { pageLabel } from '../utils/format'

const FALLBACK = {
  id: 'modern_education',
  font: 'Trebuchet MS',
  colors: {
    background: 'FFFFFF', surface: 'EEF2FF', primary: '4F46E5', primary_dark: '3730A3', accent: 'F59E0B',
    text: '1E293B', muted: '64748B', on_primary: 'FFFFFF', border: 'C7D2FE',
  },
}

const hex = (c) => `#${c}`
/** cqw helper: size expressed relative to slide width (13.333in => 100cqw). */
const u = (pt) => `${(pt / 960) * 100}cqw` // 960pt = slide width

function Header({ title, eyebrow, c, font }) {
  const size = title.length <= 48 ? 32 : title.length <= 62 ? 27 : title.length <= 80 ? 23 : 20
  return (
    <div style={{ position: 'absolute', left: u(47), right: u(47), top: u(23) }}>
      {eyebrow && (
        <div style={{ color: hex(c.primary), fontSize: u(11), fontWeight: 700, letterSpacing: '0.06em' }}>
          {eyebrow.toUpperCase()}
        </div>
      )}
      <div style={{ color: hex(c.text), fontSize: u(size), fontWeight: 700, fontFamily: font, lineHeight: 1.15, marginTop: u(eyebrow ? 4 : 18) }}>
        {title}
      </div>
      <div style={{ width: u(65), height: u(5), background: hex(c.accent), marginTop: u(8), borderRadius: 2 }} />
    </div>
  )
}

function Footer({ slide, index, total, docName, c, dark, left = 47 }) {
  const color = dark ? '#F9FAFB' : hex(c.muted)
  const src = pageLabel(slide.source_pages)
  return (
    <div style={{ position: 'absolute', left: u(left), right: u(47), bottom: u(14), display: 'flex', justifyContent: 'space-between', color, fontSize: u(10) }}>
      <span className="truncate" style={{ maxWidth: '75%' }}>
        {docName}
        {src && `  •  Source: ${src}`}
      </span>
      <span>
        {index} / {total}
      </span>
    </div>
  )
}

function Bullets({ items, c, color, bulletColor, size }) {
  const total = items.join(' ').length
  const fs = size || (total > 700 ? 14 : total > 450 ? 16 : total > 250 ? 19 : 22)
  return (
    <ul style={{ fontSize: u(fs), color: color || hex(c.text), lineHeight: 1.35 }}>
      {items.map((b, i) => (
        <li key={i} style={{ display: 'flex', gap: u(10), marginBottom: u(fs * 0.55) }}>
          <span style={{ color: bulletColor || hex(c.primary), fontWeight: 700 }}>•</span>
          <span>{b}</span>
        </li>
      ))}
    </ul>
  )
}

function Card({ c, children, style }) {
  return (
    <div style={{ background: hex(c.surface), border: `1px solid ${hex(c.border)}`, borderRadius: u(10), position: 'relative', ...style }}>
      {children}
    </div>
  )
}

function Badge({ n, c }) {
  return (
    <div style={{ width: u(40), height: u(40), borderRadius: '50%', background: hex(c.primary), color: hex(c.on_primary), display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: u(15), flexShrink: 0 }}>
      {n}
    </div>
  )
}

const BODY = { position: 'absolute', left: u(47), right: u(47), top: u(125), bottom: u(45) }

function ContentBody({ slide, c }) {
  const items = slide.bullets || []
  if (items.length >= 2 && items.length <= 3 && items.every((b) => b.length <= 130)) {
    return (
      <div style={{ ...BODY, top: u(140), display: 'flex', gap: u(25), alignItems: 'flex-start' }}>
        {items.map((b, i) => (
          <Card key={i} c={c} style={{ flex: 1, padding: u(22), minHeight: u(170) }}>
            <Badge n={i + 1} c={c} />
            <div style={{ marginTop: u(16), fontSize: u(18), color: hex(c.text), lineHeight: 1.35 }}>{b}</div>
          </Card>
        ))}
      </div>
    )
  }
  return (
    <div style={BODY}>
      <Bullets items={items} c={c} />
    </div>
  )
}

export default function SlideCanvas({ slide, index, total, template, docName = '', className = '' }) {
  const t = template || FALLBACK
  const c = t.colors
  const font = `"${t.font}", ${t.font === 'Georgia' ? 'serif' : 'sans-serif'}`
  const darkHero = t.id !== 'minimal_white'
  const common = { slide, index, total, docName, c }
  let body = null
  let bg = hex(c.background)

  switch (slide.type) {
    case 'title': {
      bg = darkHero ? hex(c.primary_dark) : hex(c.background)
      const fg = darkHero ? '#F9FAFB' : hex(c.text)
      body = (
        <>
          {darkHero ? (
            <>
              <div style={{ position: 'absolute', right: u(-100), top: u(-86), width: u(432), height: u(432), borderRadius: '50%', background: hex(c.primary) }} />
              <div style={{ position: 'absolute', right: u(-72), top: u(331), width: u(245), height: u(245), borderRadius: '50%', background: hex(c.accent) }} />
            </>
          ) : (
            <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: u(25), background: hex(c.primary) }} />
          )}
          <div style={{ position: 'absolute', left: u(65), top: u(108), width: u(605) }}>
            <div style={{ color: darkHero ? hex(c.accent) : hex(c.primary), fontSize: u(12), fontWeight: 700, letterSpacing: '0.08em' }}>SMARTSLIDE AI</div>
          </div>
          <div style={{ position: 'absolute', left: u(65), top: u(144), width: u(605), height: u(187), display: 'flex', alignItems: 'flex-end' }}>
            <div style={{ color: fg, fontFamily: font, fontWeight: 700, lineHeight: 1.1, fontSize: u(slide.title.length < 45 ? 44 : slide.title.length < 80 ? 36 : 30) }}>{slide.title}</div>
          </div>
          <div style={{ position: 'absolute', left: u(68), top: u(345), width: u(86), height: u(6), background: hex(c.accent) }} />
          {slide.subtitle && (
            <div style={{ position: 'absolute', left: u(65), top: u(364), width: u(605), color: darkHero ? '#E5E7EB' : hex(c.muted), fontSize: u(18) }}>{slide.subtitle}</div>
          )}
          <div style={{ position: 'absolute', left: u(65), bottom: u(22), color: darkHero ? '#E5E7EB' : hex(c.muted), fontSize: u(10) }}>Source: {docName}</div>
        </>
      )
      break
    }
    case 'section':
      bg = t.id === 'dark_academic' ? hex(c.primary_dark) : hex(c.surface)
      body = (
        <>
          <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: u(310), background: hex(c.primary), display: 'flex', alignItems: 'center', paddingLeft: u(50) }}>
            <span style={{ color: hex(c.on_primary), fontSize: u(96), fontWeight: 800, fontFamily: font }}>
              {String(slide._sectionNo || 1).padStart(2, '0')}
            </span>
          </div>
          <div style={{ position: 'absolute', left: u(360), right: u(50), top: u(150) }}>
            <div style={{ color: hex(c.primary), fontSize: u(13), fontWeight: 700, letterSpacing: '0.08em' }}>SECTION</div>
            <div style={{ color: hex(c.text), fontSize: u(slide.title.length < 40 ? 40 : 32), fontWeight: 700, fontFamily: font, lineHeight: 1.15, marginTop: u(12) }}>{slide.title}</div>
            {slide.subtitle && <div style={{ color: hex(c.muted), fontSize: u(16), marginTop: u(18) }}>{slide.subtitle}</div>}
          </div>
          <Footer {...common} left={360} />
        </>
      )
      break
    case 'definition':
      body = (
        <>
          <Header title={slide.title} eyebrow="Key terms" c={c} font={font} />
          <div style={{ ...BODY, display: 'flex', flexDirection: 'column', gap: u(14) }}>
            {(slide.definitions || []).slice(0, 4).map((d, i) => (
              <Card key={i} c={c} style={{ display: 'flex', alignItems: 'center', padding: `${u(14)} ${u(20)}`, borderLeft: `${u(8)} solid ${hex(c.primary)}`, minHeight: u(70) }}>
                <div style={{ width: u(210), flexShrink: 0, color: hex(c.primary), fontWeight: 700, fontSize: u(18), fontFamily: font }}>{d.term}</div>
                <div style={{ color: hex(c.text), fontSize: u(d.definition.length > 200 ? 13 : 16), lineHeight: 1.35 }}>{d.definition}</div>
              </Card>
            ))}
          </div>
          <Footer {...common} />
        </>
      )
      break
    case 'comparison': {
      const cmp = slide.comparison || { left_title: 'A', right_title: 'B', left: [], right: [] }
      const rows = Math.max(cmp.left.length, cmp.right.length, 1)
      body = (
        <>
          <Header title={slide.title} eyebrow="Comparison" c={c} font={font} />
          <div style={{ ...BODY, top: u(130) }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: u(15), color: hex(c.text) }}>
              <thead>
                <tr>
                  {[cmp.left_title, cmp.right_title].map((h, i) => (
                    <th key={i} style={{ background: i === 0 ? hex(c.primary) : t.id === 'dark_academic' ? '#374151' : hex(c.primary_dark), color: i === 0 || t.id !== 'dark_academic' ? hex(c.on_primary) : hex(c.text), textAlign: 'left', padding: u(12), fontSize: u(17), width: '50%' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Array.from({ length: rows }).map((_, r) => (
                  <tr key={r} style={{ background: r % 2 === 0 ? hex(c.surface) : 'transparent' }}>
                    <td style={{ padding: u(12), verticalAlign: 'top' }}>{cmp.left[r] || ''}</td>
                    <td style={{ padding: u(12), verticalAlign: 'top' }}>{cmp.right[r] || ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Footer {...common} />
        </>
      )
      break
    }
    case 'process': {
      const steps = (slide.steps?.length ? slide.steps : slide.bullets || []).slice(0, 6)
      const perRow = steps.length <= 4 ? steps.length : Math.ceil(steps.length / 2)
      body = (
        <>
          <Header title={slide.title} eyebrow="Process" c={c} font={font} />
          <div style={{ ...BODY, top: u(140), display: 'grid', gridTemplateColumns: `repeat(${perRow}, 1fr)`, columnGap: u(40), rowGap: u(24) }}>
            {steps.map((s, i) => (
              <div key={i} style={{ position: 'relative' }}>
                <Card c={c} style={{ padding: u(18), minHeight: u(steps.length > 4 ? 140 : 220), height: '100%' }}>
                  <Badge n={i + 1} c={c} />
                  <div style={{ marginTop: u(12), fontSize: u(steps.length > 4 ? 13 : 15), color: hex(c.text), lineHeight: 1.35 }}>{s}</div>
                </Card>
                {(i + 1) % perRow !== 0 && i < steps.length - 1 && (
                  <ArrowRight style={{ position: 'absolute', right: u(-34), top: '45%', width: u(28), height: u(28), color: hex(c.accent) }} strokeWidth={3} />
                )}
              </div>
            ))}
          </div>
          <Footer {...common} />
        </>
      )
      break
    }
    case 'takeaways': {
      const items = (slide.bullets || []).slice(0, 6)
      body = (
        <>
          <Header title={slide.title} eyebrow="Remember" c={c} font={font} />
          <div style={{ ...BODY, display: 'grid', gridTemplateColumns: items.length <= 2 ? '1fr' : '1fr 1fr', gap: u(16), alignContent: 'start' }}>
            {items.map((b, i) => (
              <Card key={i} c={c} style={{ display: 'flex', alignItems: 'center', gap: u(16), padding: `${u(14)} ${u(18)}`, minHeight: u(80) }}>
                <span style={{ color: hex(c.accent), fontWeight: 800, fontSize: u(26), fontFamily: font }}>{String(i + 1).padStart(2, '0')}</span>
                <span style={{ color: hex(c.text), fontSize: u(15), lineHeight: 1.35 }}>{b}</span>
              </Card>
            ))}
          </div>
          <Footer {...common} />
        </>
      )
      break
    }
    case 'conclusion': {
      bg = darkHero ? hex(c.primary_dark) : hex(c.background)
      const fg = darkHero ? '#F9FAFB' : hex(c.text)
      body = (
        <>
          {darkHero ? (
            <div style={{ position: 'absolute', left: u(730), top: u(310), width: u(331), height: u(331), borderRadius: '50%', background: hex(c.primary) }} />
          ) : (
            <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: u(25), background: hex(c.primary) }} />
          )}
          <div style={{ position: 'absolute', left: u(65), right: u(65), top: u(43) }}>
            <div style={{ color: hex(c.accent), fontSize: u(12), fontWeight: 700, letterSpacing: '0.08em' }}>CONCLUSION</div>
            <div style={{ color: fg, fontSize: u(36), fontWeight: 700, fontFamily: font, marginTop: u(8) }}>{slide.title}</div>
            <div style={{ marginTop: u(40) }}>
              <Bullets items={slide.bullets || []} c={c} color={fg} bulletColor={hex(c.accent)} />
            </div>
          </div>
          <div style={{ position: 'absolute', left: u(65), top: u(425), color: hex(c.accent), fontWeight: 700, fontSize: u(20), fontFamily: font }}>Thank you • Questions?</div>
          <Footer {...common} dark={darkHero} />
        </>
      )
      break
    }
    case 'example':
      body = (
        <>
          <Header title={slide.title} eyebrow="Examples" c={c} font={font} />
          <ContentBody slide={slide} c={c} />
          <Footer {...common} />
        </>
      )
      break
    default:
      body = (
        <>
          <Header title={slide.title} c={c} font={font} />
          <ContentBody slide={slide} c={c} />
          <Footer {...common} />
        </>
      )
  }

  return (
    <div className={`slide-canvas relative aspect-video w-full overflow-hidden select-none ${className}`} style={{ background: bg, fontFamily: '"Calibri", "Inter", sans-serif' }}>
      {body}
    </div>
  )
}
