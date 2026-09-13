import { useState } from 'react'
import { useEdition, useEditions } from '../../api/hooks/useEditions'
import { BriefingCard } from './BriefingCard'
import { hasBriefing, hasOutlook } from './guards'
import { KeyEvents } from './KeyEvents'
import { OutlookOverview } from './OutlookOverview'
import { RegenerateControl } from './RegenerateControl'
import { SymbolGrid } from './SymbolGrid'
import styles from './Thesis.module.css'

const MEDIA_BASE = '/api/state/thesis/editions'

/**
 * The market thesis as a trader reads it: the outlook first (lean, lead
 * reads, notes), then this week's events with measured reactions and
 * coverage, the Hermes briefing, every market as a card, and the narration.
 */
export function EditionView() {
  const list = useEditions(8)
  const [selected, setSelected] = useState<string | null>(null)
  const latest = list.data?.editions[0]
  const id = selected ?? latest?.id ?? null
  const full = useEdition(id)
  const e = full.data

  const when = e ? new Date(e.generated_at).toUTCString().slice(0, 22) + ' UTC' : ''
  const next = list.data?.schedule.next

  return (
    <div className={styles.edition}>
      <section className="panel">
        <div className={styles.head}>
          <div>
            <h2>Market Thesis</h2>
            <p>
              {e ? `${e.edition.replace('-', ' ')} edition · ${when}${e.reason ? ` · reason: ${e.reason}` : ''}` : list.isLoading ? 'loading…' : 'no edition yet'}
              {next?.at ? ` · next scheduled ${next.edition} at ${new Date(next.at).toUTCString().slice(17, 22)} UTC` : ''}
            </p>
          </div>
          <RegenerateControl />
        </div>
        {(list.data?.editions.length ?? 0) > 1 && (
          <div className={styles.editionChips}>
            {list.data!.editions.map((ed) => (
              <button key={ed.id} type="button" className={ed.id === id ? 'chip chip--active' : 'chip'} onClick={() => setSelected(ed.id)} title={ed.headline}>
                {ed.edition} · {new Date(ed.generated_at).toUTCString().slice(5, 22)}
              </button>
            ))}
          </div>
        )}
        {e && hasOutlook(e.outlook) && <OutlookOverview o={e.outlook} />}
        {e && !hasOutlook(e.outlook) && <p className="tone-dim" style={{ padding: '0 18px 14px' }}>This edition predates the market outlook. Regenerate to build one.</p>}
        {full.isError && <p className="tone-bad" style={{ padding: '0 18px 14px' }}>Edition unavailable.</p>}
      </section>

      {e && hasOutlook(e.outlook) && (
        <div className={styles.twoCol}>
          <section className="panel">
            <div className="panel-heading"><div><h3>This week</h3><p>scheduled events · how the market reacted to past releases · recent coverage</p></div></div>
            <div className={styles.sectionBody}><KeyEvents events={e.outlook.key_events} method={e.outlook.reaction_method} /></div>
          </section>
          <BriefingCard b={hasBriefing(e.briefing) ? e.briefing : null} />
        </div>
      )}

      {e?.theses && (
        <section className="panel">
          <div className="panel-heading"><div><h3>Markets</h3><p>every tracked market's thesis at this edition</p></div></div>
          <SymbolGrid theses={e.theses} order={e.symbols} />
        </section>
      )}

      {e && (e.media.video || e.media.audio) && (
        <section className="panel">
          <div className="panel-heading"><div><h3>Narrated edition</h3><p>edge-tts voice and slides, rendered on the host</p></div></div>
          <div className={styles.sectionBody}>
            {e.media.video && <video controls preload="metadata" src={`${MEDIA_BASE}/${e.id}/media/${e.media.video}`} style={{ width: '100%', maxWidth: 760, borderRadius: 4 }} />}
            {!e.media.video && e.media.audio && <audio controls preload="none" src={`${MEDIA_BASE}/${e.id}/media/${e.media.audio}`} />}
          </div>
        </section>
      )}

      {e && (
        <section className={`panel ${styles.script}`}>
          <details>
            <summary>Written edition and spoken script</summary>
            <pre>{e.text}</pre>
            <pre>{e.narration}</pre>
          </details>
        </section>
      )}
    </div>
  )
}
