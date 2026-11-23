import { useEffect, useState } from 'react'
import { api } from '../services/api'

let cache = null

/** Fetch presentation templates once and share them across components. */
export function useTemplates() {
  const [templates, setTemplates] = useState(cache || [])
  const [error, setError] = useState(null)

  useEffect(() => {
    if (cache) return
    let alive = true
    api
      .templates()
      .then((t) => {
        cache = t
        if (alive) setTemplates(t)
      })
      .catch((e) => alive && setError(e))
    return () => {
      alive = false
    }
  }, [])

  return { templates, error, byId: Object.fromEntries(templates.map((t) => [t.id, t])) }
}
