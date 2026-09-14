import { useState } from 'react'

export type NotificationPreferences = { paper_events?: boolean; timezone?: string; quiet_enabled?: boolean; quiet_start?: number; quiet_end?: number; daily_budget?: number }

export function MobilePreferences({ initial, enabled, confirmed, busy, save }: {
  initial: NotificationPreferences; enabled: boolean; confirmed: boolean; busy: boolean;
  save: (value: NotificationPreferences) => Promise<void>;
}) {
  const [paper, setPaper] = useState(initial.paper_events ?? false)
  const [timezone, setTimezone] = useState(initial.timezone ?? 'Europe/London')
  const [quiet, setQuiet] = useState(initial.quiet_enabled ?? true)
  const [start, setStart] = useState(String(initial.quiet_start ?? 22))
  const [end, setEnd] = useState(String(initial.quiet_end ?? 8))
  const [budget, setBudget] = useState(String(initial.daily_budget ?? 10))
  const valid = (value: string, min: number, max: number) => value.trim() !== '' && Number.isInteger(Number(value)) && Number(value) >= min && Number(value) <= max
  const invalid = !timezone.trim() || !valid(start, 0, 23) || !valid(end, 0, 23) || !valid(budget, 1, 50)
  return <details className="mt-3">
    <summary>Paper lifecycle notification preferences</summary>
    <form className="mt-3 space-y-3" onSubmit={event => {
      event.preventDefault()
      if (!invalid && (!paper || window.confirm('Enable generic notifications for future paper opens and closes on this phone, subject to quiet hours and the message budget?'))) void save({ paper_events: paper, timezone: timezone.trim(), quiet_enabled: quiet, quiet_start: Number(start), quiet_end: Number(end), daily_budget: Number(budget) })
    }}>
      <label className="block text-sm"><input type="checkbox" checked={paper} disabled={!enabled || !confirmed} onChange={e => setPaper(e.target.checked)} /> Notify me when a managed paper position opens or closes</label>
      {!confirmed && <p className="text-xs text-gray-400">Receive and confirm a test on this phone before enabling lifecycle alerts.</p>}
      <label className="block">Timezone<input className="input w-full" value={timezone} onChange={e => setTimezone(e.target.value)} placeholder="Europe/London" /></label>
      <label className="block text-sm"><input type="checkbox" checked={quiet} onChange={e => setQuiet(e.target.checked)} /> Enable quiet hours</label>
      <div className="flex flex-wrap gap-3">
        <label className="block flex-1" style={{ minWidth: 120 }}>Quiet start hour<input className="input w-full" type="number" min="0" max="23" value={start} onChange={e => setStart(e.target.value)} /></label>
        <label className="block flex-1" style={{ minWidth: 120 }}>Quiet end hour<input className="input w-full" type="number" min="0" max="23" value={end} onChange={e => setEnd(e.target.value)} /></label>
      </div>
      <label className="block">Maximum lifecycle messages per rolling 24 hours<input className="input w-full" type="number" min="1" max="50" value={budget} onChange={e => setBudget(e.target.value)} /></label>
      <p className="text-xs text-gray-400">Hours use the chosen timezone, including daylight saving. Equal start/end means all-day quiet. Suppressed events are not replayed later. Manual tests bypass quiet hours. Disabling cannot recall a request already in flight.</p>
      <button className="chip" disabled={busy || !enabled || invalid || (paper && !confirmed)}>Save notification preferences</button>
    </form>
  </details>
}
