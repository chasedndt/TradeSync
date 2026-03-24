interface DirectionBadgeProps {
  direction: string
}

export function DirectionBadge({ direction }: DirectionBadgeProps) {
  const isLong = direction.toLowerCase() === 'long'
  
  return (
    <span className={`font-medium ${isLong ? 'text-green-400' : 'text-red-400'}`}>
      {direction.toUpperCase()}
    </span>
  )
}
