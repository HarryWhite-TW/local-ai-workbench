from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.companion_core.chat import Conversations, now
from src.companion_core.codex_trial import LocalTrialIdentity, OWNER
from src.companion_core.domain import Authority, Execution, Task
from src.companion_core.review import ReviewError, ReviewStore
from src.companion_core.siwc import ChatError
from src.companion_core.surface import Surface
from src.companion_core.ui_candidate_check import STYLES, check_styles
from src.companion_core.ui_implementation import NativeUiImplementation, UI_SCOPE, digest, encode_source


@pytest.fixture
def host(tmp_path, monkeypatch):
    project = tmp_path / 'project'
    project.mkdir()
    auth = LocalTrialIdentity(SimpleNamespace(data={'active':OWNER}))
    chat = Conversations(project, tmp_path, auth)
    work = NativeUiImplementation(chat, tmp_path / 'unused.exe', tmp_path)
    work.surface = Surface(work, project, ReviewStore(tmp_path / 'reviews', workspace=str(project)))
    chat.work = work
    monkeypatch.setattr('src.companion_core.native_collaboration.verified_executor', lambda _: None)
    return chat, work


def proposal(host, write=True):
    chat, work = host
    ident, turn = str(uuid4()), str(uuid4())
    with chat.connect() as db:
        db.execute('INSERT INTO chats VALUES(?,?,?,?,?)', (ident, chat.workspace, OWNER, '隔離', now()))
        db.execute('''INSERT INTO turns(id,chat,question,model,sources,created,status)
                      VALUES(?,?,?,?,?,?,?)''', (turn,ident,'改善閱讀','gpt-6.1-terra','[]',now(),'pending'))
    chat.busy = {'chat':ident, 'turn':turn}
    pid = (work.offer_implementation(ident, turn, '改善閱讀', '改善介面間距') if write else
           work.offer(ident, turn, 'knowledge-lifecycle', '檢視知識', '唯讀查核'))
    with chat.connect() as db:
        db.execute("UPDATE turns SET status='complete' WHERE id=?", (turn,))
    chat.busy = None
    p = work._get(pid)
    return {key:p[key] for key in ('id', 'goal', 'expected', 'selection')}


def confirmation(work, p, token, authority='ISOLATED_WRITE'):
    return work.confirm({'id':p['id'], 'approval':token, 'authority':authority})


@pytest.mark.parametrize('obstacle', ['no_preview', 'declined', 'expired', 'wrong_authority', 'wrong_owner', 'drift'])
def test_write_confirmation_fails_closed(host, monkeypatch, obstacle):
    chat, work = host
    p = proposal(host)
    token = 'unapproved'
    authority = 'ISOLATED_WRITE'
    attempts = []
    monkeypatch.setattr(work.surface, 'start', lambda *a, **k: attempts.append(a))
    if obstacle != 'no_preview':
        token = work.preview(p)['approval']
    if obstacle == 'declined':
        work.decline({'id':p['id']})
    elif obstacle == 'expired':
        monkeypatch.setattr('src.companion_core.native_collaboration.monotonic', lambda: float('inf'))
    elif obstacle == 'wrong_authority':
        authority = 'READ_ONLY'
    elif obstacle == 'wrong_owner':
        chat.auth.vault.data['active'] = 'another-user'
    elif obstacle == 'drift':
        captured = work.capture(chat.workspace, UI_SCOPE)
        captured[0]['sha256'] = 'drifted'
        monkeypatch.setattr(work, 'capture', lambda *a: captured)
    with pytest.raises(ChatError):
        confirmation(work, p, token, authority)
    assert not attempts
    assert not work.candidates.exists()


def test_separate_read_only_grant_and_write_ticket_consumed_once(host, monkeypatch):
    _, work = host
    readonly = proposal(host, write=False)
    readonly_ticket = work.preview(readonly)['approval']
    with pytest.raises(ChatError):
        confirmation(work, readonly, readonly_ticket)
    p = proposal(host)
    grant = work.preview(p)
    with pytest.raises(ChatError):
        confirmation(work, p, readonly_ticket)
    calls = []

    def bind_only(goal, *, bind, finished, authority):
        ident = str(uuid4())
        bind(ident)
        calls.append((goal, authority))
        return {'task_id':ident}

    monkeypatch.setattr(work.surface, 'start', bind_only)
    confirmation(work, p, grant['approval'])
    with pytest.raises(ChatError):
        confirmation(work, p, grant['approval'])
    assert calls == [(p['goal'], Authority.ISOLATED_WRITE)]


def test_verified_preview_is_bound_to_receipt_owner_and_immutable_result(host):
    chat, work = host
    p = proposal(host)
    records = work.capture(chat.workspace, UI_SCOPE)
    work.preview(p)
    task = str(uuid4())
    with chat.connect() as db:
        db.execute('UPDATE work_proposals SET task_id=? WHERE id=?', (task, p['id']))
    work._mark(p['id'], state='COMPLETED', thread_id='thread-1', turn_id='turn-1')
    private = work._get(p['id'])
    root = work.candidate(private)
    (root / 'editable').mkdir(parents=True)
    for record in records[:-1]:
        name = Path(record['name']).name
        target = (root / 'editable' if name in STYLES else root) / name
        target.write_bytes(encode_source(record))
    edited = root / 'editable' / 'chat.css'
    with edited.open('ab') as out:
        out.write(b'\n.chat-message p { max-width: 58ch; }\n')
    manifest = {name:digest(data) for name, data in check_styles(root / 'editable').items()}
    report = work.completed_report(private, records, manifest)
    with pytest.raises(ReviewError):
        work.preview_document(p['id'])
    result = Task(task, p['goal'], chat.workspace, work.provider_id, Authority.ISOLATED_WRITE,
                  execution=Execution.COMPLETED, session_id='thread-1', result=report)
    receipt = work.surface.store.publish(result)
    assert receipt.task.authority == Authority.ISOLATED_WRITE
    assert receipt.task.state == 'RESULT_PENDING_REVIEW'
    assert b'.chat-message p { max-width: 58ch; }' in work.preview_document(p['id'])
    with pytest.raises(ReviewError):
        work.surface.store.decide(task, receipt.result_id, 'revise', reviewer='person', revision_intent='next')
    with pytest.raises(ReviewError):
        work.surface.decide({'task_id':task, 'result_id':receipt.result_id, 'action':'accept', 'revision_intent':None})
    chat.auth.vault.data['active'] = 'another-user'
    with pytest.raises(ChatError):
        work.preview_document(p['id'])
    chat.auth.vault.data['active'] = OWNER
    edited.write_bytes(edited.read_bytes() + b'\n/* drift */')
    with pytest.raises(ChatError):
        work.preview_document(p['id'])


@pytest.mark.parametrize('invalid', [b'</style ><script>', b'@import "file.css";', b'a{content:url(a)}', b'a{content:\\78;}'])
def test_unsafe_candidate_styles_never_pass(invalid, tmp_path):
    for name in STYLES:
        (tmp_path / name).write_bytes(invalid)
    with pytest.raises(ValueError):
        check_styles(tmp_path)
