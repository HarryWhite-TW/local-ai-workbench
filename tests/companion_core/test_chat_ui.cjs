/* Isolated Chrome regression: synthetic HTTP chat data, no model or credentials.
 * Existing production assets and optional Playwright installation are reused.
 */
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const assets=path.resolve(__dirname,'../../src/companion_core/static');

test('conversation home, drafts, knowledge consent, failure and responsive controls',async()=>{
  const calls=[],chats=new Map(),errors=[];
  let models=[],busy=null,catalogFails=false,sendFails=false,signedIn=true,credentialReady=true,pending=false,next=0,getGate=null,releaseGet;
  const source={id:'S1',key:'readme',name:'README.md',text:'Public <img src=x onerror=alert(1)>',sha256:'fixture-hash',captured_at:'2026-01-01T00:00:00Z'};
  const server=http.createServer(async(req,res)=>{
    let raw='';for await(const chunk of req)raw+=chunk;
    const body=raw?JSON.parse(raw):null;calls.push({url:req.url,body});
    res.setHeader('Content-Type','application/json');
    const reply=value=>res.end(JSON.stringify(value));
    if(req.url==='/api/state')return reply({runtime:'工作執行端未連接；可查看與審查既有成果',authority:'READ_ONLY',busy:false,active:null,tasks:[],progress:[]});
    if(req.url==='/api/chat/state')return reply({auth:{active:signedIn?'fixture-account':null,accounts:[{id:'fixture-account',label:'Synthetic account',signed_in:credentialReady}],pending,notice:'Synthetic sign-in'},models:signedIn&&credentialReady&&!pending?models:[],busy,chats:signedIn&&!pending?[...chats.keys()].map(id=>({id,title:'Synthetic '+id})):[],sources:[{id:'readme',label:'README.md'}]});
    if(req.url==='/api/chat/models'){
      if(catalogFails){res.statusCode=409;return reply({error:'Synthetic catalog unavailable'});}
      models=[{slug:'gpt-6.1-sol',display_name:'Synthetic model'}];return reply(models);
    }
    if(req.url==='/api/chat/login'){signedIn=true;credentialReady=true;return reply({});}
    if(req.url==='/api/chat/logout'){signedIn=false;return reply({});}
    if(req.url==='/api/chat/preview')return reply([source]);
    if(req.url==='/api/chat/get'){
      const value={id:body.chat,turns:chats.get(body.chat)},gate=getGate;getGate=null;
      if(gate){gate.enter();await gate.wait;}
      return reply(value);
    }
    if(req.url==='/api/chat/send'){
      if(sendFails){res.statusCode=409;return reply({error:'Synthetic send unavailable'});}
      const chat=body.chat||'chat-'+(++next);if(!chats.has(chat))chats.set(chat,[]);
      const turns=chats.get(chat),id='turn-'+turns.length;
      turns.push({id,question:body.question,answer:null,error:null,status:'pending',model:body.model,created:'2026-01-01T00:00:00Z',sources:body.sources.length?[source]:[]});
      busy={chat,turn:id};return reply({chat,turn:id});
    }
    const name=req.url==='/'?'index.html':req.url.slice(1);
    if(['index.html','chat.js','chat.css','surface.js','surface.css','reading.js','nexus.js','nexus.css'].includes(name)){
      res.setHeader('Content-Type',name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':'text/html');
      let content=fs.readFileSync(path.join(assets,name),'utf8');
      if(name==='index.html')content=content.replace('data-chat-enabled="false"','data-chat-enabled="true"');
      return res.end(content);
    }
    res.statusCode=404;res.end('{}');
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  let browser;
  try{
    browser=await chromium.launch({channel:'chrome',headless:true});
    const page=await browser.newPage({reducedMotion:'reduce',viewport:{width:1440,height:1000}});
    page.setDefaultTimeout(10000);page.on('pageerror',e=>errors.push(e.message));
    const url='http://127.0.0.1:'+server.address().port,count=p=>calls.filter(c=>c.url==='/api/chat/'+p).length;
    const ready=()=>page.waitForFunction(()=>!document.getElementById('chat-send').disabled);
    const close=()=>page.keyboard.press('Escape');
    await page.goto(url);await ready();
    assert.equal(await page.locator('#chat-space').isVisible(),true);
    assert.equal(await page.locator('#work-space').isVisible(),false);
    assert.equal(await page.locator('#chat-settings').isVisible(),false);
    assert.equal(await page.locator('#chat-sources input:checked').count(),0);
    assert.equal(await page.locator('#chat-model').inputValue(),'gpt-6.1-sol');
    assert.equal(count('models'),1);assert.equal(count('preview'),0);assert.equal(count('send'),0);
    async function send(question,keyboard=false){
      await page.locator('#chat-question').fill(question);
      const sent=page.waitForResponse(r=>r.url()===url+'/api/chat/send');
      if(keyboard)await page.locator('#chat-question').press('Control+Enter');else await page.locator('#chat-send').click();
      return (await sent).ok();
    }
    async function complete(answer){
      Object.assign(chats.get(busy.chat).at(-1),{answer,status:'complete'});busy=null;
      await page.waitForFunction(()=>!document.getElementById('chat-send').disabled&&document.getElementById('chat-notice').textContent.includes('回答已保存'));
    }
    await send('Synthetic greeting',true);
    const first=calls.find(c=>c.url==='/api/chat/send').body;
    assert.deepEqual(first.sources,[]);assert.equal(first.preview,null);
    await page.waitForFunction(()=>document.getElementById('chat-send').disabled);
    await page.locator('#chat-question').fill('Draft while waiting');
    await complete('Synthetic long discussion.\n\n'.repeat(160));
    assert.equal(await page.locator('#chat-question').inputValue(),'Draft while waiting');
    assert.equal(await page.locator('#chat-messages .chat-source-link').count(),0);
    assert.ok(await page.locator('#chat-messages').evaluate(n=>n.scrollHeight>n.clientHeight*4&&n.scrollTop<n.scrollHeight/2));
    await page.locator('#chat-messages').evaluate(n=>n.scrollTop=300);
    await page.locator('#open-workspace').click();
    assert.equal(await page.locator('#work-space').isVisible(),true);
    assert.equal(await page.locator('#new-task').isDisabled(),true);
    assert.match(await page.locator('#work-availability').textContent(),/尚未連接/);
    await page.locator('#open-chat').click();
    assert.equal(await page.locator('#chat-question').inputValue(),'Draft while waiting');
    assert.equal(await page.locator('#chat-question').evaluate(n=>n===document.activeElement),true);
    assert.ok(await page.locator('#chat-messages').evaluate(n=>n.scrollTop>=299));
    await page.locator('#chat-new').click();
    assert.equal(await page.locator('#chat-question').inputValue(),'');
    assert.equal(await page.locator('#chat-notice').textContent(),'');
    await page.locator('#chat-question').fill('New conversation draft');
    await page.locator('#chat-history').selectOption('chat-1');
    assert.equal(await page.locator('#chat-question').inputValue(),'Draft while waiting');
    await page.locator('#chat-new').click();
    assert.equal(await page.locator('#chat-question').inputValue(),'New conversation draft');
    await page.locator('#chat-question').fill('');
    await page.locator('#chat-history').selectOption('chat-1');
    await page.locator('.chat-compose-tools summary').click();
    await page.locator('#chat-source-open').click();
    await page.locator('#chat-sources input').check();
    assert.equal(await page.locator('#chat-send').isDisabled(),true);
    assert.equal(await page.locator('#chat-knowledge-done').isDisabled(),true);
    await page.locator('#chat-preview').click();await ready();
    assert.equal(await page.locator('#chat-source-preview img').count(),0);
    assert.equal(count('send'),1);
    await page.locator('#chat-sources input').uncheck();
    assert.equal(await page.locator('#chat-source-preview').textContent(),'');
    await page.locator('#chat-sources input').check();
    assert.equal(await page.locator('#chat-send').isDisabled(),true);
    await page.locator('#chat-preview').click();await ready();
    await page.locator('#chat-knowledge-done').click();
    assert.match(await page.locator('#chat-source-status').textContent(),/已預覽/);
    await send('Synthetic project question');
    const sourced=calls.filter(c=>c.url==='/api/chat/send').at(-1).body;
    assert.deepEqual(sourced.sources,['readme']);assert.deepEqual(sourced.preview,{readme:'fixture-hash'});
    await complete('Synthetic sourced response [S1:L1]');
    assert.equal(await page.locator('#chat-sources input:checked').count(),0);
    await page.locator('.chat-source-link').click();
    assert.equal(await page.locator('#chat-source-records img').count(),0);
    assert.match(await page.locator('#chat-source-records').textContent(),/fixture-hash/);
    await close();
    assert.equal(await page.locator('.chat-source-link').evaluate(n=>n===document.activeElement),true);
    await send('Synthetic return to ordinary discussion');
    const plain=calls.filter(c=>c.url==='/api/chat/send').at(-1).body;
    assert.deepEqual(plain.sources,[]);assert.equal(plain.preview,null);
    Object.assign(chats.get(busy.chat).at(-1),{status:'failed',error:'Synthetic interrupted stream'});busy=null;
    await page.waitForFunction(()=>document.getElementById('chat-notice').textContent==='Synthetic interrupted stream');
    assert.match(await page.locator('#chat-messages').textContent(),/未完成回答/);
    sendFails=true;assert.equal(await send('Keep this rejected draft'),false);
    assert.equal(await page.locator('#chat-question').inputValue(),'Keep this rejected draft');
    assert.equal(chats.get('chat-1').length,3);
    sendFails=false;
    const warning=page.waitForEvent('dialog');
    const reload=page.reload();const dialog=await warning;assert.equal(dialog.type(),'beforeunload');await dialog.accept();await reload;
    await ready();await page.locator('#chat-history').selectOption('chat-1');
    await page.waitForFunction(()=>document.querySelectorAll('#chat-messages .chat-message').length===3);
    // Recovery promises readable content, not an exact distance from the bottom.
    // The status notice can change the viewport while the short latest turn stays fully visible.
    assert.ok(await page.locator('#chat-messages').evaluate(n=>{
      const viewport=n.getBoundingClientRect(),latest=n.lastElementChild.getBoundingClientRect();
      return latest.top>=viewport.top&&latest.bottom<=viewport.bottom;
    }),'the entire latest short/failed turn is readable after recovery');
    async function stableReadingPosition(){
      const positions=await page.locator('#chat-messages').evaluate(async n=>{
        const values=[n.scrollTop];
        for(let i=0;i<3;i++){await new Promise(requestAnimationFrame);values.push(n.scrollTop);}
        return values;
      });
      assert.equal(new Set(positions).size,1,'reading position stays stable after layout');
    }
    await stableReadingPosition();
    assert.equal(await page.locator('.chat-source-link').count(),1);assert.equal(count('send'),4);
    // An unchanged poll and a changed final turn must both leave an older reading position alone.
    await page.locator('#chat-messages').evaluate(n=>n.scrollTop=300);
    await page.waitForResponse(r=>r.url()===url+'/api/chat/get');
    await stableReadingPosition();
    assert.equal(await page.locator('#chat-messages').evaluate(n=>n.scrollTop),300);
    Object.assign(chats.get('chat-1').at(-1),{status:'pending',error:null});
    busy={chat:'chat-1',turn:'turn-2'};
    await page.waitForFunction(()=>document.getElementById('chat-notice').textContent==='正在等待模型完整回答…');
    assert.equal(await page.locator('#chat-messages').evaluate(n=>n.scrollTop),300);
    await complete('Synthetic latest long answer.\n\n'.repeat(160));
    await stableReadingPosition();
    assert.equal(await page.locator('#chat-messages').evaluate(n=>n.scrollTop),300,'completion never pulls an older reader to the bottom');
    for(const size of [{width:1440,height:1000},{width:800,height:700},{width:360,height:740},{width:640,height:480}]){
      await page.setViewportSize(size);
      await page.reload();await ready();await page.locator('#chat-history').selectOption('chat-1');
      await page.waitForFunction(()=>document.querySelectorAll('#chat-messages .chat-message').length===3);
      await stableReadingPosition();
      assert.ok(await page.locator('#chat-messages').evaluate(n=>{
        const viewport=n.getBoundingClientRect(),latest=n.lastElementChild;
        const question=latest.querySelector('.chat-user').getBoundingClientRect();
        const answer=latest.querySelector('.chat-answer').getBoundingClientRect();
        // offsetTop is integer-valued; DOMRect retains fractional CSS pixels.
        return question.top>=viewport.top-1&&question.bottom<=viewport.bottom+1&&answer.top<viewport.bottom;
      }),'latest long turn opens at its readable beginning: '+JSON.stringify(size));
      const bounds=await page.evaluate(()=>{
        const ids=['open-chat','open-workspace','chat-history','chat-new','chat-settings-open','chat-question','chat-source-open','chat-send'];
        return {overflow:document.documentElement.scrollWidth>innerWidth+1,clipped:ids.filter(id=>{const b=document.getElementById(id).getBoundingClientRect();return b.x<0||b.right>innerWidth+1||b.y<0||b.bottom>innerHeight+1;}),nested:[...document.querySelectorAll('#chat-messages *')].some(n=>/auto|scroll/.test(getComputedStyle(n).overflowY)&&n.scrollHeight>n.clientHeight)};
      });
      assert.deepEqual(bounds,{overflow:false,clipped:[],nested:false},JSON.stringify(size));
      await page.locator('#chat-settings-open').click();
      await page.locator('#chat-models-refresh').scrollIntoViewIfNeeded();
      assert.equal(await page.locator('#chat-models-refresh').isVisible(),true);await close();
    }
    assert.equal(await page.evaluate(()=>document.body.dataset.motion),'reduced');
    models=[];catalogFails=true;await page.reload();
    await page.waitForFunction(()=>document.getElementById('chat-notice').textContent.includes('catalog unavailable'));
    const failedCount=count('models');await page.waitForTimeout(1800);
    assert.equal(count('models'),failedCount);assert.equal(count('send'),4);
    assert.equal(await page.locator('#chat-send').isDisabled(),true);
    assert.equal(await page.locator('#chat-recover').isVisible(),true);
    catalogFails=false;
    await page.locator('#chat-recover').click();await ready();
    assert.equal(count('send'),4,'model recovery never sends the saved draft');
    credentialReady=false;
    await page.waitForFunction(()=>document.getElementById('chat-ready').textContent.includes('登入已失效'));
    assert.equal(await page.locator('#chat-signin-open').textContent(),'重新登入此帳戶');
    assert.equal(await page.locator('#chat-send').isDisabled(),true);
    const expiredCount=count('models');
    await page.waitForResponse(r=>r.url()===url+'/api/chat/state');
    assert.equal(count('models'),expiredCount,'an expired credential does not trigger repeated model requests');
    await page.locator('#chat-signin-open').click();await page.locator('#chat-login').click();await ready();await close();
    assert.equal(count('send'),4,'reauthorization never retries a message');
    await page.locator('#chat-history').selectOption('chat-1');
    await page.waitForFunction(()=>document.querySelectorAll('#chat-messages .chat-message').length===3);
    pending=true;
    await page.waitForFunction(()=>document.getElementById('chat-ready').textContent.includes('官方瀏覽器'));
    await page.waitForFunction(()=>!document.querySelector('#chat-messages .chat-message'));
    assert.equal(await page.locator('#chat-send').isDisabled(),true,'pending login clears readable history');
    assert.equal(await page.locator('#chat-sources input:checked').count(),0);
    pending=false;await ready();
    await page.locator('#chat-history').selectOption('chat-1');
    await page.waitForFunction(()=>document.querySelectorAll('#chat-messages .chat-message').length===3);
    const priorLogins=count('login');signedIn=false;await page.reload();
    await page.locator('#chat-signin').waitFor({state:'visible'});
    assert.equal(await page.locator('#chat-send').isDisabled(),true);assert.equal(count('login'),priorLogins);
    await page.locator('#chat-signin-open').click();
    assert.equal(await page.locator('#chat-login').evaluate(n=>n===document.activeElement),true);
    await page.locator('#chat-login').click();await ready();assert.equal(count('login'),priorLogins+1);
    assert.equal(count('send'),4);
    await close();
    // An A response already emitted by the server may arrive after local logout.
    // Clearing the identity must invalidate that response before it can render.
    let entered;
    const held=new Promise(resolve=>entered=resolve);
    getGate={enter:entered,wait:new Promise(resolve=>releaseGet=resolve)};
    await page.locator('#chat-history').selectOption('chat-1');await held;
    await page.locator('#chat-settings-open').click();await page.locator('#chat-logout').click();
    assert.equal(await page.locator('#chat-messages .chat-message').count(),0);
    releaseGet();await close();
    await page.locator('#chat-signin').waitFor({state:'visible'});
    assert.equal(await page.locator('#chat-messages .chat-message').count(),0,'late old-account response stays discarded');
    assert.deepEqual(errors,[]);
  }finally{releaseGet?.();if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
});
