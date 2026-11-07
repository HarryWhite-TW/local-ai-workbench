"""ENG-01: snapshot-only proposals; a fixed host writer, never model tools.

The generated browser asset is quarantined from the normal conversation page.
Only the explicit opaque-origin, network-denied demo may execute it.
"""
from contextlib import contextmanager
import base64
import ctypes
from ctypes import wintypes
import difflib
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import threading
import time
from uuid import uuid4

from .chat import now
from .native_execution import DISABLED, NativeClient, check_thread, observe_turn, policy
from .native_codex import clean, normalized
from .organize import unique
from .resources import SENSITIVE_TEXT
from .siwc import ChatError, SignIn, Vault

TARGET = 'src/companion_core/static/engineering-pilot.js'
BASE = 'b6ae25f227d536b6110bcb29348bd82b6801f060'
AUTHORITY = 'CONTROLLED_CODE_REPLACEMENT'
MODEL = 'gpt-6.1-sol'
MAX_BYTES = 32768
VALIDATION = 'node --check (stdin, syntax only; generated code is not executed)'
EXTRA_DISABLED = ('remote_plugin', 'tool_suggest', 'auth_elicitation')
PROPOSAL_SETTINGS = tuple('features.' + key + '=false' for key in EXTRA_DISABLED)


class ExistingVault(Vault):
    """No automatic credential writes; only a user-initiated OAuth callback."""
    def __init__(self, directory, workspace):
        self._manual_login_save = False
        if not (Path(directory) / 'accounts.dpapi').is_file():
            raise ChatError('ENG-01 需要既有登入；不會建立或變更憑證。')
        super().__init__(directory, workspace)

    def save(self):
        if not self._manual_login_save:
            raise ChatError('ENG-01 只允許本人完成官方登入後保存授權，不自動變更登入資料。')
        return super().save()


class ExistingSignIn(SignIn):
    def access(self, account):
        with self.lock:
            saved = self.vault.data['accounts'].get(account)
            if (account != self.vault.data['active'] or not saved
                    or not saved.get('access_token') or saved['expires_at'] < time.time() + 90):
                self.notice = '聊天登入已到期或不可用；請點 Continue with ChatGPT，由本人完成官方登入後再重新讀取模型。ENG-01 不會自動更新登入。'
                raise ChatError(self.notice)
            return saved['access_token']

    def begin(self, origin, account=None):
        with self.lock:
            try:
                return super().begin(origin, account)
            except ChatError as exc:
                self.notice = str(exc)
                raise

    def callback(self, query):
        with self.lock:
            # The inherited callback validates state, expiry, single-use identity,
            # provider response and registration before it ever calls save().
            self.vault._manual_login_save = True
            try:
                return super().callback(query)
            finally:
                self.vault._manual_login_save = False

    def select(self, *args, **kwargs):
        raise ChatError('ENG-01 不切換或登出帳戶；如需恢復聊天，請由本人完成官方登入。')

    logout = select


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@contextmanager
def locked_target(root, write=False):
    """Pin every Windows ancestor against rename/delete, then pin the file.

    OPEN_REPARSE_POINT rejects junctions as well as symbolic links. The target
    excludes concurrent writes/deletes and hardlinks. No path-selected output,
    temporary replacement file, or candidate-supplied command is used.
    """
    if os.name != 'nt':
        raise ChatError('受控套用目前只支援已驗證的 Windows 檔案控制。')
    import msvcrt

    class Info(ctypes.Structure):
        _fields_ = [('attrs', wintypes.DWORD), ('created', wintypes.FILETIME),
                    ('accessed', wintypes.FILETIME), ('written', wintypes.FILETIME),
                    ('volume', wintypes.DWORD), ('size_hi', wintypes.DWORD),
                    ('size_lo', wintypes.DWORD), ('links', wintypes.DWORD),
                    ('index_hi', wintypes.DWORD), ('index_lo', wintypes.DWORD)]

    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                               ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    api.CreateFileW.restype = wintypes.HANDLE
    api.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.POINTER(Info)]
    api.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    handles = []
    root = Path(root).absolute()
    target = root / TARGET
    try:
        for p in reversed(target.parents):
            handle = api.CreateFileW(str(p), 0x80, 3, None, 3, 0x02200000, None)
            if handle == ctypes.c_void_p(-1).value:
                raise ChatError('無法鎖定目標的實際祖先目錄；未套用。')
            handles.append(handle)
            info = Info()
            if not api.GetFileInformationByHandle(handle, ctypes.byref(info)) or info.attrs & 0x400:
                raise ChatError('拒絕 reparse point／路徑跳脫。')
        handle = api.CreateFileW(str(target), 0x80000000 | (0x40000000 if write else 0),
                                 1, None, 3, 0x00200000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ChatError('無法獨占目標檔案；未套用。')
        handles.append(handle)
        info, final = Info(), ctypes.create_unicode_buffer(32768)
        if (not api.GetFileInformationByHandle(handle, ctypes.byref(info))
                or info.attrs & (0x400 | 0x10) or info.links != 1
                or not api.GetFinalPathNameByHandleW(handle, final, len(final), 0)
                or normalized(final.value) != normalized(target)):
            raise ChatError('目標身分不符，或是 reparse point／hardlink；未套用。')
        identity = [info.volume, info.index_hi, info.index_lo]
        fd = msvcrt.open_osfhandle(handle, os.O_BINARY | (os.O_RDWR if write else os.O_RDONLY))
        handles.pop()  # The Python stream now owns this handle.
        with os.fdopen(fd, 'r+b' if write else 'rb') as stream:
            yield stream, identity
    finally:
        for handle in reversed(handles):
            api.CloseHandle(handle)


class ControlledCode:
    def __init__(self, chat, executable, *, root=None, node=None, client_factory=None):
        self.chat, self.executable = chat, executable
        self.root = Path(root or Path(__file__).absolute().parents[2]).absolute()
        if not (self.root / '.git').is_file():
            raise ChatError('受控工程只接受獨立 Git 工作樹，不能使用原克隆。')
        self.node = str(Path(node or shutil.which('node') or '').absolute())
        if not Path(self.node).is_file() or Path(self.node).suffix.lower() != '.exe':
            raise ChatError('找不到既有的 Node.js 靜態驗證器；未安裝依賴。')
        self.key, self.worker = secrets.token_bytes(32), None
        self.client_factory = client_factory or (lambda directory: NativeClient(directory, executable, settings=PROPOSAL_SETTINGS))
        self.head = self.git('rev-parse', 'HEAD').decode().strip()
        if self.head != BASE:
            raise ChatError('工程候選 HEAD 不是指定基準。')
        # Trusted committed bytes, not a generated candidate, serve ordinary UI.
        self.served_asset = self.git('show', BASE + ':' + TARGET)
        self.snapshot()
        with chat.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS controlled_code (id TEXT PRIMARY KEY, chat TEXT NOT NULL REFERENCES chats(id), value TEXT NOT NULL)')
            for row in db.execute('SELECT id,value FROM controlled_code').fetchall():
                job = json.loads(row['value'])
                if job['state'] in ('RUNNING', 'APPLYING', 'PREVIEW'):
                    job.update(state='UNKNOWN' if job['state'] != 'PREVIEW' else 'EXPIRED',
                               summary='主機曾重新啟動；沒有重新呼叫模型或套用。')
                    db.execute('UPDATE controlled_code SET value=? WHERE id=?', (json.dumps(job), row['id']))

    def git(self, *args):
        result = subprocess.run(['git', '-c', 'core.fsmonitor=false', '-C', str(self.root), *args],
            capture_output=True, timeout=10, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise ChatError('無法確認候選 Git 來源。')
        return result.stdout

    def snapshot(self):
        with locked_target(self.root) as (stream, identity):
            raw = stream.read(MAX_BYTES + 1)
        if not raw or len(raw) > MAX_BYTES:
            raise ChatError('來源大小不符。')
        text = raw.decode('utf-8')
        if SENSITIVE_TEXT.search(text):
            raise ChatError('來源可能含敏感資料；未分享。')
        return {'target': TARGET, 'root': str(self.root), 'head': self.head,
                'sha256': sha(raw), 'identity': identity, 'text': text}

    def token(self, job):
        manifest = {k: job[k] for k in ('id', 'chat', 'account', 'workspace', 'goal', 'source', 'expires', 'validation')}
        return hmac.new(self.key, json.dumps(manifest, sort_keys=True).encode(), 'sha256').hexdigest()

    def view(self, job):
        result = {k: v for k, v in job.items() if k not in ('approval_digest', 'replacement')}
        if job['state'] == 'PREVIEW':
            result['token'] = self.token(job)
        return result

    def save(self, job):
        with self.chat.connect() as db:
            db.execute('UPDATE controlled_code SET value=? WHERE id=?', (json.dumps(job), job['id']))

    def get(self, ident):
        with self.chat.connect() as db:
            row = db.execute('SELECT value FROM controlled_code WHERE id=?', (ident,)).fetchone()
        if not row:
            raise ChatError('找不到工程工作。')
        job = json.loads(row['value'])
        conversation = self.chat.get(job['chat'])
        if conversation['account'] != job['account'] or self.chat.workspace != job['workspace']:
            raise ChatError('工程帳戶或工作區不符。')
        return job

    def preview(self, body):
        if (set(body) != {'chat', 'question'} or not isinstance(body['question'], str)
                or not 1 <= len(body['question'].strip()) <= 2000 or SENSITIVE_TEXT.search(body['question'])):
            raise ChatError('請輸入不含敏感資料的工程需求；不能指定其他目標。')
        conversation = self.chat.get(body['chat'])
        job = {'id': str(uuid4()), 'chat': body['chat'], 'turn': str(uuid4()),
               'account': conversation['account'], 'workspace': self.chat.workspace,
               'goal': body['question'].strip(), 'source': self.snapshot(), 'state': 'PREVIEW',
               'expires': time.time() + 1800, 'validation': VALIDATION, 'events': [],
               'summary': '尚未分享來源或執行；只允許替換此單一前端檔案。'}
        job['approval_digest'] = sha(self.token(job).encode())
        with self.chat.connect() as db:
            db.execute('INSERT INTO turns (id,chat,question,answer,sources,model,created,finished,status) VALUES (?,?,?,?,?,?,?,?,?)',
                (job['turn'], job['chat'], job['goal'], '請核對下方受控工程來源與寫入影響。', '[]', 'NEXUS · 受控程式修改', now(), now(), 'complete'))
            db.execute('INSERT INTO controlled_code VALUES (?,?,?)', (job['id'], job['chat'], json.dumps(job)))
        return self.view(job)

    def confirm(self, body):
        if set(body) != {'id', 'token', 'authority'} or body['authority'] != AUTHORITY:
            raise ChatError('需要獨立的受控程式修改批准；其他路線批准不適用。')
        job = self.get(body['id'])
        if (job['state'] != 'PREVIEW' or job['expires'] < time.time()
                or not isinstance(body['token'], str)
                or not hmac.compare_digest(sha(body['token'].encode()), job['approval_digest'])
                or not hmac.compare_digest(body['token'], self.token(job))
                or self.snapshot() != job['source']
                or self.git('rev-parse', 'HEAD').decode().strip() != job['source']['head']
                or self.worker and self.worker.is_alive()):
            raise ChatError('批准已失效、來源有變或已有工作；沒有執行。')
        job.update(state='RUNNING', approval_digest=None, approved_at=now(), authority=AUTHORITY,
                   summary='已消耗此次批准；模型只能回傳文字，不能使用工具。')
        self.save(job)
        self.worker = threading.Thread(target=self.run, args=(job,), daemon=False)
        self.worker.start()
        return self.view(job)

    def validate(self, answer, job):
        value = json.loads(answer, object_pairs_hook=unique)
        if (not isinstance(value, dict) or set(value) != {'target', 'source_sha256', 'replacement'}
                or value['target'] != TARGET or value['source_sha256'] != job['source']['sha256']
                or not isinstance(value['replacement'], str)):
            raise ChatError('模型輸出的目標、來源或結構不符；沒有套用。')
        raw = value['replacement'].encode('utf-8')
        if not raw or len(raw) > MAX_BYTES or b'\x00' in raw or SENSITIVE_TEXT.search(value['replacement']):
            raise ChatError('替換內容無效；沒有套用。')
        result = subprocess.run([self.node, '--check'], input=raw, capture_output=True, timeout=10,
            env={k: v for k, v in os.environ.items() if k.upper() in ('SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP')},
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        test = {'command': VALIDATION, 'exitCode': result.returncode,
                'stdout': clean(result.stdout.decode('utf-8', errors='replace')),
                'stderr': clean(result.stderr.decode('utf-8', errors='replace')),
                'validator_sha256': sha(Path(self.node).read_bytes()), 'generated_code_executed': False}
        job['tests'] = test
        if result.returncode or sha(raw) == job['source']['sha256']:
            raise ChatError('靜態驗證失敗或沒有實際差異；沒有套用。')
        job.update(replacement=value['replacement'], final_sha256=sha(raw),
            diff=''.join(difflib.unified_diff(job['source']['text'].splitlines(True),
                value['replacement'].splitlines(True), fromfile='before/' + TARGET, tofile='after/' + TARGET)))

    def apply(self, job):
        with self.chat.lock, self.chat.auth.lock:
            self.get(job['id'])  # Recheck the original account immediately before the write.
            if self.git('rev-parse', 'HEAD').decode().strip() != job['source']['head']:
                raise ChatError('來源版本已變；沒有套用。')
            with locked_target(self.root, write=True) as (stream, identity):
                before = stream.read(MAX_BYTES + 1)
                if identity != job['source']['identity'] or sha(before) != job['source']['sha256']:
                    raise ChatError('實際來源身分或內容已變；沒有套用。')
                job.update(state='APPLYING', summary='主機正在套用已通過靜態驗證的內容；中斷後不會自動重寫。')
                self.save(job)  # Write-ahead receipt; a crash remains UNKNOWN.
                raw = job['replacement'].encode('utf-8')
                stream.seek(0)
                stream.write(raw)
                stream.truncate()
                stream.flush()
                os.fsync(stream.fileno())
                stream.seek(0)
                if sha(stream.read()) != job['final_sha256']:
                    raise ChatError('套用後雜湊不符；保留原快照供恢復。')
            job.update(state='COMPLETED', applied_at=now(),
                summary='單一檔案已套用，靜態語法檢查通過；尚待隔離功能驗證與獨立技術審查。')
            self.save(job)

    def run(self, job):
        try:
            version = subprocess.run([str(self.executable), '--version'], capture_output=True,
                text=True, timeout=10, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if version.returncode or version.stdout.strip() != 'codex-cli 0.162.1':
                raise ChatError('必須使用已驗證的 Codex 0.162.1。')
            # Process/thread cwd is a source-free directory, never the candidate.
            directory = self.chat.path.parent / 'controlled-model-empty'
            directory.mkdir(exist_ok=True)
            if directory.is_symlink() or directory.resolve() != directory.absolute() or any(directory.iterdir()):
                raise ChatError('模型空白工作目錄不安全。')
            with self.client_factory(str(directory)) as rpc:
                effective = rpc.call('config/read', {'cwd': str(directory), 'includeLayers': False}).get('config', {})
                servers = effective.get('mcp_servers', {})
                features = effective.get('features', {})
                gates = {key: features.get(key) for key in (*DISABLED, *EXTRA_DISABLED)}
                if (not isinstance(servers, dict) or any(value is not False for value in gates.values())
                        or effective.get('web_search') != 'disabled'
                        or effective.get('skills', {}).get('include_instructions') is not False
                        or effective.get('skills', {}).get('bundled', {}).get('enabled') is not False):
                    raise ChatError('無法確認外部工具設定。')
                config = {'mcp_servers': {name: {'enabled': False} for name in servers},
                          'sandbox_mode': 'read-only', 'approval_policy': 'never'}
                instructions = ('Only propose the requested small frontend change from the supplied snapshot. '
                    'You have NO tools: no shell, files, browser, network, skills, MCP, apps or delegation. '
                    'Do not request tools or extra sources. Preserve unrelated behavior. '
                    'Return ONLY JSON with exactly target, source_sha256, replacement (complete UTF-8 source). '
                    'Never invent tests or acceptance. The host alone validates and writes. '
                    'The clipboard summary must use actual job.goal, modified file names, job.tests '
                    '(exitCode/stdout/stderr), and the literal 尚待獨立技術審查. '
                    'Handle clipboard rejection visibly without claiming success. Do not add dependencies, '
                    'network calls, eval, storage, or top-level side effects. Retain the existing sample route.')
                thread = check_thread(rpc.call('thread/start', {'cwd': str(directory), 'approvalPolicy': 'never',
                    'sandbox': 'read-only', 'modelProvider': 'openai', 'model': MODEL,
                    'config': config, 'developerInstructions': instructions}), str(directory), execution=True)
                job.update(thread_id=thread, model=MODEL, tools_enabled=False, tool_gates=gates,
                           disabled_mcp_servers=len(servers),
                           events=[{'at': now(), 'kind': 'snapshot_only_thread_started'}])
                self.save(job)
                prompt = json.dumps({'goal': job['goal'], 'target': TARGET,
                    'source_sha256': job['source']['sha256'], 'source': job['source']['text'],
                    'result_contract': {'goal': 'user goal', 'target': TARGET,
                        'tests': {'exitCode': 0, 'stdout': '', 'stderr': ''},
                        'diff': 'actual host diff', 'source': {'target': TARGET}}}, ensure_ascii=False)
                reply = rpc.call('turn/start', {'threadId': thread, 'cwd': str(directory),
                    'approvalPolicy': 'never', 'sandboxPolicy': policy(directory), 'model': MODEL,
                    'input': [{'type': 'text', 'text': prompt}]})
                job['turn_id'] = reply['turn']['id']
                self.save(job)
                state, answer = observe_turn(rpc, thread, job['turn_id'], threading.Event(), lambda **_: None)
                if state != 'COMPLETED':
                    raise ChatError('模型沒有確認完成；不重送。')
            job['events'].append({'at': now(), 'kind': 'text_only_turn_completed_no_tool_items'})
            self.validate(answer, job)
            self.apply(job)
        except Exception as exc:
            job.update(state='UNKNOWN' if job['state'] == 'APPLYING' else 'FAILED',
                       summary=clean(str(exc), 1000) if isinstance(exc, ChatError) else
                       '未取得可確認的安全成果；未自動重試。', error_type=type(exc).__name__)
            self.save(job)

    def respond(self, action, body):
        with self.chat.lock, self.chat.auth.lock:
            if action == 'preview':
                return self.preview(body)
            if action == 'confirm':
                return self.confirm(body)
            if action == 'state' and set(body) == {'chat'}:
                self.chat.get(body['chat'])
                with self.chat.connect() as db:
                    ids = [r['id'] for r in db.execute('SELECT id FROM controlled_code WHERE chat=?', (body['chat'],))]
                return [self.view(self.get(ident)) for ident in ids]
            if action == 'demo' and set(body) == {'id'}:
                job = self.get(body['id'])
                if job['state'] != 'COMPLETED' or self.snapshot()['sha256'] != job['final_sha256']:
                    raise ChatError('只有來源仍吻合的已套用成果可進行隔離體驗。')
                return {'source_base64': base64.b64encode(job['replacement'].encode()).decode(),
                        'job': {**self.view(job), 'state': 'COMPLETED', 'target': TARGET}}
            raise ChatError('不支援的受控工程操作。')

    def close(self):
        if self.worker:
            self.worker.join()
