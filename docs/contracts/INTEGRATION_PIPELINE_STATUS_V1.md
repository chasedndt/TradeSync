# Integration Pipeline Status v1

Status: implemented as a read-only runtime inspection contract

Endpoint: `GET /state/integration-pipeline`

Cockpit route: `/pipeline`

## Purpose

`integration_pipeline_status_v1` gives the operator one truthful view of the
TradeSync operating path. It distinguishes a live runtime probe from a contract
that only exists in source or documentation. The endpoint never starts a
service, connects a wallet, consumes an approval, or changes execution state.

The contract represents three capability tiers:

- Tier A: standalone Hyperliquid observation, transport, durable state,
  deterministic intelligence, paper opportunity support, and learning loop.
- Tier B: optional TradingView/Pine Script, Strike Zone Crypto, agent harness,
  and ChaseOS knowledge connectors.
- Tier C: isolated-wallet and governed Hyperliquid execution, currently locked.

Tier B health is excluded from the Tier A readiness count. A disconnected
optional connector can reduce a federated capability without stopping the
standalone workstation.

## Evidence model

Each node declares:

| Field | Meaning |
|---|---|
| `status` | Current observed or declared state; see status values below. |
| `required_for_tier_a` | Whether this node contributes to the Tier A readiness count. |
| `authority` | The data or decision authority owned by the component. |
| `evidence` | Probe results or explicit repository evidence supporting the state. |
| `missing` | Inputs, adapters, services, or gates not currently verified. |
| `impact` | What stops, and what continues, while the node is incomplete. |
| `recovery` | A bounded next action and optional restart target. |

Every edge declares `flowing`, `partial`, `not_connected`, or `locked`.
Recovery items are ordered with Tier A blockers before optional connector work.

## Status values

| Status | Meaning |
|---|---|
| `live` | A source or service answered its current runtime probe. |
| `healthy` | A required infrastructure probe passed. |
| `partial` | Some evidence is available, but the stage is not end-to-end complete. |
| `offline` | A required or configured runtime probe did not pass. |
| `contract_only` | A versioned boundary is declared, but no runtime endpoint is configured. |
| `planned` | The component remains roadmap work. |
| `locked` | Policy deliberately prevents the capability from operating. |

`contract_only` must never be presented as connected. A cached artifact or
repository type is not a live connector.

## Live probes

The State API probes these current-runtime surfaces:

- market-data health, provider status, and BTC-PERP feature coverage;
- Redis `PING`;
- PostgreSQL connectivity and latest signal/opportunity timestamps;
- ingest-gateway, core-scorer, and fusion-engine health routes;
- optional connector health routes only when their URLs are explicitly set.

The default probe timeout is three seconds and can be changed with
`INTEGRATION_PROBE_TIMEOUT_SECONDS` when a measured local-runtime constraint
requires it.

Unstarted internal and optional services use a separate 0.75-second deadline,
configurable with `INTEGRATION_SERVICE_PROBE_TIMEOUT_SECONDS`. Bounded probes
run outside the main API event loop, so slow dashboard work and failed Docker
DNS lookups cannot invalidate the authoritative market probe.

Optional runtime endpoints are configured server-side:

- `INGEST_GATEWAY_URL`
- `CORE_SCORER_URL`
- `FUSION_ENGINE_URL`
- `STRIKEZONE_CONNECTOR_URL`
- `AGENT_HARNESS_URL`
- `CHASEOS_CONNECTOR_URL`

The bounded `compose.market-command.yml` profile deliberately leaves the
ingest/scorer/fusion endpoints empty because it does not start those services.
Their cards remain `offline` without paying repeated Docker DNS timeouts. The
full-stack profile retains the conventional service-name defaults.

No connector secret or private key belongs in the Cockpit or this response.

## Capability gaps

The response carries explicit gaps so an empty field cannot be mistaken for a
zero or a broken dashboard:

- `direct_liquidations` is unavailable until a provenance-preserving source
  adapter exists. OI-derived pressure must not be renamed as liquidations.
- `price_change_24h` is `deferred_non_blocking`. It blocks nothing in the
  current Tier A slice and remains blank until a timestamp-aligned,
  authoritative derivation is intentionally implemented.

## Safety boundary

- `mode` is `paper`.
- `execution_authority` is `false`.
- Recovery commands are explanatory text, not executable UI controls.
- The execution node remains `locked` until the isolated signer, risk policy,
  single-use approval, replay protection, and reconciliation gates exist.
- ChaseOS means the canonical instance at
  `C:\Users\chaseos\Documents\chaseos_chaseintech`; this endpoint does not read,
  move, or modify that vault.

## Minimal response shape

```json
{
  "schema_version": "integration_pipeline_status_v1",
  "mode": "paper",
  "execution_authority": false,
  "tier_a": {
    "status": "partial",
    "ready_count": 4,
    "total_count": 7
  },
  "federated": {
    "status": "not_connected",
    "connected_count": 0,
    "total_count": 4
  },
  "nodes": [],
  "edges": [],
  "recovery_queue": [],
  "capability_gaps": []
}
```

Counts are live observations and may change between requests.
