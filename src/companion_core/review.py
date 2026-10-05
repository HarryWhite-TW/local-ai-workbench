"""Local final-result receipts and single-use decisions, not a task queue.

The trusted local host owns this directory. Digests detect mismatched/corrupt
records; they are not signatures against an attacker with host write access.
Execution providers never receive this store or its decision API.
"""
from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from uuid import UUID, uuid4

from .domain import Acceptance, Authority, Execution, Task
from .presentation import safe_text


class ReviewError(ValueError):
    def __init__(self):
        super().__init__("Review record unavailable, unsafe, mismatched or already consumed")


def default_review_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "state")
    return base / "LocalAIWorkbench" / "Companion" / "reviews"


def _uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ReviewError()
    return value


def _text(value):
    if (not isinstance(value, str) or not value.strip() or safe_text(value) != value
            or re.search(r'jsonrpc|"(?:method|params)"\s*:|item/agentMessage|turn/completed',
                         value, re.IGNORECASE)):
        raise ReviewError()
    return value


def _encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReviewError()
        result[key] = value
    return result


@dataclass(frozen=True)
class ReviewTarget:
    task: Task
    result_id: str
    revision: Task | None = None


class ReviewStore:
    def __init__(self, directory: Path | str | None = None, *, workspace: str | None = None):
        self.directory = Path(directory or default_review_dir()).resolve()
        self.workspace = Path(workspace).resolve() if workspace else None
        self._location()

    def _location(self):
        # Reject repo-backed state even if ignored. Resolve links before checking.
        root = self.directory.resolve()
        if (root != self.directory or any((p / ".git").exists() for p in (root, *root.parents))
                or (self.workspace and root.is_relative_to(self.workspace))):
            raise ReviewError()

    def _path(self, task_id, kind):
        self._location()
        return self.directory / f"{_uuid(task_id)}.{kind}.json"

    def _read(self, path):
        try:
            if path.is_symlink() or path.stat().st_size > 4 * 1024 * 1024:
                raise ReviewError()
            return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique)
        except (OSError, ValueError, TypeError):
            raise ReviewError() from None

    def _publish(self, path, value):
        """Flush a private full file, then atomically link without replacement.

        A crash before linking leaves only a non-authoritative temporary file.
        A competing writer loses with FileExistsError, never last-writer-wins.
        Unsupported filesystems fail closed; there is no weaker fallback.
        """
        self._location()
        data = _encoded(value)
        if len(data) > 4 * 1024 * 1024:
            raise ReviewError()
        self.directory.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".review-", suffix=".tmp", dir=self.directory)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temporary, path)
        except OSError:
            raise ReviewError() from None
        finally:
            # Only our own temporary file; never remove/replace a published record.
            try:
                Path(temporary).unlink()
            except OSError:
                pass

    def publish(self, task: Task) -> ReviewTarget:
        if (task.state != "RESULT_PENDING_REVIEW" or task.authority is not Authority.READ_ONLY
                or task.reviewer is not None or task.failure is not None):
            raise ReviewError()
        payload = {"id": _uuid(task.id), "intent": _text(task.intent),
            "workspace": _text(task.workspace), "provider": _text(task.provider),
            "authority": "READ_ONLY", "session_id": _text(task.session_id),
            "result": _text(task.result)}
        if self.directory.is_relative_to(Path(task.workspace).resolve()):
            raise ReviewError()
        if self._path(task.id, "decision").exists():
            raise ReviewError()
        self._publish(self._path(task.id, "result"),
                      {"version": 1, "task": payload, "result_id": _digest(payload)})
        return self.get(task.id)

    def get(self, task_id: str) -> ReviewTarget:
        try:
            record = self._read(self._path(task_id, "result"))
            if set(record) != {"version", "task", "result_id"} or type(record["version"]) is not int or record["version"] != 1:
                raise ReviewError()
            payload = record["task"]
            if (set(payload) != {"id", "intent", "workspace", "provider", "authority", "session_id", "result"}
                    or payload["id"] != task_id or payload["authority"] != "READ_ONLY"
                    or record["result_id"] != _digest(payload)):
                raise ReviewError()
            for value in payload.values():
                _text(value)
            if self.directory.is_relative_to(Path(payload["workspace"]).resolve()):
                raise ReviewError()
            task = Task(**{**payload, "authority": Authority.READ_ONLY}, execution=Execution.COMPLETED)
            decision_path = self._path(task_id, "decision")
            if not decision_path.exists() and not decision_path.is_symlink():
                return ReviewTarget(task, record["result_id"])
            decision = self._read(decision_path)
            if (set(decision) != {"version", "task_id", "result_id", "action", "reviewer", "revision"}
                    or type(decision["version"]) is not int or decision["version"] != 1
                    or decision["task_id"] != task_id or decision["result_id"] != record["result_id"]):
                raise ReviewError()
            state = {"accept": Acceptance.ACCEPTED, "reject": Acceptance.REJECTED,
                     "revise": Acceptance.REVISION_REQUESTED}[decision["action"]]
            task = replace(task, acceptance=state, reviewer=_text(decision["reviewer"]))
            revision = None
            if state == Acceptance.REVISION_REQUESTED:
                child = decision["revision"]
                if set(child) != {"id", "intent"} or _uuid(child["id"]) == task_id:
                    raise ReviewError()
                revision = Task(child["id"], _text(child["intent"]), task.workspace,
                                task.provider, Authority.READ_ONLY)
            elif decision["revision"] is not None:
                raise ReviewError()
            return ReviewTarget(task, record["result_id"], revision)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            raise ReviewError() from None

    def pending(self) -> list[ReviewTarget]:
        self._location()
        targets = [self.get(p.name.removesuffix(".result.json"))
                   for p in sorted(self.directory.glob("*.result.json"))]
        return [t for t in targets if t.task.state == "RESULT_PENDING_REVIEW"]

    def decide(self, task_id: str, result_id: str, action: str, *, reviewer: str,
               revision_intent: str | None = None) -> ReviewTarget:
        target = self.get(task_id)
        if (target.task.state != "RESULT_PENDING_REVIEW" or result_id != target.result_id
                or action not in ("accept", "reject", "revise")):
            raise ReviewError()
        child = None
        if action == "revise":
            child = {"id": str(uuid4()), "intent": _text(revision_intent)}
        elif revision_intent is not None:
            raise ReviewError()
        self._publish(self._path(task_id, "decision"), {"version": 1, "task_id": task_id,
            "result_id": result_id, "action": action, "reviewer": _text(reviewer), "revision": child})
        return self.get(task_id)


def show_review(view, target: ReviewTarget):
    view._write("正在查看工作：" + target.task.id + "\n原始工作內容：" + target.task.intent)
    view.result(target.task)
    if target.revision:
        view._write("已建立新的唯讀工作（尚未執行）：" + target.revision.id +
                    "\n調整內容：" + target.revision.intent + "\n舊結果與此調整的關聯已保留。")
    if view.details:
        view._write("Result identity：" + target.result_id)
    view._write("此審查只影響 task 狀態，不授予 Git、發布或其他外部操作權限。")


def review_interactively(store: ReviewStore, task_id: str, view, read) -> ReviewTarget:
    target = store.get(task_id)
    show_review(view, target)
    if target.task.state != "RESULT_PENDING_REVIEW" or not view.available:
        raise ReviewError()
    view._write("請明確輸入 ACCEPT（接受此結果）、REJECT（拒絕此結果）或 REVISE（建立調整工作）；其他輸入不更動。")
    if not view.available:
        raise ReviewError()
    action = {"ACCEPT": "accept", "REJECT": "reject", "REVISE": "revise"}.get(read().strip())
    if action is None:
        raise ReviewError()
    intent = None
    if action == "revise":
        view._write("請輸入新工作的明確調整內容（不會自動執行）：")
        if not view.available:
            raise ReviewError()
        intent = read().strip()
    if not view.available:
        raise ReviewError()
    decided = store.decide(task_id, target.result_id, action, reviewer="local-human",
                           revision_intent=intent)
    view._write("審查決定已保存：" + decided.task.state)
    show_review(view, decided)
    return decided
