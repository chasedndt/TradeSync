interface PreviewFormProps {
  sizeUsd: number
  onSizeUsdChange: (value: number) => void
  venue: string
  onVenueChange: (venue: string) => void
  onPreview: () => void
  isPending: boolean
}

export function PreviewForm({ sizeUsd, onSizeUsdChange, venue, onVenueChange, onPreview, isPending }: PreviewFormProps) {
  return (
    <div className="card mb-4 bg-gray-800/50">
      <h4 className="text-sm font-medium text-gray-400 mb-4">Set Execution Parameters</h4>
      <div className="space-y-4">
        <div>
          <label className="block text-xs text-gray-400 mb-1.5 uppercase font-bold">Position Size (USD)</label>
          <div className="flex items-center gap-2">
            <input
              type="number"
              value={sizeUsd}
              onChange={(e) => onSizeUsdChange(Number(e.target.value))}
              className="input flex-1 text-lg font-mono"
            />
            <span className="text-gray-500 font-bold">$</span>
          </div>
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1.5 uppercase font-bold">Target Venue</label>
          <div className="grid grid-cols-1 gap-2">
            <button
              onClick={() => onVenueChange('hyperliquid')}
              className={`px-3 py-2 rounded border text-sm font-medium transition-all ${venue === 'hyperliquid' ? 'border-blue-500 bg-blue-500/10 text-blue-400' : 'border-gray-700 bg-gray-900 text-gray-400 hover:border-gray-600'}`}
            >
              Hyperliquid
            </button>
          </div>
        </div>
        <button
          onClick={onPreview}
          disabled={isPending}
          className="btn btn-primary w-full py-3 text-base shadow-lg shadow-blue-500/20 active:translate-y-0.5"
        >
          {isPending ? 'Verifying Risk...' : 'REQUEST EXECUTION PREVIEW'}
        </button>
      </div>
    </div>
  )
}
