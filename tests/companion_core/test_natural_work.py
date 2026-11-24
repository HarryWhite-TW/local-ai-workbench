"""Safety and conversation contracts for staged natural work discussion."""
import json

import pytest

from src.companion_core.siwc import ChatError
from test_daily_delegation import host, post, submit
from test_git_readback import job, lab, local_chat, store_job


def arm(chat, routing):
    requests = []
    chat.models = [{"slug": "fixture-model", "reasoning_efforts": []}]
    chat.models_account = "fixture"
    chat.auth.access = lambda account: "fixture-token"

    def infer(model, token, inputs, sources):
        ctx = chat._delivery_context
        requests.append((ctx.copy(), inputs, sources))
        if ctx["routing"]:
            route = next(routing)
            return json.dumps({"intent": "chat", "reference": "", "choice": 0, "answer": "", "receipt_use": "preview", **route}), "router"
        assert ctx["work_analysis"]
        return "這只代表指定範圍的檢查。操作層級的行為仍需要另外驗證。[S1:L1]", "analysis"

    chat._infer = infer
    return requests


def scene(conversation, question, **fields):
    result = conversation.submit(submit(question, model="fixture-model", **fields))
    conversation.worker.join(5)
    assert not conversation.busy
    return result, turn(conversation, result)


def turn(chat, result):
    return next(t for t in chat.get(result["chat"])["turns"] if t["id"] == result["turn"])


def approve(conversation, result, preview, **overrides):
    return conversation.confirm_work_share({**result, "action": "share", "sha256": preview["sha256"], **overrides})


def test_choice_question_and_followup_survive_restart_without_implicit_sharing(lab):
    chat = lab.chat
    replies = iter([{"intent": "named", "reference": "Orion"}, {"intent": "choice", "choice": 2}])
    calls = arm(chat, replies)
    _, options = scene(chat, "想知道 Orion 以前交代的事情有留下什麼")
    assert lab.first["id"] in options["answer"] and lab.second["id"] in options["answer"]
    selected, preview = scene(chat, "後者就好，請說說那批測試到底說明什麼。")
    assert preview["delivery_state"] == "awaiting_work_share"
    assert preview["work_share"]["key"] == "git-work:" + lab.first["id"]
    assert preview["sources"] == [] and len(calls) == 2
    assert "9 passed" not in json.dumps(calls, ensure_ascii=False)
    assert lab.first["id"] not in json.dumps(calls)
    with host(lab) as server:
        assert post(server, "git-context-share", {**selected, "action": "share", "sha256": "wrong"})[0] == 409
        assert post(server, "git-context-share", {**selected, "action": "share",
                    "sha256": preview["work_share"]["sha256"]})[0] == 200
    chat.worker.join(5)
    resolved = turn(chat, selected)
    assert resolved["status"] == "complete"
    assert resolved["sources"] == [preview["work_share"]]
    assert "9 passed" in calls[-1][1][-1]["content"]
    assert "操作層級" in resolved["answer"] and len(calls) == 3
    with pytest.raises(ChatError):
        approve(chat, selected, preview["work_share"])
    reopened = local_chat(lab.root)
    calls = arm(reopened, iter([{"intent": "focus"}, {"intent": "other", "switch_scope": "project"}]))
    _, next_preview = scene(reopened, "光靠這些，足以說已經確認全部行為了嗎？")
    assert next_preview["work_share"] == preview["work_share"]
    assert "9 passed" not in json.dumps(calls, ensure_ascii=False)
    _, other = scene(reopened, "等一下，我要換一個專案，先列可能的那件。")
    assert lab.other["id"] in other["answer"] and lab.first["id"] not in other["answer"]


def test_preview_is_scoped_and_revalidated_and_decline_never_calls_model(lab):
    chat = lab.chat
    calls = arm(chat, iter([{"intent": "named", "reference": "Orion"}, {"intent": "focus"}, {"intent": "focus"}]))
    selected, preview = scene(chat, "Orion 之前查到什麼？", chat="linked")
    assert preview["work_share"]["key"] == "git-work:" + lab.first["id"]
    for foreign in ("second", "wrong-account", "wrong-workspace"):
        with pytest.raises(ChatError):
            approve(chat, selected, preview["work_share"], chat=foreign)
    altered = {**lab.first, "diff": lab.first["diff"] + "+changed\n"}
    with chat.connect() as db:
        chat.engineering_pilot.update(db, altered)
    with pytest.raises(ChatError):
        approve(chat, selected, preview["work_share"])
    assert len(calls) == 1
    selected, preview = scene(chat, "它還有什麼不確定？", chat="linked")
    chat.confirm_work_share({**selected, "action": "decline"})
    declined = turn(chat, selected)
    assert declined["delivery_state"] == "work_share_declined"
    assert "9 passed" in declined["answer"] and "UNKNOWN" in declined["answer"]
    assert not declined["sources"] and "work_share" not in declined
    assert len(calls) == 2
    stale, waiting = scene(chat, "先看得出來哪些行為沒驗證嗎？", chat="linked")
    reopened = local_chat(lab.root)
    read = turn(reopened, stale)
    assert read["delivery_state"] == "work_share_expired" and "work_share" not in read
    with pytest.raises(ChatError):
        approve(reopened, stale, waiting["work_share"])
    assert len(calls) == 3


def test_ordinary_and_unknown_go_through_one_model_call_without_receipt(lab):
    chat = lab.chat
    calls = arm(chat, iter([{"intent": "named", "reference": "Aurora Tools"},
                           {"intent": "chat", "answer": "我會選蛋餅。"},
                           {"intent": "resume"}, {"intent": "named", "reference": "Orion"}]))
    _, unknown = scene(chat, "Aurora Tools 那件需要人手決定嗎？")
    assert "UNKNOWN" in unknown["answer"] and "work_share" not in unknown
    _, ordinary = scene(chat, "另外幫我想早餐要吃什麼。")
    assert ordinary["answer"] == "我會選蛋餅。"
    assert ordinary["status"] == "complete"
    _, resumed = scene(chat, "回到早餐之前我們提過的工程工作。")
    assert lab.other["id"] in resumed["answer"] and "UNKNOWN" in resumed["answer"]
    _, invented = scene(chat, "另一個專案的工作還好嗎？")
    assert "還無法確認" in invented["answer"] and "work_share" not in invented
    assert len(calls) == 4 and all(not call[2] for call in calls)

def test_original_ordinal_survives_share_expiry_chat_restart_and_catalog_reordering(lab):
    chat = lab.chat
    arm(chat, iter([{"intent": "named", "reference": "Orion"},
                    {"intent": "choice", "choice": 1},
                    {"intent": "chat", "answer": "可以。"}]))
    _, listing = scene(chat, "Orion 那些工作做到哪了？")
    assert listing["answer"].index(lab.second["id"]) < listing["answer"].index(lab.first["id"])
    old, waiting = scene(chat, "先看第一筆。")
    assert waiting["work_share"]["key"].endswith(lab.second["id"])
    chat.work_share["expires"] = 0
    assert turn(chat, old)["delivery_state"] == "work_share_expired"
    scene(chat, "先插一句，週末會放假嗎？")
    with chat.connect() as db:
        store_job(db, job("Orion Core", "新增的另一筆工作"), "second")

    reopened = local_chat(lab.root)
    calls = arm(reopened, iter([{"intent": "named", "reference": "Orion", "choice": 2}]))
    result, preview = scene(reopened, "我想看第二筆 Orion 工作，請根據這次實際保存的驗證紀錄，分析它究竟證明了什麼。")
    assert preview["work_share"]["key"] == "git-work:" + lab.first["id"]
    assert "最近已顯示的清單有 2 個選項" in calls[0][0]["routing"]
    assert not calls[0][2]
    approve(reopened, result, preview["work_share"])
    reopened.worker.join(5)
    assert "究竟證明了什麼" in calls[-1][1][-1]["content"]
    assert "9 passed" in calls[-1][1][-1]["content"]


def test_conflicting_past_lists_ask_and_explicit_recent_list_resolves(lab):
    chat = lab.chat
    new_job = job("Orion Core", "較新的驗證")
    calls = arm(chat, iter([{"intent": "named", "reference": "Orion"},
                           {"intent": "named", "reference": "Orion"},
                           {"intent": "chat", "answer": "好。"},
                           {"intent": "choice", "reference": "Orion", "choice": 2}]))
    scene(chat, "先列 Orion 的工作。")
    with chat.connect() as db:
        store_job(db, new_job, "second")
    scene(chat, "再列一次 Orion。")
    scene(chat, "順帶一提，謝謝。")
    _, clarify = scene(chat, "Orion 的第二份驗證，請幫我看。")
    assert "指向不同工作" in clarify["answer"]
    assert lab.first["id"] in clarify["answer"] and lab.second["id"] in clarify["answer"]
    assert "work_share" not in clarify and all(not call[2] for call in calls)

    calls = arm(chat, iter([{"intent": "chat", "answer": "好。"},
                           {"intent": "choice", "choice": 1, "list_scope": "latest"}]))
    scene(chat, "早餐先不用聊了。")
    _, preview = scene(chat, "就選剛才最後列出的第一個，看看結果。")
    assert preview["work_share"]["key"] == "git-work:" + lab.second["id"]


def test_explicit_and_semantic_local_only_never_prepare_receipt(lab, monkeypatch):
    chat = lab.chat
    calls = arm(chat, iter([{"intent": "named", "reference": "Orion"},
                           {"intent": "focus", "receipt_use": "local"},
                           {"intent": "focus"}]))
    original, preview = scene(chat, "Orion 前一次有什麼結果？", chat="linked")
    assert "work_share" in preview

    def forbidden(*args, **kwargs):
        pytest.fail("local-only turn tried to prepare an external receipt")

    monkeypatch.setattr(chat.engineering_pilot, "receipt_payload", forbidden)
    for question in (
        "這次請把工程紀錄留在我電腦，只說你能確認的部分。",
        "我想知道這筆工程的細節，但這次先不要把收據提供給模型。",
    ):
        _, answer = scene(chat, question, chat="linked")
        assert answer["delivery_state"] == "complete"
        assert "work_share" not in answer and answer["sources"] == []
        assert "本輪只用本機已保存的資訊" in answer["answer"]
        assert "9 passed" in answer["answer"] and "UNKNOWN" in answer["answer"]
    assert chat.work_share is None and all(not call[2] for call in calls)
    assert "9 passed" not in json.dumps(calls, ensure_ascii=False)
    with pytest.raises(ChatError, match="失效"):
        approve(chat, original, preview["work_share"])
    with pytest.raises(ChatError, match="移除已選收據"):
        chat.submit(submit("請不要分享驗證紀錄。", chat="linked", model="fixture-model",
                           sources=[preview["work_share"]["key"]],
                           preview={preview["work_share"]["key"]: preview["work_share"]["sha256"]}))

@pytest.mark.parametrize("question, decision", [
    ("能不能把之前做過的 Orion 工程找給我？", {"intent": "discover", "reference": "Orion"}),
    ("我想查第二筆 Orion 工作。之前的驗證能證明什麼？",
     {"intent": "choice", "reference": "Orion", "choice": 2}),
])
def test_new_chat_discovers_without_ids_and_keeps_original_question(lab, question, decision):
    chat = lab.chat
    calls = arm(chat, iter([decision, {"intent": "choice", "choice": 2}]))
    created, found = scene(chat, question, chat=None)
    assert "選" in found["answer"] and lab.second["id"] in found["answer"]
    assert found["answer"].index(lab.second["id"]) < found["answer"].index(lab.first["id"])
    assert "work_share" not in found and found["sources"] == []
    assert len(calls) == 1 and calls[0][2] == []

    reopened = local_chat(lab.root)
    calls = arm(reopened, iter([{"intent": "choice", "choice": 2}]))
    selected, preview = scene(reopened, "就下面那份，說說實際結果。", chat=created["chat"])
    assert preview["work_share"]["key"] == "git-work:" + lab.first["id"]
    assert preview["sources"] == [] and len(calls) == 1
    approve(reopened, selected, preview["work_share"])
    reopened.worker.join(5)
    assert question in calls[1][1][-1]["content"]
    assert "就下面那份，說說實際結果。" in calls[1][1][-1]["content"]
    assert "9 passed" in calls[1][1][-1]["content"]
    assert turn(reopened, selected)["status"] == "complete"


def test_fresh_chat_does_not_inherit_a_list_or_share_grant(lab):
    chat = lab.chat
    calls = arm(chat, iter([{"intent": "discover", "reference": "Orion"},
                           {"intent": "choice", "choice": 1},
                           {"intent": "choice", "choice": 1},
                           {"intent": "discover", "reference": "Orion"}]))
    _, found = scene(chat, "請列出 Orion 做過的工作。")
    assert lab.first["id"] in found["answer"]
    prior, preview = scene(chat, "我選第一個，看看它的測試。")
    assert preview["work_share"]["key"].endswith(lab.second["id"])
    created, unmatched = scene(chat, "找之前的第一個工作。", chat=None)
    assert created["chat"] != prior["chat"]
    assert "work_share" not in unmatched and not unmatched["sources"]
    assert all(record["id"] in unmatched["answer"] for record in (lab.first, lab.second, lab.other))
    with pytest.raises(ChatError):
        approve(chat, prior, preview["work_share"], chat=created["chat"])

    _, recovered = scene(chat, "那就直接找 Orion，以前做過什麼？", chat=created["chat"])
    assert lab.first["id"] in recovered["answer"] and lab.second["id"] in recovered["answer"]
    assert "work_share" not in recovered and all(not call[2] for call in calls)


@pytest.mark.parametrize("project, should_find", [("Aurora Tools", True), ("Outer Workspace", False),
                                                 ("Private Account", False)])
def test_cold_discovery_respects_project_scope_and_missing_evidence(lab, project, should_find):
    chat = lab.chat
    calls = arm(chat, iter([{"intent": "discover", "reference": project},
                           {"intent": "choice", "choice": 1}]))
    result, found = scene(chat, f"想找回 {project} 以前做過的工程。", chat=None)
    assert "work_share" not in found and not found["sources"]
    if should_find:
        assert lab.other["id"] in found["answer"] and lab.first["id"] not in found["answer"]
        _, follow = scene(chat, "那一筆有通過測試嗎？", chat=result["chat"])
        assert "UNKNOWN" in follow["answer"] and "不足以核實" in follow["answer"]
        assert "work_share" not in follow and not follow["sources"]
    else:
        assert "找不到符合" in found["answer"]
        assert project not in found["answer"]
    assert all(not call[2] for call in calls)


def test_second_project_selection_does_not_reuse_other_project_order(lab):
    chat = lab.chat
    calls = arm(chat, iter([{"intent": "discover", "reference": "Orion"},
                           {"intent": "choice", "choice": 2, "reference": "Aurora Tools"},
                           {"intent": "choice", "choice": 2, "reference": "Orion"}]))
    _, old = scene(chat, "找回 Orion 的所有工程。")
    assert old["answer"].index(lab.second["id"]) < old["answer"].index(lab.first["id"])
    _, switched = scene(chat, "先看 Aurora Tools 以前的第二件。")
    assert lab.other["id"] in switched["answer"] and lab.first["id"] not in switched["answer"]
    assert "請依這份清單選擇" in switched["answer"] and "work_share" not in switched
    _, preview = scene(chat, "回去看 Orion 的第二筆，之前到底驗了什麼？")
    assert preview["work_share"]["key"] == "git-work:" + lab.first["id"]
    assert all(not call[2] for call in calls)


def test_discovery_with_local_only_request_preserves_refusal_during_selection(lab):
    chat = lab.chat
    calls = arm(chat, iter([{"intent": "choice", "choice": 2, "reference": "Orion"},
                           {"intent": "choice", "choice": 2}]))
    _, listing = scene(chat, "我想看 Orion 第二筆的結果，但不要把收據提供給模型。")
    assert lab.first["id"] in listing["answer"] and "work_share" not in listing
    _, chosen = scene(chat, "就第二筆。")
    assert "本輪只用本機已保存的資訊" in chosen["answer"]
    assert lab.first["id"] in chosen["answer"] and "9 passed" in chosen["answer"]
    assert "work_share" not in chosen and all(not call[2] for call in calls)


def test_browse_without_a_name_despite_chat_classification_and_keep_only_user_history(lab):
    calls = arm(lab.chat, iter([
        {"intent": "chat", "answer": "可以先提供專案名稱。"},
        {"intent": "chat", "answer": "這個字是一個星座。"},
        {"intent": "choice", "choice": 1, "receipt_use": "local"},
        {"intent": "chat", "answer": "早餐想吃什麼？"},
    ]))
    initial = "我們以前一起做過哪些工程？"
    ticket, listing = scene(lab.chat, initial, chat=None)
    for record in (lab.first, lab.second, lab.other):
        assert record["id"] in listing["answer"]
    assert "Private Account" not in listing["answer"] and "Outer Workspace" not in listing["answer"]
    _, narrowed = scene(lab.chat, "Orion", chat=ticket["chat"])
    assert lab.first["id"] in narrowed["answer"] and lab.other["id"] not in narrowed["answer"]
    _, local = scene(lab.chat, "先看剛剛第一筆，在本機看就好。", chat=ticket["chat"])
    assert lab.second["id"] in local["answer"] and not local["sources"]
    _, ordinary = scene(lab.chat, "今天的早餐想吃什麼？", chat=ticket["chat"])
    assert ordinary["answer"] == "早餐想吃什麼？"
    sent = json.dumps(calls, ensure_ascii=False)
    assert initial in calls[1][1][0]["content"]
    for private in (lab.first["id"], lab.second["id"], lab.other["goal"], "src/fixture.py", "Python syntax OK"):
        assert private not in sent


def test_paged_discovery_rechecks_visibility_and_keeps_display_order(lab):
    with lab.chat.connect() as db:
        extra = [job("Vela", f"匯出格式 {n}") for n in range(14)]
        for record in extra:
            store_job(db, record, "second")
    calls = arm(lab.chat, iter([{"intent": "discover"}, {"intent": "more"}]))
    ticket, _ = scene(lab.chat, "最近做的事有哪些？", chat=None)
    def displayed(ticket):
        with lab.chat.connect() as db:
            return json.loads(db.execute("SELECT options FROM git_work_readbacks WHERE turn=?",
                                         (ticket["turn"],)).fetchone()[0])
    first_page = displayed(ticket)
    assert 1 < len(first_page) <= 10
    with lab.chat.connect() as db:
        store_job(db, job("Vela", "分頁期間新增"), "second")
    more, _ = scene(lab.chat, "再翻下去。", chat=ticket["chat"])
    second_page = displayed(more)
    assert second_page and not set(first_page).intersection(second_page)
    with lab.chat.connect() as db:
        db.execute("DELETE FROM git_job_links WHERE job=?", (second_page[0],))
    reopened = local_chat(lab.root)
    calls += arm(reopened, iter([{"intent": "choice", "choice": 1, "list_scope": "latest"}]))
    _, selection = scene(reopened, "我要看剛才那一頁的第一筆。", chat=ticket["chat"])
    assert "無法" in selection["answer"] and "work_share" not in selection
    assert all(not call[2] for call in calls)


def test_missed_name_then_short_clue_then_switch_within_project(lab):
    calls = arm(lab.chat, iter([
        {"intent": "discover", "reference": "Vega"},
        {"intent": "chat", "answer": "星座。"},
        {"intent": "choice", "choice": 2, "receipt_use": "local"},
        {"intent": "other", "switch_scope": "work"},
    ]))
    t, missed = scene(lab.chat, "幫我找 Vega 之前的驗證", chat=None)
    assert "work_share" not in missed and lab.other["id"] not in missed["answer"]
    _, found = scene(lab.chat, "Orion", chat=t["chat"])
    assert lab.first["id"] in found["answer"] and lab.second["id"] in found["answer"]
    _, chosen = scene(lab.chat, "我想看第二個，證據留本機。", chat=t["chat"])
    assert lab.first["id"] in chosen["answer"] and not chosen["sources"]
    _, switch = scene(lab.chat, "想換另一筆工程來看。", chat=t["chat"])
    assert lab.second["id"] in switch["answer"] and lab.first["id"] not in switch["answer"]
    assert all(not call[2] for call in calls)
