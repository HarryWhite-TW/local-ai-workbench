/* UX-03 in Chrome: actual pointer/touch/keyboard, existing HTTP + SQLite +
 * ReviewStore + bounded audit. Only model inference and account faults are synthetic. */
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process'),readline=require('readline');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const out=process.argv[2]||fs.mkdtempSync(path.join(require('os').tmpdir(),'companion-window-'));
fs.mkdirSync(out,{recursive:true});
(async()=>{
 const child=spawn(process.env.PYTHON||'python',['-B',path.join(__dirname,'conversation_work_fixture.py'),out],{windowsHide:true,env:{...process.env,PYTHONUTF8:'1'}});
 let stderr='';child.stderr.on('data',v=>stderr+=v);
 const ready=await new Promise((resolve,reject)=>{readline.createInterface({input:child.stdout}).once('line',s=>resolve(JSON.parse(s)));child.once('exit',()=>reject(Error(stderr)));});
 let browser,p;const checks=[],errors=[],posts=[],shots=[];
 const check=(name,ok)=>{checks.push({name,passed:!!ok});assert.ok(ok,name);};
 try{
  browser=await chromium.launch({channel:'chrome',headless:true,args:['--disable-gpu']});
  p=await browser.newPage({viewport:{width:1440,height:1000},hasTouch:true,reducedMotion:'reduce'});p.setDefaultTimeout(12000);
  p.on('pageerror',e=>errors.push(e.message));p.on('request',r=>{if(r.method()==='POST')posts.push({path:new URL(r.url()).pathname,body:r.postDataJSON()});});
  const shot=async name=>{await p.screenshot({path:path.join(out,name+'.png')});shots.push(name+'.png');};
  const call=(name,body)=>p.evaluate(async({name,body})=>{const r=await fetch('/api/chat/'+name,{method:'POST',headers:{'Content-Type':'application/json','X-Companion-UI':'1'},body:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw Error(data.error);return data;},{name,body});
  const box=id=>p.locator('#'+id).evaluate(e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom};});
  const inside=r=>r.x>=7&&r.y>=7&&r.right<=p.viewportSize().width-7&&r.bottom<=p.viewportSize().height-7;
  const sameBox=(a,b)=>['x','y','width','height'].every(k=>Math.abs(a[k]-b[k])<2);
  const sends=()=>posts.filter(r=>r.path==='/api/chat/send');
  async function drag(id,dx,dy){const r=await box(id);await p.mouse.move(r.x+r.width/2,r.y+r.height/2);await p.mouse.down();await p.mouse.move(r.x+r.width/2+dx,r.y+r.height/2+dy,{steps:8});await p.mouse.up();}
  async function task(chat,turn,goal){const a=await call('work-create',{chat,turn}),v=await call('work-preview',{id:a.id,goal,expected:'限定來源結構證據，不代表功能通過。',selection:['daily']});const work=await call('work-confirm',{id:a.id,approval:v.approval,authority:'READ_ONLY'});await p.waitForFunction(async id=>{const d=await(await fetch('/api/state')).json();return !d.busy&&d.tasks.some(t=>t.task_id===id&&t.state==='RESULT_PENDING_REVIEW');},work.task_id);return work.task_id;}
  async function work(id){await p.evaluate(id=>nexusOpenWork(id),id);await p.waitForFunction(id=>surfaceInspection().result?.task_id===id,id);}
  async function open(id){await p.locator('#companion-ask').click();await p.waitForFunction(id=>document.getElementById('companion-panel').open&&document.getElementById('companion-context').dataset.task===id,id);await p.locator('#companion-panel .chat-message').first().waitFor({state:'visible'});}
  async function preview(){await p.locator('#companion-share-result').click();await p.locator('#chat-preview').click();await p.waitForFunction(()=>!document.getElementById('chat-knowledge-done').disabled);await p.locator('#chat-knowledge-done').click();}
  async function send(question){await p.locator('#chat-question').fill(question);const response=p.waitForResponse(r=>r.url().endsWith('/api/chat/send'));await p.locator('#chat-send').click();assert.ok((await response).ok());await p.waitForFunction(()=>!document.getElementById('chat-send').disabled&&document.getElementById('chat-notice').textContent.includes('回答已保存'));}
  await p.goto(ready.url);await p.waitForFunction(()=>!surfaceInspection().offline);
  const a=await task(ready.chat,ready.turn,'UX-03 工作 A：查核來源結構');
  const bChat=await call('send',{chat:null,question:'另一個工作與對話 B',model:'synthetic-model',sources:[],preview:null});
  await p.waitForFunction(async({chat,turn})=>{const response=await fetch('/api/chat/get',{method:'POST',headers:{'Content-Type':'application/json','X-Companion-UI':'1'},body:JSON.stringify({chat})});const data=await response.json();return data.turns.some(t=>t.id===turn&&t.status==='complete');},bChat);
  const b=await task(bChat.chat,bChat.turn,'UX-03 工作 B：另一段對話');
  await work(a);await open(a);
  check('non-modal dialog without background inertness',await p.locator('#companion-panel').evaluate(e=>!e.matches(':modal')&&!document.getElementById('work-space').inert));
  await p.locator('#brief-tab').click();check('background pointer input remains available',await p.locator('#brief-tab').getAttribute('aria-selected')==='true'&&await p.locator('#companion-panel').isVisible());
  await p.locator('#result-tab').click();await p.evaluate(()=>scrollTo(0,200));check('background can scroll with open Companion',await p.evaluate(()=>scrollY>0));await p.evaluate(()=>scrollTo(0,0));
  let r=await box('companion-panel');await drag('companion-window-resize',-40,-200);let resized=await box('companion-panel');
  check('pointer resizes both width and height',resized.width<r.width-20&&resized.height<r.height-100);
  r=resized;await drag('companion-panel-title',-200,-50);let moved=await box('companion-panel');check('pointer moves floating window',moved.x<r.x-150&&moved.y<r.y-30);
  r=moved;await drag('companion-window-resize',80,60);resized=await box('companion-panel');check('pointer can grow width and height',resized.width>r.width+60&&resized.height>r.height+40);
  await drag('companion-panel-title',-4000,-4000);check('drag cannot lose window beyond top/left',inside(await box('companion-panel')));
  await drag('companion-panel-title',4000,4000);check('drag cannot lose window beyond bottom/right',inside(await box('companion-panel')));
  r=await box('companion-panel');await p.locator('#companion-panel-title').focus();await p.keyboard.press('Shift+ArrowLeft');moved=await box('companion-panel');check('keyboard moves window',moved.x<r.x-20);
  r=moved;await p.locator('#companion-window-resize').focus();await p.keyboard.press('Shift+ArrowLeft');await p.keyboard.press('Shift+ArrowUp');resized=await box('companion-panel');check('keyboard resizes both dimensions',resized.width<r.width-20&&resized.height<r.height-20);
  await p.locator('#chat-question').fill('各種模式共用的草稿');await shot('floating-desktop');
  for(const mode of ['floating','dock-left','dock-right','split-left','split-right','reading']){
   await p.locator('#companion-window-mode').selectOption(mode);
   check(mode+' keeps same conversation and work',await p.locator('#chat-history').inputValue()===ready.chat&&await p.locator('#companion-context').getAttribute('data-task')===a&&p.url().includes('task='+a));
   check(mode+' preserves draft',await p.locator('#chat-question').inputValue()==='各種模式共用的草稿');
   const panel=await box('companion-panel'),workspace=await box('work-space');check(mode+' remains inside viewport',inside(panel));
   if(mode.endsWith('left'))check(mode+' reserves background space',workspace.x>=panel.right-1);
   if(mode.endsWith('right'))check(mode+' reserves background space',workspace.right<=panel.x+1);
   await send('合成驗證：'+mode+' 模式沿用原對話，沒有附加工作資料。');
   check(mode+' send uses existing API without implicit context',sends().at(-1).body.chat===ready.chat&&sends().at(-1).body.sources.length===0&&sends().at(-1).body.preview===null);
   await p.locator('#chat-question').fill('各種模式共用的草稿');await shot(mode+'-desktop');
  }
  const saved=await call('get',{chat:ready.chat});check('all mode replies persist in one SQLite history',saved.turns.length===7&&saved.turns.every(t=>t.status==='complete'));
  await p.locator('#companion-window-mode').selectOption('dock-left');await p.locator('#nexus-focus').click();
  check('docking respects hidden navigation rail',(await box('work-space')).x>=(await box('companion-panel')).right-1);await p.locator('#nexus-focus').click();
  await p.locator('#open-reader').click();await p.locator('#reader-body').focus();await p.keyboard.press('Escape');
  check('Escape in result reader leaves Companion open',!await p.locator('#reader').isVisible()&&await p.locator('#companion-panel').isVisible());
  await p.locator('#open-reader').click();await p.locator('#chat-question').focus();await p.keyboard.press('Escape');
  check('Escape in Companion leaves result reader open',await p.locator('#reader').isVisible()&&!await p.locator('#companion-panel').isVisible());await p.locator('#reader-close').click();await open(a);
  await p.locator('#companion-window-mode').selectOption('floating');await preview();check('explicit preview grants only current selection',await p.locator('#chat-sources input:checked').count()===1);
  await p.locator('#companion-window-mode').selectOption('split-right');check('mode change revokes source selection',await p.locator('#chat-sources input:checked').count()===0);
  await p.locator('#companion-window-mode').selectOption('floating');const beforeMin=await box('companion-panel');await preview();await p.locator('#companion-minimize').click();
  check('minimize leaves a separate restore control',!await p.locator('#companion-panel').isVisible()&&await p.locator('#companion-mini').isVisible());
  check('minimize revokes source authority',await p.locator('#chat-sources input:checked').count()===0);
  r=await box('companion-mini');await drag('companion-mini-move',-450,-350);moved=await box('companion-mini');check('mini can move without accidental restore',moved.x<r.x-300&&moved.y<r.y-200&&!await p.locator('#companion-panel').isVisible());
  r=moved;await drag('companion-mini-resize',80,35);resized=await box('companion-mini');check('mini pointer resizes both dimensions',resized.width>r.width+50&&resized.height>r.height+20);
  await p.locator('#companion-mini-move').focus();r=await box('companion-mini');await p.keyboard.press('ArrowLeft');moved=await box('companion-mini');check('mini supports keyboard move',moved.x<r.x-5);
  await p.locator('#companion-mini-resize').focus();r=moved;await p.keyboard.press('ArrowRight');await p.keyboard.press('ArrowDown');resized=await box('companion-mini');check('mini supports keyboard width and height',resized.width>r.width+5&&resized.height>r.height+5);
  const miniConfig=resized;await shot('mini-custom-desktop');await p.locator('#companion-restore').click();
  check('restore keeps main geometry and original chat',sameBox(beforeMin,await box('companion-panel'))&&await p.locator('#chat-history').inputValue()===ready.chat);
  check('restore does not regain source consent',await p.locator('#chat-sources input:checked').count()===0&&await p.locator('#chat-question').inputValue()==='各種模式共用的草稿');
  const prefs=await p.evaluate(()=>JSON.parse(localStorage.getItem('companion.nexus.window.v1')));check('saved preferences contain geometry only',Object.keys(prefs).sort().join(',')==='mini,mode,window'&&!JSON.stringify(prefs).includes(a)&&!JSON.stringify(prefs).includes(ready.chat));
  await p.locator('#companion-minimize').click();await p.reload();await p.waitForFunction(id=>surfaceInspection().result?.task_id===id,a);
  check('reload never auto-opens old context or authority',!await p.locator('#companion-panel').isVisible()&&!await p.locator('#companion-mini').isVisible()&&await p.locator('#chat-sources input:checked').count()===0);
  await open(a);check('reload restores main window configuration',sameBox(beforeMin,await box('companion-panel')));await p.locator('#companion-minimize').click();check('reload restores mini position and dimensions',sameBox(miniConfig,await box('companion-mini')));
  await p.setViewportSize({width:360,height:740});check('mini stays visible after viewport shrink',inside(await box('companion-mini')));
  const touch=await p.context().newCDPSession(p),handle=await box('companion-mini-move');r=await box('companion-mini');
  const x=handle.x+handle.width/2,y=handle.y+handle.height/2;
  await touch.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y}]});await touch.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:x-12,y:y-30}]});await touch.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await touch.detach();
  moved=await box('companion-mini');check('mini supports touch dragging at 360',moved.y<r.y-15&&!await p.locator('#companion-panel').isVisible());await shot('mini-360');
  await p.locator('#companion-restore').focus();await p.keyboard.press('Enter');check('explicit keyboard restore remains usable at 360',await p.locator('#companion-panel').isVisible()&&inside(await box('companion-panel')));
  for(const mode of ['floating','dock-left','dock-right','split-left','split-right','reading']){
   await p.locator('#companion-window-mode').selectOption(mode);check(mode+' fits 360',inside(await box('companion-panel'))&&await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   if(mode!=='floating'&&mode!=='reading'){
    check(mode+' stacks rather than overlaps workspace',await p.evaluate(()=>document.body.dataset.companionLayout==='stacked')&&(await box('work-space')).bottom<=(await box('companion-panel')).y+1);
    await p.locator('#brief-tab').click();check(mode+' background remains operable at 360',await p.locator('#brief-tab').getAttribute('aria-selected')==='true');
    await p.locator('#result-tab').click();
   }
   check(mode+' input stays below messages',await p.evaluate(()=>document.getElementById('chat-messages').getBoundingClientRect().bottom<=document.getElementById('chat-form').getBoundingClientRect().top+1));
  }
  await shot('reading-360');await p.locator('#companion-window-mode').selectOption('split-right');await shot('split-360');
  await p.locator('#companion-window-mode').selectOption('floating');await p.locator('#companion-window-resize').focus();await p.keyboard.press('Shift+ArrowUp');check('narrow window also resizes by keyboard',inside(await box('companion-panel')));
  await p.locator('#companion-minimize').click();await p.locator('#companion-mini-move').focus();await p.keyboard.press('Escape');check('Escape closes minimized control',!await p.locator('#companion-mini').isVisible());
  await p.setViewportSize({width:1440,height:1000});await open(a);await p.locator('#companion-window-mode').selectOption('dock-left');
  await p.locator('#companion-expand').click();check('full chat remains a separate navigation using same history',p.url().includes('chat='+ready.chat)&&await p.locator('#chat-history').inputValue()===ready.chat&&!await p.locator('#companion-panel').isVisible());
  await p.locator('#companion-return').click();await p.waitForFunction(id=>surfaceInspection().result?.task_id===id,a);check('full chat returns to exact original work',p.url().includes(a));
  await open(a);await p.locator('#companion-minimize').click();await work(b);check('changing work removes old mini association',!await p.locator('#companion-mini').isVisible());await open(b);
  check('work B resolves correct distinct history',await p.locator('#chat-history').inputValue()===bChat.chat&&await p.locator('#companion-context').getAttribute('data-task')===b&&await p.locator('#chat-question').inputValue()==='');
  await p.locator('#companion-window-mode').selectOption('floating');await p.locator('#companion-close').click();await p.locator('#open-chat').click();await p.locator('#chat-new').click();check('switching conversation clears old work link',await p.locator('#companion-context').isHidden());
  await work(b);await open(b);await p.locator('#companion-minimize').click();
  await p.route('**/api/chat/state',async route=>{const response=await route.fetch(),data=await response.json();data.auth.active='synthetic-other-account';await route.fulfill({response,json:data});});
  await p.waitForFunction(()=>document.getElementById('companion-mini').hidden&&document.getElementById('chat-question').value==='');check('account change clears minimized context',!await p.locator('#companion-mini').isVisible()&&await p.locator('#companion-context').isHidden());
  check('only explicit synthetic messages were sent',sends().length===7);check('no browser errors',errors.length===0);
 }catch(e){if(p)await p.screenshot({path:path.join(out,'failure.png')}).catch(()=>{});throw e;}
 finally{if(browser)await browser.close();const ended=new Promise(r=>child.once('exit',r));child.stdin.end('{"action":"stop"}\n');await ended;fs.writeFileSync(path.join(out,'checks.json'),JSON.stringify({checks,errors,posts,shots,syntheticInference:true,realBoundedAudit:true},null,2));}
 console.log(JSON.stringify({passed:checks.length,errors,out}));
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
