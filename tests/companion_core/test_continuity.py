"""Real Windows DPAPI, isolated SQLite, synthetic owners; no provider requests."""
import copy
import http.client
import json
import os
import threading
from types import SimpleNamespace

import pytest

from src.companion_core.chat import Conversations
from src.companion_core.siwc import ChatError
from src.companion_core.daily import WorkNotConnected
from src.companion_core.review import ReviewStore
from src.companion_core.surface import Surface, make_server

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows DPAPI continuity')


@pytest.fixture
def session(tmp_path):
    root = tmp_path / 'project'; root.mkdir()
    directory = tmp_path / 'state'; directory.mkdir()
    auth = SimpleNamespace(pending=None, vault=SimpleNamespace(data={'active': 'A'}))
    chat = Conversations(root, directory, auth)
    with chat.connect() as db:
        for ident, account in [('a', 'A'), ('b', 'B')]:
            db.execute('INSERT INTO chats VALUES (?,?,?,?,?)', (ident, str(root), account, ident, 'fixture'))
    body = {'workspace': str(root), 'account': 'A'}
    value = {'selected': 'a', 'drafts': [[json.dumps(['A', 'a'], separators=(',', ':')), 'PUBLIC_UNSENT_DRAFT']],
             'positions': [['a', 125]], 'preferences': {'material': {'theme': 'porcelain', 'motion': 'reduced', 'quality': 'high'},
                'sidebar': 'collapsed', 'window': {'mode': 'split-right', 'window': None, 'mini': None}}}
    return SimpleNamespace(chat=chat, store=chat.continuity, auth=auth, body=body, value=value, root=root, directory=directory)


def save(s, revision=0, value=None):
    return s.store.save(s.body | {'revision': revision, 'value': value if value is not None else s.value})


def test_real_encryption_restart_and_explicit_draft_removal(session):
    s = session
    assert s.store.get(s.body)['value'] is None
    assert save(s)['revision'] == 1
    assert b'PUBLIC_UNSENT_DRAFT' not in s.chat.path.read_bytes()
    with s.chat.connect() as db:
        blob = db.execute('SELECT payload FROM companion_sessions').fetchone()[0]
    assert b'PUBLIC_UNSENT_DRAFT' not in blob and not blob.startswith(b'{')
    restarted = Conversations(s.root, s.directory, s.auth)
    assert restarted.continuity.get(s.body)['value'] == s.value
    assert 'PUBLIC_UNSENT_DRAFT' not in json.dumps(restarted.get('a'))
    cleared = copy.deepcopy(s.value); cleared['drafts'] = []
    assert save(s, 1, cleared)['revision'] == 2
    assert restarted.continuity.get(s.body)['value']['drafts'] == []


@pytest.mark.parametrize('change', ['account', 'workspace', 'pending', 'signed-out'])
def test_owner_boundary_preserves_original(session, tmp_path, change):
    s = session; save(s)
    original = s.chat.path.read_bytes()
    if change == 'account': s.auth.vault.data['active'] = 'B'
    elif change == 'workspace':
        other = tmp_path / 'other'; other.mkdir(); s.chat.workspace = str(other)
    elif change == 'pending': s.auth.pending = True
    else: s.auth.vault.data['active'] = None
    for action in (lambda: s.store.get(s.body), lambda: save(s, 1)):
        with pytest.raises(ChatError): action()
    assert s.chat.path.read_bytes() == original


@pytest.mark.parametrize('mutation', ['foreign-chat', 'foreign-draft', 'authority', 'oversize', 'bad-position', 'bad-preferences', 'bad-revision'])
def test_invalid_payload_never_replaces_saved_record(session, mutation):
    s = session; save(s); value = copy.deepcopy(s.value); revision = 1
    if mutation == 'foreign-chat': value['selected'] = 'b'
    elif mutation == 'foreign-draft': value['drafts'][0][0] = '["B","b"]'
    elif mutation == 'authority': value['sources'] = ['readme']
    elif mutation == 'oversize': value['drafts'][0][1] = 'x' * 4001
    elif mutation == 'bad-position': value['positions'][0][1] = float('nan')
    elif mutation == 'bad-preferences': value['preferences']['window']['mode'] = 'execute'
    else: revision = True
    with pytest.raises(ChatError): save(s, revision, value)
    assert s.store.get(s.body)['revision'] == 1 and s.store.get(s.body)['value'] == s.value


def test_stale_window_cannot_overwrite_newer_draft(session):
    s = session; save(s)
    newer = copy.deepcopy(s.value); newer['drafts'][0][1] = 'NEWER_PUBLIC_DRAFT'
    save(s, 1, newer)
    with pytest.raises(ChatError, match='較新'): save(s, 1)
    assert s.store.get(s.body)['value'] == newer


def test_corrupt_ciphertext_is_preserved_and_not_reported_as_saved(session):
    s = session; save(s)
    with s.chat.connect() as db:
        db.execute('UPDATE companion_sessions SET payload=?', (b'CORRUPT_PUBLIC_FIXTURE',))
    with pytest.raises(ChatError, match='原記錄已保留'): s.store.get(s.body)
    with pytest.raises(ChatError, match='原記錄已保留'): save(s, 1)
    with s.chat.connect() as db:
        assert db.execute('SELECT payload FROM companion_sessions').fetchone()[0] == b'CORRUPT_PUBLIC_FIXTURE'


def test_http_large_encrypted_session_keeps_other_body_limits_and_owner_guards(session):
    s = session
    with s.chat.connect() as db:
        for ident in ('a2', 'a3', 'a4'):
            db.execute('INSERT INTO chats VALUES (?,?,?,?,?)', (ident, str(s.root), 'A', ident, 'fixture'))
    value = copy.deepcopy(s.value)
    value['drafts'] = [[json.dumps(['A', ident], separators=(',', ':')), '公開' * 2000] for ident in ('a', 'a2', 'a3', 'a4')]
    surface = Surface(WorkNotConnected(), s.root, ReviewStore(s.directory / 'reviews'))
    server = make_server(surface, s.chat); thread = threading.Thread(target=server.serve_forever); thread.start()

    def post(action, body, *, origin=None):
        raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode('utf8')
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        try:
            connection.request('POST', '/api/chat/' + action, raw, {'Content-Type': 'application/json',
                'X-Companion-UI': '1', 'Origin': origin or f'http://127.0.0.1:{server.server_port}'})
            response = connection.getresponse(); return response.status, json.loads(response.read())
        finally: connection.close()

    try:
        status, data = post('continuity-save', s.body | {'revision': 0, 'value': value})
        assert status == 200 and data['revision'] == 1
        assert post('continuity-get', s.body)[1]['value'] == value
        assert b'PUBLIC_UNSENT_DRAFT' not in s.chat.path.read_bytes()
        assert post('continuity-get', s.body | {'account': 'B'})[0] == 409
        assert post('continuity-get', s.body, origin='https://example.invalid')[0] == 403
        duplicate = json.dumps(s.body).removesuffix('}') + ',"account":"B"}'
        assert post('continuity-get', duplicate.encode())[0] == 409
        assert post('send', {'question': 'x' * 33000})[0] == 409
        assert s.store.get(s.body)['revision'] == 1
    finally:
        server.shutdown(); thread.join(); server.server_close()
