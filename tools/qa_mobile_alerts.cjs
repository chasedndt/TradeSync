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
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      await page.goto('http://127.0.0.1:3000/settings');
      const panel = page.getByRole('region', { name: 'Mobile notifications' });
      await panel.getByText(/Setup required/).waitFor();
      await panel.screenshot({ path: path.join(output, `mobile-live-setup-${width}.png`) });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
      let enrolled = false, sent = false, confirmed = false, preferencesSaved = false;
      await page.route('**/state/mobile-alerts/**', async route => {
        const url = route.request().url(), method = route.request().method();
        if (url.endsWith('/status')) return route.fulfill({ json: { configured: true, worker_running: true, note: 'QA FIXTURE — NO EXTERNAL DELIVERY' } });
        if (method === 'POST' && url.endsWith('/devices')) {
          const body = route.request().postDataJSON();
          assert.equal(body.platform, 'ios'); assert.equal(body.public_topic_generic_only_consent, true);
          enrolled = true;
          return route.fulfill({ json: { topic: 'QA-FIXTURE-NOT-A-SUBSCRIPTION', note: 'Fixture enrollment; no external send' } });
        }
        if (method === 'POST' && url.endsWith('/test')) { sent = true; return route.fulfill({ json: { status: 'fixture_test_queued' } }); }
        if (method === 'POST' && url.endsWith('/preferences')) {
          const body = route.request().postDataJSON();
          assert.equal(body.paper_events, false); assert.equal(body.timezone, 'Europe/London'); assert.equal(body.daily_budget, 5);
          preferencesSaved = true; return route.fulfill({ json: { status: 'preferences_saved' } });
        }
        if (url.endsWith('/confirm')) { confirmed = true; return route.fulfill({ json: { status: 'unexpected' } }); }
        return route.fulfill({ json: { devices: enrolled ? [{ id: 'fixture-device', label: 'QA iPhone', platform: 'ios', enabled: true, operator_confirmed_at: null }] : [], events: sent ? [{ id: 'fixture-event', device_id: 'fixture-device', kind: 'test', status: 'provider_accepted', attempts: 1, created_at: new Date().toISOString() }] : [] } });
      });
      await page.reload();
      await panel.getByLabel('Phone platform', { exact: true }).selectOption('ios');
      await panel.getByLabel('Device label', { exact: true }).fill('QA iPhone');
      await panel.getByRole('checkbox').check();
      await panel.getByRole('button', { name: 'Create subscription details — sends nothing', exact: true }).click();
      await panel.getByRole('button', { name: 'Send generic test', exact: true }).click();
      page.on('dialog', dialog => dialog.dismiss());
      await panel.getByRole('button', { name: 'I received this on my phone', exact: true }).click();
      assert.equal(confirmed, false);
      await panel.getByText('Paper lifecycle notification preferences', { exact: true }).click();
      assert.equal(await panel.getByLabel('Notify me when a managed paper position opens or closes').isDisabled(), true);
      await panel.getByLabel('Maximum lifecycle messages per rolling 24 hours').fill('5');
      await panel.getByRole('button', { name: 'Save notification preferences', exact: true }).click();
      await panel.getByText('preferences_saved', { exact: true }).waitFor();
      assert.equal(preferencesSaved, true);
      await panel.screenshot({ path: path.join(output, `mobile-fixture-${width}.png`) });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
      assert.deepEqual(errors, []);
      results.push({ width, realSetupRequired: true, fixtureEnrollmentAndTest: true, dismissedReceiptSendsNothing: true, unconfirmedOptInBlocked: true, preferencesSaved: true, noOverflow: true });
      await page.close();
    }
    await fs.writeFile(path.join(output, 'results.json'), JSON.stringify(results, null, 2));
    console.log(JSON.stringify(results));
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
