// No wallet credentials, provider IDs or live pairing are used by this check.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');

(async () => {
  const evidence = 'E:/Visual QA/TradeSync Visual QA/Current Reviews/2026-09-09-walletconnect-setup';
  await fs.mkdir(evidence, { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe' });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const failures = [], relay = [];
    page.on('pageerror', error => failures.push(error.message));
    page.on('request', request => { if (/walletconnect|reown/.test(new URL(request.url()).hostname)) relay.push(request.url()); });
    await page.goto('http://127.0.0.1:3000/execution', { waitUntil: 'domcontentloaded' });
    await page.getByRole('heading', { name: 'Pair a wallet by QR' }).waitFor();
    const pair = page.getByRole('button', { name: 'Pair wallet — address only', exact: true });
    assert.equal(await pair.isDisabled(), true);
    await page.getByRole('textbox', { name: 'Public WalletConnect project ID', exact: true }).fill('not-a-project');
    assert.equal(await pair.isDisabled(), true);
    await page.getByRole('textbox', { name: 'Public WalletConnect project ID', exact: true }).fill('');
    await page.getByRole('textbox', { name: 'Public account address', exact: true }).fill('invalid');
    await page.getByRole('button', { name: 'View account', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: 'Enter a public EVM address' }).waitFor();
    await page.getByRole('button', { name: 'Clear account', exact: true }).click();
    await page.screenshot({ path: path.join(evidence, 'execution-desktop.png'), fullPage: true, animations: 'disabled' });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(evidence, 'execution-mobile.png'), fullPage: true, animations: 'disabled' });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    assert.equal(overflow, false, 'Mobile page must not overflow horizontally');
    assert.deepEqual(relay, [], 'No provider contact before pairing consent');
    assert.deepEqual(failures, [], 'No JavaScript page errors');
    console.log(JSON.stringify({ setupScreen: 'passed', invalidProject: 'passed', invalidAddress: 'passed', noProviderRequests: true, mobileOverflow: overflow, pageErrors: failures, evidence }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
