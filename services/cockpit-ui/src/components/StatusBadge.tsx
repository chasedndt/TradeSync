interface StatusBadgeProps {
  status: string
}

const statusColors: Record<string, string> = {
  new: 'bg-blue-900 text-blue-200',
  previewed: 'bg-yellow-900 text-yellow-200',
  executed: 'bg-green-900 text-green-200',
  expired: 'bg-gray-700 text-gray-400',
  placed: 'bg-green-900 text-green-200',
  rejected: 'bg-red-900 text-red-200',
  error: 'bg-red-900 text-red-200',
  ok: 'bg-green-900 text-green-200',
  degraded: 'bg-yellow-900 text-yellow-200',
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const colorClass = statusColors[status.toLowerCase()] || 'bg-gray-700 text-gray-300'
  
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${colorClass}`}>
      {status}
    </span>
  )
}
