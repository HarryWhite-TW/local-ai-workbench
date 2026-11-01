/* Existing Playwright + real Windows Chrome. Synthetic executor, real HTTP/Core/review.
 * PLAYWRIGHT_MODULE_PATH=<installed package> node <this file> <outside-repo evidence>
 */
const fs=require("node:fs/promises"),path=require("node:path"),assert=require("node:assert/strict");
const {spawn}=require("node:child_process"),readline=require("node:readline");
const pw=require(process.env.PLAYWRIGHT_MODULE_PATH||"playwright");
const evidence=path.resolve(process.argv[2]),checks=[],errors=[],posts=[],requests=[],zoomMeasurements=[],performanceObservations=[],readerMeasurements=[],observationMeasurements=[],interactionMeasurements=[];
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
async function shot(name,settle=true){
 await page.evaluate(()=>scrollTo(0,0));if(settle)await page.waitForTimeout(750);
 // Native viewport capture avoids full-page emulation resize events changing the reader.
 const before=await page.evaluate(()=>JSON.stringify([innerWidth,innerHeight,surfaceInspection().reader?.bounds]));
 const cdp=await context.newCDPSession(page);
 try {
  const capture=await cdp.send("Page.captureScreenshot",{fromSurface:false,captureBeyondViewport:false});
  await fs.writeFile(path.join(evidence,name+".png"),Buffer.from(capture.data,"base64"));
 } finally {await cdp.detach();}
 check(name+" capture preserves viewport and reader",before===await page.evaluate(()=>JSON.stringify([innerWidth,innerHeight,surfaceInspection().reader?.bounds])));
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

async function readerFits(name){
 const b=await page.evaluate(()=>{
  const reader=document.getElementById("reader"),r=reader.getBoundingClientRect(),body=document.getElementById("reader-body").getBoundingClientRect();
  const header=document.getElementById("reader-handle").getBoundingClientRect(),title=document.getElementById("reader-title").getBoundingClientRect();
  const controls=[...reader.querySelectorAll("button")].filter(e=>e.getClientRects().length).map(e=>{
   const b=e.getBoundingClientRect(),hit=document.elementFromPoint(b.left+b.width/2,b.top+b.height/2);
   return {id:e.id,left:b.left,right:b.right,top:b.top,bottom:b.bottom,hit:hit?.id||hit?.tagName,receivesPointer:e.contains(hit)};
  });
  return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height,w:innerWidth,h:innerHeight,bodyHeight:body.height,
   grid:getComputedStyle(reader).gridTemplateColumns,headerWidth:header.width,titleLeft:title.left,titleRight:title.right,titleWidth:title.width,controls};
 });
 readerMeasurements.push({name,...b});
 check(name+" reader stays in viewport",b.left>=0&&b.right<=b.w+1&&b.top>=0&&b.bottom<=b.h+1);
 check(name+" body readable",b.bodyHeight>=80);
 check(name+" column and title fit reader",b.headerWidth<=b.width&&b.titleWidth>0&&b.titleLeft>=b.left&&b.titleRight<=b.right);
 check(name+" controls available",b.controls.every(c=>c.left>=b.left&&c.right<=b.right+1&&c.top>=b.top&&c.bottom<=b.bottom+1));
 check(name+" controls receive pointer",b.controls.every(c=>c.receivesPointer));
 return b;
}
async function openReader(){await page.locator("#open-reader").click();await page.waitForTimeout(350);}
async function observationFits(name){
 await page.waitForTimeout(300);
 const m=await page.evaluate(()=>{
  const monitor=document.getElementById("monitor"),r=monitor.getBoundingClientRect(),scroll=document.getElementById("observation-scroll"),b=scroll.getBoundingClientRect();
  const controls=[...monitor.querySelectorAll("button")].filter(e=>e.getClientRects().length).map(e=>{
   const c=e.getBoundingClientRect();return {id:e.id,left:c.left,right:c.right,top:c.top,bottom:c.bottom,hit:e.contains(document.elementFromPoint(c.left+c.width/2,c.top+c.height/2))};
  });
  return {width:r.width,height:r.height,left:r.left,right:r.right,top:r.top,bottom:r.bottom,w:innerWidth,h:innerHeight,
   bodyHeight:b.height,bodyBottom:b.bottom,font:parseFloat(getComputedStyle(document.querySelector(".detail-events p")).fontSize),
   tabsBackground:getComputedStyle(document.querySelector(".observation-tabs")).backgroundColor,task:monitor.dataset.taskId,controls,
   coversNavigation:[...document.querySelectorAll(".view-switch button")].every(e=>{
    const n=e.getBoundingClientRect(),x=n.left+n.width/2,y=n.top+n.height/2;
    return x<r.left||x>r.right||y<r.top||y>r.bottom||monitor.contains(document.elementFromPoint(x,y));
   })};
 });
 observationMeasurements.push({name,...m});
 check(name+" expanded observation fits viewport",m.left>=0&&m.right<=m.w+1&&m.top>=0&&m.bottom<=m.h+1);
 check(name+" observation reading region usable",m.bodyHeight>=100&&m.bodyBottom<=m.bottom);
 check(name+" observation controls receive pointer",m.controls.every(c=>c.left>=m.left&&c.right<=m.right&&c.top>=m.top&&c.bottom<=m.bottom&&c.hit));
 check(name+" event reading font retained",m.font>=16);
 check(name+" segmented control has no backing plate",m.tabsBackground==="rgba(0, 0, 0, 0)");
 check(name+" background navigation cannot intercept reading",m.coversNavigation);
 return m;
}
async function observationNormalFits(name){
 await page.locator("#monitor").scrollIntoViewIfNeeded();await page.waitForTimeout(300);
 const m=await page.evaluate(()=>{
  const monitor=document.getElementById("monitor"),r=monitor.getBoundingClientRect(),s=document.getElementById("observation-scroll").getBoundingClientRect(),footer=document.querySelector(".monitor-boundary").getBoundingClientRect();
  const controls=[...monitor.querySelectorAll("button")].filter(e=>e.getClientRects().length).map(e=>{
   const b=e.getBoundingClientRect();return {id:e.id,left:b.left,right:b.right,top:b.top,bottom:b.bottom,hit:e.contains(document.elementFromPoint(b.left+b.width/2,b.top+b.height/2))};
  });
  return {width:r.width,height:r.height,left:r.left,right:r.right,top:r.top,bottom:r.bottom,bodyHeight:s.height,bodyBottom:s.bottom,footerBottom:footer.bottom,controls};
 });
 observationMeasurements.push({name,mode:"normal",...m});
 check(name+" normal event viewport usable",m.bodyHeight>=70&&m.bodyBottom<=m.bottom);
 check(name+" normal boundary explanation is not clipped",m.footerBottom<=m.bottom);
 check(name+" normal controls are reachable",m.controls.every(c=>c.left>=m.left&&c.right<=m.right&&c.top>=m.top&&c.bottom<=m.bottom&&c.hit));
}
const lifecycleCount=()=>posts.filter(p=>p.url!=="/api/target").length;
(async()=>{
 await fs.mkdir(evidence,{recursive:true});fixture=await startFixture();
 browser=await pw.chromium.launch({channel:"chrome",headless:false});browserVersion=await browser.version();
 context=await browser.newContext({viewport:{width:1366,height:768},deviceScaleFactor:1});
 page=await context.newPage();page.setDefaultTimeout(10000);
 page.on("pageerror",e=>errors.push(String(e)));
 page.on("console",m=>{if(m.type()==="error"&&!/net::ERR|Failed to load resource/.test(m.text()))errors.push(m.text());});
 page.on("request",r=>{if(r.method()==="POST")posts.push({url:new URL(r.url()).pathname,body:r.postDataJSON()});});
 await page.route("**/api/state",r=>offline?r.abort("connectionrefused"):r.continue());
 await page.goto(fixture.url);await page.waitForFunction(()=>!surfaceInspection().offline);
 const a=await create("閱讀公開合成工作內容");await view("observe");
 // Interaction evidence uses actual pointer input and computed browser styles.
 await page.locator("#expand-observation").hover();await page.waitForTimeout(250);
 const hover=await page.locator("#expand-observation").evaluate(e=>({background:getComputedStyle(e).backgroundColor,shadow:getComputedStyle(e).boxShadow}));
 const pressBox=await page.locator("#expand-observation").boundingBox();
 await page.mouse.move(pressBox.x+pressBox.width/2,pressBox.y+pressBox.height/2);await page.mouse.down();await page.waitForTimeout(100);
 const pressed=await page.locator("#expand-observation").evaluate(e=>getComputedStyle(e).scale);
 await page.mouse.up();await page.waitForTimeout(320);
 const released=await page.locator("#expand-observation").evaluate(e=>getComputedStyle(e).scale);
 interactionMeasurements.push({hover,pressed,released});
 check("material hover is perceptible",hover.background!=="rgba(0, 0, 0, 0)"&&hover.shadow!=="none");
 check("press contracts and release restores",Number(pressed)<1&&(released==="none"||Number(released)===1));
 check("expansion immediately moves focus to reading region",await page.evaluate(()=>document.activeElement.id)==="observation-scroll");
 await page.keyboard.press("Escape");await page.waitForTimeout(300);
 check("Escape returns observation and focus",await page.evaluate(()=>!surfaceInspection().observationReading&&surfaceInspection().view==="observe"&&document.activeElement.id==="expand-observation"));
 check("focus indication remains visible",await page.locator("#expand-observation").evaluate(e=>getComputedStyle(e).outlineStyle)!=="none");
 await observationNormalFits("running normal monitor");
 const before=lifecycleCount();await page.locator("#observation-details").click();
 check("event view change has finite native feedback",await page.evaluate(()=>surfaceInspection().activeAnimations)>0);
 const nativeTransition=await page.locator("#observation-detail-panel").evaluate(e=>({opacity:getComputedStyle(e).opacity,
  animations:e.getAnimations().map(a=>({state:a.playState,duration:a.effect.getTiming().duration,frames:a.effect.getKeyframes()}))}));
 interactionMeasurements.push({nativeTransition});
 check("event feedback is actual browser animation",nativeTransition.animations.some(a=>a.state==="running"&&a.duration===220));
 await shot("living-details-transition",false);
 check("running status separates execution and review",await page.locator("#monitor-execution").textContent()==="執行中"&&await page.locator("#monitor-review").textContent()==="尚無可審查成果");
 const observations=(await inspect()).snapshot.observation;
 check("detailed events exactly match backend projection",await page.locator("#detail-events li").count()===observations.events.length);
 check("all displayed events bound to active task",observations.events.every(e=>e.task_id===a));
 check("tool capability is honest",await page.locator("#observation-availability").textContent()==="Core 階段回報；工具名稱、命令、工具輸出與逐項完成狀態未提供。");
 check("inspect phase never implies tool success",await page.locator('[data-kind="inspecting_repository"]').textContent().then(t=>t.includes("未提供逐項完成狀態")));
 await shot("01-detailed-running");
 await page.locator("#observation-summary").click();await page.locator("#observation-details").click();
 check("observation views do not execute",lifecycleCount()===before);
 await complete();
 const completionCue=await page.locator("#result-tab").evaluate(e=>e.getAnimations().map(a=>({state:a.playState,duration:a.effect.getTiming().duration})));
 interactionMeasurements.push({completionCue});
 check("fresh saved result gives finite native attention cue",completionCue.some(a=>a.state==="running"&&a.duration===1200));
 await result();
 await page.locator("#observation-details").click();
 check("Core confirms final execution",await page.locator('[data-kind="pending_review"]').getAttribute("data-confirmation")==="confirmed");
 check("provider result report remains provisional",await page.locator('[data-kind="execution_complete"]').getAttribute("data-confirmation")==="reported");
 check("finished execution is distinct from pending human review",await page.locator("#monitor-execution").textContent()==="執行已完成"&&await page.locator("#monitor-review").textContent()==="等待人類審查");
 check("completed task is not labelled executing",await page.locator("#monitor-id").textContent()!=="目前執行工作");
 check("confirmed and reported events have distinct treatment",await page.locator('[data-kind="pending_review"] small').evaluate(e=>getComputedStyle(e).color)!==await page.locator('[data-kind="execution_complete"] small').evaluate(e=>getComputedStyle(e).color));
 const observationCount=lifecycleCount(),eventIdentity=await page.locator("#detail-events").textContent();
 await page.locator("#observation-scroll").evaluate(e=>e.scrollTop=60);
 const originalScroll=await page.locator("#observation-scroll").evaluate(e=>e.scrollTop);
 await page.locator("#expand-observation").click();await observationFits("1366 detailed observation");
 check("expanded monitor remains bound to selected task",await page.locator("#monitor").getAttribute("data-task-id")===a&&await page.locator("#detail-events li").evaluateAll((nodes,id)=>nodes.every(n=>n.dataset.taskId===id),a));
 check("expansion preserves exact projected events",await page.locator("#detail-events").textContent()===eventIdentity);
 await page.locator("#observation-scroll").focus();await page.keyboard.press("End");
 check("long events scroll with keyboard",await page.locator("#observation-scroll").evaluate(e=>e.scrollTop>0));
 await shot("living-observation-expanded");
 await page.locator("#observation-summary").click();await page.locator("#observation-details").click();
 await page.locator("#close-monitor").click();await page.waitForTimeout(300);
 check("reading return preserves view task and scroll",await page.evaluate(id=>!surfaceInspection().observationReading&&surfaceInspection().view==="observe"&&surfaceInspection().selected===id,a)&&await page.locator("#observation-scroll").evaluate(e=>e.scrollTop)===originalScroll);
 check("observation reading grants no lifecycle operations",lifecycleCount()===observationCount);
 await shot("02-confirmed-result");
 const saved=await page.evaluate(async id=>(await(await fetch("/api/target",{method:"POST",headers:{"Content-Type":"application/json","X-Companion-UI":"1"},body:JSON.stringify({task_id:id})})).json()),a);
 const count=lifecycleCount();await openReader();await readerFits("1366 initial");
 check("reader content equals saved backend bytes",await page.locator("#reader-text").textContent()===saved.result);
 check("reader binds exact pair",await page.locator("#reader-task-id").textContent()===a&&await page.locator("#reader-result-id").textContent()===saved.result_id);
 await shot("03-reader");
 const startBounds=await page.locator("#reader").boundingBox(),handle=await page.locator("#reader-handle").boundingBox();
 await page.mouse.move(handle.x+50,handle.y+20);await page.mouse.down();await page.mouse.move(handle.x+100,handle.y+55,{steps:8});await page.mouse.up();
 const moved=await page.locator("#reader").boundingBox();check("pointer moves persistent reader",moved.x>startBounds.x&&moved.y>startBounds.y);
 const resize=await page.locator("#reader-resize").boundingBox();
 await page.mouse.move(resize.x+12,resize.y+12);await page.mouse.down();await page.mouse.move(resize.x-120,resize.y-75,{steps:8});await page.mouse.up();
 const sized=await page.locator("#reader").boundingBox();check("pointer changes reading space",sized.width<moved.width&&sized.height<moved.height);
 await page.locator("#reader-resize").focus();await page.keyboard.press("Shift+ArrowRight");
 check("keyboard resize changes width",await page.locator("#reader").evaluate(e=>e.getBoundingClientRect().width)>sized.width);
 await page.locator("#reader-handle").focus();await page.keyboard.press("ArrowLeft");await readerFits("after pointer and keyboard");
 await page.locator("#reader-focus").click();await readerFits("focused");
 check("focus expands reading space",await page.locator("#reader").evaluate(e=>e.getBoundingClientRect().width)>sized.width);
 await shot("04-focused-reader");
 await page.locator("#reader-body").focus();await page.keyboard.press("End");
 await page.waitForFunction(()=>document.getElementById("reader-body").scrollTop>0);
 check("long reader scrolls",await page.locator("#reader-body").evaluate(e=>e.scrollTop>0));
 check("reader return survives long scroll",await page.locator("#reader-return").isVisible());
 await page.locator("#reader-focus").click();await readerFits("restored");
 // Leave the background navigation exposed using the same keyboard controls.
 await page.locator("#reader-resize").focus();
 for(let i=0;i<12;i++){await page.keyboard.press("Shift+ArrowLeft");await page.keyboard.press("ArrowUp");}
 await page.locator("#reader-handle").focus();
 for(let i=0;i<10;i++)await page.keyboard.press("ArrowLeft");
 for(let i=0;i<4;i++)await page.keyboard.press("ArrowDown");
 const narrow=await readerFits("420px before background switch");
 check("keyboard reaches minimum reader width",Math.abs(narrow.width-420)<1);
 await shot("reader-420-before-switch");
 // Background task changes cannot change the pinned result or grant review.
 const b=await create("另一項合成工作");
 await select(b);
 await readerFits("420px after background switch");
 check("reader remains bound on selection update",await page.locator("#reader-task-id").textContent()===a&&await page.locator("#reader-result-id").textContent()===saved.result_id);
 check("background switch preserves saved result bytes",await page.locator("#reader-text").textContent()===saved.result);
 check("reader explains its separate work",await page.locator("#reader-context").textContent().then(t=>t.includes("另一項工作")));
 await select(a);await readerFits("420px selecting original work");
 await select(b);await readerFits("420px switching back to running work");
 await shot("reader-420-after-switch");
 await page.locator("#reader-return").click();await page.waitForFunction(id=>surfaceInspection().result?.task_id===id,a);
 check("return selects exact reviewed object",await page.evaluate(()=>surfaceInspection().selected)===a);
 check("return closes reader and reloads exact pair",await page.locator("#reader").evaluate(e=>!e.open)&&await page.evaluate(id=>surfaceInspection().result.result_id===id,saved.result_id));
 check("history cannot stop current work",await page.locator("#stop").isHidden());
 check("history has no forged detailed events",await page.locator("#detail-events li").count()===0);
 await page.locator("#accept").click();await status("ACCEPTED");
 check("review exact pair after reader return",posts.some(p=>p.url==="/api/review"&&p.body.task_id===a&&p.body.result_id===saved.result_id&&p.body.action==="accept"));
 check("reading and observation operations did not mutate",lifecycleCount()===count+2); // b start + a accept only
 await select(b);await page.locator("#stop").click();await status("CANCEL_REQUESTED");
 check("no cancelled event during pending stop",await page.locator('[data-kind="cancelled"]').count()===0);
 await view("observe");
 await observationNormalFits("cancel pending normal monitor");
 offline=true;await page.locator("#refresh").click();await page.waitForFunction(()=>surfaceInspection().offline);
 check("offline events unavailable, stop disabled",await page.locator("#detail-events li").count()===0&&await page.locator("#stop").isDisabled());
 offline=false;await refresh();await fixture.command({action:"cancel-release"});await status("CANCELLED");
 check("Core cancellation confirmed in detail",await page.locator('[data-kind="cancelled"]').getAttribute("data-confirmation")==="confirmed");
 const c=await create("失敗安全說明","failed");await view("observe");await fixture.command({action:"release"});await status("FAILED");
 await page.locator("#observation-details").click();
 check("failed Core event and safe error visible",await page.locator('[data-kind="failed"]').getAttribute("data-confirmation")==="confirmed"&&await page.locator("#observation-error").textContent().then(t=>t.includes("執行失敗")));
 await shot("05-failed-observation");
 await select(a);await view("expanded");await result();await openReader();
 const readCount=lifecycleCount();
 for(const theme of ["obsidian","umber","porcelain"]){
  await page.locator("#reader-preferences").click();await page.locator('button[data-theme="'+theme+'"]').click();await page.locator("#settings-dialog [data-close]").click();
  for(const [width,height] of [[1366,768],[1440,1000],[1920,1080],[800,640],[640,480],[420,640],[360,640]]){
   await page.setViewportSize({width,height});await page.waitForTimeout(100);await readerFits(theme+" "+width);
   await page.locator("#reader-focus").click();await readerFits(theme+" "+width+" focus");await page.locator("#reader-focus").click();
  }
  await page.setViewportSize({width:1366,height:768});await shot("reader-"+theme);
 }
 // The same monitor element expands; result reading keeps its original exact binding.
 await page.locator("#reader-close").click();await select(c);await view("observe");await page.locator("#observation-details").click();
 await page.locator("#expand-observation").click();
 for(const theme of ["obsidian","umber","porcelain"]){
  await page.locator("#observation-preferences").click();await page.locator('button[data-theme="'+theme+'"]').click();await page.locator("#settings-dialog [data-close]").click();
  for(const [width,height] of [[1366,768],[1920,1080],[800,640],[640,480],[420,640],[360,640]]){
   await page.setViewportSize({width,height});await observationFits(theme+" "+width+" observation");
   if(height>=640&&width<=800){
    await page.locator("#close-monitor").click();await observationNormalFits(theme+" "+width+" failed normal monitor");
    await page.locator("#expand-observation").click();
   }
  }
  await page.setViewportSize({width:1366,height:768});await shot("living-observation-"+theme);
 }
 await page.locator("#close-monitor").click();await select(a);await view("expanded");await result();await openReader();
 await page.locator("#reader-preferences").click();await page.locator("#motion-setting").selectOption("reduced");await page.locator("#settings-dialog [data-close]").click();
 await page.keyboard.press("Escape");check("Escape closes reader",await page.locator("#reader").evaluate(e=>!e.open));
 await openReader();check("reduced reader has no animation",await page.evaluate(()=>surfaceInspection().activeAnimations)===0);
 check("reduced motion disables CSS feedback transitions",await page.locator("#reader-close").evaluate(e=>getComputedStyle(e).transitionDuration)==="0s");
 offline=true;await page.locator("#reader-close").click();await page.locator("#observe").click();await page.locator("#refresh").click();await page.waitForFunction(()=>surfaceInspection().offline);
 offline=false;await refresh();await result();await openReader();
 offline=true;await page.locator("#refresh").click();await page.waitForFunction(()=>surfaceInspection().offline);
 check("offline reader marks cached content",await page.locator("#reader-status").textContent().then(t=>t.includes("上次讀取")));
 check("cached content never changes identity",await page.locator("#reader-result-id").textContent()===saved.result_id);
 offline=false;await refresh();
 await page.locator("#reader-close").click();
 for(let i=0;i<10;i++){await openReader();await page.locator("#reader-focus").click();await page.keyboard.press("Escape");}
 check("rapid open/focus/close retains task",await page.evaluate(()=>surfaceInspection().selected)===a);
 check("reader controls perform no lifecycle operations",lifecycleCount()===readCount);
 check("no executable result markup",await page.locator("#reader-text script,#reader-text img").count()===0);
 await fixture.stop();fixture=await startFixture();await page.goto(fixture.url);await page.waitForFunction(()=>!surfaceInspection().offline);
 await select(a);await view("observe");await page.locator("#observation-details").click();await result();await openReader();
 check("restart reloads persisted accepted result",await page.locator("#reader-result-id").textContent()===saved.result_id);
 check("restart never recreates event history",await page.locator("#detail-events li").count()===0&&await page.locator("#observation-availability").textContent().then(t=>t.includes("沒有保存")));
 check("no JS/CSP errors",errors.length===0);
 await fs.writeFile(path.join(evidence,"workux-browser-checks.json"),JSON.stringify({checks,errors,posts,readerMeasurements,observationMeasurements,interactionMeasurements,chrome:browserVersion,headed:true,syntheticExecutor:true,actualAI:false,realSurfaceCoreReview:true},null,2));
 console.log(JSON.stringify({passed:checks.length,errors,evidence}));
})().catch(async e=>{
 console.error(e);if(page)await shot("failure").catch(()=>{});await fs.writeFile(path.join(evidence,"failure.json"),JSON.stringify({error:String(e),checks,errors,readerMeasurements,observationMeasurements,interactionMeasurements},null,2));process.exitCode=1;
}).finally(async()=>{if(context)await context.close();if(browser)await browser.close();if(fixture)await fixture.stop();});
