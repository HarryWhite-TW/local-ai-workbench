"""Real Win32 file operations in isolated fixtures, with no model calls."""

from hashlib import sha256
import os
import subprocess
from threading import RLock
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.companion_core.chat import Conversations, now
from src.companion_core.siwc import ChatError

if os.name != "nt":
    pytest.skip("Windows handle and Explorer semantics", allow_module_level=True)

from src.companion_core import local_outputs


@pytest.fixture
def scenario(tmp_path):
    auth = SimpleNamespace(lock=RLock(), pending=None, vault=SimpleNamespace(data={"active": "fixture"}))
    chat = Conversations(tmp_path, tmp_path, auth)
    folder = local_outputs.OutputFolder(tmp_path / "outputs")
    controls = local_outputs.LocalOutputs(chat, folder)
    ident = str(uuid4())
    answer = "# Validated deliverable\n\nVerified fixture content."
    with chat.connect() as db:
        for chat_id, owner in [("source", "fixture"), ("second", "fixture"), ("foreign", "other")]:
            db.execute("INSERT INTO chats VALUES (?,?,?,?,?)", (chat_id, chat.workspace, owner, chat_id, now()))
        db.execute("INSERT INTO turns (id,chat,question,answer,sources,model,created,status) VALUES (?,?,?,?,?,?,?,?)",
                   (ident, "source", "fixture", answer, "[]", "fixture", now(), "complete"))

    def action(operation, **fields):
        return controls.respond(operation, {"chat": "source", **fields})

    return action, controls, folder, ident, answer + "\n", chat


def test_cancel_save_list_read_locate_and_no_conversation_mutation(scenario, monkeypatch):
    operation, _, folder, turn, text, chat = scenario
    before = chat.path.read_bytes()
    first = operation("preview", turn=turn)
    assert first["text"] == text and list(folder.root.iterdir()) == []
    operation("cancel", token=first["token"])
    with pytest.raises(ChatError, match="失效"):
        operation("save", token=first["token"])
    assert operation("list") == []
    grant = operation("preview", turn=turn)
    result = operation("save", token=grant["token"])
    path = folder.root / grant["name"]
    assert result["status"] == "SAVED" and result["path"] == str(path)
    assert path.read_bytes() == text.encode() and result["sha256"] == sha256(path.read_bytes()).hexdigest()
    assert [item["name"] for item in operation("list")] == [path.name]
    snapshot = operation("inspect", name=path.name)
    assert (snapshot["text"], snapshot["sha256"]) == (text, result["sha256"])
    called = []
    monkeypatch.setattr(local_outputs, "locate_in_explorer", called.append)
    assert operation("locate", token=snapshot["token"])["status"] == "EXPLORER_REQUESTED"
    assert called == [path]
    assert chat.path.read_bytes() == before
    with pytest.raises(ChatError, match="失效"):
        operation("save", token=grant["token"])


def test_rejects_collision_invalid_paths_and_changed_target(scenario, monkeypatch):
    operation, _, folder, turn, _, _ = scenario
    grant = operation("preview", turn=turn)
    path = folder.root / grant["name"]
    path.write_bytes(b"original")
    with pytest.raises(ChatError, match="沒有覆寫"):
        operation("save", token=grant["token"])
    assert path.read_bytes() == b"original"
    snapshot = operation("inspect", name=path.name)
    path.write_bytes(b"changed")
    monkeypatch.setattr(local_outputs, "locate_in_explorer", lambda _: pytest.fail("unexpected Explorer action"))
    with pytest.raises(ChatError, match="已變更"):
        operation("locate", token=snapshot["token"])
    assert operation("inspect", name=path.name)["text"] == "changed"
    for name in (str(path), "../" + path.name, path.name + ":data", "other.md"):
        with pytest.raises(ChatError, match="只接受"):
            operation("inspect", name=name)
    path.unlink()
    with pytest.raises(ChatError, match="不存在"):
        operation("inspect", name=path.name)


def test_folder_replacement_and_junction_are_refused(scenario, tmp_path):
    operation, _, folder, turn, _, _ = scenario
    grant = operation("preview", turn=turn)
    moved = tmp_path / "moved"
    folder.root.rename(moved)
    folder.root.mkdir()
    with pytest.raises(ChatError, match="已被替換"):
        operation("save", token=grant["token"])
    assert list(folder.root.iterdir()) == list(moved.iterdir()) == []
    junction = tmp_path / "junction"
    subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(moved)],
                   check=True, capture_output=True)
    with pytest.raises((ChatError, OSError)):
        local_outputs.OutputFolder(junction).list()


def test_pins_block_rename_and_scope_is_bound(scenario, tmp_path):
    operation, controls, folder, turn, _, chat = scenario
    grant = operation("preview", turn=turn)
    with folder.pin(), pytest.raises(PermissionError):
        folder.root.rename(tmp_path / "replacement")
    with pytest.raises(ChatError, match="時|失效"):
        operation("save", token=grant["token"], chat="second")
    with pytest.raises(ChatError, match="無權"):
        operation("preview", turn=turn, chat="foreign")
    chat.auth.vault.data["active"] = "other"
    with pytest.raises(ChatError, match="無權"):
        operation("save", token=grant["token"])
    assert list(folder.root.iterdir()) == []
    assert controls.pending["token"] == grant["token"]


def test_unknown_consumes_grant_and_explorer_failure_is_reported(scenario, monkeypatch):
    operation, _, folder, turn, _, _ = scenario
    grant = operation("preview", turn=turn)
    monkeypatch.setattr(os, "fsync", lambda _: (_ for _ in ()).throw(OSError("fixture failure")))
    assert operation("save", token=grant["token"])["status"] == "UNKNOWN"
    with pytest.raises(ChatError, match="失效"):
        operation("save", token=grant["token"])
    preview = operation("inspect", name=grant["name"])

    def failed(_):
        raise ChatError("檔案總管定位失敗。")

    monkeypatch.setattr(local_outputs, "locate_in_explorer", failed)
    with pytest.raises(ChatError, match="定位失敗"):
        operation("locate", token=preview["token"])
