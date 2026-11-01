/* Fast visual gate against the real NEXUS assets/controllers and isolated SQLite.
 * node verify_visual_acceptance.cjs <output> [--surface=overview,project,companion]
 *   [--prove] [--geometry-only] [--related] [--fault=overview|project|companion]
 *   [--compare-all] collects every pixel difference and still exits 1 on failure.
 * Initial capture: --record=<NEW directory>. Never updates an existing baseline.
 * Review PNGs + manifest before adopting a replacement directory. Normal runs are read-only.
 * PLAYWRIGHT_MODULE_PATH / PYTHON follow the existing browser verification scripts.
 */
const fs = require('fs'), path = require('path'), os = require('os');
const assert = require('assert/strict'), readline = require('readline');
const {spawn} = require('child_process'), {createRequire} = require('module');
const {pathToFileURL} = require('url'), {createHash} = require('crypto');
const playwrightPath = require.resolve(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const localRequire = createRequire(playwrightPath);
// Already supplied alongside Playwright by the local runtime; nothing is installed.
const {chromium} = require(playwrightPath), {PNG} = localRequire('pngjs');
const args = process.argv.slice(2), flags = args.filter(a => a.startsWith('--'));
const option = key => flags.find(a => a.startsWith(`--${key}=`))?.split('=').slice(1).join('=');
const selected = (option('surface') || 'overview,project,companion').split(',');
assert(selected.every(s => ['overview','project','companion'].includes(s)), 'Unknown surface');
const record = option('record') && path.resolve(option('record'));
const baseline = path.resolve(option('baseline') || path.join(__dirname, 'visual_baseline'));
const geometryOnly = flags.includes('--geometry-only'), prove = flags.includes('--prove');
const compareAll = flags.includes('--compare-all');
assert(!compareAll || (!record && !geometryOnly), '--compare-all requires existing pixel baselines');
const fault = option('fault');
assert(!fault || selected.includes(fault), 'Fault surface must be selected');
if (record) {
  assert(!fs.existsSync(record), 'Refusing to overwrite an existing baseline directory');
  assert.equal(new Set(selected).size, 3, 'Initial baseline must cover every surface');
  assert(!fault, 'Cannot record a deliberately broken page');
}
const out = path.resolve(args.find(a => !a.startsWith('--')) || fs.mkdtempSync(path.join(os.tmpdir(), 'nexus-visual-report-')));
assert(out !== baseline && out !== record, 'Evidence must be outside the baseline');
fs.mkdirSync(out, {recursive:true});
const started = performance.now(), report = {checks:[], views:[], mutations:[], related:[], errors:[],
  syntheticOnly:true, mode:record?'record':geometryOnly?'geometry-only':'geometry-and-pixels',
  requestCountersScope:'Visual stage; adjacent suites use synthetic inference only',
  modelRequests:0, associationWrites:0, reviewWrites:0};
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const check = (name, passed, detail) => {
  report.checks.push({name, passed:!!passed, ...(detail === undefined ? {} : {detail})});
  assert.ok(passed, name + (detail === undefined ? '' : ': ' + JSON.stringify(detail)));
};
let browser, child, workspace, page, stderr = '', pixelmatch;
const captured = new Map();
async function compare(actualBytes, expectedBytes) {
  const actual = PNG.sync.read(actualBytes), expected = PNG.sync.read(expectedBytes);
  if (actual.width !== expected.width || actual.height !== expected.height)
    return {passed:false, sizeMismatch:true, actual:[actual.width,actual.height], expected:[expected.width,expected.height]};
  const diff = new PNG({width:actual.width,height:actual.height});
  const changed = pixelmatch(expected.data,actual.data,diff.data,actual.width,actual.height,{threshold:0.12});
  return {passed:changed <= actual.width*actual.height*0.001, changed,
    ratio:changed/(actual.width*actual.height), diff:PNG.sync.write(diff)};
}
async function settle() {
  await page.evaluate(async () => { await document.fonts.ready; await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))); });
}
async function measure(surface) {
  return page.evaluate(surface => {
    const q = s => document.querySelector(s), rect = e => {
      const r=e.getBoundingClientRect(); return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height};
    };
    const visible = e => !!e && e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden';
    const box = s => rect(q(s));
    const root = q(surface==='overview'?'#nexus-overview':surface==='project'?'#nexus-project-page':'#companion-panel');
    const clipped = [...root.querySelectorAll('h1,h2,h3,p,dt,dd,.nexus-work-row strong')].filter(visible).filter(e => {
      // Scrolling containers are legitimate; text hidden inside a fixed box is not.
      const style=getComputedStyle(e);
      return (e.scrollWidth>e.clientWidth+2 && ['hidden','clip'].includes(style.overflowX)) ||
        (e.scrollHeight>e.clientHeight+2 && ['hidden','clip'].includes(style.overflowY));
    }).map(e => e.id || e.className || e.tagName);
    const m = {surface,width:innerWidth,height:innerHeight,scale:visualViewport.scale,dpr:devicePixelRatio,
      overflow:document.documentElement.scrollWidth>innerWidth+1, clipped,
      sidebar:box('#nexus-sidebar'), bodyMode:document.body.dataset.sidebar, root:rect(root)};
    if(surface==='overview') {
      const grid=q('.nexus-modules');m.cards=[...grid.children].map(rect);
      m.columns=getComputedStyle(grid).gridTemplateColumns.split(' ').length;
      m.grid=rect(grid);m.recent=box('#nexus-recent-section');
      m.bottom=[...q('#nexus-recent-section').children].map(rect);
      m.type=[getComputedStyle(grid.querySelector('h2')).fontSize,getComputedStyle(grid.querySelector('p')).fontSize];
      m.nav=[...q('#nexus-navigation').querySelectorAll('button')].map(e=>({label:e.getAttribute('aria-label'),...rect(e)}));
    } else if(surface==='project') {
      m.heading=box('.nexus-page-heading');m.protection=box('.project-protection');
      m.grids=[...root.querySelectorAll('.project-grid')].map(e=>({box:rect(e),columns:getComputedStyle(e).gridTemplateColumns.split(' ').length,children:[...e.children].map(rect)}));
      m.sections=['#project-title','#project-workspace','#project-current-sources','#project-tasks','#project-chats'].map(s=>({selector:s,visible:!!visible(q(s)),...box(s)}));
    } else {
      m.panel=box('#companion-panel');m.work=box('#work-space');m.messages=box('#chat-messages');
      m.form=box('#chat-form');m.input=box('#chat-question');m.send=box('#chat-send');
      m.close=box('#companion-close');m.mode=q('#companion-window-mode').value;
      m.composers=[...document.querySelectorAll('#chat-form')].filter(visible).length;
      m.modal=q('#companion-panel').matches(':modal');
    }
    return m;
  }, surface);
}
// Independent layout contract from the accepted v2/UX-04 organization. Not learned
// from the current screenshot, so even initial capture must satisfy these rules.
function violations(m) {
  const bad=[], require=(ok,name)=>{if(!ok)bad.push(name);}, narrow=m.width<=780;
  const inside=r=>r.x>=-1 && r.right<=m.width+1 && r.width>0 && r.height>0;
  const row=(a,b)=>Math.abs(a.y-b.y)<=2 && a.right+8<=b.x;
  const stack=(a,b)=>a.bottom+8<=b.y;
  require(!m.overflow,'horizontal overflow');require(!m.clipped.length,'clipped text');
  require(m.scale===1 && m.dpr===1,'zoom/DPR');
  require(Math.abs(m.sidebar.width-(narrow?60:m.bodyMode==='collapsed'?74:252))<=1,'sidebar width');
  if(m.surface==='overview') {
    require(m.cards.length===7 && m.columns===(narrow?1:2),'overview column count');
    require(m.cards.every(inside),'cards inside viewport');
    for(let i=0;i<m.cards.length;i++) {
      require(m.cards[i].height>=120,'card reading space');
      if(i)require(narrow?stack(m.cards[i-1],m.cards[i]):i%2?row(m.cards[i-1],m.cards[i]):stack(m.cards[i-2],m.cards[i]),'card order/separation');
    }
    require(stack(m.grid,m.recent),'recent work below main modules');
    require(narrow?stack(...m.bottom):row(...m.bottom),'recent/selected summary organization');
    require(m.type[0]===(narrow?'18px':'19px') && m.type[1]==='14px','readable module typography');
    require(m.nav.length===8 && m.nav.every(n=>n.label && n.width>=32 && n.height>=32),'named usable navigation');
    require(m.root.x>=m.sidebar.right-1,'content clears sidebar');
  } else if(m.surface==='project') {
    require(m.grids.length===2,'project has hero and related-content grids');
    require(stack(m.heading,m.protection) && stack(m.protection,m.grids[0].box) && stack(m.grids[0].box,m.grids[1].box),'project information order');
    for(const g of m.grids)require(g.columns===(narrow?1:2) && g.children.length===2 && g.children.every(inside) && (narrow?stack(...g.children):row(...g.children)),'project column relationship');
    require(m.sections.every(s=>s.visible && inside(s)),'required project sections readable');
    require(m.root.x>=m.sidebar.right-1,'project clears sidebar');
  } else {
    require(inside(m.panel) && m.panel.y>=0 && m.panel.bottom<=m.height+1,'window fits viewport');
    require(!m.modal,'nonmodal Companion');require(m.composers===1,'single composer');
    require(m.messages.height>=39 && m.messages.bottom<=m.form.y+1,'message/composer separation');
    require(m.form.bottom<=m.panel.bottom && m.input.height>=35 && inside(m.input),'usable input');
    require(m.send.bottom<=m.panel.bottom && m.close.bottom<=m.height && inside(m.close),'reachable controls');
    if(!narrow)require(m.mode==='split-left'?m.work.x>=m.panel.right-1:m.work.right<=m.panel.x+1,'work and chat coexist without overlap');
  }
  return [...new Set(bad)];
}
async function screenshot() {
  await settle();
  // Only volatile metadata is masked; no main card, message or layout container.
  return page.screenshot({fullPage:true,animations:'disabled',caret:'hide',maskColor:'#59636a',
    mask:[page.locator('#project-workspace'),page.locator('.chat-time')]});
}
const faultStyles={overview:'.nexus-modules {grid-template-columns:repeat(3,minmax(0,1fr)) !important}',
  project:'.project-grid {grid-template-columns:repeat(3,minmax(0,1fr)) !important}',
  companion:'#chat-form {position:fixed !important;top:20px !important;left:0 !important;width:100vw !important}'};
async function inject(surface) {
  // Same-origin test response respects the product CSP. No bypassCSP, inline
  // permission, source-file edit or server endpoint is needed.
  const url=new URL('/visual-regression.css',page.url()).href;
  await page.route(url,route=>route.fulfill({contentType:'text/css',body:faultStyles[surface]}));
  return {style:await page.addStyleTag({url}),url};
}
async function view(name,surface) {
  if(fault===surface)await inject(surface);
  const m=await measure(surface), failures=violations(m), bytes=await screenshot();
  fs.writeFileSync(path.join(out,name+'.png'),bytes);
  report.views.push({name,metrics:m});check(name+' layout',failures.length===0,failures);
  if(record) {
    const repeat=await compare(await screenshot(),bytes);
    check(name+' stable capture',repeat.passed,{changed:repeat.changed});captured.set(name,bytes);
  } else if(!geometryOnly) {
    const expected=fs.readFileSync(path.join(baseline,name+'.png'));
    const result=await compare(bytes,expected);
    if(result.diff && (compareAll || !result.passed))fs.writeFileSync(path.join(out,name+'-diff.png'),result.diff);
    const detail={changed:result.changed,ratio:result.ratio,sizeMismatch:result.sizeMismatch};
    if(compareAll)report.checks.push({name:name+' pixels',passed:result.passed,detail});
    else check(name+' pixels',result.passed,detail);
  }
  if(prove && !report.mutations.some(v=>v.surface===surface)) {
    const scroll=await page.evaluateHandle(()=>[document.scrollingElement,...document.querySelectorAll('*')].filter(e=>e.scrollTop || e.scrollLeft).map(e=>({element:e,x:e.scrollLeft,y:e.scrollTop})));
    const {style,url}=await inject(surface);
    try {
      const mutated=await measure(surface), detected=violations(mutated), altered=await screenshot();
      const pixels=await compare(altered,bytes);
      fs.writeFileSync(path.join(out,name+'-mutation.png'),altered);
      if(pixels.diff)fs.writeFileSync(path.join(out,name+'-mutation-diff.png'),pixels.diff);
      const {diff,...pixelResult}=pixels;
      report.mutations.push({surface,css:faultStyles[surface],detected,metrics:mutated,pixels:pixelResult});
      check(surface+' deliberate regression rejected by geometry',detected.length>0,detected);
      check(surface+' deliberate regression rejected by pixels',!pixels.passed,pixelResult);
    } finally {
      await style.evaluate(e=>e.remove()); await page.unroute(url); await settle();
      await scroll.evaluate(positions=>{for(const p of positions){p.element.scrollLeft=p.x;p.element.scrollTop=p.y;}});await scroll.dispose();
    }
    check(surface+' restored layout',violations(await measure(surface)).length===0);
    const restored=await screenshot(), comparison=await compare(restored,bytes);
    fs.writeFileSync(path.join(out,name+'-restored.png'),restored);
    if(!comparison.passed && comparison.diff)fs.writeFileSync(path.join(out,name+'-restored-diff.png'),comparison.diff);
    check(surface+' restored pixels',comparison.passed,{changed:comparison.changed,ratio:comparison.ratio});
  }
}
async function run() {
  pixelmatch=(await import(pathToFileURL(localRequire.resolve('pixelmatch')).href)).default;
  workspace=fs.mkdtempSync(path.join(os.tmpdir(),'nexus-visual-'));
  const project=path.join(workspace,'NEXUS-Visual-Project'), source=path.join(project,'src','companion_core');
  fs.mkdirSync(source,{recursive:true});fs.writeFileSync(path.join(source,'daily.py'),'"""Synthetic visual fixture, not product capability evidence."""\ndef status():\n    return "synthetic"\n');
  // Reusing an output directory must not accumulate chats/tasks between runs.
  report.fixtureState=fs.mkdtempSync(path.join(out,'fixture-'));
  child=spawn(process.env.PYTHON||'python',['-B',path.join(__dirname,'conversation_work_fixture.py'),report.fixtureState,project],{windowsHide:true,env:{...process.env,PYTHONUTF8:'1'}});
  child.stderr.on('data',s=>stderr+=s);
  const ready=await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(Error('Fixture startup timeout: '+stderr)),20000);
    readline.createInterface({input:child.stdout}).once('line',s=>{clearTimeout(timer);try{resolve(JSON.parse(s));}catch(e){reject(e);}});
    child.once('error',e=>{clearTimeout(timer);reject(e);});child.once('exit',()=>{clearTimeout(timer);reject(Error(stderr));});
  });
  browser=await chromium.launch({channel:'chrome',headless:true,args:['--disable-gpu']});
  const context=await browser.newContext({viewport:{width:1650,height:1100},deviceScaleFactor:1,reducedMotion:'reduce',locale:'zh-TW',timezoneId:'Asia/Taipei',colorScheme:'dark'});
  page=await context.newPage();page.setDefaultTimeout(12000);
  page.on('pageerror',e=>report.errors.push(e.message));
  // No inference or persistent associations/reviews are needed for visual checks.
  await context.route('**/*',async route=>{
    const r=route.request(),url=new URL(r.url());
    if(url.origin!==ready.url){report.errors.push('Unexpected external request: '+url.origin);return route.abort();}
    if(r.method()==='POST' && /\/api\/(chat\/send|chat\/project-confirm|review)(?:\/|$)/.test(url.pathname)) {
      if(url.pathname==='/api/chat/send')report.modelRequests++;
      else if(url.pathname.includes('project-confirm'))report.associationWrites++;else report.reviewWrites++;
      report.errors.push('Forbidden visual-test write: '+url.pathname);return route.abort();
    }
    return route.continue();
  });
  await page.goto(ready.url);await page.waitForFunction(()=>!surfaceInspection().offline);
  report.assets=[];
  for(const name of ['index.html','surface.js','surface.css','chat.js','chat.css','reading.js','nexus.js','nexus.css']) {
    const disk=fs.readFileSync(path.resolve(__dirname,'../../src/companion_core/static',name));
    const expected=name==='index.html'?Buffer.from(disk.toString('utf8').replace('data-chat-enabled="false"','data-chat-enabled="true"').replace('data-work-enabled="false"','data-work-enabled="true"')):disk;
    const response=await context.request.get(ready.url+(name==='index.html'?'/':'/'+name));
    const served=await response.body();
    check('served current asset '+name,response.ok() && hash(expected)===hash(served));
    report.assets.push({name,diskSHA256:hash(disk),servedSHA256:hash(served)});
  }
  report.environment={platform:process.platform,arch:process.arch,os:os.release(),browser:browser.version(),
    playwright:localRequire('playwright/package.json').version,pixelmatch:localRequire('pixelmatch/package.json').version,
    pngjs:localRequire('pngjs/package.json').version,locale:'zh-TW',timezone:'Asia/Taipei',dpr:1,softwareRendering:true,
    fonts:['segoeui.ttf','seguisb.ttf','msjh.ttc','msjhbd.ttc'].map(name=>{const file=path.join(process.env.WINDIR||'/missing','Fonts',name);return {name,sha256:fs.existsSync(file)?hash(fs.readFileSync(file)):null};})};
  if(!record && !geometryOnly) {
    const manifest=JSON.parse(fs.readFileSync(path.join(baseline,'manifest.json'),'utf8'));
    check('same pixel environment',JSON.stringify(manifest.environment)===JSON.stringify(report.environment),
      'Mismatch requires explicit --geometry-only; baseline is never regenerated automatically');
    for(const [name,sha] of Object.entries(manifest.images))check('baseline integrity '+name,hash(fs.readFileSync(path.join(baseline,name)))===sha);
  }
  const call=(name,body)=>page.evaluate(async({name,body})=>{const r=await fetch('/api/chat/'+name,{method:'POST',headers:{'Content-Type':'application/json','X-Companion-UI':'1'},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.error);return d;},{name,body});
  const proposal=await call('work-create',{chat:ready.chat,turn:ready.turn});
  const preview=await call('work-preview',{id:proposal.id,goal:'合成驗收工作：確認固定來源結構',expected:'僅為版面測試，不推定產品功能。',selection:['daily']});
  const work=await call('work-confirm',{id:proposal.id,approval:preview.approval,authority:'READ_ONLY'});
  await page.waitForFunction(async id=>{const d=await(await fetch('/api/state')).json();return !d.busy&&d.tasks.some(t=>t.task_id===id&&t.state==='RESULT_PENDING_REVIEW');},work.task_id);
  await page.waitForSelector('#nexus-recent [data-task="'+work.task_id+'"]');
  const setSize=async(w,h)=>{await page.setViewportSize({width:w,height:h});await settle();};
  const rail=async mode=>{if(await page.locator('body').getAttribute('data-sidebar')!==mode)await page.locator('#nexus-sidebar-toggle').click();await settle();};
  if(selected.includes('overview'))for(const [w,h] of [[1650,1100],[1440,1000],[390,844],[360,844]]) {
    await setSize(w,h);for(const mode of w>780?['expanded','collapsed']:['collapsed']) {
      await rail(mode);await page.evaluate(()=>scrollTo(0,0));await view(`overview-${w}-${mode}`,'overview');
    }
  }
  if(selected.includes('project'))for(const [w,h] of [[1650,1100],[1440,1000],[390,844],[360,844]]) {
    await setSize(w,h);await rail(w>780?'expanded':'collapsed');await page.locator('.nexus-pinned [data-route="project"]').click();
    await page.waitForFunction(()=>!!document.getElementById('nexus-project-page').dataset.project);
    await page.waitForSelector('#project-tasks [data-task="'+work.task_id+'"]');
    check(w+' actual scoped project',await page.locator('#nexus-project-page').getAttribute('data-project')===project);
    await page.evaluate(()=>scrollTo(0,0));await view(`project-${w}`,'project');
  }
  if(selected.includes('companion')) {
    await setSize(1440,1000);await rail('expanded');
    await page.evaluate(id=>nexusOpenWork(id),work.task_id);await page.waitForFunction(id=>surfaceInspection().result?.task_id===id,work.task_id);
    const result=await page.evaluate(()=>surfaceInspection().result.result_id);
    await page.locator('#companion-ask').click();await page.waitForFunction(()=>document.getElementById('companion-panel').open);
    await page.locator('#companion-panel .chat-message').first().waitFor({state:'visible'});
    await page.locator('#chat-question').fill('保留草稿；本次不傳送模型資料。');
    for(const [w,h,mode] of [[1440,1000,'split-right'],[1440,1000,'split-left'],[390,844,'floating'],[360,844,'floating']]) {
      await setSize(w,h);await page.locator('#companion-window-mode').selectOption(mode);await settle();
      check(w+' same work and conversation',await page.locator('#companion-context').getAttribute('data-task')===work.task_id && await page.locator('#chat-history').inputValue()===ready.chat);
      check(w+' no source authorization',await page.locator('#chat-sources input:checked').count()===0);
      await view(`companion-${w}-${mode}`,'companion');
    }
    await page.locator('#companion-expand').click();await page.waitForSelector('#chat-space .chat-message');
    check('expanded conversation keeps draft',await page.locator('#chat-question').inputValue()==='保留草稿；本次不傳送模型資料。');
    await page.locator('#companion-return').click();await page.waitForFunction(id=>surfaceInspection().result?.task_id===id,work.task_id);
    check('same trusted result after return',await page.evaluate(()=>surfaceInspection().result.result_id)===result);
    await page.locator('#project-work-return').click();await page.waitForFunction(project=>document.body.dataset.route==='project' && document.getElementById('nexus-project-page').dataset.project===project,project);
    check('return to original project',await page.locator('#nexus-project-page').getAttribute('data-project')===project);
  }
  check('no browser errors or forbidden requests',report.errors.length===0,report.errors);
  if(compareAll)assert.ok(report.checks.every(c=>c.passed),
    'Pixel differences collected for all selected views; inspect visual-checks.json and *-diff.png. Baselines unchanged.');
  if(record) {
    fs.mkdirSync(record);for(const [name,bytes] of captured)fs.writeFileSync(path.join(record,name+'.png'),bytes,{flag:'wx'});
    fs.writeFileSync(path.join(record,'manifest.json'),JSON.stringify({schema:1,fixture:'synthetic-v1',
      environment:report.environment,pixelTolerance:{threshold:0.12,maxChangedRatio:0.001},
      masks:['#project-workspace (temporary path)','.chat-time (wall clock)'],
      images:Object.fromEntries([...captured].map(([name,bytes])=>[name+'.png',hash(bytes)]))},null,2),{flag:'wx'});
  }
}
async function related() {
  // Optional adjacent coverage, using the existing scripts unchanged. Fast default
  // runs only the visual gate; shared UX changes can opt into full relevant flows.
  const scripts=new Set();
  if(selected.includes('overview'))scripts.add('verify_nexus_layout.cjs');
  if(selected.includes('project'))scripts.add('verify_project_context.cjs');
  if(selected.includes('companion')){scripts.add('verify_companion_window.cjs');scripts.add('verify_conversation_work.cjs');}
  for(const file of scripts) {
    const t=performance.now(), dir=path.join(out,path.basename(file,'.cjs'));
    const exit=await new Promise((resolve,reject)=>{const c=spawn(process.execPath,[path.join(__dirname,file),dir],{windowsHide:true,stdio:'inherit',env:process.env});c.once('exit',resolve);c.once('error',reject);});
    report.related.push({file,exit,seconds:(performance.now()-t)/1000});check(file+' adjacent regression',exit===0);
  }
}
(async()=>{
  try { await run(); report.visualSeconds=(performance.now()-started)/1000; if(flags.includes('--related'))await related(); report.passed=true; }
  catch(e) {report.passed=false;report.failure=e.stack;console.error(e.message);process.exitCode=1;}
  finally {
    if(browser)await browser.close();
    if(child && child.exitCode===null)await new Promise(resolve=>{child.once('exit',resolve);child.stdin.end('{"action":"stop"}\n');});
    // Temporary fixtures are retained as evidence; no production state is opened.
    report.fixtureWorkspace=workspace;report.seconds=(performance.now()-started)/1000;
    if(stderr)report.fixtureStderr=stderr;
    fs.writeFileSync(path.join(out,'visual-checks.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify({passed:report.passed,checks:report.checks.length,views:report.views.length,seconds:report.seconds,out}));
  }
})();
