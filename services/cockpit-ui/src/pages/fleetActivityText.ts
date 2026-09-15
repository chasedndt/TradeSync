import type { FleetFire, FleetJobActivity, FleetOutputSummary, FleetRun } from '../api/fleetActivityTypes'

/** "45s", "4m", "2h 5m", "3d 4h". */
export function span(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return '—'
  const s = Math.max(0, Math.round(seconds))
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m`
  if (s < 86400) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
  return `${Math.floor(s / 86400)}d ${Math.floor((s % 86400) / 3600)}h`
}

/** "850 ms", "40.0s", "2m". */
export function duration(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms)) return '—'
  if (ms < 1000) return `${ms} ms`
  return ms < 60_000 ? `${(ms / 1000).toFixed(1)}s` : span(ms / 1000)
}

/** "512 B", "3.5 KB", "1.2 MB". */
export function bytes(n: number): string {
  if (n < 1024) return `${n} B`
  return n < 1_048_576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1_048_576).toFixed(1)} MB`
}

/** "15 Sep, 01:02": an absolute local time. */
export function when(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'
}

/** Seconds since a running run started, or since it was claimed when it has not started. */
export function elapsedSeconds(run: Pick<FleetRun, 'started_at' | 'claimed_at'>, nowMs: number): number | null {
  const began = run.started_at ?? run.claimed_at
  return began ? Math.max(0, (nowMs - Date.parse(began)) / 1000) : null
}

export function deliveryName(target: string): string {
  if (target.startsWith('discord:')) return 'Discord'
  return target === 'local' ? 'TradeSync only' : target
}

/** Where a job's latest model call went: its error, silent, or the target it was delivered to. */
export function fireLine(fire: Pick<FleetFire, 'silent' | 'deliver_target' | 'error'> | null): string {
  if (!fire) return 'no model call recorded (script jobs make none)'
  if (fire.error) return `model call failed: ${fire.error}`
  if (fire.silent) return 'silent: nothing delivered'
  return `delivered to ${fire.deliver_target ? deliveryName(fire.deliver_target) : 'no recorded target'}`
}

export function outputDelivery(output: Pick<FleetOutputSummary, 'delivery'>): string {
  const { kind, channel_label: label } = output.delivery
  if (kind === 'discord') return `Discord${label ? ` #${label}` : ''}`
  if (kind === 'local') return 'TradeSync only'
  return kind ?? 'delivery not recorded'
}

export function laterRunsLine(activity: Pick<FleetJobActivity, 'latest_output' | 'later_runs_without_output'>): string | null {
  const n = activity.later_runs_without_output
  if (!activity.latest_output || !n) return null
  return `${n} later run${n === 1 ? '' : 's'} left no stored output: silent runs are not stored.`
}

export function runTone(status: string | null): 'tone-good' | 'tone-bad' | 'tone-warn' | 'tone-dim' {
  const s = (status ?? '').toLowerCase()
  if (s === 'completed' || s === 'ok') return 'tone-good'
  if (s === 'failed' || s === 'error' || s === 'timeout') return 'tone-bad'
  if (s === 'unknown' || s === 'interrupted') return 'tone-warn'
  return 'tone-dim'
}
