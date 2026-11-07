/* Real auth UI handler, synthetic API only; no browser or credentials. */
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../../src/companion_core/static/chat.js'),'utf8');
const start=source.indexOf('  async function changeAccount('),end=source.indexOf('  async function loadModels(',start);
assert.ok(start>=0&&end>start);
function setup(api){
  const calls=[],notice={textContent:''};
  const c=vm.createContext({authChanging:false,authPreparing:false,authActionError:'',catalogError:'',state:{continuity:false},
    connected:true,selected:'saved-chat',draft:'keep my draft',body:null,window:{NexusConversation:{resetContext(){calls.push('reset');}}},
    updateSend(){},saveDraft(){},api,el:()=>notice,notice(){},
    invalidateAccount(){calls.push('invalidate');c.selected='';c.draft='';},
    async refresh(){calls.push('refresh');c.connected=true;vm.runInContext("el('chat-auth-notice').textContent=authActionError||catalogError||data.auth.notice;",c);},
    data:{auth:{notice:'Old backend notice'}}});
  vm.runInContext(source.slice(start,end),c);
  return {c,calls,notice};
}
test('rejected login preserves conversation/draft and persists the error across refreshes',async()=>{
  const e=setup(async()=>{throw Error('Browser could not open');});
  await e.c.changeAccount('login',{account:'owner'});
  assert.deepEqual(e.calls,['refresh']);assert.equal(e.c.selected,'saved-chat');assert.equal(e.c.draft,'keep my draft');
  assert.equal(e.notice.textContent,'Browser could not open');await e.c.refresh();assert.equal(e.notice.textContent,'Browser could not open');
  assert.equal(e.c.authChanging,false);assert.equal(e.c.connected,true);
});
test('account context is invalidated only after the login API succeeds',async()=>{
  let release;const e=setup(()=>new Promise(resolve=>{release=resolve;}));
  e.c.authActionError='old error';const pending=e.c.changeAccount('login',{account:'owner'});
  assert.equal(e.c.authChanging,true);assert.equal(e.c.authActionError,'');assert.equal(e.c.selected,'saved-chat');assert.deepEqual(e.calls,[]);
  release({pending:true});await pending;
  assert.deepEqual(e.calls,['invalidate','refresh']);assert.equal(e.c.authChanging,false);
});
test('periodic auth feedback retains model-load failure and can show official-login waiting state',()=>{
  assert.ok(source.includes("el('chat-auth-notice').textContent=authActionError||catalogError||data.auth.notice;"));
  const e=setup(async()=>{});e.c.catalogError='Login expired';e.c.refresh();assert.equal(e.notice.textContent,'Login expired');
  e.c.catalogError='';e.c.data.auth.notice='Please complete official sign in';e.c.refresh();assert.equal(e.notice.textContent,'Please complete official sign in');
});
