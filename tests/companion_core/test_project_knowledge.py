"""Exercise the owner, source-version and model-history boundaries without inference."""
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.companion_core.chat import Conversations, now
from src.companion_core.codex_trial import LocalTrialIdentity
from src.companion_core.codex_work_agent import CodexWorkAgent
from src.companion_core.project_knowledge import OWNER, ProjectKnowledge
from src.companion_core.siwc import ChatError


def note(summary="紫梧-731", **changes):
    return dict(slug="test-record", kind="test", source="validation", date="2026-11-24",
                title="驗證燈", scope="隔離測試", summary=summary, visibility="shared") | changes


@pytest.fixture
def chat(tmp_path):
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps([note()]), encoding="utf-8")
    host = Conversations(tmp_path, tmp_path,
                         LocalTrialIdentity(SimpleNamespace(data={"active": OWNER}), owner=OWNER),
                         codex_agent=CodexWorkAgent(tmp_path / "audit.jsonl"))
    host.knowledge = ProjectKnowledge(host, seed)
    return host


def preview(host, record, attested=False):
    return host.knowledge.manage("preview", {"action": "upsert", "record": record,
                                             "decision_attested": attested})


def apply(host, pending):
    return host.knowledge.manage("apply", {"approval": pending["approval"]})


def set_visibility(host, action):
    return apply(host, host.knowledge.manage("preview", {"action": action, "slug": "test-record"}))


def project_turn(host, owner=OWNER, workspace=None):
    chat_id, turn_id = str(uuid4()), str(uuid4())
    with host.connect() as db:
        db.execute("INSERT INTO chats VALUES (?,?,?,?,?)",
                   (chat_id, workspace or host.workspace, owner, "測試", now()))
        db.execute("""INSERT INTO turns (id,chat,model,question,sources,created,status)
                      VALUES (?,?,?,?,?,?,?)""", (turn_id, chat_id, "gpt-6.1-terra", "驗證？", "[]", now(), "pending"))
    host.busy = {"chat": chat_id, "turn": turn_id}
    return chat_id, turn_id


def retrieve(host, prior=False):
    ids = project_turn(host)
    try:
        return host.knowledge.search(*ids, "驗證燈", include_history=prior)
    finally:
        host.busy = None


def test_confirmed_updates_are_versioned_idempotent_and_failure_atomic(chat):
    assert retrieve(chat)[0]["reference"] == "[K:test-record@1]"
    pending = preview(chat, note("青梧-508"))
    assert retrieve(chat)[0]["summary"] == "紫梧-731"
    assert apply(chat, pending)["version"] == 2
    with pytest.raises(ChatError):
        apply(chat, pending)
    assert apply(chat, preview(chat, note("青梧-508"))) == {"unchanged": True, "version": 2}
    assert [(r["summary"], r["edition"]) for r in retrieve(chat, prior=True)] == [
        ("青梧-508", "latest"), ("紫梧-731", "superseded")]
    for invalid in [note("contact me at a@example.com"), note("Open C:\\Users\\example-user"),
                    note(date="2026-02-29"), note(source="coordination")]:
        with pytest.raises(ChatError):
            preview(chat, invalid)
    cancelled = preview(chat, note("未批准"))
    assert chat.knowledge.manage("cancel", {"approval": cancelled["approval"]}) == {"cancelled": True}
    with pytest.raises(ChatError):
        apply(chat, cancelled)
    assert retrieve(chat)[0]["summary"] == "青梧-508"


@pytest.mark.parametrize("visibility", ["withdraw", "expire", "local"])
def test_latest_inaccessible_record_hides_earlier_versions(chat, visibility):
    if visibility == "local":
        assert apply(chat, preview(chat, note("靛梧-966", visibility="local")))["version"] == 2
    else:
        assert set_visibility(chat, visibility)["version"] == 2
    assert retrieve(chat, prior=True) == []
    assert apply(chat, preview(chat, note("新授權版本")))["version"] == 3
    assert [item["summary"] for item in retrieve(chat, prior=True)] == ["新授權版本"]


def test_workspaces_accounts_review_and_current_turn_are_rechecked(chat, monkeypatch):
    for owner, workspace in [(OWNER, "another-workspace"), ("another-owner", chat.workspace)]:
        ids = project_turn(chat, owner, workspace)
        with pytest.raises(ChatError):
            chat.knowledge.search(*ids, "")
    ids = project_turn(chat)
    with pytest.raises(ChatError):
        chat.knowledge.search(ids[0], "unbound-turn", "")
    with pytest.raises(ChatError):
        preview(chat, note("脫離當前回合"))
    chat.busy = None
    formal = note(kind="decision", source="coordination")
    with pytest.raises(ChatError):
        preview(chat, formal)
    with pytest.raises(ChatError):
        preview(chat, formal, attested=True)
    formal = formal | {"slug": "separate-decision"}
    assert apply(chat, preview(chat, formal, attested=True))["version"] == 1
    pending = preview(chat, note("逾時測試"))
    monkeypatch.setattr("src.companion_core.project_knowledge.monotonic", lambda: float("inf"))
    with pytest.raises(ChatError):
        apply(chat, pending)


def test_change_prunes_project_derived_answers_across_models_but_keeps_independent_history(chat, monkeypatch):
    chat_id, seeded_turn = project_turn(chat)
    assert chat.knowledge.search(chat_id, seeded_turn, "驗證燈")
    chat.busy = None
    with chat.connect() as db:
        db.execute("UPDATE turns SET status='complete', answer=? WHERE id=?",
                   ("紫梧-731 [K:test-record@1]", seeded_turn))
        db.execute("""INSERT INTO turns (id,chat,model,question,answer,sources,created,status)
                      VALUES (?,?,?,?,?,?,?,?)""",
                   (str(uuid4()), chat_id, "gpt-6.1-terra", "一般問題", "獨立回答", "[]", now(), "complete"))
    captured = []
    monkeypatch.setattr(chat, "_start_worker", lambda *args, **_: captured.append(args))
    chat.catalog()
    prompt = {"chat": chat_id, "question": "再解釋一下", "sources": [], "preview": None,
              "model": "gpt-6.2-sol", "effort": "low"}
    derived = chat.submit(prompt)["turn"]
    assert "紫梧-731" in str(captured[-1][4])
    with chat.connect() as db:
        assert derived in chat.knowledge.history(db, chat_id)[1]
        db.execute("UPDATE turns SET status='complete', answer=? WHERE id=?", ("衍生舊回答", derived))
    set_visibility(chat, "withdraw")
    chat.submit(prompt | {"question": "之後的問題"})
    assert "獨立回答" in str(captured[-1][4])
    for private in ("紫梧-731", "衍生舊回答", "再解釋一下", "[K:test-record@1]"):
        assert private not in str(captured[-1][4])
