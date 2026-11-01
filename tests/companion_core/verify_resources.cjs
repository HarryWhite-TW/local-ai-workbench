/* UX-05 actual HTTP/SQLite/filesystem/UI. Synthetic account, no model/network integration.
 * node verify_resources.cjs <output> [approved-prototype.html]
 * The optional prototype is compared by layout/semantics, never pixels or demo data.
 */
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),readline=require('readline'),{spawn}=require('child_process'),{pathToFileURL}=require('url');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const out=path.resolve(process.argv[2]||fs.mkdtempSync(path.join(require('os').tmpdir(),'nexus-resources-'))),prototype=process.argv[3];fs.mkdirSync(out,{recursive:true});
const started=performance.now(),checks=[],shots=[],comparisons=[],errors=[],requests=[],children=[];let browser,p;
const check=(name,passed,detail)=>{checks.push({name,passed:!!passed,detail});assert.ok(passed,name+(detail?' '+JSON.stringify(detail):''));};
async function fixture(dir,root){fs.mkdirSync(dir,{recursive:true});const child=spawn(process.env.PYTHON||'python',['-B',path.join(__dirname,'conversation_work_fixture.py'),dir,root],{windowsHide:true,env:{...process.env,PYTHONUTF8:'1'}});children.push(child);let stderr='';child.stderr.on('data',s=>stderr+=s);const lines=readline.createInterface({input:child.stdout});const ready=await new Promise((resolve,reject)=>{lines.once('line',s=>resolve(JSON.parse(s)));child.once('exit',()=>reject(Error(stderr)));});return {...ready,child,lines};}
(async()=>{
 const root=path.join(out,'NEXUS-UX05-Project');fs.mkdirSync(path.join(root,'docs'),{recursive:true});fs.mkdirSync(path.join(root,'src','companion_core'),{recursive:true});
 const content='# UX-05 browser fixture\n\nThis is a real scoped UTF-8 file, not a model answer.\n<script>window.resourceXSS=true</script>\n';
 fs.writeFileSync(path.join(root,'README.md'),content);fs.writeFileSync(path.join(root,'AGENTS.md'),'Synthetic local boundaries.');fs.writeFileSync(path.join(root,'docs','guide.txt'),'A real scoped text guide.');fs.writeFileSync(path.join(root,'src','companion_core','daily.py'),'def status():\n    return "synthetic"\n');
 const ready=await fixture(path.join(out,'isolated'),root);
 try{
  browser=await chromium.launch({channel:'chrome',headless:true,args:['--disable-gpu']});const context=await browser.newContext({viewport:{width:1440,height:1000},deviceScaleFactor:1,reducedMotion:'reduce',locale:'zh-TW'});p=await context.newPage();p.setDefaultTimeout(12000);p.on('pageerror',e=>errors.push(e.message));
  await context.route('https://example.com/**',r=>r.fulfill({contentType:'text/plain',body:'Navigation intercepted by browser test; no external network.'}));
  p.on('request',r=>{if(r.method()==='POST')requests.push({path:new URL(r.url()).pathname,body:r.postDataJSON()});});
  const raw=(action,body)=>p.evaluate(async({action,body})=>{const r=await fetch('/api/chat/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Companion-UI':'1'},body:JSON.stringify(body)});return {status:r.status,data:await r.json()};},{action,body});
  const api=async(action,body)=>{const r=await raw(action,body);assert.equal(r.status,200,JSON.stringify(r.data));return r.data;};
  const nav=async route=>{await p.locator('#nexus-navigation [data-route="'+route+'"]').click();await p.waitForFunction(route=>document.body.dataset.route===route,route);};
  const docs=async()=>{await nav('documents');await p.locator('#documents-list [data-document]').first().waitFor();};
  const links=async()=>{await nav('links');await p.locator('#links-list [data-link="project"]').waitFor();};
  const sourceFree=async()=>await p.locator('#chat-sources input:checked').count()===0;
  const shot=async(page,name)=>{await page.evaluate(async()=>{await document.fonts.ready;scrollTo(0,0);});await page.screenshot({path:path.join(out,name+'.png'),fullPage:true,animations:'disabled',caret:'hide'});shots.push(name+'.png');};
  const chooseReadme=()=>p.locator('#documents-list .resource-row').filter({hasText:'README.md'}).click();
  await p.goto(ready.url);await p.waitForFunction(()=>!surfaceInspection().offline);await p.locator('.nexus-pinned [data-route="project"]').click();await p.waitForFunction(()=>!!document.getElementById('nexus-project-page').dataset.project);
  await p.locator('.project-stack [data-route="documents"]').click();await p.locator('#documents-list [data-document]').first().waitFor();
  check('project enters actual scoped document index',await p.locator('#documents-list [data-document]').count()===3 && (await p.locator('[data-resource-project]').first().innerText())===path.basename(root));
  await chooseReadme();check('selection does not read preview or grant sources',await p.locator('#document-content').isHidden()&&await sourceFree()&&!requests.some(r=>r.path==='/api/chat/resource-preview'));
  const original=fs.readFileSync(path.join(root,'README.md'));await p.locator('#document-preview').click();await p.locator('#document-content').waitFor({state:'visible'});
  check('real readonly text, safe HTML rendering',await p.locator('#document-content').textContent()===content && !(await p.evaluate(()=>window.resourceXSS)) && fs.readFileSync(path.join(root,'README.md')).equals(original));
  check('preview remains separate from explicit Companion authorization',/未提供給模型/.test(await p.locator('#document-source').innerText())&&await p.locator('#document-discuss').isEnabled()&&await sourceFree());
  await p.locator('#documents-search').fill('not-present');check('honest filtered empty state',await p.locator('#documents-list [data-document]').count()===0);await p.locator('#documents-search').fill('');
  await p.locator('[data-document-filter="boundary"]').click();check('real boundary category',await p.locator('#documents-list [data-document]').count()===1);await p.locator('[data-document-filter="all"]').click();await chooseReadme();
  await p.locator('#documents-list button').first().focus();await p.keyboard.press('End');check('document keyboard list navigation',await p.locator('#documents-list button').last().evaluate(e=>e===document.activeElement));
  fs.writeFileSync(path.join(root,'README.md'),'changed after index');await p.locator('#document-preview').click();await p.waitForFunction(()=>document.getElementById('document-notice').textContent.includes('變動'));
  check('changed document hides previous text',await p.locator('#document-content').isHidden()&&await p.locator('#document-content').innerText()==='');fs.writeFileSync(path.join(root,'README.md'),content);await p.locator('#documents-refresh').click();await p.locator('#documents-list [data-document]').first().waitFor();
  await links();check('no invented reference data',await p.locator('#links-list [data-link]').count()===2);
  await p.locator('[data-link="unconnected"]').click();check('external integration is truly unavailable',await p.locator('#link-open').isDisabled()&&/未接通/.test(await p.locator('#link-open').innerText()));
  await p.locator('#link-add').click();await p.locator('#reference-name').fill('<img src=x onerror=alert(1)>');await p.locator('#reference-url').fill('https://example.com/resources');await p.locator('#reference-form button').click();await p.locator('#resource-confirm').waitFor({state:'visible'});
  check('save preview is not persistent and input is text',(await api('resource-links',{workspace:root})).links.length===0&&await p.locator('#resource-confirm-name img').count()===0);
  await p.keyboard.press('Escape');check('cancel saves nothing',(await api('resource-links',{workspace:root})).links.length===0);
  await p.locator('#reference-form button').click();await p.locator('#resource-confirm').waitFor({state:'visible'});await p.locator('#reference-save').click();await p.waitForFunction(()=>document.getElementById('reference-notice').textContent.includes('已保存'));
  const saved=(await api('resource-links',{workspace:root})).links[0];check('confirmed reference saved with exact name and URL',saved.name==='<img src=x onerror=alert(1)>'&&saved.url==='https://example.com/resources');
  await p.reload();await p.locator('#links-list [data-link="'+saved.id+'"]').waitFor();await p.locator('#links-list [data-link="'+saved.id+'"]').click();
  check('reload retrieves real stored URL safely',await p.locator('#link-description').innerText()===saved.url&&await p.locator('#link-title img').count()===0);
  await p.locator('#link-open').click();await p.locator('#reference-open').waitFor({state:'visible'});check('opening requires separate confirmation with safe target',await p.locator('#reference-open').getAttribute('href')===saved.url&&await p.locator('#reference-open').getAttribute('rel')==='noopener noreferrer');
  const popup=await Promise.all([p.waitForEvent('popup'),p.locator('#reference-open').click()]).then(r=>r[0]);await popup.waitForLoadState();check('explicit browser navigation only',popup.url()===saved.url);await popup.close();
  check('dangerous URL rejected by backend',(await raw('resource-link-preview',{workspace:root,name:'Unsafe',url:'javascript:alert(1)'})).status===409);
  check('foreign workspace and arbitrary path API rejected',(await raw('resource-documents',{workspace:path.dirname(root)})).status===409&&(await raw('resource-preview',{workspace:root,id:'../outside',version:'x'})).status===409);
  const a=await api('work-create',{chat:ready.chat,turn:ready.turn}),v=await api('work-preview',{id:a.id,goal:'UX05 resource round trip',expected:'Only bounded source structure',selection:['daily']}),work=await api('work-confirm',{id:a.id,approval:v.approval,authority:'READ_ONLY'});
  await p.waitForFunction(async id=>{const d=await(await fetch('/api/state')).json();return !d.busy&&d.tasks.some(t=>t.task_id===id&&t.state==='RESULT_PENDING_REVIEW');},work.task_id);
  await p.evaluate(id=>nexusOpenWork(id),work.task_id);await p.waitForFunction(id=>surfaceInspection().result?.task_id===id,work.task_id);const result=await p.evaluate(()=>surfaceInspection().result.result_id);
  await p.locator('#companion-ask').click();await p.locator('#companion-panel .chat-message').first().waitFor();await p.locator('#chat-question').fill('UX05 draft retained');await p.locator('#companion-close').click();await p.locator('#project-work-return').click();await p.waitForFunction(()=>document.body.dataset.route==='project');await docs();
  await nav('chat');await p.waitForFunction(id=>document.getElementById('chat-history').value===id,ready.chat);check('resources/work/Companion round trip retains chat draft and no source consent',await p.locator('#chat-question').inputValue()==='UX05 draft retained'&&await sourceFree());
  const ref=prototype?await context.newPage():null;if(ref)await ref.goto(pathToFileURL(path.resolve(prototype)).href+'#documents');
  for(const [width,height] of [[1650,1100],[1440,1000],[390,844],[360,844]]){
    await p.setViewportSize({width,height});if(ref)await ref.setViewportSize({width,height});
    for(const screen of ['documents','links']){
      if(screen==='documents'){await docs();await chooseReadme();await p.locator('#document-preview').click();await p.locator('#document-content').waitFor({state:'visible'});}else{await links();await p.locator('#links-list [data-link="'+saved.id+'"]').click();}
      const m=await p.evaluate(screen=>{const root=document.getElementById('nexus-'+screen),grid=root.querySelector(screen==='documents'?'.resource-doc-layout':'.resource-links-layout'),children=[...grid.children].map(e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width};});return {width:innerWidth,scale:visualViewport.scale,columns:getComputedStyle(grid).gridTemplateColumns.split(' ').length,overflow:document.documentElement.scrollWidth>innerWidth+1,children,clipped:[...root.querySelectorAll('h1,h2,p,strong,small,input,button')].filter(e=>e.getClientRects().length&&getComputedStyle(e).overflowX==='hidden'&&e.scrollWidth>e.clientWidth+2).map(e=>e.id||e.tagName)};},screen);
      check(`${screen} ${width}: layout, no clipping or overflow`,m.columns===(width>1100?2:1)&&!m.overflow&&!m.clipped.length&&m.scale===1,m);
      check(`${screen} ${width}: separated index/detail`,width>1100?m.children[0].right<m.children[1].x:m.children[0].bottom<m.children[1].y);
      await shot(p,`product-${screen}-${width}`);
      if(ref){await ref.evaluate(screen=>{location.hash=screen;dispatchEvent(new Event('hashchange'));},screen);await ref.locator('#screen-'+screen).waitFor({state:'visible'});await ref.waitForTimeout(200);const r=await ref.locator(screen==='documents'?'.ux05-doc-layout':'.ux05-links-layout').evaluate(e=>({columns:getComputedStyle(e).gridTemplateColumns.split(' ').length,scale:visualViewport.scale}));check(`${screen} ${width}: same primary layout as approved prototype`,r.columns===m.columns&&r.scale===m.scale);comparisons.push({screen,width,height,product:m,prototype:r});await shot(ref,`prototype-${screen}-${width}`);}
    }
    await p.locator('#link-add').click();await p.locator('#reference-name').fill('Example reference');await p.locator('#reference-url').fill('https://example.com/help');await p.locator('#reference-form button').click();await p.locator('#resource-confirm').waitFor({state:'visible'});check(width+' save confirmation reachable',await p.locator('#reference-save').evaluate(e=>{const r=e.getBoundingClientRect();return r.right<=innerWidth&&r.bottom<=innerHeight;}));await shot(p,'product-confirm-'+width);await p.keyboard.press('Escape');
  }
  // Actual projects can fill the bounded 64-entry index. Keep detail reading near
  // the selection, rather than allowing the entire page to grow with the index.
  for(let i=0;i<70;i++)fs.writeFileSync(path.join(root,'docs',`guide-${i}.txt`),'Bounded long-index fixture.');
  fs.writeFileSync(path.join(root,'docs','000_'+'long_resource_title_'.repeat(4)+'.txt'),'Long filename with a genuine text file.');
  await p.setViewportSize({width:1440,height:1000});await docs();
  check('long filenames fit desktop rows without overlap',await p.locator('#documents-list .resource-row').evaluateAll(rows=>rows.every(row=>{const outer=row.getBoundingClientRect(),text=row.lastElementChild.getBoundingClientRect();return text.top>=outer.top&&text.bottom<=outer.bottom;})));
  await p.setViewportSize({width:390,height:844});await docs();
  check('long real file index remains bounded and scrollable',await p.locator('#documents-list [data-document]').count()===64&&await p.locator('#documents-list').evaluate(e=>e.scrollHeight>e.clientHeight&&e.clientHeight<=innerHeight*.66));
  await p.locator('#documents-list button').last().click();
  check('narrow selection moves reading focus to detail without sharing',await p.locator('#document-title').evaluate(e=>e===document.activeElement)&&await sourceFree());
  await p.setViewportSize({width:1440,height:1000});await links();await p.locator('#links-list [data-link="'+saved.id+'"]').click();await p.locator('#link-open').click();await p.locator('#resource-confirm').waitFor({state:'visible'});
  const ack=new Promise(resolve=>ready.lines.once('line',resolve));ready.child.stdin.write('{"action":"account","account":"synthetic-other"}\n');await ack;await p.waitForFunction(()=>companionProjectStatus().account==='synthetic-other');await links();
  check('account switch revokes open navigation confirmation',!await p.locator('#resource-confirm').isVisible()&&await p.locator('#reference-open').getAttribute('href')===null);
  check('other account cannot read stored references',await p.locator('#links-list [data-link="'+saved.id+'"]').count()===0&&(await raw('resource-link-open',{workspace:root,id:saved.id})).status===409);
  await docs();const old=await api('resource-documents',{workspace:root});await p.route('**/api/chat/resource-documents',route=>route.abort());await p.locator('#documents-refresh').click();await p.waitForFunction(()=>document.getElementById('documents-list').textContent.includes('無法取得'));check('unavailable resource clears previous contents',await p.locator('#documents-list [data-document]').count()===0&&await p.locator('#document-content').isHidden());await p.unrouteAll({behavior:'wait'});
  check('no model calls, project relation changes or review decisions',!requests.some(r=>['/api/chat/send','/api/chat/project-confirm','/api/review'].includes(r.path)));
  check('no browser errors',errors.length===0,errors);
 }catch(e){if(p)await p.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});throw e;}
 finally{if(browser)await browser.close();for(const child of children){const ended=new Promise(resolve=>child.once('exit',resolve));child.stdin.end('{"action":"stop"}\n');await ended;}fs.writeFileSync(path.join(out,'checks.json'),JSON.stringify({checks,shots,comparisons,errors,requests,seconds:(performance.now()-started)/1000,syntheticAccount:true,realModelRequests:0,realFilesystemAndSQLite:true},null,2));}
 console.log(JSON.stringify({passed:checks.length,seconds:(performance.now()-started)/1000,out}));
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
