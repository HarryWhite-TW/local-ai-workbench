"""Explicit Windows trial scope and synthetic NEXUS receipt setup."""
import hashlib
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from .chat import now
from .real_git_job import ensure_git_index
from .siwc import ChatError


OWNER = "nexus-hl04-local-studio"
TRIAL = Path(__file__).resolve().parents[3] / "daily-work-trial"
WORKSPACE = TRIAL / "workspace"
STATE = TRIAL / "state"


class LocalTrialIdentity:
    """Existing owner scope, independent of the model provider's subscription account."""

    pending = None

    def __init__(self, vault, *, owner=OWNER, notice=None):
        self.vault = vault
        self.owner = owner
        self.notice = notice or "本機資料限此合成工作區。模型選單只列已通過訂閱實測的模型與推理組合。"

    def snapshot(self):
        return {"active": self.owner, "pending": False,
                "accounts": [{"id": self.owner, "label": "隔離試用工作區", "signed_in": True}],
                "notice": self.notice}

    def access(self, _):
        raise ChatError("隔離模式僅使用既有 Codex 訂閱。")


def prepare_trial():
    if TRIAL.resolve() != TRIAL or WORKSPACE.resolve() != WORKSPACE or STATE.resolve() != STATE:
        raise ChatError("隔離試用目錄不可重新導向。")
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    for name, content in {
        "AGENTS.md": "# HL-04 隔離試用\n\n此工作區僅包含合成工作和測試資料。\n",
        "README.md": "# HL-04 合成工作區\n\n這裡的工作紀錄供 NEXUS 自然問答體驗。\n",
    }.items():
        path = WORKSPACE / name
        if path.resolve() != path:
            raise ChatError("隔離試用資料不可重新導向。")
        if not path.exists():
            path.write_text(content, encoding="utf-8")
    return WORKSPACE, STATE


def seed_receipts(chat):
    """Populate the existing chat and Git receipt schema with the approved synthetic examples."""
    rows = [
        ("W-09", "字幕時間對齊", "確認字幕位置", "2026-11-12", "UNKNOWN", None),
        ("W-18", "Reverb 預覽音量", "驗收預覽音量", "2026-11-16", "ACCEPTED", None),
        ("W-31", "Reverb 尾音匯出", "核對匯出尾音", "2026-11-20", "PENDING_REVIEW",
         "合成測試觀察：匯出尾端保留 240 個取樣，審查者尚未簽收。"),
        ("W-50", "封存用合成樣本", "archive-only-canary", "2026-11-21", "ACCEPTED", None),
        ("W-60", "其他帳戶的合成樣本", "guest-only-canary", "2026-11-22", "ACCEPTED", None),
    ]

    def fixture_id(kind, key):
        return str(uuid5(NAMESPACE_URL, f"nexus/hl03/{kind}/{key}"))

    with chat.connect() as db:
        ensure_git_index(db)
        for key, project, goal, date, state, detail in rows:
            ident = fixture_id("job", key)
            if db.execute("SELECT 1 FROM git_jobs WHERE id=?", (ident,)).fetchone():
                continue
            workspace = str(WORKSPACE.parent / "restricted") if key == "W-50" else chat.workspace
            owner = "nexus-hl03-other" if key == "W-60" else OWNER
            project_id, chat_id, turn_id = (fixture_id(kind, key) for kind in ("project", "chat", "turn"))
            captured = date + "T02:00:00+00:00"
            job = {"id": ident, "project": {"id": project_id, "name": project},
                   "goal": goal, "state": state, "recorded_at": captured, "events": []}
            if detail:
                job.update(verified={"head": "0" * 40, "sha256": hashlib.sha256(ident.encode()).hexdigest()},
                           targets=["synthetic/tail.py"],
                           verification="合成匯出尾音量測",
                           diff="--- a/synthetic/tail.py\n+++ b/synthetic/tail.py\n@@ -1 +1 @@\n-old_tail()\n+keep_tail()",
                           tests={"exitCode": 0, "stdout": detail, "stderr": ""},
                           events=[{"kind": "host_verified", "at": captured}])
            db.execute("INSERT INTO git_jobs VALUES (?,?,?,?)",
                       (ident, owner, project_id, json.dumps(job, ensure_ascii=False)))
            db.execute("INSERT INTO chats VALUES (?,?,?,?,?)",
                       (chat_id, workspace, owner, project + " · 合成工程", captured))
            db.execute("""INSERT INTO turns (id,chat,question,answer,sources,model,created,finished,status)
                          VALUES (?,?,?,?,?,?,?,?,?)""",
                       (turn_id, chat_id, goal, "已保存合成工程收據。", "[]", "NEXUS · Git 工程",
                        captured, now(), "complete"))
            db.execute("INSERT INTO git_job_links VALUES (?,?,?)", (chat_id, ident, turn_id))

