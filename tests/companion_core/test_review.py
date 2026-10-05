from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Barrier
from uuid import uuid4

import pytest

from src.companion_core.core import Companion
from src.companion_core.domain import Acceptance, Authority, Execution, Task
from src.companion_core.presentation import HumanView
from src.companion_core.review import ReviewError, ReviewStore, review_interactively, show_review
from src.companion_core.runtime import EventKind, RuntimeEvent


@pytest.fixture
def setup(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    task = Task(str(uuid4()), "唯讀檢視專案", str(workspace), "test-provider", Authority.READ_ONLY,
                Execution.COMPLETED, "session-1", "專案結果 → café — 繁體中文")
    return ReviewStore(tmp_path / "reviews", workspace=str(workspace)), task


@pytest.mark.parametrize("action,state", [("accept", "ACCEPTED"), ("reject", "REJECTED")])
def test_restart_exact_decision_and_duplicate_closed(setup, action, state):
    store, task = setup
    target = store.publish(task)
    restarted = ReviewStore(store.directory)
    assert restarted.get(task.id) == target
    assert target.task.state == "RESULT_PENDING_REVIEW"
    decided = restarted.decide(task.id, target.result_id, action, reviewer="human")
    assert decided.task.state == state and decided.task.authority == Authority.READ_ONLY
    assert decided.task.result == task.result
    original = (store.directory / f"{task.id}.decision.json").read_bytes()
    for again in ("accept", "reject", "revise"):
        with pytest.raises(ReviewError):
            store.decide(task.id, target.result_id, again, reviewer="other", revision_intent="new")
    assert (store.directory / f"{task.id}.decision.json").read_bytes() == original
    assert ReviewStore(store.directory).get(task.id).task.state == state
    assert restarted.pending() == []


def test_multiple_pending_wrong_unknown_and_stale_result_identity(setup):
    store, first = setup
    second = replace(first, id=str(uuid4()), result="另一份結果")
    a, b = store.publish(first), store.publish(second)
    assert len(store.pending()) == 2
    for task_id, result_id in ((first.id, b.result_id), (second.id, a.result_id),
                               (str(uuid4()), a.result_id), ("../outside", a.result_id),
                               (first.id, "0" * 64)):
        with pytest.raises(ReviewError):
            store.decide(task_id, result_id, "accept", reviewer="human")
    assert len(store.pending()) == 2
    store.decide(first.id, a.result_id, "reject", reviewer="human")
    assert [x.task.id for x in store.pending()] == [second.id]
    assert store.get(second.id).task.state == "RESULT_PENDING_REVIEW"


def test_late_or_duplicate_result_cannot_replace_pending_or_reviewed(setup):
    store, task = setup
    target = store.publish(task)
    for late in (task, replace(task, result="late replacement")):
        with pytest.raises(ReviewError):
            store.publish(late)
    store.decide(task.id, target.result_id, "accept", reviewer="human")
    with pytest.raises(ReviewError):
        store.publish(task)
    assert store.get(task.id).task.state == "ACCEPTED"
    assert store.get(task.id).task.result == task.result


@pytest.mark.parametrize("answer", ["好", "OK", "可以", "yes", "accept", "ACCEPT all", "", "批准"])
def test_ambiguous_input_never_mints_authority(setup, answer):
    store, task = setup
    target = store.publish(task)
    with pytest.raises(ReviewError):
        review_interactively(store, task.id, HumanView(lambda _: None), lambda: answer)
    assert store.get(task.id) == target
    # The host API's exact action name is not the CLI's case-sensitive input.
    if answer != "accept":
        with pytest.raises(ReviewError):
            store.decide(task.id, target.result_id, answer, reviewer="human")


def test_revision_is_new_unstarted_identity_with_atomic_provenance(setup):
    store, task = setup
    target = store.publish(task)
    reviewed = store.decide(task.id, target.result_id, "revise", reviewer="human",
                            revision_intent="請改為只列出公開產品名稱")
    assert reviewed.task.state == "REVISION_REQUESTED"
    assert reviewed.task.result == task.result and reviewed.result_id == target.result_id
    assert reviewed.revision.id != task.id
    assert reviewed.revision.state == "CREATED"
    assert reviewed.revision.authority == Authority.READ_ONLY
    assert reviewed.revision.session_id is None and reviewed.revision.result is None
    assert reviewed.revision.acceptance == Acceptance.UNREVIEWED
    assert ReviewStore(store.directory).get(task.id) == reviewed
    assert store.pending() == []
    with pytest.raises(ReviewError):
        store.decide(reviewed.revision.id, target.result_id, "accept", reviewer="human")
    output = []
    show_review(HumanView(output.append), reviewed)
    assert reviewed.revision.id in "\n".join(output) and "尚未執行" in "\n".join(output)


def test_revision_requires_explicit_nonempty_intent(setup):
    store, task = setup
    target = store.publish(task)
    for intent in (None, "", " "):
        with pytest.raises(ReviewError):
            store.decide(task.id, target.result_id, "revise", reviewer="human", revision_intent=intent)
    assert store.get(task.id) == target


@pytest.mark.parametrize("phase", ["preview", "decision_output"])
def test_presentation_failure_and_reconnect_do_not_mutate_review_truth(setup, phase):
    store, task = setup
    target = store.publish(task)
    def display(text):
        if phase == "preview" or text.startswith("審查決定已保存"):
            raise BrokenPipeError("private rendering body")
    view = HumanView(display)
    if phase == "preview":
        with pytest.raises(ReviewError):
            review_interactively(store, task.id, view, lambda: pytest.fail("must not read a decision"))
        assert store.get(task.id) == target
    else:
        review_interactively(store, task.id, view, lambda: "ACCEPT")
        assert ReviewStore(store.directory).get(task.id).task.state == "ACCEPTED"
    assert not view.available


def test_preview_then_stale_decision_cannot_rewrite_winner(setup):
    store, task = setup
    target = store.publish(task)
    def answer():
        store.decide(task.id, target.result_id, "reject", reviewer="other-human")
        return "ACCEPT"
    with pytest.raises(ReviewError):
        review_interactively(store, task.id, HumanView(lambda _: None), answer)
    assert store.get(task.id).task.state == "REJECTED"


def test_competing_decisions_have_exactly_one_winner(setup, monkeypatch):
    store, task = setup
    target = store.publish(task)
    barrier = Barrier(2)
    original = store._publish
    def publish(path, value):
        barrier.wait(timeout=5)
        original(path, value)
    monkeypatch.setattr(store, "_publish", publish)
    def decide(action):
        try:
            return store.decide(task.id, target.result_id, action, reviewer="human").task.state
        except ReviewError:
            return "closed"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(decide, ("accept", "reject")))
    assert results.count("closed") == 1
    assert store.get(task.id).task.state in results


@pytest.mark.parametrize("kind,contents", [("result", "{"), ("result", "{}"),
    ("result", '{"version":1,"version":1}'), ("decision", "{"), ("decision", "{}"),
    ("decision", '{"action":"accept"}'), ("decision", "null")])
def test_corrupt_or_incomplete_record_never_looks_accepted(setup, kind, contents):
    store, task = setup
    target = store.publish(task)
    path = store.directory / f"{task.id}.{kind}.json"
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(ReviewError):
        store.get(task.id)
    with pytest.raises(ReviewError):
        store.decide(task.id, target.result_id, "accept", reviewer="human")
    assert path.read_text(encoding="utf-8") == contents


def test_result_tampering_detected(setup):
    store, task = setup
    target = store.publish(task)
    path = store.directory / f"{task.id}.result.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["task"]["result"] = "tampered result"
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ReviewError):
        store.decide(task.id, target.result_id, "accept", reviewer="human")


@pytest.mark.parametrize("failure_at", ["fsync", "link"])
def test_failed_atomic_publication_leaves_pending_not_partial_acceptance(setup, monkeypatch, failure_at):
    store, task = setup
    target = store.publish(task)
    def fail(*args):
        raise OSError("private disk error")
    monkeypatch.setattr(os, failure_at, fail)
    with pytest.raises(ReviewError):
        store.decide(task.id, target.result_id, "accept", reviewer="human")
    assert store.get(task.id) == target
    assert not list(store.directory.glob("*.decision.json"))


def test_incomplete_temp_is_not_authoritative(setup):
    store, task = setup
    target = store.publish(task)
    (store.directory / ".review-crashed.tmp").write_text('{"action":"accept"', encoding="utf-8")
    assert store.get(task.id) == target
    assert store.pending() == [target]


@pytest.mark.parametrize("secret", ["Cookie: private", "Authorization: Bearer private", "sk-private",
    '"access_token": "private"', '{"jsonrpc":"2.0","params":{}}', "eyJabc.def.ghi"])
def test_unsafe_payload_is_never_persisted(setup, secret):
    store, task = setup
    for field in ("result", "intent", "session_id"):
        with pytest.raises(ReviewError):
            store.publish(replace(task, **{field: secret}))
    assert not store.directory.exists()


def test_state_cannot_live_in_repo_or_workspace(setup, tmp_path):
    _, task = setup
    with pytest.raises(ReviewError):
        ReviewStore(Path(task.workspace) / "state", workspace=task.workspace)
    other_repo = tmp_path / "repo"
    other_repo.mkdir()
    (other_repo / ".git").write_text("gitdir: other", encoding="utf-8")
    with pytest.raises(ReviewError):
        ReviewStore(other_repo / "ignored" / "state")


def test_preaccepted_or_incomplete_execution_cannot_publish(setup):
    store, task = setup
    for bad in (replace(task, acceptance=Acceptance.ACCEPTED), replace(task, execution=Execution.RUNNING),
                replace(task, reviewer="automatic"), replace(task, authority=Authority.NONE)):
        with pytest.raises(ReviewError):
            store.publish(bad)


def test_observer_failure_still_allows_durable_pending(setup):
    store, task = setup
    class Runtime:
        provider_id = "synthetic"
        def run(self, request):
            yield RuntimeEvent(EventKind.SESSION, session_id="s")
            yield RuntimeEvent(EventKind.COMPLETED, text="valid result")
    def broken(event):
        raise ValueError("render error")
    core = Companion(Runtime(), task.intent, task.workspace, Authority.READ_ONLY)
    completed = core.run(broken)
    saved = store.publish(completed)
    assert saved.task.state == "RESULT_PENDING_REVIEW"
    assert ReviewStore(store.directory).get(completed.id).task.result == "valid result"


def cli(store, *args, stdin=""):
    return subprocess.run([sys.executable, "-m", "src.companion_core", *args,
        "--review-dir", str(store.directory)], input=stdin, capture_output=True,
        encoding="utf-8", env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})


def test_fresh_cli_processes_preview_accept_and_readback_without_runtime(setup):
    store, task = setup
    target = store.publish(task)
    listed = cli(store, "pending")
    assert listed.returncode == 0 and task.id in listed.stdout
    shown = cli(store, "show", "--task", task.id)
    assert shown.returncode == 0 and task.result in shown.stdout
    assert target.result_id not in shown.stdout  # Digest is not the default human UI.
    rejected = cli(store, "review", "--task", task.id, stdin="OK\n")
    assert rejected.returncode == 1 and store.get(task.id) == target
    accepted = cli(store, "review", "--task", task.id, stdin="ACCEPT\n")
    assert accepted.returncode == 0 and "審查決定已保存：ACCEPTED" in accepted.stdout
    final = cli(store, "show", "--task", task.id, "--details")
    assert final.returncode == 0 and "獨立審查狀態：ACCEPTED" in final.stdout
    assert target.result_id in final.stdout and not final.stderr
    assert not list(Path(task.workspace).iterdir())


def test_cli_unknown_or_unspecified_target_never_selects_latest(setup):
    store, task = setup
    target = store.publish(task)
    assert cli(store, "review", stdin="ACCEPT\n").returncode == 1
    assert cli(store, "review", "--task", str(uuid4()), stdin="ACCEPT\n").returncode == 1
    assert store.get(task.id) == target


@pytest.mark.parametrize("answer,state", [("REJECT\n", "REJECTED"),
    ("REVISE\n只列出公開產品名稱\n", "REVISION_REQUESTED")])
def test_fresh_cli_reject_and_revision(setup, answer, state):
    store, task = setup
    store.publish(task)
    response = cli(store, "review", "--task", task.id, stdin=answer)
    assert response.returncode == 0 and "審查決定已保存：" + state in response.stdout
    target = ReviewStore(store.directory).get(task.id)
    assert target.task.state == state
    if state == "REVISION_REQUESTED":
        assert target.revision.id in response.stdout
        assert target.revision.intent == "只列出公開產品名稱"


@pytest.mark.parametrize("field,value", [("task_id", str(uuid4())), ("result_id", "0" * 64),
    ("version", True), ("action", "OK"), ("revision", {"id": "incomplete"})])
def test_mismatched_decision_record_fails_closed(setup, field, value):
    store, task = setup
    target = store.publish(task)
    store.decide(task.id, target.result_id, "accept", reviewer="human")
    path = store.directory / f"{task.id}.decision.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record[field] = value
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ReviewError):
        store.get(task.id)


def test_view_with_no_decision_does_not_consume_target(setup):
    store, task = setup
    target = store.publish(task)
    output = []
    show_review(HumanView(output.append), target)
    assert store.get(task.id) == target
    assert not list(store.directory.glob("*.decision.json"))
