/* One daily journey through the real UI, HTTP, SQLite, DPAPI and ReviewStore.
 * Identity and inference are synthetic; no live service or private data is used. */
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),readline=require('readline'),{spawn}=require('child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const out=path.resolve(process.argv[2]||fs.mkdtempSync(path.join(require('os').tmpdir(),'nexus-daily-flow-'))),root=path.join(out,'public-project');
fs.mkdirSync(path.join(root,'src/companion_core'),{recursive:true});
const document='# Public daily workflow\r\nPUBLIC_DAILY_CODE: ORCHID-73\r\nOnly this public excerpt is selected.\r\n';
fs.writeFileSync(path.join(root,'README.md'),document);fs.writeFileSync(path.join(root,'AGENTS.md'),'Public fixture, read-only project sources.');
for(const name of ['daily','chat','surface','core','runtime','review','work'])fs.writeFileSync(path.join(root,'src/companion_core',name+'.py'),'class PublicCapability:\n    pass\n');
const checks=[],errors=[],sessions=[],posts=[],shots=[];let browser,page,live;
const check=(name,value)=>{checks.push({name,passed:!!value});assert.ok(value,name);};
async function start(){
 const child=spawn(process.env.PYTHON||'python',['-B',path.join(__dirname,'conversation_work_fixture.py'),out,root],{windowsHide:true,env:{...process.env,PYTHONUTF8:'1'}}),lines=readline.createInterface({input:child.stdout});let stderr='';child.stderr.on('data',s=>stderr+=s);
 const ready=await new Promise((resolve,reject)=>{lines.once('line',s=>resolve(JSON.parse(s)));child.once('error',reject);child.once('exit',()=>reject(Error(stderr)));});
 const fixture={...ready,child};sessions.push(fixture);return fixture;
}
async function stop(fixture){if(fixture.child.exitCode!==null)return;const ended=new Promise(resolve=>fixture.child.once('exit',resolve));fixture.child.stdin.end('{"action":"stop"}\n');await ended;}
async function open(url){
 const p=await browser.newPage({viewport:{width:1440,height:1000},locale:'zh-TW',reducedMotion:'reduce'});p.setDefaultTimeout(12000);p.on('pageerror',e=>errors.push(e.message));p.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname);});
 await p.goto(url);await p.waitForFunction(()=>!surfaceInspection().offline&&!!companionProjectStatus().account);page=p;return p;
}
async function project(){await page.locator('.nexus-pinned [data-route="project"]').click();await page.waitForFunction(()=>!!document.getElementById('nexus-project-page').dataset.project);}
async function nav(route){if(await page.locator('#nexus-menu').isVisible()&&await page.locator('#nexus-menu').getAttribute('aria-expanded')==='false')await page.locator('#nexus-menu').click();await page.locator('#nexus-navigation [data-route="'+route+'"]').click();}
const saved=()=>page.waitForFunction(()=>document.getElementById('chat-save-status').dataset.state==='saved'&&/已.*保存/.test(document.getElementById('chat-save-status').textContent));
async function api(action,body){return page.evaluate(async({action,body})=>{const r=await fetch('/api/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Companion-UI':'1'},body:JSON.stringify(body)});if(!r.ok)throw Error('Fixture API '+r.status);return r.json();},{action,body});}
async function shot(name){await page.screenshot({path:path.join(out,name+'.png')});shots.push(name+'.png');}
(async()=>{try{
 live=await start();browser=await chromium.launch({channel:'chrome',headless:true,args:['--disable-gpu']});await open(live.url);await project();
 check('start in the actual launch project',await page.locator('#project-workspace').textContent()===root);
 await page.locator('#nexus-project-page [data-route="documents"]').click();await page.locator('#documents-list button').filter({hasText:'README.md'}).click();await page.locator('#document-preview').click();await page.locator('#document-discuss:not([disabled])').click();
 await page.locator('input[name="document-scope"][value="excerpt"]').check();await page.locator('#document-excerpt-start').fill('2');await page.locator('#document-excerpt-end').fill('3');
 await page.locator('#document-source-confirm').click();await page.locator('#document-chat-context').waitFor({state:'visible'});
 check('document begins an explicit new conversation context',await page.locator('#chat-history').inputValue()===''&&await page.locator('#document-chat-content').textContent()===document.split('\r\n').slice(1,3).join('\n'));
 await page.locator('#chat-question').fill('請根據本次公開節錄說明可確認的內容。');const sent=page.waitForResponse(r=>r.url().endsWith('/api/chat/send'));await page.locator('#chat-send').click();const response=await sent;assert.equal(response.status(),200);const identity=await response.json();
 await page.waitForFunction(id=>document.querySelector('[data-turn="'+id+'"] .chat-answer strong')?.textContent==='Companion',identity.turn);await page.locator('#companion-expand').click();
 check('submitted source is consumed and original conversation is selected',await page.locator('#chat-history').inputValue()===identity.chat&&await page.locator('#document-chat-context').isHidden()&&await page.locator('#chat-sources input:checked').count()===0);
 await page.locator('#project-chat-link:not([disabled])').click();await page.locator('#project-confirm').waitFor({state:'visible'});
 check('project binding remains a separate explicit confirmation',(await page.locator('#project-confirm-copy').textContent()).includes(root));await page.locator('#project-confirm-save').click();await page.locator('#project-confirm').waitFor({state:'hidden'});
 await project();await page.locator('#project-chats [data-chat="'+identity.chat+'"]').waitFor();
 check('project exposes the saved conversation without adding sources',await page.locator('#project-chats button').count()===1&&await page.evaluate(()=>companionProjectStatus().sources===0));await shot('project-related-chat');
 await page.locator('#project-chats [data-chat="'+identity.chat+'"]').click();await page.waitForFunction(id=>document.getElementById('chat-history').value===id&&document.body.dataset.route==='chat',identity.chat);
 await page.locator('[data-turn="'+identity.turn+'"]').getByRole('button',{name:'將這輪討論整理成工作提案'}).click();
 await page.locator('#work-goal').fill('核對目前專案提供的受限程式範圍');await page.locator('#work-expected').fill('取得可回讀的程式結構紀錄；不推定模型或產品功能已驗收。');await page.locator('#work-preview').click();await page.locator('#work-confirm:not([disabled])').click();
 await page.waitForFunction(()=>document.querySelector('.chat-work-card')?.dataset.state==='RESULT_PENDING_REVIEW');const task=await page.locator('.chat-work-card').getAttribute('data-task');await page.locator('.chat-work-card .secondary-button').click();await page.waitForFunction(id=>surfaceInspection().result?.task_id===id,task);
 const result=await api('target',{task_id:task});check('bounded work produces a durable pending-review result',result.state==='RESULT_PENDING_REVIEW'&&result.provider==='bounded-python-source-audit-v1');
 await page.locator('#open-reader').click();check('result can be read with original evidence',(await page.locator('#reader-text').textContent()).includes('可信本機唯讀查核紀錄'));await page.locator('#reader-close').click();
 await page.locator('#accept').click();await page.waitForFunction(()=>surfaceInspection().task?.state==='ACCEPTED');
 check('human result decision preserves the exact receipt',(await api('target',{task_id:task})).result_id===result.result_id);await shot('reviewed-work');
 await page.locator('#work-origin').click();await page.waitForFunction(id=>document.getElementById('chat-history').value===id&&document.body.dataset.route==='chat',identity.chat);
 await page.waitForFunction(()=>document.querySelector('.chat-work-card')?.dataset.state==='ACCEPTED');
 check('work returns to its original conversation and review state',await page.locator('.chat-work-card').getAttribute('data-state')==='ACCEPTED'&&(await page.locator('.chat-work-card').textContent()).includes('未由 ChatGPT 技術驗收'));
  await project();await page.locator('#project-tasks [data-task="'+task+'"]').click();await page.waitForFunction(id=>surfaceInspection().result?.task_id===id,task);await page.locator('#companion-ask').click();
  await page.waitForFunction(id=>document.getElementById('companion-context').dataset.task===id,task);await page.locator('#companion-expand').click();await page.locator('#chat-question').fill('PUBLIC_DAILY_FOLLOWUP_DRAFT');await saved();await page.reload();
  await page.waitForFunction(id=>document.getElementById('companion-context').dataset.task===id,task);
  await project();await page.locator('#project-chats [data-chat="'+identity.chat+'"]').click();await page.locator('#companion-share-result:not([disabled])').waitFor({state:'visible'});
  check('same-tab reload and project return preserve the exact work context',await page.locator('#companion-context').getAttribute('data-task')===task&&await page.locator('#chat-question').inputValue()==='PUBLIC_DAILY_FOLLOWUP_DRAFT');
  await page.locator('#companion-share-result').click();await page.locator('#chat-preview').click();await page.locator('#chat-knowledge-done:not([disabled])').click();
  check('restored work context still requires explicit result selection and preview',await page.locator('#chat-sources input:checked').count()===1&&(await page.locator('#chat-source-preview').textContent()).includes('可信本機唯讀查核紀錄'));
  await project();check('project navigation clears the selected result source',await page.locator('#chat-sources input:checked').count()===0);await page.locator('#project-chats [data-chat="'+identity.chat+'"]').click();
 await page.locator('#chat-question').fill('PUBLIC_DAILY_FOLLOWUP_DRAFT');await project();await page.locator('#project-tasks [data-task="'+task+'"]').click();await page.waitForFunction(id=>surfaceInspection().result?.task_id===id,task);await page.locator('#work-origin').click();
 check('draft survives the project-work-origin round trip',await page.locator('#chat-question').inputValue()==='PUBLIC_DAILY_FOLLOWUP_DRAFT');
 await page.locator('[data-turn="'+identity.turn+'"] .chat-source-link').first().click();await page.getByRole('button',{name:'返回來源文件 · 重新核對目前版本'}).click();await page.locator('#document-source-location').waitFor();
 check('result discussion returns to the exact original document excerpt',await page.locator('#document-source-location').textContent()===document.split('\r\n').slice(1,3).join('\r\n')&&await page.locator('#document-content').textContent()===document);await shot('returned-original-source');
 await nav('chat');check('returning source preserves draft and project relation',await page.locator('#chat-question').inputValue()==='PUBLIC_DAILY_FOLLOWUP_DRAFT'&&await page.evaluate(()=>!!companionProjectStatus().association&&companionProjectStatus().sources===0&&!companionProjectStatus().preview));await saved();
 const oldURL=live.url;await browser.close();browser=null;await stop(live);live=await start();browser=await chromium.launch({channel:'chrome',headless:true,args:['--disable-gpu']});await open(live.url);
 await page.locator('#nexus-overview .nexus-home-actions [data-route="chat"]').filter({hasText:'繼續草稿'}).click();await page.waitForFunction(id=>document.getElementById('chat-history').value===id,identity.chat);await saved();
 check('fresh browser and process resume the same conversation and draft',await page.locator('#chat-question').inputValue()==='PUBLIC_DAILY_FOLLOWUP_DRAFT');
 check('restart restores no sharing authority',await page.locator('#chat-sources input:checked').count()===0&&await page.locator('#document-chat-context').isHidden()&&!await page.evaluate(()=>companionProjectStatus().preview));await shot('next-day-conversation');
 await project();await page.locator('#project-chats [data-chat="'+identity.chat+'"]').waitFor();await page.locator('#project-tasks [data-task="'+task+'"]').click();await page.waitForFunction(id=>surfaceInspection().result?.task_id===id,task);
 const reloaded=await api('target',{task_id:task});check('project still finds the exact reviewed result after restart',reloaded.result_id===result.result_id&&reloaded.result===result.result&&reloaded.state==='ACCEPTED');
 check('project workspace and source files remain untouched',fs.readFileSync(path.join(root,'README.md'),'utf8')===document);
 check('only the explicit question called synthetic inference',posts.filter(p=>p==='/api/chat/send').length===1);check('no browser errors',errors.length===0);
 fs.writeFileSync(path.join(out,'identity.json'),JSON.stringify({chat:identity.chat,turn:identity.turn,task,resultId:result.result_id,oldURL,newURL:live.url},null,2));console.log(JSON.stringify({passed:checks.length,errors,out}));
}catch(e){errors.push(e.stack);if(page&&!page.isClosed())await page.screenshot({path:path.join(out,'failure.png')}).catch(()=>{});throw e;
}finally{if(browser)await browser.close();for(const fixture of sessions)await stop(fixture);fs.writeFileSync(path.join(out,'checks.json'),JSON.stringify({checks,errors,posts,shots,syntheticIdentityAndInference:true,realHTTPDPAPISQLiteAndReviewStore:true,realBrowserAndProcessRestart:true},null,2));}})().catch(e=>{console.error(e.stack);process.exitCode=1;});
