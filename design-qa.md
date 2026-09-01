# Design QA — TradeSync Mission Control

## Comparison target

- Source visual truth: `E:\Visual QA\TradeSync Visual QA\Current Reviews\2026-09-01-dashboard-overhaul-audit\Redesign Directions\01-mission-control.png`
- Source pixels: 1487×1058.
- Intended implementation viewport: 1440×1024 CSS pixels at device scale factor 1.
- Implementation URL: `http://localhost:3000/`
- Implementation screenshot: unavailable.
- State: live Hyperliquid market data, no scoring output, execution disabled, CoinGecko and DefiLlama healthy, FRED unconfigured.
- Density normalization: not performed because a browser-rendered implementation capture could not be obtained.

## Findings

- [P0] Browser-rendered comparison evidence is unavailable
  - Location: full Mission Control screen and responsive breakpoints.
  - Evidence: the Docker cockpit is healthy and the production frontend build passed, but every in-app browser control attempt failed with `Transport closed` before the tab could be captured.
  - Impact: typography, spacing, colors, icon fidelity, live copy, interactions, console state, and viewport overflow cannot be truthfully passed from source code or HTTP readback.
  - Fix: restore the in-app browser connection or obtain operator approval to use the Playwright CLI as a fallback; capture the implementation at 1440×1024, 834×1194, and 390×844.

## Required fidelity surfaces

- Fonts and typography: blocked pending rendered comparison.
- Spacing and layout rhythm: blocked pending rendered comparison.
- Colors and visual tokens: blocked pending rendered comparison.
- Image quality and asset fidelity: source uses standard UI/market icons rather than raster imagery; rendered icon fidelity remains blocked.
- Copy and content: code review confirms the intended authority and safety language, but rendered wrapping/truncation remains blocked.
- Interactions and responsiveness: mobile drawer, navigation, loading/empty/live states, keyboard focus, console errors, and horizontal overflow remain blocked.

## Full-view and focused-region evidence

- Source visual was opened at original resolution.
- No implementation screenshot exists, so a combined comparison input could not be created.
- Focused region comparison was not attempted because the required full-view implementation artifact is missing.

## Comparison history

1. Initial pass: blocked before capture. The in-app browser automation transport disconnected after the healthy Docker replacement.
2. Recovery attempts: repeated browser connection and runtime reset attempts returned the same `Transport closed` error.
3. No visual fixes were claimed from this pass because no valid rendered comparison was available.

## Implementation checklist

- [x] Production TypeScript/Vite build passes.
- [x] Docker cockpit image rebuilt and container healthy.
- [x] Live API readback confirms BTC, ETH, SOL and disabled execution.
- [x] Context-feed tests pass.
- [ ] Capture desktop implementation and console state.
- [ ] Create combined source/implementation comparison input.
- [ ] Fix all P0/P1/P2 desktop differences.
- [ ] Capture and fix tablet and mobile overflow/interactions.
- [ ] Repeat visual comparison and change final result only after evidence passes.

## Follow-up polish

No P3 items are classified until the blocking rendered comparison is available.

final result: blocked
