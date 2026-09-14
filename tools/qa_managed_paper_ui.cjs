const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const output = process.env.TRADESYNC_QA_DIR;
if (!output || !output.includes('TradeSync Visual QA')) throw new Error('Set TradeSync QA directory');
(async () => {
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  const results = [];
  try {
    for (const width of [1366, 375]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const errors = []; page.on('pageerror', e => errors.push(e.message));
      await page.goto('http://127.0.0.1:3000/signal-ledger');
      const panel = page.getByRole('region', { name: 'Managed paper positions', exact: true });
      await panel.getByText(/No managed paper positions yet/).waitFor();
      await panel.screenshot({ path: path.join(output, `paper-live-empty-${width}.png`) });
      const comparison = page.getByRole('region', { name: 'Does liquidity context help?', exact: true });
      await comparison.getByText(/No clean closed managed-paper trades/).waitFor();
      await comparison.screenshot({ path: path.join(output, `comparison-live-empty-${width}.png`) });
      let opened = false, closed = false, evidenceRead = false, accepted = false;
      let paused = true;
      await page.route('**/state/paper-control', route => {
        if (route.request().method() === 'POST') {
          assert.equal(route.request().postDataJSON().reason, 'QA explicit resume');
          paused = route.request().postDataJSON().entries_paused;
        }
        return route.fulfill({json:{entries_paused:paused,reason:'QA control fixture',updated_at:new Date().toISOString()}});
      });
      page.on('dialog', d => accepted ? d.accept() : d.dismiss());
      await page.route('**/state/opportunities?**', route => route.fulfill({ json: [{ id: 'fixture-opportunity', symbol: 'BTC-PERP', dir: 'long', timeframe: '1h', snapshot_ts: new Date().toISOString() }] }));
      await page.route('**/state/paper-positions**', route => {
        const request = route.request(), url = request.url();
        if (url.endsWith('/source-comparison')) {
          const summary = { eligible:2, context_available:1, selected:1, abstained:1, baseline_mean_bps_per_opportunity:-50, filter_mean_bps_per_opportunity:50, paired_mean_difference_bps:100, excluded:{observation_gap:1}, note:'QA FIXTURE — NOT STRATEGY PERFORMANCE' };
          return route.fulfill({ json: { summary, cohorts:[{style:'scalp',...summary}], records_considered:3, truncated:false, scope:'QA fixture only' } });
        }
        if (url.endsWith('/evidence')) { evidenceRead = true; return route.fulfill({ json: { evidence_sha256: 'QA-FIXTURE', entry_evidence: { classification: 'QA FIXTURE — NOT A REAL TRADE', external_context: {
          bybit_liquidations: { status: 'no_eligible_receipts', cutoff: Date.now()/1000, events: [], excluded: 2, scoring_influence: false, coverage: 'QA fixture: empty receipts do not establish zero market liquidations.' },
          hyperliquid_book_history: { status: 'unavailable', cutoff: Date.now()/1000, samples: [], scoring_influence: false, reason: 'QA timeout' }
        } } } }); }
        if (url.endsWith('/close')) { closed = true; return route.fulfill({ json: { status: 'closed' } }); }
        if (request.method() === 'POST') {
          assert.deepEqual(request.postDataJSON(), { opportunity_id: 'fixture-opportunity', style: 'swing', notional: 250 });
          opened = true; return route.fulfill({ json: { duplicate: false } });
        }
        const now = Date.now() / 1000;
        return route.fulfill({ json: { worker: { last_tick: now, last_error: null }, note: 'QA FIXTURE — NO LIVE PORTFOLIO WRITES', positions: opened ? [{ id: 'fixture-position', symbol: 'BTC-PERP', evidence_sha256: 'a'.repeat(64), position_state: { status: closed ? 'closed' : 'open', side: 'long', style: 'swing', entry_price: 77000, stop: 76000, target: 79000, notional: 250, expiry: now + 60000, last_quote_time: now - 70, observations: 2, net_estimate_usdc: -1.23, fees_usdc: .23, funding_scenario_usdc: .01, observation_gap: true, max_observation_gap_s: 70, ...(closed ? { exit_reason: 'operator_close', exit_price: 76700 } : {}) } }] : [] } });
      });
      await page.reload();
      await panel.getByLabel('Paper control reason').fill('QA explicit resume');
      await panel.getByRole('button', {name:'Resume new paper entries',exact:true}).click();
      assert.equal(paused,true);
      accepted=true;
      await panel.getByRole('button', {name:'Resume new paper entries',exact:true}).click();
      await panel.getByRole('button', {name:'Pause new paper entries',exact:true}).waitFor();
      accepted=false;
      await comparison.getByText('100 bps', { exact: true }).waitFor();
      await comparison.getByText('Rule, exclusions and limits', { exact: true }).click();
      await comparison.screenshot({ path: path.join(output, `comparison-fixture-${width}.png`) });
      await panel.getByLabel('Current opportunity').selectOption('fixture-opportunity');
      await panel.getByLabel('Holding style').selectOption('swing');
      await panel.getByRole('button', { name: 'Open paper position', exact: true }).click();
      assert.equal(opened, false, 'Dismiss must not write');
      accepted = true;
      await panel.getByRole('button', { name: 'Open paper position', exact: true }).click();
      await panel.getByText(/Observation gap recorded/).waitFor();
      await panel.getByRole('button', { name: 'Inspect frozen entry evidence' }).click();
      await panel.getByText('Bybit liquidation receipts', { exact: true }).waitFor();
      await panel.getByText('Unavailable reason: QA timeout', { exact: true }).waitFor();
      await panel.getByText('Raw frozen record', { exact: true }).click();
      await panel.getByText(/NOT A REAL TRADE/).waitFor();
      assert.equal(evidenceRead, true);
      await panel.screenshot({ path: path.join(output, `paper-fixture-open-${width}.png`) });
      await panel.getByRole('button', { name: 'Close paper position', exact: true }).click();
      await panel.getByText(/Exit: operator close/).waitFor();
      assert.equal(closed, true);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
      assert.deepEqual(errors, []);
      results.push({ width, liveEmptyReadback: true, fixtureOpenCloseEvidence: true, dismissedOpenNoWrite: true, noOverflow: true, noPageErrors: true });
      await page.close();
    }
    await fs.writeFile(path.join(output, 'results.json'), JSON.stringify(results, null, 2));
    console.log(JSON.stringify(results));
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
