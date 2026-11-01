/* Existing Playwright + real Windows Chrome. Synthetic executor, real HTTP/Core/review.
 * PLAYWRIGHT_MODULE_PATH=<installed package> node <this file> <outside-repo evidence>
 */
const fs=require("node:fs/promises"),path=require("node:path"),assert=require("node:assert/strict");
const {spawn}=require("node:child_process"),readline=require("node:readline");
const pw=require(process.env.PLAYWRIGHT_MODULE_PATH||"playwright");
const evidence=path.resolve(process.argv[2]),checks=[],errors=[],posts=[],requests=[],zoomMeasurements=[],performanceObservations=[];
let fixture,browser,page,context,offline=false,browserVersion="";
const check=(name,value)=>{assert.ok(value,name);checks.push({name,passed:true});};
async function startFixture(){
 const child=spawn(process.env.PYTHON||"python",[path.join(__dirname,"browser_fixture.py"),"--data",path.join(evidence,"fixture")],
   {windowsHide:true,env:{...process.env,PYTHONDONTWRITEBYTECODE:"1"}});
 let queued=[],waiting=[],stderr="";
 child.stderr.on("data",b=>stderr+=b);
 readline.createInterface({input:child.stdout}).on("line",line=>{const d=JSON.parse(line);if(waiting.length)waiting.shift()(d);else queued.push(d);});
 const next=()=>queued.length?Promise.resolve(queued.shift()):new Promise((resolve,reject)=>{
   const timer=setTimeout(()=>reject(Error("Fixture timeout "+stderr)),10000);waiting.push(v=>{clearTimeout(timer);resolve(v);});});
 const ready=await next();
 return {url:ready.url,command:async value=>{child.stdin.write(JSON.stringify(value)+"\n");return next();},
 stop:async()=>{const ended=new Promise(r=>child.once("exit",r));child.stdin.end('{"action":"stop"}\n');await ended;}};
}
async function status(state){await page.waitForFunction(s=>surfaceInspection().task?.state===s&&!surfaceInspection().offline,state);}
async function refresh(){await page.locator("#refresh").click();await page.waitForFunction(()=>!surfaceInspection().offline&&!refreshPending);}
async function view(name){await page.locator('.view-switch button[data-view="'+name+'"]').click();await page.waitForTimeout(730);}
async function select(id){await page.locator('[data-task="'+id+'"]').click();await page.waitForTimeout(300);}
async function result(){await page.locator("#result-tab").click();await page.waitForFunction(()=>!!surfaceInspection().result);}
async function shot(name){
 await page.evaluate(()=>scrollTo(0,0));await page.waitForTimeout(750);
 await page.screenshot({path:path.join(evidence,name+".png"),fullPage:true});
}
async function create(intent,outcome="complete"){
 await fixture.command({action:"prepare",outcome});await view("glance");
 await page.locator("#new-task").click();await page.locator("#new-intent").fill(intent);
 await page.locator("#start").click();await status("RUNNING");return page.evaluate(()=>surfaceInspection().selected);
}
async function complete(){await fixture.command({action:"release"});await status("RESULT_PENDING_REVIEW");await page.waitForFunction(()=>!document.getElementById("result-tab").disabled);}
const inspect=()=>fixture.command({action:"inspect"});
async function layout(name){
 const metrics=await page.evaluate(()=>{
  const d=document.getElementById("detail-main"),v=document.getElementById("vessel"),b=document.getElementById("return");
  const dr=d.getBoundingClientRect(),vr=v.getBoundingClientRect(),br=b.getBoundingClientRect();
  const controls=[...v.querySelectorAll("button")].filter(e=>!e.disabled&&e.getClientRects().length).map(e=>{
   const r=e.getBoundingClientRect();return {id:e.id,l:r.left,r:r.right,t:r.top,b:r.bottom};});
  return {width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth,
   detail:dr.height,visibleReturn:br.width>0&&br.left>=vr.left&&br.right<=vr.right&&br.bottom<=vr.bottom,
   controls,readingFont:parseFloat(getComputedStyle(document.getElementById("result-text")).fontSize)};
 });
 check(name+" no page horizontal overflow",!metrics.overflow);
 check(name+" reading viewport has usable height",metrics.detail>=110);
 check(name+" return remains inside vessel",metrics.visibleReturn);
 check(name+" controls within width",metrics.controls.every(r=>r.l>=0&&r.r<=metrics.width));
 check(name+" main reading size retained",metrics.readingFont>=16);
 return metrics;
}
(async()=>{
 await fs.mkdir(evidence,{recursive:true});fixture=await startFixture();
 browser=await pw.chromium.launch({channel:"chrome",headless:false});
 browserVersion=await browser.version();
 context=await browser.newContext({viewport:{width:1440,height:1000},deviceScaleFactor:1});
 page=await context.newPage();page.setDefaultTimeout(10000);
 page.on("pageerror",e=>errors.push(String(e)));
 page.on("console",m=>{if(m.type()==="error"&&!/net::ERR|Failed to load resource/.test(m.text()))errors.push(m.text());});
 page.on("request",r=>{requests.push(r.url());if(r.method()==="POST")posts.push({url:new URL(r.url()).pathname,body:r.postDataJSON()});});
 await page.route("**/api/state",r=>offline?r.abort("connectionrefused"):r.continue());
 await page.goto(fixture.url);await page.waitForFunction(()=>!surfaceInspection().offline);
 check("fresh entry has no invented tasks",await page.locator(".task-tile").count()===0);
 check("synthetic executor labelled, real backend state",await page.locator("#runtime-label").textContent()==="驗證環境 · 合成執行器，非實際 AI");
 check("prototype lifecycle controls removed",await page.locator("#advance,#confirm-cancel,#monitor-advance,#reset-demo,#offline-toggle").count()===0);
 await shot("00-entry");
 const a=await create("整理公開文件與模組邊界");
 await shot("01-glance");
 const before=posts.length;
 await view("expanded");await shot("02-expanded");
 await view("observe");await shot("03-observe");
 check("same backend UUID across views",await page.locator("#task-id").textContent()===a&&/^[0-9a-f-]{36}$/.test(a));
 check("events come from real Core projection",await page.locator("#event-list").textContent()===(await inspect()).snapshot.progress.map((s,i)=>String(i+1).padStart(2,"0")+s).join(""));
 await page.locator("#close-monitor").click();await page.locator("#return").click();await page.waitForTimeout(730);
 check("view switches submit no API calls",posts.length===before);
 check("return retains identity",await page.evaluate(()=>surfaceInspection().selected)===a);
 await complete();await view("expanded");await result();
 const resultA=await page.evaluate(()=>surfaceInspection().result.result_id);
 check("result text equals backend saved result",await page.locator("#result-text").textContent()===await page.evaluate(async id=>(await(await fetch("/api/target",{method:"POST",headers:{"Content-Type":"application/json","X-Companion-UI":"1"},body:JSON.stringify({task_id:id})})).json()).result,a));
 check("viewing does not accept",(await inspect()).snapshot.tasks.find(t=>t.task_id===a).state==="RESULT_PENDING_REVIEW");
 await shot("04-review-pending");await page.locator("#accept").click();await status("ACCEPTED");await shot("05-accepted");
 check("accept binds exact task/result",posts.some(p=>p.url==="/api/review"&&p.body.task_id===a&&p.body.result_id===resultA&&p.body.action==="accept"));
 await page.reload();await page.waitForFunction(()=>!surfaceInspection().offline);await select(a);await view("expanded");await result();
 check("accepted decision survives page reload",await page.evaluate(()=>surfaceInspection().result.state)==="ACCEPTED");
 const b=await create("另一份公開筆記");await complete();
 const c=await create("等待停止確認的工作");
 await select(b);await view("observe");await result();
 check("history cannot stop another task",await page.locator("#stop").isHidden());
 check("history cannot borrow active progress",await page.locator("#event-list").textContent()==="01歷史執行事件未保存，沒有可回放的進度。");
 await page.locator("#revise").click();await page.locator("#revision-intent").fill("補充待確認事項");
 await page.locator("#revision-submit").click();await status("REVISION_REQUESTED");
 check("revision never executes",(await inspect()).requests===3);await shot("06-revision");
 await select(c);await page.locator("#stop").click();await status("CANCEL_REQUESTED");
 check("cancel is pending, not cancelled",await page.locator("#status-label").textContent()==="已請求停止，尚未確認取消");
 check("stop disabled once submitted",await page.locator("#stop").isDisabled());await shot("07-cancel-requested");
 offline=true;await page.locator("#refresh").click();await page.waitForFunction(()=>surfaceInspection().offline);
 check("offline unknown and mutations disabled",await page.locator("#status-label").textContent()==="狀態未確認"&&await page.locator("#stop").isDisabled()&&await page.locator("#new-task").isDisabled());
 check("disconnect did not cancel backend",(await inspect()).snapshot.active.state==="CANCEL_REQUESTED");await shot("08-disconnected");
 offline=false;await refresh();await fixture.command({action:"cancel-release"});await status("CANCELLED");
 check("one exact cancellation POST",posts.filter(p=>p.url==="/api/cancel"&&p.body.task_id===c).length===1);
 await shot("09-cancelled");
 const d=await create("取消收尾失敗","failed");await view("observe");await page.locator("#stop").click();await status("CANCEL_REQUESTED");
 await fixture.command({action:"cancel-release"});await status("FAILED");
 check("failed cancellation never claims cancelled",await page.locator("#status-label").textContent()==="執行失敗");await shot("10-failed");
 const e=await create("拒絕這份合成結果");await complete();await view("expanded");await result();
 await page.locator("#reject").click();await status("REJECTED");
 check("reject remains readonly",(await inspect()).snapshot.authority==="READ_ONLY");
 // Actual host restart: durable review only, no fabricated recovered execution.
 await fixture.stop();fixture=await startFixture();await page.goto(fixture.url);await page.waitForFunction(()=>!surfaceInspection().offline);
 const restarted=await inspect();
 check("host restart has no recovered task or progress",restarted.snapshot.active===null&&restarted.snapshot.progress.length===0);
 for(const [id,state] of [[a,"ACCEPTED"],[b,"REVISION_REQUESTED"],[e,"REJECTED"]]){
  await select(id);await view("expanded");await result();check("host restart reads "+state,await page.evaluate(()=>surfaceInspection().result.state)===state);
 }
 const f=await create("尚未審查的結果");await complete();await view("observe");await result();
 // Delay an old target response, then switch task: the old response cannot rebind review.
 let releaseTarget,arrived;
 const targetArrived=new Promise(r=>arrived=r),targetGate=new Promise(r=>releaseTarget=r);
 await page.route("**/api/target",async route=>{
  const response=await route.fetch();arrived();await targetGate;await route.fulfill({response});
 },{times:1});
 await page.locator("#reload-result").click();await targetArrived;await select(a);releaseTarget();await page.waitForTimeout(400);
 check("late result cannot bind wrong selection",await page.evaluate(id=>surfaceInspection().selected===id&&!surfaceInspection().result,a));
 await select(f);await result();
 // Backend consumes review, but response lost: UI must read back and never resubmit.
 await page.route("**/api/review",async route=>{await route.fetch();await route.abort("connectionreset");},{times:1});
 await page.locator("#accept").click();await status("ACCEPTED");
 check("lost review response never retries",posts.filter(p=>p.url==="/api/review"&&p.body.task_id===f).length===1);
 check("lost response does not invent a review receipt",await page.locator("#review-receipt").isHidden());
 check("unconfirmed review has persistent readback instruction",await page.locator("#result-text").textContent()==="審查是否保存尚未確認。請按「重新讀取成果」確認指定工作；不會自動重試。");
 await page.locator("#reload-result").click();await page.waitForFunction(()=>surfaceInspection().result?.state==="ACCEPTED");
 check("explicit readback reconciles accepted result",await page.locator("#review-receipt").isVisible());
 const g=await create("停止回應遺失的工作");await view("observe");
 await page.route("**/api/cancel",async route=>{await route.fetch();await route.abort("connectionreset");},{times:1});
 await page.locator("#stop").click();await status("CANCEL_REQUESTED");await refresh();
 check("lost stop response remains pending and one shot",posts.filter(p=>p.url==="/api/cancel"&&p.body.task_id===g).length===1&&await page.locator("#stop").isDisabled());
 await fixture.command({action:"cancel-release"});await status("CANCELLED");
 const h=await create("長內容閱讀與視窗操作");await complete();await view("observe");await result();
 const measurements=[];
 for(const theme of ["obsidian","umber","porcelain"]){
  await page.locator("#preferences").click();await page.locator('button[data-theme="'+theme+'"]').click();await page.locator("#settings-dialog [data-close]").click();
  for(const [width,height] of [[1366,768],[1440,1000],[1920,1080],[900,700],[640,640]]){
   await page.setViewportSize({width,height});await page.waitForTimeout(200);
   measurements.push({theme,width,height,...await layout(theme+" "+width)});
   await page.locator("#detail-main").evaluate(e=>e.scrollTop=e.scrollHeight);
   check(theme+" "+width+" result scrolls",await page.locator("#detail-main").evaluate(e=>e.scrollTop>0));
   check(theme+" "+width+" return accessible after reading",await page.locator("#return").isVisible());
   if(width===1366)await shot("theme-"+theme+"-1366");
  }
 }
 await page.setViewportSize({width:1366,height:768});await page.evaluate(()=>scrollTo(0,0));
 await page.locator("#preferences").click();await page.locator("#motion-setting").selectOption("reduced");
 await page.locator("#settings-dialog [data-close]").click();
 const mutations=posts.filter(p=>p.url!=="/api/target").length;
 await page.locator("#close-monitor").focus();await page.keyboard.press("Enter");
 check("keyboard closes observe",await page.evaluate(()=>surfaceInspection().view==="expanded"&&document.activeElement.id==="task-title"));
 await page.locator("#return").focus();await page.keyboard.press("Enter");
 check("keyboard returns glance",await page.evaluate(()=>surfaceInspection().view==="glance"));
 check("reduced motion has no active WAAPI",await page.evaluate(()=>surfaceInspection().activeAnimations)===0);
 await page.locator("#expand").focus();check("focus visible",await page.locator("#expand").evaluate(e=>getComputedStyle(e).outlineStyle)!=="none");
 for(let i=0;i<15;i++){await page.keyboard.press("2");await page.keyboard.press("3");await page.keyboard.press("1");}
 check("rapid reduced views keep exact task",await page.evaluate(()=>surfaceInspection().selected)===h);
 await page.locator("#preferences").click();await page.locator("#motion-setting").selectOption("full");await page.locator("#quality-setting").selectOption("low");await page.locator("#settings-dialog [data-close]").click();
 check("quality preference changes actual light effect",await page.locator(".material-light").evaluate(e=>getComputedStyle(e).display)==="none");
 for(let i=0;i<12;i++){await page.keyboard.press("2");await page.keyboard.press("3");await page.keyboard.press("1");}
 await page.keyboard.press("3");await page.waitForTimeout(850);
 check("interrupted springs settle",await page.evaluate(()=>surfaceInspection().activeAnimations===0&&surfaceInspection().view==="observe"&&surfaceInspection().interrupted>0));
 check("preferences/view animations submit no lifecycle operations",posts.filter(p=>p.url!=="/api/target").length===mutations);
 // Observe a foreground animation rather than assert a universal FPS promise.
 performanceObservations.push(await page.evaluate(()=>new Promise(resolve=>{
  const stamps=[],started=performance.now();transition("expanded",false);
  function frame(time){stamps.push(time);if(time-started<900)requestAnimationFrame(frame);else{
   const gaps=stamps.slice(1).map((v,i)=>v-stamps[i]).sort((a,b)=>a-b);
   resolve({durationMs:time-started,frames:stamps.length,medianFrameMs:gaps[Math.floor(gaps.length/2)],
    p95FrameMs:gaps[Math.floor(gaps.length*.95)],finiteAnimations:surfaceInspection().activeAnimations,
    heapBytes:performance.memory?.usedJSHeapSize||null});
  }}requestAnimationFrame(frame);
 })));
 check("observed animation finishes without retained WAAPI",performanceObservations[0].finiteAnimations===0);
 await view("observe");
 await page.route("**/api/state",async route=>{
  const response=await route.fetch(),body=await response.json();body.active={...body.active,state:"FINISHED_BY_ANIMATION"};
  await route.fulfill({response,json:body});
 },{times:1});
 await page.locator("#refresh").click();await page.waitForFunction(()=>surfaceInspection().offline);
 check("unknown backend state is never shown as success",await page.locator("#status-label").textContent()==="狀態未確認"&&await page.locator("#new-task").isDisabled());
 await refresh();check("reconnect reads real state",await page.evaluate(()=>surfaceInspection().task.state)==="RESULT_PENDING_REVIEW");
 const longIntent="整理公開內容 <b>literal</b>\n\n"+Array.from({length:22},(_,i)=>"工作範圍 "+(i+1)+"：整理可確認內容，保留待釐清問題；這段合成文字用來驗證長工作內容。").join("\n\n");
 const longId=await create(longIntent);await view("expanded");
 check("long task title and brief retain backend intent",await page.locator("#detail-text").textContent()===longIntent&&await page.locator("#task-title").textContent()===longIntent);
 check("intent renders literal text, not HTML",await page.locator("#detail-text b,#task-title b").count()===0);
 await page.locator("#detail-main").evaluate(e=>e.scrollTop=e.scrollHeight);
 check("long task scope scrolls and navigation remains",await page.locator("#detail-main").evaluate(e=>e.scrollTop>0)&&await page.locator("#return").isVisible());
 await complete();await result();await page.locator("#reject").click();await status("REJECTED");
 check("long intent uses a backend UUID",(await inspect()).snapshot.tasks.some(t=>t.task_id===longId&&t.state==="REJECTED"));
 await page.emulateMedia({reducedMotion:"reduce"});check("system reduced motion overrides full preference",await page.evaluate(()=>surfaceInspection().reduced));
 check("all network is same local Surface",requests.every(u=>new URL(u).origin===fixture.url||u.startsWith("http://127.0.0.1:")));
 check("mutations only use existing endpoints",posts.every(p=>["/api/start","/api/target","/api/cancel","/api/review"].includes(p.url)));
 check("no JS or rendering/CSP errors",errors.length===0);
 // New Chrome profiles only: real browser zoom, no CSS zoom or personal profile.
 await browser.close();browser=null;
 for(const width of [1366,1440])for(const factor of [1,1.25,1.5,2]){
  const profile=path.join(evidence,"native-zoom-profiles",width+"-"+factor);
  await fs.mkdir(path.join(profile,"Default"),{recursive:true});
  await fs.writeFile(path.join(profile,"Default","Preferences"),JSON.stringify({partition:{default_zoom_level:{x:Math.log(factor)/Math.log(1.2)}}}));
  context=await pw.chromium.launchPersistentContext(profile,{channel:"chrome",headless:false,viewport:null,args:["--window-size="+width+",950"]});
  page=context.pages()[0];page.setDefaultTimeout(10000);page.on("pageerror",e=>errors.push(String(e)));
  page.on("console",m=>{if(m.type()==="error"&&!/net::ERR|Failed to load resource/.test(m.text()))errors.push(m.text());});
  await page.goto(fixture.url);await page.waitForFunction(()=>!surfaceInspection().offline);
  const windowMetrics=await page.evaluate(()=>({outerWidth,outerHeight,innerWidth,innerHeight}));
  const cdp=await context.newCDPSession(page),targetWindow=await cdp.send("Browser.getWindowForTarget");
  await cdp.send("Browser.setWindowBounds",{windowId:targetWindow.windowId,bounds:{windowState:"normal"}});
  await cdp.send("Browser.setWindowBounds",{windowId:targetWindow.windowId,bounds:{
   width:width+windowMetrics.outerWidth-Math.round(windowMetrics.innerWidth*factor),
   height:(width===1366?768:1000)+windowMetrics.outerHeight-Math.round(windowMetrics.innerHeight*factor)}});
  await page.waitForFunction(w=>Math.abs(innerWidth*devicePixelRatio-w)<3,width);
  const metrics=await page.evaluate(()=>({innerWidth,innerHeight,devicePixelRatio,cssZoom:getComputedStyle(document.body).zoom}));
  zoomMeasurements.push({width,factor,metrics});
  check(width+" native zoom "+factor,Math.abs(metrics.devicePixelRatio-factor)<.015&&Number(metrics.cssZoom)===1);
  await select(h);
  for(const name of ["glance","expanded","observe"]){
   await view(name);
   check(width+" "+factor+" "+name+" no overflow",await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   if(name!=="glance"){
    await result();await layout(width+" "+factor+" "+name);
    await page.locator("#detail-main").evaluate(e=>e.scrollTop=e.scrollHeight);
    check(width+" "+factor+" "+name+" long result scrolls",await page.locator("#detail-main").evaluate(e=>e.scrollTop>0));
   }
  }
  await page.locator("#close-monitor").scrollIntoViewIfNeeded();await page.locator("#close-monitor").click();await page.waitForTimeout(750);
  await page.locator("#return").scrollIntoViewIfNeeded();await page.locator("#return").click();await page.waitForTimeout(750);
  check(width+" "+factor+" native zoom roundtrip",await page.evaluate(id=>surfaceInspection().view==="glance"&&surfaceInspection().selected===id,h));
  // A screenshot of the physical Chrome surface, without changing viewport metrics.
  await page.evaluate(()=>scrollTo(0,0));
  await page.waitForFunction(w=>Math.abs(innerWidth*devicePixelRatio-w)<3,width);
  const capture=await cdp.send("Page.captureScreenshot",{fromSurface:false,captureBeyondViewport:false});
  const png=Buffer.from(capture.data,"base64");await fs.writeFile(path.join(evidence,"native-zoom-"+width+"-"+factor+".png"),png);
  check(width+" "+factor+" full physical capture",Math.abs(png.readUInt32BE(16)-width)<=2);
  await context.close();context=null;
 }
 check("native zoom has no browser errors",errors.length===0);
 await fs.writeFile(path.join(evidence,"browser-checks.json"),JSON.stringify({syntheticExecutor:true,actualAI:false,realSurfaceCoreReview:true,
  browser:browserVersion,headed:true,checks,errors,posts,measurements,zoomMeasurements,performanceObservations},null,2));
 console.log(JSON.stringify({passed:checks.length,errors,evidence}));
})().catch(async e=>{
 console.error(e);if(page)await shot("failure").catch(()=>{});
 await fs.mkdir(evidence,{recursive:true});await fs.writeFile(path.join(evidence,"failure.json"),JSON.stringify({error:String(e),checks,errors},null,2));process.exitCode=1;
}).finally(async()=>{if(context)await context.close();if(browser)await browser.close();if(fixture)await fixture.stop();});
