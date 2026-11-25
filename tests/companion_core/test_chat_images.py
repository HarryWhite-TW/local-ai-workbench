from base64 import b64encode
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.companion_core.chat import Conversations
from src.companion_core.chat_images import decode_image, IMAGE_MODEL, IMAGE_EFFORT, PNG_PREFIX
from src.companion_core.codex_trial import LocalTrialIdentity, OWNER
from src.companion_core.codex_work_agent import CodexWorkAgent
from src.companion_core.siwc import ChatError


PNG = bytes.fromhex('89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de'
                    '0000000c49444154089963606060000000040001a30a15e30000000049454e44ae426082')


@pytest.fixture
def composer(tmp_path, monkeypatch):
    agent = CodexWorkAgent(tmp_path / 'audit.jsonl')
    auth = LocalTrialIdentity(SimpleNamespace(data={'active':OWNER}))
    chat = Conversations(tmp_path, tmp_path, auth, codex_agent=agent)
    chat.catalog()
    calls = []
    monkeypatch.setattr(chat, '_start_worker', lambda *args, **kwargs: calls.append(args))
    body = {'chat':None,'question':'','sources':[],'preview':None,'model':IMAGE_MODEL,'effort':IMAGE_EFFORT,
            'request_id':str(uuid4()),'image':PNG_PREFIX+b64encode(PNG).decode('ascii')}
    return chat, body, calls


def test_attachment_atomic_replay_and_readback(composer):
    chat, body, calls = composer
    result = chat.submit(body)
    assert chat.submit(body) == result and len(calls) == 1
    assert calls[0][4][-1]['image'] == PNG
    assert chat.image(result['chat'],result['turn']) == PNG
    turn = chat.get(result['chat'])['turns'][0]
    assert turn['has_image'] and PNG_PREFIX not in str(turn)
    reopened = Conversations(chat.workspace, chat.path.parent, chat.auth, codex_agent=chat.codex_agent)
    assert reopened.image(result['chat'],result['turn']) == PNG
    with pytest.raises(ChatError):
        reopened.image(str(uuid4()),result['turn'])
    chat.auth.vault.data['active'] = 'different-owner'
    with pytest.raises(ChatError):
        reopened.image(result['chat'],result['turn'])


def test_followup_never_includes_previous_image_binary(composer):
    chat, body, calls = composer
    result = chat.submit(body)
    with chat.connect() as db:
        db.execute("UPDATE turns SET status='complete',answer='藍色圓形' WHERE id=?", (result['turn'],))
    body = {key:value for key,value in body.items() if key not in ('image','request_id')}
    chat.submit(body | {'chat':result['chat'],'question':'它是什麼顏色？'})
    inputs = calls[-1][4]
    assert len(inputs) == 3 and inputs[1]['content'] == '藍色圓形'
    assert all('image' not in m for m in inputs)
    chat.submit(body | {'question':'新對話'})
    assert len(calls[-1][4]) == 1 and 'image' not in calls[-1][4][0]


@pytest.mark.parametrize('override', [
    {'effort':'low'}, {'image':'https://example.invalid/test.png'}, {'image':PNG_PREFIX+'invalid'},
    {'sources':['git-work:receipt']}, {'question':'只在本機處理，不要外送'},
])
def test_ineligible_attachment_leaves_no_turn(composer, override):
    chat, body, calls = composer
    with pytest.raises(ChatError):
        chat.submit(body | override)
    assert not calls and not chat.snapshot()['chats']


def test_png_limits_and_appended_payload():
    assert decode_image(PNG_PREFIX+b64encode(PNG).decode('ascii')) == PNG
    for raw in (PNG+b'other data', PNG[:-1], b'GIF89a', b'z'*(4*1024*1024+1)):
        with pytest.raises(ChatError):
            decode_image(PNG_PREFIX+b64encode(raw).decode('ascii'))
