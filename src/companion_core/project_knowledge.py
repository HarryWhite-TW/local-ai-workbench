"""Owner-scoped NEXUS summaries with explicit sharing and immutable revisions."""
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import re
from time import monotonic
from uuid import uuid4

from .git_readback import normalize
from .resources import SENSITIVE_TEXT
from .siwc import ChatError


OWNER = "nexus-hl05-project"
ROOT = Path(__file__).resolve().parents[3] / "real-project"
WORKSPACE = ROOT / "NEXUS"
STATE = ROOT / "state"
SEED = Path(__file__).resolve().parents[2] / "docs/hl05-project-knowledge.json"
SOURCE_LABELS = {
    "coordination": "NEXUS 工程協調正式裁決",
    "repository": "NEXUS 已指定 Repository 文件",
    "evidence": "已指定 NEXUS 工程證據",
    "principles": "全面性準備與開工判斷原則 v1.1",
    "implementation": "已指定 NEXUS 候選與環境觀測",
    "validation": "HL-05 隔離更新驗證",
}
SOURCES_FOR = {
    "decision": {"coordination"},
    "historical": {"repository", "evidence"},
    "principle": {"repository", "principles"},
    "observation": {"implementation", "evidence"},
    "test": {"validation"},
}
MEMORY_KINDS = {
    "preference": "工作偏好", "context": "已確認工作脈絡", "tentative": "暫定方向",
    "settled": "使用者已選方向", "next-step": "未完成事項",
}
MEMORY_SOURCE = "conversation"
NOTE_FIELDS = {"slug", "kind", "source", "date", "title", "scope", "summary", "visibility"}
ID = re.compile(r"[a-z0-9][a-z0-9-]{0,47}\Z")
PRIVATE = re.compile(r"(?i)[a-z]:[\\/]|\\\\|/(?:users|home|etc|mnt|var|tmp)/|[\w.+-]+@[\w.-]+\.[a-z]{2,}|https?://|[\x00-\x08\x0b-\x1f\x7f]")
REFERENCE = re.compile(r"\[K:([a-z0-9-]+)@([0-9]+)\]")


def prepare_project(root=ROOT):
    workspace, state = root / "NEXUS", root / "state"
    if any(path.resolve() != path for path in (root, workspace, state)):
        raise ChatError("隔離專案目錄不可重新導向。")
    workspace.mkdir(parents=True, exist_ok=True)
    rules = workspace / "AGENTS.md"
    if rules.resolve() != rules:
        raise ChatError("隔離工作區文件不可重新導向。")
    if not rules.exists():
        rules.write_text("# NEXUS\n\n此工作區使用有來源且經核准分享的工程摘要。\n", encoding="utf-8")
    return workspace, state


def valid_record(value, *, memory=False):
    error = "請選擇已批准的來源類型，並僅填日期、範圍及非敏感工程摘要。"
    if not isinstance(value, dict) or value.keys() != NOTE_FIELDS:
        raise ChatError(error)
    limits = {"slug":48, "kind":16, "source":16, "date":10, "title":80,
              "scope":120, "summary":680, "visibility":12}
    if any(not isinstance(v,str) or not 1 <= len(v.strip()) <= limits[k]
           or PRIVATE.search(v) or SENSITIVE_TEXT.search(v) for k,v in value.items()):
        raise ChatError(error)
    value = {key: value[key].strip() for key in sorted(value)}
    sources = {kind: {MEMORY_SOURCE} for kind in MEMORY_KINDS} if memory else SOURCES_FOR
    if (not ID.fullmatch(value["slug"]) or value["source"] not in sources.get(value["kind"], ())
            or value["visibility"] not in ("shared", "local")):
        raise ChatError(error)
    try:
        if date.fromisoformat(value["date"]).isoformat() != value["date"]:
            raise ValueError
    except ValueError:
        raise ChatError(error) from None
    return value


class ProjectKnowledge:
    def __init__(self, chat, seed=SEED):
        self.chat = chat
        self.pending = None
        self.memory_pending = None
        self.owner = chat._project_owner(None)
        self.workspace = chat.workspace
        with chat.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS project_knowledge (
                    revision INTEGER PRIMARY KEY, owner TEXT NOT NULL, workspace TEXT NOT NULL,
                    slug TEXT NOT NULL, version INTEGER NOT NULL, data TEXT NOT NULL,
                    provenance TEXT NOT NULL, sha256 TEXT NOT NULL,
                    UNIQUE(owner,workspace,slug,version));
                CREATE TABLE IF NOT EXISTS project_knowledge_turns (
                    turn TEXT PRIMARY KEY REFERENCES turns(id), revision INTEGER NOT NULL);
            """)
            if not self.revision(db):
                for item in json.loads(seed.read_text(encoding="utf-8")):
                    self.append(db, valid_record(item), 1, "approved_seed")

    def scope(self, db, chat_id=None):
        owner = self.chat._project_owner(db, chat_id, require_chat=chat_id is not None)
        if owner != self.owner or self.chat.workspace != self.workspace:
            raise ChatError("目前本機身分或工作區沒有此專案知識權限。")
        return owner, self.workspace

    def revision(self, db):
        return db.execute("SELECT COALESCE(MAX(revision),0) FROM project_knowledge WHERE owner=? AND workspace=?",
                          self.scope(db)).fetchone()[0]

    def append(self, db, record, version, provenance):
        encoded = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = sha256(encoded.encode()).hexdigest()
        db.execute("""INSERT INTO project_knowledge(owner,workspace,slug,version,data,provenance,sha256)
                      VALUES(?,?,?,?,?,?,?)""",
                   (*self.scope(db), record["slug"], version, encoded, provenance, digest))

    def rows(self, db):
        return [{**json.loads(row["data"]), "version":row["version"], "revision":row["revision"],
                 "provenance":row["provenance"],"sha256":row["sha256"]}
                for row in db.execute("""SELECT version,revision,data,provenance,sha256 FROM project_knowledge
                                        WHERE owner=? AND workspace=? ORDER BY revision DESC""", self.scope(db))]

    @staticmethod
    def latest(rows):
        result = {}
        for row in rows:
            result.setdefault(row["slug"], row)
        return result

    def history(self, db, chat_id):
        self.scope(db, chat_id)
        return self.revision(db), {row[0]:row[1] for row in db.execute(
            """SELECT k.turn,k.revision FROM project_knowledge_turns k JOIN turns t ON t.id=k.turn
               WHERE t.chat=?""", (chat_id,))}

    @staticmethod
    def mark(db, turn, revision):
        db.execute("INSERT OR IGNORE INTO project_knowledge_turns VALUES (?,?)", (turn, revision))

    def search(self, chat_id, turn, query, include_history=False, *, memory=False):
        with self.chat.connect() as db:
            self.scope(db, chat_id)
            if not self.chat.busy or self.chat.busy != {"chat":chat_id, "turn":turn}:
                raise ChatError("此回合沒有專案知識讀取權限。")
            rows = self.rows(db)
            latest = self.latest(rows)
            sealed_through = self.latest(row for row in rows if row["visibility"] != "shared")
            candidates = []
            term = normalize(query)[:220].strip()
            words = set(re.findall(r"[a-z0-9-]{2,}", term))
            for block in re.findall(r"[\u3400-\u9fff]+", term):
                words.update(block[i:i+2] for i in range(len(block)-1))
            for row in rows:
                if (row["source"] == MEMORY_SOURCE) != memory:
                    continue
                current = latest[row["slug"]]
                if row["visibility"] != "shared" or current["visibility"] != "shared":
                    continue
                if row["revision"] < sealed_through.get(row["slug"], {}).get("revision", 0):
                    continue
                superseded = row["revision"] != current["revision"]
                if superseded and (memory or not include_history):
                    continue
                title = normalize(row["title"]+" "+row["slug"])
                detail = normalize(row["summary"]+" "+row["scope"])
                score = (8 if term and term in title else 0) + (4 if term and term in detail else 0)
                score += sum(3*(word in title)+(word in detail) for word in words)
                if not term or score:
                    candidates.append((score, not superseded, row))
            candidates.sort(key=lambda item: (item[0],item[1],item[2]["slug"]=="mainline",
                                              item[2]["kind"]=="decision",item[2]["revision"]), reverse=True)
            found = []
            for _, current, row in candidates[:6]:
                if memory:
                    found.append({key: row[key] for key in ("title", "summary", "date")}
                                 | {"kind": MEMORY_KINDS[row["kind"]],
                                    "source": "使用者確認的對話記憶",
                                    "reference": f"[K:{row['slug']}@{row['version']}]"})
                    continue
                found.append({key:row[key] for key in ("title","summary","kind","date","scope","provenance","sha256")}
                             | {"source":SOURCE_LABELS[row["source"]],
                                "reference":f"[K:{row['slug']}@{row['version']}]",
                                "edition":"latest" if current else "superseded"})
            if found:
                self.mark(db, turn, self.revision(db))
            return found

    def manage(self, action, body):
        with self.chat.lock, self.chat.connect() as db:
            self.scope(db)
            if action == "list" and not body:
                return {"records": list(self.latest(row for row in self.rows(db) if row["source"] != MEMORY_SOURCE).values()),
                        "sources": SOURCE_LABELS, "kinds": {k:sorted(v) for k,v in SOURCES_FOR.items()}}
            if self.chat.busy:
                raise ChatError("請等目前回合完成，再更新模型可見的知識。")
            if action == "preview":
                return self.preview(db, body)
            if action in ("apply","cancel") and set(body)=={"approval"}:
                pending = self.pending
                if not pending or body["approval"] != pending["approval"] or monotonic() >= pending["until"]:
                    raise ChatError("此確認已失效，請重新預覽。")
                self.pending = None
                if action == "cancel":
                    return {"cancelled":True}
                if pending["revision"] != self.revision(db):
                    raise ChatError("知識已更新，請重新預覽。")
                if pending["unchanged"]:
                    return {"unchanged":True, "version":pending["version"]}
                self.append(db, pending["record"], pending["version"], "operator_confirmed")
                return {"updated":True, "version":pending["version"],"revision":self.revision(db)}
            raise ChatError("找不到指定知識操作。")

    def preview(self, db, body):
        action = body.get("action")
        rows = self.rows(db)
        if action=="upsert" and set(body)=={"action","record","decision_attested"}:
            record = valid_record(body["record"])
            if record["kind"]=="decision" and body["decision_attested"] is not True:
                raise ChatError("請確認此摘要對應已取得的正式裁決。")
        elif action in ("withdraw","expire") and set(body)=={"action","slug"}:
            if not isinstance(body["slug"],str):
                raise ChatError("請選擇既有知識。")
            old = self.latest(rows).get(body["slug"])
            if not old:
                raise ChatError("請選擇既有知識。")
            record = {key:old[key] for key in NOTE_FIELDS}
            record["visibility"] = "withdrawn" if action=="withdraw" else "expired"
        else:
            raise ChatError("知識更新格式不正確。")
        latest = self.latest(rows)
        old = latest.get(record["slug"])
        if old and old["source"] == MEMORY_SOURCE:
            raise ChatError("對話記憶請由聊天提出變更並確認。")
        if old and old["kind"] != record["kind"]:
            raise ChatError("資料性質須維持原類型，正式裁決請另建並明確確認。")
        same = old and all(old[key]==record[key] for key in NOTE_FIELDS)
        if len(rows)>=768 and not same:
            raise ChatError("專案知識版本已達上限。")
        approval = str(uuid4())
        version = (old["version"] if old else 0) + (0 if same else 1)
        self.pending = {"approval":approval,"record":record,"version":version,
                        "unchanged":bool(same),"revision":self.revision(db),"until":monotonic()+300}
        return {k:self.pending[k] for k in ("approval","record","version","unchanged")}


    def offer_memory(self, chat_id, turn, action, kind, title, summary, reference):
        with self.chat.lock, self.chat.connect() as db:
            self.scope(db, chat_id)
            if self.chat.busy != {"chat": chat_id, "turn": turn} or self.chat.cancel_event.is_set():
                raise ChatError("此回合不能建立記憶預覽。")
            rows = self.rows(db)
            if len(rows) >= 768:
                raise ChatError("專案知識與記憶版本已達上限。")
            current = None
            if action != "create":
                match = REFERENCE.fullmatch(reference)
                current = self.latest(rows).get(match[1]) if match else None
                if (not current or current["source"] != MEMORY_SOURCE or current["visibility"] != "shared"
                        or str(current["version"]) != match[2]):
                    raise ChatError("找不到目前仍可用的記憶版本。")
            if action == "withdraw":
                record = {key: current[key] for key in NOTE_FIELDS}
                record["visibility"] = "withdrawn"
            else:
                record = valid_record(dict(
                    slug=current["slug"] if current else f"memory-{uuid4().hex}",
                    kind=kind, source=MEMORY_SOURCE, date=date.today().isoformat(),
                    title=title, scope="使用者確認的工作記憶", summary=summary, visibility="shared",
                ), memory=True)
            self.memory_pending = {"chat": chat_id, "turn": turn, "action": action, "record": record,
                                   "version": current["version"] + 1 if current else 1,
                                   "revision": self.revision(db), "approval": str(uuid4()),
                                   "until": monotonic() + 300}

    def memory_preview(self, db, chat_id):
        self.scope(db, chat_id)
        pending = self.memory_pending
        if (not pending or pending["chat"] != chat_id or pending["until"] <= monotonic()
                or pending["revision"] != self.revision(db) or self.chat.busy):
            return None
        latest = db.execute("SELECT id,status FROM turns WHERE chat=? ORDER BY rowid DESC LIMIT 1",
                            (chat_id,)).fetchone()
        if not latest or latest["id"] != pending["turn"] or latest["status"] != "complete":
            return None
        record = pending["record"]
        return dict(turn=pending["turn"], action=pending["action"], approval=pending["approval"],
                    version=pending["version"], kind=MEMORY_KINDS[record["kind"]],
                    title=record["title"], summary=record["summary"])

    def confirm_memory(self, body):
        if not isinstance(body.get("chat"), str) or not isinstance(body.get("approval"), str):
            raise ChatError("記憶確認格式不正確。")
        with self.chat.lock, self.chat.connect() as db:
            current = self.memory_preview(db, body["chat"])
            if not current or body["approval"] != current["approval"]:
                raise ChatError("此記憶預覽已失效，請重新提出。")
            if body.get("action") == "cancel" and set(body) == {"chat", "approval", "action"}:
                self.memory_pending = None
                return {"cancelled": True}
            editing = current["action"] != "withdraw"
            fields = {"chat", "approval", "action"} | ({"title", "summary"} if editing else set())
            if body.get("action") != "apply" or set(body) != fields:
                raise ChatError("記憶確認格式不正確。")
            pending = self.memory_pending
            record = pending["record"]
            if editing:
                record = valid_record(record | {"title": body["title"], "summary": body["summary"]},
                                      memory=True)
            self.append(db, record, pending["version"], f"conversation_confirmed:{pending['turn']}")
            # Keep the original capture conversation usable at v1. A revision
            # request can contain the old wording even without a tool return,
            # so automatic replay of that conversation must use the old epoch.
            history_revision = self.revision(db) if editing and pending["action"] == "create" else pending["revision"]
            db.execute("""INSERT OR IGNORE INTO project_knowledge_turns
                          SELECT id,? FROM turns WHERE chat=?""", (history_revision, pending["chat"]))
            self.memory_pending = None
            return {"updated": True, "version": pending["version"], "action": pending["action"]}
