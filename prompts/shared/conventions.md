# TradeSync – Global Conventions
- Read these first: docs/PRD.md, docs/SYSTEM_DESIGN.md, docs/AGENT_INTERFACE.md.
- Streams: x:events.raw, x:events.norm, x:signals.*, x:opps, x:exec.orders.
- Timeframes (canonical): ["1m","5m","15m","30m","1h","2h","4h","8h","1d"].
- DB tables & fields must match AGENT_INTERFACE §20 exactly.
- APIs must match OPENAPI/state-api.v0_1.yaml (do not invent endpoints).
- Expose /healthz and /metrics on every API service.
- No secrets in code; use env vars and .env files.
