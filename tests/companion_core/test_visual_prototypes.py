from contextlib import closing
import http.client
from threading import Event, Thread
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.companion_core.chat import Conversations
from src.companion_core.codex_trial import LocalTrialIdentity
from src.companion_core.siwc import ChatError
from src.companion_core.surface import make_server
from src.companion_core.visual_prototypes import CSP, InvalidPrototype, VisualPrototypes, validate


@pytest.mark.parametrize(("markup", "style"), [
    ("<script></script>", ""),
    ("<main onclick='example'>Sample</main>", ""),
    ("<a href='/api/state'>Sample</a>", ""),
    ("<form></form>", ""),
    ("<svg></svg>", ""),
    ("<div><p>Sample</div></p>", ""),
    ("<main>Sample</main>", "@import 'same-origin.css';"),
    ("<main>Sample</main>", "main{background:url('/local-file')}"),
    ("<main>Sample</main>", "main{background:u\\72l('/local-file')}"),
    ("<main>Sample</main>", "main{content:'</style>'}"),
    ("<main>Sample</main>", "x"*14001),
    ("<main>"+"x"*18000+"</main>", ""),
    ("<span></span>"*361, ""),
])
def test_active_content_and_limits_are_rejected(markup, style):
    with pytest.raises(InvalidPrototype):
        validate("Sample", markup, style)


def test_css_can_express_layout_without_active_elements():
    html = '<main class="board"><h1>Compare &lt; or &amp;</h1><button>Preview</button></main>'
    css = '.board{display:grid;gap:1rem;background:linear-gradient(120deg,#ddd,#fff)}@media(max-width:400px){.board{display:block}}'
    document = validate("Test", html, css).document().decode()
    assert 'Compare &lt; or &amp;' in document and '<button type="button">Preview' in document
    assert css in document


@pytest.fixture
def chat(tmp_path):
    auth = LocalTrialIdentity(SimpleNamespace(data={"active":"test-owner"}), owner="test-owner")
    result = Conversations(tmp_path, tmp_path, auth)
    result.visuals = VisualPrototypes(result)
    result.cancel_event = Event()
    return result


def make_turn(chat, db, chat_id=None, owner="test-owner"):
    if not chat_id:
        chat_id = str(uuid4())
        db.execute("INSERT INTO chats VALUES (?,?,?,?,?)", (chat_id, chat.workspace, owner, "Test", "1"))
    turn = str(uuid4())
    db.execute("INSERT INTO turns(id,chat,question,sources,model,created,status) VALUES (?,?,?,?,?,?,?)",
               (turn, chat_id, "Show design", "[]", "model", "1", "pending"))
    return chat_id, turn


def save(chat, db, chat_id, turn, owner="test-owner", *, parent=None, complete=True):
    chat.busy = {"chat":chat_id, "turn":turn}
    chat.visuals.stage(chat_id, owner, turn, validate("Example", "<main>Example</main>", "", parent))
    db.execute("UPDATE turns SET status=? WHERE id=?", ("complete" if complete else "failed", turn))
    chat.visuals.finish(db, turn, complete)


def test_history_survives_reopen_and_failed_or_foreign_parent_is_never_published(chat):
    with chat.connect() as db:
        first_chat, first = make_turn(chat, db)
        save(chat, db, first_chat, first)
        _, second = make_turn(chat, db, first_chat)
        save(chat, db, first_chat, second, parent=first)
        _, failed = make_turn(chat, db, first_chat)
        save(chat, db, first_chat, failed, parent=second, complete=False)
        other_chat, wrong = make_turn(chat, db)
        save(chat, db, other_chat, wrong, parent=second)
        assert chat.visuals.list(db, other_chat, "test-owner") == []
    reopened = Conversations(chat.workspace, chat.path.parent, chat.auth)
    reopened.visuals = VisualPrototypes(reopened)
    visible = reopened.get(first_chat)["visual_prototypes"]
    assert visible == [{"turn":first, "parent":None, "title":"Example"},
                       {"turn":second, "parent":first, "title":"Example"}]
    assert b'<main>Example</main>' in reopened.visuals.document(first_chat, second)
    with pytest.raises(ChatError):
        reopened.visuals.document(other_chat, first)
    with pytest.raises(ChatError):
        reopened.visuals.document(first_chat, failed)
    reopened.auth.vault.data["active"] = "different-owner"
    with pytest.raises(ChatError):
        reopened.visuals.document(first_chat, first)


def test_render_route_requires_iframe_and_isolating_policy(chat):
    with chat.connect() as db:
        chat_id, turn = make_turn(chat, db)
        save(chat, db, chat_id, turn)
    with make_server(None, chat=chat) as server:
        thread = Thread(target=server.serve_forever)
        thread.start()
        try:
            route = f"/chat-visual/{chat_id}/{turn}"
            with closing(http.client.HTTPConnection("127.0.0.1", server.server_port)) as client:
                client.request("GET", route)
                response = client.getresponse()
                assert response.status == 404
                response.read()
                client.request("GET", route, headers={"Sec-Fetch-Dest":"iframe", "Sec-Fetch-Site":"cross-site"})
                response = client.getresponse()
                assert response.status == 403
                response.read()
                client.request("GET", route, headers={"Sec-Fetch-Dest":"iframe", "Sec-Fetch-Site":"same-origin"})
                response = client.getresponse()
                assert response.status == 200 and response.headers["Content-Security-Policy"] == CSP
                assert response.headers["Cache-Control"] == "no-store"
                assert b'<main>Example</main>' in response.read()
        finally:
            server.shutdown()
            thread.join()
