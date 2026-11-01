/* UX-04: real browser + isolated SQLite/ReviewStore/bounded audits. Inference and status faults are synthetic. */
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process'),readline=require('readline');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const out=path.resolve(process.argv[2]||fs.mkdtempSync(path.join(require('os').tmpdir(),'nexus-hierarchy-')));
fs.mkdirSync(out,{recursive:true});
(async()=>{
 const children=[],checks=[],errors=[],shots=[],posts=[];let browser,p;
 const check=(name,ok)=>{checks.push({name,passed:!!ok});assert.ok(ok,name);};
 async function fixture(workspace){const child=spawn(process.env.PYTHON||'python',['-B',path.join(__dirname,'conversation_work_fixture.py'),out,...workspace?[workspace]:[]],{windowsHide:true,env:{...process.env,PYTHONUTF8:'1'}});children.push(child);let stderr='';child.stderr.on('data',s=>stderr+=s);return new Promise((resolve,reject)=>{readline.createInterface({input:child.stdout}).once('line',s=>resolve(JSON.parse(s)));child.once('exit',()=>reject(Error(stderr)));});}
 try {
  const ready=await fixture();browser=await chromium.launch({channel:'chrome',headless:true,args:['--disable-gpu']});
  p=await browser.newPage({viewport:{width:1440,height:1000},deviceScaleFactor:1,reducedMotion:'reduce'});p.setDefaultTimeout(12000);p.on('pageerror',e=>errors.push(e.message));p.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname);});
  const shot=async name=>{await p.screenshot({path:path.join(out,name+'.png')});shots.push(name+'.png');};
  const call=(name,body)=>p.evaluate(async({name,body})=>{const r=await fetch('/api/chat/'+name,{method:'POST',headers:{'Content-Type':'application/json','X-Companion-UI':'1'},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.error);return d;},{name,body});
  async function create(chat,turn,goal){const a=await call('work-create',{chat,turn}),v=await call('work-preview',{id:a.id,goal,expected:'僅核對指定來源結構。',selection:['daily']});const w=await call('work-confirm',{id:a.id,approval:v.approval,authority:'READ_ONLY'});await p.waitForFunction(async id=>{const d=await(await fetch('/api/state')).json();return !d.busy&&d.tasks.some(t=>t.task_id===id);},w.task_id);return w.task_id;}
  const nav=async route=>{await p.locator('#nexus-navigation [data-route="'+route+'"]').click();};
  const work=async id=>{await p.evaluate(id=>nexusOpenWork(id),id);await p.waitForFunction(id=>surfaceInspection().result?.task_id===id,id);};
  const open=async id=>{await p.locator('#companion-ask').click();await p.waitForFunction(id=>document.getElementById('companion-context').dataset.task===id,id);await p.locator('#companion-panel .chat-message').first().waitFor({state:'visible'});};
  const composerFits=()=>p.evaluate(()=>{const q=document.querySelectorAll('#chat-question'),form=document.getElementById('chat-form').getBoundingClientRect(),messages=document.getElementById('chat-messages').getBoundingClientRect();return q.length===1&&q[0].getClientRects().length>0&&messages.bottom<=form.top+1&&form.bottom<=innerHeight+1&&document.documentElement.scrollWidth<=innerWidth+1;});
  await p.goto(ready.url);await p.waitForFunction(()=>!surfaceInspection().offline);
  check('overview retains two columns and seven entries',await p.locator('.nexus-module').count()===7&&await p.locator('.nexus-modules').evaluate(e=>getComputedStyle(e).gridTemplateColumns.split(' ').length===2));
  check('demonstration explanation removed',await p.locator('.nexus-home-note').count()===0);
  const a=await create(ready.chat,ready.turn,'UX-04 工作 A：查核 daily.py'),b=await create(ready.chat,ready.turn,'UX-04 工作 B：來源結構核對');
  await nav('work');await p.waitForSelector('.task-tile[data-task="'+b+'"]');
  const tiles=p.locator('.task-tile');await tiles.first().focus();await p.keyboard.press('End');check('End focuses last work item',await tiles.last().evaluate(e=>e===document.activeElement));await p.keyboard.press('Home');await p.keyboard.press('ArrowRight');check('arrow keys move focus without opening work',await tiles.nth(1).evaluate(e=>e===document.activeElement)&&await p.locator('body').getAttribute('data-work-detail')==='false');
  check('separate bordered items',await tiles.first().evaluate(e=>getComputedStyle(e).borderTopStyle==='solid'&&getComputedStyle(e).borderTopWidth==='1px'));
  await shot('work-list-desktop');await tiles.first().focus();const selected=await tiles.first().getAttribute('data-task');await p.keyboard.press('Enter');await p.waitForFunction(id=>surfaceInspection().result?.task_id===id,selected);
  check('keyboard activates exact task',p.url().includes('task='+selected));
  check('activated item retains current selection',await p.locator('.task-tile[aria-pressed="true"]').count()===1&&await p.locator('.task-tile[aria-pressed="true"]').getAttribute('data-task')===selected);
  check('one Companion entry and no window toolbar in work body',await p.locator('#work-space #companion-ask:visible').count()===1&&await p.locator('#work-space .companion-modebar,#work-space #companion-window-mode').count()===0);
  check('connected instructions hidden without hiding status',await p.locator('#work-availability').isHidden()&&await p.locator('#state-pill').isVisible());await shot('work-detail-desktop');
  await open(selected);check('context state matches detail exactly',await p.locator('#companion-task-state').innerText()===await p.locator('#status-label').innerText());
  check('mode controls remain in window',await p.locator('#companion-panel #companion-window-mode option').count()===6&&await p.locator('#companion-window-status').innerText()==='');
  check('window title is readable without displacing controls',await p.locator('#companion-panel-title').evaluate(e=>getComputedStyle(e).fontSize==='16px'));
  await p.locator('#chat-question').fill('工作延伸聊天草稿');await p.locator('#companion-expand').click();check('linked full conversation has one non-overlapping input',await composerFits());await shot('linked-chat-desktop');
  const beforeSends=posts.filter(s=>s==='/api/chat/send').length;
  await p.locator('#companion-share-result').click();await p.locator('#chat-preview').click();await p.waitForFunction(()=>!document.getElementById('chat-knowledge-done').disabled);await p.locator('#chat-knowledge-done').click();
  check('source preview remains explicit without model send',await p.locator('#chat-sources input:checked').count()===1&&posts.filter(s=>s==='/api/chat/send').length===beforeSends);
  await p.locator('#companion-return').click();await p.waitForFunction(id=>surfaceInspection().result?.task_id===id,selected);
  for(const width of [390,360]){
   await p.setViewportSize({width,height:844});await open(selected);await p.locator('#companion-expand').click();
   check(width+' linked chat uses single readable input',await composerFits()&&await p.locator('#chat-question').inputValue()==='工作延伸聊天草稿');await shot('linked-chat-'+width);
   check(width+' navigation revoked source selection',await p.locator('#chat-sources input:checked').count()===0);
   await p.locator('#companion-return').click();await p.locator('#nexus-work-list').click();await shot('work-list-'+width);
   await work(selected);
  }
  await p.setViewportSize({width:1440,height:1000});await nav('chat');await p.locator('#chat-new').click();
  check('ordinary chat hides old context and uses same composer',await p.locator('#companion-context').isHidden()&&await composerFits());await shot('ordinary-chat-desktop');
  for(const width of [390,360]){await p.setViewportSize({width,height:844});check(width+' ordinary chat fits',await composerFits());await shot('ordinary-chat-'+width);}
  await p.setViewportSize({width:1440,height:1000});await nav('work');
  const states={UNKNOWN:'執行狀態未確認',CREATED:'正在準備',RUNNING:'執行中',CANCEL_REQUESTED:'停止待確認',CANCELLED:'已確認取消',FAILED:'執行失敗',RESULT_PENDING_REVIEW:'成果等待審查',ACCEPTED:'人類已接受',REJECTED:'人類已拒絕',REVISION_REQUESTED:'已記錄調整方向'};
  await p.route('**/api/state',async route=>{const r=await route.fetch(),d=await r.json();d.tasks=Object.entries(states).map(([state,intent])=>({task_id:'synthetic-'+state,state,intent:'狀態辨識測試：'+intent}));d.active=null;d.observation={task_id:null,events:[]};await route.fulfill({response:r,json:d});});
  await p.waitForSelector('.task-tile[data-task="synthetic-UNKNOWN"]');
  for(const [state,label]of Object.entries(states))check('trusted state mapping and badge '+state,await p.locator('.tile-state[data-state="'+state+'"]').innerText()===label&&await p.locator('.tile-state[data-state="'+state+'"]').evaluate(e=>parseFloat(getComputedStyle(e).fontSize)>=12));
  check('failed and unknown have distinct visual states',await p.locator('.tile-state[data-state="FAILED"]').evaluate(e=>getComputedStyle(e).backgroundColor)!==await p.locator('.tile-state[data-state="UNKNOWN"]').evaluate(e=>getComputedStyle(e).backgroundColor));await shot('synthetic-states-desktop');
  await p.setViewportSize({width:360,height:844});check('all state labels wrap without horizontal overflow',await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await shot('synthetic-states-360');await p.unrouteAll({behavior:'wait'});
  // Current product switches workspaces by launcher URL, not a simulated project selector.
  await p.setViewportSize({width:1440,height:1000});await nav('chat');await p.locator('#chat-history').selectOption(ready.chat);await p.locator('#chat-question').fill('工作區 A 草稿');
  const other=path.join(out,'other-workspace');fs.mkdirSync(path.join(other,'src/companion_core'),{recursive:true});fs.copyFileSync(path.join(__dirname,'../../src/companion_core/daily.py'),path.join(other,'src/companion_core/daily.py'));
  const second=await fixture(other);await p.goto(second.url+'/#work');await p.waitForFunction(()=>!surfaceInspection().offline);
  check('shared store cannot expose first workspace tasks',await p.locator('.task-tile').count()===0&&await p.locator('#nexus-project').innerText()==='other-workspace');
  await nav('chat');await p.waitForFunction(id=>!!document.querySelector('#chat-history option[value="'+id+'"]'),second.chat);
  check('other workspace history excludes first conversation',await p.locator('#chat-history option[value="'+ready.chat+'"]').count()===0&&await p.locator('#chat-question').inputValue()==='');
  const c=await create(second.chat,second.turn,'UX-04 工作區 B：查核限定來源');await nav('work');await p.waitForSelector('.task-tile[data-task="'+c+'"]');check('other workspace binds its own work',await p.locator('.task-tile').count()===1);
  await p.goto(ready.url+'/#chat?chat='+ready.chat);await p.waitForFunction(id=>document.getElementById('chat-history').value===id&&document.getElementById('chat-question').value==='工作區 A 草稿',ready.chat);
  check('workspace return preserves correct draft and no source grant',await p.locator('#chat-sources input:checked').count()===0);await nav('work');await p.waitForFunction(()=>document.querySelectorAll('.task-tile').length===2);
  check('first workspace still excludes second result',await p.locator('.task-tile[data-task="'+c+'"]').count()===0);check('no browser errors',errors.length===0);
 }catch(e){if(p)await p.screenshot({path:path.join(out,'failure.png')}).catch(()=>{});throw e;}
 finally{if(browser){for(const c of browser.contexts())for(const page of c.pages())await page.unrouteAll({behavior:'wait'});await browser.close();}for(const child of children){const done=new Promise(r=>child.once('exit',r));child.stdin.end('{"action":"stop"}\n');await done;}fs.writeFileSync(path.join(out,'checks.json'),JSON.stringify({checks,errors,shots,posts,syntheticInference:true,syntheticStates:true,realBoundedAudit:true,sharedStoreTwoWorkspaces:true},null,2));}
 console.log(JSON.stringify({passed:checks.length,errors,out}));
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
