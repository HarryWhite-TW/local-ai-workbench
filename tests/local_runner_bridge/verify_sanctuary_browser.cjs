/* Run: node tests/local_runner_bridge/verify_sanctuary_browser.cjs <evidence-dir>
 * Uses an already-installed playwright/playwright-core (or PLAYWRIGHT_MODULE_PATH).
 * Never installs packages. PYTHON and PLAYWRIGHT_BROWSER_PATH are optional.
 * Starts/stops only its own isolated fixture server. No production control writes.
 */
const fs=require('node:fs/promises'),path=require('node:path'),{spawn}=require('node:child_process'),readline=require('node:readline');
let playwright;
for(const name of [process.env.PLAYWRIGHT_MODULE_PATH,'playwright','playwright-core'].filter(Boolean)){try{playwright=require(name);break;}catch{}}
if(!playwright)throw Error('Use an existing Playwright installation via PLAYWRIGHT_MODULE_PATH; no install is performed.');
const evidence=path.resolve(process.argv[2]||'sanctuary-browser-evidence');
const checks=[],errors=[],requests=[];
let server,browser,page,context,fault=null,replayed=null;
function check(name,value,detail){if(!value)throw Error(name+': '+JSON.stringify(detail));checks.push({name,passed:true,detail});}
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function startServer(port=0){
 const child=spawn(process.env.PYTHON||'python',[path.join(__dirname,'sanctuary_browser_server.py'),'--port',String(port)],{windowsHide:true,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}});
 const queued=[],waiting=[];let stderr='';child.stderr.on('data',b=>stderr+=b);
 readline.createInterface({input:child.stdout}).on('line',line=>{try{const v=JSON.parse(line);if(waiting.length)waiting.shift()(v);else queued.push(v);}catch{stderr+=line;}});
 const next=()=>queued.length?Promise.resolve(queued.shift()):new Promise((resolve,reject)=>{const fail=e=>reject(e),timer=setTimeout(()=>{child.removeListener('error',fail);reject(Error('fixture server timeout '+stderr));},15000);waiting.push(v=>{clearTimeout(timer);child.removeListener('error',fail);resolve(v);});child.once('error',fail);});
 const ready=await next();
 return{child,url:ready.url,session:ready.session,configure:async value=>{child.stdin.write(JSON.stringify(value)+'\n');return next();},stop:async()=>{if(child.exitCode!==null)return;const ended=new Promise(r=>child.once('exit',r));child.stdin.end('{"stop":true}\n');await ended;}};
}
async function state(){return page.evaluate(()=>window.sanctuaryInspection());}
async function refresh(){const before=(await state()).delivery;await page.locator('#refresh').click();await page.waitForFunction(old=>{const s=window.sanctuaryInspection();return s.connectionFailure||JSON.stringify(s.delivery)!==JSON.stringify(old);},before);}
async function configure(name,extra={}){await server.configure({case:name,offset:0,reset:false,...extra});await refresh();await page.waitForFunction(()=>!window.sanctuaryInspection().connectionFailure);}
async function visibleWorld(){
 await page.waitForFunction(()=>window.sanctuaryInspection()?.source&&window.sanctuaryInspection().rendered.frames>1);
 const pixels=await page.evaluate(()=>{const c=document.querySelector('#living-world'),data=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let opaque=0,samples=0;const colors=new Set();for(let i=0;i<data.length;i+=64){samples++;if(data[i+3]>0){opaque++;colors.add([data[i],data[i+1],data[i+2]].join(','));}}return{width:c.width,height:c.height,opaque,samples,colors:colors.size};});
 check('actual visible canvas pixels',pixels.width>300&&pixels.height>300&&pixels.opaque>pixels.samples*.2&&pixels.colors>30,pixels);
}
async function shot(name){await visibleWorld();await page.screenshot({path:path.join(evidence,name+'.png'),fullPage:true});}
(async()=>{
 await fs.mkdir(evidence,{recursive:true});server=await startServer();
 browser=await playwright.chromium.launch(process.env.PLAYWRIGHT_BROWSER_PATH?{executablePath:process.env.PLAYWRIGHT_BROWSER_PATH,headless:true}:{channel:'chrome',headless:true});
 context=await browser.newContext({viewport:{width:1600,height:1000},deviceScaleFactor:1});page=await context.newPage();page.setDefaultTimeout(10000);
 page.on('pageerror',e=>errors.push(String(e)));page.on('request',r=>requests.push({method:r.method(),url:r.url()}));
 await page.route('**/api/sanctuary',async route=>{
  if(fault==='offline')return route.abort('connectionrefused');
  if(fault==='timeout'){await pause(4500);return route.abort().catch(()=>{});}
  let response;
  try{response=await route.fetch();}catch{return route.abort('connectionrefused').catch(()=>{});}
  let value=await response.json();
  if(fault==='duplicate')value=replayed;
  if(fault==='stale')value.snapshot.observed_at_utc=new Date(Date.now()-20000).toISOString();
  if(fault==='identity')value.world.identity.run_id='wrong-run-999';
  replayed=value;
  await route.fulfill({response,json:value});
 });
 await page.goto(server.url+'/sanctuary');await visibleWorld();
 let s=await state();check('source, projection and rendered identity agree',s.source.observability.run_id===s.projection.identity.run_id&&s.rendered.identity.run_id===s.source.observability.run_id,s);
 check('initial historical position does not replay travel',!s.rendered.actorMoving&&!s.rendered.artifactMoving);
 await shot('01-current-task');
 await page.locator('#expert-open').click();
 check('inspector readable with raw JSON closed',!await page.locator('#expert-diagnostics').evaluate(e=>e.open)&&await page.locator('#expert-facts').innerText().then(t=>t.includes('Codex')&&t.includes('RUNNING')));
 check('timeline exposes identifiable test',await page.locator('#activity-timeline').innerText().then(t=>t.includes('pytest')));
 await page.locator('[data-event="2"]').click();check('event locates Test Bench',(await state()).selectedZone==='test');
 await shot('02-integrated-inspector');
 await page.locator('#event-detail button').click();check('locate returns to visible world',!await page.locator('#expert-dialog').evaluate(e=>e.open)&&(await state()).rendered.selected==='test');
 await page.locator('[data-zone="test"]').click();check('station opens matching evidence',(await state()).selectedEvent===2&&await page.locator('#expert-dialog').evaluate(e=>e.open));
 await page.keyboard.press('Escape');check('keyboard close restores trigger focus',await page.locator('#expert-open').evaluate(e=>e===document.activeElement));
 const target=(await state()).rendered.targets.actor,box=await page.locator('#living-world').boundingBox();await page.mouse.click(box.x+target[0],box.y+target[1]);
 check('actor opens relevant inspector',await page.locator('#expert-dialog').evaluate(e=>e.open)&&(await state()).selectedZone==='test'&&await page.locator('#selection-context').innerText().then(t=>t.includes('Builder')));await page.keyboard.press('Escape');
 const artifact=(await state()).rendered.targets.artifact;await page.mouse.click(box.x+artifact[0],box.y+artifact[1]);
 check('artifact opens relevant inspector',await page.locator('#expert-dialog').evaluate(e=>e.open)&&await page.locator('#selection-context').innerText().then(t=>t.includes('成果')));await page.keyboard.press('Escape');
 await page.reload();await visibleWorld();s=await state();check('refresh snaps to source without replay',!s.rendered.actorMoving&&!s.rendered.artifactMoving);
 await configure('technical-repair');check('repair remains technical with no human callout',(await state()).projection.human.kind==='TECHNICAL_ACTION'&&await page.locator('#human-callout').isHidden());await shot('03-technical-action');
 await configure('waiting-review');check('ChatGPT owns review',(await state()).projection.human.kind==='CHATGPT_REVIEW');
 await page.locator('#expert-open').click();check('missing summaries and proposal stay unavailable',await page.locator('#review-facts').innerText().then(t=>t.includes('unavailable')&&t.includes('Test summary')));await page.keyboard.press('Escape');
 await configure('accepted');check('accepted result static',(await state()).rendered.pose==='accepted'&&!(await state()).rendered.semanticMotion);
 await configure('process-completed');check('process completion not final acceptance',(await state()).rendered.pose==='settled'&&(await state()).source.current_task.lifecycle.stage==='RUNNING');
 await server.configure({case:'execution',reset:true});await refresh();check('completed run cannot resume after contradictory source reset',(await state()).connectionFailure==='completed_run_activity_conflict'&&!(await state()).rendered.semanticMotion);
 await configure('command',{generation:1});
 for(const name of ['command','file','tool','test']){await configure(name);check(name+' readable activity',(await state()).projection.activity===name);}
 for(const name of ['offline','timeout','stale','duplicate','identity']){
  fault=name;await refresh();await page.waitForFunction(()=>!!window.sanctuaryInspection().connectionFailure);s=await state();check(name+' fails closed',!s.rendered.semanticMotion&&!s.rendered.actorMoving&&!s.rendered.artifactMoving,s.connectionFailure);
  fault=null;await refresh();await page.waitForFunction(()=>!window.sanctuaryInspection().connectionFailure);s=await state();check(name+' reconnect does not replay',!s.rendered.actorMoving&&!s.rendered.artifactMoving);
 }
 await configure('test');const observed=(await state()).source.observed_at_utc;await configure('test',{offset:-4});s=await state();check('clock rollback accepted using transport ordering',Date.parse(s.source.observed_at_utc)<Date.parse(observed)&&!s.connectionFailure);
 await configure('test');await page.locator('[data-zone="test"]').click();await page.keyboard.press('Escape');const selection=(await state()).selectedEvent;
 fault='offline';await refresh();fault=null;await refresh();await page.waitForFunction(()=>!window.sanctuaryInspection().connectionFailure);check('same-source selection survives reconnect',(await state()).selectedEvent===selection);
 await configure('test',{reset:true});s=await state();check('source reset clears selection and travel',s.selectedEvent===null&&!s.rendered.actorMoving&&!s.rendered.artifactMoving);
 await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));});check('visibility suspension stops activity',!(await state()).rendered.semanticMotion);
 await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'));});await page.waitForFunction(()=>!window.sanctuaryInspection().connectionFailure);check('visibility resume snaps to current evidence',!(await state()).rendered.actorMoving);
 const cdp=await context.newCDPSession(page);await cdp.send('Page.setWebLifecycleState',{state:'frozen'});await pause(6500);await cdp.send('Page.setWebLifecycleState',{state:'active'});await page.waitForFunction(()=>!window.sanctuaryInspection().connectionFailure&&window.sanctuaryInspection().receivedAgeMs<2000);check('real browser freeze resumes without journey replay',!(await state()).rendered.actorMoving);
 const port=Number(new URL(server.url).port),oldSession=(await state()).delivery.session;await server.stop();await refresh();check('actual server stop is visible',!!(await state()).connectionFailure);
 server=await startServer(port);await server.configure({generation:1});await refresh();await page.waitForFunction(()=>!window.sanctuaryInspection().connectionFailure);s=await state();check('actual server restart changes transport only',s.delivery.session!==oldSession&&!s.rendered.actorMoving&&s.source.observability.run_id===s.rendered.identity.run_id);await shot('04-reconnected');
 await page.emulateMedia({reducedMotion:'reduce'});await page.waitForFunction(()=>window.sanctuaryInspection().rendered.reducedMotion);const before=await page.locator('#living-world').screenshot();await pause(500);const after=await page.locator('#living-world').screenshot();check('reduced motion canvas actually static',before.equals(after));
 await page.setViewportSize({width:1280,height:900});await shot('05-desktop-1280');
 await page.setViewportSize({width:390,height:844});await shot('06-narrow-world');await page.locator('#expert-open').click();await shot('07-narrow-inspector');check('narrow layout has no horizontal overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.keyboard.press('Escape');await page.setViewportSize({width:1600,height:1000});await page.emulateMedia({reducedMotion:'no-preference'});
 // Canvas capture uses the browser's existing encoder, no new package/binary.
 await page.evaluate(()=>{
  const canvas=document.createElement('canvas');canvas.width=1280;canvas.height=900;const ctx=canvas.getContext('2d'),world=document.querySelector('#living-world'),chunks=[];
  const stream=canvas.captureStream(20),recorder=new MediaRecorder(stream,{mimeType:'video/webm;codecs=vp9'});let frame;
  function draw(){const state=window.sanctuaryInspection();ctx.fillStyle='#0b1520';ctx.fillRect(0,0,1280,900);ctx.drawImage(world,0,105,1280,780);ctx.fillStyle='#9edfd2';ctx.font="14px 'Segoe UI'";ctx.fillText('STABILIZATION | CONTROLLED FIXTURE REPLAY | NO WORKFLOW EXECUTION',25,27);ctx.font="24px 'Segoe UI','Microsoft JhengHei'";ctx.fillStyle='#e0e8e5';ctx.fillText(state.presentation.title,25,62);ctx.font="14px 'Segoe UI','Microsoft JhengHei'";ctx.fillText(state.presentation.human.owner+' / '+state.presentation.description,25,88);frame=requestAnimationFrame(draw);}draw();
  window.verificationVideo=new Promise(resolve=>{recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};recorder.onstop=()=>{cancelAnimationFrame(frame);stream.getTracks().forEach(t=>t.stop());const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.readAsDataURL(new Blob(chunks,{type:'video/webm'}));};});window.stopVerificationVideo=()=>recorder.stop();recorder.start();
 });
 const timeline=['request','execution','test','process-completed','waiting-review','technical-repair','accepted'];
 for(const name of timeline){await configure(name);await pause(name==='execution'||name==='test'?2200:1000);}
 await page.evaluate(()=>window.stopVerificationVideo());const video=await page.evaluate(()=>window.verificationVideo);const videoBytes=Buffer.from(video.split(',')[1],'base64');await fs.writeFile(path.join(evidence,'stabilization-replay.webm'),videoBytes);
 const metadataPage=await context.newPage();await metadataPage.goto('about:blank');const videoMeta=await metadataPage.evaluate(async data=>{const v=document.createElement('video');v.src=data;await new Promise((resolve,reject)=>{v.onloadedmetadata=resolve;v.onerror=reject;});return{width:v.videoWidth,height:v.videoHeight};},video);await metadataPage.close();
 check('recording decodes as rendered video',videoMeta.width===1280&&videoMeta.height===900&&videoBytes.length>10000,videoMeta);await fs.writeFile(path.join(evidence,'recording.json'),JSON.stringify({mode:'controlled fixture replay, not real execution',timeline,...videoMeta,bytes:videoBytes.length},null,2));
 await configure('test-discovery',{generation:2});
 check('tool help does not become test activity',(await state()).rendered.activity==='command'&&(await state()).rendered.station==='workshop');
 await page.locator('[data-zone="test"]').click();
 check('explicit unknown cannot fall back to executable in Inspector',await page.locator('#event-detail').innerText().then(t=>t.includes('沒有可核對')));
 await page.keyboard.press('Escape');
 for(const name of ['pytest-funcargs','pytest-setup-only','pytest-setuponly','pytest-setup-plan','pytest-setupplan','pytest-version-repeat','pytest-collectonly','pytest-cache-show','pytest-cache-show-pattern','ctest-show-only','ctest-print-labels','vitest-list','vitest-standalone','vitest-clear-cache','jest-show-config','jest-clear-cache']){
  await configure(name,{generation:2});
  if(name.startsWith('pytest-')){
   const payload=[...replayed.events].reverse().find(e=>e.kind==='codex.command.started')?.payload;
   check(name+' explicitly suppresses pytest executable fallback',payload?.command_name==='pytest'&&payload.activity_kind==='command'&&!('test_framework' in payload),payload);
  }
  check(name+' stays command activity',(await state()).rendered.activity==='command'&&(await state()).rendered.station==='workshop');
  await page.locator('[data-zone="test"]').click();
  check(name+' has no test evidence',await page.locator('#event-detail').innerText().then(t=>t.includes('沒有可核對'))&&await page.locator('#review-facts').innerText().then(t=>t.includes('沒有可辨識測試')));
  await page.keyboard.press('Escape');
 }
 await configure('wrapped-test',{generation:2});
 check('structured wrapped test activates Test Bench',(await state()).rendered.station==='test'&&(await state()).rendered.activity==='test');
 await page.locator('[data-zone="test"]').click();
 check('wrapper framework comes from safe structured evidence',await page.locator('#event-detail').innerText().then(t=>t.includes('pytest')&&t.includes('完成狀態未提供')&&!t.includes('.venv-course')));
 await page.keyboard.press('Escape');
 for(const [name,code] of [['short-test-completed',0],['short-test-failed',1],['short-test-review',0]]){
  await configure(name,{generation:3});
  // Reload after both source events: no active-state sample or UI memory exists.
  await page.reload();await visibleWorld();s=await state();
  check(name+' remains static without observing start',!s.rendered.semanticMotion&&!s.rendered.actorMoving&&!s.rendered.artifactMoving&&s.rendered.activity!=='test');
  await page.locator('[data-zone="test"]').click();
  check(name+' opens completed test evidence',await page.locator('#event-detail').innerText().then(t=>t.includes('pytest')&&t.includes('已結束')&&t.includes('exit '+code)));
  check(name+' readable history without raw JSON',await page.locator('#review-facts').innerText().then(t=>t.includes('已觀察測試活動')&&t.includes('pytest')&&t.includes('已結束'))&&!await page.locator('#expert-diagnostics').evaluate(e=>e.open));
  check(name+' preserves request/run correlation',(await state()).source.observability.run_id===(await state()).rendered.identity.run_id);
  if(name==='short-test-review')check('completed test does not replace review ownership',s.source.current_task.lifecycle.stage==='WAITING_FOR_CHATGPT_REVIEW'&&s.projection.human.kind==='CHATGPT_REVIEW'&&!s.projection.human.attention&&s.rendered.station==='review');
  await shot(name);await page.keyboard.press('Escape');
 }
 if(process.env.SANCTUARY_LIVE_URL){
  await page.unroute('**/api/sanctuary');await page.goto(process.env.SANCTUARY_LIVE_URL+'/sanctuary');await visibleWorld();s=await state();
  check('unmocked local source identities agree',s.source.current_task.request_id===s.projection.identity.request_id&&s.source.observability.run_id===s.rendered.identity.run_id,s.source.observability);
  if(process.env.SANCTUARY_EXPECTED_REQUEST)check('independent expected live request',s.source.current_task.request_id===process.env.SANCTUARY_EXPECTED_REQUEST);
  if(process.env.SANCTUARY_EXPECTED_RUN)check('independent expected live run',s.source.observability.run_id===process.env.SANCTUARY_EXPECTED_RUN);
  if(process.env.SANCTUARY_EXPECTED_EVENT_COUNT)check('independent expected live event count',s.source.observability.request_event_count===Number(process.env.SANCTUARY_EXPECTED_EVENT_COUNT));
  check('unmocked historical result stays static',!s.rendered.actorMoving&&!s.rendered.artifactMoving&&!s.rendered.semanticMotion);
  await shot('08-live-current-task');await page.locator('#expert-open').click();await shot('09-live-inspector');
  check('unmocked timeline matches current run count',await page.locator('[data-event]').count()===s.source.observability.request_event_count);
  await fs.writeFile(path.join(evidence,'live-browser-state.json'),JSON.stringify(s,null,2));
 }
 check('no JavaScript runtime errors',errors.length===0,errors);check('browser issues only GET requests',requests.every(r=>r.method==='GET'),requests.length);
 await fs.writeFile(path.join(evidence,'browser-results.json'),JSON.stringify({checks,errors,requests,final:await state()},null,2));
 console.log(JSON.stringify({checks:checks.length,passed:true,evidence}));
})().catch(async error=>{console.error(error);await fs.mkdir(evidence,{recursive:true});await fs.writeFile(path.join(evidence,'browser-failure.json'),JSON.stringify({error:String(error),checks,errors,state:page?await state().catch(()=>null):null},null,2));if(page)await page.screenshot({path:path.join(evidence,'browser-failure.png'),fullPage:true}).catch(()=>{});process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(server)await server.stop();});
