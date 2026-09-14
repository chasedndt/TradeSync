import { useEffect, useState } from 'react'
import { DEFAULT_STYLE, isDrawingStyle } from './shapes'
import type { DrawingStyle } from './types'

const STORAGE_KEY = 'tradesync.canvas.drawings'

interface DrawingPrefs {
  /** The last style chosen; new drawings use it. */
  style: DrawingStyle
  hidden: boolean
  locked: boolean
}

const DEFAULTS: DrawingPrefs = { style: DEFAULT_STYLE, hidden: false, locked: false }

function load(): DrawingPrefs {
  try {
    const stored: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null')
    if (!stored || typeof stored !== 'object') return DEFAULTS
    const { style, hidden, locked } = stored as Record<string, unknown>
    return { style: isDrawingStyle(style) ? style : DEFAULT_STYLE, hidden: hidden === true, locked: locked === true }
  } catch {
    return DEFAULTS
  }
}

/** The last chosen style, and whether drawings are hidden or locked. Remembered in this browser only. */
export function useDrawingPrefs() {
  const [prefs, setPrefs] = useState(load)

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs))
    } catch {
      // Storage can be unavailable (a private window); the choice lasts for this visit.
    }
  }, [prefs])

  const change = (changes: Partial<DrawingPrefs>) => setPrefs((current) => ({ ...current, ...changes }))
  return { ...prefs, change }
}
