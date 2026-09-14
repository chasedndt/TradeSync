import { useSearchParams } from 'react-router-dom'
import { useEvidenceCards } from '../api/hooks/useEvidenceCards'
import { useRegimeLabOverview } from '../api/hooks/useRegimeLab'
import { useTrackedSymbols } from '../api/hooks/useTrackedSymbols'
import { ChallengerPanel } from '../components/regime-lab/ChallengerPanel'
import { FeatureTable } from '../components/regime-lab/FeatureTable'
import { HealthStrip } from '../components/regime-lab/HealthStrip'
import { LabHeader } from '../components/regime-lab/LabHeader'
import { RecentExperiments } from '../components/regime-lab/RecentExperiments'
import { SlowStatistics } from '../components/regime-lab/SlowStatistics'
import styles from './RegimeLab.module.css'

/**
 * Regime Lab: the live feature evidence behind the baseline rulebook, and
 * challenger weights judged by replaying the scorer's stored decisions. Each
 * section loads and fails on its own; the slow statistics sit last, collapsed.
 */
export function RegimeLab() {
  const { symbols } = useTrackedSymbols()
  const [params, setParams] = useSearchParams()
  const symbol = params.get('symbol') ?? symbols[0] ?? 'BTC-PERP'
  const overview = useRegimeLabOverview(symbol)
  const cards = useEvidenceCards(symbol)

  const chooseSymbol = (next: string) => {
    const nextParams = new URLSearchParams(params)
    nextParams.set('symbol', next)
    setParams(nextParams, { replace: true })
  }

  return (
    <div className={styles.page}>
      <LabHeader symbol={symbol} symbols={symbols} onSymbol={chooseSymbol} overview={overview} />
      <HealthStrip overview={overview} />
      <FeatureTable symbol={symbol} overview={overview} cards={cards} />
      <ChallengerPanel symbol={symbol} overview={overview.data} overviewError={overview.error} />
      <RecentExperiments />
      <SlowStatistics symbol={symbol} />
    </div>
  )
}
