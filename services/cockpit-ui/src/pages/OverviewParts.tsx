import { Fragment } from 'react'
import { Bank, GlobeHemisphereWest, Waves } from '../components/icons'
import { formatAge, formatCompactUsd, formatPercent, formatUsd } from '../components/home/format'
import type { useContextOverview } from '../api/hooks'

export function ContextPanel({ context }: { context: ReturnType<typeof useContextOverview>['data'] }) {
  const coin = context?.providers.coingecko
  const llama = context?.providers.defillama
  const fred = context?.providers.fred
  const assets = coin?.data.assets || {}
  return (
    <section className="panel context-panel" aria-labelledby="context-title">
      <div id="context-title" className="context-title">Context only <span>(non-authoritative)</span></div>
      <div className="context-grid">
        <div className="context-block">
          <div className="context-provider"><GlobeHemisphereWest size={18} className="tone-good" weight="duotone" />CoinGecko <span>(spot reference)</span></div>
          <div className="context-assets">
            {['BTC', 'ETH', 'SOL'].map((symbol) => (
              <Fragment key={symbol}>
                <span>{symbol}</span>
                <span>{formatUsd(assets[symbol]?.price_usd, assets[symbol]?.price_usd < 1000 ? 2 : 0)}</span>
                <span className={(assets[symbol]?.change_24h_pct ?? 0) >= 0 ? 'tone-good' : 'tone-bad'}>{formatPercent(assets[symbol]?.change_24h_pct)}</span>
              </Fragment>
            ))}
          </div>
          <div className="context-age">Updated {formatAge(coin?.age_seconds)}</div>
        </div>
        <div className="context-block">
          <div className="context-provider"><Waves size={18} className="tone-info" weight="duotone" />DefiLlama <span>(Hyperliquid TVL)</span></div>
          <div className="context-big">{formatCompactUsd(llama?.data.tvl_usd)}</div>
          <div className="context-age">Updated {formatAge(llama?.age_seconds)}</div>
        </div>
        <div className="context-block">
          <div className="context-provider"><Bank size={18} weight="duotone" />FRED <span>(macro reference)</span></div>
          <div className="context-big tone-dim">{fred?.status === 'healthy' ? 'Configured' : 'Not configured'}</div>
          <div className="context-age">{fred?.status === 'healthy' ? 'official release dates live' : 'free API key required'}</div>
        </div>
      </div>
    </section>
  )
}

interface HealthItemProps { name: string; state: string; detail: string; tone: 'good' | 'warn' | 'bad' | 'dim' }

export function HealthItem({ name, state, detail, tone }: HealthItemProps) {
  return (
    <div className="health-item">
      <span className="health-name">{name}</span>
      <span className={`health-state tone-${tone}`}>{state}</span>
      <span className="health-latency">{detail}</span>
    </div>
  )
}
