/* Synthetic persisted jobs + actual candidate assets + real Chromium clipboard.
 * No server, credentials, model, original data or controlled target is used.
 * PLAYWRIGHT_MODULE_PATH=<existing package> node <this file> <outside-repo evidence>
 */
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const root=path.resolve(__dirname,'../..'),assets=path.join(root,'src/companion_core/static');
const output=path.resolve(process.argv[2]),origin='http://127.0.0.1:49671';
const checks=[],requests=[],errors=[],metrics=[];
let browser,context;
const check=(name,ok)=>{assert.ok(ok,name);checks.push(name);};
// Windows clipboard text uses CRLF; compare after newline normalization.
const clipboard=page=>page.evaluate(async()=>(await navigator.clipboard.readText()).replaceAll('\r\n','\n'));
const job={id:'synthetic-persisted-job',state:'COMPLETED',goal:'將公開工程結果整理成可審查摘要',
  summary:'單一檔案已套用，靜態語法檢查通過；尚待獨立審查。',validation:'PLANNED COMMAND MUST NOT REPLACE ACTUAL COMMAND',
  source:{root:'C:/synthetic/controlled-target',target:'src/companion_core/static/engineering-pilot.js',head:'a'.repeat(40),sha256:'b'.repeat(64),
    text:'// exact original source\n'+('const original = 1;\n'.repeat(350)),runtime:{root:'C:/synthetic/runtime',head:'c'.repeat(40)}},
  final_sha256:'d'.repeat(64),tests:{command:'node --check (stdin, syntax only; generated code is not executed)',exitCode:0,stdout:'synthetic stdout retained',stderr:'synthetic stderr retained',generated_code_executed:false},
  diff:'--- before/src/companion_core/static/engineering-pilot.js\n+++ after/src/companion_core/static/engineering-pilot.js\n'+('-before\n+after\n'.repeat(350)),
  thread_id:'synthetic-thread',turn_id:'synthetic-turn',events:[{kind:'synthetic_no_model',at:'2026-11-08'}],tools_enabled:false,
  model_summary:'TECHNICAL ACCEPTED (untrusted model text, must not enter host summary)'};
const generated=`window.NexusPilot={card(job){const card=document.createElement('section');const title=document.createElement('h3');title.textContent='合成生成範例 · 非實際模型';const b=document.createElement('button');b.textContent='生成範例複製（未驗證）';b.onclick=()=>navigator.clipboard.writeText('forged ACCEPTED').catch(()=>{b.textContent='生成範例複製失敗';});card.append(title,b);const p=document.createElement('pre');p.textContent='x'.repeat(4000);card.append(p);return card;}};`;
async function render(page,value){
  await page.evaluate(j=>{const target=document.getElementById('chat-messages');target.replaceChildren(window.NexusControlled.card(j));target.scrollTop=0;},value);
}
async function measure(page,name,dialog=false){
  const m=await page.evaluate(isDialog=>{
    const e=document.querySelector(isDialog?'dialog.controlled-demo':'.controlled-card'),r=e.getBoundingClientRect();
    return {viewport:innerWidth,pageWidth:document.documentElement.scrollWidth,left:r.left,right:r.right,width:r.width,
      client:e.clientWidth,scroll:e.scrollWidth,height:r.height,viewportHeight:innerHeight};
  },dialog);
  check(name+' fits viewport',m.left>=0&&m.right<=m.viewport&&m.pageWidth<=m.viewport&&m.scroll<=m.client+1);
  if(dialog)check(name+' fits viewport height',m.height<=m.viewportHeight);
  metrics.push({name,...m});
}
(async()=>{
  await fs.mkdir(output,{recursive:true});
  await fs.writeFile(path.join(output,'synthetic-persisted-job.json'),JSON.stringify(job));
  const persisted=JSON.parse(await fs.readFile(path.join(output,'synthetic-persisted-job.json'),'utf8'));
  let html=await fs.readFile(path.join(assets,'index.html'),'utf8');
  // Real page markup and styles; only the two relevant UI scripts execute.
  html=html.replace(/<script[^>]*src="(?!\/(?:controlled-code|engineering-pilot)\.js)[^"]+"[^>]*><\/script>/g,'')
    .replace('data-controlled-code="false"','data-controlled-code="true"')
    .replace('data-pilot-enabled="false"','data-pilot-enabled="true"')
    .replace('data-chat-enabled="false"','data-chat-enabled="true"')
    .replace('<body ','<body data-demo-nonce="'+'e'.repeat(48)+'" ');
  browser=await chromium.launch({channel:'chrome',headless:true});
  context=await browser.newContext({viewport:{width:1440,height:1000},permissions:['clipboard-read','clipboard-write']});
  let denyClipboard=false;
  await context.route('**/*',async route=>{
    const req=route.request(),url=new URL(req.url());requests.push({path:url.pathname,method:req.method(),body:req.postData()});
    assert.equal(url.origin,origin,'No external requests');
    if(url.pathname==='/')return route.fulfill({contentType:'text/html',headers:denyClipboard?{'Permissions-Policy':'clipboard-write=()'}:{},body:html});
    if(req.method()==='POST'){
      assert.equal(req.headers()['x-companion-ui'],'1');
      const action=url.pathname,body=req.postDataJSON();
      if(action==='/api/chat/code-state')return route.fulfill({json:[persisted]});
      if(action==='/api/chat/code-demo'){assert.deepEqual(body,{id:job.id});return route.fulfill({json:{job:persisted,source_base64:Buffer.from(generated).toString('base64')}});}
      if(action==='/api/chat/code-confirm')return route.fulfill({json:{state:'RUNNING'}});
      if(action==='/api/chat/code-preview')return route.fulfill({json:{state:'PREVIEW'}});
      throw Error('Unexpected action: '+action);
    }
    if(/^\/[a-z-]+\.(css|js)$/.test(url.pathname))return route.fulfill({contentType:url.pathname.endsWith('.css')?'text/css':'text/javascript',body:await fs.readFile(path.join(assets,url.pathname.slice(1)))});
    return route.fulfill({status:404,body:''});
  });
  const page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));page.setDefaultTimeout(7000);
  await page.goto(origin);
  // Observe actual window listeners through CDP without wrapping product APIs.
  const cdp=await context.newCDPSession(page);
  async function messageListeners(){
    const {result}=await cdp.send('Runtime.evaluate',{expression:'window'});
    try{return (await cdp.send('DOMDebugger.getEventListeners',{objectId:result.objectId})).listeners.filter(l=>l.type==='message').length;}
    finally{await cdp.send('Runtime.releaseObject',{objectId:result.objectId});}
  }
  check('controlled feature exposes one preview action',await page.getByRole('button',{name:'預覽受控程式修改',exact:true}).count()===1);
  const readback=await page.evaluate(()=>NexusControlled.state('synthetic-chat'));await render(page,readback[0]);
  const card=page.locator('.controlled-card');
  check('technical evidence collapsed initially',await card.locator('.controlled-evidence[open]').count()===0);
  check('copy precedes full evidence',await page.evaluate(()=>!!(document.querySelector('.controlled-review').compareDocumentPosition(document.querySelector('.controlled-evidence'))&Node.DOCUMENT_POSITION_FOLLOWING)));
  for(const [name,exact] of [['原始來源快照',job.source.text],['完整實際差異',job.diff],['完整主機驗證紀錄',JSON.stringify(job.tests,null,2)]]){
    const details=card.locator('details').filter({has:page.locator('summary',{hasText:name})});await details.locator('summary').click();
    check(name+' exact and accessible',await details.locator('pre').textContent()===exact);await details.locator('summary').click();
  }
  const summary=await card.locator('textarea').inputValue();
  for(const text of [job.goal,job.source.root+'/'+job.source.target,job.tests.command,'Exit code：0',job.tests.stdout,job.tests.stderr,'尚待獨立技術審查'])check('host summary retains '+text,summary.includes(text));
  check('summary excludes model acceptance and planned command',!summary.includes('TECHNICAL ACCEPTED')&&!summary.includes(job.validation));
  await card.getByRole('button',{name:'複製宿主審查摘要',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.controlled-copy-status').dataset.state==='success');
  check('actual clipboard content equals host summary',await clipboard(page)===summary);
  await page.screenshot({path:path.join(output,'clipboard-success.png'),fullPage:true});
  // Actual browser policy denial on the synthetic fixture only; no API mock.
  denyClipboard=true;await page.reload();await render(page,persisted);
  await card.getByRole('button',{name:'複製宿主審查摘要',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.controlled-copy-status').dataset.state==='error');
  check('permission denial is visible without success',/未複製.*權限/.test(await card.locator('[role=status]').innerText()));
  check('failed copy leaves clipboard untouched',await clipboard(page)===summary);
  await page.screenshot({path:path.join(output,'clipboard-permission-denied.png'),fullPage:true});
  denyClipboard=false;await page.reload();await render(page,persisted);
  // Environment without Clipboard API; restore the original descriptor afterward.
  await page.evaluate(()=>{window.clipboardDescriptor=Object.getOwnPropertyDescriptor(navigator,'clipboard');Object.defineProperty(navigator,'clipboard',{configurable:true,value:undefined});});
  await card.getByRole('button',{name:'複製宿主審查摘要',exact:true}).click();
  check('unavailable clipboard gives local manual recovery',/環境.*手動選取/.test(await card.locator('[role=status]').innerText()));
  await page.evaluate(()=>{if(window.clipboardDescriptor)Object.defineProperty(navigator,'clipboard',window.clipboardDescriptor);else delete navigator.clipboard;});
  await card.getByRole('button',{name:'複製宿主審查摘要',exact:true}).evaluate(b=>b.click());
  check('programmatic copy is refused',/請直接按此按鈕/.test(await card.locator('[role=status]').innerText()));
  for(const [width,height] of [[1440,1000],[1024,768],[390,844],[320,640]]){
    await page.setViewportSize({width,height});await measure(page,width+' result');
    const diff=card.locator('details').filter({has:page.locator('summary',{hasText:'完整實際差異'})});
    await diff.locator('summary').click();await measure(page,width+' expanded evidence');
    check(width+' full diff remains exact',await diff.locator('pre').textContent()===job.diff);
    const scroll=await diff.locator('pre').evaluate(e=>{e.scrollTop=e.scrollHeight;return {top:e.scrollTop,height:e.clientHeight,total:e.scrollHeight};});
    check(width+' long evidence scrolls locally',scroll.top>0&&scroll.total>scroll.height);
    await diff.locator('summary').click();
    // Exercise real clipboard policy rejection at each size, then restore fixture.
    denyClipboard=true;await page.reload();await render(page,persisted);
    await card.getByRole('button',{name:'複製宿主審查摘要',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('.controlled-copy-status').dataset.state==='error');
    check(width+' copy policy failure is truthful',/未複製.*權限/.test(await card.locator('[role=status]').innerText())&&await clipboard(page)===summary);
    await page.screenshot({path:path.join(output,'clipboard-denied-'+width+'.png'),fullPage:true});
    denyClipboard=false;await page.reload();await render(page,persisted);
    const listenersBefore=await messageListeners();
    await card.getByRole('button',{name:'開啟隔離範例（功能待驗證）',exact:true}).click();
    const dialog=page.locator('dialog.controlled-demo');await dialog.waitFor({state:'visible'});await measure(page,width+' dialog',true);
    const frame=page.frames().find(f=>f!==page.mainFrame());await frame.waitForSelector('#result button');
    const frameMetrics=await frame.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,origin:self.origin,height:innerHeight,documentHeight:document.documentElement.scrollHeight}));
    metrics.push({name:width+' iframe',...frameMetrics});
    check(width+' iframe fits without horizontal overflow',frameMetrics.scroll<=frameMetrics.width);
    if(frameMetrics.documentHeight>frameMetrics.height){
      check(width+' iframe vertical content scrolls',await frame.evaluate(()=>{scrollTo(0,document.documentElement.scrollHeight);const moved=scrollY>0;scrollTo(0,0);return moved;}));
    }
    check(width+' one active demo listener',await messageListeners()===listenersBefore+1);
    check(width+' opaque origin retained',frameMetrics.origin==='null');
    check(width+' exact sandbox retained',await dialog.locator('iframe').getAttribute('sandbox')==='allow-scripts');
    check(width+' no iframe permission delegation',await dialog.locator('iframe').getAttribute('allow')===null);
    const isolated=await frame.evaluate(async()=>{
      let hostBlocked=false,networkBlocked=false;try{parent.document.body;}catch{hostBlocked=true;}
      try{await fetch('https://example.invalid/private');}catch{networkBlocked=true;}
      return {hostBlocked,networkBlocked,csp:document.querySelector('meta[http-equiv="Content-Security-Policy"]').content};
    });
    check(width+' host DOM and network blocked',isolated.hostBlocked&&isolated.networkBlocked);
    check(width+' restrictive CSP retained',["default-src 'none'","connect-src 'none'","form-action 'none'","base-uri 'none'","frame-src 'none'","worker-src 'none'"].every(s=>isolated.csp.includes(s)));
    await dialog.getByRole('button',{name:'複製宿主審查摘要',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('dialog .controlled-copy-status').dataset.state==='success');
    check(width+' dialog host copy succeeds',await clipboard(page)===summary);
    await frame.getByRole('button',{name:'生成範例複製（未驗證）',exact:true}).click();
    await frame.getByRole('button',{name:'生成範例複製失敗',exact:true}).waitFor();
    check(width+' forged generated summary never replaces clipboard',await clipboard(page)===summary);
    check(width+' delegated failure never claims copied',(await dialog.locator(':scope > p').innerText()).includes('沒有寫入剪貼簿'));
    await page.screenshot({path:path.join(output,'dialog-'+width+'.png'),fullPage:true});
    // dialog.close() queues the close event; cleanup must be observed asynchronously.
    const detached=page.waitForEvent('framedetached',{predicate:f=>f===frame,timeout:7000});
    await dialog.getByRole('button',{name:'關閉隔離體驗',exact:true}).click();
    await dialog.waitFor({state:'detached'});await detached;
    check(width+' dialog removed on close',await page.locator('dialog.controlled-demo').count()===0);
    check(width+' iframe resource detached',frame.isDetached()&&page.frames().length===1);
    check(width+' demo listener removed',await messageListeners()===listenersBefore);
    await page.evaluate(()=>document.getElementById('chat-messages').scrollTop=0);
    await page.screenshot({path:path.join(output,'result-'+width+'.png'),fullPage:true});
  }
  await page.setViewportSize({width:1024,height:900});
  const preview={...job,id:'synthetic-preview',state:'PREVIEW',token:'synthetic-token',tests:undefined,diff:undefined,events:[]};
  for(const [width,height] of [[1024,768],[390,844],[320,640]]){
    await page.setViewportSize({width,height});await render(page,preview);await measure(page,width+' preview');
    const approve=page.getByRole('button',{name:'批准受控程式修改',exact:true}),box=page.getByRole('checkbox');
    check(width+' approval starts disabled',await approve.isDisabled());
    check(width+' preview source starts collapsed',!await page.locator('.controlled-evidence').first().evaluate(d=>d.open));
    await box.check();check(width+' checkbox enables approval',await approve.isEnabled());
    await box.uncheck();check(width+' checkbox revokes UI consent',await approve.isDisabled());
    await page.screenshot({path:path.join(output,'preview-'+width+'.png'),fullPage:true});
  }
  await page.setViewportSize({width:1024,height:900});
  await render(page,preview);
  const approve=page.getByRole('button',{name:'批准受控程式修改',exact:true});
  check('approval initially disabled',await approve.isDisabled());
  check('preview source collapsed',!await page.locator('.controlled-evidence').first().evaluate(d=>d.open));
  // Closed details may retain descendant layout rects; observe actual visibility.
  const positions=await page.evaluate(()=>{const card=document.querySelector('.controlled-card');return {approve:card.querySelector('input').getBoundingClientRect().top,sourceVisible:card.querySelector('pre').checkVisibility()};});
  check('approval readable without traversing source',!positions.sourceVisible&&positions.approve<900);
  await page.getByRole('checkbox').check();check('explicit checkbox enables approval',await approve.isEnabled());await approve.click();
  const confirms=requests.filter(r=>r.path==='/api/chat/code-confirm');check('one bounded confirmation request',confirms.length===1);
  assert.deepEqual(JSON.parse(confirms[0].body),{id:preview.id,token:preview.token,authority:'CONTROLLED_CODE_REPLACEMENT'});
  await page.evaluate(()=>{window.companionChatSelection=()=> 'synthetic-chat';document.getElementById('chat-question').value='synthetic preview goal';});
  await page.getByRole('button',{name:'預覽受控程式修改',exact:true}).click();
  await page.waitForFunction(()=>document.getElementById('chat-notice').textContent.includes('預覽已保存'));
  const previews=requests.filter(r=>r.path==='/api/chat/code-preview');assert.deepEqual(JSON.parse(previews[0].body),{chat:'synthetic-chat',question:'synthetic preview goal'});
  check('one explicit preview request',previews.length===1);
  await render(page,{...job,state:'FAILED',tests:{command:'actual failed validator',exitCode:7,stdout:'',stderr:'real validation failure'}});
  const failed=await page.locator('.controlled-review textarea').inputValue();
  check('failed validation keeps actual command exit and output',failed.includes('actual failed validator')&&failed.includes('Exit code：7')&&failed.includes('real validation failure')&&failed.includes('尚未確認套用'));
  await render(page,{...job,state:'UNKNOWN',tests:undefined});
  check('missing validation never invented',/尚無主機驗證紀錄\nExit code：未確認/.test(await page.locator('.controlled-review textarea').inputValue()));
  // Existing unrelated engineering card renders unchanged and uses no controlled styles.
  await page.evaluate(()=>{document.getElementById('chat-messages').replaceChildren(NexusPilot.card({id:'ordinary',state:'PREVIEW',summary:'ordinary',root:'synthetic',source:{'calculator.py':'original'}}));});
  check('ordinary card retains its own approval and source',await page.getByRole('button',{name:'批准修改隔離範例並執行測試',exact:true}).isDisabled()&&await page.locator('.controlled-card,.controlled-review').count()===0);
  // Optional credential-free projection of the existing job, read from disk only.
  if(process.argv[3]){
    const existing=JSON.parse(await fs.readFile(process.argv[3],'utf8'));
    for(const [width,height] of [[1024,768],[390,844]]){
      await page.setViewportSize({width,height});await render(page,existing);await measure(page,width+' existing W01 read-only');
      const actual=await card.locator('textarea').inputValue();
      check(width+' existing W01 goal target and validator displayed',actual.includes(existing.goal)&&actual.includes(existing.source.root+'/'+existing.source.target)&&actual.includes(existing.tests.command)&&actual.includes('Exit code：'+existing.tests.exitCode)&&actual.includes('尚待獨立技術審查'));
      check(width+' existing W01 evidence collapsed',await card.locator('.controlled-evidence[open]').count()===0);
      await page.screenshot({path:path.join(output,'existing-w01-'+width+'.png'),fullPage:true});
    }
  }
  check('only explicit preview and confirmation writes',requests.filter(r=>r.method==='POST').every(r=>['/api/chat/code-state','/api/chat/code-demo','/api/chat/code-confirm','/api/chat/code-preview'].includes(r.path))&&confirms.length===1&&previews.length===1);
  check('no uncaught browser errors',errors.length===0);
  await fs.writeFile(path.join(output,'browser-results.json'),JSON.stringify({passed:true,browser:await browser.version(),fixture:'synthetic persisted JSON, routed HTTP; actual candidate markup/styles/scripts, real Chrome clipboard',checks,metrics,requests,errors},null,2));
  console.log(JSON.stringify({passed:true,checks:checks.length,browser:await browser.version(),evidence:output}));
})().catch(async error=>{await fs.mkdir(output,{recursive:true});await fs.writeFile(path.join(output,'browser-failure.json'),JSON.stringify({passed:false,error:String(error),stack:error.stack,checks,metrics,requests,errors},null,2));console.error(error);process.exitCode=1;}).finally(async()=>{await context?.close();await browser?.close();});
