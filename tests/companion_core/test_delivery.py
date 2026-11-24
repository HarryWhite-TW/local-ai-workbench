"""Real official SDK, loopback HTTP, SQLite; no real credentials/inference."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
from types import SimpleNamespace

import httpx2
from openai import OpenAI
import pytest

from src.companion_core.chat import Conversations, validate_citations
from src.companion_core.delivery import capabilities
from src.companion_core.siwc import ChatError


@pytest.fixture
def lab(tmp_path):
    calls=[]; config={'mode':'complete','text':'A normal answer.','gate':None}
    ready=threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append(body)
            if config['mode']=='reject':
                self.send_response(400);self.send_header('Content-Type','application/json');self.end_headers()
                self.wfile.write(json.dumps({'error':config.get('error',{'code':'unsupported_parameter','param':'reasoning.effort','message':'PRIVATE_SENTINEL'})}).encode());return
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
            def event(kind,**payload):
                self.wfile.write(('data: '+json.dumps({'type':kind,**payload})+'\n\n').encode());self.wfile.flush()
            try:
                event('response.created',response={'id':config.get('response_id','r')})
                event('response.output_item.added',output_index=0,item={'id':'m','type':'message','role':'assistant','status':'in_progress','content':[]})
                text=config['text'];mid=max(1,len(text)//2)
                chunks=config.get('chunks',[text[:mid]])
                for chunk in chunks:
                    event('response.output_text.delta',output_index=0,content_index=0,item_id='m',delta=chunk)
                    if config.get('chunks'):time.sleep(.3)
                # Allow a persisted checkpoint to be observed before terminal.
                ready.set()
                if config['gate']:config['gate'].wait(5)
                time.sleep(.3)
                if config['mode']=='disconnect':return
                if config['mode'] in ('failed','incomplete'):
                    event('response.'+config['mode'],response={'id':'r','error':config.get('error',{'code':'synthetic_failure'})});return
                event('response.output_text.delta',output_index=0,content_index=0,item_id='m',delta=text[mid:])
                item={'id':'m','type':'message','role':'assistant','status':'completed','content':[{'type':'output_text','text':text}]}
                event('response.output_item.done',output_index=0,item=item)
                event('response.completed',response={'id':'r','status':'completed','output':[] if config['mode']=='empty-output' else [item]})
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever);thread.start()
    auth=SimpleNamespace(pending=None,lock=threading.RLock(),vault=SimpleNamespace(data={'active':'A'}),access=lambda _: 'test-only-credential')
    auth.snapshot=lambda:{'active':auth.vault.data['active'],'pending':False,'accounts':[]}
    workspace=tmp_path/'project';workspace.mkdir();directory=tmp_path/'data';directory.mkdir()
    @contextmanager
    def factory(token,request):
        with httpx2.Client(trust_env=False,timeout=2) as transport:
            with OpenAI(api_key=token,base_url=f'http://127.0.0.1:{server.server_port}/v1',max_retries=0,http_client=transport) as client:
                with client.responses.create(**request) as stream:yield stream
    def reopen():
        chat=Conversations(workspace,directory,auth);chat._sdk_factory=factory
        chat.models=[{'slug':'synthetic','reasoning_efforts':['low','high']}];chat.models_account='A'
        return chat
    chat=reopen()
    body={'chat':None,'question':'Explain','sources':[],'preview':None,'model':'synthetic','effort':'high','request_id':'one'}
    yield SimpleNamespace(chat=chat,config=config,calls=calls,ready=ready,body=body,reopen=reopen,auth=auth,
                          workspace=workspace,directory=directory,url=f'http://127.0.0.1:{server.server_port}/v1')
    if config['gate']:config['gate'].set()
    if chat.worker:chat.worker.join(5)
    server.shutdown();server.server_close();thread.join()


@pytest.mark.parametrize('mode,length',[('complete',16),('complete',70000),('empty-output',600000)])
def test_sdk_completion_and_request_contract(lab,mode,length):
    lab.config.update(mode=mode,text='X'*length)
    receipt=lab.chat.submit(lab.body);lab.chat.worker.join(5)
    turn=lab.chat.get(receipt['chat'])['turns'][0]
    assert turn['status']=='complete' and turn['delivery_state']=='complete'
    assert turn['answer']=='X'*length and turn['requested_effort']=='high'
    assert len(lab.calls)==1
    assert lab.calls[0]['reasoning']=={'effort':'high'}
    assert lab.calls[0]['store'] is False and lab.calls[0]['stream'] is True
    assert lab.reopen().get(receipt['chat'])['turns'][0]['answer']==turn['answer']


@pytest.mark.parametrize("citation", [
    "[S2:L1]", "[X1:L1]", "[S1:L0-L2]", "[S1:L2-L1]", "[S1:L1-L3]",
    "[S1:L3]", "[S1:L1-2]", "[S1:L1-L]", "[S1:L1-L2", "[S1:L1 L2]",
    "[s1:L1]", "[S1:L１]", "[S1]", "[ S1:L1]", "[S1:L1234567890]",
])
def test_malformed_or_out_of_bounds_citation_fails_even_with_valid_citation(citation):
    sources = [{"id": "S1", "text": "first\nsecond"}]
    with pytest.raises(ChatError, match="來源身分或行號不符"):
        validate_citations("[S1:L1] " + citation, sources, require=True)


@pytest.mark.parametrize("citation, completed", [
    ("[S1:L1]", True), ("[S1:L1-L2]", True), ("[S1:L2-L2]", True),
    ("[S1:L1-L3]", False), ("", False),
])
def test_web_citation_reaches_terminal_storage_through_sdk(lab, monkeypatch, citation, completed):
    source = {"id": "S1", "key": "web:test", "name": "Approved excerpt",
              "sha256": "fixture-digest", "captured_at": "2026-11-24", "text": "first\nsecond"}
    monkeypatch.setattr(lab.chat, "selected_sources", lambda *_args, **_kwargs: [source])
    lab.config["text"] = "Answer " + citation
    receipt = lab.chat.submit({**lab.body, "sources": [source["key"]], "preview": {source["key"]: source["sha256"]}})
    lab.chat.worker.join(5)
    turn = lab.reopen().get(receipt["chat"])["turns"][0]
    assert turn["delivery_state"] == ("complete" if completed else "failed")
    assert turn["sources"] == [source]
    if completed:
        assert turn["answer"] == lab.config["text"]


@pytest.mark.parametrize('mode,state',[('disconnect','interrupted'),('failed','failed'),('incomplete','interrupted'),('reject','failed')])
def test_faults_preserve_partial_without_success_or_retries(lab,mode,state):
    lab.config.update(mode=mode,text='Saved partial '*30)
    receipt=lab.chat.submit(lab.body);lab.chat.worker.join(5)
    turn=lab.chat.get(receipt['chat'])['turns'][0]
    assert turn['delivery_state']==state and turn['status']=='failed'
    if mode!='reject':assert turn['answer'] and 'Saved partial' in turn['answer']
    else:
        assert turn['error_code']=='unsupported_parameter' and turn['error_param']=='reasoning.effort'
        assert 'PRIVATE_SENTINEL' not in json.dumps(turn)
    assert len(lab.calls)==1


def test_live_progress_duplicate_cancel_and_owner(lab):
    lab.config.update(text='Visible progress '*50,gate=threading.Event())
    receipt=lab.chat.submit(lab.body);assert lab.ready.wait(3)
    deadline=time.monotonic()+3
    while not lab.chat.get(receipt['chat'])['turns'][0]['answer'] and time.monotonic()<deadline:time.sleep(.02)
    assert lab.chat.get(receipt['chat'])['turns'][0]['answer']
    assert lab.chat.submit(lab.body)==receipt and len(lab.calls)==1
    with pytest.raises(ChatError):lab.chat.submit({**lab.body,'question':'different'})
    lab.auth.vault.data['active']='B'
    with pytest.raises(ChatError):lab.chat.cancel(receipt)
    with pytest.raises(ChatError):lab.chat.get(receipt['chat'])
    lab.auth.vault.data['active']='A'
    lab.chat.cancel(receipt);lab.config['gate'].set();lab.chat.worker.join(5)
    turn=lab.chat.get(receipt['chat'])['turns'][0]
    assert turn['delivery_state']=='cancelled' and turn['answer']
    reopened=lab.reopen();assert reopened.submit(lab.body)==receipt and len(lab.calls)==1


def test_restart_pending_compatibility_and_unknown_effort(lab):
    with pytest.raises(ChatError):lab.chat.submit({**lab.body,'effort':'ultra'})
    assert not lab.calls
    with lab.chat.connect() as db:
        db.execute('INSERT INTO chats VALUES (?,?,?,?,?)',('old',lab.chat.workspace,'A','old','now'))
        db.execute('INSERT INTO turns(id,chat,question,answer,sources,model,created,status) VALUES (?,?,?,?,?,?,?,?)',('old-turn','old','q','partial text','[]','synthetic','now','pending'))
        db.execute('INSERT INTO turn_delivery(turn,state) VALUES (?,?)',('old-turn','pending'))
    reopened=lab.reopen();turn=reopened.get('old')['turns'][0]
    assert turn['answer']=='partial text' and turn['delivery_state']=='interrupted' and turn['status']=='failed'
    # Legacy reader still understands all base columns and never sees partial as complete.
    with reopened.connect() as db:assert db.execute('SELECT answer FROM turns WHERE status="complete"').fetchall()==[]
    assert not lab.calls


def test_catalog_never_guesses():
    assert capabilities({'slug':'gpt-6.1-sol'})['reasoning_efforts']==[]
    assert capabilities({'supported_reasoning_levels':[{'effort':'high'}]})['reasoning_efforts']==['high']
    assert capabilities({'supported_reasoning_levels':['ultra']})['reasoning_efforts']==[]


@pytest.mark.parametrize('levels,default,expected,expected_default',[
    ([{'effort':'low'},{'effort':'high'}],None,['low','high'],None),
    ([{'effort':'medium'},{'effort':'max'}],None,['medium','max'],None),
    ([{'effort':'medium'},{'effort':'ultra'},{'effort':'max'}],'max',['medium','max'],'max'),
    ([None,{},'high',{'effort':[]},{'effort':'low'},{'effort':'low'}],'ultra',['low'],None),
    ([{'effort':'high'}],'medium',['high'],None),
    (None,'high',[],None),
])
def test_catalog_filters_each_explicit_effort(levels,default,expected,expected_default):
    result=capabilities({'supported_reasoning_levels':levels,'default_reasoning_level':default})
    assert result=={'reasoning_efforts':expected,'default_effort':expected_default}


@pytest.mark.parametrize('effort',['ultra','off','xhigh'])
def test_catalog_unsupported_effort_is_rejected_before_inference(tmp_path,effort):
    accessed=[]
    auth=SimpleNamespace(pending=None,lock=threading.RLock(),
        vault=SimpleNamespace(data={'active':'A'}),access=lambda _:accessed.append(True))
    workspace=tmp_path/'project';workspace.mkdir()
    directory=tmp_path/'data';directory.mkdir()
    chat=Conversations(workspace,directory,auth)
    chat.models_account='A'
    chat.models=[{'slug':'synthetic',**capabilities({'supported_reasoning_levels':[
        {'effort':'medium'},{'effort':'max'},{'effort':'ultra'},{'effort':'off'}]})}]
    with pytest.raises(ChatError):chat.submit({'chat':None,'question':'Explain',
        'sources':[],'preview':None,'model':'synthetic','effort':effort})
    assert not accessed and chat.worker is None
    with chat.connect() as db:assert db.execute('SELECT count(*) FROM turns').fetchone()[0]==0


@pytest.mark.parametrize('mode',['complete','disconnect','failed'])
def test_segmented_credential_never_reaches_readback_or_sqlite(lab,mode):
    credential='test-only-credential'
    lab.config.update(mode=mode,text='unused',chunks=['Safe public introduction. ',credential[:9],credential[9:]])
    receipt=lab.chat.submit(lab.body)
    deadline=time.monotonic()+5
    while lab.chat.worker.is_alive() and time.monotonic()<deadline:
        visible=json.dumps(lab.chat.get(receipt['chat']))
        assert credential not in visible and credential[:9] not in visible
        time.sleep(.02)
    lab.chat.worker.join(3);assert not lab.chat.worker.is_alive()
    turn=lab.chat.get(receipt['chat'])['turns'][0]
    assert turn['status']=='failed' and turn['delivery_state']=='failed'
    assert turn['answer']=='Safe public introduction. '
    for path in lab.directory.glob('conversations.sqlite3*'):
        assert credential.encode() not in path.read_bytes()
    assert len(lab.calls)==1


@pytest.mark.parametrize('field',['response_id','http-error','stream-error'])
def test_credential_in_provider_metadata_is_not_persisted(lab,field):
    credential='test-only-credential'
    if field=='response_id':lab.config['response_id']=credential
    else:lab.config.update(mode='reject' if field=='http-error' else 'failed',error={'code':credential,'param':credential,'message':credential})
    receipt=lab.chat.submit(lab.body);lab.chat.worker.join(5)
    turn=lab.chat.get(receipt['chat'])['turns'][0]
    assert turn['status']=='failed' and credential not in json.dumps(turn)
    for path in lab.directory.glob('conversations.sqlite3*'):
        assert credential.encode() not in path.read_bytes()
    assert len(lab.calls)==1


def test_real_worker_process_termination_preserves_partial_without_resubmit(lab):
    import subprocess
    import sys
    lab.config.update(text='Durable process output. '*50,gate=threading.Event())
    script='''
import sys,threading,time
from contextlib import contextmanager
from types import SimpleNamespace
import httpx2
from openai import OpenAI
from src.companion_core.chat import Conversations
auth=SimpleNamespace(pending=None,lock=threading.RLock(),vault=SimpleNamespace(data={'active':'A'}),access=lambda _: 'test-only-credential')
c=Conversations(sys.argv[1],sys.argv[2],auth)
c.models=[{'slug':'synthetic','reasoning_efforts':['high']}];c.models_account='A'
@contextmanager
def factory(token,request):
    with httpx2.Client(trust_env=False,timeout=10) as http:
        with OpenAI(api_key=token,base_url=sys.argv[3],max_retries=0,http_client=http) as client:
            with client.responses.create(**request) as stream:yield stream
c._sdk_factory=factory
c.submit({'chat':None,'question':'Explain','sources':[],'preview':None,'model':'synthetic','effort':'high','request_id':'one'})
c.worker.join()
'''
    process=subprocess.Popen([sys.executable,'-B','-c',script,str(lab.workspace),str(lab.directory),lab.url],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        deadline=time.monotonic()+4
        saved=None
        while time.monotonic()<deadline:
            with lab.chat.connect() as db:
                saved=db.execute("SELECT id,chat,answer,status FROM turns WHERE answer IS NOT NULL").fetchone()
            if saved:break
            time.sleep(.025)
        assert saved is not None and saved['status']=='pending'
        process.kill();process.wait(timeout=3)
        reopened=lab.reopen();turn=reopened.get(saved['chat'])['turns'][0]
        assert turn['delivery_state']=='interrupted' and turn['answer']==saved['answer']
        assert reopened.submit(lab.body)=={'chat':saved['chat'],'turn':saved['id']}
        assert len(lab.calls)==1
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=3)
        process.communicate(timeout=3)


def test_accepted_sqlite_upgrade_and_legacy_readback_on_isolated_backup(lab,tmp_path):
    import shutil
    import subprocess
    import types
    baseline='8411721ca92b4a58d9eb87c8cb8af52b086f1642'
    source=subprocess.check_output(['git','show',baseline+':src/companion_core/chat.py']).decode('utf-8')
    legacy=types.ModuleType('src.companion_core._accepted_chat')
    exec(compile(source,'accepted-chat.py','exec'),legacy.__dict__)
    olddir=tmp_path/'old-data';olddir.mkdir()
    old=legacy.Conversations(lab.workspace,olddir,lab.auth)
    with old.connect() as db:
        db.execute('INSERT INTO chats VALUES (?,?,?,?,?)',('historic',old.workspace,'A','Saved history','then'))
        db.execute('INSERT INTO turns(id,chat,question,answer,sources,model,created,status) VALUES (?,?,?,?,?,?,?,?)',('historic-turn','historic','old question','old answer','[]','synthetic','then','complete'))
    original=old.get('historic');before=old.path.read_bytes()
    upgraded=Conversations(lab.workspace,olddir,lab.auth)
    assert upgraded.get('historic')==original
    with upgraded.connect() as db:
        db.execute('INSERT INTO turns(id,chat,question,answer,sources,model,created,status) VALUES (?,?,?,?,?,?,?,?)',('partial','historic','new question','retained partial','[]','synthetic','later','failed'))
        db.execute('INSERT INTO turn_delivery(turn,state,effort) VALUES (?,?,?)',('partial','interrupted','high'))
    # Rollback is a separate backup copy; never restore a backup over new turns.
    rollback=tmp_path/'rollback-copy';rollback.mkdir()
    shutil.copyfile(upgraded.path,rollback/'conversations.sqlite3')
    oldreader=legacy.Conversations(lab.workspace,rollback,lab.auth)
    rows=oldreader.get('historic')['turns']
    # created is TEXT: "later" sorts before "then". Identity, not insertion
    # position, determines which historical turn must remain byte-for-byte equal.
    assert [row['id'] for row in rows]==['partial','historic-turn']
    by_id={row['id']:row for row in rows}
    assert by_id['historic-turn']==original['turns'][0]
    assert by_id['partial']['answer']=='retained partial' and by_id['partial']['status']=='failed'
    current={row['id']:row for row in upgraded.get('historic')['turns']}
    assert current['historic-turn']==original['turns'][0]
    assert current['partial']['answer']=='retained partial' and current['partial']['delivery_state']=='interrupted'
    assert old.path.read_bytes()!=before  # Additive table; base data stayed intact.
    assert not lab.calls
