/* Real project UI + SQLite + ReviewStore + bounded audits. Only inference/accounts are synthetic. */
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),readline=require('readline'),{spawn}=require('child_process'),{pathToFileURL}=require('url');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const out=path.resolve(process.argv[2]||fs.mkdtempSync(path.join(require('os').tmpdir(),'project-context-'))),prototype=process.argv[3];fs.mkdirSync(out,{recursive:true});
(async()=>{
 const children=[],checks=[],errors=[],posts=[],shots=[],comparisons=[];let browser,p;
 const check=(name,ok)=>{checks.push({name,passed:!!ok});assert.ok(ok,name);};
 async function fixture(workspace){const child=spawn(process.env.PYTHON||'python',['-B',path.join(__dirname,'conversation_work_fixture.py'),out,...workspace?[workspace]:[]],{windowsHide:true,env:{...process.env,PYTHONUTF8:'1'}});children.push(child);let stderr='';child.stderr.on('data',s=>stderr+=s);const lines=readline.createInterface({input:child.stdout});return new Promise((resolve,reject)=>{lines.once('line',s=>resolve({...JSON.parse(s),child,lines}));child.once('exit',()=>reject(Error(stderr)));});}
 try {
  const ready=await fixture();browser=await chromium.launch({channel:'chrome',headless:true,args:['--disable-gpu']});const context=await browser.newContext({viewport:{width:1440,height:1000},deviceScaleFactor:1,reducedMotion:'reduce'});p=await context.newPage();p.setDefaultTimeout(12000);
  p.on('pageerror',e=>errors.push(e.message));p.on('request',r=>{if(r.method()==='POST')posts.push({path:new URL(r.url()).pathname,body:r.postDataJSON()});});
  const shot=async(page,name)=>{await page.screenshot({path:path.join(out,name+'.png')});shots.push(name+'.png');};
  const call=(name,body)=>p.evaluate(async({name,body})=>{const r=await fetch('/api/chat/'+name,{method:'POST',headers:{'Content-Type':'application/json','X-Companion-UI':'1'},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.error);return d;},{name,body});
  const raw=(name,body)=>p.evaluate(async({name,body})=>{const r=await fetch('/api/chat/'+name,{method:'POST',headers:{'Content-Type':'application/json','X-Companion-UI':'1'},body:JSON.stringify(body)});return {status:r.status,data:await r.json()};},{name,body});
  const pin=()=>p.locator('.nexus-pinned [data-route="project"]');
  async function project(){await pin().click();await p.waitForFunction(()=>!!document.getElementById('nexus-project-page').dataset.project);}
  async function work(id){await p.locator('#project-tasks [data-task="'+id+'"]').click();await p.waitForFunction(id=>surfaceInspection().result?.task_id===id,id);}
  async function create(goal){const a=await call('work-create',{chat:ready.chat,turn:ready.turn}),v=await call('work-preview',{id:a.id,goal,expected:'只確認來源結構，不推定功能可用。',selection:['daily']});const w=await call('work-confirm',{id:a.id,approval:v.approval,authority:'READ_ONLY'});await p.waitForFunction(async id=>{const d=await(await fetch('/api/state')).json();return !d.busy&&d.tasks.some(t=>t.task_id===id&&t.state==='RESULT_PENDING_REVIEW');},w.task_id);return w.task_id;}
  async function relation(action){const control=p.locator(action==='link'?'#project-chat-link':'#project-chat-unlink');await control.waitFor({state:'visible'});await p.waitForFunction(id=>!document.getElementById(id).disabled,action==='link'?'project-chat-link':'project-chat-unlink');await control.click();await p.locator('#project-confirm').waitFor({state:'visible'});}
  async function saveRelation(){await p.locator('#project-confirm-save').click();await p.locator('#project-confirm').waitFor({state:'hidden'});}
  const fit=()=>p.evaluate(()=>{const q=document.querySelectorAll('#chat-question'),f=document.getElementById('chat-form').getBoundingClientRect(),m=document.getElementById('chat-messages').getBoundingClientRect();return q.length===1&&f.bottom<=innerHeight+1&&m.bottom<=f.top+1&&m.height>=39&&document.documentElement.scrollWidth<=innerWidth+1;});
  await p.goto(ready.url);await p.waitForFunction(()=>!surfaceInspection().offline);await project();
  const identity=await p.locator('#nexus-project-page').getAttribute('data-project');
  check('pin opens actual launch workspace without a ninth top-level nav',path.resolve(identity)===path.resolve(__dirname,'../..')&&await p.locator('#nexus-navigation button').count()===8);
  check('honest empty work and relation states',await p.locator('#project-tasks button').count()===0&&await p.locator('#project-chats').innerText().then(s=>s.includes('尚無')));
  check('documents links and other projects not fabricated',/未連接/.test(await p.locator('#nexus-project-page').innerText())&&!/Reverb Core/.test(await p.locator('#nexus-project-page').innerText()));
  check('viewing project makes no model or association writes',!posts.some(r=>['/api/chat/send','/api/chat/project-confirm'].includes(r.path)));
  const a=await create('Project Context 工作 A：限定查核 daily.py');await p.waitForSelector('#project-tasks [data-task="'+a+'"]');
  const b=await create('Project Context 工作 B：核對來源結構');await p.waitForSelector('#project-tasks [data-task="'+b+'"]');
  check('actual scoped tasks appear in project',await p.locator('#project-tasks button').count()===2);
  await work(a);const result=await p.evaluate(()=>surfaceInspection().result.result_id);await p.locator('#companion-ask').click();await p.waitForFunction(id=>document.getElementById('companion-context').dataset.task===id,a);await p.locator('#companion-panel .chat-message').first().waitFor({state:'visible'});
  check('project work opens its original Companion conversation',await p.locator('#chat-history').inputValue()===ready.chat);
  await p.locator('#chat-question').fill('專案與工作往返的草稿');await p.locator('#companion-expand').click();await relation('link');
  check('preview shows actual project identity',await p.locator('#project-confirm-copy').innerText().then(s=>s.includes(identity)));
  check('preview does not persist association',(await call('project-get',{chat:ready.chat})).association===null);
  await p.keyboard.press('Escape');check('cancel leaves relation unchanged',(await call('project-get',{chat:ready.chat})).association===null);
  await relation('link');await saveRelation();const linked=await call('project-get',{chat:ready.chat});
  check('explicit confirmation persists exact relation',linked.association.project.id===identity&&!!linked.association.linked_at);
  check('association grants no model sources',await p.locator('#chat-sources input:checked').count()===0&&!posts.some(r=>r.path==='/api/chat/send'));
  await p.reload();await p.waitForFunction(id=>companionProjectStatus().association?.project.id===id,identity);
  await p.waitForFunction(id=>document.getElementById('chat-history').value===id&&document.getElementById('chat-question').value==='專案與工作往返的草稿',ready.chat);
  check('reload preserves link conversation and draft',await p.locator('#chat-history').inputValue()===ready.chat&&await p.locator('#chat-question').inputValue()==='專案與工作往返的草稿');
  await project();await p.waitForSelector('#project-chats [data-chat="'+ready.chat+'"]');check('related conversation is real saved association',await p.locator('#project-chats button').count()===1);
  await p.locator('#project-chats [data-chat="'+ready.chat+'"]').click();await p.waitForFunction(id=>document.body.dataset.route==='chat'&&document.getElementById('chat-history').value===id,ready.chat);await p.locator('#chat-space .chat-message').first().waitFor({state:'visible'});
  check('project conversation entry preserves association without granting sources',await p.locator('#chat-sources input:checked').count()===0&&await fit());
  await p.locator('#companion-share-result').click();await p.locator('#chat-preview').click();await p.waitForFunction(()=>!document.getElementById('chat-knowledge-done').disabled);await p.locator('#chat-knowledge-done').click();
  check('work result still requires explicit selection and preview',await p.locator('#chat-sources input:checked').count()===1);
  await project();check('project navigation revokes source authorization',await p.locator('#chat-sources input:checked').count()===0);
  await p.locator('#project-chats [data-chat="'+ready.chat+'"]').click();await p.waitForFunction(()=>document.body.dataset.route==='chat');await relation('unlink');await saveRelation();await p.reload();await p.waitForFunction(()=>companionProjectStatus().status==='ready');
  check('explicit unlink survives reload',companionNull(await call('project-get',{chat:ready.chat}))&&await p.locator('#project-chat-binding').innerText()==='目前對話未關聯專案');
  await relation('link');await saveRelation();
  const ref=prototype?await context.newPage():null;if(ref){await ref.goto(pathToFileURL(path.resolve(prototype)).href);await ref.locator('[data-ux04-project="ai"]').click();await ref.locator('#screen-project').waitFor({state:'visible'});}
  for(const [width,height]of [[1650,1100],[1440,1000],[390,844],[360,844]]){
   await p.setViewportSize({width,height});await project();
   check(width+' project retains approved hero/content organization',await p.locator('.project-grid').first().evaluate((e,w)=>getComputedStyle(e).gridTemplateColumns.split(' ').length===(w>780?2:1),width));
   check(width+' project has no horizontal overflow',await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   await p.evaluate(()=>scrollTo(0,0));await shot(p,'product-project-'+width);await p.locator('#project-tasks').scrollIntoViewIfNeeded();await shot(p,'product-project-'+width+'-work');
   if(ref){await ref.setViewportSize({width,height});await ref.evaluate(()=>scrollTo(0,0));await ref.waitForTimeout(250);await shot(ref,'prototype-project-'+width);await ref.locator('#ux04-work-items').scrollIntoViewIfNeeded();await shot(ref,'prototype-project-'+width+'-work');comparisons.push({width,height,scale:await p.evaluate(()=>visualViewport.scale),prototypeScale:await ref.evaluate(()=>visualViewport.scale)});}
   await work(a);await p.locator('#companion-ask').click();await p.waitForFunction(()=>document.getElementById('companion-panel').open);await p.locator('#companion-expand').click();await p.waitForFunction(()=>companionProjectStatus().status==='ready');await p.locator('#chat-space .chat-message').first().waitFor({state:'visible'});
   check(width+' full contextual chat has one usable composer',await fit());await shot(p,'product-linked-chat-'+width);
   if(width<=390){await relation('unlink');check(width+' confirmation remains operable',await p.locator('#project-confirm-save').evaluate(e=>{const r=e.getBoundingClientRect();return r.right<=innerWidth&&r.bottom<=innerHeight;}));await p.keyboard.press('Escape');check(width+' cancelling unlink preserves saved relation',!!(await call('project-get',{chat:ready.chat})).association);}
   if(ref){await ref.locator('.nav[data-view="chat"]').click();await ref.waitForTimeout(250);await shot(ref,'prototype-chat-'+width);await ref.locator('[data-ux04-project="ai"]').click();}
   await p.locator('#companion-return').click();await p.waitForFunction(id=>surfaceInspection().result?.task_id===id,a);check(width+' same work and result after conversation',await p.evaluate(()=>surfaceInspection().result.result_id)===result);
   await p.locator('#project-work-return').click();await p.waitForFunction(id=>document.getElementById('nexus-project-page').dataset.project===id,identity);
  }
  await p.setViewportSize({width:1440,height:1000});await p.locator('#nexus-navigation [data-route="chat"]').click();await p.locator('#chat-new').click();
  check('unsaved new chat is honest and cannot pretend to be linked',await p.locator('#project-chat-link').isDisabled()&&await p.locator('#project-chat-binding').innerText()==='新對話尚未保存');
  await p.locator('#chat-question').fill('普通聊天，請勿假裝已讀取專案資料。');await p.locator('#chat-send').click();await p.waitForFunction(()=>document.getElementById('chat-notice').textContent.includes('回答已保存'));const fresh=await p.locator('#chat-history').inputValue();
  const sends=posts.filter(r=>r.path==='/api/chat/send');check('same real chat service saves ordinary synthetic exchange with no sources',fresh!==ready.chat&&sends.length===1&&sends[0].body.sources.length===0&&sends[0].body.preview===null);
  await relation('link');await saveRelation();await project();await p.waitForFunction(()=>document.querySelectorAll('#project-chats button').length===2);
  const changeAccount=async account=>{const ack=new Promise(resolve=>ready.lines.once('line',resolve));ready.child.stdin.write(JSON.stringify({action:'account',account})+'\n');await ack;await p.waitForFunction(account=>companionProjectStatus().account===account,account);};
  await changeAccount('synthetic-other-account');await project();
  check('other account cannot see related chats or work through project',await p.locator('#project-chats button').count()===0&&await p.locator('#project-tasks button').count()===0);
  check('new association API denies known foreign chat ID',(await raw('project-get',{chat:ready.chat})).status===409&&(await raw('project-preview',{chat:ready.chat,action:'link'})).status===409);
  await changeAccount('synthetic-test-account');await project();await p.waitForFunction(()=>document.querySelectorAll('#project-chats button').length===2);
  const other=path.join(out,'other-workspace');fs.mkdirSync(other,{recursive:true});const second=await fixture(other);await p.goto(second.url+'/#project');await p.waitForFunction(()=>!!document.getElementById('nexus-project-page').dataset.project);
  check('same database other workspace has independent real identity and no foreign data',await p.locator('#project-title').innerText()==='other-workspace'&&await p.locator('#project-chats button').count()===0&&await p.locator('#project-tasks button').count()===0);
  check('other workspace new API cannot read existing association',(await raw('project-get',{chat:ready.chat})).status===409);
  await p.locator('#nexus-navigation [data-route="chat"]').click();await p.locator('#chat-history').selectOption(second.chat);await relation('link');await saveRelation();
  check('other workspace only links its own conversation',(await call('project-get',{chat:second.chat})).association.project.id===other);
  await p.goto(ready.url+'/#project');await p.waitForFunction(()=>document.querySelectorAll('#project-chats button').length===2);check('return to original project excludes other workspace relation',await p.locator('#project-chats [data-chat="'+second.chat+'"]').count()===0);
  // An unavailable service must clear the current project display, not retain another owner's data.
  await p.route('**/api/chat/project-context',route=>route.abort());await p.locator('#nexus-navigation [data-route="overview"]').click();await pin().click();await p.waitForFunction(()=>!document.getElementById('nexus-project-page').dataset.project);
  check('unavailable context does not show stale work or associations',await p.locator('#project-tasks button').count()===0&&await p.locator('#project-chats button').count()===0);check('no browser errors',errors.length===0);
 }catch(e){if(p)await p.screenshot({path:path.join(out,'failure.png')}).catch(()=>{});throw e;}
 finally{if(browser){for(const c of browser.contexts())for(const page of c.pages())await page.unrouteAll({behavior:'wait'});await browser.close();}for(const child of children){const ended=new Promise(r=>child.once('exit',r));child.stdin.end('{"action":"stop"}\n');await ended;}fs.writeFileSync(path.join(out,'checks.json'),JSON.stringify({checks,errors,posts,shots,comparisons,syntheticInference:true,realSQLiteAndReviewStore:true,realBoundedAudit:true},null,2));}
 console.log(JSON.stringify({passed:checks.length,errors,out}));
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
function companionNull(value){return value.association===null;}
