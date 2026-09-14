// Read-only acceptance against the running cockpit. No job or trading actions.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');

const output = process.env.TRADESYNC_QA_DIR;
if (!output) throw new Error('Set TRADESYNC_QA_DIR to the TradeSync Visual QA review directory');
const base = process.env.TRADESYNC_QA_URL || 'http://127.0.0.1:3000';

(async () => {
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  const results = [];
  try {
    for (const width of [1366, 1024, 768, 375]) {
      const page = await browser.newPage({ viewport: { width, height: 768 } });
      await page.goto(base, { waitUntil: 'domcontentloaded' });
      const card = page.locator('[aria-labelledby="context-title"]');
      await card.waitFor();
      await page.waitForFunction(() => document.querySelector('.context-assets')?.textContent.includes('$'), null, { timeout: 90000 });
      await card.scrollIntoViewIfNeeded();
      const fit = await card.evaluate(el => {
        const box = el.getBoundingClientRect();
        const overflow = [...el.querySelectorAll('*')].filter(child => {
          const r = child.getBoundingClientRect();
          return r.width && (r.right > box.right + 1 || r.left < box.left - 1 || child.scrollWidth > child.clientWidth + 1);
        }).map(child => child.className?.baseVal ?? child.className);
        return { width: box.width, overflow };
      });
      assert.deepEqual(fit.overflow, [], `Context overflow at ${width}: ${JSON.stringify(fit)}`);
      await card.screenshot({ path: path.join(output, `context-${width}.png`) });
      results.push({ page: 'context', viewport: width, ...fit });
      await page.close();
    }
    for (const width of [1366, 375]) {
      const page = await browser.newPage({ viewport: { width, height: 768 } });
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      await page.goto(`${base}/timeframes?symbol=ETH-PERP`, { waitUntil: 'domcontentloaded' });
      await page.locator('#feature-trend').waitFor({ timeout: 120000 });
      const trend = page.getByRole('button', { name: 'Trend', exact: true }).first();
      await trend.click();
      await page.locator('#feature-trend canvas').first().waitFor({ timeout: 120000 });
      await page.waitForTimeout(1100);
      const position = await page.locator('#feature-trend').evaluate(el => {
        const r = el.getBoundingClientRect();
        return { inView: r.top < innerHeight && r.bottom > 0, overflow: document.documentElement.scrollWidth > innerWidth + 1 };
      });
      assert.equal(position.inView, true, 'Feature link must scroll into view');
      assert.equal(position.overflow, false, 'Timeframes must fit viewport');
      assert.deepEqual(errors, [], 'No uncaught chart errors');
      await page.screenshot({ path: path.join(output, `timeframes-${width}.png`) });
      results.push({ page: 'timeframes-ETH', viewport: width, ...position, errors });
      await page.close();
    }
    await fs.writeFile(path.join(output, 'acceptance.json'), JSON.stringify(results, null, 2));
    console.log(JSON.stringify(results, null, 2));
  } finally { await browser.close(); }
})().catch(e => { console.error(e.message); process.exitCode = 1; });
