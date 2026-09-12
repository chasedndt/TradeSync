# The Hermes harness wired in, and earned sources on the thesis

Date: 2026-09-13
Scope: `services/state-api/app/agent_connector.py` (OpenAI dialect + Bearer key),
`ops/compose.market-command.yml` (`AGENT_HARNESS_API`, `AGENT_HARNESS_KEY`),
`libs/tradesync_core/tradesync_core/thesis.py` (`sources`), `services/state-api/app/thesis.py`,
`services/cockpit-ui/src/pages/ThesisParts.tsx`, tests.

## The harness is Hermes itself

The operator's correction on 2026-09-12: "the harness is online, check the
ports it runs on, read the Hermes documentation." Done. The Hermes gateway
(hermes-agent 0.21.0, running in WSL from `~/runtimes/hermes-home`) has an
**API server** platform, reported `connected` in its `gateway_state.json`,
that speaks the OpenAI dialect: `GET /health`, `GET /v1/models`,
`POST /v1/chat/completions`, `POST /v1/responses`, `POST /v1/runs`,
authenticated with a Bearer token (`API_SERVER_KEY`). It binds
`127.0.0.1:8642` inside WSL, which WSL forwards to the Windows loopback, so
containers reach it at `http://host.docker.internal:8642`. Verified from the
state-api container: `/health` answers `{"status":"ok","platform":"hermes-agent","version":"0.21.0"}`.
Hermes's own model is `gpt-6-astra` through the OpenAI Codex provider, with a
local `deepseek-r1:8b` fallback. Its Discord platform was in `retrying` at
the time (Discord connect timeouts since 00:19 UTC), which is why some fleet
posts were not reaching channels; the API server was unaffected.

## What changed

- **The connector speaks both dialects.** `AGENT_HARNESS_API=openai` selects
  `/v1/models` for the probe and `/v1/chat/completions` for asks, with the
  key from `AGENT_HARNESS_KEY` sent only in the Authorization header. The
  default stays `ollama`, so nothing changes for a runtime that was never
  configured. The boundary is unchanged: an answer carrying a score,
  direction, approval or order field is refused by name, and every accepted
  answer is filed in quarantine, never in evidence. A test proves the
  refusal holds in the new dialect and that the module logs nothing.
- **The key was copied file to file.** `tools/copy-hermes-discord-token.ps1
  -SourceName API_SERVER_KEY -TargetName AGENT_HARNESS_KEY` moved Hermes's
  own API key into `runtime.env` without displaying it. `AGENT_HARNESS_URL`
  and `AGENT_HARNESS_API` were set alongside.
- **Earned sources join the thesis.** The thesis now reads the source cards:
  earned sources are listed in the confirmation stack and lift the
  `no_earned_inputs` condition exactly as an earned feature would; the
  counts of measured and recording sources are shown so the reader knows
  how much of the fleet has been judged at all. One new line in the text.

## What the harness will be used for

Advisory only, as the boundary says: explaining a thesis, comparing two
reads, drafting prose, and proposing claims from the held posts the rule
extractor cannot read. Proposed claims enter through the same `Claim` shape
under their own extractor name and are measured on exactly the same footing
as rule-extracted ones. The harness cannot set a direction the system acts
on, cannot score, cannot approve.

## Tests

State-api: `test_agent_connector.py` (probe lists models and sends the
Bearer key, ask posts chat completions and wraps the answer, an answer
claiming authority is refused, the module prints nothing). Root:
`test_thesis.py` gains the sources line and the earned-source case.
