import { useEffect, useRef, useState } from 'react'
import { placesApi } from '../services/api'
import type { GeoLocation, PlaceResult } from '../types'

interface Props {
  placeholder?: string
  value: string                    // text in the box
  selected: GeoLocation | null     // the confirmed place (null while the user is typing)
  onTextChange: (text: string) => void
  onSelect: (loc: GeoLocation) => void
  className?: string
  dark?: boolean
}

const REGION_KINDS = new Set(['state', 'country', 'region'])

/**
 * India-wide autocomplete (via the backend's /api/places/search).
 * Typing clears the previously selected coordinates, so a trip can never be
 * planned with text that no longer matches the chosen place.
 */
export default function LocationSearch({ placeholder = 'Search a city or address…', value, selected, onTextChange,
  onSelect, className = '' }: Props) {
  const [results, setResults] = useState<PlaceResult[]>([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [active, setActive] = useState(-1)
  const [error, setError] = useState<string | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const controller = useRef<AbortController | null>(null)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => () => { timer.current && clearTimeout(timer.current); controller.current?.abort() }, [])

  useEffect(() => {
    const onDown = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [])

  const runSearch = (q: string) => {
    controller.current?.abort()
    if (q.trim().length < 2) { setResults([]); setOpen(false); setLoading(false); return }
    const ctrl = new AbortController()
    controller.current = ctrl
    setLoading(true)
    setError(null)
    placesApi.search(q, ctrl.signal)
      .then(r => { if (!ctrl.signal.aborted) { setResults(r); setOpen(true); setActive(-1) } })
      .catch(e => { if (!ctrl.signal.aborted) { setResults([]); setError(e.message || 'Search failed'); setOpen(true) } })
      .finally(() => { if (!ctrl.signal.aborted) setLoading(false) })
  }

  const handleChange = (text: string) => {
    onTextChange(text)
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => runSearch(text), 400)
  }

  const choose = (r: PlaceResult) => {
    if (REGION_KINDS.has(r.kind)) return
    setOpen(false)
    setResults([])
    onSelect({ label: r.label, lat: r.lat, lon: r.lon })
  }

  const handleKey = (e: React.KeyboardEvent) => {
    if (!open || results.length === 0) return
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive(a => Math.min(a + 1, results.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(a => Math.max(a - 1, 0)) }
    else if (e.key === 'Enter') { e.preventDefault(); const r = results[active >= 0 ? active : 0]; if (r) choose(r) }
    else if (e.key === 'Escape') setOpen(false)
  }

  return (
    <div ref={box} className={`relative ${className}`}>
      <div className="relative">
        <input
          type="text"
          className={`w-full px-4 py-3 pr-10 border rounded-xl bg-white text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-green-500 transition-all ${
            value && !selected ? 'border-amber-300' : 'border-gray-200'}`}
          placeholder={placeholder}
          value={value}
          onChange={e => handleChange(e.target.value)}
          onKeyDown={handleKey}
          onFocus={() => results.length > 0 && setOpen(true)}
          autoComplete="off"
          role="combobox"
          aria-expanded={open}
          aria-autocomplete="list"
        />
        <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none">
          {loading ? (
            <div className="w-4 h-4 border-2 border-green-500 border-t-transparent rounded-full animate-spin" />
          ) : selected ? (
            <svg className="w-4 h-4 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          ) : (
            <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          )}
        </div>
      </div>
      {value && !selected && !open && !loading && (
        <p className="mt-1 text-xs text-amber-600">Pick a place from the suggestions.</p>
      )}
      {open && (
        <ul className="absolute z-[1000] left-0 right-0 mt-1 bg-white border border-gray-200 rounded-xl shadow-xl overflow-hidden max-h-72 overflow-y-auto" role="listbox">
          {error && <li className="px-4 py-3 text-sm text-red-600">{error}</li>}
          {!error && results.length === 0 && <li className="px-4 py-3 text-sm text-gray-500">No places found in India.</li>}
          {results.map((r, i) => {
            const region = REGION_KINDS.has(r.kind)
            return (
              <li key={`${r.lat},${r.lon},${i}`} role="option" aria-selected={i === active}>
                <button
                  type="button"
                  disabled={region}
                  className={`w-full text-left px-4 py-2.5 border-b border-gray-50 last:border-0 transition-colors ${
                    region ? 'cursor-not-allowed opacity-60' : i === active ? 'bg-green-50' : 'hover:bg-green-50'}`}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => choose(r)}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium text-gray-900 truncate">{r.label}</span>
                    <span className="text-[10px] uppercase tracking-wide text-gray-400 shrink-0">{r.kind}</span>
                  </div>
                  {region && <div className="text-xs text-amber-600">This is a {r.kind} - choose a city or town in it.</div>}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
