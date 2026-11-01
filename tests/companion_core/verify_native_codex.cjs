/* Real Chrome + real HTTP boundary. --live reads this repository's native
 * Codex history; SIWC authentication and chat inference stay synthetic. */
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process'),readline=require('readline');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const out=path.resolve(process.argv[2]),live=process.argv.includes('--live');fs.mkdirSync(out,{recursive:true});
(async()=>{
 const root=path.resolve(__dirname,'../..'),child=spawn(process.env.PYTHON||path.join(root,'.venv/Scripts/python.exe'),['-B',path.join(__dirname,'conversation_work_fixture.py'),out,root,live?'--native-codex-live-proof':'--native-codex-proof'],{windowsHide:true,env:{...process.env,PYTHONUTF8:'1'}});
 const lines=readline.createInterface({input:child.stdout});let stderr='';child.stderr.on('data',v=>stderr+=v);
 const next=()=>new Promise((resolve,reject)=>{lines.once('line',s=>{try{resolve(JSON.parse(s));}catch(e){reject(e);}});child.once('exit',()=>reject(Error(stderr)));});
 const ready=await next();const checks=[],errors=[],requests=[];let browser;
 const check=(name,value)=>{checks.push({name,passed:!!value});assert.ok(value,name);};
 try{
  browser=await chromium.launch({channel:'chrome',headless:true});const p=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});p.setDefaultTimeout(15000);
  p.on('pageerror',e=>errors.push(e.message));p.on('request',r=>{if(r.method()==='POST')requests.push(new URL(r.url()).pathname);});
  await p.goto(ready.url+'/#execute');await p.waitForFunction(()=>window.companionProjectStatus?.().account);
  check('no native history read on navigation',requests.every(s=>!s.includes('/codex-')));
  await p.locator('#native-preview').click();await p.locator('#native-confirm').waitFor({state:'visible'});
  check('scope discloses native owner and workspace',/未驗證與 NEXUS/.test(await p.locator('#native-scope-description').textContent())&&(await p.locator('#native-scope-path').textContent()).includes(root));
  check('preview does not read history',!requests.some(s=>s.endsWith('codex-list')||s.endsWith('codex-detail')));
  await p.locator('#native-confirm').click();await p.locator('.native-row').first().waitFor();
  check('real native list' +(live?' live':''),(await p.locator('.native-row').count())>0);
  await p.locator('.native-row').first().click();await p.waitForFunction(()=>document.querySelector('#native-detail').textContent.includes('來源：官方'));
  check('runtime truth is qualified',/即時執行狀態未確認/.test(await p.locator('#native-codex').textContent()));
  check('deep link bound to selected thread',(await p.locator('#native-detail a').getAttribute('href'))==='codex://threads/'+await p.locator('.native-row[aria-pressed="true"]').getAttribute('data-thread'));
  check('visible useful reply',await p.locator('.native-message').count()>0);
  check('history initially collapsed',await p.locator('.native-record[open]').count()===0);
  if(!live){
   check('paired user instruction visible',/請檢查目前修改/.test(await p.locator('#native-pair').textContent()));
   check('title is inert text',(await p.locator('.native-row strong').textContent()).includes('<script>'));
   check('private reasoning and tools absent',!(/PRIVATE/.test(await p.locator('#native-detail').textContent())));
   const received=next();child.stdin.write('{"action":"native-update"}\n');await received;
   await p.locator('#native-refresh').click();await p.waitForFunction(()=>document.querySelector('#native-detail').textContent.includes('新的最後回覆'));
   check('refresh reflects changed source',true);
  }
  if(!live){
   await p.route('**/api/chat/codex-detail',async route=>{const response=await route.fetch(),data=await response.json();const old=data.turns[0];old.instructions[0].text='這是完整交辦原文。'.repeat(150);data.turns.unshift({...old,id:'unpaired',instructions:[],messages:[{text:'較新的獨立回覆',phase:'final_answer'}]});await route.fulfill({response,json:data});});
   await p.locator('#native-refresh').click();await p.waitForFunction(()=>document.querySelector('#native-turn')?.value==='1');
   check('older instruction never attributed to newer response',!(await p.locator('#native-pair').textContent()).includes('較新的獨立回覆'));
   check('long source collapsed by default',await p.locator('.native-full:not([open])').count()>0);
   await p.locator('.native-full summary').first().click();check('full instruction can expand',await p.locator('.native-full[open]').count()===1);
   await p.locator('#native-refresh').click();await p.waitForFunction(()=>!document.querySelector('#native-refresh').disabled);check('refresh retains reading expansion',await p.locator('.native-full[open]').count()===1);
   await p.locator('#native-turn').selectOption('0');check('missing prompt is explicit',/沒有已保存的使用者文字指令/.test(await p.locator('#native-pair').textContent())&&!(await p.locator('#native-pair').textContent()).includes('完整交辦原文'));
   await p.locator('#native-turn').selectOption('1');await p.unroute('**/api/chat/codex-detail');
  }
  await p.evaluate(()=>scrollTo(0,0));await p.screenshot({path:path.join(out,'native-desktop.png'),fullPage:true});
  await p.setViewportSize({width:390,height:844});await p.screenshot({path:path.join(out,'native-mobile.png'),fullPage:true});
  check('mobile has no horizontal overflow',await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  if(!live){
   await p.route('**/api/chat/codex-list',route=>route.abort());await p.locator('#native-refresh').click();await p.waitForFunction(()=>document.querySelector('#native-notice').textContent.includes('上次資料已移除'));
   check('failure clears stale transcript',await p.locator('.native-message').count()===0&&await p.locator('.native-row').count()===0);
   await p.unroute('**/api/chat/codex-list');await p.locator('#native-refresh').click();await p.locator('.native-row').waitFor();
   const switched=next();child.stdin.write('{"action":"account","account":"synthetic-other"}\n');await switched;
   await p.waitForFunction(()=>document.querySelector('#native-notice').textContent.includes('帳戶或登入狀態已變更'));
   check('account switch clears and requires scope again',await p.locator('.native-row').count()===0&&await p.locator('#native-preview').isVisible());
  }else{
   await p.locator('.native-settings summary').click();await p.locator('#native-disconnect').click();check('disconnect clears live content',await p.locator('.native-message').count()===0);
  }
  check('no chat send or execution or review',requests.every(s=>!s.endsWith('/send')&&!s.endsWith('/work-confirm')&&!['/api/start','/api/cancel','/api/review'].includes(s)));
  check('no browser errors',errors.length===0);
 }finally{
  if(browser)await browser.close();const exited=new Promise(r=>child.once('exit',r));child.stdin.end('{"action":"stop"}\n');await exited;
  fs.writeFileSync(path.join(out,'checks.json'),JSON.stringify({checks,errors,requests,liveNativeHistory:live,syntheticSIWC:true},null,2));
 }
 console.log(JSON.stringify({passed:checks.length,out,live}));
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
