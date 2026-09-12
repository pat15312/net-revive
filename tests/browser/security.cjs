// Only run against the disposable fake-controller server in tests/browser/server.py.
const {chromium}=require('playwright');
const http=require('node:http');
const assert=require('node:assert/strict');
(async()=>{
 const attacker=http.createServer((req,res)=>{res.setHeader('content-type','text/html');res.end('<!doctype html><title>Isolated attacker</title><iframe src="http://127.0.0.1:8019/"></iframe>');});
 await new Promise(resolve=>attacker.listen(8020,'127.0.0.1',resolve));
 const browser=await chromium.launch({headless:true,args:['--no-sandbox','--no-proxy-server','--host-resolver-rules=MAP rebind.attacker.test 127.0.0.1']});
 try{
  const context=await browser.newContext();const page=await context.newPage();
  await page.goto('http://127.0.0.1:8019/');
  const session=await (await context.request.get('http://127.0.0.1:8019/api/session')).json();
  const login=await context.request.post('http://127.0.0.1:8019/api/login',{headers:{'x-csrf-token':session.csrf},data:{password:'browser-updated-password'}});
  assert.equal(login.status(),200);const csrf=(await login.json()).csrf;
  const payload='<img data-probe src=x onerror="window.xssProbe=1">';
  for(const [path,data] of [
   ['/general',{title:payload,timezone:'UTC'}],
   ['/operators/1',{name:payload}],
   ['/targets/1',{label:payload,enabled:true}],
   ['/groups/1',{name:payload,button_label:payload,description:payload,target_ids:[1]}],
  ]){assert.equal((await context.request.put('http://127.0.0.1:8019/api/admin'+path,{headers:{'x-csrf-token':csrf},data})).status(),200);}
  await page.goto('http://127.0.0.1:8019/');await page.getByRole('heading',{name:payload,exact:true}).first().waitFor();
  assert.equal(await page.locator('img[data-probe]').count(),0);assert.equal(await page.evaluate(()=>window.xssProbe),undefined);
  for(const tab of ['general','users','groups','unifi','history']){
   await page.goto('http://127.0.0.1:8019/admin#'+tab);await page.locator('#admin-content .panel').first().waitFor();
   assert.equal(await page.locator('img[data-probe]').count(),0);assert.equal(await page.evaluate(()=>window.xssProbe),undefined);
  }
  const messages=[];page.on('console',m=>messages.push(m.text()));
  await page.goto('http://127.0.0.1:8020/');
  const attacks=await page.evaluate(async()=>{
   const results=[];
   for(const options of [
    {credentials:'include'},
    {method:'POST',credentials:'include',headers:{'content-type':'text/plain'},body:'{}'},
    {method:'POST',credentials:'include',headers:{'content-type':'application/json','x-csrf-token':'forged'},body:'{}'},
   ]){try{await fetch('http://127.0.0.1:8019/api/logout',options);results.push('readable');}catch{results.push('blocked');}}
   return results;
  });
  assert.deepEqual(attacks,['blocked','blocked','blocked']);
  assert.equal((await context.request.get('http://127.0.0.1:8019/api/admin/config')).status(),200);
  await page.waitForTimeout(200);
  assert.ok(messages.some(m=>m.includes('frame-ancestors')||m.includes('X-Frame-Options')),'Framing must be blocked by response policy');
  const rebind=await page.goto('http://rebind.attacker.test:8019/api/session');
  assert.equal(rebind.status(),400);assert.ok(!(await rebind.text()).includes('csrf'));
  console.log('PASS: stored XSS in title/user/group/button/description/label, cross-origin reads and writes, preflight, clickjacking, rebinding-style Host routing; no real controller traffic.');
 }finally{await browser.close();attacker.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
