interface Props {
  symbols: readonly string[]
  intervals: readonly string[]
  symbol: string
  interval: string
  onSymbol: (next: string) => void
  onInterval: (next: string) => void
  showDepth: boolean
  onToggleDepth: () => void
  children?: React.ReactNode
}

/** Symbol, interval and the depth toggle. Drawing tools are on the rail beside the chart. */
export function CanvasToolbar({
  symbols,
  intervals,
  symbol,
  interval,
  onSymbol,
  onInterval,
  showDepth,
  onToggleDepth,
  children,
}: Props) {
  return (
    <div
      style={{
        display: 'flex',
        gap: 20,
        flexWrap: 'wrap',
        alignItems: 'center',
        marginBottom: 14,
      }}
    >
      <div style={{ display: 'flex', gap: 6 }}>
        {symbols.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => onSymbol(s)}
            className={s === symbol ? 'chip chip--active' : 'chip'}
            aria-pressed={s === symbol}
          >
            {s.replace('-PERP', '')}
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 6 }}>
        {intervals.map((i) => (
          <button
            key={i}
            type="button"
            onClick={() => onInterval(i)}
            className={i === interval ? 'chip chip--active' : 'chip'}
            aria-pressed={i === interval}
          >
            {i}
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 6 }}>
        <button
          type="button"
          className={showDepth ? 'chip chip--active' : 'chip'}
          onClick={onToggleDepth}
          aria-pressed={showDepth}
          title="Show the current order book and mark its walls on the price axis"
        >
          depth
        </button>
      </div>

      <div style={{ marginLeft: 'auto', display: 'flex', gap: 22 }}>{children}</div>
    </div>
  )
}
