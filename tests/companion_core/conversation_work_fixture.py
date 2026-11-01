"""Synthetic by default; explicit live proof uses only an isolated SIWC store."""
import sys,json,threading
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root))
workspace=Path(sys.argv[2]).resolve() if len(sys.argv)>2 else root
from src.companion_core.chat import Conversations,now
from src.companion_core.work import ProjectWork
from src.companion_core.surface import Surface,make_server
from src.companion_core.review import ReviewStore
directory=Path(sys.argv[1])/'browser-state';directory.mkdir(parents=True,exist_ok=True)
live='--live-document-proof' in sys.argv[3:]
vault=None
if live:
 from src.companion_core.siwc import Vault,SignIn
 if not (directory/'accounts.dpapi').is_file():raise RuntimeError('Isolated SIWC proof store required')
 vault=Vault(directory,workspace);auth=SignIn(vault)
else:
 auth=SimpleNamespace(pending=None,vault=SimpleNamespace(data={'active':'synthetic-test-account'}))
 auth.snapshot=lambda:{'active':auth.vault.data['active'],'accounts':[],'pending':bool(auth.pending),'notice':'Synthetic browser test; no model'}
 auth.access=lambda _: 'synthetic-only'
chat=Conversations(workspace,directory,auth)
if live:chat.catalog()
else:
 chat.models=[{'slug':'synthetic-model','display_name':'Synthetic test only'}];chat.models_account='synthetic-test-account'
 chat._infer=lambda *args: ('合成對話測試：請先確認固定檔案查核範圍。這不是模型回答。', 'synthetic-response')
ident,turn=str(uuid4()),str(uuid4())
with chat.connect() as db:
 db.execute('INSERT INTO chats VALUES (?,?,?,?,?)',(ident,str(workspace),auth.vault.data['active'],'公開文件驗證' if live else '合成對話／真實限定讀取測試',now()))
 if not live:db.execute('INSERT INTO turns (id,chat,question,answer,sources,model,created,status) VALUES (?,?,?,?,?,?,?,?)',(turn,ident,'查核目前 Companion 程式中已實現的能力與未接通範圍','請先確認明確資料範圍；查核定義及入口連接，不將程式存在視為測試通過。','[]','synthetic-model',now(),'complete'))
work=ProjectWork(chat);surface=Surface(work,workspace,ReviewStore(directory/'reviews',workspace=str(workspace)));chat.work,work.surface=work,surface
native=None
if '--native-codex-proof' in sys.argv[3:] or '--native-codex-live-proof' in sys.argv[3:]:
 from src.companion_core.native_codex import NativeCodex
 if '--native-codex-live-proof' in sys.argv[3:]:
  native=NativeCodex(chat)
 else:
  from test_native_codex import FakeRPC
  native_rpc=FakeRPC(workspace)
  native=NativeCodex(chat,executable=Path(__file__),client_factory=lambda:native_rpc)
server=make_server(surface,chat,work,native_codex=native);thread=threading.Thread(target=server.serve_forever);thread.start()
ready={'url':f'http://127.0.0.1:{server.server_port}','chat':ident,'turn':turn}
# Optional stdin-only proof controls; never exposed as product HTTP endpoints.
# They simulate the concurrent SIWC callback changing auth during a resource read.
proof='--resources-proof' in sys.argv[3:]
if proof:
 import hashlib,os,types
 from src.companion_core import resources
 originals={'text':resources.read_text,'url':resources.safe_url}
 paused,release=threading.Event(),threading.Event()
 def code_identity(value):
  if isinstance(value,types.CodeType):
   return [value.co_code.hex(),[code_identity(v) for v in value.co_consts],value.co_names,
    value.co_varnames,value.co_freevars,value.co_cellvars,value.co_argcount,
    value.co_kwonlyargcount,value.co_posonlyargcount,value.co_flags]
  if isinstance(value,(set,frozenset)):return sorted([code_identity(v) for v in value],key=json.dumps)
  if isinstance(value,tuple):return [code_identity(v) for v in value]
  return repr(value)
 ready.update(pid=os.getpid(),database=str(chat.path),resources_file=resources.__file__,
  resources_sha256=hashlib.sha256(Path(resources.__file__).read_bytes()).hexdigest(),
  loaded_methods={name:hashlib.sha256(json.dumps(code_identity(getattr(type(chat.resources),name).__code__),separators=(',',':')).encode()).hexdigest()
   for name in ('documents','preview','links','open_link')})
print(json.dumps(ready),flush=True)
try:
 for line in sys.stdin:
  command=json.loads(line)
  if command['action']=='stop':break
  if command['action']=='native-update' and native is not None and '--native-codex-proof' in sys.argv[3:]:
   native_rpc.text='新的最後回覆：請核對已保存的成果。'
   print(json.dumps({'updated':True}),flush=True)
  if command['action']=='account':
   auth.vault.data['active']=command['account']
   if 'pending' in command:auth.pending=command['pending']
   print(json.dumps({'account':command['account']}),flush=True)
  if proof and command['action']=='arm':
   paused.clear();release.clear();kind=command['kind'];original=originals[kind];armed=[True]
   def hold(*args,_original=original,_armed=armed,**kwargs):
    value=_original(*args,**kwargs)
    if _armed[0]:
     _armed[0]=False;paused.set()
     if not release.wait(15):raise RuntimeError('Synthetic concurrency proof timed out')
    return value
   if kind=='text':resources.read_text=hold
   else:resources.safe_url=hold
   print(json.dumps({'armed':kind}),flush=True)
  if proof and command['action']=='paused':
   print(json.dumps({'paused':paused.wait(5)}),flush=True)
  if proof and command['action']=='release':
   release.set()
   print(json.dumps({'released':True}),flush=True)
finally:
 if proof:release.set()
 server.shutdown();thread.join();server.server_close()
 if surface.worker:surface.worker.join()
 if chat.worker:chat.worker.join()
 if vault:auth.http.close();vault.close()
