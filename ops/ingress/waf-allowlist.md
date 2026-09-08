# Cloudflare WAF: the four-IP allowlist

This is layer 1, and it does most of the work. An allowlist of four IPs at
Cloudflare's edge means an attacker has to source traffic from a TradingView
egress address before anything else in the chain is even tested.

Add one **Custom Rule** in the Cloudflare dashboard, on the zone that owns the
webhook hostname. Order matters: this must run before anything permissive.

**Field:** Expression editor
**Expression:**

```
(http.host eq "REPLACE_WITH_YOUR_HOSTNAME"
 and not ip.src in {52.89.214.238 34.212.75.30 54.218.53.128 52.32.178.7})
```

**Action:** Block

These four addresses are TradingView's published webhook egress IPs and are the
same list `tradesync_core.tradingview_webhook.TRADINGVIEW_SOURCE_IPS` checks in
the receiver. Two places, one fact — if TradingView changes them, both must move,
and `tests/test_tradingview_webhook.py` pins the pair so a one-sided edit fails.

## Why the receiver still checks, given the edge already did

The edge rule can be misconfigured, disabled during an incident, or bypassed if
the origin is ever reachable another way. The receiver's check costs nothing and
fails closed. Neither layer is load-bearing alone.

## What this does not do

An IP allowlist does not authenticate. Anyone who can make TradingView send a
request — which is anyone with the alert URL — passes it. That is what the shared
secret in the alert body is for, and why the endpoint refuses an unauthenticated
alert rather than accepting it with a warning.

**The threat here is evidence poisoning, not theft.** A Pine alert becomes
quarantined evidence, never a signal, and a receipt cannot set its own authority.
