/** Each Hermes job's run progress and stored output, as the state API shapes the fleet read model and quarantine. */

export interface FleetRun {
  id: string
  status: string | null
  claimed_at: string | null
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
  error: string | null
  /** Present on a run the ledger has claimed or started and not finished. */
  running?: boolean
  elapsed_s?: number | null
  /** False when the newest run snapshot no longer carried this run, so it may have finished since. */
  in_latest_snapshot?: boolean
}

export interface FleetOutputSummary {
  id: string
  job_id: string | null
  agent: string | null
  received_at: string | null
  observed_at: string | null
  /** The output file's stamp on the fleet host's local clock. */
  ran_at_stamp: string | null
  bytes: number
  lines: number
  truncated: boolean
  accepted: boolean
  refused_because: string[]
  delivery: { kind: string | null; channel_label: string | null }
  first_lines: string[]
  /** How many token-, key- or webhook-shaped strings were masked. */
  masked: number
}

export interface FleetOutputText extends FleetOutputSummary {
  text: string
  note: string
}

export interface FleetFire {
  ts: string | null
  model: string | null
  duration_ms: number | null
  silent: boolean | null
  deliver_target: string | null
  error: string | null
}

export interface FleetJobActivity {
  running: FleetRun[]
  runs: FleetRun[]
  latest_output: FleetOutputSummary | null
  later_runs_without_output: number | null
  latest_fire: FleetFire | null
}

export interface FleetSnapshotAges {
  bridge_every_s: { fleet: number; outputs: number }
  runs_snapshot_at: string | null
  runs_snapshot_age_s: number | null
  jobs_snapshot_at: string | null
  jobs_snapshot_age_s: number | null
  usage_newest_at: string | null
  usage_newest_age_s: number | null
  outputs_received_at: string | null
  outputs_received_age_s: number | null
}

export interface FleetActivityResponse {
  schema_version: 'fleet_activity_v1'
  generated_at: string
  snapshot: FleetSnapshotAges
  outputs_indexed_since: string | null
  jobs: Record<string, FleetJobActivity>
  note: string
}

export interface FleetJobOutputs {
  job_id: string
  outputs: { id: string; received_at: string }[]
  latest: FleetOutputSummary | null
  indexed_since: string | null
  note: string
}
