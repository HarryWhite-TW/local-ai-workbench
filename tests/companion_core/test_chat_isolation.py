"""Real HTTP/SQLite, synthetic identities only; no SIWC credentials or model calls."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
import http.client
import json
from types import SimpleNamespace
import threading

import pytest

from src.companion_core.chat import Conversations
from src.companion_core.daily import WorkNotConnected
from src.companion_core.review import ReviewStore
from src.companion_core.siwc import ChatError
from src.companion_core.surface import Surface, make_server


@pytest.fixture
def isolated(tmp_path):
    root = tmp_path / 'project'; root.mkdir()
    other = tmp_path / 'other-project'; other.mkdir()
    directory = tmp_path / 'state'; directory.mkdir()
    auth = SimpleNamespace(lock=threading.RLock(), pending=None,
                           vault=SimpleNamespace(data={'active': 'A'}))

    def snapshot():
        with auth.lock:
            return {'active': auth.vault.data['active'], 'pending': bool(auth.pending),
                    'accounts': [{'id': a, 'label': 'Synthetic ' + a, 'signed_in': True} for a in ('A', 'B')],
                    'notice': 'Synthetic only; no provider calls'}

    def select(account):
        with auth.lock:
            assert account in ('A', 'B')
            auth.vault.data['active'] = account

    def logout():
        with auth.lock:
            auth.vault.data['active'] = None
            auth.pending = None

    def begin(origin, account):
        with auth.lock:
            auth.pending = {'synthetic': True}

    def callback(query):
        # Simulates the existing SIWC callback's use of SignIn.lock, not auth policy.
        with auth.lock:
            select(query['account'])
            auth.pending = None

    auth.snapshot, auth.select, auth.logout = snapshot, select, logout
    auth.begin, auth.callback = begin, callback
    chat = Conversations(root, directory, auth)
    records = [{'id': 'S1', 'key': 'readme', 'name': 'README.md',
                'text': 'A synthetic source original', 'sha256': 'fixture', 'captured_at': 'fixture-date'}]
    with chat.connect() as db:
        for ident, workspace, account in [('a', root, 'A'), ('b', root, 'B'), ('elsewhere', other, 'A')]:
            db.execute('INSERT INTO chats VALUES (?,?,?,?,?)',
                       (ident, str(workspace), account, ident + ' private title', 'fixture-date'))
            db.execute('INSERT INTO turns (id,chat,question,answer,sources,model,created,status) '
                       'VALUES (?,?,?,?,?,?,?,?)', (ident + '-turn', ident, ident + ' question',
                       ident + ' source-bearing answer', json.dumps(records), 'synthetic', 'fixture-date', 'complete'))
    chat.models, chat.models_account = [{'slug': 'synthetic'}], 'A'
    chat.busy = {'chat': 'a', 'turn': 'a-turn'}
    surface = Surface(WorkNotConnected(), root, ReviewStore(directory / 'reviews'))
    server = make_server(surface, chat)
    thread = threading.Thread(target=server.serve_forever); thread.start()

    def request(action, body=None):
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=8)
        try:
            headers = {'Origin': f'http://127.0.0.1:{server.server_port}',
                       'Content-Type': 'application/json', 'X-Companion-UI': '1'}
            path = action if action.startswith('/') else '/api/chat/' + action
            conn.request('GET' if body is None else 'POST', path,
                         None if body is None else json.dumps(body), headers)
            response = conn.getresponse(); raw = response.read()
            return response.status, json.loads(raw) if path.startswith('/api/chat/') else raw.decode()
        finally:
            conn.close()

    yield SimpleNamespace(chat=chat, auth=auth, root=root, other=other, server=server, request=request)
    server.shutdown(); thread.join(); server.server_close()


def test_real_http_owner_history_switch_logout_pending_and_integrity(isolated):
    s = isolated
    database_before = s.chat.path.read_bytes()
    code, original = s.request('get', {'chat': 'a'})
    assert code == 200 and original['turns'][0]['sources'][0]['text'] == 'A synthetic source original'
    assert original['turns'][0]['answer'] == 'a source-bearing answer'
    assert [r['id'] for r in s.request('state')[1]['chats']] == ['a']
    assert s.request('state')[1]['busy'] == {'chat': 'a', 'turn': 'a-turn'}
    assert s.request('get', {'chat': 'b'})[0] == 409
    s.chat.busy = None
    assert s.request('select', {'account': 'B'})[0] == 200
    code, state = s.request('state')
    assert code == 200 and [r['id'] for r in state['chats']] == ['b']
    assert state['models'] == [] and state['busy'] is None
    denied = s.request('get', {'chat': 'a'})
    assert denied[0] == 409 and 'A synthetic source original' not in json.dumps(denied)
    assert s.request('get', {'chat': 'b'})[0] == 200
    assert s.request('logout', {})[0] == 200
    for pending in (False, True):
        if pending:
            # Pending reauthorization can retain the original active ID.
            s.auth.select('A')
            assert s.request('login', {'account': 'A'})[0] == 200
        code, state = s.request('state')
        assert code == 200 and state['chats'] == [] and state['busy'] is None and state['models'] == []
        assert len(state['auth']['accounts']) == 2  # Account picker stays available.
        assert s.request('get', {'chat': 'a'})[0] == 409
        assert s.request('get', {'chat': 'b'})[0] == 409
    assert s.request('/auth/callback?account=A')[0] == 200
    assert s.request('get', {'chat': 'a'}) == (200, original)
    assert s.chat.path.read_bytes() == database_before


def test_foreign_busy_models_and_workspace_do_not_leak(isolated):
    s = isolated
    s.auth.select('B')
    state = s.request('state')[1]
    assert state['busy'] is None and state['models'] == []
    assert 'a-turn' not in json.dumps(state) and 'a private title' not in json.dumps(state)
    s.auth.select('A')
    assert s.request('get', {'chat': 'elsewhere'})[0] == 409
    with s.chat.connect() as db:
        assert db.execute('SELECT count(*) FROM chats').fetchone()[0] == 3


@pytest.mark.parametrize('ident', [None, [], {}, True, 3, '', 'x' * 129, "a' OR 1=1--"])
def test_invalid_or_guessed_ids_cannot_bypass_read_scope(isolated, ident):
    assert isolated.request('get', {'chat': ident})[0] == 409


@pytest.mark.parametrize('change', ['account', 'pending', 'workspace'])
@pytest.mark.parametrize('operation', ['get', 'state'])
def test_changed_identity_during_materialization_fails_closed(isolated, monkeypatch, change, operation):
    s = isolated

    def mutate():
        if change == 'account':
            s.auth.vault.data['active'] = 'B'
        elif change == 'pending':
            s.auth.pending = {'synthetic': True}
        else:
            s.chat.workspace = str(s.other)

    if operation == 'get':
        original = json.loads

        def load(*args, **kwargs):
            result = original(*args, **kwargs); mutate(); return result

        monkeypatch.setattr('src.companion_core.chat.json.loads', load)
        read = lambda: s.chat.get('a')
    else:
        original = s.auth.snapshot

        def snapshot():
            result = original(); mutate(); return result

        monkeypatch.setattr(s.auth, 'snapshot', snapshot)
        read = s.chat.snapshot
    with pytest.raises(ChatError):
        read()


@pytest.mark.parametrize('operation', ['get', 'state'])
@pytest.mark.parametrize('transition', ['select', 'logout', 'callback'])
@pytest.mark.parametrize('stage', ['serialize', 'body'])
def test_http_response_is_atomic_with_existing_auth_lock(isolated, monkeypatch, operation, transition, stage):
    s = isolated
    entered, release, switching = threading.Event(), threading.Event(), threading.Event()
    handler = s.server.RequestHandlerClass
    target = '/api/chat/' + operation
    original_dumps, original_headers = json.dumps, handler.end_headers

    def hold():
        entered.set()
        assert release.wait(5), 'Test barrier timed out'

    def dumps(value, *args, **kwargs):
        if isinstance(value, dict) and ((operation == 'get' and value.get('id') == 'a') or
                                       (operation == 'state' and 'auth' in value)):
            hold()
        return original_dumps(value, *args, **kwargs)

    def end_headers(self):
        original_headers(self)
        if self.path == target:
            hold()  # Headers sent, JSON body not yet emitted.

    monkeypatch.setattr('src.companion_core.surface.json.dumps', dumps) if stage == 'serialize' else monkeypatch.setattr(handler, 'end_headers', end_headers)
    method = 'do_GET' if transition == 'callback' else 'do_POST'
    original_method = getattr(handler, method)

    def switching_request(self):
        if self.path.startswith('/auth/callback') or self.path == '/api/chat/' + transition:
            switching.set()
        return original_method(self)

    monkeypatch.setattr(handler, method, switching_request)
    s.chat.busy = None
    with ThreadPoolExecutor(max_workers=2) as pool:
        reading = pool.submit(s.request, operation, {'chat': 'a'} if operation == 'get' else None)
        try:
            assert entered.wait(5)
            switching_read = pool.submit(s.request, '/auth/callback?account=B' if transition == 'callback' else transition,
                                         None if transition == 'callback' else {'account': 'B'} if transition == 'select' else {})
            assert switching.wait(5)
            with pytest.raises(FutureTimeout):
                switching_read.result(timeout=0.05)
            assert s.auth.vault.data['active'] == 'A'
        finally:
            release.set()
        assert reading.result(timeout=5)[0] == 200  # A's response is emitted before identity changes.
        assert switching_read.result(timeout=5)[0] == 200
    assert s.request('get', {'chat': 'a'})[0] == 409
    state = s.request('state')[1]
    assert all(c['id'] != 'a' for c in state['chats'])
    assert state['busy'] is None and state['models'] == []
