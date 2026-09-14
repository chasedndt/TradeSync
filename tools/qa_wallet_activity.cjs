// Fixture rendering is deliberately separate from live public-API verification.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const output = process.env.TRADESYNC_QA_DIR;
if (!output || !output.includes('TradeSync Visual QA')) throw new Error('Set TradeSync QA directory');
const address = '0x' + 'a'.repeat(40);
(async () => {
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  const results = [];
  try {
    for (const width of [1366, 375]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const errors = [], calls = [];
      page.on('pageerror', e => errors.push(e.message));
      await page.route('**/state/execution/wallet-*', async route => {
        const url = route.request().url(); calls.push(url);
        const now = new Date().toISOString();
        const body = url.includes('wallet-preview') ? { configured: true, authority: 'read_only', address, network: 'QA FIXTURE — NOT A REAL ACCOUNT', observed_at: now, account_value_usd: 1000, withdrawable_usd: 900, total_margin_used_usd: 100, open_positions: [{ symbol: 'BTC-PERP', side: 'LONG', size: .01, entry_price: 60000, unrealized_pnl: 3, leverage: 2, liquidation_price: 30000 }] } : { open_orders: { status: 'available', observed_at: now, received_count: 1, invalid_rows: 0, rows: [{ instrument: 'BTC', side: 'SELL', price: 59000, size: .01, time_ms: Date.now(), order_id: '123', order_type: 'Stop Market', reduce_only: true, is_trigger: true, trigger_price: 59000, trigger_condition: 'Price below 59000' }] }, recent_fills: { status: 'unavailable', observed_at: null, rows: null }, note: 'QA FIXTURE. Partial source failure must not hide valid open orders.' };
        await route.fulfill({ json: body });
      });
      await page.goto('http://127.0.0.1:3000/execution', { waitUntil: 'domcontentloaded' });
      await page.getByRole('textbox', { name: 'Public account address' }).fill(address);
      await page.getByRole('button', { name: 'View account', exact: true }).click();
      await page.getByText('QA FIXTURE — NOT A REAL ACCOUNT', { exact: false }).waitFor();
      await page.getByRole('heading', { name: 'Reported open orders' }).waitFor();
      await page.getByText('Unavailable — not interpreted as no activity.', { exact: true }).waitFor();
      const panel = page.getByRole('heading', { name: 'Watch-only account', exact: true }).locator('xpath=ancestor::section[1]');
      await panel.screenshot({ path: path.join(output, `wallet-fixture-${width}.png`) });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
      await page.getByRole('checkbox').check();
      await page.getByRole('button', { name: 'Clear account', exact: true }).click();
      await page.getByRole('region', { name: 'Read-only wallet activity' }).waitFor({ state: 'detached' });
      assert.equal(await page.getByRole('textbox', { name: 'Public account address' }).inputValue(), '');
      assert.deepEqual(errors, []);
      results.push({ width, fixture: true, validOrdersBesideUnavailableFills: true, clearWorks: true, noOverflow: true, errors, readRequests: calls.length });
      await page.close();
    }
    await fs.writeFile(path.join(output, 'wallet-results.json'), JSON.stringify(results, null, 2));
    console.log(JSON.stringify(results));
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
