"""Real filesystem/SQLite resource boundaries. No credentials, network or model calls."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from src.companion_core.chat import Conversations
from src.companion_core.resources import MAX_BYTES, read_text, safe_url
from src.companion_core.siwc import ChatError


@pytest.fixture
def resource(tmp_path):
    root=tmp_path/'workspace';root.mkdir();(root/'docs').mkdir()
    (root/'README.md').write_text('# Actual fixture document\n<script>unsafe()</script>',encoding='utf-8')
    (root/'AGENTS.md').write_text('Local boundaries',encoding='utf-8')
    (root/'docs'/'guide.txt').write_text('A real scoped text file',encoding='utf-8')
    directory=tmp_path/'state';directory.mkdir()
    auth=SimpleNamespace(pending=None,vault=SimpleNamespace(data={'active':'owner'}))
    chat=Conversations(root,directory,auth)
    return SimpleNamespace(root=root,directory=directory,auth=auth,chat=chat,r=chat.resources,body={'workspace':str(root)})


def doc(s,name='README.md'):
    return next(d for d in s.r.documents(s.body)['documents'] if d['relative']==name)


def preview(s,item):
    return s.r.preview({**s.body,'id':item['id'],'version':item['version']})


def save(s,name='Reference',url='https://example.com/docs'):
    p=s.r.preview_link({**s.body,'name':name,'url':url})
    return s.r.confirm_link({**s.body,'approval':p['approval']})


def test_real_index_and_preview_read_only_and_no_model_authority(resource):
    s=resource;before=(s.root/'README.md').read_bytes();item=doc(s)
    assert item['available'] and item['type']=='Markdown' and item['workspace']==str(s.root)
    result=preview(s,item)
    assert result['text']==before.decode() and result['version']==hashlib.sha256(before).hexdigest()
    assert (s.root/'README.md').read_bytes()==before
    assert '未提供給模型' in result['status']
    assert s.chat.busy is None and s.chat.project_approval is None
    with s.chat.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM turns').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM chat_projects').fetchone()[0]==0


def test_only_bounded_root_and_first_docs_layer_are_indexed(resource):
    s=resource;(s.root/'outside.txt').write_text('not allowed')
    (s.root/'docs'/'nested').mkdir();(s.root/'docs'/'nested'/'private.md').write_text('not allowed')
    (s.root/'docs'/'passwords.md').write_text('sensitive file name')
    (s.root/'docs'/'binary.pdf').write_bytes(b'not text')
    names={d['relative'] for d in s.r.documents(s.body)['documents']}
    assert names=={'README.md','AGENTS.md','docs/guide.txt'}
    for relative in ('../outside.txt','/etc/passwd','docs/../outside.txt','docs\\guide.txt','README.md:stream','docs/nested/private.md'):
        with pytest.raises(ChatError):s.r.preview({**s.body,'id':relative,'version':'arbitrary'})
    with pytest.raises(ChatError):s.r.documents({**s.body,'path':'../'})


@pytest.mark.parametrize('content',[b'\x00binary',b'\xff\xfe',b'x'*(MAX_BYTES+1),b'api_key = "abcdefgh12345678"',b'-----BEGIN PRIVATE KEY-----',b'sk-'+b'x'*30],ids=['binary','encoding','oversize','assignment','private-key','provider-key'])
def test_unsafe_contents_are_not_previewable(resource,content):
    s=resource;(s.root/'docs'/'guide.txt').write_bytes(content)
    item=doc(s,'docs/guide.txt')
    assert not item['available'] and item['version'] is None
    with pytest.raises(ChatError):preview(s,item)


def test_changed_deleted_and_hardlinked_files_fail_closed(resource,tmp_path):
    s=resource;item=doc(s);(s.root/'README.md').write_text('changed')
    with pytest.raises(ChatError,match='變動'):preview(s,item)
    item=doc(s);(s.root/'README.md').unlink()
    with pytest.raises(ChatError):preview(s,item)
    outside=tmp_path/'external.txt';outside.write_text('outside content')
    os.link(outside,s.root/'README.md')
    assert not doc(s)['available']


def test_unreadable_file_fails_closed(resource,monkeypatch):
    from contextlib import contextmanager
    import src.companion_core.resources as module
    s=resource;original=module.windows_handle
    @contextmanager
    def deny(path,directory=False):
        if path.name=='guide.txt':raise PermissionError('Synthetic access denied')
        with original(path,directory) as handle:yield handle
    if os.name=='nt':monkeypatch.setattr(module,'windows_handle',deny)
    else:
        original_open=module.os.open
        def deny_open(path,*args,**kwargs):
            if Path(path).name=='guide.txt':raise PermissionError('Synthetic access denied')
            return original_open(path,*args,**kwargs)
        monkeypatch.setattr(module.os,'open',deny_open)
    assert not doc(s,'docs/guide.txt')['available']


def test_file_and_directory_links_cannot_escape(resource,tmp_path):
    s=resource;outside=tmp_path/'external';outside.mkdir();(outside/'leak.md').write_text('NEVER DISCLOSE')
    target=s.root/'docs'/'linked.md'
    try:target.symlink_to(outside/'leak.md')
    except OSError:pass  # Windows normally requires a privilege for file symlinks.
    else:assert not doc(s,'docs/linked.md')['available']
    # A junction exercises the Windows reparse-point boundary without symlink privileges.
    other=s.root/'linked-directory'
    if os.name=='nt':
        p=subprocess.run(['cmd','/c','mklink','/J',str(other),str(outside)],capture_output=True)
        assert p.returncode==0
    else:other.symlink_to(outside,target_is_directory=True)
    try:
        from src.companion_core.resources import checked_path
        with pytest.raises(OSError):checked_path(s.root,'linked-directory/leak.md')
        # Replace the allowed docs directory with that junction/symlink.
        (s.root/'docs'/'guide.txt').unlink()
        if target.is_symlink():target.unlink()
        (s.root/'docs').rmdir();other.rename(s.root/'docs')
        assert all(not d['relative'].startswith('docs/') for d in s.r.documents(s.body)['documents'])
    finally:
        junction=s.root/'docs'
        if junction.is_symlink():junction.unlink()
        elif os.name=='nt' and junction.exists():os.rmdir(junction)


def test_changed_between_open_and_validation_is_not_disclosed(resource,monkeypatch):
    s=resource
    import src.companion_core.resources as module
    original=module.checked_path;calls=[]
    def change_after_read(root,relative):
        result=original(root,relative);calls.append(relative)
        if len(calls)==2:(root/relative).write_text('concurrent content',encoding='utf-8')
        return result
    # On Windows the pinned file denies the write; elsewhere final identity detects it.
    monkeypatch.setattr(module,'checked_path',change_after_read)
    with pytest.raises(ValueError):read_text(s.root,'README.md')


@pytest.mark.parametrize('url',['javascript:alert(1)','data:text/html,x','file:///C:/Windows/win.ini','https://user:pass@example.com','https://example.com\\@evil.test','https://example.com/%0d%0aX:evil','https://example.com/%5cpath','https://example.com:99999','https://','https://example.com/?token=secret',' https://example.com','https://example.com/a b','https://example.com/\n','https://exa<mple.com','https://example.com/?api_key=abcdefghijk',None,{},123])
def test_dangerous_reference_urls_are_rejected(url):
    with pytest.raises(ChatError):safe_url(url)


@pytest.mark.parametrize('url',['https://example.com/docs?q=hello#part','http://127.0.0.1:8000/','https://[::1]/','https://例子.台灣/文件'])
def test_http_references_are_navigation_only(url):
    assert safe_url(url).startswith(('http://','https://'))


def test_link_preview_confirmation_persistence_and_owner_isolation(resource,tmp_path):
    s=resource;p=s.r.preview_link({**s.body,'name':'<img src=x onerror=alert(1)>','url':'https://example.com'})
    assert s.r.links(s.body)['links']==[]
    saved=s.r.confirm_link({**s.body,'approval':p['approval']})
    with pytest.raises(ChatError):s.r.confirm_link({**s.body,'approval':p['approval']})
    restart=Conversations(s.root,s.directory,s.auth)
    assert restart.resources.open_link({**s.body,'id':saved['id']})['name']==p['name']
    s.auth.vault.data['active']='other'
    assert s.r.links(s.body)['links']==[]
    with pytest.raises(ChatError):s.r.open_link({**s.body,'id':saved['id']})
    other=tmp_path/'other';other.mkdir();foreign=Conversations(other,s.directory,s.auth).resources
    assert foreign.links({'workspace':str(other)})['links']==[]
    with pytest.raises(ChatError):foreign.links(s.body)


@pytest.mark.parametrize('change',['account','pending','signed-out','workspace','expiry','restart'])
def test_preview_grants_are_bound_and_ephemeral(resource,change):
    s=resource;item=doc(s);p=s.r.preview_link({**s.body,'name':'Example','url':'https://example.com'})
    if change=='account':s.auth.vault.data['active']='other'
    if change=='pending':s.auth.pending=True
    if change=='signed-out':s.auth.vault.data['active']=None
    if change=='workspace':s.body={'workspace':'foreign-workspace'}
    if change=='expiry':s.r.pending['expires']=0
    if change=='restart':s.r=Conversations(s.root,s.directory,s.auth).resources
    with pytest.raises(ChatError):s.r.confirm_link({**s.body,'approval':p['approval']})
    if change not in ('expiry',):
        with pytest.raises(ChatError):preview(s,item)


def test_document_and_reference_counts_are_bounded(resource):
    s=resource
    for i in range(80):(s.root/'docs'/f'{i:03}.txt').write_text('bounded')
    assert len(s.r.documents(s.body)['documents'])==64
    with s.chat.connect() as db:
        db.executemany('INSERT INTO project_reference_links VALUES (?,?,?,?,?,?)',[(str(i),str(s.root),'owner','Name','https://example.com/','now') for i in range(100)])
    with pytest.raises(ChatError,match='100'):save(s)


def test_corrupt_saved_url_is_never_exposed_as_a_navigation_target(resource):
    s=resource;saved=save(s)
    with s.chat.connect() as db:db.execute('UPDATE project_reference_links SET url=? WHERE id=?',('javascript:alert(1)',saved['id']))
    row=s.r.links(s.body)['links'][0]
    assert row['url'] is None and not row['available']
    with pytest.raises(ChatError):s.r.open_link({**s.body,'id':saved['id']})


def test_resource_http_contract_and_source_scope(resource,tmp_path):
    import http.client
    import threading
    from src.companion_core.surface import Surface, make_server
    from src.companion_core.review import ReviewStore
    from src.companion_core.work import ProjectWork
    from src.companion_core.chat import sources
    s=resource;work=ProjectWork(s.chat);surface=Surface(work,s.root,ReviewStore(tmp_path/'reviews',workspace=str(s.root)))
    s.chat.work=work;work.surface=surface;server=make_server(surface,s.chat,work)
    thread=threading.Thread(target=server.serve_forever);thread.start()
    def post(action,body,origin=None):
        c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
        headers={'Content-Type':'application/json','Origin':origin or f'http://127.0.0.1:{server.server_port}','X-Companion-UI':'1'}
        c.request('POST','/api/chat/'+action,body if isinstance(body,str) else json.dumps(body),headers)
        r=c.getresponse();data=json.loads(r.read());c.close();return r.status,data
    try:
        status,data=post('resource-documents',s.body);assert status==200
        assert post('resource-documents',s.body,'https://evil.example')[0]==403
        assert post('resource-documents','{"workspace":"x","workspace":"y"}')[0]==409
        assert post('resource-documents',{'workspace':'foreign'})[0]==409
        assert post('resource-preview',{**s.body,'id':data['documents'][0]['id'],'version':data['documents'][0]['version']})[0]==200
        assert post('resource-link-confirm',{**s.body,'approval':'invented'})[0]==409
        assert post('resource-link-preview',{**s.body,'name':'Name','url':'file:///outside'})[0]==409
        with pytest.raises(ChatError):sources(s.root,['docs/guide.txt'])
        assert post('preview',{'sources':['docs/guide.txt']})[0]==409
        s.auth.vault.data['active']=None
        assert post('resource-documents',s.body)[0]==409
    finally:server.shutdown();thread.join();server.server_close()


def test_account_change_during_document_index_never_returns_old_owner(resource,monkeypatch):
    import src.companion_core.resources as module
    s=resource;original=module.read_text
    def changed(*args):
        result=original(*args);s.auth.vault.data['active']='other';return result
    monkeypatch.setattr(module,'read_text',changed)
    with pytest.raises(ChatError,match='帳戶已變更'):s.r.documents(s.body)


def test_account_change_during_link_read_never_returns_old_owner(resource,monkeypatch):
    import src.companion_core.resources as module
    s=resource;save(s);original=module.safe_url
    def changed(value):
        result=original(value);s.auth.vault.data['active']='other';return result
    monkeypatch.setattr(module,'safe_url',changed)
    with pytest.raises(ChatError,match='帳戶已變更'):s.r.links(s.body)
