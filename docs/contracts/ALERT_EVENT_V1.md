# Alert Event v1

`alert_event_v1` is the reusable producer-to-notification-control-plane envelope.

## Required fields

| Field | Type | Rule |
|---|---|---|
| `schema_version` | string | Exactly `alert_event_v1` |
| `event_id` | string | Globally unique immutable ID |
| `project` | string | Producer namespace such as `tradesync` |
| `source` | string | Exact producing service/rule |
| `category` | string | Stable dotted category |
| `severity` | enum | `info`, `warning`, `critical` |
| `environment` | enum | `paper`, `testnet`, `live`, `system` |
| `title` | string | 1–120 characters |
| `body` | string | 1–1000 characters; no secrets |
| `created_at_ms` | integer | UTC Unix milliseconds |
| `dedupe_key` | string | Stable for equivalent alerts within a policy window |
| `data_classification` | enum | `public`, `internal`, `restricted` |

## Optional fields

- `symbol`, `timeframe`
- `evidence_refs[]`
- `deep_link`
- `expires_at_ms`
- `requires_ack`
- `correlation_id`, `causation_id`
- `attributes` with size/count limits

## Rules

- `restricted` alerts cannot use an adapter that lacks restricted-payload permission.
- Unknown schema versions are rejected, not guessed.
- Expired alerts are recorded as expired and not delivered.
- Deduplication suppresses duplicate delivery, never the durable receipt.
- A notification cannot carry or consume trading authority.

The initial Rust representation lives in `libs/tradesync-contracts-rs`.
