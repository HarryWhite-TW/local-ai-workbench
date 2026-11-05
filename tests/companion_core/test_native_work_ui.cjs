const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../../src/companion_core/static/chat.js'),'utf8');
const cardSource=source.slice(source.indexOf('  function workCard(p)'),source.indexOf('  function editProposal(p)'));
class Element {
  constructor(tag,value=''){this.tag=tag;this.textContent=value;this.children=[];this.dataset={};this.value='';}
  append(...nodes){this.children.push(...nodes);}
  setAttribute(k,v){this[k]=v;}
  querySelector(selector){return all(this).find(n=>selector==='[data-native-result]'&&n.dataset.nativeResult)||null;}
}
function all(node){return [node,...node.children.flatMap(n=>all(n))];}
function setup(){
  const calls=[],edits=[],notices=[];
  const c=vm.createContext({
    text:(tag,value)=>new Element(tag,value),document:{createElement:tag=>new Element(tag)},
    state:{auth:{active:'owner',pending:false}},selected:'chat',workspace:'workspace',authChanging:false,rendered:'',reconcileFeedback:new Map(),nativeResults:new Map(),nativeLoading:new Map(),
    api:async(operation,body)=>{calls.push({operation,body});return operation==='work-result'?{task_id:'task',result_id:'receipt',result:'<img src=x onerror=alert(1)>'}:{id:'child'};},
    refresh:async()=>{},notice:message=>notices.push(message),editProposal:p=>edits.push(p),
    attachResult(){},action:fn=>fn(),window:{CompanionReading:{markdown:(node,value)=>node.textContent=value}},showSpace(){},
  });
  vm.runInContext(cardSource,c);
  const p={id:'proposal',chat:'chat',task_id:'task',goal:'Diagnose',state:'RUNNING',kind:'native_codex',
    review_status:'PENDING_REVIEW',technical_acceptance:'PENDING_REVIEW',capability:'Selected snapshots only',
    thread_id:'thread',turn_id:'turn',candidate_id:'digest',events:[{kind:'turn_bound',at:'time'}]};
  return {c,p,calls,edits,notices,card:()=>c.workCard(p)};
}
const button=(card,label)=>all(card).find(n=>n.tag==='button'&&n.textContent===label);
test('inline native stop and unknown reconciliation bind the exact proposal',async()=>{
  const e=setup();let card=e.card();
  await button(card,'停止這項診斷').onclick();
  assert.deepEqual(JSON.parse(JSON.stringify(e.calls)),[{operation:'work-stop',body:{id:'proposal'}}]);
  e.p.state='UNKNOWN';card=e.card();
  assert.equal(button(card,'停止這項診斷'),undefined);
  await button(card,'讀取原生狀態對帳').onclick();
  assert.equal(e.calls.at(-1).operation,'work-reconcile');
  assert.ok(all(card).some(n=>n.textContent.includes('PENDING_REVIEW')));
  assert.ok(all(card).some(n=>n.textContent.includes('Thread: thread / Turn: turn')));
});
test('native result is text only and a delayed cross-account result is withheld',async()=>{
  const e=setup();e.p.state='RESULT_PENDING_REVIEW';e.p.result_id='receipt';
  let card=e.card();await button(card,'在此讀取診斷結果').onclick();
  const saved=e.c.nativeResults.get(e.c.nativeResultKey(e.p));assert.equal(saved.data.result,'<img src=x onerror=alert(1)>');card=e.card();assert.equal(card.querySelector('[data-native-result]').textContent,'<img src=x onerror=alert(1)>');assert.ok(all(card).every(n=>n.tag!=='img'));
  e.c.nativeResults.clear();card=e.card();e.c.api=async()=>{e.c.state.auth.active='other';return {result:'MUST NOT SHOW'};};
  await button(card,'在此讀取診斷結果').onclick();
  assert.equal(card.querySelector('[data-native-result]'),null);
});
test('one revision creates a proposal and opens preview without starting execution',async()=>{
  const e=setup();e.p.state='RESULT_PENDING_REVIEW';e.p.result_id='receipt';e.p.can_revise=true;
  const card=e.card(),feedback=all(card).find(n=>n.tag==='textarea');
  feedback.value='Review the missing edge';
  await button(card,'預覽一次後續修正').onclick();
  assert.equal(e.calls.length,1);assert.equal(e.calls[0].operation,'work-revise');
  assert.equal(e.calls[0].body.id,'proposal');assert.equal(e.edits[0].id,'child');
  assert.equal(e.calls.some(c=>c.operation==='work-confirm'),false);
});

test('first-use RPC rejection shows the stage and keeps UNKNOWN work unhideable',()=>{
  const e=setup();e.p.state='FAILED';
  Object.assign(e.p,{failure_stage:'turn/start',failure_code:-32602,start_outcome:'REJECTED',failure_summary:'Codex 明確拒絕啟動參數。'});
  let card=e.card();
  assert.ok(all(card).some(n=>n.textContent.includes('turn/start')&&n.textContent.includes('-32602')));
  assert.ok(all(card).some(n=>n.textContent.includes('沒有自動重送')));
  e.p.state='UNKNOWN';e.p.draft_hidden=true;e.p.can_hide_draft=true;card=e.card();
  assert.equal(button(card,'收起未執行草稿'),undefined);
  assert.equal(button(card,'展開並繼續草稿'),undefined);
  assert.ok(button(card,'讀取原生狀態對帳'));
});
test('first-use unused drafts fold/restore with explicit actions only',async()=>{
  const e=setup();Object.assign(e.p,{task_id:null,state:'AWAITING_AUTHORIZATION',can_hide_draft:true});
  let card=e.card();
  assert.ok(button(card,'設定並預覽診斷'));
  await button(card,'收起未執行草稿').onclick();
  assert.equal(e.calls[0].operation,'work-draft-visibility');assert.equal(e.calls[0].body.hidden,true);
  e.p.draft_hidden=true;card=e.card();
  assert.equal(button(card,'設定並預覽診斷'),undefined);
  await button(card,'展開並繼續草稿').onclick();
  assert.equal(e.calls.at(-1).body.hidden,false);
  assert.equal(e.calls.some(c=>c.operation==='work-confirm'),false);
});
test('first-use prior reconcile feedback remains visible when identity is incomplete',async()=>{
  const e=setup();e.p.state='UNKNOWN';
  e.c.api=async()=>({state:'UNKNOWN',thread_id:'thread',turn_id:null});
  const card=e.card();await button(card,'讀取原生狀態對帳').onclick();
  assert.ok(all(card).some(n=>n.textContent.includes('沒有重新執行工作')));
  assert.ok(all(card).some(n=>n.role==='status'&&!n.hidden));
});
test('first-use discussion entry reuses bound work and suppresses double clicks',async()=>{
  const e=setup();const start=source.indexOf("      if(workEnabled&&turn.status==='complete'&&!organizations.some(o=>o.turn===turn.id)) {");
  const end=source.indexOf('      for(const p of proposals.filter',start);assert.ok(start>=0&&end>start);
  e.c.workEnabled=true;e.c.id='chat';e.c.turn={id:'turn',status:'complete'};
  e.c.organizations=[];e.c.proposals=[{...e.p,turn:'turn',state:'UNKNOWN'}];
  e.c.read=async()=>{};e.c.el=()=>new Element('div');
  vm.runInContext("function turnEntry(){const answer=text('div','');"+source.slice(start,end)+"return answer;}",e.c);
  const card=e.c.turnEntry(),b=button(card,'查看這次診斷');
  assert.ok(b);
  let release;
  e.c.api=async(operation,body)=>{e.calls.push({operation,body});return new Promise(resolve=>{release=resolve;});};
  const first=b.onclick();await b.onclick();assert.equal(e.calls.length,1);
  release({...e.p,turn:'turn',state:'UNKNOWN'});await first;
  assert.equal(e.edits.length,0);assert.equal(e.calls[0].operation,'work-create');
  assert.equal(e.calls.some(c=>c.operation==='work-confirm'),false);
});


test('automatic saved result readback is owner-scoped, identity checked and cached',async()=>{
  const e=setup();e.p.result_id='receipt';
  await e.c.loadNativeResult(e.p);await e.c.loadNativeResult(e.p);
  assert.equal(e.calls.length,1);assert.ok(e.c.nativeResults.get(e.c.nativeResultKey(e.p)).data);
  e.c.nativeResults.clear();e.c.api=async()=>({task_id:'other-task',result_id:'receipt',result:'WRONG WORK'});
  await e.c.loadNativeResult(e.p);assert.equal(e.c.nativeResults.get(e.c.nativeResultKey(e.p)).data,undefined);
  assert.ok(e.c.nativeResults.get(e.c.nativeResultKey(e.p)).error.includes('身分未確認'));
});

test('result summaries and full raw evidence are display-only, with no automatic review or model request',()=>{
  const e=setup();Object.assign(e.p,{result_id:'receipt',state:'RESULT_PENDING_REVIEW'});
  e.c.nativeResults.set(e.c.nativeResultKey(e.p),{data:{result:'Full original report',presentation:{overview:'Conclusion',evidence:'file.py L3',next_steps:'Check boundary'}}});
  const card=e.card();assert.ok(all(card).some(n=>n.textContent==='Conclusion'));assert.ok(all(card).some(n=>n.textContent==='file.py L3'));
  assert.equal(card.querySelector('[data-native-result]').textContent,'Full original report');assert.equal(e.calls.length,0);
  assert.ok(all(card).some(n=>n.textContent.includes('尚待獨立技術審查')));
});

test('an unstarted draft keeps its setup action outside collapsed technical details',()=>{
  const e=setup();Object.assign(e.p,{task_id:null,state:'AWAITING_AUTHORIZATION'});
  const card=e.card();assert.ok(card.children.includes(button(card,'設定並預覽診斷')));
});

test('UX-02 layout comparison cannot persist private drafts or overwrite host continuity',async()=>{
  const sections=[['  function writeTab() {','  function saveStatus() {'],
    ['  async function flushContinuity(','  function persistChat() {'],
    ['  function persistChat() {','  function saveDraft() {']];
  const c=vm.createContext({window:{nexusComparisonLayout:true},
    api:()=>assert.fail('comparison must not call a persistence API'),
    sessionStorage:{setItem:()=>assert.fail('comparison must not store draft text')}});
  for(const [start,end]of sections){const a=source.indexOf(start),b=source.indexOf(end,a);assert.ok(a>=0&&b>a);vm.runInContext(source.slice(a,b),c);}
  c.writeTab();c.persistChat();assert.equal(await c.flushContinuity(),true);
});
