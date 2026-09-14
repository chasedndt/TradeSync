// Map reason codes to user-friendly messages
export const reasonCodeExplanations: Record<string, { title: string; fix?: string }> = {
  EXPIRED: {
    title: 'Opportunity Expired',
    fix: 'The opportunity window has closed. Wait for a new signal.'
  },
  SIZE_TOO_SMALL: {
    title: 'Position Size Too Small',
    fix: 'Increase the position size to meet the minimum requirement.'
  },
  SIZE_TOO_LARGE: {
    title: 'Position Size Too Large',
    fix: 'Reduce the position size to stay within risk limits.'
  },
  QUALITY_TOO_LOW: {
    title: 'Signal Quality Below Threshold',
    fix: 'Wait for a higher quality signal or adjust min_quality policy.'
  },
  BLACKLISTED: {
    title: 'Symbol Blacklisted',
    fix: 'This symbol is on the blacklist. Remove it from risk policies to trade.'
  },
  COOLDOWN_ACTIVE: {
    title: 'Cooldown Period Active',
    fix: 'Recent activity on this symbol. Wait for cooldown to expire.'
  },
  DAILY_LIMIT_REACHED: {
    title: 'Daily Notional Limit Reached',
    fix: 'You have reached your daily trading limit. Resume tomorrow.'
  },
  SIGNAL_STALE: {
    title: 'Signal Data Stale',
    fix: 'The underlying signal is too old. Wait for fresh data.'
  }
}
