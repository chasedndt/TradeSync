# Scheduled economic events on Mission Control

Date: 2026-09-12
Scope: `services/state-api/app/{economic_calendar,context_shapes,context_feed}.py`,
`services/cockpit-ui/src/components/EventsStrip.tsx`, `Overview.tsx`, tests.

First of the three sources from the 2026-09-12 open-data research. Full
rationale is in the commit message (`12803d5`); this record carries what the
live rollout showed.

## What went wrong on rollout, and what it fixed

ForexFactory's feed answered **429** after a handful of requests from this host
— my own probes plus the container's first fetch. That exposed a gap in the
context-feed service itself: a failed fetch was not cached, so the Cockpit's
one-minute overview poll would have re-asked the rate-limiting feed every
minute and kept the host banned. A failure is now **held for fifteen minutes**
before the provider is asked again, and the response reports `retry_in_seconds`.
The ban lasted roughly an hour; the hold made exactly four attempts in that
time, all logged.

`context_feed.py` had grown past the file-size limit; its three response-shape
builders moved unchanged into `context_shapes.py`.

## Live

Once the feed admitted the host again (2026-09-12 ~07:40 UTC):

```
status healthy   sources ['forexfactory']   counts total=2 high=0 market_moving=1 rejected=0
next market-moving: ECB President Lagarde Speaks  EUR  Medium  in 82m
  Medium  EUR  ECB President Lagarde Speaks   82m   market_moving=True
  Low     All  BRICS Summit                   97m   market_moving=False
```

Two events because it is Saturday and the feed is *this week*; the new week's
calendar loads when the feed rolls over. Mission Control renders the strip with
the countdown and the source line "forexfactory · FRED release dates need the
free FRED key · all events validated". FRED's official release dates join the
strip as soon as `FRED_API_KEY` is set in `runtime.env`.

## Tests

56 state-api tests pass: 11 for the calendar (offset-less dates refused rather
than guessed, malformed events dropped and counted, window edges, holidays
never market-moving, spelled-out FRED names matched like ForexFactory's
abbreviations, merge ordering) and one for the negative cache.
