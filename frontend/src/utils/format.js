export function formatBytes(bytes) {
  if (!bytes && bytes !== 0) return ''
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let n = bytes
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024
    i++
  }
  return `${n.toFixed(n < 10 && i > 0 ? 1 : 0)} ${units[i]}`
}

export function pageLabel(pages) {
  if (!pages || pages.length === 0) return ''
  const sorted = [...new Set(pages)].sort((a, b) => a - b)
  const ranges = []
  let start = sorted[0]
  let prev = sorted[0]
  for (const p of sorted.slice(1)) {
    if (p === prev + 1) {
      prev = p
      continue
    }
    ranges.push(start === prev ? `${start}` : `${start}–${prev}`)
    start = prev = p
  }
  ranges.push(start === prev ? `${start}` : `${start}–${prev}`)
  return (sorted.length === 1 ? 'p. ' : 'pp. ') + ranges.join(', ')
}

export const SLIDE_TYPE_LABELS = {
  title: 'Title',
  section: 'Section',
  content: 'Content',
  definition: 'Definitions',
  comparison: 'Comparison',
  process: 'Process',
  example: 'Examples',
  takeaways: 'Key takeaways',
  conclusion: 'Conclusion',
  diagram: 'Diagram',
}
