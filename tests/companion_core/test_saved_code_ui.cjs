/* Production UI with synthetic HTTP identities only; no model or host apply. */
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),http=require('node:http');
const source=fs.readFileSync(path.join(__dirname,'../../src/companion_core/static/controlled-code.js'),'utf8');
function setup(enabled=true){
  const calls=[],notices={textContent:''},window={};let current=true,changed=0,release;
  const document={body:{dataset:{controlledCode:String(enabled)}},createElement:tag=>({tag}),getElementById:()=>notices};
  vm.runInNewContext(source,{window,document,addEventListener(){},fetch:async(url,options)=>{
    calls.push({url,body:JSON.parse(options.body)});await new Promise(resolve=>release=resolve);
    return {ok:true,json:async()=>({id:'job'})};
  }});
  const turn={id:'saved',status:'complete',model:'synthetic-model'};
  return {calls,notices,window,turn,button:()=>window.NexusControlled.savedTurn(turn,'chat',[],()=>{changed++;},()=>current),
    release:()=>release(),stale:()=>{current=false;},changed:()=>changed};
}
test('ENG-01 disabled leaves ordinary chat untouched',()=>assert.equal(setup(false).window.NexusControlled,undefined));
test('only completed saved chat messages offer the explicit action',()=>{
  const e=setup();for(const status of ['pending','failed']){e.turn.status=status;assert.equal(e.button(),null);}
  e.turn.status='complete';e.turn.model='NEXUS · 受控程式修改';assert.equal(e.button(),null);
});
test('click sends message identity only and suppresses duplicate in-flight actions',async()=>{
  const e=setup(),button=e.button(),pending=button.onclick();await button.onclick();
  assert.deepEqual(e.calls,[{url:'/api/chat/code-preview',body:{chat:'chat',turn:'saved'}}]);
  e.release();await pending;assert.equal(e.changed(),1);assert.equal(button.disabled,false);
});
test('stale chat/account context neither submits nor consumes a delayed result',async()=>{
  const e=setup(),button=e.button(),pending=button.onclick();e.stale();e.release();await pending;
  assert.equal(e.changed(),0);await button.onclick();assert.equal(e.calls.length,1);
});

test('browser preserves draft, links and reloads the original saved turn, and withholds a delayed cross-chat result',async()=>{
  const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
  const assets=path.resolve(__dirname,'../../src/companion_core/static'),calls=[],jobs=new Map(),errors=[];
  let enabled=false,hold=null,entered=null;
  const turn={id:'saved',question:'Saved requirement',answer:'Saved discussion',status:'complete',model:'synthetic-model',sources:[],created:'2026-11-07T00:00:00Z'};
  const server=http.createServer(async(req,res)=>{
    let raw='';for await(const part of req)raw+=part;const body=raw?JSON.parse(raw):null;calls.push({url:req.url,body});
    res.setHeader('Content-Type','application/json');const reply=value=>res.end(JSON.stringify(value));
    if(req.url==='/api/state')return reply({workspace:'synthetic-workspace',authority:'READ_ONLY',busy:false,tasks:[],progress:[]});
    if(req.url==='/api/chat/state')return reply({auth:{active:'owner',pending:false,accounts:[{id:'owner',label:'Synthetic',signed_in:true}]},chats:['a','b'].map(id=>({id,title:id,account:'owner'})),models:[{slug:'synthetic-model',display_name:'Synthetic'}],sources:[],busy:null});
    if(req.url==='/api/chat/models')return reply([{slug:'synthetic-model',display_name:'Synthetic'}]);
    if(req.url==='/api/chat/get')return reply({id:body.chat,turns:body.chat==='a'?[turn,{...turn,id:'pending',status:'pending'}]:[{...turn,id:'b-turn'}]});
    if(req.url==='/api/chat/code-state')return reply(jobs.has(body.chat)?[jobs.get(body.chat)]:[]);
    if(req.url==='/api/chat/code-preview'){
      if(hold){entered();await hold;hold=null;}
      if(!jobs.has(body.chat))jobs.set(body.chat,{id:'saved-job',chat:body.chat,turn:body.turn,source_turn:body.turn,goal:turn.question,state:'PREVIEW',token:'synthetic-token',summary:'Not executed',validation:'node --check',source:{root:'fixed',target:'src/companion_core/static/engineering-pilot.js',head:'synthetic',sha256:'synthetic',text:'const saved = 1;'}});
      return reply(jobs.get(body.chat));
    }
    const name=req.url==='/'?'index.html':req.url.slice(1),file=path.join(assets,name);
    if(file.startsWith(assets+path.sep)&&fs.existsSync(file)&&fs.statSync(file).isFile()){
      res.setHeader('Content-Type',name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':'text/html');
      let content=fs.readFileSync(file,'utf8');if(name==='index.html'){content=content.replace('data-chat-enabled="false"','data-chat-enabled="true"');if(enabled)content=content.replace('data-controlled-code="false"','data-controlled-code="true"');}
      return res.end(content);
    }
    res.statusCode=404;reply({error:'Unsupported synthetic operation'});
  });
  let browser,release;
  try{
    await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
    browser=await chromium.launch({channel:'chrome',headless:true});const page=await browser.newPage();page.setDefaultTimeout(10000);page.on('pageerror',e=>errors.push(e.message));
    const url='http://127.0.0.1:'+server.address().port,action=()=>page.getByRole('button',{name:'從這則需求預覽固定範例修改',exact:true});
    await page.goto(url);await page.locator('#chat-history').selectOption('a');
    assert.equal(await action().count(),0);assert.equal(await page.evaluate(()=>!!window.NexusControlled),false);
    enabled=true;await page.reload();await page.locator('#chat-history').selectOption('a');
    await page.locator('[data-turn="saved"]').waitFor();
    assert.equal(await action().count(),0,'ordinary chat does not expose engineering buttons');
    const beforeExpand=calls.length;
    await page.locator('[data-turn="saved"] .chat-message-options summary').click();
    await action().waitFor();assert.equal(await action().count(),1);
    assert.equal(calls.slice(beforeExpand).filter(c=>c.url==='/api/chat/code-preview').length,0,'opening options never creates work');
    await page.locator('#chat-question').fill('UNSENT DRAFT');await action().click();
    await page.locator('[data-turn="saved"] [data-controlled-job="saved-job"]').waitFor();
    assert.equal(await page.locator('#chat-question').inputValue(),'UNSENT DRAFT');
    assert.deepEqual(calls.find(c=>c.url==='/api/chat/code-preview').body,{chat:'a',turn:'saved'});
    await page.reload();await page.locator('#chat-history').selectOption('a');await page.locator('[data-turn="saved"] [data-controlled-job="saved-job"]').waitFor();
    const viewed=page.getByRole('button',{name:'查看受控修改 · PREVIEW',exact:true});
    assert.equal(await viewed.isVisible(),true,'existing work remains directly reachable');
    const started=new Promise(resolve=>entered=resolve);hold=new Promise(resolve=>release=resolve);
    await viewed.click();await started;await page.locator('#chat-history').selectOption('b');release();
    await page.locator('[data-turn="b-turn"]').waitFor();assert.equal(await page.locator('[data-controlled-job]').count(),0);
    assert.equal(calls.filter(c=>c.url==='/api/chat/code-confirm'||c.url==='/api/chat/send').length,0);
    assert.deepEqual(errors,[]);
  }finally{release?.();if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
});
