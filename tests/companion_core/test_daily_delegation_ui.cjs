/* Real Windows Chrome, Companion HTTP/SQLite, and Win32 outputs. SIWC and E1 are synthetic. */
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process'),{createInterface}=require('node:readline');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');

test('local delegation and E1 delivery continue in the original conversation',async()=>{
  const root=fs.mkdtempSync(path.join(process.env.DD_EVIDENCE_DIR||os.tmpdir(),'daily-delegation-ui-'));
  const repo=path.resolve(__dirname,'../..');
  const fixture=path.join(__dirname,'test_daily_delegation.py');
  let host,browser,page;
  const errors=[],posts=[],sent=[];
  async function start(){
    const processHandle=spawn(process.env.PYTHON||'python',['-B',fixture,root],{
      cwd:repo, windowsHide:true, env:{...process.env,PYTHONPATH:repo,PYTHONUTF8:'1'}
    });
    const lines=createInterface({input:processHandle.stdout});
    let stderr='';
    processHandle.stderr.on('data',value=>{stderr+=value;});
    try{
      const meta=await new Promise((resolve,reject)=>{
        lines.once('line',line=>{try{resolve(JSON.parse(line));}catch(e){reject(e);}});
        processHandle.once('error',reject);
        processHandle.once('exit',()=>reject(Error(stderr)));
      });
      return {...meta,processHandle};
    }catch(e){processHandle.stdin.end();throw e;}
  }
  async function stop(item){
    if(!item||item.processHandle.exitCode!==null)return;
    const closed=new Promise(resolve=>item.processHandle.once('exit',resolve));
    item.processHandle.stdin.end();
    await closed;
  }
  async function open(){
    const p=await browser.newPage({viewport:{width:1280,height:850},locale:'zh-TW'});
    p.setDefaultTimeout(12000);
    p.on('pageerror',e=>errors.push(e.message));
    p.on('request',r=>{
      if(r.method()!=='POST')return;
      const route=new URL(r.url()).pathname;
      posts.push(route);
      if(route==='/api/chat/send')sent.push(r.postDataJSON());
    });
    await p.goto(host.url+'/#chat?chat='+host.chat);
    await p.locator('#chat-history').selectOption(host.chat);
    return p;
  }
  async function say(question){
    const count=await page.locator('[data-daily-work]').count();
    await page.locator('#chat-question').fill(question);
    await page.locator('#chat-send').click();
    await page.waitForFunction(n=>document.querySelectorAll('[data-daily-work]').length===n+1,count);
    return page.locator('[data-daily-work]').last();
  }
  function waitText(locator, fragment){
    return locator.getByText(fragment,{exact:false}).first().waitFor();
  }
  const calls=action=>posts.filter(route=>route==='/api/chat/'+action).length;
  try{
    host=await start();
    browser=await chromium.launch({channel:'chrome',headless:true,args:['--disable-gpu']});
    page=await open();
    const list=await say('請列出已保存成果。');
    await list.getByRole('button',{name:host.saved,exact:true}).click();
    await waitText(list,'actual fixture bytes');
    assert.equal(await page.locator('#outputs-panel').isVisible(),false);
    const inspected=await say('檢視「'+host.saved+'」');
    await waitText(inspected,'actual fixture bytes');
    const pre=await say('預覽回答 '+host.answer+' 的 Markdown');
    await pre.getByRole('button',{name:'確認寫入 Markdown'}).waitFor();
    assert.equal(await page.locator('#outputs-panel').isVisible(),false);
    assert.equal(fs.readdirSync(path.join(root,'outputs')).length,1);
    await page.close();await stop(host);host=await start();page=await open();
    await waitText(page.locator('[data-daily-work]').last(),'寫入確認已失效');
    await page.locator('[data-daily-work]').last().getByRole('button',{name:'準備 Markdown 預覽'}).click();
    await page.locator('[data-daily-work]').last().getByRole('button',{name:'取消寫入'}).click();
    await waitText(page.locator('[data-daily-work]').last(),'已取消');
    assert.equal(fs.readdirSync(path.join(root,'outputs')).length,1);
    const localSendCount=calls('send');
    const deliveryOption=page.getByRole('checkbox',{name:/回答完成後準備 Markdown 預覽/});
    await page.locator('#chat-question').fill(host.question);
    await page.locator('#web-open').click();
    await page.locator('#web-fetch').waitFor();
    assert.equal(await deliveryOption.isVisible(),false);
    assert.equal(calls('web-fetch'),0);
    assert.equal(calls('send'),localSendCount);
    await page.locator('#web-fetch').click();
    await deliveryOption.waitFor();
    assert.equal(await deliveryOption.isChecked(),false);
    assert.equal(calls('web-fetch'),1);
    await deliveryOption.check();
    await page.locator('#chat-form').evaluate(form=>form.requestSubmit());
    await page.locator('#web-cancel').click();
    await page.locator('#web-panel').waitFor({state:'hidden'});
    assert.equal(await page.locator('#chat-question').inputValue(),host.question);
    assert.equal(calls('send'),localSendCount);
    await page.locator('#web-open').click();
    await page.locator('#web-fetch').click();
    await deliveryOption.waitFor();
    assert.equal(await deliveryOption.isChecked(),false);
    await page.setViewportSize({width:390,height:450});
    assert.equal(await page.locator('#web-share').evaluate(button=>button.getBoundingClientRect().bottom<=innerHeight),true);
    await deliveryOption.check();
    await page.setViewportSize({width:1280,height:850});
    await page.screenshot({path:path.join(root,'e1-share-pending-explicit-preview.png')});
    assert.equal(calls('web-fetch'),2);
    assert.equal(calls('send'),localSendCount);
    await page.locator('#web-share').click();
    const delivery=page.locator('[data-daily-work]').last();
    await delivery.getByRole('button',{name:'確認寫入 Markdown'}).waitFor();
    assert.equal(calls('send'),localSendCount+1);
    assert.equal(sent.at(-1).question,host.question);
    assert.equal(sent.at(-1).web_markdown_preview,true);
    assert.equal(calls('outputs-preview'),0);
    assert.equal(fs.readdirSync(path.join(root,'outputs')).length,1);
    assert.match(await delivery.innerText(),/Windows fixture \[S1:L1\]/);
    await waitText(page.locator('#chat-ready'),'可以開始聊天');
    await delivery.getByRole('button',{name:'確認寫入 Markdown'}).scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(root,'e1-to-markdown-confirmation.png')});
    await delivery.getByRole('button',{name:'確認寫入 Markdown'}).click();
    await delivery.getByRole('button',{name:'查驗磁碟成果'}).click();
    await waitText(delivery,'磁碟內容與工作預覽相符。');
    const results=fs.readdirSync(path.join(root,'outputs'));
    assert.equal(results.length,2);
    const written=results.find(n=>n!==host.saved);
    assert.equal(fs.readFileSync(path.join(root,'outputs',written),'utf8'),'Windows fixture [S1:L1]\n');
    await page.reload();
    await page.locator('#chat-history').selectOption(host.chat);
    await waitText(page.locator('[data-daily-work]').last(),'已核對保存');
    await waitText(page.locator('[data-daily-work]').last(),'磁碟內容與工作預覽相符。');
    assert.equal(await page.locator('#chat-history').inputValue(),host.chat);
    await page.locator('[data-daily-work]').last().getByText('磁碟內容與工作預覽相符。').scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(root,'reopened-save-and-readback.png')});
    assert.deepEqual(errors,[]);
    console.log('Windows UI evidence: '+root);
  }finally{await browser?.close();await stop(host);}
});

