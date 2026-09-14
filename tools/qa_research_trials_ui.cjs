const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const output = process.env.TRADESYNC_QA_DIR;
if (!output?.includes('TradeSync Visual QA')) throw new Error('Set project QA directory');
(async () => {
  await fs.mkdir(output, {recursive:true});
  const browser = await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
  try {
    for (const width of [1366,375]) {
      const page = await browser.newPage({viewport:{width,height:900}});
      const errors=[]; page.on('pageerror',e=>errors.push(e.message));
      await page.goto('http://127.0.0.1:3000/signal-ledger');
      const panel=page.getByRole('region',{name:'Registered forward research',exact:true});
      await panel.getByText(/No registered trials yet/).waitFor();
      let created=false, accept=false;
      page.on('dialog',d=>accept?d.accept():d.dismiss());
      await page.route('**/state/research-trials**',route=>{
        if(route.request().url().endsWith('/evaluation')) return route.fulfill({json:{state:'collecting',pending_outcomes:1,comparison:{eligible:0,context_available:0,paired_mean_difference_bps:null},note:'QA FIXTURE — NO FORWARD EVIDENCE'}});
        if(route.request().method()==='POST') { assert.equal(route.request().postDataJSON().style,'swing'); created=true; return route.fulfill({json:{duplicate:false}}); }
        return route.fulfill({json:{trials:created?[{id:'fixture',registered_at:new Date().toISOString(),specification_sha256:'a'.repeat(64),specification:{style:'swing',classification:'QA FIXTURE',promotion:'Never automatic'}}]:[]}});
      });
      await panel.getByLabel('Trial holding style').selectOption('swing');
      await panel.getByRole('button',{name:'Register fixed research protocol'}).click();
      assert.equal(created,false);
      accept=true;
      await panel.getByRole('button',{name:'Register fixed research protocol'}).click();
      await panel.getByText(/swing · registered/).click();
      await panel.getByText(/NO FORWARD EVIDENCE/).waitFor();
      await panel.getByText('Frozen specification',{exact:true}).click();
      await panel.screenshot({path:path.join(output,`trial-fixture-${width}.png`)});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
      assert.deepEqual(errors,[]);
      await page.close();
    }
    console.log('PASS: live empty registry, cancelled registration no write, fixture registration/evaluation/specification, 1366/375px no overflow/errors. No public trial created.');
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
