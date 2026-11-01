/* Experience gate only: real Surface/Core/ReviewStore, explicitly synthetic.
 * Existing Playwright/Chrome; evidence and fixture state must live outside Git.
 */
const fs=require("node:fs/promises"),path=require("node:path"),assert=require("node:assert/strict");
const {spawn}=require("node:child_process"),readline=require("node:readline");
const {isDeepStrictEqual}=require("node:util");
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||"playwright");
const evidence=path.resolve(process.argv[2]),checks=[],errors=[],posts=[],requests=[],measurements=[];
let fixture,browser,context,page,url,childStderr="";
const check=(name,value)=>{checks.push({name,passed:!!value});assert.ok(value,name);};
async function startFixture(){
 const child=spawn(process.env.PYTHON||"python",[path.join(__dirname,"browser_fixture.py"),"--experience","--data",path.join(evidence,"fixture")],{windowsHide:true,env:{...process.env,PYTHONDONTWRITEBYTECODE:"1"}});
 const queue=[],waiting=[];child.stderr.on("data",b=>childStderr+=b);
 readline.createInterface({input:child.stdout}).on("line",line=>{const value=JSON.parse(line);if(waiting.length)waiting.shift()(value);else queue.push(value);});
 const next=()=>queue.length ? Promise.resolve(queue.shift()) : new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error("Fixture timeout: "+childStderr)),10000);waiting.push(value=>{clearTimeout(timer);resolve(value);});});
 const ready=await next();url=ready.url;
 return {command:async value=>{child.stdin.write(JSON.stringify(value)+"\n");return next();},stop:async()=>{const end=new Promise(resolve=>child.once("exit",resolve));child.stdin.end('{"action":"stop"}\n');await end;}};
}
const settle=()=>page.waitForTimeout(700);
async function mode(next){await page.locator(`[data-view="${next}"]`).click();await settle();}
async function state(next){await page.waitForFunction(expected=>surfaceInspection().task?.state===expected&&!surfaceInspection().offline,next,{timeout:18000});}
async function snapshot(){return (await fixture.command({action:"inspect"})).snapshot;}
async function screenshot(name){
 const before=await page.evaluate(()=>JSON.stringify([innerWidth,innerHeight,surfaceInspection().reader?.bounds]));
 const cdp=await context.newCDPSession(page);
 try{const capture=await cdp.send("Page.captureScreenshot",{fromSurface:true,captureBeyondViewport:false});await fs.writeFile(path.join(evidence,name+".png"),Buffer.from(capture.data,"base64"));}finally{await cdp.detach();}
 check(name+" screenshot preserves viewport/reader",before===await page.evaluate(()=>JSON.stringify([innerWidth,innerHeight,surfaceInspection().reader?.bounds])));
}
async function observeEvidence(name){
 const backend=await snapshot();
 const actual=await page.locator("#detail-events .experience-event").evaluateAll(rows=>rows.map(row=>({task_id:row.dataset.taskId,sequence:Number(row.dataset.sequence),kind:row.dataset.kind,confirmation:row.dataset.confirmation,title:row.querySelector("strong").textContent,detail:row.querySelector("p").textContent,badge:row.querySelector("small").textContent})));
 measurements.push({name,events:actual,source:backend.observation.events});
 // Compare structured fields, not JSON property order. A periodic UI poll may
 // legitimately trail the provider's next event; every visible event must match.
 check(name+" exact trusted event projection",actual.length>0&&actual.every(({badge,...event})=>isDeepStrictEqual(event,backend.observation.events.find(e=>e.sequence===event.sequence))));
 check(name+" reported phases never display confirmed success",actual.filter(e=>e.confirmation==="reported").every(e=>!e.badge.includes("已確認")||e.badge.includes("未確認")));
 check(name+" evidence tier is visible on each event",actual.length>0&&actual.every(e=>e.badge.length>0));
}
async function geometry(name){
 const m=await page.evaluate(()=>{
  const monitor=document.getElementById("monitor"),scroll=document.getElementById("observation-scroll"),stage=document.getElementById("stage");
  const r=monitor.getBoundingClientRect(),s=stage.getBoundingClientRect(),t=scroll.getBoundingClientRect();
  const controls=[...monitor.querySelectorAll("button")].filter(e=>e.getClientRects().length).map(e=>{const b=e.getBoundingClientRect();return {id:e.id,left:b.left,right:b.right,top:b.top,bottom:b.bottom};});
  return {width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth,monitor:{width:r.width,height:r.height,left:r.left,right:r.right},stage:{width:s.width},readingHeight:t.height,controls};
 });
 measurements.push({name,...m});
 check(name+" no horizontal overflow",!m.overflow);
 check(name+" observation controls remain inside panel",m.controls.every(b=>b.left>=m.monitor.left-1&&b.right<=m.monitor.right+1));
 check(name+" usable event reading height",m.readingHeight>=130);
 if(name.includes("desktop expanded")) check(name+" uses the canvas width",m.monitor.width>=m.stage.width*.95);
}
async function main(){
 await fs.mkdir(evidence,{recursive:true});fixture=await startFixture();
 browser=await chromium.launch({channel:"chrome",headless:true});
 context=await browser.newContext({viewport:{width:1440,height:1000}});page=await context.newPage();
 page.on("pageerror",error=>errors.push(String(error)));
 page.on("request",request=>{requests.push(request.url());if(request.method()==="POST")posts.push({path:new URL(request.url()).pathname,body:request.postDataJSON()});});
 const response=await page.goto(url);await page.waitForFunction(()=>!surfaceInspection().offline);await settle();
 check("synthetic provider, explicit label and READ_ONLY authority",(await snapshot()).runtime==="synthetic-no-ai"&&(await snapshot()).authority==="READ_ONLY"&&await page.locator(".scenario-intro").textContent().then(t=>t.includes("沒有實際 AI")));
 check("incumbent CSP retained",response.headers()["content-security-policy"].includes("connect-src 'self'"));
 const saved=(await snapshot()).tasks, current=await page.evaluate(()=>surfaceInspection().selected);
 const seeds=[saved.find(t=>t.task_id!==current),saved.find(t=>t.task_id===current)];
 check("two independently identified pending synthetic results",saved.length===2&&seeds.every(t=>t?.state==="RESULT_PENDING_REVIEW")&&seeds[0].task_id!==seeds[1].task_id);
 await screenshot("01-workspace");
 await page.locator(`[data-task="${seeds[0].task_id}"]`).click();
 const motion=await page.evaluate(()=>document.getElementById("vessel").getAnimations().map(a=>({duration:a.effect.getTiming().duration,keyframes:a.effect.getKeyframes().map(f=>f.transform)})));
 check("task selection has substantial native motion",motion.some(a=>a.duration>=450&&a.keyframes.some(t=>t?.includes("48px"))));
 measurements.push({name:"task selection motion",motion});await settle();
 await mode("expanded");await page.locator("#result-tab").click();await page.waitForFunction(()=>!!surfaceInspection().result);
 const pinned=await page.evaluate(()=>surfaceInspection().result);await page.locator("#open-reader").click();await settle();
 await page.evaluate(()=>{document.getElementById("reader-resize").focus();});
 for(let i=0;i<14;i++)await page.keyboard.press("Shift+ArrowLeft");await settle();
 const reader=await page.evaluate(()=>{const r=document.getElementById("reader").getBoundingClientRect();return {width:r.width,controls:[...document.querySelectorAll("#reader button")].filter(e=>e.getClientRects().length).map(e=>{const b=e.getBoundingClientRect();return {id:e.id,inside:b.left>=r.left&&b.right<=r.right+1,hit:e.contains(document.elementFromPoint(b.left+b.width/2,b.top+b.height/2))};})};});
 check("accepted Reader minimum 420px and controls retained",Math.abs(reader.width-420)<2&&reader.controls.every(c=>c.inside&&c.hit));measurements.push({name:"420px Reader",...reader});
 // Move the actual floating reader off the left work rail before clicking it.
 // An intentionally covered work card should not receive a pointer through a dialog.
 await page.locator("#reader-handle").focus();
 for(let i=0;i<7;i++)await page.keyboard.press("Shift+ArrowRight");
 await page.locator(`[data-task="${seeds[1].task_id}"]`).click();await settle();
 check("reader identity survives background selection",await page.evaluate(expected=>surfaceInspection().reader.task_id===expected.task_id&&surfaceInspection().reader.result_id===expected.result_id,pinned));
 await screenshot("02-reader-background-selection");
 await page.locator("#reader-return").click();await page.waitForFunction(expected=>surfaceInspection().result?.task_id===expected.task_id&&surfaceInspection().result?.result_id===expected.result_id,pinned);
 check("return selects exact Result/Task, without automatic review",await page.evaluate(id=>surfaceInspection().selected===id,pinned.task_id)&&posts.filter(p=>p.path==="/api/review").length===0);
 await page.locator("#accept").click();await state("ACCEPTED");
 const review=posts.find(p=>p.path==="/api/review");check("human review retains exact pinned pair",review.body.task_id===pinned.task_id&&review.body.result_id===pinned.result_id&&review.body.action==="accept");
 await page.locator('[data-scenario="running"]').click();await state("RUNNING");await page.waitForFunction(()=>surfaceInspection().view==="observe");await settle();
 const running=await page.evaluate(()=>surfaceInspection().selected);await page.locator("#observation-details").click();await settle();
 await observeEvidence("running");await screenshot("03-running-events");
 await page.locator("#expand-observation").click();await settle();await geometry("desktop expanded observation");
 check("observation expansion has preserved task and focus",await page.evaluate(id=>surfaceInspection().selected===id&&surfaceInspection().observationReading&&document.activeElement.id==="observation-scroll",running));
 await screenshot("04-observation-canvas");
 await page.keyboard.press("Escape");await settle();check("observation returns with keyboard focus",await page.evaluate(()=>!surfaceInspection().observationReading&&document.activeElement.id==="expand-observation"));
 await state("RESULT_PENDING_REVIEW");await page.waitForFunction(()=>!document.getElementById("result-tab").disabled);await settle();await observeEvidence("completed");
 check("past inspecting event remains a phase report after completion",await page.locator('[data-kind="inspecting_repository"] small').allTextContents().then(values=>values.every(t=>t.includes("階段回報"))));
 await page.locator('[data-scenario="failed"]').click();await state("FAILED");await settle();await observeEvidence("failed");
 check("failed task shows failure, not a reviewable success",await page.locator("#monitor-state").textContent().then(t=>t.includes("失敗"))&&await page.locator("#result-tab").isDisabled()&&await page.locator('#detail-events [data-kind="failed"] small').textContent().then(t=>t.includes("失敗已確認")));
 await screenshot("05-failure-evidence");
 await page.locator('[data-scenario="running"]').click();await state("RUNNING");await page.locator("#stop").click();await state("CANCELLED");
 check("cancel is explicit, exact task and confirmed by Core",posts.filter(p=>p.path==="/api/cancel").length===1&&(await snapshot()).active.state==="CANCELLED");
 await page.locator("#preferences").click();await page.locator('#settings-dialog [data-theme="umber"]').click();await page.locator('#settings-dialog [data-close]').click();await settle();await screenshot("06-umber");
 await page.locator("#preferences").click();await page.locator('#settings-dialog [data-theme="porcelain"]').click();await page.locator('#settings-dialog [data-close]').click();await settle();await screenshot("07-porcelain");
 check("three existing themes remain selectable",await page.evaluate(()=>surfaceInspection().preferences.theme==="porcelain"));
 await page.setViewportSize({width:420,height:850});await page.locator("#expand-observation").click();await settle();await geometry("420px expanded observation");
 check("mobile expanded lens isolates background",await page.locator(".task-tray").evaluate(e=>e.inert));
 await screenshot("08-mobile-observation");await page.keyboard.press("Escape");await settle();
 check("mobile return restores background",!await page.locator(".task-tray").evaluate(e=>e.inert));
 await page.setViewportSize({width:1280,height:800});await settle();await geometry("1280 observation");
 await context.setOffline(true);await page.waitForFunction(()=>surfaceInspection().offline);check("offline state becomes unknown and execution controls pause",await page.locator("#monitor-state").textContent().then(t=>t.includes("未確認"))&&await page.locator('[data-scenario="running"]').isDisabled());
 await context.setOffline(false);await page.waitForFunction(()=>!surfaceInspection().offline);
 await page.emulateMedia({reducedMotion:"reduce"});await settle();await mode("expanded");
 check("reduced-motion has no active application animations",await page.evaluate(()=>surfaceInspection().reduced&&surfaceInspection().activeAnimations===0));
 const guarded=await page.evaluate(async()=>{
  const a=await fetch("/api/start",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({intent:"blocked probe"})});
  const b=await fetch("/api/start",{method:"POST",headers:{"Content-Type":"application/json","X-Companion-UI":"1"},body:JSON.stringify({intent:"authority probe",authority:"WRITE"})});
  const c=await fetch("/../../AGENTS.md");return [a.status,b.status,c.status];
 });check("same-origin marker, input shape and file route guards retained",guarded.join(",")==="403,409,404");
 check("browser requests stay on isolated localhost",requests.every(request=>new URL(request).origin===url));
 check("no browser errors",errors.length===0);
 await fs.writeFile(path.join(evidence,"final-state.json"),JSON.stringify(await snapshot(),null,2));
}
(async()=>{
 let failure=null;
 try{await main();}catch(error){failure=String(error.stack||error);process.exitCode=1;}
 finally{
  if(page&&failure)try{await screenshot("smoke-failure");}catch{}
  if(browser)await browser.close();if(fixture)await fixture.stop();
  await fs.mkdir(evidence,{recursive:true});await fs.writeFile(path.join(evidence,"browser-smoke.json"),JSON.stringify({passed:!failure,checks,failure,errors,posts,requests,measurements,fixtureStderr:childStderr,fullRegression:false},null,2));
  console.log(JSON.stringify({passed:!failure,checks:checks.length,evidence,failure}));
 }
})();
