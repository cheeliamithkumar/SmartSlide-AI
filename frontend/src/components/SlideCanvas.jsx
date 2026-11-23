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

function Footer({ slide, index, total, c, dark, left = 47 }) {
  const color = dark ? '#F9FAFB' : hex(c.muted)
  const src = pageLabel(slide.source_pages)
  return (
    <div style={{ position: 'absolute', left: u(left), right: u(47), bottom: u(14), display: 'flex', justifyContent: 'space-between', color, fontSize: u(10) }}>
      <span className="truncate" style={{ maxWidth: '75%' }}>{src && `Source: ${src}`}</span>
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

// ---------------------------------------------------------------------------
// Diagrams (mirror pptx_builder.py). Coordinates are in points on a 960x540 slide.
// ---------------------------------------------------------------------------
const PT_W = 960
const PT_H = 540

function Lines({ lines, color, width = 2, arrow = false }) {
  const id = `ah-${color}`
  return (
    <svg viewBox={`0 0 ${PT_W} ${PT_H}`} preserveAspectRatio="none" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}>
      {arrow && (
        <defs>
          <marker id={id} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill={hex(color)} />
          </marker>
        </defs>
      )}
      {lines.map(([x1, y1, x2, y2], i) => (
        <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke={hex(color)} strokeWidth={width} markerEnd={arrow ? `url(#${id})` : undefined} />
      ))}
    </svg>
  )
}

function Box({ x, y, w, h, children, style }) {
  return (
    <div style={{ position: 'absolute', left: u(x), top: u(y), width: u(w), height: u(h), display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center', boxSizing: 'border-box', ...style }}>
      {children}
    </div>
  )
}

const fitPt = (text, max, min, boxW) => {
  const longest = Math.max(1, ...String(text).split(/\s+/).map((w) => w.length))
  for (let s = max; s >= min; s--) {
    const cpl = boxW / (s * 0.62)
    if (longest <= cpl && Math.ceil((text.length * 1.1) / cpl) <= 2) return s
  }
  return min
}

function MindMap({ diag, c, font, x = 47, y = 122, w = 866, h = 367 }) {
  const nodes = (diag.nodes || []).slice(0, 6)
  const n = Math.max(1, nodes.length)
  const cx = x + w / 2
  const cy = y + h / 2
  const cw = w * 0.27
  const ch = h * 0.22
  const nw = w * 0.23
  const nh = h * 0.17
  const rx = (w - nw) / 2
  const ry = (h - nh) / 2
  const pos = nodes.map((_, i) => {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / n
    return [cx + rx * Math.cos(a), cy + ry * Math.sin(a)]
  })
  const lineColor = c.border
  return (
    <>
      <Lines lines={pos.map(([px, py]) => [cx, cy, px, py])} color={lineColor} />
      <Box x={cx - cw / 2} y={cy - ch / 2} w={cw} h={ch} style={{ background: hex(c.primary), color: hex(c.on_primary), borderRadius: '50%', fontWeight: 700, fontFamily: font, fontSize: u(fitPt(diag.center || '', 20, 11, cw * 0.72)), padding: u(8), lineHeight: 1.15 }}>
        {diag.center}
      </Box>
      {nodes.map((nd, i) => (
        <Box key={i} x={pos[i][0] - nw / 2} y={pos[i][1] - nh / 2} w={nw} h={nh} style={{ background: hex(c.surface), border: `1.5px solid ${hex(c.primary)}`, borderRadius: u(10), color: hex(c.text), fontWeight: 700, fontSize: u(fitPt(nd.label, 15, 9, nw - 16)), padding: u(6), lineHeight: 1.2 }}>
          {nd.label}
        </Box>
      ))}
    </>
  )
}

function ConceptTree({ diag, c, font, x = 544, y = 119, w = 371, h = 367 }) {
  const nodes = (diag.nodes || []).slice(0, 6)
  const rows = Math.ceil(nodes.length / 2)
  const topH = 72
  const cw = w * 0.78
  const busY = y + 7 + topH + 22
  const gap = 18
  const nw = (w - gap) / 2
  const avail = y + h - busY - 18
  const nh = Math.min(68, (avail - 16 * (rows - 1)) / Math.max(rows, 1))
  const colX = [x + nw / 2, x + nw + gap + nw / 2]
  const lines = [[x + w / 2, y + 7 + topH, x + w / 2, busY], [colX[0], busY, nodes.length > 1 ? colX[1] : colX[0], busY]]
  const placed = nodes.map((nd, i) => {
    const r = Math.floor(i / 2)
    const col = i % 2
    const ny = busY + 18 + r * (nh + 16)
    lines.push([colX[col], r === 0 ? busY : ny - 16, colX[col], ny])
    return { nd, x: colX[col] - nw / 2, y: ny }
  })
  return (
    <>
      <Lines lines={lines} color={c.border} />
      <Box x={x + (w - cw) / 2} y={y + 7} w={cw} h={topH} style={{ background: hex(c.primary), color: hex(c.on_primary), borderRadius: u(12), fontWeight: 700, fontFamily: font, fontSize: u(fitPt(diag.center || '', 18, 11, cw - 22)), padding: u(8) }}>
        {diag.center}
      </Box>
      {placed.map((p, i) => (
        <Box key={i} x={p.x} y={p.y} w={nw} h={nh} style={{ background: hex(c.surface), border: `1.5px solid ${hex(c.primary)}`, borderRadius: u(10), color: hex(c.text), fontWeight: 700, fontSize: u(fitPt(p.nd.label, 15, 10, nw - 22)), padding: u(6) }}>
          {p.nd.label}
        </Box>
      ))}
    </>
  )
}

function Timeline({ diag, c, font, x = 47, y = 147, w = 866, h = 342 }) {
  const nodes = (diag.nodes || []).slice(0, 7)
  const n = Math.max(1, nodes.length)
  const slot = w / n
  const lineY = y + h * 0.42
  const cardW = slot - 13
  const r = 19
  return (
    <>
      <div style={{ position: 'absolute', left: u(x + slot / 2), top: u(lineY - 2), width: u(slot * (n - 1)), height: u(4), background: hex(c.accent) }} />
      {nodes.map((nd, i) => {
        const cx = x + slot * i + slot / 2
        return (
          <div key={i}>
            <Box x={cx - cardW / 2} y={y + 11} w={cardW} h={lineY - y - 47} style={{ background: hex(c.surface), border: `1px solid ${hex(c.border)}`, borderRadius: u(12), color: hex(c.text), fontWeight: 700, fontFamily: font, fontSize: u(fitPt(nd.label, 15, 9, cardW - 18)), padding: u(6), lineHeight: 1.2 }}>
              {nd.label}
            </Box>
            <div style={{ position: 'absolute', left: u(cx - 0.6), top: u(lineY - 36), width: u(1.2), height: u(36 - r), background: hex(c.border) }} />
            <Box x={cx - r} y={lineY - r} w={2 * r} h={2 * r} style={{ background: hex(c.primary), color: hex(c.on_primary), borderRadius: '50%', fontWeight: 700, fontSize: u(13) }}>
              {i + 1}
            </Box>
            {nd.detail && (
              <div style={{ position: 'absolute', left: u(cx - cardW / 2), top: u(lineY + r + 11), width: u(cardW), color: hex(c.muted), fontSize: u(11), textAlign: 'center', lineHeight: 1.3 }}>
                {nd.detail}
              </div>
            )}
          </div>
        )
      })}
    </>
  )
}

function Cycle({ steps, c, x = 47, y = 119, w = 866, h = 371 }) {
  const n = steps.length
  const cx = x + w / 2
  const cy = y + h / 2
  const nw = 252
  const nh = 94
  const rx = ((w - nw) / 2) * 0.86
  const ry = (h - nh) / 2
  const pos = steps.map((_, i) => {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / n
    return [cx + rx * Math.cos(a), cy + ry * Math.sin(a)]
  })
  const arrows = pos.map(([x1, y1], i) => {
    const [x2, y2] = pos[(i + 1) % n]
    const dx = x2 - x1
    const dy = y2 - y1
    const dist = Math.hypot(dx, dy) || 1
    const ux = dx / dist
    const uy = dy / dist
    const trim = Math.min(ux ? Math.abs(nw / 2 / ux) : Infinity, uy ? Math.abs(nh / 2 / uy) : Infinity) + 6
    return [x1 + ux * trim, y1 + uy * trim, x2 - ux * trim, y2 - uy * trim]
  })
  return (
    <>
      <Lines lines={arrows} color={c.accent} width={2.5} arrow />
      <Box x={cx - 68} y={cy - 36} w={137} h={72} style={{ background: hex(c.surface), border: `1px solid ${hex(c.border)}`, borderRadius: '50%', color: hex(c.primary), fontWeight: 700, fontSize: u(13) }}>
        ↻ Repeats
      </Box>
      {steps.map((st, i) => (
        <Box key={i} x={pos[i][0] - nw / 2} y={pos[i][1] - nh / 2} w={nw} h={nh} style={{ background: hex(c.surface), border: `1.5px solid ${hex(c.primary)}`, borderRadius: u(14), justifyContent: 'flex-start', textAlign: 'left', gap: u(10), padding: `0 ${u(10)}` }}>
          <Badge n={i + 1} c={c} />
          <span style={{ color: hex(c.text), fontSize: u(st.length > 90 ? 11 : 13), lineHeight: 1.3 }}>{st}</span>
        </Box>
      ))}
    </>
  )
}

const BODY = { position: 'absolute', left: u(47), right: u(47), top: u(125), bottom: u(45) }

function ContentBody({ slide, c, font }) {
  const items = slide.bullets || []
  if (slide.diagram?.kind === 'mindmap' && slide.diagram.nodes?.length) {
    return (
      <>
        <div style={{ ...BODY, right: 'auto', width: u(475) }}>
          <Bullets items={items} c={c} size={items.join(' ').length > 500 ? 14 : 17} />
        </div>
        <ConceptTree diag={slide.diagram} c={c} font={font} />
      </>
    )
  }
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

export default function SlideCanvas({ slide, index, total, template, className = "" }) {
  const t = template || FALLBACK
  const c = t.colors
  const font = `"${t.font}", ${t.font === 'Georgia' ? 'serif' : 'sans-serif'}`
  const darkHero = t.id !== 'minimal_white'
  const common = { slide, index, total, c }
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
          <div style={{ position: 'absolute', left: u(65), top: u(144), width: u(605), height: u(187), display: 'flex', alignItems: 'flex-end' }}>
            <div style={{ color: fg, fontFamily: font, fontWeight: 700, lineHeight: 1.1, fontSize: u(slide.title.length < 45 ? 44 : slide.title.length < 80 ? 36 : 30) }}>{slide.title}</div>
          </div>
          <div style={{ position: 'absolute', left: u(68), top: u(345), width: u(86), height: u(6), background: hex(c.accent) }} />
          {slide.subtitle && (
            <div style={{ position: 'absolute', left: u(65), top: u(364), width: u(605), color: darkHero ? '#E5E7EB' : hex(c.muted), fontSize: u(18) }}>{slide.subtitle}</div>
          )}
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
      if (slide.diagram?.kind === 'cycle' && steps.length >= 3) {
        body = (
          <>
            <Header title={slide.title} eyebrow="Cycle" c={c} font={font} />
            <Cycle steps={steps} c={c} />
            <Footer {...common} />
          </>
        )
        break
      }
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
    case 'diagram': {
      const d = slide.diagram || { kind: 'mindmap', center: slide.title, nodes: [] }
      const eyebrow = { timeline: 'Roadmap', mindmap: 'Concept map', cycle: 'Cycle', flow: 'Process' }[d.kind]
      body = (
        <>
          <Header title={slide.title} eyebrow={eyebrow} c={c} font={font} />
          {d.kind === 'timeline' && d.nodes?.length > 0 && <Timeline diag={d} c={c} font={font} />}
          {d.kind === 'mindmap' && d.nodes?.length > 0 && <MindMap diag={d} c={c} font={font} />}
          {d.kind === 'cycle' && d.nodes?.length >= 3 && <Cycle steps={d.nodes.map((nd) => nd.label)} c={c} />}
          {!(d.nodes?.length) && slide.bullets?.length > 0 && <div style={BODY}><Bullets items={slide.bullets} c={c} /></div>}
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
          <ContentBody slide={slide} c={c} font={font} />
          <Footer {...common} />
        </>
      )
      break
    default:
      body = (
        <>
          <Header title={slide.title} c={c} font={font} />
          <ContentBody slide={slide} c={c} font={font} />
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
