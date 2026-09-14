const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const output = process.env.TRADESYNC_QA_DIR;
if (!output || !output.includes('TradeSync Visual QA')) throw new Error('Set project-specific TRADESYNC_QA_DIR');
(async () => {
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  const results = [];
  try {
    for (const width of [1366, 375]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      await page.goto('http://127.0.0.1:3000/market', { waitUntil: 'domcontentloaded' });
      const heatmap = page.getByRole('region', { name: 'Observed liquidity history' });
      await heatmap.getByRole('img').waitFor({ timeout: 90000 });
      await page.getByText('Bybit liquidation events · context only', { exact: true }).waitFor();
      await heatmap.getByRole('combobox', { name: 'Liquidity history window' }).selectOption('3600');
      await heatmap.getByRole('img', { name: /60 minutes/ }).waitFor();
      await heatmap.getByRole('combobox', { name: 'Liquidity history window' }).selectOption('900');
      await heatmap.getByRole('img', { name: /15 minutes/ }).waitFor();
      if (width < 640) await heatmap.locator('svg').evaluate(svg => { svg.parentElement.scrollLeft = svg.parentElement.scrollWidth; });
      await heatmap.screenshot({ path: path.join(output, `heatmap-${width}.png`) });
      await page.getByRole('heading', { name: 'Liquidations', exact: true }).locator('xpath=ancestor::div[contains(@class,"card")][1]').screenshot({ path: path.join(output, `liquidations-${width}.png`) });
      const overflowMarket = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
      assert.equal(overflowMarket, false);
      await page.goto('http://127.0.0.1:3000/timeframes', { waitUntil: 'domcontentloaded' });
      const horizons = page.getByRole('region', { name: 'Trading-day horizons' });
      await horizons.getByRole('heading', { name: '8 hours', exact: true }).waitFor({ timeout: 90000 });
      await horizons.getByRole('heading', { name: '1 day', exact: true }).waitFor();
      await horizons.screenshot({ path: path.join(output, `intraday-${width}.png`) });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
      assert.deepEqual(errors, []);
      results.push({ width, marketHeatmap: 'rendered real observations', intraday: 'rendered', overflow: false, errors });
      await page.close();
    }
    await fs.writeFile(path.join(output, 'results.json'), JSON.stringify(results, null, 2));
    console.log(JSON.stringify(results));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
