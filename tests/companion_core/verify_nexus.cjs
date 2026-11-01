/* Real Chrome + isolated SQLite/ReviewStore + real bounded audit.
 * Markdown/status fault cases are explicitly synthetic; no credentials/model access. */
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process'),readline=require('readline');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const out=process.argv[2]?path.resolve(process.argv[2]):fs.mkdtempSync(path.join(require('os').tmpdir(),'nexus-ui-'));
fs.mkdirSync(out,{recursive:true});
(async()=>{
  const child=spawn(process.env.PYTHON||'python',['-B',path.join(__dirname,'conversation_work_fixture.py'),out],{windowsHide:true,env:{...process.env,PYTHONUTF8:'1'}});
  let stderr='';child.stderr.on('data',v=>stderr+=v);
  const ready=await new Promise((resolve,reject)=>{readline.createInterface({input:child.stdout}).once('line',s=>resolve(JSON.parse(s)));child.once('exit',()=>reject(Error(stderr)));});
  let browser;const checks=[],errors=[],posts=[],shots=[];
  const check=(name,ok)=>{checks.push({name,passed:!!ok});assert.ok(ok,name);};
  try {
    browser=await chromium.launch({channel:'chrome',headless:true});
    const p=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});p.setDefaultTimeout(12000);
    p.on('pageerror',e=>errors.push(e.message));p.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname);});
    const shot=async name=>{await p.screenshot({path:path.join(out,name+'.png'),fullPage:true});shots.push(name+'.png');};
    async function nav(route){if(await p.locator('#nexus-menu').isVisible()&&await p.locator('#nexus-menu').getAttribute('aria-expanded')==='false')await p.locator('#nexus-menu').click();await p.locator('#nexus-navigation [data-route="'+route+'"]').click();}
    const noOverflow=()=>p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1);
    await p.goto(ready.url);await p.waitForFunction(()=>!surfaceInspection().offline);
    check('default overview and semantic location',await p.locator('#nexus-overview').isVisible()&&await p.locator('#nexus-location').textContent()==='總覽');
    check('actual workspace pin',/local-ai-workbench-lc-workux01/.test(await p.locator('#nexus-project').textContent()));
    check('all eight navigation destinations',await p.locator('#nexus-navigation button').count()===8);
    // The approved encrypted UI continuity is separate from work/model/source authority.
    check('overview only persists approved local UI continuity',posts.every(p=>['/api/chat/continuity-get','/api/chat/continuity-save'].includes(p))&&await p.evaluate(async()=>!(await(await fetch('/api/state')).json()).active));await shot('overview-desktop');
    for(const route of ['monitor','navigator']) {
      await nav(route);check(route+' explicitly not connected',await p.locator('#nexus-concept').isVisible()&&/未連接/.test(await p.locator('.nexus-badge').textContent()));
      check(route+' no fabricated metrics',!(await p.locator('#nexus-concept').textContent()).match(/\d+%|\d+\s*ms/));
    }
    for(const route of ['documents','links']) {
      await nav(route);check(route+' has an actual bounded resource page',await p.locator('#nexus-'+route).isVisible()&&!await p.locator('#nexus-concept').isVisible());
    }
    await shot('galaxy-concept-desktop');
    await nav('chat');await p.locator('#chat-history').selectOption(ready.chat);
    await p.locator('#chat-question').fill('這是保留在目前對話的草稿。');await nav('overview');await nav('chat');
    check('draft across overview',(await p.locator('#chat-question').inputValue()).includes('保留'));
    await p.goBack();check('browser back restores overview',await p.locator('#nexus-overview').isVisible());await p.goForward();
    await p.locator('.chat-answer > .chat-source-link').click();await p.locator('#work-preview').click();await p.waitForFunction(()=>!document.getElementById('work-confirm').disabled);
    await p.locator('#work-confirm').click();await p.waitForFunction(()=>document.querySelector('.chat-work-card')?.dataset.state==='RESULT_PENDING_REVIEW');
    const task=await p.locator('.chat-work-card').getAttribute('data-task');
    await nav('execute');await p.waitForSelector('#nexus-execution-list [data-task="'+task+'"]');check('real task on execution page',await p.locator('#nexus-execution-list [data-task="'+task+'"]').count()===1);await shot('execution-desktop');
    await p.locator('#nexus-execution-list [data-task="'+task+'"]').click();await p.waitForFunction(()=>!!surfaceInspection().result);
    check('work identity retained',await p.evaluate(id=>surfaceInspection().selected===id,task));
    check('user-facing conclusion visible',await p.locator('#result-text .result-summary').isVisible());
    const target=await p.evaluate(async id=>(await(await fetch('/api/target',{method:'POST',headers:{'Content-Type':'application/json','X-Companion-UI':'1'},body:JSON.stringify({task_id:id})})).json()),task);
    check('correct original provider',target.provider==='bounded-python-source-audit-v1');
    check('original evidence byte-for-byte',await p.locator('#result-text .raw-evidence pre').textContent()===target.result);
    check('evidence starts collapsed',!(await p.locator('#result-text .raw-evidence').evaluate(e=>e.open)));
    await shot('work-desktop');await p.locator('#open-reader').click();await p.locator('#reader-focus').click();await shot('reader-focus-desktop');
    await p.locator('#reader-text .raw-evidence summary').click();check('evidence can expand',await p.locator('#reader-text .raw-evidence pre').isVisible());
    await p.locator('#reader-close').click();await p.locator('#work-origin').click();await p.waitForSelector('#chat-space',{state:'visible'});check('origin link from execution list',(await p.locator('#chat-history').inputValue())===ready.chat);
    const md='# 安全閱讀測試\n\n這是 **重點**，也是 *補充* 與 `inline code`。\n\n- 第一項\n- 第二項\n\n> 引用內容\n\n| 狀態 | 含義 |\n| --- | --- |\n| UNKNOWN | 未確認 |\n\n```python\nprint("<script>not executable</script>")\n```\n\n[安全連結](https://example.com) [禁止連結](javascript:alert(1))\n\n<img src=x onerror="window.nexusXss=true">\n\n'+('長篇段落，保留閱讀位置與足夠的內容空間。\n\n'.repeat(75));
    await p.route('**/api/chat/get',async route=>{
      const response=await route.fetch(),data=await response.json();data.turns[0].answer=md;await route.fulfill({response,json:data});
    });
    await p.reload();await p.locator('#chat-history').selectOption(ready.chat);await p.waitForSelector('.markdown table');
    check('safe headings list table code',await p.locator('.markdown h2').count()>0&&await p.locator('.markdown ul').count()>0&&await p.locator('.markdown pre code').count()>0);
    check('HTML inert and unsafe href absent',await p.evaluate(()=>!window.nexusXss&&!document.querySelector('.markdown img,.markdown script,.markdown a[href^="javascript:"]')));
    await p.locator('#chat-messages').evaluate(e=>e.scrollTop=0);await shot('markdown-desktop');
    const before=await p.locator('#chat-space').evaluate(e=>e.getBoundingClientRect().width);await p.locator('#nexus-focus').click();
    check('focus hides navigation and preserves chat',!(await p.locator('#nexus-sidebar').isVisible())&&await p.locator('#chat-space').evaluate(e=>e.getBoundingClientRect().width)>=before);
    await p.locator('#nexus-focus').click();
    await p.setViewportSize({width:360,height:740});await shot('markdown-360');
    check('chat no horizontal overflow at 360',await noOverflow());
    check('composer never overlaps messages',await p.evaluate(()=>document.getElementById('chat-messages').getBoundingClientRect().bottom<=document.getElementById('chat-form').getBoundingClientRect().top+1));
    check('send reachable at 360',await p.locator('#chat-send').evaluate(e=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.bottom<=innerHeight;}));
    await p.locator('#chat-question').fill('窄視窗保留草稿');
    await nav('overview');check('overview no overflow at 360',await noOverflow());await shot('overview-360');
    await p.locator('#nexus-menu').click();await shot('navigation-360');await p.keyboard.press('Escape');check('escape closes mobile navigation',(await p.locator('#nexus-menu').getAttribute('aria-expanded'))==='false');
    await nav('work');await p.locator('#task-items [data-task="'+task+'"]').click();await p.waitForFunction(()=>!!surfaceInspection().result);check('work no overflow at 360',await noOverflow());await shot('work-360');
    await p.locator('#open-reader').click();await shot('reader-360');check('narrow reader close reachable',await p.locator('#reader-close').evaluate(e=>{const r=e.getBoundingClientRect();return r.right<=innerWidth&&r.bottom<=innerHeight;}));await p.locator('#reader-close').click();
    for(const route of ['execute','monitor','documents','links','navigator']){await nav(route);check(route+' no overflow at 360',await noOverflow());}
    await shot('galaxy-concept-360');await nav('chat');check('mobile draft preserved',(await p.locator('#chat-question').inputValue())==='窄視窗保留草稿');
    // Status fault projection; the synthetic cases never create backend work/results.
    await p.route('**/api/state',async route=>{
      const response=await route.fetch(),data=await response.json();data.tasks=['UNKNOWN','FAILED','RESULT_PENDING_REVIEW'].map((state,i)=>({task_id:'fault-'+i,intent:'合成狀態對照 '+state,state}));data.active=null;data.observation={task_id:null,events:[]};await route.fulfill({response,json:data});
    });
    await nav('execute');await p.waitForSelector('#nexus-execution-list .nexus-work-row[data-state="UNKNOWN"]');
    for(const state of ['UNKNOWN','FAILED','RESULT_PENDING_REVIEW'])check('distinct '+state,(await p.locator('#nexus-execution-list .nexus-work-row[data-state="'+state+'"]').textContent()).includes(namesForTest(state)));
    await shot('synthetic-statuses-360');
    await p.unroute('**/api/state');await p.route('**/api/state',route=>route.abort());
    await p.waitForFunction(()=>surfaceInspection().offline);check('disconnect does not show stale successes',/未確認/.test(await p.locator('#nexus-execution-list').textContent())&&await p.locator('#nexus-execution-list button').count()===0);
    check('no model requests in navigation test',!posts.includes('/api/chat/send'));check('no browser errors',errors.length===0);
  } finally {
    if(browser)await browser.close();const exited=new Promise(r=>child.once('exit',r));child.stdin.end('{"action":"stop"}\n');await exited;
    fs.writeFileSync(path.join(out,'checks.json'),JSON.stringify({checks,errors,shots,posts,realBoundedAudit:true,syntheticChat:true,syntheticStatusFaults:true},null,2));
  }
  console.log(JSON.stringify({passed:checks.length,errors,out}));
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
function namesForTest(state){return {UNKNOWN:'執行狀態未確認',FAILED:'執行失敗',RESULT_PENDING_REVIEW:'成果等待審查'}[state];}
