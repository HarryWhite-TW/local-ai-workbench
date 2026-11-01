"""Project metadata is persistent, owner-scoped, and never model/source authority."""
import http.client
import json
import sqlite3
import threading
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.companion_core.chat import Conversations, now
from src.companion_core.siwc import ChatError
from src.companion_core.work import ProjectWork
from src.companion_core.surface import Surface, make_server
from src.companion_core.review import ReviewStore


@pytest.fixture
def scoped(tmp_path):
    root=tmp_path/'project';root.mkdir();directory=tmp_path/'state';directory.mkdir()
    auth=SimpleNamespace(pending=None,vault=SimpleNamespace(data={'active':'owner'}))
    auth.snapshot=lambda:{'active':auth.vault.data['active'],'accounts':[],'pending':bool(auth.pending),'notice':'Synthetic only'}
    auth.access=lambda _: 'synthetic-only'
    chat=Conversations(root,directory,auth);ident,turn,foreign=str(uuid4()),str(uuid4()),str(uuid4())
    with chat.connect() as db:
        db.execute('INSERT INTO chats VALUES (?,?,?,?,?)',(ident,str(root),'owner','Owned conversation',now()))
        db.execute('INSERT INTO chats VALUES (?,?,?,?,?)',(foreign,str(root),'other','Private foreign title',now()))
        db.execute('INSERT INTO turns (id,chat,question,answer,sources,model,created,status) VALUES (?,?,?,?,?,?,?,?)',
                   (turn,ident,'原本的問題','原本的回答','[]','synthetic',now(),'complete'))
    work=ProjectWork(chat);surface=Surface(work,root,ReviewStore(tmp_path/'reviews',workspace=str(root)))
    chat.work,work.surface=work,surface
    return SimpleNamespace(chat=chat,ident=ident,foreign=foreign,auth=auth,root=root,directory=directory,work=work,surface=surface)


def confirm(chat,ident,action='link'):
    p=chat.preview_project_link({'chat':ident,'action':action})
    return chat.confirm_project_link({k:p[k] for k in ('chat','action','approval')})


def test_explicit_link_unlink_survives_restart_without_changing_chat(scoped):
    s=scoped;before=s.chat.get(s.ident)
    assert s.chat.project_link(s.ident)['association'] is None
    p=s.chat.preview_project_link({'chat':s.ident,'action':'link'})
    assert s.chat.project_context()['chats']==[]
    body={k:p[k] for k in ('chat','action','approval')}
    linked=s.chat.confirm_project_link(body)
    assert linked['association']['project']['id']==str(s.root)
    assert s.chat.get(s.ident)==before
    assert [r['id'] for r in s.chat.project_context()['chats']]==[s.ident]
    with pytest.raises(ChatError):s.chat.confirm_project_link(body)
    restarted=Conversations(s.root,s.directory,s.auth)
    assert restarted.project_link(s.ident)==linked
    assert restarted.get(s.ident)==before
    confirm(restarted,s.ident,'unlink')
    assert Conversations(s.root,s.directory,s.auth).project_link(s.ident)['association'] is None
    assert restarted.get(s.ident)==before


@pytest.mark.parametrize('ident',[None,False,[],{},'',123,'missing'])
def test_invalid_or_unsaved_chat_cannot_be_linked(scoped,ident):
    with pytest.raises(ChatError):scoped.chat.project_link(ident)
    with pytest.raises(ChatError):scoped.chat.preview_project_link({'chat':ident,'action':'link'})


@pytest.mark.parametrize('scope',['account','workspace','pending','signed-out'])
def test_new_reads_and_writes_fail_closed_for_other_owner(scoped,scope,tmp_path):
    s=scoped;confirm(s.chat,s.ident)
    p=s.chat.preview_project_link({'chat':s.ident,'action':'unlink'})
    chat=s.chat
    if scope=='account':s.auth.vault.data['active']='other'
    elif scope=='workspace':
        other=tmp_path/'other';other.mkdir();chat=Conversations(other,s.directory,s.auth)
    elif scope=='pending':s.auth.pending=True
    else:s.auth.vault.data['active']=None
    with pytest.raises(ChatError):chat.project_link(s.ident)
    with pytest.raises(ChatError):chat.preview_project_link({'chat':s.ident,'action':'link'})
    with pytest.raises(ChatError):chat.confirm_project_link({k:p[k] for k in ('chat','action','approval')})
    if scope in ('pending','signed-out'):
        with pytest.raises(ChatError):chat.project_context()
    else:assert chat.project_context()['chats']==[]
    s.auth.pending=None;s.auth.vault.data['active']='owner'
    assert s.chat.project_link(s.ident)['association'] is not None


def test_preview_expires_is_bound_and_detects_concurrent_change(scoped):
    s=scoped;p=s.chat.preview_project_link({'chat':s.ident,'action':'link'})
    s.chat.project_approval['expires']=0
    with pytest.raises(ChatError):s.chat.confirm_project_link({k:p[k] for k in ('chat','action','approval')})
    p=s.chat.preview_project_link({'chat':s.ident,'action':'link'})
    with pytest.raises(ChatError):s.chat.confirm_project_link({'chat':s.ident,'action':'unlink','approval':p['approval']})
    assert s.chat.project_link(s.ident)['association'] is None
    p=s.chat.preview_project_link({'chat':s.ident,'action':'link'})
    other=Conversations(s.root,s.directory,s.auth);confirm(other,s.ident)
    with pytest.raises(ChatError):s.chat.confirm_project_link({k:p[k] for k in ('chat','action','approval')})
    # No authorization survives process restart.
    p=s.chat.preview_project_link({'chat':s.ident,'action':'unlink'})
    with pytest.raises(ChatError):Conversations(s.root,s.directory,s.auth).confirm_project_link({k:p[k] for k in ('chat','action','approval')})


def test_corrupt_association_identity_is_not_repaired_or_disclosed(scoped):
    s=scoped
    with s.chat.connect() as db:
        db.execute('INSERT INTO chat_projects VALUES (?,?,?,?)',(s.ident,'foreign-project','other',now()))
    with pytest.raises(ChatError):s.chat.project_link(s.ident)
    with pytest.raises(ChatError):s.chat.preview_project_link({'chat':s.ident,'action':'link'})
    assert s.chat.project_context()['chats']==[]
    with s.chat.connect() as db:assert db.execute('SELECT workspace FROM chat_projects').fetchone()[0]=='foreign-project'


def test_relation_never_enters_model_inputs_or_grants_sources(scoped,monkeypatch):
    s=scoped;confirm(s.chat,s.ident);captured=[]
    s.chat.models=[{'slug':'synthetic','display_name':'Synthetic only'}];s.chat.models_account='owner'
    def infer(model,token,inputs,chosen):
        captured.append((inputs,chosen));return '一般聊天回答，不代表查核專案。','synthetic-response'
    monkeypatch.setattr(s.chat,'_infer',infer)
    s.chat.submit({'chat':s.ident,'question':'繼續普通聊天','sources':[],'model':'synthetic','preview':None});s.chat.worker.join(5)
    assert captured and captured[0][1]==[]
    assert str(s.root) not in json.dumps(captured,ensure_ascii=False)
    assert s.chat.project_link(s.ident)['association'] is not None


def test_additive_schema_keeps_existing_rows_and_legacy_insert_shape(tmp_path):
    directory=tmp_path/'state';directory.mkdir();root=tmp_path/'root';root.mkdir()
    with sqlite3.connect(directory/'conversations.sqlite3') as db:
        db.execute('CREATE TABLE chats (id TEXT PRIMARY KEY,workspace TEXT NOT NULL,account TEXT NOT NULL,title TEXT NOT NULL,created TEXT NOT NULL)')
        db.execute('INSERT INTO chats VALUES (?,?,?,?,?)',('old',str(root),'owner','Existing title','existing-date'))
    auth=SimpleNamespace(pending=None,vault=SimpleNamespace(data={'active':'owner'}))
    chat=Conversations(root,directory,auth)
    assert chat.get('old')['title']=='Existing title'
    assert chat.project_link('old')['association'] is None
    with chat.connect() as db:db.execute('INSERT INTO chats VALUES (?,?,?,?,?)',('new',str(root),'owner','New','new-date'))
    assert chat.get('old')['created']=='existing-date'


def test_http_project_routes_enforce_owner_and_strict_payload(scoped,monkeypatch):
    s=scoped;confirm(s.chat,s.ident)
    server=make_server(s.surface,s.chat,s.work);thread=threading.Thread(target=server.serve_forever);thread.start()
    conn=http.client.HTTPConnection('127.0.0.1',server.server_port)
    def post(action,body):
        conn.request('POST','/api/chat/'+action,json.dumps(body),{'Content-Type':'application/json','X-Companion-UI':'1','Origin':f'http://127.0.0.1:{server.server_port}'})
        r=conn.getresponse();return r.status,json.loads(r.read())
    try:
        status,data=post('project-context',{});assert status==200
        assert data['project']['workspace']==str(s.root) and data['work']['workspace']==str(s.root)
        assert [c['id'] for c in data['chats']]==[s.ident]
        for action,body in [('project-get',{'chat':s.foreign}),('project-preview',{'chat':s.foreign,'action':'link'}),
                            ('project-get',{'chat':None}),('project-context',{'account':'other'}),
                            ('project-preview',{'chat':s.ident,'action':'link','project':'foreign'})]:
            status,data=post(action,body);assert status==409 and 'Private foreign title' not in json.dumps(data)
        s.auth.vault.data['active']='other'
        assert post('project-get',{'chat':s.ident})[0]==409
        assert post('project-context',{})[1]['chats']==[]
        s.auth.vault.data['active']=None
        assert post('project-context',{})[0]==409
        s.auth.vault.data['active']='owner'
        snapshot=s.surface.snapshot
        def changed_during_read():
            value=snapshot();s.auth.vault.data['active']='other';return value
        monkeypatch.setattr(s.surface,'snapshot',changed_during_read)
        status,data=post('project-context',{})
        assert status==409 and 'Owned conversation' not in json.dumps(data)
    finally:conn.close();server.shutdown();thread.join();server.server_close()
