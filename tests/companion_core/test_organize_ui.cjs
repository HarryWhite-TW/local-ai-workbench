/* DOM contract tests: transport is stubbed; real-browser evidence is separate. */
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
class Node {
  constructor(tag){this.tag=tag;this.children=[];this.textContent='';this.dataset={};this.value='';this.files=[];this.disabled=false;this.hidden=false;this.open=false;this.clicks=0;}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;}
  setAttribute(k,v){this[k]=v;}
  focus(){}
  click(){this.clicks++;}
  addEventListener(){}
  remove(){}
}
const bytes=Buffer.from('real ZIP bytes for hash contract');
const hash=crypto.createHash('sha256').update(bytes).digest('hex');
const preview={id:'job',chat:'chat',turn:'turn',state:'PREVIEW',label:'Preview',documents:[{name:'a.txt'}],approval:'bound-token',
  plan:[{id:'D1',name:'a.txt',category:'Study',reason:'<img src=x onerror=alert(1)>',evidence:'actual quotation',destination:'Study/D1-a.txt'}]};
const complete={...preview,state:'COMPLETED',output_sha256:hash};
const archive={name:'copies.zip',content:bytes.toString('base64'),sha256:hash};
function setup(handler=async action=>action==='confirm'?complete:archive){
  const elements=new Map(),listeners={},calls=[],created=[];
  const document={getElementById:id=>{if(!elements.has(id))elements.set(id,new Node('div'));return elements.get(id);},
    createElement:tag=>{const n=new Node(tag);created.push(n);return n;},addEventListener:(name,fn)=>{listeners[name]=fn;}};
  const window={},context={window,document,console,Uint8Array,Blob,
    URL:{createObjectURL:()=> 'blob:verified-copy',revokeObjectURL:()=>{}},setTimeout:()=>{},
    crypto:crypto.webcrypto,atob,btoa,
    fetch:async(url,options)=>{const body=JSON.parse(options.body);calls.push({url,body});return {ok:true,json:async()=>handler(url.split('organize-')[1],body)};}};
  vm.runInNewContext(fs.readFileSync(path.resolve(__dirname,'../../src/companion_core/static/organize.js'),'utf8'),context);
  listeners.DOMContentLoaded();return {ui:window.NexusOrganize,document,calls,created,e:id=>document.getElementById(id)};
}
function all(n){return [n,...n.children.flatMap(c=>typeof c==='object'?all(c):[])];}
function button(n,label){return all(n).find(x=>x.tag==='button'&&x.textContent===label);}
function selection(s,valid=()=>true,started=()=>{}){
  s.ui.open({account:'owner',workspace:'workspace',chat:null,valid,started});
  s.e('chat-question').value='Classify by content';
  const raw=new Uint8Array([65,66,67,10]);
  s.e('organize-files').files=[{name:'a.txt',size:raw.length,arrayBuffer:async()=>raw.buffer}];s.e('organize-files').onchange();
}

test('summary defaults to collapsed evidence; explicit confirmation downloads only after approval',async()=>{
  const {ui,calls,created}=setup();let refreshed=0;
  const card=ui.card(preview,()=>refreshed++,()=>true);
  assert.equal(calls.length,0);assert.ok(all(card).some(n=>n.textContent===preview.plan[0].reason));
  assert.ok(all(card).every(n=>n.tag!=='img'));assert.equal(all(card).find(n=>n.tag==='details').open,false);
  await button(card,'確認並下載 ZIP').onclick();
  assert.deepEqual(calls,[{url:'/api/chat/organize-confirm',body:{id:'job',approval:'bound-token'}},{url:'/api/chat/organize-download',body:{id:'job'}}]);
  assert.equal(created.find(n=>n.tag==='a').clicks,1);assert.equal(refreshed,1);
});

test('rejected confirmation never downloads or offers a ZIP',async()=>{
  const {ui,calls,created}=setup(async()=>{throw Error('Approval expired');});
  const card=ui.card(preview,()=>assert.fail(),()=>true);await button(card,'確認並下載 ZIP').onclick();
  assert.equal(calls.length,1);assert.equal(created.filter(n=>n.tag==='a').length,0);
  assert.ok(all(card).some(n=>n.textContent==='Approval expired'));
});

test('failed automatic download preserves saved result and manual retry does not reconfirm',async()=>{
  let failed=true;const s=setup(async action=>{if(action==='confirm')return complete;if(failed)throw Error('Network unavailable');return archive;});
  const first=s.ui.card(preview,()=>{},()=>true);await button(first,'確認並下載 ZIP').onclick();
  const saved=s.ui.card(complete,()=>{},()=>true);
  assert.ok(all(saved).some(n=>n.textContent.includes('副本已保存，但下載未完成')));
  failed=false;await button(saved,'下載 ZIP').onclick();
  assert.equal(s.calls.filter(c=>c.url.endsWith('confirm')).length,1);
  assert.equal(s.calls.filter(c=>c.url.endsWith('download')).length,2);
  assert.equal(s.created.filter(n=>n.tag==='a'&&n.clicks===1).length,1);
});

test('saved result render does not automatically download again',()=>{
  const {ui,calls}=setup();const card=ui.card(complete,()=>{},()=>true);
  assert.equal(calls.length,0);assert.ok(button(card,'下載 ZIP'));assert.equal(button(card,'確認並下載 ZIP'),undefined);
});

test('wrong download identity never creates a download link',async()=>{
  const s=setup(async action=>action==='confirm'?complete:{...archive,content:Buffer.from('corrupt').toString('base64')});
  const card=s.ui.card(preview,()=>{},()=>true);await button(card,'確認並下載 ZIP').onclick();
  assert.equal(s.created.filter(n=>n.tag==='a').length,0);assert.ok(all(card).some(n=>n.textContent.includes('下載內容身分不符')));
});

test('changing account during confirmation prevents subsequent download',async()=>{
  let valid=true,release;const pending=new Promise(resolve=>release=resolve);
  const s=setup(()=>pending),card=s.ui.card(preview,()=>assert.fail(),()=>valid);
  const task=button(card,'確認並下載 ZIP').onclick();valid=false;release(complete);await task;
  assert.equal(s.calls.length,1);assert.equal(s.created.filter(n=>n.tag==='a').length,0);
});

test('duplicate activation across rerendered cards cannot duplicate confirmation',async()=>{
  let release;const pending=new Promise(resolve=>release=resolve);const s=setup(action=>action==='confirm'?pending:archive);
  const a=s.ui.card(preview,()=>{},()=>true);const task=button(a,'確認並下載 ZIP').onclick();
  const b=s.ui.card(preview,()=>{},()=>true);assert.equal(button(b,'確認並下載 ZIP').disabled,true);
  await button(b,'確認並下載 ZIP').onclick();release(complete);await task;
  assert.equal(s.calls.filter(c=>c.url.endsWith('confirm')).length,1);
});

test('unknown, failed and stale-account cards cannot produce copies',async()=>{
  const {ui,calls}=setup();
  const unknown=ui.card({...preview,state:'UNKNOWN',plan:null,thread_id:'thread',turn_id:'turn'},()=>{},()=>false);
  await button(unknown,'核對分析結果').onclick();assert.equal(calls.length,0);
  const missing=ui.card({...preview,state:'UNKNOWN',plan:null,thread_id:null,turn_id:null},()=>{},()=>true);
  assert.equal(all(missing).filter(n=>n.tag==='button').length,0);
  const failed=ui.card({...preview,state:'FAILED',plan:null,error:'No model result'},()=>{},()=>true);
  assert.equal(all(failed).filter(n=>n.tag==='button').length,0);
});

test('inline selection never shares before start; submission uses the current shared composer and exact bytes',async()=>{
  const s=setup(async()=>({chat:'new-chat',id:'job'}));let started=null;selection(s,()=>true,r=>{started=r;});
  assert.equal(s.ui.active(),true);assert.equal(s.e('organize-panel').hidden,false);assert.equal(s.e('organize-files').clicks,1);
  assert.equal(s.calls.length,0);s.e('chat-question').value='Updated shared request';
  await s.ui.submit();assert.equal(s.calls.length,1);const body=s.calls[0].body;
  assert.equal(body.question,'Updated shared request');assert.equal(body.account,'owner');assert.equal(body.workspace,'workspace');
  assert.deepEqual(body.files,[{name:'a.txt',content:'QUJDCg=='}]);assert.equal(started.chat,'new-chat');assert.equal(s.ui.active(),false);assert.equal(s.e('organize-panel').hidden,true);
});

test('blank composer has explicit content-classification default',async()=>{
  const s=setup(async()=>({id:'job',chat:'new-chat'}));selection(s);s.e('chat-question').value='';await s.ui.submit();
  assert.match(s.calls[0].body.question,/依文件實際內容分類/);
});

test('changing conversation while file bytes load prevents upload',async()=>{
  const s=setup();let release;const pending=new Promise(resolve=>release=resolve);selection(s,()=>true,()=>assert.fail());
  s.e('organize-files').files=[{name:'a.txt',size:1,arrayBuffer:()=>pending}];
  const task=s.ui.submit();s.ui.reset();release(new Uint8Array([65]).buffer);await task;assert.equal(s.calls.length,0);
});
