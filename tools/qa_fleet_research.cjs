// Real-data rendered checks. All Fleet writes are blocked, confirmations dismissed.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const output = process.env.TRADESYNC_QA_DIR;
if (!output) throw new Error('Set TRADESYNC_QA_DIR under TradeSync Visual QA');
const base = process.env.TRADESYNC_QA_URL || 'http://127.0.0.1:3000';
(async () => {
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  const results = [];
  try {
    for (const width of [1366, 375]) {
      const page = await browser.newPage({ viewport: { width, height: 768 } });
      const errors = [], blockedWrites = [];
      page.on('pageerror', e => errors.push(e.message));
      await page.route('**/state/fleet/**', route => {
        if (route.request().method() !== 'GET') {
          blockedWrites.push(route.request().url());
          return route.abort();
        }
        return route.continue();
      });
      let confirmations = 0;
      page.on('dialog', async dialog => { confirmations++; await dialog.dismiss(); });
      await page.goto(`${base}/fleet`, { waitUntil: 'domcontentloaded' });
      await page.getByRole('combobox').first().waitFor({ timeout: 120000 });
      const select = page.getByRole('combobox').first();
      const option = await select.locator('option').nth(1).getAttribute('value');
      await select.selectOption(option);
      await page.getByRole('button', { name: 'set', exact: true }).first().click();
      assert.equal(confirmations, 1, 'Schedule change requires confirmation');
      assert.equal(blockedWrites.length, 0, 'Cancelled confirmation sends no directive');
      await page.getByRole('button', { name: 'failed jobs only', exact: true }).click();
      assert.equal(await page.getByRole('button', { name: 'failed jobs only', exact: true }).getAttribute('aria-pressed'), 'true');
      await page.getByLabel('Filter jobs').fill('no-such-job-qa');
      await page.getByText('0 shown', { exact: true }).waitFor();
      await page.getByLabel('Filter jobs').fill('');
      await page.getByRole('button', { name: 'failed jobs only', exact: true }).click();
      const fit = await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1);
      assert.equal(fit, true, `Fleet page fits ${width}`);
      await page.screenshot({ path: path.join(output, `fleet-${width}.png`) });
      results.push({ page: 'fleet', width, fit, confirmations, writes: blockedWrites.length });
      await page.goto(`${base}/signal-ledger`, { waitUntil: 'domcontentloaded' });
      const section = page.locator('[aria-labelledby="trade-research-title"]');
      await section.getByText('Recorded net', { exact: false }).waitFor({ timeout: 120000 });
      await section.getByText('Is ingested evidence influencing these trades?', { exact: true }).click();
      await section.getByText('Accepted intake', { exact: true }).waitFor({ timeout: 120000 });
      await section.scrollIntoViewIfNeeded();
      const researchFit = await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1);
      assert.equal(researchFit, true, `Ledger page fits ${width}`);
      assert.deepEqual(errors, [], 'No uncaught browser errors');
      await section.screenshot({ path: path.join(output, `research-${width}.png`) });
      const saved = section.locator('details').filter({ has: page.locator('summary', { hasText: 'BTC-PERP · swing' }) }).first();
      await saved.locator('summary').click();
      await saved.getByText('Candle opens UTC:', { exact: false }).waitFor();
      assert.ok(await saved.locator('tbody tr').count() > 0, 'Saved replay exposes individual trades');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
      await saved.screenshot({ path: path.join(output, `swing-detail-${width}.png`) });
      results.push({ page: 'research', width, fit: researchFit, errors });
      await page.close();
    }
    await fs.writeFile(path.join(output, 'acceptance.json'), JSON.stringify(results, null, 2));
    console.log(JSON.stringify(results));
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
