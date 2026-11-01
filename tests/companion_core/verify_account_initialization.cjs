/* Real resource/chat handlers + isolated SQLite. Synthetic auth transitions only.
 * Controlled response gates exercise ordering without sleeps or model requests.
 * node verify_account_initialization.cjs <evidence-directory>
 */
const fs=require('fs'),path=require('path'),readline=require('readline'),assert=require('assert/strict');
const {spawn}=require('child_process'),{chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const out=path.resolve(process.argv[2]),repo=path.resolve(__dirname,'../..');fs.mkdirSync(out,{recursive:true});
const root=path.join(out,'synthetic-project');fs.mkdirSync(root);fs.writeFileSync(path.join(root,'README.md'),'Synthetic account initialization document.');
const A='synthetic-test-account',B='synthetic-other-account',checks=[],errors=[],traces=[],started=performance.now();
let browser,page,fixture;
const check=(name,passed)=>{checks.push({name,passed:!!passed});assert.ok(passed,name);};
async function post(action,body){const r=await fetch(fixture.url+'/api/chat/'+action,{method:'POST',headers:{'Content-Type':'application/json','Origin':fixture.url,'X-Companion-UI':'1'},body:JSON.stringify(body)});return {status:r.status,data:await r.json()};}
async function save(name){const p=await post('resource-link-preview',{workspace:root,name,url:'https://example.com/'+name});assert.equal(p.status,200);const s=await post('resource-link-confirm',{workspace:root,approval:p.data.approval});assert.equal(s.status,200);return s.data.id;}
async function account(value,pending=null){return fixture.send({action:'account',account:value,pending});}
async function newPage(width,holdFirst=false,holdProject=false){
 const context=await browser.newContext({viewport:{width,height:900},deviceScaleFactor:1,reducedMotion:'reduce'});
 const p=await context.newPage();p.setDefaultTimeout(12000);p.on('pageerror',e=>errors.push(e.message));
 await p.addInitScript(({holdFirst,holdProject})=>{
  window.__events=[];const gates={},record=(type,data={})=>window.__events.push({type,time:performance.now(),...data});
  window.__arm=key=>{let release;gates[key]={wait:new Promise(r=>release=r),release:()=>release(),used:false};};
  window.__release=key=>gates[key].release();
  if(holdFirst)window.__arm('/api/chat/state');if(holdProject)window.__arm('/api/chat/project-context');
  window.addEventListener('companion-project',e=>record('identity',{account:e.detail.account}));
  const original=fetch.bind(window);
  window.fetch=async(...args)=>{
   const key=new URL(args[0],location.href).pathname,response=await original(...args),gate=gates[key];
   if(key==='/api/chat/send')record('model-request');
   if(gate&&!gate.used){gate.used=true;const data=await response.clone().json();record('held',{key,account:data.auth?.active||data.account||''});await gate.wait;record('released',{key});}
   return response;
  };
 },{holdFirst,holdProject});
 return {p,context};
}
const held=(p,key)=>p.waitForFunction(key=>window.__events.some(e=>e.type==='held'&&e.key===key),key);
const visibleLink=(p,id)=>p.locator('#links-list [data-link="'+id+'"]').waitFor();
(async()=>{
 const child=spawn(process.env.PYTHON||'python',['-B',path.join(__dirname,'conversation_work_fixture.py'),out,root],{cwd:repo,windowsHide:true,env:{...process.env,PYTHONUTF8:'1'}});
 const lines=readline.createInterface({input:child.stdout});let stderr='';child.stderr.on('data',s=>stderr+=s);
 const ready=await new Promise((resolve,reject)=>{lines.once('line',s=>resolve(JSON.parse(s)));child.once('error',reject);child.once('exit',()=>reject(Error(stderr)));});
 fixture={...ready,child,send:command=>new Promise(resolve=>{lines.once('line',s=>resolve(JSON.parse(s)));child.stdin.write(JSON.stringify(command)+'\n');})};
 const linkA=await save('owner-A'),original=await post('get',{chat:ready.chat});
 await account(B);const linkB=await save('owner-B');await account(A);
 browser=await chromium.launch({channel:'chrome',headless:true,args:['--disable-gpu']});
 for(const [route,projectFirst,width] of [['links',false,1440],['links',true,390],['documents',false,390],['documents',true,1440]]){
  const {p,context}=await newPage(width,true,!projectFirst);page=p;
  await p.goto(ready.url+'/#'+route);await held(p,'/api/chat/state');
  if(projectFirst)await p.waitForFunction(route=>document.getElementById(route+'-status').textContent.includes('帳戶尚未確認'),route);
  else await held(p,'/api/chat/project-context');
  await p.evaluate(()=>window.__release('/api/chat/state'));
  await p.waitForFunction(A=>companionProjectStatus().account===A,A);
  if(!projectFirst)await p.evaluate(()=>window.__release('/api/chat/project-context'));
  if(route==='links')await visibleLink(p,linkA);else await p.locator('#documents-list [data-document]').first().waitFor();
  check(route+' '+width+' initializes with '+(projectFirst?'project':'account')+' response first',true);
  check(route+' '+width+' has no overflow or inherited sources',await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1&&document.querySelectorAll('#chat-sources input:checked').length===0));
  await p.screenshot({path:path.join(out,route+'-'+width+'-'+projectFirst+'.png'),fullPage:true});
  traces.push({case:route+'-'+width+'-'+projectFirst,events:await p.evaluate(()=>window.__events)});await context.close();
 }
 const {p}=await newPage(1440);page=p;await p.goto(ready.url+'/#links');await visibleLink(p,linkA);
 await p.reload();await visibleLink(p,linkA);check('same-account reload restores real saved reference',true);
 for(const route of ['documents','project','links']){
  await p.locator((route==='project'?'.nexus-pinned':'#nexus-navigation')+' [data-route="'+route+'"]').click();
  if(route==='links')await visibleLink(p,linkA);else if(route==='documents')await p.locator('#documents-list [data-document]').first().waitFor();
  else await p.waitForFunction(()=>!!document.getElementById('nexus-project-page').dataset.project);
 }
 check('normal navigation preserves initialized account',await p.evaluate(A=>companionProjectStatus().account===A,A));
 await p.locator('#nexus-navigation [data-route="chat"]').click();await p.locator('#chat-history').selectOption(ready.chat);
 await p.locator('#chat-messages .chat-message').first().waitFor();await p.locator('#chat-question').fill('Owner A private synthetic draft');
 await p.locator('#chat-source-open').click();await p.locator('#chat-sources input').first().check();await p.keyboard.press('Escape');
 await p.evaluate(()=>window.__arm('/api/chat/state'));await held(p,'/api/chat/state');
 // Only the auth provider transition is synthetic. Every state/detail/resource
 // response continues through the real production HTTP handlers and SQLite.
 await p.route('**/api/chat/select',async route=>{await account(route.request().postDataJSON().account);await route.fulfill({json:{}});});
 const selected=p.waitForResponse(r=>r.url().endsWith('/api/chat/select'));
 await p.evaluate(B=>{const e=document.getElementById('chat-accounts');e.add(new Option('Synthetic B',B));e.value=B;e.dispatchEvent(new Event('change'));},B);await selected;
 check('explicit switch immediately clears old messages sources and draft',await p.locator('#chat-messages .chat-message').count()===0&&await p.locator('#chat-sources input:checked').count()===0&&await p.locator('#chat-question').inputValue()==='');
 await p.evaluate(()=>window.__release('/api/chat/state'));await p.waitForFunction(B=>companionProjectStatus().account===B,B);
 check('delayed old state cannot restore old history or draft',await p.locator('#chat-history option[value="'+ready.chat+'"]').count()===0&&await p.locator('#chat-messages .chat-message').count()===0&&await p.locator('#chat-question').inputValue()==='');
 check('old chat ID is denied by real backend after switch',(await post('get',{chat:ready.chat})).status===409);
 await p.locator('#nexus-navigation [data-route="links"]').click();await visibleLink(p,linkB);
 check('B sees only B saved references',await p.locator('[data-link="'+linkA+'"]').count()===0);
 await p.reload();await visibleLink(p,linkB);check('B reload remains owner-scoped',true);
 await account(B,true);await p.waitForFunction(()=>companionProjectStatus().account==='');
 await p.waitForFunction(()=>document.querySelectorAll('#links-list [data-link]').length===0);
 check('pending login clears previously visible resources',await p.locator('#chat-sources input:checked').count()===0&&(await post('get',{chat:ready.chat})).status===409);
 await account(B);await visibleLink(p,linkB);check('completed login reloads resources without navigation',true);
 await account(null);await p.waitForFunction(()=>companionProjectStatus().account==='');
 await p.waitForFunction(()=>document.querySelectorAll('#links-list [data-link]').length===0);
 check('logout clears resources and backend denies history',(await post('get',{chat:ready.chat})).status===409);
 let loginRequests=0;p.on('request',request=>{if(request.url().endsWith('/api/chat/login'))loginRequests++;});
 for(const route of ['documents','links']){
  await p.setViewportSize({width:route==='documents'?390:1440,height:900});
  await p.locator('#nexus-navigation [data-route="'+route+'"]').click();
  await p.locator('#'+route+'-account-open').click();
  check(route+' can open existing login controls without leaving the resource page',await p.locator('#chat-settings').isVisible()&&await p.evaluate(route=>document.body.dataset.route===route,route)&&await p.locator('#chat-login').evaluate(e=>e===document.activeElement));
  await p.screenshot({path:path.join(out,route+'-signin-recovery.png'),fullPage:true});
  await p.locator('#chat-settings [data-close]').first().click();
  check(route+' login recovery never starts OAuth or selects a source',loginRequests===0&&await p.locator('#chat-sources input:checked').count()===0);
 }
 await account(A);await visibleLink(p,linkA);check('original account recovers its reference automatically',true);
 await p.evaluate(()=>window.__arm('/api/chat/resource-links'));await p.locator('#links-refresh').click();await held(p,'/api/chat/resource-links');
 await account(B);await visibleLink(p,linkB);await p.evaluate(()=>window.__release('/api/chat/resource-links'));
 await p.evaluate(async()=>{await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);});
 check('late A resource response cannot overwrite known B resources',await p.locator('[data-link="'+linkA+'"]').count()===0&&await p.locator('[data-link="'+linkB+'"]').count()===1);
 await account(A);await visibleLink(p,linkA);check('owner history unchanged after all transitions',JSON.stringify(await post('get',{chat:ready.chat}))===JSON.stringify(original));
 check('no model request and no browser errors',await p.evaluate(()=>!window.__events.some(e=>e.type==='model-request'))&&errors.length===0);
 traces.push({case:'transitions',events:await p.evaluate(()=>window.__events)});
 console.log(JSON.stringify({passed:checks.length,seconds:(performance.now()-started)/1000,out}));
})().catch(async e=>{errors.push(e.stack);if(page&&!page.isClosed())await page.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});console.error(e.stack);process.exitCode=1;}).finally(async()=>{
 if(browser)await browser.close();if(fixture){const ended=new Promise(resolve=>fixture.child.once('exit',resolve));fixture.child.stdin.end('{"action":"stop"}\n');await ended;}
 fs.writeFileSync(path.join(out,'checks.json'),JSON.stringify({checks,errors,traces,seconds:(performance.now()-started)/1000,modelRequests:0,syntheticAuth:true,realHTTPAndSQLite:true},null,2));
});
