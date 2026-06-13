import { useState } from 'react'

interface NominatimResult {
  lat: string
  lon: string
  display_name: string
}

interface Props {
  onSelect: (lat: number, lon: number, label: string) => void
  disabled?: boolean
}

export function LocationSearch({ onSelect, disabled }: Props) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<NominatimResult[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function search() {
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    try {
      const url = new URL('https://nominatim.openstreetmap.org/search')
      url.searchParams.set('q', query)
      url.searchParams.set('format', 'json')
      url.searchParams.set('limit', '5')
      url.searchParams.set('countrycodes', 'in')
      const res = await fetch(url.toString(), {
        headers: { Accept: 'application/json' },
      })
      if (!res.ok) throw new Error('Search failed')
      setResults((await res.json()) as NominatimResult[])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed')
      setResults([])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="border-b border-stone-200 bg-white p-4">
      <label className="flex flex-col gap-2 text-sm">
        <span className="font-medium text-stone-700">Find location (India)</span>
        <span className="text-xs text-stone-500">Search via Nominatim · map shows Google satellite imagery</span>
        <div className="flex gap-2">
          <input
            className="flex-1 rounded-lg border border-stone-300 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-200"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && search()}
            placeholder="Village, tehsil, or district"
            disabled={disabled}
          />
          <button
            type="button"
            onClick={search}
            disabled={disabled || loading || !query.trim()}
            className="rounded-lg bg-stone-700 px-3 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:bg-stone-300"
          >
            {loading ? '…' : 'Search'}
          </button>
        </div>
      </label>
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      {results.length > 0 && (
        <ul className="mt-2 max-h-36 overflow-y-auto rounded-lg border border-stone-200 bg-stone-50 text-sm">
          {results.map((r) => (
            <li key={`${r.lat}-${r.lon}`}>
              <button
                type="button"
                className="w-full px-3 py-2 text-left hover:bg-amber-50"
                onClick={() => {
                  onSelect(Number(r.lat), Number(r.lon), r.display_name)
                  setResults([])
                  setQuery(r.display_name.split(',')[0] ?? query)
                }}
              >
                {r.display_name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
