interface RiskBadgeProps {
  allowed: boolean
  reason?: string
}

export function RiskBadge({ allowed, reason }: RiskBadgeProps) {
  return (
    <div className={`px-3 py-1 rounded text-sm ${
      allowed ? 'bg-green-900 text-green-200' : 'bg-red-900 text-red-200'
    }`}>
      <span className="font-medium">{allowed ? 'ALLOWED' : 'BLOCKED'}</span>
      {reason && <span className="ml-2 opacity-75">- {reason}</span>}
    </div>
  )
}
