/* Local Chrome and synthetic routes. No external page or model is contacted. */
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const assets=path.resolve(__dirname,'../../src/companion_core/static');
const url='https://docs.python.org/3.10/library/asyncio-platforms.html';

test('E1 draft, fetch approval, plain preview, share approval and saved citation',async()=>{
  const calls=[],turns=[];
  const excerpt=['Windows <img src="x"> fixture',...Array.from({length:92},(_, i)=>
    'Windows platform documentation, example line '+(i+2)+' with text for the preview.')].join('\n');
  const source={id:'S1',key:'web:fixture',name:'Python docs fixture',url,text:excerpt,
    sha256:'excerpt-hash',response_sha256:'response-hash',captured_at:'2026-01-01T00:00:00Z'};
  const server=http.createServer(async(req,res)=>{
    let raw='';
    for await(const part of req)raw+=part;
    const body=raw?JSON.parse(raw):null;
    const reply=value=>{res.setHeader('Content-Type','application/json');res.end(JSON.stringify(value));};
    const route=req.url;
    if(route==='/api/state')return reply({runtime:'synthetic',tasks:[],progress:[]});
    if(route==='/api/chat/state')return reply({
      auth:{active:'fixture',accounts:[{id:'fixture',label:'Fixture',signed_in:true}],pending:false},
      models:[{slug:'fixture',display_name:'Fixture'}],busy:null,
      chats:[{id:'original',account:'fixture',title:'Existing conversation'}],sources:[],
    });
    if(route==='/api/chat/get')return reply({id:'original',turns});
    if(route==='/api/chat/project-get')return reply({project:null});
    if(route.startsWith('/api/chat/'))calls.push({route,body});
    if(route==='/api/chat/web-preview')return reply({url,ticket:'fixture-ticket'});
    if(route==='/api/chat/web-fetch')return reply(source);
    if(route==='/api/chat/web-cancel')return reply({});
    if(route==='/api/chat/send'){
      turns.push({id:'turn',created:source.captured_at,model:'Fixture',question:body.question,
        answer:'Windows example [S1:L1-L2]',sources:[source],status:'complete'});
      return reply({chat:'original',turn:'turn'});
    }
    const name=route==='/'?'index.html':route.slice(1), file=path.join(assets,name);
    if(!fs.existsSync(file)){res.writeHead(404);res.end();return;}
    if(name==='index.html'){
      res.setHeader('Content-Type','text/html; charset=utf-8');
      return res.end(fs.readFileSync(file,'utf8').replace('data-chat-enabled="false"','data-chat-enabled="true"')
        .replace('data-web-enabled="false"','data-web-enabled="true"'));
    }
    res.setHeader('Content-Type',name.endsWith('.css')?'text/css':'text/javascript');
    res.end(fs.readFileSync(file));
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  let browser;
  try{
    browser=await chromium.launch({channel:'chrome',headless:true});
    const page=await browser.newPage({viewport:{width:1024,height:600}});
    const base='http://127.0.0.1:'+server.address().port;
    const times=route=>calls.filter(c=>c.route==='/api/chat/'+route).length;
    await page.goto(base+'/#chat?chat=original');
    await page.locator('#chat-history').selectOption('original');
    await page.locator('#web-open').click();
    assert.match(await page.locator('#web-status').textContent(),/指定一個/);
    await page.keyboard.press('Escape');
    await page.locator('#web-panel').waitFor({state:'hidden'});
    await page.locator('#chat-question').fill('What are the Windows limitations? '+url);
    await page.locator('#web-open').click();
    await page.locator('#web-fetch').waitFor();
    assert.equal(times('web-fetch'),0);
    assert.equal(times('send'),0);
    await page.locator('#web-fetch').click();
    await page.locator('#web-share').waitFor();
    assert.equal(await page.locator('#web-preview img').count(),0);
    assert.match(await page.locator('#web-preview pre').textContent(),/L1: Windows <img/);
    const scroll=page.locator('#web-scroll');
    const footerInView=()=>page.evaluate(()=>{
      return ['web-cancel','web-share'].every(id=>{
        const rect=document.getElementById(id).getBoundingClientRect();
        return rect.top>=0&&rect.bottom<=innerHeight;
      });
    });
    assert.equal(await footerInView(),true);
    await scroll.hover();
    await page.mouse.wheel(0,520);
    await page.waitForFunction(()=>document.getElementById('web-scroll').scrollTop>0);
    assert.equal(await footerInView(),true);
    await page.locator('#web-excerpt summary').click();
    assert.equal(await page.locator('#web-excerpt').evaluate(el=>el.open),false);
    await page.locator('#web-excerpt summary').click();
    await page.setViewportSize({width:390,height:450});
    assert.equal(await footerInView(),true);
    await page.setViewportSize({width:1024,height:600});
    assert.equal(times('send'),0);
    await page.locator('#web-cancel').click();
    await page.waitForFunction(()=>document.getElementById('web-share').hidden);
    assert.equal(times('send'),0);
    await page.locator('#web-open').click();
    await page.locator('#web-fetch').click();
    await page.locator('#web-share').click();
    await page.getByText('Windows example [S1:L1-L2]',{exact:true}).waitFor();
    await page.getByText('核對這一輪的來源快照',{exact:true}).click();
    assert.match(await page.locator('#chat-source-records pre').textContent(),/L1: Windows/);
    assert.equal(times('web-fetch'),2);
    assert.equal(times('send'),1);
    const sent=calls.find(c=>c.route==='/api/chat/send').body;
    assert.equal(sent.chat,'original');
    assert.deepEqual(sent.sources,['web:fixture']);
    assert.deepEqual(sent.preview,{'web:fixture':'excerpt-hash'});
  }finally{
    await browser?.close();
    await new Promise(resolve=>server.close(resolve));
  }
});
