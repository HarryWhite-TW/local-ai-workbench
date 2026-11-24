"""Regression coverage for local Git work lookup from the chat entry point."""
import json
from threading import RLock
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.companion_core.chat import Conversations, LOCAL_MODEL, now
from src.companion_core.daily import WorkNotConnected
from src.companion_core.real_git_job import RealGitJob
from src.companion_core.review import ReviewStore
from src.companion_core.siwc import ChatError
from src.companion_core.surface import Surface
from test_daily_delegation import host, post, submit


def local_chat(root):
    workspace = root / "candidate"
    state = root / "real-git-job" / "state"
    workspace.mkdir(parents=True, exist_ok=True)
    state.mkdir(parents=True, exist_ok=True)
    vault = SimpleNamespace(data={"active": "fixture"})
    auth = SimpleNamespace(vault=vault, lock=RLock(), pending=None)
    auth.snapshot = lambda: {
        "active": vault.data["active"], "pending": False,
        "accounts": [{"id": "fixture", "label": "Isolated test", "signed_in": True}],
    }

    def must_not_access(account):
        raise AssertionError("A readback must not access an external model")

    auth.access = must_not_access
    chat = Conversations(workspace, state, auth)
    chat.catalog = lambda: []
    chat.engineering_pilot = RealGitJob(chat, executable=None)
    return chat


def conversation(db, chat, ident, *, owner="fixture", workspace=None):
    db.execute("INSERT INTO chats VALUES (?,?,?,?,?)",
               (ident, workspace or chat.workspace, owner, "工程接續測試", now()))


def job(name, goal, *, state="PENDING_REVIEW", output="Python syntax OK\n"):
    return {
        "id": str(uuid4()), "project": {"id": str(uuid4()), "name": name},
        "state": state, "goal": goal, "targets": ["src/fixture.py"],
        "verification": "保存的驗證範圍", "tests": {"exitCode": 0, "stdout": output, "stderr": ""},
        "verified": {"head": "a" * 40, "sha256": "b" * 64},
        "diff": "--- a/src/fixture.py\n+++ b/src/fixture.py\n+value = 1\n",
        "events": [{"kind": "host_verified", "at": now()}],
        "thread_id": "history-thread", "turn_id": "history-turn",
    }


def store_job(db, record, chat_id, *, owner="fixture"):
    db.execute("INSERT INTO git_jobs VALUES (?,?,?,?)",
               (record["id"], owner, record["project"]["id"], json.dumps(record)))
    db.execute("INSERT INTO git_job_links VALUES (?,?,?)", (chat_id, record["id"], str(uuid4())))


@pytest.fixture
def lab(tmp_path):
    chat = local_chat(tmp_path)
    first = job("Orion Core", "編碼調整", output="9 passed in 0.14s\n")
    second = job("Orion Core", "不同的文字輸出修正")
    other = job("Aurora Tools", "修正未完成的匯入", state="RUNNING")
    with chat.connect() as db:
        for name in ("original", "linked", "second", "other"):
            conversation(db, chat, name)
        conversation(db, chat, "wrong-workspace", workspace=str(tmp_path / "elsewhere"))
        conversation(db, chat, "wrong-account", owner="different")
        store_job(db, first, "linked")
        store_job(db, second, "second")
        store_job(db, other, "other")
        store_job(db, job("Outer Workspace", "不可讀取"), "wrong-workspace")
        store_job(db, job("Private Account", "不可讀取"), "wrong-account", owner="different")
    return SimpleNamespace(chat=chat, first=first, second=second, other=other, root=tmp_path,
                           surface=Surface(WorkNotConnected(), chat.workspace, ReviewStore(tmp_path / "reviews")))


def answer(chat, result):
    turn = next(t for t in chat.get(result["chat"])["turns"] if t["id"] == result["turn"])
    assert turn["model"] == LOCAL_MODEL
    assert turn["sources"] == []
    return turn["answer"]


def test_chat_finds_linked_receipt_and_replays_identically(lab):
    request = submit("上次 Orion 那件工程工作做到哪裡了？先前有哪些測試結果？接下來建議怎麼做？", chat="linked")
    with host(lab) as server:
        code, result = post(server, "send", request)
        assert code == 200 and result["chat"] == "linked"
        assert post(server, "send", request) == (code, result)
    body = answer(lab.chat, result)
    for expected in (lab.first["id"], "9 passed", "src/fixture.py", "PENDING_REVIEW", "UNKNOWN", "建議下一步"):
        assert expected in body
    assert lab.second["id"] not in body


def test_ambiguity_selection_and_follow_up_survive_host_reopen(lab):
    chat = lab.chat
    unclear = answer(chat, chat.submit(submit("上次 Orion Core 的工程進度如何？")))
    assert "找到多筆" in unclear and "9 passed" not in unclear
    assert lab.first["id"] in unclear and lab.second["id"] in unclear
    reopened = local_chat(lab.root)
    assert "找到多筆" in answer(reopened, reopened.submit(submit("第 9 筆")))
    chosen = reopened.submit(submit("我指的是第一筆"))
    body = answer(reopened, chosen)
    assert lab.second["id"] in body and "9 passed" not in body
    assert "Python 語法檢查通過" in body
    reopened = local_chat(lab.root)
    assert answer(reopened, chosen) == body
    follow = answer(reopened, reopened.submit(submit("那跑了哪些測試？")))
    assert lab.second["id"] in follow and "UNKNOWN" in follow


def test_second_project_requires_receipt_and_maps_unconfirmed_state(lab):
    chat = lab.chat
    first = answer(chat, chat.submit(submit("Aurora Tools 的工作目前還剩什麼、做到哪裡？")))
    assert "UNKNOWN" in first and "不足以核實" in first
    assert lab.other["id"] in first and lab.first["id"] not in first
    reopened = local_chat(lab.root)
    assert "UNKNOWN" in answer(reopened, reopened.submit(submit("那下一步呢？")))
    damaged = {**lab.first, "tests": {"exitCode": 99, "stdout": "", "stderr": "invalid"}}
    with reopened.connect() as db:
        reopened.engineering_pilot.update(db, damaged)
    selected = answer(reopened, reopened.submit(submit(lab.first["id"])))
    assert "PENDING_REVIEW" in selected and "不足以核實" in selected
    tests = {"exitCode": 1, "stdout": "", "stderr": "fixture test failed"}
    with reopened.connect() as db:
        reopened.engineering_pilot.update(db, {**lab.other, "state": "UNKNOWN", "tests": tests,
            "events": [{"kind": "host_verification", "at": now(), "result": tests}]})
    selected = answer(reopened, reopened.submit(submit(lab.other["id"])))
    assert "主機驗證事件記錄退出碼 1" in selected and "UNKNOWN" in selected


def test_no_foreign_receipts_no_implicit_sharing_and_no_new_execution(lab):
    chat = lab.chat
    for name in ("Outer Workspace", "Private Account", "Unregistered"):
        assert "未找到" in answer(chat, chat.submit(submit(f"{name} 工程的狀態？")))
    for foreign in ("wrong-workspace", "wrong-account"):
        with pytest.raises(ChatError):
            chat.submit(submit("Orion 的工程結果？", chat=foreign))
    with pytest.raises(ChatError, match="選擇此帳戶的模型"):
        chat.submit(submit("Orion 的工程結果？", sources=["git-work:" + lab.first["id"]]))

    assert "9 passed" in answer(chat, chat.submit(submit(lab.first["id"])))
    received = []
    chat.models = [{"slug": "fake", "reasoning_efforts": []}]
    chat.models_account = "fixture"
    chat.auth.access = lambda account: "fixture-only"

    def infer(model, token, inputs, sources):
        received.append((inputs, sources))
        return "自然對話維持可用。", "fake-response"

    chat._infer = infer
    chat.submit(submit("嗨，幫我想一個名稱。", model="fake"))
    chat.worker.join(5)
    assert len(received) == 1
    assert len(received[0][0]) == 1 and received[0][1] == []
    assert "9 passed" not in json.dumps(received)
    chat.submit(submit("那跑了哪些測試？", model="fake"))
    chat.worker.join(5)
    assert len(received) == 2 and "9 passed" not in json.dumps(received)
