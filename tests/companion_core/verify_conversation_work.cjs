/* Real Chrome and bounded audit, synthetic chat only. No credentials or model access. */
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process'),readline=require('readline');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const root=path.resolve(__dirname,'../..'),out=process.argv[2]?path.resolve(process.argv[2]):fs.mkdtempSync(path.join(require('os').tmpdir(),'companion-work-ui-'));
fs.mkdirSync(out,{recursive:true});
(async()=>{
 const child=spawn(process.env.PYTHON||'python',['-B',path.join(__dirname,'conversation_work_fixture.py'),out],{windowsHide:true,env:{...process.env,PYTHONUTF8:'1'}});
 let stderr='';child.stderr.on('data',x=>stderr+=x);const lines=readline.createInterface({input:child.stdout});
 const ready=await new Promise((resolve,reject)=>{lines.once('line',x=>resolve(JSON.parse(x)));child.once('exit',()=>reject(Error('Fixture failed '+stderr)));});
 let browser,p;const checks=[],errors=[],sendBodies=[];let sends=0;
 const check=(name,ok)=>{checks.push({name,passed:!!ok});assert.ok(ok,name);};
 try{
  browser=await chromium.launch({channel:'chrome',headless:true});p=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
  p.setDefaultTimeout(12000);p.on('pageerror',e=>errors.push(e.message));p.on('request',r=>{if(r.url().endsWith('/api/chat/send')){sends++;sendBodies.push(r.postDataJSON());}});
  await p.goto(ready.url+'/#chat');await p.locator('#chat-history').selectOption(ready.chat);
  await p.locator('.chat-message-options summary').click();
  await p.getByRole('button',{name:'建立唯讀 Codex 診斷',exact:true}).click();
  check('proposal opens without starting execution',await p.evaluate(async()=>!(await(await fetch('/api/state')).json()).active));
  await p.locator('#work-goal').fill('查核 Companion 的實際程式定義與入口連接');
  await p.locator('#work-settings summary').click();
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
  const audit=await p.evaluate(async task=>(await(await fetch('/api/target',{method:'POST',headers:{'Content-Type':'application/json','X-Companion-UI':'1'},body:JSON.stringify({task_id:task})})).json()).result,identity.task);
  const attach=async()=>{
   const response=p.waitForResponse(r=>r.url().endsWith('/api/chat/preview'));
   await p.getByRole('button',{name:'加入成果，繼續討論',exact:true}).click();
   const r=await response;assert.equal(r.status(),200);const records=await r.json();
   await p.locator('#work-chat-context').waitFor({state:'visible'});
   return records;
  };
  const records=await attach(),key='work:'+identity.proposal;
  check('explicit attachment previews only the bound saved result',records.length===1&&records[0].key===key&&records[0].text===audit&&records[0].sha256===require('crypto').createHash('sha256').update(audit).digest('hex'));
  check('pending result explains the send boundary',await p.locator('#work-chat-context').innerText().then(t=>t.includes('按「傳送訊息」才分享給聊天模型'))&&sends===0);
  check('pending result preserves draft and is ready without a hidden extra step',await p.locator('#chat-question').inputValue()==='保留的追問草稿'&&!await p.locator('#chat-send').isDisabled());
  check('generic source dialog remains closed',!await p.locator('#chat-preview').isVisible());
  for(const [width,height] of [[1440,1000],[390,844]]){
   await p.setViewportSize({width,height});
   await p.getByRole('button',{name:'閱讀待分享的診斷',exact:true}).click();
   const reader=p.locator('#conversation-reader');await reader.waitFor({state:'visible'});
   check(width+' visible reader contains the exact saved audit',await reader.locator('.conversation-reading-content').textContent()===audit);
   check(width+' visible audit identifies task, proposal, workspace and source hashes',await reader.innerText().then(t=>t.includes(identity.task)&&t.includes(identity.proposal)&&t.includes(root)&&t.includes('SHA-256')));
   check(width+' inspection never sends to the model',sends===0);
   await p.screenshot({path:out+'/pending-source-'+width+'.png'});
   await p.getByRole('button',{name:'關閉情境閱讀區',exact:true}).click();
   check(width+' closing inspection keeps the explicitly selected source',await p.locator('#work-chat-context').isVisible());
  }
  await p.setViewportSize({width:1440,height:1000});
  await p.locator('#work-chat-clear').click();
  check('remove pending result cancels sharing without sending',await p.locator('#work-chat-context').isHidden()&&await p.locator('#chat-sources input:checked').count()===0&&await p.locator('#work-chat-preview').textContent()===''&&sends===0);
  const fresh=await attach();check('reattaching reads the same source identity',JSON.stringify(fresh)===JSON.stringify(records)&&sends===0);
  await p.locator('#chat-question').fill('根據剛才成果分析目前可確認與未知事項。');await p.locator('#chat-send').click();
  await p.waitForFunction(()=>document.querySelectorAll('.chat-message').length===2&&!document.getElementById('chat-send').disabled);
  check('only explicit send invoked synthetic model',sends===1);
  check('explicit send contains exactly the previewed source and hash',JSON.stringify(sendBodies[0].sources)===JSON.stringify([key])&&JSON.stringify(sendBodies[0].preview)===JSON.stringify({[key]:records[0].sha256}));
  const saved=await p.evaluate(async chat=>(await(await fetch('/api/chat/get',{method:'POST',headers:{'Content-Type':'application/json','X-Companion-UI':'1'},body:JSON.stringify({chat})})).json()),ready.chat);
  check('persisted model source equals the source the user could read',JSON.stringify(saved.turns.at(-1).sources)===JSON.stringify(records));
  check('send consumes the pending source',await p.locator('#work-chat-context').isHidden()&&await p.locator('#chat-sources input:checked').count()===0);
  await p.reload();await p.locator('#chat-history').selectOption(ready.chat);
  await p.waitForFunction(()=>document.querySelector('.chat-work-card')?.dataset.task);
  check('reopened work link preserves identity',(await p.locator('.chat-work-card').getAttribute('data-task'))===identity.task);
  await p.locator('.chat-work-card .secondary-button').click();await p.waitForFunction(()=>!!surfaceInspection().result);
  await p.locator('#accept').click();await p.waitForFunction(()=>surfaceInspection().task?.state==='ACCEPTED');
  await p.locator('#work-origin').click();await p.waitForFunction(()=>document.querySelector('.chat-work-card')?.dataset.state==='ACCEPTED');
  check('human review not technical acceptance',/未由 ChatGPT 技術驗收/.test(await p.locator('.chat-work-card').textContent()));
  await attach();await p.getByRole('button',{name:'閱讀待分享的診斷',exact:true}).click();
  const changed=new Promise(resolve=>lines.once('line',s=>resolve(JSON.parse(s))));
  child.stdin.write('{"action":"account","account":"synthetic-other-account"}\n');await changed;
  await p.waitForFunction(()=>companionProjectStatus().account==='synthetic-other-account');
  check('account switch revokes pending content and its visible reader',await p.locator('#work-chat-context').isHidden()&&await p.locator('#conversation-reader').isHidden()&&await p.locator('#chat-sources input:checked').count()===0&&sends===1);
  const denied=await p.evaluate(async body=>{const r=await fetch('/api/chat/preview',{method:'POST',headers:{'Content-Type':'application/json','X-Companion-UI':'1'},body:JSON.stringify(body)});return r.status;},{sources:[key],chat:ready.chat});
  check('other account cannot reload the original work source',denied===409);
  check('no JS errors',errors.length===0);
 }catch(e){checks.push({failure:e.message});if(p)await p.screenshot({path:out+'/failure.png',fullPage:true}).catch(()=>{});throw e;}
 finally{if(browser)await browser.close();const ended=new Promise(r=>child.once('exit',r));child.stdin.end('{"action":"stop"}\n');await ended;fs.writeFileSync(out+'/browser-checks.json',JSON.stringify({checks,errors,syntheticConversation:true,realBoundedAudit:true,sends},null,2));}
 console.log(JSON.stringify({passed:checks.length,errors}));
})().catch(e=>{console.error(e.message);process.exitCode=1;});
