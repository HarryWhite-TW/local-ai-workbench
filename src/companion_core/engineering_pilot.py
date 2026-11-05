"""Single explicitly approved sample edit. Not a general engineering runtime.

Independent of READ_ONLY tasks and ReviewStore decisions. The official native
app-server owns tools; this adapter captures a bounded receipt, never ACCEPTED.
"""
import difflib
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
from uuid import uuid4

from .chat import now
from .codex import _Rpc
from .native_execution import NativeClient, SETTINGS
from .native_codex import clean
from .siwc import ChatError

FILES = ('calculator.py', 'test_calculator.py', 'AGENTS.md')
MODEL = 'gpt-6.1-sol'


class PilotClient(NativeClient):
    def __enter__(self):
        # The process cwd MUST be the sample itself, not its parent/data store.
        args = [str(self.executable), 'app-server', '--listen', 'stdio://']
        for value in SETTINGS + ('features.shell_tool=true', 'features.apply_patch_freeform=true',
                                 'approval_policy="on-request"', 'sandbox_mode="workspace-write"',
                                 'features.code_mode_host=true', 'features.code_mode=true', 'features.unified_exec=true'):
            args += ['-c', value]
        env = {k: v for k, v in os.environ.items() if k.upper() in {
            'PATH', 'PATHEXT', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'USERPROFILE',
            'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP', 'PROGRAMFILES', 'PROGRAMFILES(X86)', 'PROGRAMDATA'}}
        self.process = subprocess.Popen(args, cwd=self.directory, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
        _Rpc.__init__(self, self.process)
        try:
            self.call('initialize', {'clientInfo': {'name': 'nexus_isolated_sample', 'version': '0.1'}})
            self.send({'method': 'initialized', 'params': {}})
            if self.call('account/read', {'refreshToken': False}).get('account', {}).get('type') != 'chatgpt':
                raise ChatError('原生 Codex 登入不可用。')
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def begin(self, method, params):
        if method not in {'initialize', 'account/read', 'thread/start', 'turn/start',
                          'turn/interrupt', 'command/exec'}:
            raise ChatError('試點不支援此能力。')
        return _Rpc.begin(self, method, params)
    # Inherited receive rejects ALL server-initiated escalation/tool requests.


class EngineeringPilot:
    def __init__(self, chat, root, executable):
        self.chat, self.root, self.executable = chat, Path(root).absolute(), executable
        if self.root.resolve(strict=True) != self.root or self.root != Path(chat.path.parent).parent / 'fixture':
            raise ChatError('工程試點只接受本機固定隔離範例。')
        if self.root.is_relative_to(Path(chat.workspace)) or (self.root / '.git').exists():
            raise ChatError('工程範例不得使用產品工作區或 Git 工作樹。')
        self.python = sys.executable
        self.lock, self.worker = threading.RLock(), None
        with chat.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS engineering_pilot (id TEXT PRIMARY KEY, chat TEXT NOT NULL, turn TEXT NOT NULL, value TEXT NOT NULL)')
            for row in db.execute('SELECT id,value FROM engineering_pilot').fetchall():
                job = json.loads(row['value'])
                if job['state'] == 'RUNNING':
                    job.update(state='UNKNOWN', summary='主機曾中斷；沒有自動重跑。')
                    db.execute('UPDATE engineering_pilot SET value=? WHERE id=?', (json.dumps(job), row['id']))

    def snapshot(self):
        result = {}
        for name in FILES:
            p = self.root / name
            if p.resolve(strict=True) != p or p.stat().st_size > 32768:
                raise ChatError('範例來源位置或大小不符。')
            result[name] = p.read_text(encoding='utf-8')
        return result

    def save(self, job):
        with self.chat.connect() as db:
            db.execute('UPDATE engineering_pilot SET value=? WHERE id=?', (json.dumps(job), job['id']))

    def get(self, ident):
        with self.chat.connect() as db:
            row = db.execute('SELECT value FROM engineering_pilot WHERE id=?', (ident,)).fetchone()
        if not row:
            raise ChatError('找不到這次試點。')
        job = json.loads(row['value'])
        self.chat.get(job['chat'])  # Existing account + workspace ownership guard.
        return job

    def state(self, body):
        if set(body) != {'chat'}:
            raise ChatError('試點格式不正確。')
        self.chat.get(body['chat'])
        with self.chat.connect() as db:
            return [json.loads(r['value']) for r in db.execute('SELECT value FROM engineering_pilot WHERE chat=?', (body['chat'],))]

    def preview(self, body):
        if set(body) != {'chat', 'question'} or not isinstance(body['question'], str) or not 1 <= len(body['question'].strip()) <= 2000:
            raise ChatError('請在目前對話輸入工程範例需求。')
        conversation = self.chat.get(body['chat'])
        source = self.snapshot()
        ident, turn = str(uuid4()), str(uuid4())
        job = {'id': ident, 'chat': body['chat'], 'turn': turn, 'account': conversation['account'],
               'state': 'PREVIEW', 'goal': body['question'].strip(), 'root': str(self.root),
               'source': source, 'token': secrets.token_urlsafe(32), 'expires': time.time() + 600,
               'events': [], 'summary': '尚未執行；核對範例來源及寫入範圍後才可開始。'}
        with self.chat.connect() as db:
            db.execute('INSERT INTO turns (id,chat,question,answer,sources,model,created,finished,status) VALUES (?,?,?,?,?,?,?,?,?)',
                (turn, body['chat'], job['goal'], '以下為本機工程試點預覽，尚未交給 Codex 執行。', '[]', 'NEXUS · 工程試點', now(), now(), 'complete'))
            db.execute('INSERT INTO engineering_pilot VALUES (?,?,?,?)', (ident, body['chat'], turn, json.dumps(job)))
        return job

    def confirm(self, body):
        if set(body) != {'id', 'token', 'authority'} or body['authority'] != 'ISOLATED_SAMPLE_WRITE':
            raise ChatError('需要獨立的隔離範例寫入授權；唯讀批准不適用。')
        with self.lock:
            job = self.get(body['id'])
            if (job['state'] != 'PREVIEW' or job['expires'] < time.time()
                    or not secrets.compare_digest(job['token'], str(body['token']))
                    or self.snapshot() != job['source'] or self.worker and self.worker.is_alive()):
                raise ChatError('預覽已失效、來源有變或已有工作；未開始執行。')
            job.update(state='RUNNING', token=None, summary='正在驗證寫入邊界並啟動原生 Codex。')
            self.save(job)
            self.worker = threading.Thread(target=self.run, args=(job,), daemon=True)
            self.worker.start()
            return job

    def run(self, job):
        sent = False
        def event(name, **data):
            job['events'].append({'at': now(), 'kind': name, **data})
            self.save(job)
        policy = {'type': 'workspaceWrite', 'writableRoots': [str(self.root)],
                  'networkAccess': False, 'excludeTmpdirEnvVar': True, 'excludeSlashTmp': True}
        try:
            if self.snapshot() != job['source']:
                raise ChatError('確認後來源已變；未啟動模型。')
            with PilotClient(self.root, self.executable) as rpc:
                # Live negative probe before exposing a writable tool to a model.
                guard = "from pathlib import Path; Path('probe-inside.txt').write_text('inside'); print('INSIDE_OK')\ntry:\n Path(r'" + str(self.root.parent / 'outside-canary.txt') + "').write_text('FORBIDDEN'); print('OUTSIDE_WRITABLE')\nexcept PermissionError: print('OUTSIDE_DENIED')"
                result = rpc.call('command/exec', {'command': [self.python, '-B', '-c', guard], 'cwd': str(self.root), 'sandboxPolicy': policy, 'timeoutMs': 10000})
                event('boundary_probe', result=result)
                if result.get('exitCode') != 0 or 'OUTSIDE_DENIED' not in result.get('stdout', '') or 'OUTSIDE_WRITABLE' in result.get('stdout', ''):
                    raise ChatError('寫入限制未通過，未啟動模型。')
                settings = {'sandbox_workspace_write': {'writable_roots': [str(self.root)], 'network_access': False, 'exclude_tmpdir_env_var': True, 'exclude_slash_tmp': True}}
                reply = rpc.call('thread/start', {'cwd': str(self.root), 'approvalPolicy': 'on-request', 'sandbox': 'workspace-write',
                    'model': MODEL, 'modelProvider': 'openai', 'config': settings,
                    'developerInstructions': 'Only work in this isolated non-sensitive sample. Only edit calculator.py. Never access any other workspace, credentials, network, or Git. Do not modify tests or AGENTS.md. Run the exact test command supplied by the user, using -B. Do not request elevated permissions. Do not claim independent technical acceptance.'})
                if (reply.get('approvalPolicy') != 'on-request' or reply.get('sandbox', {}).get('type') != 'workspaceWrite'
                        or Path(reply['thread']['cwd']).resolve() != self.root):
                    raise ChatError('原生執行政策不符。')
                thread = reply['thread']['id']
                job['thread_id'] = thread
                event('thread_created')
                prompt = job['goal'] + '\nOnly fix calculator.py. Read the provided test_calculator.py and AGENTS.md. Empty average must be 0; other averages unchanged. Actually apply the change and run: "' + self.python + '" -B -m unittest -v. This is approved only for ' + str(self.root) + '. Do not write outside it.'
                sent = True
                reply = rpc.call('turn/start', {'threadId': thread, 'cwd': str(self.root), 'approvalPolicy': 'on-request', 'sandboxPolicy': policy,
                    'input': [{'type': 'text', 'text': prompt, 'text_elements': []}], 'model': MODEL})
                turn = reply['turn']['id']
                job['turn_id'] = turn
                event('model_running')
                deadline = time.monotonic() + 240
                completed, tools, answer = False, [], []
                while time.monotonic() < deadline:
                    try:
                        message = rpc.notification(.5)
                    except Exception as exc:
                        from .runtime import RuntimeFailure
                        from .domain import Failure
                        if isinstance(exc, RuntimeFailure) and exc.reason == Failure.TIMEOUT:
                            continue
                        raise
                    p = message.get('params', {})
                    if p.get('threadId') != thread:
                        continue
                    if message.get('method') == 'item/completed' and p.get('turnId') == turn:
                        item = p.get('item', {})
                        if item.get('type') == 'agentMessage':
                            answer.append(clean(item.get('text', ''), 10000))
                        elif item.get('type') in ('commandExecution', 'fileChange'):
                            record = {k: clean(item[k], 16000) if isinstance(item.get(k), str) else item.get(k)
                                      for k in ('type', 'command', 'cwd', 'status', 'exitCode', 'aggregatedOutput') if k in item}
                            tools.append(record)
                            event('native_tool_completed', tool=record)
                    if message.get('method') == 'turn/completed' and p.get('turn', {}).get('id') == turn:
                        completed = p['turn'].get('status') == 'completed'
                        break
                if not completed:
                    rpc.call('turn/interrupt', {'threadId': thread, 'turnId': turn})
                    raise ChatError('模型未確認完成；不會自動重試。')
                source = self.snapshot()
                job['model_summary'] = '\n\n'.join(answer)
                if any(source[n] != job['source'][n] for n in FILES if n != 'calculator.py'):
                    raise ChatError('固定測試或規則發生變更；成果未確認。')
                test = rpc.call('command/exec', {'command': [self.python, '-B', '-m', 'unittest', '-v'], 'cwd': str(self.root), 'sandboxPolicy': policy, 'timeoutMs': 15000})
                diff = ''.join(difflib.unified_diff(job['source']['calculator.py'].splitlines(True), source['calculator.py'].splitlines(True), fromfile='before/calculator.py', tofile='after/calculator.py'))
                if test.get('exitCode') != 0 or not diff or not any('unittest' in t.get('command', '') and t.get('exitCode') == 0 for t in tools):
                    raise ChatError('實際差異或 Codex 測試證據不足。')
                job.update(state='COMPLETED', summary='隔離範例已修改，Codex 測試與主機覆核測試通過；尚待獨立技術審查。',
                           diff=diff, tests=test, model_summary='\n\n'.join(answer), final_sha256=hashlib.sha256((self.root / 'calculator.py').read_bytes()).hexdigest())
                event('host_verified')
        except Exception as exc:
            job.update(state='UNKNOWN' if sent else 'FAILED', summary=clean(str(exc), 1000) if isinstance(exc, ChatError) else '原生執行未能確認；沒有自動重送。')
            event('execution_unconfirmed', error_type=type(exc).__name__)

    def respond(self, action, body):
        with self.chat.lock, self.chat.auth.lock:
            if not self.chat.auth.vault.data['active'] or self.chat.auth.pending:
                raise ChatError('請先確認對話帳戶。')
            if action == 'state': return self.state(body)
            if action == 'preview': return self.preview(body)
            if action == 'confirm': return self.confirm(body)
            raise ChatError('不支援的工程試點操作。')
