/* Real Chrome, process restart, SQLite and DPAPI; synthetic identity/inference only. */
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),readline=require('readline'),{spawn}=require('child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const out=path.resolve(process.argv[2]||fs.mkdtempSync(path.join(require('os').tmpdir(),'nexus-continuity-'))),root=path.join(out,'public-project');
fs.mkdirSync(path.join(root,'src/companion_core'),{recursive:true});
fs.writeFileSync(path.join(root,'README.md'),'# Public restart fixture\nNo private input.\n');fs.writeFileSync(path.join(root,'AGENTS.md'),'Public fixture only.');
for(const name of ['daily','chat','surface','core','runtime','review','work'])fs.writeFileSync(path.join(root,'src/companion_core',name+'.py'),'class PublicCapability:\n    pass\n');
const checks=[],errors=[],sessions=[],owner='synthetic-test-account';let browser,fixture,release;
const check=(name,value)=>{checks.push({name,passed:!!value});assert.ok(value,name);};
async function start(){
 const child=spawn(process.env.PYTHON||'python',['-B',path.join(__dirname,'conversation_work_fixture.py'),out,root],{windowsHide:true,env:{...process.env,PYTHONUTF8:'1'}});
 const lines=readline.createInterface({input:child.stdout});let stderr='';child.stderr.on('data',s=>stderr+=s);
 const ready=await new Promise((resolve,reject)=>{lines.once('line',s=>resolve(JSON.parse(s)));child.once('error',reject);child.once('exit',()=>reject(Error(stderr)));});
 const s={child,...ready,command:body=>new Promise(resolve=>{lines.once('line',s=>resolve(JSON.parse(s)));child.stdin.write(JSON.stringify(body)+'\n');})};sessions.push(s);return s;
}
async function stop(s){if(s.child.exitCode!==null)return;const ended=new Promise(r=>s.child.once('exit',r));s.child.stdin.end('{"action":"stop"}\n');await ended;}
const saved=p=>p.waitForFunction(()=>document.getElementById('chat-save-status').dataset.state==='saved'&&/已.*保存/.test(document.getElementById('chat-save-status').textContent));
let sends=0;
async function page(){const context=await browser.newContext({viewport:{width:1440,height:1000},locale:'zh-TW',reducedMotion:'reduce'}),p=await context.newPage();p.setDefaultTimeout(12000);p.on('pageerror',e=>errors.push(e.message));p.on('request',r=>{if(r.url().endsWith('/api/chat/send'))sends++;});return {p,context};}
async function post(p,action,body){return p.evaluate(async({action,body})=>{const r=await fetch('/api/chat/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Companion-UI':'1'},body:JSON.stringify(body)});return {status:r.status,data:await r.json()};},{action,body});}
(async()=>{try{
 fixture=await start();browser=await chromium.launch({channel:'chrome',headless:true,args:['--disable-gpu']});let {p,context}=await page();
 await p.goto(fixture.url+'/#chat?chat='+fixture.chat);await p.waitForFunction(id=>document.getElementById('chat-history').value===id,fixture.chat);
 await p.locator('.chat-answer>.chat-source-link').click();await p.locator('#work-preview').click();await p.locator('#work-confirm:not([disabled])').click();await p.waitForFunction(()=>document.querySelector('.chat-work-card')?.dataset.state==='RESULT_PENDING_REVIEW');
 const chat=fixture.chat,task=await p.locator('.chat-work-card').getAttribute('data-task'),oldURL=fixture.url;
 await p.locator('.chat-work-card .secondary-button').click();await p.locator('#companion-ask').click();await p.locator('#companion-window-mode').selectOption('split-right');await p.locator('#companion-close').click();
 await p.locator('#nexus-navigation [data-route="chat"]').click();await p.locator('#preferences').click();await p.locator('button[data-theme="porcelain"]').click();await p.locator('#settings-dialog [data-close]').click();
 await p.locator('#nexus-sidebar-toggle').click();await p.locator('#chat-question').fill('PUBLIC_DRAFT_BEFORE_RESTART');
 await p.locator('#chat-source-open').click();await p.locator('#chat-sources input').first().check();await p.locator('#chat-preview').click();await p.locator('#chat-knowledge-done:not([disabled])').click();await saved(p);
 check('confirmed local save is visible before shutdown',(await p.locator('#chat-save-status').textContent()).includes('草稿已加密保存'));
 check('browser stores no plaintext draft',await p.evaluate(()=>![...Object.values(sessionStorage),...Object.values(localStorage)].some(v=>v.includes('PUBLIC_DRAFT_BEFORE_RESTART'))));
 await context.close();await stop(fixture);fixture=await start();({p,context}=await page());
 const nexusGate=new Promise(r=>release=r);await p.route('**/nexus.js',async route=>{await nexusGate;await route.continue();});
 const navigation=p.goto(fixture.url+'/');
 await p.waitForFunction(id=>document.getElementById('chat-history')?.value===id&&typeof companionSidebarPreference==='undefined',chat);
 release();await navigation;await p.unroute('**/nexus.js');
 const resume=p.locator('#nexus-overview .nexus-home-actions [data-route="chat"]');
 check('daily overview offers continuation of the restored conversation',(await resume.textContent()).includes('繼續草稿')&&(await p.locator('#nexus-resume-copy').textContent()).includes('已加密保存'));await resume.click();
 await p.waitForFunction(id=>document.getElementById('chat-history').value===id,chat);await saved(p);
 check('fresh browser storage resumes original conversation and draft',await p.locator('#chat-question').inputValue()==='PUBLIC_DRAFT_BEFORE_RESTART');
 check('material and sidebar survive process and browser-context restart',await p.locator('body').getAttribute('data-theme')==='porcelain'&&await p.locator('body').getAttribute('data-sidebar')==='collapsed');
 check('delayed navigation script cannot discard restored preferences',await p.locator('body').getAttribute('data-sidebar')==='collapsed');
 check('source selections and preview authority never resume',await p.locator('#chat-sources input:checked').count()===0&&await p.locator('#document-chat-context').isHidden()&&!await p.evaluate(()=>companionProjectStatus().preview));
 check('existing pending review receipt remains visible',await p.locator('.chat-work-card[data-task="'+task+'"]').getAttribute('data-state')==='RESULT_PENDING_REVIEW');
 await p.locator('.chat-work-card .secondary-button').click();await p.locator('#companion-ask').click();
 check('Companion window preference survives restart',await p.locator('#companion-window-mode').inputValue()==='split-right');await p.locator('#companion-close').click();await p.locator('#nexus-navigation [data-route="chat"]').click();
 await p.locator('#chat-new').click();await p.locator('#chat-question').fill('PUBLIC_NEW_CONVERSATION_DRAFT');await saved(p);await p.locator('#chat-history').selectOption(chat);await saved(p);
 check('new-conversation draft and existing draft stay separate',await p.locator('#chat-question').inputValue()==='PUBLIC_DRAFT_BEFORE_RESTART');
 await p.locator('#chat-send').click();await p.waitForFunction(()=>document.querySelectorAll('.chat-message').length===2&&!document.getElementById('chat-send').disabled);await saved(p);await p.reload();await saved(p);
 check('sent message does not resurrect as an unsent draft',await p.locator('#chat-question').inputValue()==='');await p.locator('#chat-new').click();
 check('another unsent draft survives message send and reload',await p.locator('#chat-question').inputValue()==='PUBLIC_NEW_CONVERSATION_DRAFT');await saved(p);
 await context.close();({p,context}=await page());await p.goto(fixture.url+'/');
 await p.waitForFunction(()=>document.getElementById('nexus-resume-copy').textContent.includes('已加密保存'));
 check('fresh homepage identifies a draft with no submitted conversation',await p.locator('#nexus-resume-title').textContent()==='尚未送出的新對話'&&!(await p.locator('#nexus-resume').textContent()).includes('PUBLIC_NEW_CONVERSATION_DRAFT'));
 await p.setViewportSize({width:390,height:844});await p.screenshot({path:path.join(out,'resume-home-mobile.png'),fullPage:true});
 check('resume entry fits narrow screen',await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 await p.locator('#nexus-overview .nexus-home-actions [data-route="chat"]').click();await saved(p);
 check('homepage resumes exact new draft without sending or granting sources',await p.locator('#chat-question').inputValue()==='PUBLIC_NEW_CONVERSATION_DRAFT'&&await p.locator('#chat-history').inputValue()===''&&!await p.evaluate(()=>companionProjectStatus().preview));
 await p.setViewportSize({width:1440,height:1000});
 const scope={account:owner,workspace:root},record=(await post(p,'continuity-get',scope)).data;
 const newer=structuredClone(record.value);newer.drafts.find(([key])=>JSON.parse(key)[1]==='')[1]='PUBLIC_NEWER_WINDOW_DRAFT';
 const changed=await post(p,'continuity-save',{...scope,revision:record.revision,value:newer});check('another window can durably save its own newer revision',changed.status===200);
 await p.locator('#chat-question').fill('PUBLIC_STALE_WINDOW_DRAFT');await p.waitForFunction(()=>document.getElementById('chat-save-status').dataset.state==='error');
 check('stale save preserves current text and newer durable draft',await p.locator('#chat-question').inputValue()==='PUBLIC_STALE_WINDOW_DRAFT'&&(await post(p,'continuity-get',scope)).data.value.drafts.some(([,v])=>v==='PUBLIC_NEWER_WINDOW_DRAFT'));
 await p.locator('#chat-save-recover').click();await p.locator('#chat-continuity').waitFor({state:'visible'});check('conflict preview shows the actual durable version',(await p.locator('#chat-continuity-saved').textContent()).includes('PUBLIC_NEWER_WINDOW_DRAFT'));await p.locator('#chat-continuity [data-close]').first().click();
 check('cancel keeps current unsaved draft',await p.locator('#chat-question').inputValue()==='PUBLIC_STALE_WINDOW_DRAFT');
 await p.locator('#chat-save-recover').click();await p.locator('#chat-continuity-use').click();await saved(p);check('only explicit recovery replaces the local draft',await p.locator('#chat-question').inputValue()==='PUBLIC_NEWER_WINDOW_DRAFT');
 await p.route('**/api/chat/continuity-save',route=>route.abort());await p.locator('#chat-question').fill('PUBLIC_DRAFT_DURING_OUTAGE');await p.waitForFunction(()=>document.getElementById('chat-save-status').dataset.state==='error');
 check('failed save never claims persistence and protects navigation',await p.locator('#chat-question').inputValue()==='PUBLIC_DRAFT_DURING_OUTAGE'&&await p.evaluate(()=>!window.dispatchEvent(new Event('beforeunload',{cancelable:true}))));
 await p.locator('#nexus-navigation [data-route="overview"]').click();
 check('homepage distinguishes unsaved draft from confirmed persistence',await p.locator('#nexus-resume').getAttribute('data-state')==='error'&&(await p.locator('#nexus-resume-copy').textContent()).includes('尚未確認')&&!(await p.locator('#nexus-resume-copy').textContent()).includes('已加密保存'));
 await p.locator('#nexus-overview .nexus-home-actions [data-route="chat"]').click();
 await p.unroute('**/api/chat/continuity-save');await p.locator('#chat-save-retry').click();await saved(p);
 check('explicit retry saves the preserved draft',(await post(p,'continuity-get',scope)).data.value.drafts.some(([,v])=>v==='PUBLIC_DRAFT_DURING_OUTAGE'));
 await p.route('**/api/chat/continuity-save',async route=>{await route.fetch();await route.abort();});await p.locator('#chat-question').fill('PUBLIC_DRAFT_WITH_LOST_ACK');await p.waitForFunction(()=>document.getElementById('chat-save-status').dataset.state==='error');
 const committed=(await post(p,'continuity-get',scope)).data;
 check('lost acknowledgement is distinguished from absent persistence',committed.value.drafts.some(([,v])=>v==='PUBLIC_DRAFT_WITH_LOST_ACK'));
 await p.unroute('**/api/chat/continuity-save');await p.locator('#chat-save-retry').click();await saved(p);
 check('retry reconciles a committed save without overwriting again',(await post(p,'continuity-get',scope)).data.revision===committed.revision&&await p.locator('#chat-question').inputValue()==='PUBLIC_DRAFT_WITH_LOST_ACK');
 await p.setViewportSize({width:390,height:844});await p.screenshot({path:path.join(out,'saved-draft-mobile.png'),fullPage:true});
 check('saved status and composer fit a narrow viewport',await p.locator('#chat-send').evaluate(e=>{const r=e.getBoundingClientRect();return r.right<=innerWidth&&r.bottom<=innerHeight;})&&await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 await context.close();const delayed=await page();p=delayed.p;
 // Hold a real, fully received response inside fetch, as the account verifier
 // does. This avoids route.fulfill racing Playwright's route removal/cancel.
 await p.addInitScript(()=>{
  const original=window.fetch.bind(window);let held=false,release;const gate=new Promise(r=>release=r);
  window.__releaseContinuity=()=>release();window.__continuityHeld=false;window.__continuityReturned=false;window.__draftLeaks=[];
  const descriptor=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value');
  Object.defineProperty(HTMLTextAreaElement.prototype,'value',{...descriptor,set(value){if(this.id==='chat-question'&&window.__auditContinuityOwner&&value)window.__draftLeaks.push(value);descriptor.set.call(this,value);}});
  window.fetch=async(...args)=>{const response=await original(...args),url=typeof args[0]==='string'?args[0]:args[0].url;
   if(!held&&url.endsWith('/api/chat/continuity-get')){held=true;await response.clone().arrayBuffer();window.__continuityHeld=true;await gate;window.__continuityReturned=true;}return response;
  };
 });
 await p.goto(fixture.url+'/#chat');await p.waitForFunction(()=>window.__continuityHeld);await fixture.command({action:'account',account:'synthetic-other-account'});
 await p.waitForFunction(()=>companionProjectStatus().account==='synthetic-other-account');await p.evaluate(()=>{window.__auditContinuityOwner=true;window.__releaseContinuity();});await p.waitForFunction(()=>window.__continuityReturned);await p.evaluate(async()=>{await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);});
 check('late old-owner draft cannot reappear after account change',await p.evaluate(()=>window.__draftLeaks.length===0)&&await p.locator('#chat-question').inputValue()===''&&await p.locator('#chat-history option[value="'+chat+'"]').count()===0&&await p.locator('#chat-continuity-saved').textContent()==='');
 check('homepage clears the previous account continuation',await p.locator('#nexus-resume-title').textContent()===''&&await p.locator('#nexus-resume').isHidden());
 check('resuming, recovery and preference changes never invoke a model',sends===1);check('no browser errors',errors.length===0);
 fs.writeFileSync(path.join(out,'restart.json'),JSON.stringify({oldURL,newURL:fixture.url,originalChat:chat,originalTask:task,freshBrowserContext:true},null,2));
 console.log(JSON.stringify({passed:checks.length,errors,out}));
}catch(e){errors.push(e.stack);throw e;
}finally{if(release)release();if(browser){for(const context of browser.contexts())for(const page of context.pages())await page.unrouteAll({behavior:'ignoreErrors'});await browser.close();}for(const s of sessions)await stop(s);fs.writeFileSync(path.join(out,'checks.json'),JSON.stringify({checks,errors,sends,syntheticAuthAndInference:true,realDPAPIAndSQLite:true,realProcessRestart:true},null,2));}})().catch(e=>{console.error(e.stack);process.exitCode=1;});
