import { useState } from 'react'
import { useEditions, useGenerateEdition } from '../api/hooks/useEditions'
import type { ThesisEdition } from '../api/types'

const MEDIA_BASE = '/api/state/thesis/editions'

/**
 * The daily edition: every symbol's thesis frozen at the NY premarket,
 * midday and session-handoff checks, with the written text, the spoken
 * script, and any narration or video the host renderer attached. Editions
 * are the record; the live thesis above recomputes on every read.
 */
export function EditionPanel() {
  const { data, isLoading, isError } = useEditions(8)
  const generate = useGenerateEdition()
  const [openId, setOpenId] = useState<string | null>(null)
  const [tab, setTab] = useState<'text' | 'narration'>('text')

  const latest = data?.editions[0]
  const shown = data?.editions.find((e) => e.id === openId) ?? latest

  return (
    <section className="panel" aria-labelledby="edition-title">
      <div className="panel-heading">
        <div>
          <h2 id="edition-title">Daily edition</h2>
          <p>
            {data?.schedule ? `${data.schedule.entries.split(',').map((e) => e.replace('=', ' ')).join(' · ')} (${data.schedule.timezone})` : 'schedule…'}
            {data?.schedule.next.at ? ` · next ${data.schedule.next.edition} at ${new Date(data.schedule.next.at).toUTCString().slice(17, 22)} UTC` : ''}
          </p>
        </div>
        <button type="button" className="chip" disabled={generate.isPending} onClick={() => generate.mutate()}>
          {generate.isPending ? 'assembling all symbols…' : 'Generate edition now'}
        </button>
      </div>

      {isError && <p className="tone-bad" style={{ padding: 16 }}>Editions unavailable.</p>}
      {isLoading && <p className="tone-dim" style={{ padding: 16 }}>Loading editions…</p>}
      {data && data.editions.length === 0 && (
        <p className="tone-dim" style={{ padding: 16 }}>No edition yet. The first scheduled one is {data.schedule.next.edition} at {data.schedule.next.at ? new Date(data.schedule.next.at).toUTCString() : '—'}; or generate one now.</p>
      )}

      {shown && (
        <div style={{ padding: '0 17px 14px', display: 'grid', gap: 10 }}>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            {data!.editions.map((e) => (
              <button key={e.id} type="button" className={e.id === shown.id ? 'chip chip--active' : 'chip'} onClick={() => setOpenId(e.id)} title={e.headline}>
                {e.edition} · {new Date(e.generated_at).toUTCString().slice(5, 22)}
              </button>
            ))}
          </div>
          <strong style={{ fontSize: 13 }}>{shown.headline}</strong>
          <Verdicts edition={shown} />
          <Media edition={shown} />
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" className={tab === 'text' ? 'chip chip--active' : 'chip'} onClick={() => setTab('text')}>written</button>
            <button type="button" className={tab === 'narration' ? 'chip chip--active' : 'chip'} onClick={() => setTab('narration')}>spoken script</button>
          </div>
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, lineHeight: 1.5, margin: 0, maxHeight: 420, overflowY: 'auto', fontFamily: tab === 'text' ? 'inherit' : 'var(--font-mono)' }}>
            {tab === 'text' ? shown.text : shown.narration}
          </pre>
          <span className="metric-sub">edition {shown.id} · trigger {shown.trigger} · {shown.symbols.length} symbols · private, not for publication</span>
        </div>
      )}
    </section>
  )
}

function Verdicts({ edition }: { edition: ThesisEdition }) {
  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
      {edition.symbols.map((s) => {
        const v = edition.verdicts[s]
        const dir = edition.headline.includes(`${s.replace('-PERP', '')} LONG`) ? 'LONG' : edition.headline.includes(`${s.replace('-PERP', '')} SHORT`) ? 'SHORT' : '—'
        return (
          <span key={s} className={`pill ${v === 'NO TRADE' ? 'pill--bad' : 'pill--warn'}`} title={v}>
            {s.replace('-PERP', '')} {dir}
          </span>
        )
      })}
    </div>
  )
}

function Media({ edition }: { edition: ThesisEdition }) {
  const audio = edition.media.audio
  const video = edition.media.video
  if (!audio && !video) return <span className="metric-sub">no narration rendered yet · the host renderer attaches audio and video after each edition</span>
  return (
    <div style={{ display: 'grid', gap: 8 }}>
      {audio && <audio controls preload="none" src={`${MEDIA_BASE}/${edition.id}/media/${audio}`} style={{ width: '100%', maxWidth: 520 }} />}
      {video && <video controls preload="metadata" src={`${MEDIA_BASE}/${edition.id}/media/${video}`} style={{ width: '100%', maxWidth: 640, borderRadius: 4 }} />}
    </div>
  )
}
