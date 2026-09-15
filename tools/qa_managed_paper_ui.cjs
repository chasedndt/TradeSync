const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const output = process.env.TRADESYNC_QA_DIR;
const base = process.env.TRADESYNC_COCKPIT_URL || 'http://127.0.0.1:3000';
if (!output || !output.includes('TradeSync Visual QA')) throw new Error('Set TradeSync QA directory');

// QA fixtures only: shapes the managed paper routes serve. Nothing here is a trade or a rule source.
const rules = {
  version: 'managed-paper-lifecycle-v2',
  styles: Object.fromEntries([['scalp', '15m', 900, 1.5, 0.4, 10800, 1, 1], ['intraday', '1h', 3600, 1.5, 0.8, 86400, 1, 1.25], ['swing', '4h', 14400, 2, 2, 604800, 1.5, 1.5]]
    .map(([style, atr_interval, atr_seconds, stop_atr, min_target_pct, max_hold_s, trail_activate_r, trail_atr]) => [style, { version: 'managed-paper-lifecycle-v2', style, atr_interval, atr_seconds, atr_period: 14, stop_atr, reward_risk: 2, min_target_pct, max_hold_s, trail_activate_r, trail_atr }])),
  common: { max_notional_usdc: 1000, max_planned_risk_usdc: 50, max_opportunity_age_s: 300, observation_gap_s: 45 },
  fees: { taker_fee: 0.00045, maker_fee: 0.00015, source: 'https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees', read_on: '2026-09-14' },
  fill_model: 'observed_depth_walk_v1', funding_model: 'hyperliquid_settled_hourly_v1', evidence_schema: 'managed-paper-entry-evidence-v2',
};
const snapshot = (t) => ({ source: 'hyperliquid_l2_book', precision: 'full', observed_at: t, received_at: t, best_bid: 49.99, best_ask: 50.01, bid_levels: 10, ask_levels: 10 });
const fill = (t, price) => ({ basis: 'book_walk', fill_price: price, quantity: 4.999, reference_price: price, cost_bps: 2.1, cost_usdc: 0.0525, half_spread_bps: 2, depth_bps: 0.1, total_bps: 2.1, levels_taken: [[price, 4.999]], levels_available: 10, snapshot: snapshot(t) });
const quote = (t, bid) => ({ kind: 'quote', observed_at: t, received_at: t, best_bid: bid, best_ask: bid + 0.02, touch: bid });
const position = (t, closed) => ({
  version: 'managed-paper-lifecycle-v2', status: closed ? 'closed' : 'open', side: 'long', style: 'swing', rules: rules.styles.swing, atr: 0.5,
  entry_time: t - 4000, entry_price: 50.01, quantity: 4.999, notional: 250, stop: 49.01, target: 52.01, expiry: t + 600000,
  current_stop: 49.01, current_stop_rule: 'stop', trail: { activate_price: 51.51, distance: 0.75, best: 50.2, active: false, stop: null },
  fees: { schedule: rules.fees, liquidity: 'taker', rate: 0.00045, entry_usdc: 0.1125, exit_usdc: closed ? 0.112 : null, exit_estimate_usdc: closed ? null : 0.1121 },
  slippage: { model: 'observed_depth_walk_v1', entry: fill(t - 4000, 50.01), exit: closed ? fill(t, 49.8) : null },
  funding: { model: 'hyperliquid_settled_hourly_v1', accrued_usdc: 0.0031, settled_hours: 1, expected_hours: 2, missing_hours: [Math.floor(t / 3600) * 3600], through: t, status: 'awaiting_rows' },
  gross_pnl_usdc: -1.05, fees_usdc: 0.2245, funding_usdc: 0.0031, net_estimate_usdc: -1.2776,
  last_quote_time: t - 70, observations: 2, observation_gap: true, max_observation_gap_s: 70, pending_exit: null,
  ...(closed ? { exit_reason: 'operator_close', exit_price: 49.8, exit_time: t, exit: { rule: 'operator_close', level: null, trigger_price: 49.8, gap_fill: false, path: null, ambiguous_candle: false, trigger_observation: quote(t, 49.8), fill_observation: quote(t, 49.8), fill_price: 49.8, at: t } } : { exit: null }),
});
const item = (label, status, records, extra = {}) => ({ label, source: 'QA fixture source', status, reason: status === 'missing' ? 'no liquidation received in the hour before entry' : null, coverage: null, records, newest_age_s: records.length ? 20 : null, excluded_count: 0, excluded: [], ...extra });
const evidence = (t) => ({ evidence_sha256: 'QA-FIXTURE', digest_verified: true, entry_evidence: {
  classification: 'QA FIXTURE — NOT A REAL TRADE', schema_version: 'managed-paper-entry-evidence-v2', entry_time: t - 4000,
  cutoff_rule: 'observed_at <= entry_time and received_at <= entry_time', excluded_count: 1, item_order: ['opportunity', 'features', 'liquidations'],
  items: {
    opportunity: item('Opportunity', 'present', [{ id: 'fixture-opportunity', symbol: 'HYPE-PERP', dir: 'LONG', observed_at: t - 4020, received_at: t - 4020, age_s: 20 }]),
    features: item('Feature observations', 'present', [{ id: 'spread', feature_id: 'hl_spread_bps', value: 4, observed_at: t - 4030, received_at: t - 4005, age_s: 30 }],
      { excluded_count: 1, excluded: [{ reason: 'observed after entry', observed_at: t - 3940, received_at: t - 4005, id: 'return' }] }),
    liquidations: item('Liquidations received', 'missing', []),
  },
  external_context: {
    bybit_liquidations: { status: 'no_eligible_receipts', cutoff: t - 4003, events: [], excluded: 2, scoring_influence: false, coverage: 'QA fixture: empty receipts do not establish zero market liquidations.' },
    hyperliquid_book_history: { status: 'unavailable', cutoff: t - 4003, samples: [], scoring_influence: false, reason: 'QA timeout' },
  },
} });

(async () => {
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  const results = [];
  try {
    for (const width of [1366, 375]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const errors = []; page.on('pageerror', e => errors.push(e.message));
      await page.goto(`${base}/signal-ledger`);
      const panel = page.getByRole('region', { name: 'Managed paper positions', exact: true });
      await panel.getByText(/No managed paper positions yet/).waitFor();
      await panel.screenshot({ path: path.join(output, `paper-live-empty-${width}.png`) });
      let opened = false, closed = false, evidenceRead = false, fundingRead = false, accepted = false, paused = true;
      await page.route('**/state/paper-control', route => {
        if (route.request().method() === 'POST') {
          assert.equal(route.request().postDataJSON().reason, 'QA explicit resume');
          paused = route.request().postDataJSON().entries_paused;
        }
        return route.fulfill({ json: { entries_paused: paused, reason: 'QA control fixture', updated_at: new Date().toISOString() } });
      });
      page.on('dialog', d => accepted ? d.accept() : d.dismiss());
      await page.route('**/state/paper-positions**', route => {
        const request = route.request(), url = request.url(), t = Date.now() / 1000;
        if (url.endsWith('/source-comparison')) {
          const summary = { eligible: 0, context_available: 0, selected: 0, abstained: 0, baseline_mean_bps_per_opportunity: null, filter_mean_bps_per_opportunity: null, paired_mean_difference_bps: null, excluded: {}, note: 'QA FIXTURE — NOT STRATEGY PERFORMANCE' };
          return route.fulfill({ json: { summary, cohorts: [{ style: 'scalp', ...summary }], records_considered: 0, truncated: false, scope: 'QA fixture only' } });
        }
        if (url.endsWith('/candidates')) return route.fulfill({ json: { universe: ['BTC-PERP', 'HYPE-PERP'], max_age_s: 300, checked_at: t, symbols_without_candidate: ['BTC-PERP'],
          candidates: [{ id: 'fixture-opportunity', symbol: 'HYPE-PERP', timeframe: '1m', dir: 'LONG', direction: 'long', bias: 0.2, quality: 50, snapshot_ts: new Date().toISOString(), expires_at: null, age_s: 20, position_id: null }] } });
        if (url.endsWith('/rules')) return route.fulfill({ json: rules });
        if (url.endsWith('/evidence')) { evidenceRead = true; return route.fulfill({ json: evidence(t) }); }
        if (url.endsWith('/funding')) { fundingRead = true; return route.fulfill({ json: { model: rules.funding_model, note: 'QA fixture', rows: [{ settled_at: Math.floor(t / 3600) * 3600 - 3600, funding_rate: 0.0000125, premium: -0.0001, side: 'long', quantity: 4.999, price: 50.02, price_source: 'market_open_interest.oracle_price', price_observed_at: Math.floor(t / 3600) * 3600 - 3620, payment_usdc: 0.0031, received_at: Math.floor(t / 3600) * 3600 - 3590, recorded_at: Math.floor(t / 3600) * 3600 - 3589 }] } }); }
        if (url.endsWith('/close')) { closed = true; return route.fulfill({ json: position(t, true) }); }
        if (request.method() === 'POST') {
          assert.deepEqual(request.postDataJSON(), { opportunity_id: 'fixture-opportunity', style: 'swing', notional: 250 });
          opened = true; return route.fulfill({ json: { duplicate: false } });
        }
        return route.fulfill({ json: { worker: { last_tick: t, last_error: null }, note: 'QA FIXTURE — NO LIVE PORTFOLIO WRITES', positions: opened ? [{ id: 'fixture-position', symbol: 'HYPE-PERP', evidence_sha256: 'a'.repeat(64), position_state: position(t, closed) }] : [] } });
      });
      await page.reload();
      await panel.getByLabel('Paper control reason').fill('QA explicit resume');
      await panel.getByRole('button', { name: 'Resume new paper entries', exact: true }).click();
      assert.equal(paused, true);
      accepted = true;
      await panel.getByRole('button', { name: 'Resume new paper entries', exact: true }).click();
      await panel.getByRole('button', { name: 'Pause new paper entries', exact: true }).waitFor();
      accepted = false;
      await panel.getByText(/Universe read from the API at/).waitFor();
      await panel.getByLabel('Current opportunity').selectOption('fixture-opportunity');
      await panel.getByLabel('Holding style').selectOption('swing');
      await panel.getByText(/Rules for swing: stop 2 × ATR/).waitFor();
      await panel.getByRole('button', { name: 'Open paper position', exact: true }).click();
      assert.equal(opened, false, 'Dismiss must not write');
      accepted = true;
      await panel.getByRole('button', { name: 'Open paper position', exact: true }).click();
      await panel.getByText(/Observation gap recorded/).waitFor();
      await panel.getByText('Trailing stop', { exact: true }).waitFor();
      await panel.getByText(/Starts once the exit-side price reaches/).waitFor();
      await panel.getByRole('columnheader', { name: 'How it was measured' }).waitFor();
      await panel.getByText(/Not settled yet:/).waitFor();
      await panel.getByRole('button', { name: 'Show funding rows', exact: true }).click();
      await panel.getByText(/oracle price seen/).waitFor();
      await panel.getByRole('button', { name: 'Inspect frozen entry evidence' }).click();
      await panel.getByText(/matches the stored record/).waitFor();
      await panel.getByText('Feature observations', { exact: true }).waitFor();
      await panel.getByText(/missing: no liquidation received in the hour before entry/).waitFor();
      await panel.getByText('Bybit liquidation receipts', { exact: true }).waitFor();
      await panel.getByText('Unavailable reason: QA timeout', { exact: true }).waitFor();
      await panel.getByText('Raw frozen record', { exact: true }).click();
      await panel.getByText(/NOT A REAL TRADE/).waitFor();
      assert.equal(evidenceRead, true);
      assert.equal(fundingRead, true);
      await panel.screenshot({ path: path.join(output, `paper-fixture-open-${width}.png`) });
      await panel.getByRole('button', { name: 'Close paper position', exact: true }).click();
      await panel.getByText(/Exit: operator close at/).waitFor();
      await panel.getByText(/Fired by the quote at/).waitFor();
      assert.equal(closed, true);
      await panel.screenshot({ path: path.join(output, `paper-fixture-closed-${width}.png`) });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
      assert.deepEqual(errors, []);
      results.push({ width, liveEmptyReadback: true, fixtureOpenCloseEvidence: true, rulesCostsFundingShown: true, dismissedOpenNoWrite: true, noOverflow: true, noPageErrors: true });
      await page.close();
    }
    await fs.writeFile(path.join(output, 'results.json'), JSON.stringify(results, null, 2));
    console.log(JSON.stringify(results));
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
