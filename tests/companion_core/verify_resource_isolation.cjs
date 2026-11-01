/* Latest production HTTP handlers on fresh loopback ports, isolated SQLite and
 * synthetic accounts. Concurrent callback changes use stdin-only fixture hooks.
 * node verify_resource_isolation.cjs <output>; no existing process is contacted.
 */
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {spawn,spawnSync}=require('child_process'),readline=require('readline'),{createHash}=require('crypto');
const out=path.resolve(process.argv[2]||fs.mkdtempSync(path.join(require('os').tmpdir(),'resource-isolation-')));
fs.mkdirSync(out,{recursive:true});
const root=path.resolve(__dirname,'../..'),python=process.env.PYTHON||'python',sessions=[],checks=[],races=[];
const started=performance.now(),sha=b=>createHash('sha256').update(b).digest('hex');
const check=(name,passed)=>{checks.push({name,passed:!!passed});assert.ok(passed,name);};
const account='synthetic-test-account',other='synthetic-other-account';
async function fixture(workspace){
 const child=spawn(python,['-B',path.join(__dirname,'conversation_work_fixture.py'),out,workspace,'--resources-proof'],{cwd:root,windowsHide:true,env:{...process.env,PYTHONUTF8:'1'}});
 let stderr='';child.stderr.on('data',s=>stderr+=s);
 const lines=readline.createInterface({input:child.stdout});
 const ready=await new Promise((resolve,reject)=>{lines.once('line',s=>resolve(JSON.parse(s)));child.once('error',reject);child.once('exit',()=>reject(Error(stderr)));});
 const send=command=>new Promise((resolve,reject)=>{lines.once('line',s=>{try{resolve(JSON.parse(s));}catch(e){reject(e);}});child.stdin.write(JSON.stringify(command)+'\n');});
 const session={child,ready,send,workspace};sessions.push(session);return session;
}
async function post(s,action,body){
 const response=await fetch(s.ready.url+'/api/chat/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Companion-UI':'1','Origin':s.ready.url},body:JSON.stringify(body),signal:AbortSignal.timeout(12000)});
 return {status:response.status,data:await response.json()};
}
const call=async(s,action,body)=>{const r=await post(s,action,body);assert.equal(r.status,200,JSON.stringify(r.data));return r.data;};
(async()=>{
 let failure;
 try{
  const source=path.join(root,'src/companion_core/resources.py'),sourceSHA=sha(fs.readFileSync(source));
  // Canonicalize code values rather than marshal's process-dependent intern flags.
  const code=`import hashlib,json,types
from src.companion_core.resources import ProjectResources
def identity(v):
 if isinstance(v,types.CodeType):return [v.co_code.hex(),[identity(c) for c in v.co_consts],v.co_names,v.co_varnames,v.co_freevars,v.co_cellvars,v.co_argcount,v.co_kwonlyargcount,v.co_posonlyargcount,v.co_flags]
 if isinstance(v,(set,frozenset)):return sorted([identity(c) for c in v],key=json.dumps)
 if isinstance(v,tuple):return [identity(c) for c in v]
 return repr(v)
print(json.dumps({n:hashlib.sha256(json.dumps(identity(getattr(ProjectResources,n).__code__),separators=(',',':')).encode()).hexdigest() for n in ('documents','preview','links','open_link')}))`;
  const expected=spawnSync(python,['-B','-c',code],{cwd:root,windowsHide:true,encoding:'utf8'});
  assert.equal(expected.status,0,expected.stderr);const methods=JSON.parse(expected.stdout);
  for(const name of ['workspace-A','workspace-B']){fs.mkdirSync(path.join(out,name));fs.writeFileSync(path.join(out,name,'README.md'),'Synthetic scoped document '+name);}
  const a=await fixture(path.join(out,'workspace-A')),b=await fixture(path.join(out,'workspace-B'));
  fs.writeFileSync(path.join(out,'loaded-backend.json'),JSON.stringify({sourceSHA256:sourceSHA,expectedLoadedMethods:methods,services:sessions.map(s=>s.ready)},null,2));
  for(const s of sessions){
   check('fresh '+path.basename(s.workspace)+' imports current resources module',path.resolve(s.ready.resources_file)===source&&s.ready.resources_sha256===sourceSHA);
   check('loaded code objects match current '+path.basename(s.workspace),JSON.stringify(s.ready.loaded_methods)===JSON.stringify(methods));
   check('SQLite entirely inside evidence folder '+path.basename(s.workspace),path.resolve(s.ready.database)===path.join(out,'browser-state','conversations.sqlite3'));
  }
  check('independent ports and PIDs',a.ready.url!==b.ready.url&&a.ready.pid!==b.ready.pid);
  const body={workspace:a.workspace},index=await call(a,'resource-documents',body),item=index.documents[0];
  const previewBody={...body,id:item.id,version:item.version};
  check('actual HTTP document preview', (await call(a,'resource-preview',previewBody)).text==='Synthetic scoped document workspace-A');
  const pending=await call(a,'resource-link-preview',{...body,name:'Owner-only reference',url:'https://example.com/owned'});
  check('reference preview does not persist',(await call(a,'resource-links',body)).links.length===0);
  const saved=await call(a,'resource-link-confirm',{...body,approval:pending.approval});
  check('confirmed link uses real SQLite',(await call(a,'resource-link-open',{...body,id:saved.id})).url==='https://example.com/owned');
  const foreign={workspace:b.workspace};
  check('shared SQLite other workspace cannot see owner references',(await call(b,'resource-links',foreign)).links.length===0);
  check('other workspace cannot open known reference ID',(await post(b,'resource-link-open',{...foreign,id:saved.id})).status===409);
  check('other workspace rejects original workspace argument',(await post(b,'resource-documents',body)).status===409 && (await post(b,'resource-preview',previewBody)).status===409);
  await a.send({action:'account',account:other});
  check('other account cannot reuse document index',(await post(a,'resource-preview',previewBody)).status===409);
  check('other account sees no owner references',(await call(a,'resource-links',body)).links.length===0);
  check('other account cannot open known reference ID',(await post(a,'resource-link-open',{...body,id:saved.id})).status===409);
  await a.send({action:'account',account:null});
  check('signed out document and link entrypoints fail closed',(await post(a,'resource-documents',body)).status===409&&(await post(a,'resource-links',body)).status===409);
  await a.send({action:'account',account});
  const p=await call(a,'resource-link-preview',{...body,name:'Not authorized after switch',url:'https://example.com/never-saved'});
  await a.send({action:'account',account:other});
  check('account switch invalidates pending save',(await post(a,'resource-link-confirm',{...body,approval:p.approval})).status===409);
  await a.send({action:'account',account});
  for(const [action,kind,request] of [['resource-documents','text',body],['resource-preview','text',previewBody],['resource-links','url',body],['resource-link-open','url',{...body,id:saved.id}]]){
   // Re-index under the owner for a valid preview, then stop inside actual IO.
   await call(a,'resource-documents',body);
   await a.send({action:'arm',kind});const response=post(a,action,request);
   check(action+' reaches controlled concurrent read barrier',(await a.send({action:'paused'})).paused);
   await a.send({action:'account',account:other});await a.send({action:'release'});
   const r=await response;
   check(action+' rejects account change during HTTP read',r.status===409&&typeof r.data.error==='string'&&r.data.error.includes('帳戶已變更'));
   check(action+' discloses no earlier document/URL',!JSON.stringify(r.data).includes('Synthetic scoped document')&&!JSON.stringify(r.data).includes('https://example.com/owned'));
   races.push({action,status:r.status,error:r.data.error,concurrentAccountChange:true});
   await a.send({action:'account',account});
  }
  check('failed races never create a second reference',(await call(a,'resource-links',body)).links.length===1);
  check('product source unchanged during proof',sha(fs.readFileSync(source))===sourceSHA);
  fs.writeFileSync(path.join(out,'loaded-backend.json'),JSON.stringify({sourceSHA256:sourceSHA,expectedLoadedMethods:methods,services:sessions.map(s=>s.ready)},null,2));
 }catch(e){failure=e.stack;console.error(failure);process.exitCode=1;}
 finally{
  // Orderly shutdown of these temporary servers only, using the existing stdin protocol.
  for(const s of sessions){await s.send({action:'release'});const ended=new Promise(resolve=>s.child.once('exit',resolve));s.child.stdin.end('{"action":"stop"}\n');await ended;}
  const result={passed:!failure,checks,races,failure,seconds:(performance.now()-started)/1000,syntheticAccounts:true,realProductionHTTPHandlers:true,realSQLite:true,modelRequests:0,canonicalDataOpened:false,existingServiceContacted:false,temporaryServersClosed:true};
  fs.writeFileSync(path.join(out,'isolation-checks.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({passed:result.passed,checks:checks.length,seconds:result.seconds,out}));
 }
})();
