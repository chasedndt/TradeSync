import { useState, useMemo } from 'react'
import { useOpportunities } from '../api/hooks'
import { OpportunityCard, DryRunBanner } from '../components'
import { Search, Filter } from 'lucide-react'

const statusOptions = ['new', 'previewed', 'executed', 'expired']
const timeframeOptions = ['all', '1m', '5m', '15m', '1h', '4h', '1d']

export function Opportunities() {
  const [status, setStatus] = useState('new')
  const [timeframe, setTimeframe] = useState('all')
  const [search, setSearch] = useState('')
  const [dedup, setDedup] = useState(true)

  const { data: opportunities, isLoading, error } = useOpportunities(status, 100)

  const filtered = useMemo(() => {
    if (!opportunities) return []

    let list = opportunities.filter(o =>
      (timeframe === 'all' || o.timeframe === timeframe) &&
      (o.symbol.toLowerCase().includes(search.toLowerCase()))
    )

    if (dedup) {
      // Keep only the newest for each (symbol, timeframe, direction)
      const seen = new Set()
      list = list.filter(o => {
        const key = `${o.symbol}-${o.timeframe}-${o.dir}`
        if (seen.has(key)) return false
        seen.add(key)
        return true
      })
    }

    return list
  }, [opportunities, timeframe, search, dedup])

  return (
    <div className="space-y-6">
      {/* Dry Run / Mode Banner */}
      <DryRunBanner variant="inline" />

      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <h2 className="text-xl font-bold">Market Opportunities</h2>
        <div className="flex flex-wrap gap-2">
          {statusOptions.map((s) => (
            <button
              key={s}
              onClick={() => setStatus(s)}
              className={`px-3 py-1 rounded text-sm capitalize ${status === s
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* Filters Bar */}
      <div className="flex flex-col md:flex-row gap-4 bg-gray-900/50 p-4 rounded-lg border border-gray-800">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" size={16} />
          <input
            type="text"
            placeholder="Search symbol (e.g. BTC)..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="input w-full pl-10"
          />
        </div>

        <div className="flex items-center gap-2">
          <Filter size={16} className="text-gray-500" />
          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            className="input text-sm bg-gray-800 border-gray-700"
          >
            {timeframeOptions.map(tf => (
              <option key={tf} value={tf}>{tf.toUpperCase()}</option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2 text-sm text-gray-400">
          <input
            type="checkbox"
            id="dedup"
            checked={dedup}
            onChange={(e) => setDedup(e.target.checked)}
            className="rounded border-gray-700 bg-gray-800 text-blue-600 focus:ring-blue-500"
          />
          <label htmlFor="dedup">Deduplicate</label>
        </div>
      </div>

      {isLoading && <div className="text-gray-400">Scanning data streams...</div>}
      {error && <div className="text-red-400">Error loading opportunities</div>}

      {!isLoading && filtered.length === 0 && (
        <div className="card text-center py-12 text-gray-500 border-dashed">
          No opportunities match your current filters.
        </div>
      )}

      {filtered.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {filtered.map((opp) => (
            <OpportunityCard key={opp.id} opportunity={opp} />
          ))}
        </div>
      )}
    </div>
  )
}
