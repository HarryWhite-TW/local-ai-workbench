"""Explicit conversation proposals and a host-owned, fixed-file Python source audit.

No model tools, subprocesses, filesystem discovery, imports of inspected code,
or project writes. ReviewStore remains the authority for results and decisions.
"""
import ast
import hashlib
import json
from pathlib import Path
import re
import threading
from uuid import uuid4

from .chat import now
from .domain import Authority, Failure
from .presentation import safe_text
from .runtime import EventKind, RuntimeEvent, RuntimeFailure
from .siwc import ChatError


FILES = {name: f"src/companion_core/{name}.py" for name in
         ("daily", "chat", "surface", "core", "runtime", "review", "work")}
SECRET = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|\bBearer\s+[A-Za-z0-9._-]{16,}")


def capture(workspace, selection):
    if (not isinstance(selection, list) or not selection or len(selection) > len(FILES)
            or any(not isinstance(k, str) for k in selection)
            or len(set(selection)) != len(selection) or not set(selection) <= FILES.keys()):
        raise ChatError("只能選擇列出的 Companion 程式檔案。")
    root = Path(workspace).resolve(strict=True)
    records = []
    for key in selection:
        p = root / FILES[key]
        try:
            # Reject junctions/symlinks anywhere below the approved repository.
            if p.resolve(strict=True) != p or not p.is_file():
                raise ValueError()
            with p.open('rb') as stream:
                raw = stream.read(65_537)
            if len(raw) > 65_536:
                raise ValueError()
            text = raw.decode('utf-8-sig')
            if SECRET.search(text):
                raise ValueError()
            records.append({"key": key, "name": FILES[key], "bytes": len(raw),
                            "sha256": hashlib.sha256(raw).hexdigest(), "text": text})
        except (OSError, ValueError, UnicodeError):
            raise ChatError("選定檔案無法安全讀取；請確認檔案範圍與內容。") from None
    return records


class ProjectWork:
    provider_id = "bounded-python-source-audit-v1"
    requires_proposal = True
    capture = staticmethod(capture)

    def __init__(self, chat):
        self.chat, self.surface = chat, None
        self.lock = threading.RLock()
        self.grant = None
        with chat.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS work_proposals (
                id TEXT PRIMARY KEY, chat TEXT NOT NULL REFERENCES chats(id),
                turn TEXT NOT NULL REFERENCES turns(id), goal TEXT NOT NULL,
                expected TEXT NOT NULL, selection TEXT NOT NULL, created TEXT NOT NULL,
                preview TEXT, approval TEXT, task_id TEXT UNIQUE, stopped TEXT)""")

    def _conversation(self, ident):
        conversation = self.chat.get(ident)
        if (self.chat.auth.pending or not self.chat.auth.vault.data['active']
                or conversation['account'] != self.chat.auth.vault.data['active']):
            raise ChatError("請使用此對話原本的帳戶確認工作。")
        return conversation

    def _get(self, ident):
        with self.chat.connect() as db:
            row = db.execute('SELECT * FROM work_proposals WHERE id=?', (ident,)).fetchone()
        if row is None:
            raise ChatError("找不到這份工作提案。")
        value = dict(row)
        self._conversation(value['chat'])
        value['selection'] = json.loads(value['selection'])
        return value

    @staticmethod
    def _text(value, maximum):
        if (not isinstance(value, str) or not value.strip() or len(value) > maximum
                or safe_text(value) != value or SECRET.search(value)):
            raise ChatError("工作目標與預期結果需要有效的非敏感文字。")
        return value.strip()

    def create(self, body):
        if set(body) != {'chat', 'turn'}:
            raise ChatError("提案要求格式不正確。")
        conversation = self._conversation(body['chat'])
        turn = next((t for t in conversation['turns'] if t['id'] == body['turn']), None)
        if not turn or turn['status'] != 'complete':
            raise ChatError("請先完成一輪討論，再明確建立提案。")
        ident = str(uuid4())
        goal = self._text(turn['question'], 4000)
        expected = self._text(turn['answer'][:4000], 4000)
        with self.chat.connect() as db:
            db.execute('INSERT INTO work_proposals (id,chat,turn,goal,expected,selection,created) VALUES (?,?,?,?,?,?,?)',
                       (ident, body['chat'], body['turn'], goal, expected, json.dumps(list(FILES)), now()))
        return self.describe(self._get(ident))

    def preview(self, body):
        if set(body) != {'id', 'goal', 'expected', 'selection'}:
            raise ChatError("提案預覽格式不正確。")
        with self.lock:
            p = self._get(body['id'])
            if p['task_id']:
                raise ChatError("已確認的工作不能修改或重複執行。")
            goal, expected = self._text(body['goal'], 4000), self._text(body['expected'], 4000)
            records = self.capture(self.chat.workspace, body['selection'])
            manifest = [{k: r[k] for k in ('key', 'name', 'bytes', 'sha256')} for r in records]
            approval = str(uuid4())
            with self.chat.connect() as db:
                db.execute('UPDATE work_proposals SET goal=?,expected=?,selection=?,preview=?,approval=? WHERE id=?',
                           (goal, expected, json.dumps(body['selection']), json.dumps(manifest), approval, p['id']))
            return {**self.describe(self._get(p['id'])), 'approval': approval, 'manifest': manifest}

    def confirm(self, body):
        if set(body) != {'id', 'approval', 'authority'} or body['authority'] != 'READ_ONLY':
            raise ChatError("必須明確確認此提案的唯讀權限。")
        with self.lock:
            p = self._get(body['id'])
            if p['task_id'] or not p['approval'] or p['approval'] != body['approval']:
                raise ChatError("授權預覽已失效或已使用，請重新讀取提案。")
            if self.surface is None or self.surface.runtime is not self:
                raise ChatError("受限專案查核執行器目前不可用。")
            manifest = json.loads(p['preview'])
            current = self.capture(self.chat.workspace, p['selection'])
            if [r['sha256'] for r in current] != [r['sha256'] for r in manifest]:
                raise ChatError("來源已變更，請重新預覽並確認。")

            def bind(task_id):
                with self.chat.connect() as db:
                    db.execute('UPDATE work_proposals SET task_id=?,approval=NULL WHERE id=? AND task_id IS NULL', (task_id, p['id']))
                self.grant = (p, manifest, task_id)

            try:
                result = self.surface.start(p['goal'], bind=bind, finished=self._finished)
            except Exception:
                self.grant = None
                raise ChatError("工作未確認啟動；請重新讀取狀態，不會自動重試。") from None
            return {**result, 'id': p['id'], 'chat': p['chat']}

    def _finished(self, task):
        # Only non-result execution outcomes live with the proposal link.
        # Completed results and all review decisions are read from ReviewStore.
        stopped = task.state if task.state in ('FAILED', 'CANCELLED') else None
        with self.chat.connect() as db:
            db.execute('UPDATE work_proposals SET stopped=? WHERE task_id=?', (stopped, task.id))

    def run(self, request):
        with self.lock:
            grant, self.grant = self.grant, None
        if not grant or request.authority is not Authority.READ_ONLY:
            raise RuntimeFailure(Failure.POLICY)
        p, manifest, task_id = grant
        if request.workspace != self.chat.workspace or request.intent != p['goal']:
            raise RuntimeFailure(Failure.POLICY)
        yield RuntimeEvent(EventKind.SESSION, session_id=task_id)
        yield RuntimeEvent(EventKind.INSPECTING)
        records = self.capture(self.chat.workspace, p['selection'])
        if [r['sha256'] for r in records] != [r['sha256'] for r in manifest]:
            raise RuntimeFailure(Failure.POLICY)
        lines = ['可信本機唯讀查核紀錄（非模型摘要）', f'工作：{task_id}', f'提案：{p["id"]}',
                 f'擷取時間：{now()}', f'Repository：{self.chat.workspace}',
                 '操作：固定清單檔案讀取、SHA-256、Python AST 解析。沒有執行被讀取程式、Shell、網路或寫入專案。',
                 '範圍限制：以下證明程式定義與呼叫位置存在，不等於功能測試、登入可用或技術驗收；未查核 Git／遠端進度。']
        for r in records:
            if request.cancel_requested and request.cancel_requested.is_set():
                yield RuntimeEvent(EventKind.CANCELLED)
                return
            tree = ast.parse(r['text'])
            lines.extend(['', f'來源：{r["name"]}', f'SHA-256：{r["sha256"]} · {r["bytes"]} bytes', '實際程式結構：'])
            for node in ast.walk(tree):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    lines.append(f'L{node.lineno}：{type(node).__name__} {node.name}')
                # Top-level launcher wiring, directly extracted, never an inferred success claim.
                if isinstance(node, ast.FunctionDef) and node.name == 'main':
                    calls = sorted({(n.lineno, ast.unparse(n.func)) for n in ast.walk(node) if isinstance(n, ast.Call)})
                    lines.extend(f'L{line}：main 呼叫 {name}' for line, name in calls)
            lines.append('解析完成；上述行號可對照此雜湊的來源檔案。')
        report = '\n'.join(lines)
        if len(report) > 50_000 or safe_text(report) != report:
            raise RuntimeFailure(Failure.PROTOCOL)
        yield RuntimeEvent(EventKind.RECEIVING)
        yield RuntimeEvent(EventKind.COMPLETED, text=report)

    def describe(self, p):
        state, result_id = 'AWAITING_AUTHORIZATION', None
        if p['task_id']:
            # A missing receipt is not evidence of failed execution (e.g. host exit).
            state = p['stopped'] if p['stopped'] in ('FAILED', 'CANCELLED') else 'UNKNOWN'
            if self.surface:
                active = self.surface.active
                if active and active.task.id == p['task_id']:
                    state = active.task.state
                try:
                    target = self.surface._scoped(self.surface.store.get(p['task_id']))
                    state, result_id = target.task.state, target.result_id
                except Exception:
                    pass
        return {k: p[k] for k in ('id', 'chat', 'turn', 'goal', 'expected', 'selection', 'created', 'task_id')} | {
            'state': state, 'result_id': result_id, 'technical_acceptance': '未由 ChatGPT 技術驗收',
            'capability': '僅查核選定 Python 程式結構；不執行程式、測試或任意命令。',
            'workspace': self.chat.workspace}

    def state(self, chat_id):
        self._conversation(chat_id)
        with self.chat.connect() as db:
            ids = [r[0] for r in db.execute('SELECT id FROM work_proposals WHERE chat=? ORDER BY created', (chat_id,))]
        return [self.describe(self._get(ident)) for ident in ids]

    def saved_failures(self):
        if self.chat.auth.pending or not self.chat.auth.vault.data['active']:
            return []
        with self.chat.connect() as db:
            rows = db.execute('''SELECT p.task_id,p.goal,p.stopped FROM work_proposals p
                JOIN chats c ON c.id=p.chat
                WHERE p.task_id IS NOT NULL AND c.workspace=? AND c.account=?''',
                (self.chat.workspace, self.chat.auth.vault.data['active'])).fetchall()
        return [{'task_id': r['task_id'], 'intent': r['goal'],
                 'state': r['stopped'] if r['stopped'] in ('FAILED', 'CANCELLED') else 'UNKNOWN'} for r in rows]

    def can_view(self, task):
        """Apply the conversation owner to linked work, including saved receipts.

        Legacy work has no conversation/account link; retain its workspace-only
        access. A bounded-audit receipt without its link must fail closed.
        """
        with self.chat.connect() as db:
            row = db.execute('''SELECT c.workspace,c.account FROM work_proposals p
                JOIN chats c ON c.id=p.chat WHERE p.task_id=?''', (task.id,)).fetchone()
        if row is None:
            return task.provider != self.provider_id
        return (not self.chat.auth.pending and bool(self.chat.auth.vault.data['active'])
                and row['workspace'] == self.chat.workspace
                and row['account'] == self.chat.auth.vault.data['active'])

    def origin(self, task_id):
        with self.chat.connect() as db:
            row = db.execute('SELECT id FROM work_proposals WHERE task_id=?', (task_id,)).fetchone()
        if row is None:
            raise ChatError('目前工作沒有可確認的原對話連結。')
        return self.describe(self._get(row[0]))

    def context(self, key, chat_id):
        p = self._get(key.removeprefix('work:'))
        if p['chat'] != chat_id or not p['task_id']:
            raise ChatError("此成果不屬於目前對話。")
        try:
            target = self.surface._scoped(self.surface.store.get(p['task_id']))
        except Exception:
            raise ChatError("沒有可核對的已保存工作成果。") from None
        captured = next((line.removeprefix('擷取時間：') for line in target.task.result.splitlines()
                         if line.startswith('擷取時間：')), None)
        if not captured:
            raise ChatError('成果缺少可核對的擷取時間。')
        return {'id': 'S1', 'key': key, 'name': '工作成果 '+p['task_id'], 'captured_at': captured,
                'sha256': hashlib.sha256(target.task.result.encode()).hexdigest(), 'text': target.task.result}
