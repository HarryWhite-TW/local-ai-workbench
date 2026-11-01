/* Actual Chrome, isolated SQLite/ReviewStore, synthetic inference, real bounded audit.
 * State/account fault projections below are explicit test fixtures, never product data. */
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process'),readline=require('readline');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const out=process.argv[2]||fs.mkdtempSync(path.join(require('os').tmpdir(),'nexus-ux-'));
fs.mkdirSync(out,{recursive:true});
(async()=>{
  const child=spawn(process.env.PYTHON||'python',['-B',path.join(__dirname,'conversation_work_fixture.py'),out],{windowsHide:true,env:{...process.env,PYTHONUTF8:'1'}});
  let stderr='';child.stderr.on('data',v=>stderr+=v);
  const ready=await new Promise((resolve,reject)=>{readline.createInterface({input:child.stdout}).once('line',s=>resolve(JSON.parse(s)));child.once('exit',()=>reject(Error(stderr)));});
  let browser;const checks=[],errors=[],posts=[];
  const check=(name,ok)=>{checks.push({name,passed:!!ok});assert.ok(ok,name);};
  try{
    browser=await chromium.launch({channel:'chrome',headless:true});
    const p=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});p.setDefaultTimeout(12000);
    p.on('pageerror',e=>errors.push(e.message));p.on('request',r=>{if(r.method()==='POST')posts.push({path:new URL(r.url()).pathname,body:r.postDataJSON()});});
    const shot=name=>p.screenshot({path:path.join(out,name+'.png'),fullPage:true});
    async function nav(route){if(await p.locator('#nexus-menu').isVisible()&&await p.locator('#nexus-menu').getAttribute('aria-expanded')==='false')await p.locator('#nexus-menu').click();await p.locator('#nexus-navigation [data-route="'+route+'"]').click();}
    async function result(id){await p.waitForFunction(id=>surfaceInspection().selected===id&&surfaceInspection().result?.task_id===id,id);}
    async function proposal(){
      await p.locator('.chat-answer > .chat-source-link').last().click();
      check('proposal requires preview',await p.locator('#work-confirm').isDisabled());
      await p.locator('#work-preview').click();await p.waitForFunction(()=>!document.getElementById('work-confirm').disabled);
      const confirmed=p.waitForResponse(r=>r.url().endsWith('/api/chat/work-confirm'));
      await p.locator('#work-confirm').click();const response=await confirmed;
      assert.ok(response.ok(),'confirmation response: '+await response.text());
      await p.waitForFunction(()=>document.querySelector('.chat-work-card')?.dataset.state==='RESULT_PENDING_REVIEW');
      return p.locator('.chat-work-card').getAttribute('data-task');
    }
    await p.goto(ready.url+'/#chat');await p.waitForFunction(()=>!document.getElementById('chat-send').disabled);
    await p.locator('#chat-question').fill('請協助查核 Companion 功能是否接通。');await p.locator('#chat-send').click();
    await p.waitForSelector('.chat-answer > .chat-source-link');
    const chatA=await p.locator('#chat-history').inputValue();
    check('new conversation saved and addressable',!!chatA&&chatA!==ready.chat&&p.url().includes('chat='+chatA));
    const taskA=await proposal();
    await p.locator('#chat-question').fill('這是工作 A 原對話的未送出草稿');
    await p.locator('.chat-work-card .secondary-button').click();await result(taskA);
    check('task address includes exact id',p.url().includes('task='+taskA));
    check('detail opens directly without duplicate list',await p.locator('#expanded-content').isVisible()&&!await p.locator('.task-tray').isVisible());
    check('next step before evidence',await p.locator('#nexus-next-step').isVisible()&&/先閱讀/.test(await p.locator('#nexus-next-step').textContent()));
    await p.waitForFunction(()=>document.getElementById('nexus-work-scope').textContent.includes('daily.py'));
    check('scope is authorized files not inferred functionality',/僅查核來源結構/.test(await p.locator('#nexus-work-scope').textContent()));
    check('explicit insufficient evidence and next step',/目前證據不足/.test(await p.locator('#result-text').textContent())&&/合理的下一步/.test(await p.locator('#result-text').textContent()));
    const audit=await p.evaluate(async id=>(await(await fetch('/api/target',{method:'POST',headers:{'Content-Type':'application/json','X-Companion-UI':'1'},body:JSON.stringify({task_id:id})})).json()),taskA);
    check('raw trusted evidence intact',await p.locator('#result-text .raw-evidence pre').textContent()===audit.result);
    await shot('work-detail-desktop');
    await p.locator('#open-reader').click();await p.locator('#reader-focus').click();await shot('result-focus-desktop');await p.locator('#reader-close').click();
    await p.reload();await result(taskA);
    check('reload preserves exact task and result',await p.evaluate(r=>surfaceInspection().result.result_id===r,audit.result_id));
    await p.locator('#work-origin').click();await p.locator('#chat-space').waitFor({state:'visible'});await p.waitForFunction(id=>document.getElementById('chat-history').value===id,chatA);
    check('return from reload keeps original draft',await p.locator('#chat-question').inputValue()==='這是工作 A 原對話的未送出草稿');
    await p.reload();await p.waitForFunction(id=>document.getElementById('chat-history').value===id,chatA);
    check('chat reload keeps selected conversation and draft',await p.locator('#chat-question').inputValue()==='這是工作 A 原對話的未送出草稿');
    await p.route('**/api/chat/get',async route=>{if(route.request().postDataJSON().chat===ready.chat)await new Promise(r=>setTimeout(r,400));await route.continue();});
    await p.locator('#chat-history').selectOption(ready.chat);
    check('switching conversation immediately removes former actions',await p.locator('.chat-work-card').count()===0);
    await p.waitForSelector('[data-turn="'+ready.turn+'"]');await p.unrouteAll({behavior:'wait'});const taskB=await proposal();
    await p.locator('#chat-question').fill('這是工作 B 的另一份草稿');
    await p.locator('.chat-work-card .secondary-button').click();await result(taskB);
    await nav('work');check('work entrance is complete finder',await p.locator('#task-items button').count()===2&&!await p.locator('#stage').isVisible());
    await p.locator('#task-items [data-task="'+taskA+'"]').click();await result(taskA);
    await p.locator('#nexus-work-list').click();await p.locator('#task-items [data-task="'+taskB+'"]').click();await result(taskB);
    await p.goBack();check('back to finder',!await p.locator('#stage').isVisible());await p.goBack();await result(taskA);
    check('back restores A not latest selected B',p.url().includes(taskA));
    await p.locator('#work-origin').click();await p.locator('#chat-space').waitFor({state:'visible'});await p.waitForFunction(id=>document.getElementById('chat-history').value===id,chatA);
    check('origin and draft remain A after B',await p.locator('#chat-question').inputValue()==='這是工作 A 原對話的未送出草稿');
    await p.goBack();await result(taskA);
    await p.goto(ready.url+'/#work?task=missing-task');await p.waitForFunction(()=>!surfaceInspection().offline&&surfaceInspection().selected==='missing-task');
    check('missing task does not reuse previous result',await p.evaluate(()=>!surfaceInspection().result));
    check('missing destination has honest recovery',/找不到此工作/.test(await p.locator('#nexus-next-step').textContent())&&await p.locator('#accept').isDisabled());
    await p.goto(ready.url+'/#work?task='+taskA);await result(taskA);
    // Delay origin resolution, then leave: an old response must not navigate the user back.
    await p.route('**/api/chat/work-origin',async route=>{await new Promise(r=>setTimeout(r,400));await route.continue();});
    await p.locator('#work-origin').click();await nav('overview');await p.waitForTimeout(550);
    check('late origin response cannot change new route',await p.locator('#nexus-overview').isVisible());await p.unrouteAll({behavior:'wait'});
    // A later task navigation wins even when A's result arrives last.
    await p.route('**/api/target',async route=>{if(route.request().postDataJSON().task_id===taskA)await new Promise(r=>setTimeout(r,400));await route.continue();});
    await p.evaluate(({a,b})=>{void nexusOpenWork(a);setTimeout(()=>void nexusOpenWork(b),40);},{a:taskA,b:taskB});await result(taskB);await p.waitForTimeout(550);
    check('late result cannot replace B',await p.evaluate(id=>surfaceInspection().selected===id&&surfaceInspection().result?.task_id===id,taskB));await p.unrouteAll({behavior:'wait'});
    await p.evaluate(id=>nexusOpenWork(id),taskA);await result(taskA);await nav('overview');
    await p.route('**/api/target',async route=>{if(route.request().postDataJSON().task_id===taskA)await new Promise(r=>setTimeout(r,400));await route.continue();});
    await p.goBack();await p.evaluate(id=>nexusOpenWork(id),taskB);await result(taskB);await p.waitForTimeout(550);
    check('new navigation supersedes pending browser back',p.url().includes('task='+taskB)&&await p.evaluate(id=>surfaceInspection().selected===id,taskB));await p.unrouteAll({behavior:'wait'});
    await p.locator('#accept').click();await p.waitForFunction(()=>surfaceInspection().task?.state==='ACCEPTED');
    await nav('execute');check('execution omits completed review',await p.locator('#nexus-execution-list [data-task="'+taskB+'"]').count()===0);
    check('pending review remains actionable',await p.locator('#nexus-execution-list [data-task="'+taskA+'"]').count()===1);
    await shot('execution-desktop');
    const statuses=['CREATED','RUNNING','UNKNOWN','FAILED','CANCEL_REQUESTED','CANCELLED','RESULT_PENDING_REVIEW'];
    await p.route('**/api/state',async route=>{
      const response=await route.fetch(),data=await response.json();data.tasks=statuses.map(state=>({task_id:'test-'+state,intent:'合成狀態 '+state,state}));data.active=data.tasks[1];data.busy=true;data.progress=[];data.observation={task_id:data.active.task_id,events:[]};await route.fulfill({response,json:data});
    });
    await p.waitForSelector('#nexus-execution-list .nexus-work-row[data-state="CREATED"]');
    const labels={CREATED:'正在準備',RUNNING:'執行中',UNKNOWN:'執行狀態未確認',FAILED:'執行失敗',CANCEL_REQUESTED:'停止待確認',RESULT_PENDING_REVIEW:'成果等待審查'};
    for(const [state,label] of Object.entries(labels))check('distinct execution state '+state,(await p.locator('#nexus-execution-list .nexus-work-row[data-state="'+state+'"]').textContent()).includes(label));
    check('cancelled is not pending execution',await p.locator('#nexus-execution-list .nexus-work-row[data-state="CANCELLED"]').count()===0);
    check('no invented percentage',!/%/.test(await p.locator('#nexus-execution-list').textContent()));
    await p.setViewportSize({width:360,height:740});await shot('execution-states-360');
    await nav('work');check('cancelled still visible in full records',/已確認取消/.test(await p.locator('#task-items [data-task="test-CANCELLED"]').textContent()));
    await p.locator('#task-items [data-task="test-UNKNOWN"]').click();check('unknown has no result or review',await p.locator('#result-tab').isDisabled()&&await p.locator('#accept').isDisabled());
    await p.unrouteAll({behavior:'wait'});await p.goto(ready.url+'/#work?task='+taskA);await result(taskA);
    check('detail 360 no horizontal overflow',await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await shot('work-detail-360');
    await p.locator('#open-reader').click();await shot('result-reader-360');check('reader controls fit',await p.locator('#reader-close').evaluate(e=>{const r=e.getBoundingClientRect();return r.right<=innerWidth&&r.bottom<=innerHeight;}));await p.locator('#reader-close').click();
    await p.locator('#work-origin').click();await p.locator('#chat-space').waitFor({state:'visible'});await p.waitForFunction(id=>document.getElementById('chat-history').value===id,chatA);
    // Synthetic long answer tests real safe DOM rendering and reading restoration.
    await p.route('**/api/chat/get',async route=>{
      const response=await route.fetch(),data=await response.json();data.turns[0].answer='# 查核限制\n\n<img src=x onerror="window.bad=true"> [bad](javascript:alert(1))\n\n'+('尚未確認的功能需要實際操作證據。\n\n'.repeat(90));await route.fulfill({response,json:data});
    });
    await p.reload();await p.waitForSelector('.markdown h2');await p.locator('#chat-messages').evaluate(e=>e.scrollTop=480);await p.waitForTimeout(100);
    await nav('overview');await nav('chat');check('chat reading position after navigation',await p.locator('#chat-messages').evaluate(e=>Math.abs(e.scrollTop-480)<5));
    await p.reload();await p.waitForSelector('.markdown h2');check('chat reading position after reload',await p.locator('#chat-messages').evaluate(e=>Math.abs(e.scrollTop-480)<5));
    check('markdown remains inert',await p.evaluate(()=>!window.bad&&!document.querySelector('.markdown img,.markdown a[href^="javascript:"]')));
    check('composer does not cover long answer',await p.evaluate(()=>document.getElementById('chat-messages').getBoundingClientRect().bottom<=document.getElementById('chat-form').getBoundingClientRect().top+1));await shot('chat-360');
    await p.locator('.chat-work-card .text-button').click();await p.locator('#chat-preview').click();await p.waitForFunction(()=>!document.getElementById('chat-knowledge-done').disabled);
    check('trusted result source preview remains exact',/可信本機唯讀查核紀錄/.test(await p.locator('#chat-source-preview').textContent()));
    await p.reload();await p.waitForSelector('.markdown h2');check('reload never restores source sharing authority',await p.locator('#chat-sources input:checked').count()===0);
    const second=await browser.newPage();await second.goto(ready.url+'/#chat');await second.waitForFunction(()=>!document.getElementById('chat-send').disabled);
    check('another tab does not inherit draft',await second.locator('#chat-question').inputValue()==='');await second.close();
    const before=posts.length;
    await p.route('**/api/chat/state',async route=>{const response=await route.fetch(),data=await response.json();data.auth.active='synthetic-other-account';await route.fulfill({response,json:data});});
    await p.waitForFunction(()=>document.getElementById('chat-history').value===''&&document.getElementById('chat-question').value==='');await p.waitForTimeout(1600);
    check('account switch clears draft and selection',await p.locator('#chat-question').inputValue()===''&&await p.locator('.chat-message').count()===0);
    check('navigation does not read former account chat',!posts.slice(before).some(r=>r.path==='/api/chat/get'&&r.body.chat===chatA));
    check('old account session draft removed',await p.evaluate(()=>!Object.keys(sessionStorage).some(k=>k.includes('synthetic-test-account'))));
    check('only one explicit synthetic inference',posts.filter(r=>r.path==='/api/chat/send').length===1);
    check('no JS errors',errors.length===0);
  }finally{
    if(browser)await browser.close();const exited=new Promise(r=>child.once('exit',r));child.stdin.end('{"action":"stop"}\n');await exited;
    fs.writeFileSync(path.join(out,'checks.json'),JSON.stringify({checks,errors,syntheticInference:true,realBoundedAudit:true,posts:posts.map(r=>r.path)},null,2));
  }
  console.log(JSON.stringify({passed:checks.length,errors,out}));
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
