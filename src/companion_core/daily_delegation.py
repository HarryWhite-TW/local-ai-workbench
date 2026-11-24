"""Rule-based work in the original conversation, using the existing E2 grants."""
import json
import re
from time import monotonic
from uuid import uuid4

from .chat import LOCAL_MODEL, now
from .local_outputs import NAME
from .siwc import ChatError


UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
LIST = re.compile(r"(?:列出|顯示|查看)(?:目前|所有)?(?:已保存的?|已儲存的?|本機)?(?:成果|成果清單|成果檔名)")
INSPECT = re.compile(r"(?:檢視|查看|打開|閱讀|看一下)\s*(?:成果\s*)?(?P<name>nexus-" + UUID + r"\.md)(?:\s*的內容)?")
PREVIEW = re.compile(r"(?:準備|預覽|產生)\s*(?:回答|回覆)\s*(?P<answer>" + UUID + r")\s*(?:的\s*)?(?:Markdown(?:\s*預覽)?|MD\s*預覽)", re.IGNORECASE)


def local_intent(question):
    if "\n" not in question and "\r" not in question:
        command = re.sub(r"^(?:請幫我|幫我|請|我想)\s*", "", question.strip()).rstrip("。！!").strip()
        if LIST.fullmatch(command):
            return {"kind": "list"}
        # Quoting an exact filename is allowed only after the top-level verb.
        command = re.sub(r'「(nexus-' + UUID + r'\.md)」', r'\1', command)
        if match := INSPECT.fullmatch(command):
            return {"kind": "inspect", "name": match["name"]}
        if match := PREVIEW.fullmatch(command):
            return {"kind": "preview", "answer": match["answer"]}
    else:
        command = question.lstrip()
    starts_action = re.match(
        r"^(?:請幫我|幫我|請|我想)?\s*(?:列出|顯示|查看|檢視|打開|閱讀|看一下|準備|預覽|產生|保存|儲存|寫入|覆寫|刪除|移動)",
        command,
    )
    if starts_action and re.search(r"成果|那篇|這篇|回答|回覆|Markdown|\.md\b|資料夾|[A-Za-z]:[\\/]", command, re.I):
        if re.match(r"^(?:保存|儲存|寫入|覆寫|刪除|移動)", command):
            return {"kind": "clarify", "message": "本機委派只能查詢成果或準備指定回答的預覽。寫入須在預覽後確認。"}
        return {"kind": "clarify"}
    return None


class DailyDelegation:
    def __init__(self, chat):
        self.chat = chat
        with chat.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS daily_delegations (
                turn TEXT PRIMARY KEY REFERENCES turns(id), step TEXT NOT NULL, data TEXT NOT NULL
            )""")
            db.execute("UPDATE daily_delegations SET step='UNKNOWN' WHERE step='SAVING'")
            db.execute("UPDATE daily_delegations SET step='INTERRUPTED' WHERE step='RUNNING'")

    @staticmethod
    def insert(db, turn, step, data):
        db.execute("INSERT INTO daily_delegations VALUES (?,?,?)",
                   (turn, step, json.dumps(data, ensure_ascii=False)))

    def update(self, turn, step, data):
        with self.chat.connect() as db:
            db.execute("UPDATE daily_delegations SET step=?,data=? WHERE turn=?",
                       (step, json.dumps(data, ensure_ascii=False), turn))

    @property
    def outputs(self):
        return self.chat.resources.outputs

    def active_grant(self, work, chat_id):
        grant = self.outputs.pending
        owner = (self.chat.auth.vault.data["active"], self.chat.workspace, chat_id)
        if (grant and grant.get("work") == work and grant["owner"] == owner
                and grant["until"] > monotonic()):
            return grant["token"]
        return None

    def for_turn(self, db, turn):
        row = db.execute("SELECT step,data FROM daily_delegations WHERE turn=?", (turn["id"],)).fetchone()
        if row is None:
            return None
        data, step = json.loads(row["data"]), row["step"]
        token = None
        # All writers hold chat.lock. A SAVING row seen by a reader has no confirmed receipt.
        if step == "SAVING":
            step = "UNKNOWN"
        if step == "AWAITING_ANSWER":
            delivery = turn.get("delivery_state", turn["status"])
            step = {"complete": "READY", "pending": "AWAITING_ANSWER", "cancelled": "CANCELLED",
                    "interrupted": "INTERRUPTED"}.get(delivery, "FAILED")
        if step == "AWAITING_SAVE":
            token = self.active_grant(turn["id"], turn["chat"])
            if token is None:
                step = "EXPIRED"
        return {**data, "step": step, "grant": token}

    def submit(self, body, account, digest, data):
        chat_id, question, work = body["chat"], body["question"].strip(), str(uuid4())
        with self.chat.connect() as db:
            if chat_id is None:
                chat_id = str(uuid4())
                db.execute("INSERT INTO chats VALUES (?,?,?,?,?)",
                           (chat_id, self.chat.workspace, account, question[:60], now()))
            else:
                self.chat._project_owner(db, chat_id, require_chat=True)
            ts = now()
            db.execute("""INSERT INTO turns (id,chat,question,sources,model,created,finished,status)
                          VALUES (?,?,?,?,?,?,?,?)""",
                       (work, chat_id, question, "[]", LOCAL_MODEL, ts, ts, "complete"))
            db.execute("""INSERT INTO turn_delivery (turn,state,request_key,request_hash,owner,workspace)
                          VALUES (?,?,?,?,?,?)""",
                       (work, "complete", body.get("request_id"), digest, account, self.chat.workspace))
            self.insert(db, work, "RUNNING", data)
        if body["sources"] != [] or body["preview"] is not None:
            self.update(work, "REJECTED", {"kind": "clarify",
                        "message": "本機委派只接受你輸入的直接指令。請先移除附加來源再提出本機要求。"})
        elif data["kind"] == "clarify":
            self.update(work, "REJECTED" if "message" in data else "CLARIFY", data)
        elif data["kind"] == "preview":
            self.prepare(work, chat_id, data)
        else:
            try:
                fields = {"name": data["name"]} if data["kind"] == "inspect" else {}
                result = self.outputs.respond(data["kind"], {"chat": chat_id, **fields})
                if fields:
                    result.pop("token", None)
                self.update(work, "COMPLETE", {**data, "result": result})
            except ChatError as exc:
                self.update(work, "FAILED", {**data, "message": str(exc)})
        return {"chat": chat_id, "turn": work}

    def prepare(self, work, chat_id, data):
        clean = {k: v for k, v in data.items() if k in ("kind", "answer", "e1", "generated")}
        try:
            result = self.outputs.respond("preview", {"chat": chat_id, "turn": clean["answer"]}, work=work)
            result.pop("token")
            self.update(work, "AWAITING_SAVE", {**clean, "preview": result})
        except ChatError as exc:
            self.update(work, "PREVIEW_FAILED", {**clean, "message": str(exc)})

    def offer_answer(self, db, turn):
        # E1 may have queued the same preview during the original submission.
        if not db.execute("SELECT 1 FROM daily_delegations WHERE turn=?", (turn,)).fetchone():
            self.insert(db, turn, "AWAITING_ANSWER", {"kind": "preview", "answer": turn, "generated": True})

    def finish_answer(self, work):
        with self.chat.connect() as db:
            row = db.execute("""SELECT d.data, t.chat FROM daily_delegations d JOIN turns t ON t.id=d.turn
                                WHERE d.turn=? AND d.step='AWAITING_ANSWER'""", (work,)).fetchone()
        if row:
            self.prepare(work, row["chat"], json.loads(row["data"]))

    def respond(self, body):
        base = {"chat", "turn", "action"}
        if set(body) not in (base, base | {"token"}, base | {"name"}):
            raise ChatError("工作操作格式不正確。")
        with self.chat.lock, getattr(self.chat.auth, "lock", self.chat.lock):
            conversation = self.chat.get(body["chat"])
            turn = next((t for t in conversation["turns"] if t["id"] == body["turn"]), None)
            data = turn.get("daily_work") if turn else None
            if not data:
                raise ChatError("找不到本對話中的工作。")
            work, chat_id, action = turn["id"], conversation["id"], body["action"]
            step = data.pop("step")
            grant = data.pop("grant")
            if action == "prepare" and set(body) == base and data["kind"] == "preview" and step in (
                    "READY", "EXPIRED", "PREVIEW_FAILED"):
                self.prepare(work, chat_id, data)
            elif action in ("save", "cancel") and set(body) == base | {"token"}:
                if step != "AWAITING_SAVE" or not grant or body["token"] != grant:
                    raise ChatError("此工作確認已失效或已使用，請先查看原對話狀態。")
                if action == "save":
                    # Once attempted, a crash may leave a file. Never reissue this grant.
                    self.update(work, "SAVING", data)
                try:
                    result = self.outputs.respond(action, {"chat": chat_id, "token": grant}, work=work)
                except ChatError as exc:
                    self.update(work, "FAILED", {**data, "message": str(exc)})
                else:
                    self.update(work, result["status"] if action == "save" else "CANCELLED",
                                {**data, "receipt": result} if action == "save" else data)
            elif action == "inspect" and set(body) == base | {"name"}:
                name = body["name"]
                listed = data["result"] if data["kind"] == "list" and step == "COMPLETE" else []
                if not isinstance(name, str) or not NAME.fullmatch(name) or not (
                        any(item["name"] == name for item in listed)
                        or (step in ("SAVED", "UNKNOWN", "FAILED") and data.get("preview", {}).get("name") == name)):
                    raise ChatError("請從此工作的成果中選擇要核對的項目。")
                try:
                    result = self.outputs.respond("inspect", {"chat": chat_id, "name": name})
                    result.pop("token", None)
                    data["checked"] = result
                    data.pop("read_error", None)
                except ChatError as exc:
                    data["read_error"] = str(exc)
                    data.pop("checked", None)
                self.update(work, step, data)
            else:
                raise ChatError("此工作目前不接受這項操作。")
            return {"chat": chat_id, "turn": work}

