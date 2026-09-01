# Mobile Alert Control Plane

## Answer

Yes. A useful mobile-alert MVP is feasible within three weeks without Xcode or a native iOS app.

The recommended reusable system is a vendor-neutral **ChaseOS Notification Control Plane** whose first producer is TradeSync. TradeSync owns market alert meaning; the control plane owns routing, preferences, delivery, acknowledgement, and receipts.

## Delivery channels

1. **In-app stream** — always available while the Cockpit is open.
2. **Standards-based Web Push/PWA** — primary mobile path. On iOS/iPadOS 16.4+, the user adds the web app to the Home Screen and grants notification permission from a user interaction. Apple states that this does not require Apple Developer Program membership.
3. **ntfy adapter** — free rapid-delivery path using the ntfy mobile/web clients. It can start with a private topic on the hosted service for development or a self-hosted Docker service later.
4. **Email and chat adapters** — later, behind the same router and per-project policy.

No delivery adapter receives wallet secrets, private keys, full approval payloads, or sensitive model context.

## Rust router responsibilities

The planned `alert-router-rs` service uses Tokio/Axum and owns:

- authenticated producer ingress;
- JSON/schema validation against `alert_event_v1`;
- deduplication and idempotency;
- project/category/severity routing;
- quiet hours and escalation policy;
- per-device subscriptions;
- rate limits and alert storms;
- PostgreSQL transactional outbox;
- delivery attempts, retries, acknowledgements, expiration, and dead letters;
- adapter isolation so one failing channel cannot block others;
- SSE/WebSocket status for the Cockpit.

It does **not** score markets, approve trades, sign payloads, or place orders.

## Shared cross-project event

Every alert includes `project`, `source`, `category`, `severity`, `environment`, `title`, `body`, timestamps, dedupe key, optional symbol/timeframe, evidence links, expiry, acknowledgement requirement, and a data-classification label.

Examples:

- `tradesync.market.regime_transition`
- `tradesync.paper.opportunity_ready`
- `tradesync.system.market_feed_stale`
- `chaseos.approval.requested`
- `strikezone.paper.candidate_ready`
- `opus_vela.render.failed`

Projects publish the same envelope and define separate routing policies and credentials.

## Three-week implementation

### Week 1

- contract and Rust validation crate;
- PostgreSQL alert/outbox/device schema;
- Redis consumer group;
- in-app delivery;
- producer authentication design.

### Week 2

- Rust router service;
- ntfy adapter;
- PWA manifest/service worker/subscription endpoints;
- operator preferences and test-notification flow.

### Week 3

- iOS Home Screen and Android enrollment tests;
- retry, acknowledgement, dedupe, quiet hours, dead-letter, and rate-limit tests;
- restart recovery and latency soak;
- mobile responsive notification inbox;
- security and operational runbook.

## Constraints and honest limitations

- Web Push needs HTTPS outside localhost and device enrollment. Exposing the service externally is a separate deployment/security approval.
- iOS Web Push is for Home Screen web apps; an ordinary Safari tab is not the enrollment experience.
- A hosted ntfy topic is convenient but is an external provider boundary. Sensitive payloads should use self-hosting or minimal opaque messages with authenticated deep links.
- “Notification accepted by adapter” is not “seen by user.” The ledger distinguishes queued, attempted, accepted, delivered when knowable, and acknowledged.
- Three weeks is realistic for the MVP and reliability baseline, not for a polished App Store application or every future project adapter.

## Security defaults

- per-project producer credentials and scopes;
- payload size and classification limits;
- no action-capable links without re-authentication;
- random/private topic names are not treated as authentication;
- VAPID private key and provider credentials stay in a governed secret store;
- user opt-in and explicit test notification;
- notification actions never consume a trading approval.

## Official references

- [WebKit: Web Push for Web Apps on iOS and iPadOS](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/)
- [ntfy self-hosting and Web Push configuration](https://docs.ntfy.sh/config/)
- [ntfy publishing API](https://docs.ntfy.sh/publish/)
- [Axum documentation](https://docs.rs/axum/latest/axum/)

## Canonical diagram

Source: [mobile-alert-control-plane.mmd](../diagrams/mobile-alert-control-plane.mmd)
