/* Approved v2 alignment in Chrome. Isolated SQLite and real bounded audit;
 * model/account and state-fault cases are synthetic. Optional prototype is visual reference only. */
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process'),readline=require('readline'),{pathToFileURL}=require('url');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const out=path.resolve(process.argv[2]||fs.mkdtempSync(path.join(require('os').tmpdir(),'nexus-layout-'))),prototype=process.argv[3];
fs.mkdirSync(out,{recursive:true});
(async()=>{
 const child=spawn(process.env.PYTHON||'python',['-B',path.join(__dirname,'conversation_work_fixture.py'),out],{windowsHide:true,env:{...process.env,PYTHONUTF8:'1'}});
 let stderr='';child.stderr.on('data',s=>stderr+=s);
 const ready=await new Promise((resolve,reject)=>{readline.createInterface({input:child.stdout}).once('line',s=>resolve(JSON.parse(s)));child.once('exit',()=>reject(Error(stderr)));});
 let browser;const checks=[],errors=[],shots=[],comparisons=[];
 const check=(name,ok)=>{checks.push({name,passed:!!ok});assert.ok(ok,name);};
 try {
  browser=await chromium.launch({channel:'chrome',headless:true,args:['--disable-gpu']});
  const context=await browser.newContext({viewport:{width:1650,height:1100},deviceScaleFactor:1,reducedMotion:'reduce'});
  const p=await context.newPage();p.setDefaultTimeout(12000);p.on('pageerror',e=>errors.push(e.message));
  await p.goto(ready.url);await p.waitForFunction(()=>!surfaceInspection().offline);
  check('honest empty overview',await p.locator('#nexus-recent').innerText().then(s=>s.includes('沒有'))&&await p.locator('#nexus-peek-open').isDisabled());
  const call=(name,body)=>p.evaluate(async({name,body})=>{const r=await fetch('/api/chat/'+name,{method:'POST',headers:{'Content-Type':'application/json','X-Companion-UI':'1'},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.error);return d;},{name,body});
  async function create(goal){const a=await call('work-create',{chat:ready.chat,turn:ready.turn}),v=await call('work-preview',{id:a.id,goal,expected:'限定來源結構，不推定完整功能通過。',selection:['daily']});const w=await call('work-confirm',{id:a.id,approval:v.approval,authority:'READ_ONLY'});await p.waitForFunction(async id=>{const d=await(await fetch('/api/state')).json();return !d.busy&&d.tasks.some(t=>t.task_id===id&&t.state==='RESULT_PENDING_REVIEW');},w.task_id);return w.task_id;}
  const a=await create('版面驗證工作 A：限定查核 daily.py'),b=await create('版面驗證工作 B：確認實際來源結構');
  await p.waitForSelector('#nexus-recent [data-task="'+b+'"]');
  await p.locator('#nexus-recent [data-task="'+a+'"]').click();
  check('recent selection stays on overview',await p.locator('#nexus-overview').isVisible());
  check('summary uses selected actual identity',await p.locator('#nexus-work-peek').getAttribute('data-task')===a&&(await p.locator('#nexus-peek-title').innerText()).includes('工作 A'));
  check('summary does not fabricate content verification',/可信成果已保存/.test(await p.locator('#nexus-peek-confirmed').innerText())&&/工作狀態不代表/.test(await p.locator('#nexus-peek-limit').innerText()));
  await p.locator('#nexus-peek-open').click();await p.waitForFunction(id=>surfaceInspection().result?.task_id===id,a);
  check('summary opens exact trusted work',p.url().includes('task='+a)&&await p.locator('#result-text .raw-evidence pre').count()===1);
  await p.locator('#companion-ask').click();await p.waitForFunction(id=>document.getElementById('companion-context').dataset.task===id,a);
  await p.locator('#companion-panel .chat-message').first().waitFor({state:'visible'});
  await p.locator('#companion-window-mode').selectOption('split-left');
  for(const mode of ['collapsed','expanded']) {
   await p.locator('#nexus-sidebar-toggle').click();
   const fit=await p.evaluate(()=>{
    const rail=document.getElementById('nexus-sidebar').getBoundingClientRect(),panel=document.getElementById('companion-panel').getBoundingClientRect(),work=document.getElementById('work-space').getBoundingClientRect();
    return panel.left>=rail.right&&work.left>=panel.right;
   });
   check('Companion split adjusts to '+mode+' rail',fit&&await p.locator('#companion-context').getAttribute('data-task')===a&&await p.locator('#chat-history').inputValue()===ready.chat);
  }
  await p.locator('#companion-close').click();
  await p.locator('#work-origin').click();await p.waitForSelector('#chat-space',{state:'visible'});
  check('work returns to original conversation',await p.locator('#chat-history').inputValue()===ready.chat);
  await p.locator('#chat-question').fill('版面切換後仍保留的草稿');
  await p.locator('#nexus-navigation [data-route="overview"]').click();
  async function shot(page,name){await page.screenshot({path:path.join(out,name+'.png')});shots.push(name+'.png');}
  const ref=prototype?await context.newPage():null;
  if(ref)await ref.goto(pathToFileURL(path.resolve(prototype)).href);
  async function metrics(page,reference){return page.evaluate(reference=>{
   const q=s=>document.querySelector(s),grid=q(reference?'.align-modules':'.nexus-modules'),cards=[...grid.children],r=cards[0].getBoundingClientRect(),side=q(reference?'.sidebar':'.nexus-sidebar');
   return {width:innerWidth,scale:visualViewport.scale,dpr:devicePixelRatio,columns:getComputedStyle(grid).gridTemplateColumns.split(' ').length,count:cards.length,cardWidth:r.width,cardHeight:r.height,bodyFont:getComputedStyle(document.body).fontSize,descriptionFont:getComputedStyle(cards[0].querySelector('p')).fontSize,titleFont:getComputedStyle(cards[0].querySelector(reference?'h3':'h2')).fontSize,sidebar:side.getBoundingClientRect().width,overflow:document.documentElement.scrollWidth>innerWidth+1};
  },reference);}
  for(const [width,height] of [[1650,1100],[1440,1000],[390,844],[360,800]]) {
   for(const page of [p,ref].filter(Boolean))await page.setViewportSize({width,height});
   for(const mode of width>780?['expanded','collapsed']:['collapsed']) {
    for(const [page,reference] of [[p,false],[ref,true]].filter(([page])=>page)) {
     const toggle=page.locator(reference?'#sidebar-toggle':'#nexus-sidebar-toggle');
     if(await page.locator('body').getAttribute('data-sidebar')!==mode)await toggle.click();
     await page.evaluate(()=>scrollTo(0,0));await page.waitForTimeout(250);
     const m=await metrics(page,reference);comparisons.push({reference,mode,...m});
     check(`${reference?'prototype':'product'} ${width} ${mode}: zoom, grid and no overflow`,m.scale===1&&m.dpr===1&&m.count===7&&m.columns===(width>780?2:1)&&!m.overflow);
     check(`${reference?'prototype':'product'} ${width} ${mode}: readable type and rail`,m.descriptionFont==='14px'&&m.titleFont===(width<=780?'18px':'19px')&&m.sidebar===(width<=780?60:mode==='collapsed'?74:252));
     await shot(page,`${reference?'prototype':'product'}-${width}-${mode}-top`);
     await page.locator(reference?'.align-bottom':'#nexus-recent-section').scrollIntoViewIfNeeded();
     await shot(page,`${reference?'prototype':'product'}-${width}-${mode}-recent`);
    }
   }
   if(width<=780) {
    for(const [page,reference] of [[p,false],[ref,true]].filter(([page])=>page)) {
     await page.locator(reference?'#sidebar-toggle':'#nexus-sidebar-toggle').click();
     await shot(page,`${reference?'prototype':'product'}-${width}-expanded-nav`);
     await page.keyboard.press('Escape');
     check(`${reference?'prototype':'product'} ${width}: Escape restores compact rail`,await page.locator('body').getAttribute('data-sidebar')==='collapsed');
    }
   }
  }
  await p.setViewportSize({width:1440,height:1000});
  await p.locator('#nexus-sidebar-toggle').focus();await p.keyboard.press('Enter');
  check('keyboard toggle exposes complete labels',await p.locator('body').getAttribute('data-sidebar')==='expanded'&&await p.locator('.nexus-nav-label:visible').count()===8);
  await p.keyboard.press('Space');
  check('collapsed navigation retains eight named targets',await p.locator('#nexus-navigation button[title][aria-label]').count()===8&&await p.locator('.nexus-nav-label:visible').count()===0);
  await p.reload();await p.waitForFunction(()=>!surfaceInspection().offline);
  check('only non-sensitive rail mode persisted',await p.evaluate(()=>localStorage.getItem('nexus-layout-sidebar-mode-v2')==='collapsed'&&document.body.dataset.sidebar==='collapsed'));
  await p.locator('#nexus-navigation [data-route="chat"]').click();
  await p.waitForFunction(id=>document.getElementById('chat-history').value===id&&document.getElementById('chat-question').value==='版面切換後仍保留的草稿',ready.chat);
  check('same conversation and draft after rail reload',await p.locator('#chat-history').inputValue()===ready.chat&&await p.locator('#chat-question').inputValue()==='版面切換後仍保留的草稿');
  for(const route of ['monitor','navigator']) {
   await p.locator('#nexus-navigation [data-route="'+route+'"]').click();
   check(route+' remains explicitly unconnected',/未連接/.test(await p.locator('.nexus-badge').innerText()));
  }
  for(const route of ['documents','links']) {
   await p.locator('#nexus-navigation [data-route="'+route+'"]').click();
   check(route+' opens real bounded resources',await p.locator('#nexus-'+route).isVisible()&&!await p.locator('#nexus-concept').isVisible());
  }
  await p.locator('#nexus-navigation [data-route="overview"]').click();
  // Synthetic projection faults never modify saved tasks or trusted results.
  let projected='CREATED',disconnected=false;
  await p.route('**/api/state',async route=>{
   if(disconnected){await route.abort();return;}
   const state=projected,r=await route.fetch(),d=await r.json();
   d.tasks=state==='empty'?[]:[{task_id:a,intent:'合成狀態驗證 '+state,state}];
   d.active=null;d.observation={task_id:null,events:[]};await route.fulfill({response:r,json:d});
  });
  for(const state of ['CREATED','RUNNING','UNKNOWN','FAILED','CANCEL_REQUESTED','CANCELLED','RESULT_PENDING_REVIEW','ACCEPTED','REJECTED','REVISION_REQUESTED']) {
    projected=state;
   await p.waitForFunction(state=>document.querySelector('#nexus-peek-title').textContent.endsWith(state),state);
   check('truthful summary '+state,!(await p.locator('#nexus-peek-state').innerText()).includes(state)&&!!(await p.locator('#nexus-peek-confirmed').innerText()));
  }
  projected='empty';
  await p.waitForFunction(()=>document.querySelector('#nexus-peek-open').disabled);
  check('visibility removal clears previous identity',await p.locator('#nexus-work-peek').getAttribute('data-task')===''&&await p.locator('#nexus-recent button').count()===0);
  disconnected=true;await p.waitForFunction(()=>surfaceInspection().offline);
  check('offline clears stale overview summary',await p.locator('#nexus-peek-open').isDisabled()&&/連線未確認/.test(await p.locator('#nexus-peek-title').innerText()));
  check('no browser errors',errors.length===0);
 } finally {
  if(browser){for(const context of browser.contexts())for(const page of context.pages())await page.unrouteAll({behavior:'wait'});await browser.close();}
  const exited=new Promise(r=>child.once('exit',r));child.stdin.end('{"action":"stop"}\n');await exited;
  fs.writeFileSync(path.join(out,'checks.json'),JSON.stringify({checks,errors,shots,comparisons,syntheticModel:true,realBoundedAudit:true},null,2));
 }
 console.log(JSON.stringify({passed:checks.length,errors,out}));
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
