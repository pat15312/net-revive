// Run against tests/browser/server.py only: this suite simulates PoE restarts.
require('node:fs').mkdirSync('test-results', {recursive:true});
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
try{
 const page=await browser.newPage({viewport:{width:1360,height:1000}});const errors=[],remote=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(!r.url().startsWith('http://127.0.0.1:8019'))remote.push(r.url());});
 await page.goto('http://127.0.0.1:8019/');
 await page.getByLabel('Administrator password',{exact:true}).fill('browser-testing-password');
 await page.getByLabel('Confirm password').fill('browser-testing-password');
 await page.getByRole('button',{name:'Create password & continue'}).click();
 await page.getByLabel('Application display title').waitFor();
 await page.getByRole('button',{name:'Save general settings'}).click();
 await page.getByRole('button',{name:'Continue →'}).click();
 await page.getByLabel('Controller URL').fill('https://controller.test');
 await page.getByLabel('API key',{exact:true}).fill('browser-test-api-key');
 await page.getByLabel('Verify the controller’s TLS certificate (recommended)').uncheck();
 const draftRequest=page.waitForRequest(r=>r.url().endsWith('/api/admin/unifi/test'));
 await page.getByRole('button',{name:'Test UniFi connection'}).click();
 assert.equal((await draftRequest).postDataJSON().verify_tls,false);
 await page.getByText('Connected and authenticated. These settings have not been saved. Click Save connection to use them.',{exact:true}).waitFor();
 assert.equal(await page.getByLabel('API key',{exact:true}).inputValue(),'browser-test-api-key');
 assert.equal((await (await page.request.get('http://127.0.0.1:8019/api/admin/config')).json()).settings.api_key_configured,false);
 await page.getByRole('button',{name:'Save connection',exact:true}).click();
 await page.getByLabel('Replace API key (leave blank to keep it)').waitFor();
 await page.getByLabel('UniFi site',{exact:true}).selectOption('site-a');
 await page.getByRole('button',{name:'Save site & discover ports'}).click();
 await page.getByText('Discovered PoE ports',{exact:true}).waitFor();
 await page.getByRole('button',{name:'Continue →'}).click();
 await page.getByLabel('Group name',{exact:true}).fill('Router');
 await page.getByLabel('Button label',{exact:true}).fill('Restart Router');
 await page.getByLabel('Description (optional)').fill('Restarts the equipment that connects you to the internet.');
 await page.locator('input[name=target_ids][value="1"]').check();
 await page.locator('input[name=confirm_targets]').check();
 await page.getByRole('button',{name:'Save restart group'}).click();
 await page.getByText('Restart Router · 1 target · Enabled').waitFor();
 await page.getByRole('button',{name:'Continue →'}).click();
 await page.getByLabel('Name',{exact:true}).fill('Operator A');
 await page.getByRole('button',{name:'Add operator',exact:true}).click();
 await page.getByText('Operator A',{exact:true}).waitFor();
 await page.getByRole('button',{name:'Continue →'}).click();
 await page.getByRole('button',{name:'Save monitoring settings'}).click();
 await page.getByRole('button',{name:'Finish setup'}).click();
 await page.getByRole('heading',{name:'Network overview'}).waitFor();
 await page.getByLabel('Who is restarting?').selectOption('Operator A');
 const button=page.getByRole('button',{name:'Restart Router',exact:true});
 await button.click();await page.waitForTimeout(200);assert.equal(await page.locator('.activity').count(),0);
 await button.focus();await page.keyboard.down('Space');await page.waitForTimeout(700);await page.keyboard.up('Space');assert.equal(await page.locator('.activity').count(),0);
 await page.screenshot({path:'test-results/dashboard-desktop.png',fullPage:true});
 await button.focus();await page.keyboard.down('Space');await page.waitForTimeout(2250);await page.keyboard.up('Space');
 await page.locator('.activity').first().waitFor();assert.equal(await button.isDisabled(),true);
 await page.reload();await page.getByLabel('Who is restarting?').waitFor();assert.equal(await page.getByLabel('Who is restarting?').inputValue(),'Operator A');
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:'test-results/dashboard-mobile.png',fullPage:true});
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
 await page.goto('http://127.0.0.1:8019/admin#history');
 await page.getByText('Restart history',{exact:true}).waitFor();await page.locator('summary').first().click();
 await page.getByText('switch-a / 1',{exact:false}).first().waitFor();
 for(const hash of ['general','users','unifi','groups','monitoring']){
  await page.goto('http://127.0.0.1:8019/admin#'+hash);await page.locator('#admin-content .panel').first().waitFor();
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),hash+' mobile overflow');
 }
 assert.deepEqual(errors,[]);assert.deepEqual(remote,[]);
 console.log('PASS: complete first-run setup, authenticated administration, real API persistence, click/short-hold cancellation, keyboard hold restart, lockout, remembered operator, detailed history, mobile layouts, no remote assets or JS errors.');
}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
