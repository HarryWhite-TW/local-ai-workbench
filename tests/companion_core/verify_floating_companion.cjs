/* Chrome + real Conversations/SQLite/ReviewStore/bounded audit. Inference and
 * unavailable-service cases are synthetic and explicitly identified in evidence. */
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process'),readline=require('readline');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const out=process.argv[2]||fs.mkdtempSync(path.join(require('os').tmpdir(),'companion-floating-'));
fs.mkdirSync(out,{recursive:true});
(async()=>{
  const child=spawn(process.env.PYTHON||'python',['-B',path.join(__dirname,'conversation_work_fixture.py'),out],{windowsHide:true,env:{...process.env,PYTHONUTF8:'1'}});
  let stderr='';child.stderr.on('data',v=>stderr+=v);
  const ready=await new Promise((resolve,reject)=>{readline.createInterface({input:child.stdout}).once('line',s=>resolve(JSON.parse(s)));child.once('exit',()=>reject(Error(stderr)));});
  let browser,p;const checks=[],errors=[],posts=[],shots=[];
  const check=(name,ok)=>{checks.push({name,passed:!!ok});assert.ok(ok,name);};
  try{
    // Software rendering avoids Windows headless GPU screenshot composition artifacts.
    browser=await chromium.launch({channel:'chrome',headless:true,args:['--disable-gpu']});p=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});p.setDefaultTimeout(12000);
    p.on('pageerror',e=>errors.push(e.message));p.on('request',r=>{if(r.method()==='POST')posts.push({path:new URL(r.url()).pathname,body:r.postDataJSON()});});
    const shot=async name=>{await p.screenshot({path:path.join(out,name+'.png')});shots.push(name+'.png');};
    const call=(name,body)=>p.evaluate(async({name,body})=>{
      const r=await fetch('/api/chat/'+name,{method:'POST',headers:{'Content-Type':'application/json','X-Companion-UI':'1'},body:JSON.stringify(body)}),data=await r.json();if(!r.ok)throw Error(data.error);return data;
    },{name,body});
    const sends=()=>posts.filter(r=>r.path==='/api/chat/send');
    async function createWork(chat,turn,goal){
      const proposal=await call('work-create',{chat,turn});
      const preview=await call('work-preview',{id:proposal.id,goal,expected:'僅檔案結構紀錄；不推定功能可用。',selection:['daily']});
      const result=await call('work-confirm',{id:proposal.id,approval:preview.approval,authority:'READ_ONLY'});
      await p.waitForFunction(async id=>{const d=await(await fetch('/api/state')).json();return !d.busy&&d.tasks.some(t=>t.task_id===id&&t.state==='RESULT_PENDING_REVIEW');},result.task_id);
      return result.task_id;
    }
    async function work(id){await p.evaluate(id=>nexusOpenWork(id),id);await p.waitForFunction(id=>surfaceInspection().result?.task_id===id,id);}
    async function open(id){await p.locator('#companion-ask').click();await p.waitForFunction(id=>document.getElementById('companion-panel').open&&document.getElementById('companion-context').dataset.task===id&&!document.getElementById('chat-space').hidden,id);await p.locator('#companion-panel .chat-message').first().waitFor({state:'visible'});}
    async function send(question){await p.locator('#chat-question').fill(question);const response=p.waitForResponse(r=>r.url().endsWith('/api/chat/send'));await p.locator('#chat-send').click();assert.ok((await response).ok());await p.waitForFunction(()=>!document.getElementById('chat-send').disabled&&document.getElementById('chat-notice').textContent.includes('回答已保存'));}
    await p.goto(ready.url);await p.waitForFunction(()=>!surfaceInspection().offline);
    const taskA=await createWork(ready.chat,ready.turn,'工作 A：查核 daily.py 的來源結構');
    const b=await call('send',{chat:null,question:'工作 B 的獨立討論',model:'synthetic-model',sources:[],preview:null});
    await p.waitForFunction(async()=>!(await(await fetch('/api/chat/state')).json()).busy);
    const taskB=await createWork(b.chat,b.turn,'工作 B：另一個對話的查核');
    await work(taskA);const before=sends().length;
    check('ask is available in actual task detail',await p.locator('#companion-ask').isVisible());
    await open(taskA);
    check('only one conversation interface exists',await p.locator('#chat-space').count()===1&&await p.locator('#companion-panel #chat-space').count()===1);
    check('correct original history selected',await p.locator('#chat-history').inputValue()===ready.chat&&await p.locator('.chat-message').count()===1);
    check('actual work name and status',/工作 A/.test(await p.locator('#companion-task-name').textContent())&&/等待審查/.test(await p.locator('#companion-task-state').textContent()));
    check('opening never sends or grants sources',sends().length===before&&await p.locator('#chat-sources input:checked').count()===0);
    check('consent distinguishes identity from shared content',/本次未加入工作資料/.test(await p.locator('#companion-sharing').textContent()));
    check('input receives keyboard focus',await p.locator('#chat-question').evaluate(e=>e===document.activeElement));
    check('Companion is non-modal',await p.locator('#companion-panel').evaluate(e=>!e.matches(':modal')));
    await p.locator('#brief-tab').focus();await p.keyboard.press('Space');
    check('keyboard can operate background without closing Companion',await p.locator('#brief-tab').getAttribute('aria-selected')==='true'&&await p.locator('#companion-panel').isVisible());
    await p.locator('#result-tab').click();
    await p.locator('#chat-question').fill('工作 A 尚未送出的草稿');await shot('floating-desktop');
    const scroll=await p.evaluate(()=>scrollY);await p.keyboard.press('Escape');
    check('Escape closes panel and returns focus',!await p.locator('#companion-panel').isVisible()&&await p.locator('#companion-ask').evaluate(e=>e===document.activeElement));
    check('work reading position retained',await p.evaluate(y=>Math.abs(scrollY-y)<2,scroll));
    await open(taskA);check('reopening keeps same draft',await p.locator('#chat-question').inputValue()==='工作 A 尚未送出的草稿');
    await send('普通聊天：本輪沒有提供工作資料。');
    const ordinary=sends().at(-1).body;check('plain chat has no implicit task content',ordinary.chat===ready.chat&&ordinary.sources.length===0&&ordinary.preview===null&&Object.keys(ordinary).sort().join(',')==='chat,model,preview,question,sources');
    let saved=await call('get',{chat:ready.chat});check('ordinary answer saved by same SQLite conversation',saved.turns.length===2&&saved.turns.at(-1).status==='complete'&&saved.turns.at(-1).sources.length===0);
    await p.locator('#companion-share-result').click();await p.locator('#chat-knowledge').waitFor({state:'visible'});
    check('result cannot send before preview',await p.locator('#chat-send').isDisabled()&&await p.locator('#chat-knowledge-done').isDisabled());
    await p.locator('#chat-preview').click();await p.waitForFunction(()=>!document.getElementById('chat-knowledge-done').disabled);
    check('preview is actual trusted audit',/可信本機唯讀查核紀錄/.test(await p.locator('#chat-source-preview').textContent())&&/daily.py/.test(await p.locator('#chat-source-preview').textContent()));
    await shot('source-preview-desktop');await p.keyboard.press('Escape');
    check('Escape closes source dialog first',!await p.locator('#chat-knowledge').isVisible()&&await p.locator('#companion-panel').isVisible());
    check('explicit source disclosure names provided content',/本次提供：已保存工作成果：工作 A/.test(await p.locator('#companion-sharing').textContent()));
    await send('根據已預覽成果，區分已確認與未確認。');
    const grounded=sends().at(-1).body;check('only explicit source preview permits grounded message',grounded.chat===ready.chat&&grounded.sources.length===1&&grounded.sources[0].startsWith('work:')&&Object.keys(grounded.preview).length===1);
    saved=await call('get',{chat:ready.chat});check('source snapshot remains in authoritative saved turn',saved.turns.at(-1).sources.length===1&&saved.turns.at(-1).sources[0].text.includes('可信本機唯讀查核紀錄'));
    check('send consumes this source selection',await p.locator('#chat-sources input:checked').count()===0);
    await p.locator('#chat-question').fill('展開完整對話後接續的草稿');await p.locator('#companion-share-result').click();await p.locator('#chat-preview').click();await p.waitForFunction(()=>!document.getElementById('chat-knowledge-done').disabled);await p.locator('#chat-knowledge-done').click();
    await p.locator('#companion-expand').click();
    check('expand uses full existing conversation',!await p.locator('#companion-panel').isVisible()&&await p.locator('#chat-history').inputValue()===ready.chat&&await p.locator('#chat-space').isVisible()&&p.url().includes('chat='+ready.chat));
    check('expand preserves draft but revokes source consent',await p.locator('#chat-question').inputValue()==='展開完整對話後接續的草稿'&&await p.locator('#chat-sources input:checked').count()===0);
    await send('完整對話繼續交流，未重新提供成果。');
    check('full conversation continues same ID without automatic sources',sends().at(-1).body.chat===ready.chat&&sends().at(-1).body.sources.length===0);
    await p.locator('#chat-question').fill('返回工作後保留的草稿');await p.reload();await p.locator('#companion-return').waitFor({state:'visible'});
    check('full reload restores contextual return without authority',await p.locator('#companion-context').getAttribute('data-task')===taskA&&await p.locator('#chat-sources input:checked').count()===0);
    await p.locator('#companion-return').click();await p.waitForFunction(id=>surfaceInspection().result?.task_id===id,taskA);
    check('returns to same work and trusted result',p.url().includes('task='+taskA)&&await p.locator('#result-text .raw-evidence').count()===1);
    await open(taskA);check('return to work preserves draft',await p.locator('#chat-question').inputValue()==='返回工作後保留的草稿');await p.locator('#companion-close').click();
    await work(taskB);await open(taskB);check('work B never retains A context or draft',await p.locator('#companion-context').getAttribute('data-task')===taskB&&await p.locator('#chat-history').inputValue()===b.chat&&await p.locator('#chat-question').inputValue()===''&&!/工作 A/.test(await p.locator('#companion-task-name').textContent()));
    await p.locator('#chat-question').fill('工作 B 的獨立草稿');await p.reload();await p.waitForFunction(id=>surfaceInspection().result?.task_id===id,taskB);
    check('reload leaves panel closed with exact work',!await p.locator('#companion-panel').isVisible()&&p.url().includes(taskB));await open(taskB);
    check('reload draft does not restore sources',await p.locator('#chat-question').inputValue()==='工作 B 的獨立草稿'&&await p.locator('#chat-sources input:checked').count()===0);await p.locator('#companion-close').click();
    // Explicit delayed-response fixture: an old origin cannot reopen over another task.
    await work(taskA);await p.route('**/api/chat/work-origin',async route=>{await new Promise(r=>setTimeout(r,400));await route.continue();});
    await p.locator('#companion-ask').click();await work(taskB);await p.waitForTimeout(550);
    check('changing work closes panel and invalidates late origin',!await p.locator('#companion-panel').isVisible()&&await p.locator('#companion-panel').getAttribute('data-task')==='');await p.unrouteAll({behavior:'wait'});
    // Long Markdown is an explicit response projection, never a saved AI answer.
    await p.route('**/api/chat/get',async route=>{const response=await route.fetch(),data=await response.json();if(data.id===b.chat)data.turns[0].answer='# 長答案閱讀\n\n<img src=x onerror="window.bad=true"> [unsafe](javascript:alert(1))\n\n'+('尚未確認的功能仍需要實際操作證據。\n\n'.repeat(70));await route.fulfill({response,json:data});});
    await p.setViewportSize({width:360,height:740});await open(taskB);await p.waitForSelector('#companion-panel .markdown h2');await p.locator('#chat-messages').evaluate(e=>e.scrollTop=400);
    await p.locator('#companion-close').click();await open(taskB);await p.waitForFunction(()=>Math.abs(document.getElementById('chat-messages').scrollTop-400)<3);
    check('floating long answer retains reading position',await p.locator('#chat-messages').evaluate(e=>e.scrollHeight>e.clientHeight*4));
    check('long answer keeps panel controls visible and hit-testable',await p.locator('#companion-close').evaluate(e=>{const r=e.getBoundingClientRect();return r.top>=0&&r.right<=innerWidth&&document.elementFromPoint(r.left+r.width/2,r.top+r.height/2)===e;}));
    check('floating Markdown remains safe',await p.evaluate(()=>!window.bad&&!document.querySelector('#companion-panel .markdown img,#companion-panel .markdown a[href^="javascript:"]')));await shot('floating-360');await p.unrouteAll({behavior:'wait'});
    check('360 panel fits viewport',await p.locator('#companion-panel').evaluate(e=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight;}));
    check('360 input never covers messages',await p.evaluate(()=>document.getElementById('chat-messages').getBoundingClientRect().bottom<=document.getElementById('chat-form').getBoundingClientRect().top+1));
    for(const id of ['chat-send','companion-close','companion-expand'])check('360 reachable '+id,await p.locator('#'+id).evaluate(e=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.bottom<=innerHeight;}));
    check('360 no horizontal overflow',await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await p.keyboard.press('Escape');
    // Explicit unavailable-origin fixture, not a fabricated conversation or result.
    await p.route('**/api/chat/work-origin',route=>route.fulfill({status:409,json:{error:'目前工作沒有可確認的原對話連結。'}}));
    await p.locator('#companion-ask').click();await p.locator('#companion-start-new').waitFor({state:'visible'});
    check('missing origin is explicit and shows no old chat',/沒有可確認/.test(await p.locator('#companion-link-notice').textContent())&&!await p.locator('#chat-space').isVisible());await shot('no-origin-360');
    await p.locator('#companion-start-new').click();check('ordinary new chat has no fabricated history',await p.locator('.chat-message').count()===0&&await p.locator('#companion-share-result').isDisabled());
    await send('沒有原對話時，普通聊天仍可明確建立。');const unlinked=sends().at(-1).body;check('unlinked task is never smuggled into new conversation',unlinked.chat===null&&unlinked.sources.length===0&&unlinked.preview===null);
    const newChat=await p.locator('#chat-history').inputValue();check('new chat created by existing service',!!newChat&&newChat!==ready.chat&&newChat!==b.chat);
    await p.locator('#companion-expand').click();await p.locator('#companion-return').click();await p.waitForFunction(id=>surfaceInspection().selected===id&&document.body.dataset.route==='work',taskB);await p.unrouteAll({behavior:'wait'});
    await open(taskB);check('reopen resolves real origin rather than assuming new link',await p.locator('#chat-history').inputValue()===b.chat);
    // Model/data failures are honest and do not synthesize responses.
    await p.route('**/api/chat/state',async route=>{const response=await route.fetch(),data=await response.json();data.models=[];await route.fulfill({response,json:data});});
    await p.route('**/api/chat/models',route=>route.fulfill({status:409,json:{error:'合成情境：模型清單不可用。'}}));
    await p.waitForFunction(()=>document.getElementById('chat-send').disabled&&document.getElementById('chat-ready').textContent.includes('模型尚未就緒'));
    check('unavailable model disables send with explanation',/模型尚未就緒/.test(await p.locator('#chat-ready').textContent()));await p.unrouteAll({behavior:'wait'});await p.waitForFunction(()=>!document.getElementById('chat-send').disabled);
    await p.route('**/api/chat/preview',route=>route.fulfill({status:409,json:{error:'合成情境：成果目前不可讀取。'}}));
    await p.locator('#companion-share-result').click();await p.locator('#chat-preview').click();await p.waitForFunction(()=>document.getElementById('chat-preview-notice').textContent.includes('不可讀取'));
    check('unavailable evidence cannot gain preview authority',await p.locator('#chat-send').isDisabled()&&await p.locator('#chat-knowledge-done').isDisabled());await p.keyboard.press('Escape');await p.unrouteAll({behavior:'wait'});
    const beforeAccount=posts.length;
    await p.route('**/api/chat/state',async route=>{const response=await route.fetch(),data=await response.json();data.auth.active='synthetic-other-account';await route.fulfill({response,json:data});});
    await p.waitForFunction(()=>!document.getElementById('companion-panel').open&&document.getElementById('chat-question').value==='');await p.waitForTimeout(1600);
    check('account change closes panel clears context and consent',await p.locator('#companion-context').isHidden()&&await p.locator('#chat-sources input:checked').count()===0);
    check('panel does not read former account conversation',!posts.slice(beforeAccount).some(r=>r.path==='/api/chat/get'&&[ready.chat,b.chat].includes(r.body.chat)));
    check('only explicit test messages invoked synthetic inference',sends().length===5);check('no browser errors',errors.length===0);
  }catch(e){if(p)await p.screenshot({path:path.join(out,'failure.png')}).catch(()=>{});throw e;}
  finally{if(browser)await browser.close();const exited=new Promise(r=>child.once('exit',r));child.stdin.end('{"action":"stop"}\n');await exited;fs.writeFileSync(path.join(out,'checks.json'),JSON.stringify({checks,errors,posts,shots,syntheticInference:true,realBoundedAudit:true},null,2));}
  console.log(JSON.stringify({passed:checks.length,errors,out}));
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
