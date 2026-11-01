"""Synthetic conversation identity, real bounded file reads/Core/ReviewStore. No AI."""
from hashlib import sha256
import http.client
import json
from pathlib import Path
from types import SimpleNamespace
import threading
from uuid import uuid4

import pytest

from src.companion_core.chat import Conversations, now
from src.companion_core.domain import Authority
from src.companion_core.review import ReviewError, ReviewStore
from src.companion_core.runtime import Request, RuntimeFailure
from src.companion_core.siwc import ChatError
from src.companion_core.surface import Surface, make_server
from src.companion_core.work import ProjectWork, capture, FILES


@pytest.fixture
def work(tmp_path, request):
    root=tmp_path/getattr(request, 'param', 'project');root.mkdir()
    for name in FILES.values():
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text('class CurrentCapability:\n    pass\ndef main():\n    CurrentCapability()\n',encoding='utf8')
    state=tmp_path/'state';state.mkdir()
    auth=SimpleNamespace(pending=None,vault=SimpleNamespace(data={'active':'fixture-account'}))
    auth.snapshot=lambda: {'active':'fixture-account','accounts':[],'pending':False,'notice':'Synthetic only'}
    chat=Conversations(root,state,auth)
    ident,turn=str(uuid4()),str(uuid4())
    with chat.connect() as db:
        db.execute('INSERT INTO chats VALUES (?,?,?,?,?)',(ident,str(root),'fixture-account','Synthetic proposal',now()))
        db.execute("INSERT INTO turns (id,chat,question,answer,sources,model,created,status) VALUES (?,?,?,?,?,?,?,?)",
                   (turn,ident,'查核 Companion 能力','先查核明確程式範圍，不推定測試通過。','[]','synthetic',now(),'complete'))
    runtime=ProjectWork(chat);surface=Surface(runtime,root,ReviewStore(tmp_path/'reviews',workspace=str(root)))
    chat.work,runtime.surface=runtime,surface
    yield runtime,chat,ident,turn
    if surface.worker:surface.worker.join(5)


def proposal(work):
    runtime,chat,ident,turn=work
    return runtime.create({'chat':ident,'turn':turn})


def preview(runtime,p):
    return runtime.preview({'id':p['id'],'goal':p['goal'],'expected':p['expected'],'selection':['daily','core']})


def confirm(runtime,p):
    return runtime.confirm({'id':p['id'],'approval':p['approval'],'authority':'READ_ONLY'})


@pytest.mark.parametrize('work', ['project', 'task-project'], indirect=True)
def test_explicit_proposal_real_read_shared_review_and_restart(work):
    runtime,chat,ident,turn=work
    p=proposal(work)
    assert p['state']=='AWAITING_AUTHORIZATION' and runtime.surface.active is None
    assert runtime.state(ident)[0]['id']==p['id'] and runtime.surface.active is None
    p=preview(runtime,p)
    assert runtime.surface.active is None
    before={k:Path(chat.workspace,FILES[k]).read_bytes() for k in p['selection']}
    started=confirm(runtime,p);runtime.surface.worker.join(5)
    result=runtime.surface.target(started['task_id']);linked=runtime.state(ident)[0]
    assert result['state']==linked['state']=='RESULT_PENDING_REVIEW'
    assert result['task_id']==linked['task_id'] and result['result_id']==linked['result_id']
    assert '非模型摘要' in result['result'] and 'L1：ClassDef CurrentCapability' in result['result']
    for k,data in before.items():
        assert sha256(data).hexdigest() in result['result']
        assert Path(chat.workspace,FILES[k]).read_bytes()==data
    with pytest.raises(ChatError):confirm(runtime,p)
    runtime.surface.decide({'task_id':result['task_id'],'result_id':result['result_id'],'action':'accept','revision_intent':None})
    assert runtime.state(ident)[0]['state']=='ACCEPTED'
    assert runtime.state(ident)[0]['technical_acceptance']=='未由 ChatGPT 技術驗收'
    restarted=ProjectWork(chat);restarted.surface=Surface(restarted,chat.workspace,runtime.surface.store)
    assert restarted.state(ident)[0]['result_id']==result['result_id']
    source=restarted.context('work:'+p['id'],ident)
    assert source['text']==result['result']
    assert source['captured_at']==next(line.split('：',1)[1] for line in result['result'].splitlines() if line.startswith('擷取時間：'))
    assert restarted.origin(result['task_id'])['chat']==ident
    with pytest.raises(ChatError):restarted.origin(str(uuid4()))
    with pytest.raises(ChatError):restarted.context('work:'+p['id'],str(uuid4()))


def test_authority_scope_preview_staleness_and_account(work):
    runtime,chat,ident,turn=work;p=proposal(work)
    for authority in ['NONE','WRITE',True]:
        with pytest.raises(ChatError):runtime.confirm({'id':p['id'],'approval':'not-granted','authority':authority})
    with pytest.raises(ChatError):confirm(runtime,{**p,'approval':'not-granted'})
    with pytest.raises(RuntimeFailure):list(runtime.run(Request('anything',chat.workspace,Authority.READ_ONLY)))
    for selection in [[],['../private'],['daily','daily'],[{}]]:
        with pytest.raises(ChatError):capture(chat.workspace,selection)
    p=preview(runtime,p)
    Path(chat.workspace,FILES['daily']).write_text('def changed():\n    pass\n',encoding='utf8')
    with pytest.raises(ChatError,match='來源已變更'):confirm(runtime,p)
    assert runtime.surface.active is None
    p=preview(runtime,p);chat.auth.vault.data['active']='other-account'
    with pytest.raises(ChatError,match='原本的帳戶'):confirm(runtime,p)


def test_edit_invalidates_approval_and_unavailable_executor(work):
    runtime,chat,ident,turn=work;p=preview(runtime,proposal(work));old=dict(p)
    p=runtime.preview({'id':p['id'],'goal':'修改後的查核','expected':'新的預期結果','selection':['core']})
    with pytest.raises(ChatError):confirm(runtime,old)
    runtime.surface=None
    with pytest.raises(ChatError,match='不可用'):confirm(runtime,p)


def test_real_parse_failure_has_no_result_and_survives_reload(work):
    runtime,chat,ident,turn=work
    Path(chat.workspace,FILES['daily']).write_text('def broken(:\n',encoding='utf8')
    p=preview(runtime,proposal(work));started=confirm(runtime,p);runtime.surface.worker.join(5)
    assert runtime.surface.active.task.state=='FAILED' and runtime.surface.active.task.result is None
    assert runtime.state(ident)[0]['state']=='FAILED'
    with pytest.raises(ChatError):runtime.context('work:'+p['id'],ident)
    restarted=ProjectWork(chat);restarted.surface=Surface(restarted,chat.workspace,runtime.surface.store)
    assert restarted.state(ident)[0]['state']=='FAILED'
    assert restarted.surface.snapshot()['tasks'][0]['task_id']==started['task_id']


def test_sensitive_source_and_size_fail_closed(work):
    runtime,chat,*_=work;p=Path(chat.workspace,FILES['daily'])
    p.write_text('key = "sk-'+('A'*30)+'"',encoding='utf8')
    with pytest.raises(ChatError):capture(chat.workspace,['daily'])
    p.write_text('#'*65_537,encoding='utf8')
    with pytest.raises(ChatError):capture(chat.workspace,['daily'])


def test_http_cannot_bypass_proposal_and_rejects_cross_origin(work):
    runtime,chat,ident,turn=work
    server=make_server(runtime.surface,chat,runtime);thread=threading.Thread(target=server.serve_forever);thread.start()
    try:
        conn=http.client.HTTPConnection('127.0.0.1',server.server_port)
        conn.request('POST','/api/start',json.dumps({'intent':'bypass'}),{'Content-Type':'application/json','X-Companion-UI':'1','Origin':f'http://127.0.0.1:{server.server_port}'})
        response=conn.getresponse();assert response.status==409;response.read()
        conn.request('POST','/api/chat/work-create',json.dumps({'chat':ident,'turn':turn}),{'Content-Type':'application/json','X-Companion-UI':'1','Origin':'https://evil.invalid'})
        response=conn.getresponse();assert response.status==403;response.read()
        assert runtime.surface.active is None
    finally:
        server.shutdown();thread.join();server.server_close()


def test_saved_work_projection_does_not_cross_workspace(work, tmp_path):
    runtime,chat,ident,turn=work
    p=preview(runtime,proposal(work));started=confirm(runtime,p);runtime.surface.worker.join(5)
    original=runtime.surface.target(started['task_id'])
    other=tmp_path/'other-project';other.mkdir()
    # Same application data directory, another workspace; only synthetic test data.
    other_chat=Conversations(other,chat.path.parent,chat.auth)
    for _ in range(2):
        other_work=ProjectWork(other_chat)
        other_work.surface=Surface(other_work,other,ReviewStore(runtime.surface.store.directory,workspace=str(other)))
        assert other_work.saved_failures()==[]
        assert other_work.surface.snapshot()['tasks']==[]
        with pytest.raises(ChatError):other_work.state(ident)
        with pytest.raises(ChatError):other_work.origin(started['task_id'])
        with pytest.raises(ChatError):other_work.context('work:'+p['id'],ident)
        with pytest.raises(ReviewError):other_work.surface.target(started['task_id'])
        with pytest.raises(ReviewError):other_work.surface.decide({'task_id':started['task_id'],
            'result_id':original['result_id'],'action':'accept','revision_intent':None})
    restarted=ProjectWork(chat)
    restarted.surface=Surface(restarted,chat.workspace,runtime.surface.store)
    assert restarted.surface.snapshot()['tasks']==[{'task_id':started['task_id'],
        'intent':p['goal'],'state':'RESULT_PENDING_REVIEW'}]
    assert restarted.surface.target(started['task_id'])==original
    assert restarted.origin(started['task_id'])['chat']==ident


@pytest.mark.parametrize('auth_state',['other-account','signed-out','pending'])
def test_account_guard_covers_summary_links_result_and_review(work,auth_state):
    runtime,chat,ident,turn=work
    p=preview(runtime,proposal(work));started=confirm(runtime,p);runtime.surface.worker.join(5)
    original=runtime.surface.target(started['task_id'])
    if auth_state=='pending':chat.auth.pending=object()
    else:chat.auth.vault.data['active']='other-account' if auth_state=='other-account' else None
    for current in (runtime,ProjectWork(chat)):
        if current.surface is None:current.surface=Surface(current,chat.workspace,runtime.surface.store)
        state=current.surface.snapshot()
        assert state['tasks']==[] and state['active'] is None
        assert state['progress']==[] and state['observation']['events']==[] and state['notice']==''
        assert current.saved_failures()==[]
        with pytest.raises(ChatError):current.state(ident)
        with pytest.raises(ChatError):current.origin(started['task_id'])
        with pytest.raises(ChatError):current.context('work:'+p['id'],ident)
        with pytest.raises(ReviewError):current.surface.target(started['task_id'])
        with pytest.raises(ReviewError):current.surface.decide({'task_id':started['task_id'],
            'result_id':original['result_id'],'action':'accept','revision_intent':None})
    chat.auth.pending=None;chat.auth.vault.data['active']='fixture-account'
    assert runtime.surface.target(started['task_id'])==original
    assert runtime.state(ident)[0]['state']=='RESULT_PENDING_REVIEW'


def test_missing_end_evidence_is_unknown_not_failed(work):
    runtime,chat,ident,turn=work;p=proposal(work);task_id=str(uuid4())
    # Simulate a host exit after binding a task but before recording an outcome.
    with chat.connect() as db:
        db.execute('UPDATE work_proposals SET task_id=? WHERE id=?',(task_id,p['id']))
    for current in (runtime,ProjectWork(chat)):
        current.surface=Surface(current,chat.workspace,runtime.surface.store)
        assert current.state(ident)[0]['state']=='UNKNOWN'
        assert current.surface.snapshot()['tasks']==[{'task_id':task_id,'intent':p['goal'],'state':'UNKNOWN'}]
        with pytest.raises(ChatError):current.context('work:'+p['id'],ident)


def test_cancelled_work_preserves_confirmed_state_and_owner(work,monkeypatch):
    runtime,chat,ident,turn=work;p=preview(runtime,proposal(work))
    entered,release=threading.Event(),threading.Event()
    def waiting_capture(*args):
        if threading.current_thread() is not threading.main_thread():
            entered.set();assert release.wait(5)
        return capture(*args)
    monkeypatch.setattr('src.companion_core.work.capture',waiting_capture)
    started=confirm(runtime,p)
    try:
        assert entered.wait(3)
        chat.auth.vault.data['active']='other-account'
        with pytest.raises(ReviewError):runtime.surface.cancel({'task_id':started['task_id']})
        assert runtime.surface.active.task.state=='RUNNING'
        assert runtime.surface.snapshot()['active'] is None
        chat.auth.vault.data['active']='fixture-account'
        assert runtime.surface.cancel({'task_id':started['task_id']})['state']=='CANCEL_REQUESTED'
    finally:
        release.set();runtime.surface.worker.join(5)
    assert runtime.state(ident)[0]['state']=='CANCELLED'
    restarted=ProjectWork(chat);restarted.surface=Surface(restarted,chat.workspace,runtime.surface.store)
    assert restarted.surface.snapshot()['tasks']==[{'task_id':started['task_id'],
        'intent':p['goal'],'state':'CANCELLED'}]
    with pytest.raises(ChatError):restarted.context('work:'+p['id'],ident)


@pytest.mark.parametrize('different_workspace',[True,False])
def test_http_work_entrypoints_cannot_bypass_owner(work,tmp_path,different_workspace):
    runtime,chat,ident,turn=work;p=preview(runtime,proposal(work))
    started=confirm(runtime,p);runtime.surface.worker.join(5)
    original=runtime.surface.target(started['task_id'])
    if different_workspace:
        other=tmp_path/'other';other.mkdir()
        chat=Conversations(other,chat.path.parent,chat.auth)
    else:
        chat.auth.vault.data['active']='other-account'
    guarded=ProjectWork(chat);chat.work=guarded
    guarded.surface=Surface(guarded,chat.workspace,runtime.surface.store)
    server=make_server(guarded.surface,chat,guarded)
    thread=threading.Thread(target=server.serve_forever);thread.start()
    conn=http.client.HTTPConnection('127.0.0.1',server.server_port)
    try:
        conn.request('GET','/api/state');response=conn.getresponse()
        assert response.status==200
        state=json.loads(response.read());assert state['tasks']==[] and state['active'] is None
        requests=[('/api/chat/work-state',{'chat':ident}),
            ('/api/chat/work-origin',{'task_id':started['task_id']}),
            ('/api/chat/preview',{'chat':ident,'sources':['work:'+p['id']]}),
            ('/api/target',{'task_id':started['task_id']}),
            ('/api/review',{'task_id':started['task_id'],'result_id':original['result_id'],
                'action':'accept','revision_intent':None})]
        for route,body in requests:
            conn.request('POST',route,json.dumps(body),{'Content-Type':'application/json',
                'X-Companion-UI':'1','Origin':f'http://127.0.0.1:{server.server_port}'})
            response=conn.getresponse();assert response.status==409,route
            error=response.read().decode()
            assert p['goal'] not in error and ident not in error and started['task_id'] not in error
        assert runtime.surface.store.get(started['task_id']).task.state=='RESULT_PENDING_REVIEW'
    finally:
        conn.close();server.shutdown();thread.join();server.server_close()
