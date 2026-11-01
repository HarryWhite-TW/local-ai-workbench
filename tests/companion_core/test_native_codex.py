"""Official read boundary and account/workspace isolation; no model or credentials."""
import json
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from src.companion_core.native_codex import NativeCodex, ReadClient, clean
from src.companion_core.siwc import ChatError


class FakeRPC:
    def __init__(self, workspace):
        self.workspace, self.calls = str(workspace), []
        self.foreign = False
        self.on_read = lambda: None
        self.status = 'interrupted'
        self.text = '已檢查目前修改；下一步請核對結果。'

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def call(self, method, params):
        self.calls.append((method, params))
        thread = {'id': 'native-1', 'cwd': str(Path(self.workspace).parent) if self.foreign else self.workspace,
                  'name': '<script>工作</script>', 'updatedAt': 1793451621, 'source': 'vscode',
                  'status': {'type': 'active', 'activeFlags': ['waitingOnApproval']}}
        if method == 'thread/list':
            self.on_read()
            return {'data': [thread], 'nextCursor': None}
        if method == 'thread/read':
            return {'thread': thread}
        assert method == 'thread/turns/list'
        return {'data': [{'id': 'turn-1', 'status': self.status, 'items': [
            {'type': 'reasoning', 'content': ['PRIVATE REASONING']},
            {'type': 'userMessage', 'content': [{'type': 'text', 'text': '請檢查目前修改並列出下一步。'},
                                             {'type': 'localImage', 'path': 'PRIVATE IMAGE PATH'}]},
            {'type': 'commandExecution', 'command': 'PRIVATE COMMAND', 'aggregatedOutput': 'PRIVATE OUTPUT',
             'status': 'completed', 'exitCode': 1},
            {'type': 'agentMessage', 'phase': 'commentary', 'text': '正在檢查'},
            {'type': 'agentMessage', 'phase': 'final_answer', 'text': self.text}]}], 'nextCursor': 'older'}


@pytest.fixture
def integration(tmp_path):
    auth = SimpleNamespace(pending=None, vault=SimpleNamespace(data={'active': 'account-a'}), lock=threading.RLock())
    chat = SimpleNamespace(workspace=tmp_path, lock=threading.RLock(), auth=auth)
    rpc = FakeRPC(tmp_path)
    native = NativeCodex(chat, executable=Path(__file__), client_factory=lambda: rpc)
    return native, rpc, auth


def connect(native):
    preview = native.handle('preview', {})
    assert not native.client_factory().calls
    token = preview['token']
    native.handle('connect', {'token': token})
    return token


def test_preview_and_confirm_before_read(integration):
    native, rpc, _ = integration
    preview = native.handle('preview', {})
    assert not rpc.calls
    with pytest.raises(ChatError):
        native.handle('list', {'token': preview['token'], 'archived': False})
    assert not rpc.calls
    native.handle('connect', {'token': preview['token']})
    value = native.handle('list', {'token': preview['token'], 'archived': False})
    assert value['threads'][0]['live_state'] == 'UNKNOWN'
    assert rpc.calls[0][1]['useStateDbOnly'] is True
    assert rpc.calls[0][1]['cwd'][0] == native.workspace


def test_transcript_projection_and_refresh_never_claim_live(integration):
    native, rpc, _ = integration
    token = connect(native)
    data = native.handle('detail', {'token': token, 'id': 'native-1'})
    assert data['live_state'] == 'UNKNOWN'
    assert data['turns'][0]['recorded_status'] == 'interrupted'
    assert data['turns'][0]['instructions'] == [{'text': '請檢查目前修改並列出下一步。', 'truncated': False, 'attachments_omitted': True}]
    assert data['turns'][0]['commands'] == [{'status': 'completed', 'exit_code': 1}]
    assert data['has_older']
    assert 'PRIVATE' not in json.dumps(data)
    assert data['thread']['url'] == 'codex://threads/native-1'
    rpc.text = '新的最後回覆'
    newer = native.handle('detail', {'token': token, 'id': 'native-1'})
    assert newer['turns'][0]['messages'][-1]['text'] == rpc.text
    rpc.text = 'x' * 13000
    excerpt = native.handle('detail', {'token': token, 'id': 'native-1'})['turns'][0]['messages'][-1]
    assert excerpt['truncated'] and len(excerpt['text']) == 12000


def test_foreign_thread_rejected_before_transcript_read(integration):
    native, rpc, _ = integration
    token = connect(native)
    rpc.foreign = True
    with pytest.raises(ChatError):
        native.handle('detail', {'token': token, 'id': 'native-1'})
    assert [m for m, _ in rpc.calls] == ['thread/read']
    with pytest.raises(ChatError):
        native.handle('list', {'token': token, 'archived': False})


def test_account_changes_during_read_do_not_emit_data(integration):
    native, rpc, auth = integration
    token = connect(native)
    rpc.on_read = lambda: auth.vault.data.update(active='account-b')
    with pytest.raises(ChatError):
        native.handle('list', {'token': token, 'archived': False})
    with pytest.raises(ChatError):
        native.handle('detail', {'token': token, 'id': 'native-1'})


def test_pending_expiry_disconnect_and_bad_input_fail_closed(integration):
    native, rpc, auth = integration
    token = connect(native)
    for action, body in [('detail', {'token': token, 'id': '../other'}),
                         ('list', {'token': token, 'archived': False, 'cwd': '/other'}),
                         ('resume', {'token': token})]:
        with pytest.raises(ChatError):
            native.handle(action, body)
    assert not rpc.calls
    auth.pending = True
    with pytest.raises(ChatError):
        native.handle('list', {'token': token, 'archived': False})
    auth.pending = None
    native.handle('disconnect', {'token': token})
    with pytest.raises(ChatError):
        native.handle('list', {'token': token, 'archived': False})
    token = connect(native)
    native.grants[token]['expires'] = 0
    with pytest.raises(ChatError):
        native.handle('list', {'token': token, 'archived': False})


def test_rpc_has_no_execution_route_and_redacts_credentials():
    client = ReadClient(None)
    for method in ('turn/start', 'thread/resume', 'thread/start', 'account/read'):
        with pytest.raises(ChatError):
            client.call(method, {})
    text = clean('safe\nAuthorization: Bearer synthetic_secret\napi_key=private\nnext')
    assert 'synthetic_secret' not in text and 'private' not in text
    assert text.startswith('safe') and text.endswith('next')
    with pytest.raises(ChatError):
        with ReadClient(None):
            pass


def test_response_binding_covers_serialization_and_scope_revocation(integration, monkeypatch):
    native, rpc, auth = integration
    token = connect(native)
    emitted = []

    def emit(data):
        assert native.chat.lock._is_owned() and auth.lock._is_owned()
        emitted.append(data)

    native.respond('list', {'token': token, 'archived': False}, emit)
    assert len(emitted) == 1

    original = native.handle

    def revoke_after_read(action, body):
        value = original(action, body)
        native.grants.clear()
        return value

    monkeypatch.setattr(native, 'handle', revoke_after_read)
    with pytest.raises(ChatError):
        native.respond('list', {'token': token, 'archived': False}, emit)
    assert len(emitted) == 1


def test_user_text_is_bound_to_its_turn_and_redacted(integration, monkeypatch):
    native, rpc, _ = integration
    token = connect(native)
    original = rpc.call

    def read(method, params):
        result = original(method, params)
        if method == 'thread/turns/list':
            first = result['data'][0]
            first['items'].insert(0, {'type': 'userMessage', 'content': [
                {'type': 'text', 'text': '確認來源\nBearer synthetic_secret'},
                {'type': 'image', 'url': 'PRIVATE IMAGE URL'}]})
            result['data'].insert(0, {'id': 'continuation', 'status': 'completed', 'items': [
                {'type': 'agentMessage', 'text': '續行回覆', 'phase': 'final_answer'}]})
        return result

    monkeypatch.setattr(rpc, 'call', read)
    turns = native.handle('detail', {'token': token, 'id': 'native-1'})['turns']
    assert turns[0]['instructions'] == []
    assert turns[1]['instructions'][0]['text'].startswith('確認來源')
    assert 'synthetic_secret' not in json.dumps(turns)
    assert 'PRIVATE' not in json.dumps(turns)
