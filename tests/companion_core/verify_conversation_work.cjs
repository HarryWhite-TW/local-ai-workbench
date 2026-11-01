/* Real Chrome and bounded audit, synthetic chat only. No credentials or model access. */
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process'),readline=require('readline');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const root=path.resolve(__dirname,'../..'),out=process.argv[2]?path.resolve(process.argv[2]):fs.mkdtempSync(path.join(require('os').tmpdir(),'companion-work-ui-'));
fs.mkdirSync(out,{recursive:true});
(async()=>{
 const child=spawn(process.env.PYTHON||'python',['-B',path.join(__dirname,'conversation_work_fixture.py'),out],{windowsHide:true,env:{...process.env,PYTHONUTF8:'1'}});
 let stderr='';child.stderr.on('data',x=>stderr+=x);const lines=readline.createInterface({input:child.stdout});
 const ready=await new Promise((resolve,reject)=>{lines.once('line',x=>resolve(JSON.parse(x)));child.once('exit',()=>reject(Error('Fixture failed '+stderr)));});
 let browser;const checks=[],errors=[];let sends=0;
 const check=(name,ok)=>{checks.push({name,passed:!!ok});assert.ok(ok,name);};
 try{
  browser=await chromium.launch({channel:'chrome',headless:true});const p=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
  p.setDefaultTimeout(12000);p.on('pageerror',e=>errors.push(e.message));p.on('request',r=>{if(r.url().endsWith('/api/chat/send'))sends++;});
  await p.goto(ready.url+'/#chat');await p.locator('#chat-history').selectOption(ready.chat);
  await p.locator('.chat-answer > .chat-source-link').click();
  check('proposal opens without starting execution',await p.evaluate(async()=>!(await(await fetch('/api/state')).json()).active));
  await p.locator('#work-goal').fill('查核 Companion 的實際程式定義與入口連接');
  await p.locator('#work-expected').fill('可核對的檔案雜湊、定義與入口行號；未執行的功能仍標示未知。');
  check('confirmation disabled before preview',await p.locator('#work-confirm').isDisabled());
  await p.locator('#work-preview').click();await p.waitForFunction(()=>!document.getElementById('work-confirm').disabled);
  await p.setViewportSize({width:360,height:740});await p.screenshot({path:out+'/proposal-360.png'});
  check('confirm reachable at 360',await p.locator('#work-confirm').evaluate(e=>{const r=e.getBoundingClientRect();return r.bottom<=innerHeight&&r.right<=innerWidth;}));
  check('preview still does not execute',await p.evaluate(async()=>!(await(await fetch('/api/state')).json()).active));
  await p.locator('#work-confirm').click();
  await p.waitForFunction(()=>document.querySelector('.chat-work-card')?.dataset.state==='RESULT_PENDING_REVIEW');
  const identity=await p.locator('.chat-work-card').evaluate(e=>({proposal:e.dataset.work,task:e.dataset.task,state:e.dataset.state}));
  await p.setViewportSize({width:1440,height:1000});await p.locator('.chat-work-card').screenshot({path:out+'/work-card.png'});
  await p.locator('.chat-work-card .secondary-button').click();
  await p.waitForFunction(()=>surfaceInspection().result?.state==='RESULT_PENDING_REVIEW');
  check('same task and status in work space',await p.evaluate(id=>surfaceInspection().selected===id.task&&surfaceInspection().task.state===id.state,identity));
  await p.locator('#open-reader').click();
  check('real host audit contains provenance',/可信本機唯讀查核紀錄/.test(await p.locator('#reader-text').textContent())&&/SHA-256/.test(await p.locator('#reader-text').textContent()));
  check('conclusion before collapsed original evidence',await p.locator('#reader-text .result-summary').isVisible()&&!(await p.locator('#reader-text .raw-evidence').getAttribute('open')));
  await p.screenshot({path:out+'/result-desktop.png'});
  for(const theme of ['obsidian','umber','porcelain']){
   await p.locator('#reader-preferences').click();await p.locator('button[data-theme="'+theme+'"]').click();await p.locator('#settings-dialog [data-close]').click();
   await p.setViewportSize({width:360,height:740});await p.screenshot({path:out+'/result-360-'+theme+'.png'});
   check(theme+' reader controls reachable',await p.locator('#reader-close').evaluate(e=>{const r=e.getBoundingClientRect();return r.x>=0&&r.y>=0&&r.right<=innerWidth&&r.bottom<=innerHeight;}));
   await p.setViewportSize({width:1440,height:1000});
  }
  await p.keyboard.press('Escape');await p.locator('#work-origin').click();
  check('returns to originating conversation',(await p.locator('#chat-history').inputValue())===ready.chat);
  await p.locator('#chat-question').fill('保留的追問草稿');await p.locator('#open-workspace').click();await p.locator('#open-chat').click();
  check('draft preserved',(await p.locator('#chat-question').inputValue())==='保留的追問草稿');
  await p.locator('.chat-work-card .text-button').click();check('result requires explicit preview',await p.locator('#chat-send').isDisabled());
  await p.locator('#chat-preview').click();await p.waitForFunction(()=>!document.getElementById('chat-knowledge-done').disabled);
  check('work result preview is exact audit',/可信本機唯讀查核紀錄/.test(await p.locator('#chat-source-preview').textContent()));
  await p.locator('#chat-knowledge-done').click();
  await p.locator('#chat-question').fill('根據剛才成果分析目前可確認與未知事項。');await p.locator('#chat-send').click();
  await p.waitForFunction(()=>document.querySelectorAll('.chat-message').length===2&&!document.getElementById('chat-send').disabled);
  check('only explicit send invoked synthetic model',sends===1);
  await p.reload();await p.locator('#chat-history').selectOption(ready.chat);
  await p.waitForFunction(()=>document.querySelector('.chat-work-card')?.dataset.task);
  check('reopened work link preserves identity',(await p.locator('.chat-work-card').getAttribute('data-task'))===identity.task);
  await p.locator('.chat-work-card .secondary-button').click();await p.waitForFunction(()=>!!surfaceInspection().result);
  await p.locator('#accept').click();await p.waitForFunction(()=>surfaceInspection().task?.state==='ACCEPTED');
  await p.locator('#work-origin').click();await p.waitForFunction(()=>document.querySelector('.chat-work-card')?.dataset.state==='ACCEPTED');
  check('human review not technical acceptance',/未由 ChatGPT 技術驗收/.test(await p.locator('.chat-work-card').textContent()));
  check('no JS errors',errors.length===0);
 }catch(e){checks.push({failure:e.message});throw e;}
 finally{if(browser)await browser.close();const ended=new Promise(r=>child.once('exit',r));child.stdin.end('{"action":"stop"}\n');await ended;fs.writeFileSync(out+'/browser-checks.json',JSON.stringify({checks,errors,syntheticConversation:true,realBoundedAudit:true,sends},null,2));}
 console.log(JSON.stringify({passed:checks.length,errors}));
})().catch(e=>{console.error(e.message);process.exitCode=1;});
