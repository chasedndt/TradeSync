import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useEvidence, usePreview, useExecute, useMarketSnapshot } from '../api/hooks'
import { EvidenceTrail, PreviewPanel, DryRunBanner } from '../components'
import type { PreviewResponse, ExecutionResult, MarketSnapshotWithMicrostructure } from '../api/types'
import { calculateBiasStrength } from '../utils/metrics'
import { AlertTriangle } from 'lucide-react'
import { ExecuteResultCard } from '../components/opportunity/ExecuteResultCard'
import { ExecutionRiskBox } from '../components/opportunity/ExecutionRiskBox'
import { MarketContextCard } from '../components/opportunity/MarketContextCard'
import { OpportunityHeader } from '../components/opportunity/OpportunityHeader'
import { PreviewForm } from '../components/opportunity/PreviewForm'
import { TradePlanSkeleton } from '../components/opportunity/TradePlanSkeleton'
import { TradeSummary } from '../components/opportunity/TradeSummary'

export function OpportunityDetail() {
  const { id } = useParams<{ id: string }>()
  const { data: evidence, isLoading, error } = useEvidence(id)
  const previewMutation = usePreview()
  const executeMutation = useExecute()

  // Extract symbol for market context (fallback until evidence loads)
  const symbol = evidence?.opportunity?.symbol || ''
  const { data: marketSnapshot } = useMarketSnapshot('hyperliquid', symbol)

  const [sizeUsd, setSizeUsd] = useState(1000)
  const [venue, setVenue] = useState('hyperliquid')
  const [previewResult, setPreviewResult] = useState<PreviewResponse | null>(null)
  const [executeResult, setExecuteResult] = useState<ExecutionResult | null>(null)

  const handlePreview = async () => {
    if (!id) return
    setExecuteResult(null)
    const result = await previewMutation.mutateAsync({
      opportunity_id: id,
      size_usd: sizeUsd,
      venue,
    })
    setPreviewResult(result)
  }

  const handleExecute = async (decisionId: string) => {
    const result = await executeMutation.mutateAsync({
      decision_id: decisionId,
      confirm: true,
    })
    setExecuteResult(result)
  }

  if (isLoading) {
    return <div className="text-gray-400">Syncing with data nodes...</div>
  }

  if (error || !evidence) {
    return (
      <div className="space-y-4">
        <Link to="/opportunities" className="text-blue-400 hover:underline text-sm flex items-center gap-1">
          &larr; Back to Opportunities
        </Link>
        <div className="card border-red-900 bg-red-900/10 text-red-400 flex items-center gap-3">
          <AlertTriangle size={20} />
          Error loading opportunity details. The record may have expired.
        </div>
      </div>
    )
  }

  const { opportunity } = evidence

  if (!opportunity) {
    return (
      <div className="space-y-4">
        <Link to="/opportunities" className="text-blue-400 hover:underline text-sm">
          &larr; Back to Opportunities
        </Link>
        <div className="text-gray-400">Opportunity not found.</div>
      </div>
    )
  }

  const biasStrength = calculateBiasStrength(opportunity.bias)
  const ageMs = Date.now() - new Date(opportunity.snapshot_ts).getTime()
  const ageSec = Math.floor(ageMs / 1000)

  return (
    <div className="space-y-6">
      <Link to="/opportunities" className="text-blue-400 hover:underline text-sm flex items-center gap-1">
        &larr; Back to Opportunities
      </Link>

      {/* Dry Run / Mode Banner */}
      <DryRunBanner variant="compact" />

      {/* Opportunity Header */}
      <OpportunityHeader opportunity={opportunity} biasStrength={biasStrength} ageSec={ageSec} />

      <div className="grid lg:grid-cols-5 gap-6">
        {/* Left 3/5: Evidence and Insights */}
        <div className="lg:col-span-3 space-y-6">
          <TradeSummary opportunity={opportunity} biasStrength={biasStrength} ageSec={ageSec} />

          <section>
            <h3 className="text-lg font-medium mb-3">Evidence Trail</h3>
            <EvidenceTrail evidence={evidence} />
          </section>

          <MarketContextCard marketSnapshot={marketSnapshot} symbol={symbol} />

          {/* Phase 3C: Execution Risk Box */}
          <ExecutionRiskBox
            marketSnapshot={marketSnapshot as MarketSnapshotWithMicrostructure}
            confluence={(evidence?.opportunity as any)?.confluence}
          />
        </div>

        {/* Right 2/5: Controls and Action */}
        <div className="lg:col-span-2 space-y-6">
          <section>
            <h3 className="text-lg font-medium mb-3">Execution Control</h3>

            {/* Preview Form */}
            {opportunity.status !== 'executed' && (
              <PreviewForm
                sizeUsd={sizeUsd}
                onSizeUsdChange={setSizeUsd}
                venue={venue}
                onVenueChange={setVenue}
                onPreview={handlePreview}
                isPending={previewMutation.isPending}
              />
            )}

            {/* Preview Result */}
            {previewResult && !executeResult && (
              <PreviewPanel
                preview={previewResult}
                onExecute={handleExecute}
                isExecuting={executeMutation.isPending}
              />
            )}

            {/* Execute Result */}
            {executeResult && (
              <ExecuteResultCard executeResult={executeResult} onDismiss={() => setExecuteResult(null)} />
            )}

            {opportunity.status === 'executed' && !executeResult && (
              <div className="card border-green-900/50 text-gray-400 italic text-center py-8">
                Entry complete. Monitoring position in Portfolio.
              </div>
            )}
          </section>

          {/* Trade Plan Skeleton */}
          <TradePlanSkeleton />
        </div>
      </div>
    </div>
  )
}
