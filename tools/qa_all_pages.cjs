// Visits every Cockpit page at desktop and phone widths and records page errors, console
// errors, horizontal overflow (with the elements causing it) and a screenshot of each page.
// Usage: set TRADESYNC_QA_DIR to a folder under "TradeSync Visual QA", then
//   node tools/qa_all_pages.cjs
const { chromium } = require('playwright');
const fs = require('node:fs/promises');
const path = require('node:path');

const output = process.env.TRADESYNC_QA_DIR;
if (!output || !output.includes('TradeSync Visual QA')) throw new Error('Set TRADESYNC_QA_DIR to a folder under TradeSync Visual QA');
const base = process.env.TRADESYNC_QA_BASE || 'http://127.0.0.1:3000';
const ROUTES = ['/', '/thesis', '/timeframes', '/market', '/canvas', '/opportunities', '/signal-ledger', '/agents', '/fleet',
  '/regime-lab', '/pipeline', '/intake', '/logs', '/execution', '/positions', '/risk-policies', '/settings', '/sources',
  '/copilot', '/autonomy'];
const WIDTHS = [1366, 375];

// Runs in the page: elements reaching past the viewport that no scrolling container holds.
function overflowProbe() {
  const limit = window.innerWidth + 1;
  const contained = (el) => {
    for (let node = el.parentElement; node && node !== document.body; node = node.parentElement) {
      if (/(auto|scroll|hidden|clip)/.test(getComputedStyle(node).overflowX)) return true;
    }
    return false;
  };
  const offenders = [];
  for (const el of document.querySelectorAll('body *')) {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.right <= limit || contained(el)) continue;
    const cls = typeof el.className === 'string' && el.className ? `.${el.className.trim().split(/\s+/).slice(0, 2).join('.')}` : '';
    offenders.push(`${el.tagName.toLowerCase()}${cls} right=${Math.round(rect.right)}`);
    if (offenders.length >= 5) break;
  }
  return { documentWidth: document.documentElement.scrollWidth, viewport: window.innerWidth, offenders };
}

(async () => {
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  const results = [];
  try {
    for (const width of WIDTHS) {
      const phone = width < 768;
      const context = await browser.newContext({ viewport: { width, height: 900 }, isMobile: phone, hasTouch: phone });
      for (const route of ROUTES) {
        const page = await context.newPage();
        const errors = [];
        page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
        page.on('console', (m) => { if (m.type() === 'error') errors.push(`console: ${m.text().slice(0, 200)}`); });
        await page.goto(base + route, { waitUntil: 'domcontentloaded' });
        await page.waitForFunction(() => !document.body.innerText.includes('Loading page…'), null, { timeout: 20000 })
          .catch(() => errors.push('page code did not load within 20 s'));
        await page.waitForTimeout(3500);
        const layout = await page.evaluate(overflowProbe);
        const screenshot = `${route === '/' ? 'home' : route.slice(1).replace(/\//g, '-')}-${width}.png`;
        await page.screenshot({ path: path.join(output, screenshot) });
        results.push({ route, width, errors, overflow: layout.documentWidth > layout.viewport + 1, ...layout, screenshot });
        await page.close();
      }
      await context.close();
    }
  } finally {
    await browser.close();
  }
  await fs.writeFile(path.join(output, 'summary.json'), JSON.stringify(results, null, 2));
  for (const r of results) {
    const findings = [r.overflow && 'page overflows', r.offenders.length && `${r.offenders.length} wide elements`, r.errors.length && `${r.errors.length} errors`].filter(Boolean);
    console.log(`${r.width}px ${r.route}: ${findings.length ? findings.join(', ') : 'ok'}`);
  }
  const failing = results.filter((r) => r.errors.length || r.overflow || r.offenders.length);
  console.log(`${results.length} page views, ${failing.length} with findings; summary.json in ${output}`);
  process.exitCode = failing.length ? 1 : 0;
})();
