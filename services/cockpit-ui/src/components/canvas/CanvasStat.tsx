export function Stat({ label, value, tone }: { label: string; value: string; tone?: 'good' | 'bad' }) {
  return (
    <div>
      <span className="metric-sub" style={{ display: 'block' }}>
        {label}
      </span>
      <span className={`metric-main ${tone ? `tone-${tone}` : ''}`}>{value}</span>
    </div>
  )
}
