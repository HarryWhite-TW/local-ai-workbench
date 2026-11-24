"""Host tests for the Codex work index and one-use browser consent."""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.companion_core.chat import Conversations, now
from src.companion_core.codex_trial import LocalTrialIdentity, OWNER, seed_receipts
from src.companion_core.codex_work_agent import AWAITING, CodexWorkAgent, MODEL, RunningAgent
from src.companion_core.siwc import ChatError


@pytest.fixture
def host(tmp_path):
    agent = CodexWorkAgent(tmp_path / "audit.jsonl")
    auth = LocalTrialIdentity(SimpleNamespace(data={"active": OWNER}))
    chat = Conversations(tmp_path, tmp_path, auth, codex_agent=agent)
    seed_receipts(chat)
    return chat


def new_turn(chat):
    chat_id, turn = str(uuid4()), str(uuid4())
    with chat.connect() as db:
        db.execute("INSERT INTO chats VALUES (?,?,?,?,?)", (chat_id, chat.workspace, OWNER, "試用", now()))
        db.execute("""INSERT INTO turns (id,chat,question,model,sources,created,status)
                      VALUES (?,?,?,?,?,?,?)""", (turn, chat_id, "測試量到什麼？", MODEL, "[]", now(), "pending"))
        db.execute("INSERT INTO turn_delivery (turn,state,owner,workspace) VALUES (?,?,?,?)",
                   (turn, "pending", OWNER, chat.workspace))
    return chat_id, turn


def test_visible_scope_without_siwc(host):
    agent = host.codex_agent
    chat_id, _ = new_turn(host)
    rows = agent.jobs(host, chat_id, OWNER)
    assert sorted(agent.metadata(*row)["status"] for row in rows.values()) == [
        "ACCEPTED", "PENDING_REVIEW", "UNKNOWN"
    ]
    assert "canary" not in str(rows)
    for work_id, work in rows.items():
        assert agent.lookup(host, chat_id, OWNER, work_id) == work
        assert agent.lookup(host, chat_id, OWNER, "git_jobs#" + work_id) == work
    with host.connect() as db:
        restricted = db.execute("SELECT id FROM git_jobs").fetchall()
    hidden = {row["id"] for row in restricted} - rows.keys()
    assert len(hidden) == 2
    assert all(agent.lookup(host, chat_id, OWNER, "git_jobs#" + ident) is None for ident in hidden)
    with pytest.raises(ChatError):
        agent.jobs(host, chat_id, "other")
    options = {item["slug"]:item["reasoning_efforts"] for item in host.catalog()}
    assert options == {"gpt-6.2-sol": ["low", "medium"], MODEL: ["medium"]}
    with pytest.raises(ChatError):
        host.auth_action("login", {"account": None}, "http://127.0.0.1")


@pytest.mark.parametrize("action", ["share", "decline"])
def test_work_receipt_bound_to_turn_owner_and_digest(host, action):
    agent = host.codex_agent
    chat_id, turn = new_turn(host)
    other_chat, other_turn = new_turn(host)
    job = next(row[1] for row in agent.jobs(host, chat_id, OWNER).values()
               if row[1]["state"] == "PENDING_REVIEW")
    source = agent.source(job)
    host.busy = {"chat": chat_id, "turn": turn}

    async def simulate():
        grant = asyncio.create_task(agent.request_share(host, RunningAgent(), chat_id, turn, OWNER, job["id"], source))
        await asyncio.sleep(0)
        original_turn = host.get(chat_id)["turns"][-1]
        assert original_turn["delivery_state"] == AWAITING
        assert original_turn["work_share"] == source and original_turn["sources"] == []
        assert not host.get(other_chat)["turns"][-1].get("work_share")
        with pytest.raises(ChatError):
            agent.confirm(host, {"chat": other_chat, "turn": other_turn, "action": "share", "sha256": source["sha256"]})
        with pytest.raises(ChatError):
            agent.confirm(host, {"chat": chat_id, "turn": turn, "action": "share", "sha256": "wrong"})
        body = {"chat": chat_id, "turn": turn, "action": action}
        if action == "share":
            body["sha256"] = source["sha256"]
        assert agent.confirm(host, body) == {"chat": chat_id, "turn": turn}
        assert await asyncio.wait_for(grant, 1) == action
        with pytest.raises(ChatError):
            agent.confirm(host, body)

    asyncio.run(simulate())
    settled = host.get(chat_id)["turns"][-1]
    assert settled["sources"] == ([source] if action == "share" else [])
    assert "work_share" not in settled


def test_next_turn_cannot_replay_shared_receipt_or_derived_answer(host, monkeypatch):
    chat_id, turn = new_turn(host)
    with host.connect() as db:
        db.execute("UPDATE turns SET status='complete', answer=?, sources=? WHERE id=?",
                   ("approved-derived-canary", '[{"key":"git-work:test","text":"private-source-canary"}]', turn))
        db.execute("UPDATE turn_delivery SET state='complete' WHERE turn=?", (turn,))
        db.execute("""INSERT INTO turns (id,chat,question,answer,model,sources,created,status)
                      VALUES (?,?,?,?,?,?,?,?)""",
                   (str(uuid4()), chat_id, "普通的前一題", "公開脈絡可接續", MODEL, "[]", now(), "complete"))
    captured = []
    monkeypatch.setattr(host, "_start_worker", lambda *args, **_: captured.append(args))
    host.catalog()
    body = {"chat": chat_id, "question": "那個呢？", "sources": [], "preview": None,
            "model": "gpt-6.2-sol", "effort": "low"}
    with pytest.raises(ChatError):
        host.submit({**body, "effort": "ultra"})
    assert not captured
    new_turn_data = host.submit(body)
    assert new_turn_data["chat"] == chat_id and new_turn_data["turn"] != turn
    inputs = captured[0][4]
    assert len(inputs) == 3 and inputs[1]["content"] == "公開脈絡可接續"
    assert "approved-derived-canary" not in str(inputs) and "private-source-canary" not in str(inputs)
    assert "測試量到什麼？" not in str(inputs)
    turn = host.get(chat_id)["turns"][-1]
    assert (turn["model"], turn["requested_effort"]) == ("gpt-6.2-sol", "low")

    another_chat = host.submit({"chat": None, "question": "以前做過哪些？", "sources": [], "preview": None, "model": MODEL})
    assert another_chat["chat"] != chat_id
    assert captured[1][4] == [{"role": "user", "content": "以前做過哪些？"}]


def test_core_approval_and_history_with_offline_stream(host, monkeypatch):
    import json
    from contextlib import asynccontextmanager
    from time import monotonic, sleep

    from pydantic_ai.messages import ToolReturnPart
    from pydantic_ai.models.function import DeltaToolCall, FunctionModel
    from src.companion_core import codex_work_agent

    model_inputs = []
    async def stream(messages, info):
        model_inputs.append(messages)
        call = len(model_inputs)
        if call == 1:
            yield {0: DeltaToolCall("search_works", '{"query":"尾音"}', tool_call_id="search")}
        elif call == 2:
            result = next(part.content for part in messages[-1].parts if isinstance(part, ToolReturnPart))
            yield {0: DeltaToolCall("read_work_evidence", json.dumps({"work_id":result[0]["source"]}),
                                    tool_call_id="evidence")}
        elif call == 3:
            result = next(part.content for part in messages[-1].parts if isinstance(part, ToolReturnPart))
            assert result["decision"] == "allowed"
            lines = result["evidence"].splitlines()
            index = next(i for i, line in enumerate(lines) if "240" in line)
            first_line, last_line = (line.split(":")[0] for line in lines[index - 1:index + 1])
            yield f"合成量測為 240 個取樣 [S1:{first_line}-{last_line}]。"
        elif call == 4:
            assert "240 個取樣" not in str(messages)
            assert "核對詳細收據" not in str(messages)
            assert "上一個完成回合的公開工作參照" in info.instructions
            assert "240 個取樣" not in info.instructions
            source = host.get(first["chat"])["turns"][0]["sources"][0]
            ref = "git_jobs#" + source["key"].removeprefix("git-work:")
            assert ref in info.instructions
            yield {0: DeltaToolCall("get_work", json.dumps({"work_id": ref}), tool_call_id="followup")}
        else:
            result = next(part.content for part in messages[-1].parts if isinstance(part, ToolReturnPart))
            assert result["status"] == "PENDING_REVIEW"
            yield "本輪重讀到這筆工作仍待審。"

    class LocalStream(FunctionModel):
        @asynccontextmanager
        async def request_stream(self, *args, **kwargs):
            async with super().request_stream(*args, **kwargs) as result:
                result.provider_response_id = f"synthetic-stream-{len(model_inputs)}"
                yield result

    async def fake_build(_check, _record, model_name):
        return LocalStream(stream_function=stream, model_name=model_name), None

    monkeypatch.setattr(codex_work_agent, "build_model", fake_build)
    host.catalog()
    body = {"chat": None, "question": "請核對詳細收據，看它測了什麼。", "sources": [], "preview": None, "model": MODEL}
    first = host.submit(body)
    deadline = monotonic() + 4
    while monotonic() < deadline:
        turn = host.get(first["chat"])["turns"][-1]
        if turn.get("work_share"):
            break
        sleep(0.02)
    assert turn["work_share"]["sha256"]
    host.confirm_work_share({**first, "action": "share", "sha256": turn["work_share"]["sha256"]})
    host.worker.join(4)
    assert not host.worker.is_alive()
    approved = host.get(first["chat"])["turns"][-1]
    assert approved["delivery_state"] == "complete" and "240" in approved["answer"]
    assert len(approved["sources"]) == 1

    host.submit({**body, "chat": first["chat"], "question": "後續呢？",
                 "model": "gpt-6.2-sol", "effort": "low"})
    host.worker.join(4)
    follow_up = host.get(first["chat"])["turns"][-1]
    assert follow_up["delivery_state"] == "complete" and "240" not in follow_up["answer"]
    assert (follow_up["model"], follow_up["requested_effort"]) == ("gpt-6.2-sol", "low")
    assert len(model_inputs) == 5

