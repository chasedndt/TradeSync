import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../../../api/client'
import type { EvidenceResponse } from './paperTypes'
import { exactTime } from './paperFormat'
import { PaperEvidenceItem } from './PaperEvidenceItem'
import { PaperExternalContext } from './PaperExternalContext'
import styles from './PaperEvidence.module.css'

/** The frozen entry record: its fingerprint check, the cut-off, every item with ages and missing markers, and the raw document. */
export function PaperEvidence({ id, fingerprint }: { id: string; fingerprint: string }) {
  const evidence = useQuery({ queryKey: ['paper-evidence', id], queryFn: () => apiGet<EvidenceResponse>(`/state/paper-positions/${id}/evidence`) })
  const doc = evidence.data?.entry_evidence
  const items = doc?.items ?? {}
  const order = (doc?.item_order ?? Object.keys(items)).filter((key) => items[key])
  const verified = evidence.data?.digest_verified
  return (
    <div className={styles.evidence}>
      <p>Entry fingerprint: {fingerprint}{verified === true ? ' · matches the stored record' : verified === false ? ' · does not match the stored record' : ''}</p>
      {evidence.isLoading && <p>Loading entry evidence…</p>}
      {evidence.isError && <p role="alert">Entry evidence unavailable: {evidence.error.message}</p>}
      {doc && (
        <>
          <p>
            {doc.schema_version
              ? `Entry at ${exactTime(doc.entry_time)}. Only facts observed and received before it are kept (${doc.cutoff_rule}); ${doc.excluded_count ?? 0} later or undated records were excluded. Schema ${doc.schema_version}.`
              : 'Recorded before itemised entry evidence; older entries are not backfilled.'}{' '}
            Capturing context does not make it a scored signal.
          </p>
          {order.length > 0 && <ul className={styles.items}>{order.map((key) => <PaperEvidenceItem key={key} item={items[key]} />)}</ul>}
          <PaperExternalContext context={doc.external_context} />
          <details>
            <summary>Raw frozen record</summary>
            <pre>{JSON.stringify(evidence.data, null, 2)}</pre>
          </details>
        </>
      )}
    </div>
  )
}
