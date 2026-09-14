# Mobile alerts: Android and iPhone

Status: source implemented and locally deployed; **no real device enrolled or
delivery verified yet**. The transport is generic ntfy.sh notifications, not a
custom native application. It carries no signing or trading authority.

## Setup and acceptance

1. Configure a dedicated random **32+ character application control key** as
   `MOBILE_ALERTS_CONTROL_KEY` in the private
   `E:/Projects/TradeSync/dashboard-runtime/runtime.env`, using the governed
   private-configuration workflow. This is not a wallet key, seed, provider key
   or new paid subscription. Do not paste it in chat, logs or this repository.
2. Recreate only State API using the existing compose project and files:
   `docker compose --project-name tradesync-full --env-file E:/Projects/TradeSync/dashboard-runtime/runtime.env -f ops/compose.full.yml -f ops/compose.market-command.yml up -d --no-deps --no-build state-api`.
3. Authorized browser/API requests must supply the same key as `X-API-Key`.
   The existing local Cockpit API-key mechanism sends this header. Use the
   trusted local workstation/browser profile; it currently stores that control
   credential in browser local storage. Do not expose the dashboard/API to the
   internet or enter the credential into another project's API configuration.
   A hardened session-based local control flow remains a security improvement.
4. Install [ntfy on the phone](https://docs.ntfy.sh/subscribe/phone/).
   In TradeSync **Settings → Mobile notifications**, select Android or iPhone,
   enter a label and explicitly accept generic public-topic delivery.
   **Create subscription details** creates a local record only; it sends nothing.
5. In the ntfy app, subscribe using server `https://ntfy.sh` and the generated
   topic. Enable phone notification permission. Save the topic privately;
   **Show subscription details** can reveal it again to an authorized operator.
6. Click **Send generic test**. Watch the delivery ledger. `provider_accepted`
   means the response matched the topic/message and included a provider ID.
   It does **not** mean the phone received a notification.
7. On the specified physical phone, find the matching reference. Only then click
   **I received this on my phone**. This records operator attestation, not
   automated telemetry. Repeat independently for the other phone platform.
8. Disable a channel to stop pending sends. An already in-flight HTTP request
   cannot be recalled. Notifications cannot approve, modify or execute a trade.

No real topic, control credential or physical-device receipt is included here.
There is no need to invent a TradingView/Reown/crypto wallet key for this setup.

## Reliability and privacy

PostgreSQL `mobile_alert_outbox` stores events separately from provider delivery.
`(device_id, dedupe_key)` deduplicates enqueue calls. Events expire after ten
minutes; the worker claims rows with a lease and retries at most three attempts.
400-class denials other than rate limiting fail without retry. HTTP redirects
are not followed. Topic format and fixed HTTPS provider prevent arbitrary URL
publishing. Only two hardcoded generic templates are permitted.

Transport is **at least once**, not exactly once: a timeout after provider
acceptance can produce a duplicate on retry. A stable short reference lets the
operator recognize duplicates. The service can also be offline beyond expiry;
this is not a guaranteed emergency notification service. Device disable and
expired entries never create execution authority.

Public ntfy topics are not authenticated private channels. Anyone who learns a
topic may subscribe or spoof messages. High-entropy generated topics reduce
guessability but are not a replacement for access control. Do not send balances,
wallet addresses, trade details, secrets or approval actions. Provider quotas
can delay/refuse messages; a future authenticated/private adapter can replace
this transport without changing the durable event ledger.

## Remaining work

- Actual setup, subscription and receipt on **both** Android and iPhone.
- Managed-paper open/close producer, per-phone opt-in, quiet hours/timezone and
  rolling 24-hour budgets are deployed and isolated-test verified. Actual phone
  delivery remains unverified. Chart-alert producers are still unconnected.
- Preferences by symbol/category/severity, global cross-device budgets,
  acknowledgement reminders and long-running outage recovery tests remain.
- Optional authenticated self-hosting/private delivery and/or PWA Web Push;
  native ntfy clients do not mean TradeSync already has a PWA/service worker.
- Phone-to-dashboard remote access remains separate. Do not publish the entire
  State API or reuse the restricted Pine ingress as a mobile dashboard tunnel.

References: [ntfy publishing and limitations](https://docs.ntfy.sh/publish/),
[phone clients](https://docs.ntfy.sh/subscribe/phone/).
# Lifecycle preferences update — 14 September

After receiving and confirming a test on a phone, open its **Paper lifecycle
notification preferences** in Settings. Explicitly opt in to future managed-paper
opens/closes, choose an IANA timezone, quiet hours and a rolling 24-hour budget.
Default: opt-out, Europe/London, quiet 22:00–08:00, maximum 10 lifecycle messages.
Equal start/end means all-day quiet. Suppressed events are recorded but not
replayed; manual tests bypass quiet hours. Opt-out cannot recall an in-flight
request. Messages remain generic, without symbols, balances or trade instructions.

Implementation/isolated SQL/UI checks passed; actual Android/iPhone delivery
remains unverified and requires the private setup described below.
