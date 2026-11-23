import { useCallback, useEffect, useState } from 'react'
import { ThemeContext } from './theme'

function readInitial() {
  try {
    return localStorage.getItem('smartslide-theme') === 'dark'
  } catch {
    return false
  }
}

export function ThemeProvider({ children }) {
  const [dark, setDark] = useState(readInitial)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    try {
      localStorage.setItem('smartslide-theme', dark ? 'dark' : 'light')
    } catch {
      /* storage unavailable: theme simply won't persist */
    }
  }, [dark])

  const toggle = useCallback(() => setDark((d) => !d), [])
  return <ThemeContext.Provider value={{ dark, toggle }}>{children}</ThemeContext.Provider>
}
