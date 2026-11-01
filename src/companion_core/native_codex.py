"""Workspace-scoped observation through official Codex app-server read RPCs.

No resume, turn execution, approval, model request, transcript storage or raw
tool output. Each bounded read owns and stops its own stdio process. Runtime
status from this separate process is deliberately never advertised as live.
"""
from datetime import datetime, timezone
import json
import ntpath
import os
from pathlib import Path
import queue
import re
import secrets
import subprocess
import threading
import time

from .siwc import ChatError


DOCS = 'https://learn.chatgpt.com/docs/app-server'
METHODS = {'thread/list', 'thread/read', 'thread/turns/list'}
IDENT = re.compile(r'^[a-zA-Z0-9_-]{1,100}$')
SENSITIVE = re.compile(r'(?i)\b(?:sk-[a-z0-9_-]{12,}|Bearer\s+\S+|eyJ[a-z0-9_-]+\.[a-z0-9_-]+\.[a-z0-9_-]+|(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|client_secret)\s*[=:]\s*\S+)')


def clean(value, limit=12000):
    value = value if isinstance(value, str) else ''
    # Plain text only on the surface; omit credential-looking lines entirely.
    value = '\n'.join('[已隱藏可能敏感的一行]' if SENSITIVE.search(line) else line
                      for line in value.splitlines())
    return ''.join(c for c in value if c in '\n\t' or ord(c) >= 32)[:limit]


def normalized(path):
    return ntpath.normcase(ntpath.normpath(str(path).removeprefix('\\\\?\\')))


def find_codex():
    base = Path(os.environ.get('LOCALAPPDATA', '')) / 'OpenAI' / 'Codex' / 'bin'
    candidates = list(base.glob('*/codex.exe')) if base.is_dir() else []
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


class ReadClient:
    """A short-lived stdio client. The allowlist is independent of HTTP input."""

    def __init__(self, executable):
        self.executable = executable

    def __enter__(self):
        if not self.executable or not Path(self.executable).is_file():
            raise ChatError('找不到本機 Codex App Server；請先安裝或開啟原生 Codex。')
        self.deadline = time.monotonic() + 20
        self.messages = queue.Queue(maxsize=64)
        self.process = subprocess.Popen(
            [str(self.executable), 'app-server', '--listen', 'stdio://',
             '-c', 'analytics.enabled=false', '-c', 'otel.log_user_prompt=false'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        self.sequence = 0
        try:
            self._call('initialize', {'clientInfo': {'name': 'nexus_local_observer', 'version': '0.1.0'},
                                      'capabilities': {'experimentalApi': True}})
            self._send({'method': 'initialized'})
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def _read(self):
        try:
            while True:
                line = self.process.stdout.readline(8_388_609)
                if not line or len(line) > 8_388_608:
                    break
                self.messages.put_nowait(json.loads(line))
        except (OSError, ValueError, queue.Full):
            pass
        finally:
            try:
                self.messages.put_nowait(None)
            except queue.Full:
                pass

    def _send(self, message):
        self.process.stdin.write(json.dumps(message).encode() + b'\n')
        self.process.stdin.flush()

    def _call(self, method, params):
        self.sequence += 1
        sequence = self.sequence
        self._send({'id': sequence, 'method': method, 'params': params})
        while True:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise ChatError('Codex 讀取逾時；原生工作未被中止，請稍後重新整理。')
            try:
                message = self.messages.get(timeout=remaining)
            except queue.Empty:
                raise ChatError('Codex 讀取逾時；請稍後重新整理。') from None
            if not isinstance(message, dict):
                raise ChatError('Codex 讀取連線已結束；沒有推定工作狀態。')
            if 'method' in message and 'id' in message:
                self._send({'id': message['id'], 'error': {'code': -32601, 'message': 'Observation only'}})
            elif message.get('id') == sequence:
                if 'error' in message or not isinstance(message.get('result'), dict):
                    raise ChatError('此 Codex 版本無法提供要求的讀取資料；請回原生工具查看。')
                return message['result']

    def call(self, method, params):
        if method not in METHODS:
            raise ChatError('觀察端不提供此操作。')
        return self._call(method, params)

    def __exit__(self, *args):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self.reader.join(timeout=1)
        self.process.stdin.close()
        self.process.stdout.close()


class NativeCodex:
    def __init__(self, chat, executable=None, client_factory=None):
        self.chat = chat
        self.workspace = str(chat.workspace)
        self.executable = executable or find_codex()
        self.client_factory = client_factory or (lambda: ReadClient(self.executable))
        self.lock = threading.Lock()
        self.grants = {}

    def _owner(self):
        owner = self.chat.auth.vault.data['active']
        if self.chat.auth.pending or not owner:
            raise ChatError('請先確認目前 NEXUS 帳戶，再連接本機 Codex 資料。')
        return owner

    def _scope(self, thread):
        if normalized(thread.get('cwd', '')) != normalized(self.workspace):
            raise ChatError('這項 Codex 工作不在目前允許的工作區。')

    def _summary(self, thread):
        self._scope(thread)
        ident = thread['id']
        if not isinstance(ident, str) or not IDENT.fullmatch(ident):
            raise ChatError('Codex 工作識別資訊無效。')
        return {'id': ident, 'title': clean(thread.get('name') or thread.get('preview'), 240) or '未命名 Codex 工作',
                'updated_at': thread.get('updatedAt'), 'source': clean(thread.get('source'), 80),
                'archived': bool(thread.get('archived', False)), 'live_state': 'UNKNOWN',
                'url': 'codex://threads/' + ident}

    def handle(self, action, body):
        if not isinstance(body, dict):
            raise ChatError('Codex 讀取格式不正確。')
        with self.chat.lock, getattr(self.chat.auth, 'lock', self.chat.lock):
            owner = self._owner()
            if action == 'preview' and not body:
                token = secrets.token_urlsafe(32)
                self.grants = {k: v for k, v in self.grants.items() if v['expires'] > time.monotonic()}
                if len(self.grants) >= 32:
                    raise ChatError('已開啟過多連接預覽；請稍後再試。')
                self.grants[token] = {'owner': owner, 'expires': time.monotonic() + 3600, 'confirmed': False}
                return {'token': token, 'workspace': self.workspace, 'available': bool(self.executable),
                        'source': DOCS, 'scope': '目前工作區的原生 Codex 工作標題、最近回合的使用者指令與 Codex 可見回覆。資料屬於這台電腦的 Codex 使用者，未驗證與 NEXUS 登入帳戶相同。只在此分頁閱讀，不加入對話、不傳給模型、不保存副本。'}
            expected = {'token', 'id'} if action == 'detail' else {'token', 'archived'} if action == 'list' else {'token'}
            if set(body) != expected or not isinstance(body.get('token'), str):
                raise ChatError('Codex 讀取格式不正確。')
            grant = self.grants.get(body['token'])
            if not grant or grant['owner'] != owner or grant['expires'] <= time.monotonic():
                raise ChatError('讀取範圍已失效，請重新預覽連接。')
            if action == 'disconnect':
                del self.grants[body['token']]
                return {'disconnected': True}
            if action == 'connect':
                grant['confirmed'] = True
                return {'connected': True}
            if action not in ('list', 'detail') or not grant['confirmed']:
                raise ChatError('請先預覽並確認本機讀取範圍。')
        # Slow subprocess work does not hold account/UI locks.
        if not self.lock.acquire(blocking=False):
            raise ChatError('正在讀取 Codex，請稍候再試。')
        try:
            with self.client_factory() as rpc:
                if action == 'list':
                    if not isinstance(body['archived'], bool):
                        raise ChatError('封存篩選格式不正確。')
                    result = rpc.call('thread/list', {'cwd': [self.workspace, '\\\\?\\' + self.workspace],
                        'useStateDbOnly': True, 'limit': 100, 'sortKey': 'updated_at',
                        'sourceKinds': ['cli', 'vscode', 'exec', 'appServer'], 'archived': body['archived']})
                    data = {'threads': [self._summary(t) | {'archived': body['archived']} for t in result['data']],
                            'has_more': bool(result.get('nextCursor'))}
                else:
                    ident = body['id']
                    if not isinstance(ident, str) or not IDENT.fullmatch(ident):
                        raise ChatError('Codex 工作識別資訊無效。')
                    # Verify authoritative metadata before reading any transcript.
                    thread = rpc.call('thread/read', {'threadId': ident})['thread']
                    summary = self._summary(thread)
                    if summary['id'] != ident:
                        raise ChatError('Codex 工作識別資訊不符。')
                    history = rpc.call('thread/turns/list', {'threadId': ident, 'limit': 5,
                                                          'sortDirection': 'desc', 'itemsView': 'full'})
                    turns = []
                    for turn in history['data']:
                        messages, commands, changes, instructions = [], [], [], []
                        for item in turn.get('items', []):
                            kind = item.get('type')
                            if kind == 'userMessage':
                                content = item.get('content', [])
                                parts = content if isinstance(content, list) else []
                                # Only native visible text. Never load image/file paths,
                                # tool context or synthesize a prompt from another turn.
                                raw = '\n\n'.join(p['text'] for p in parts if isinstance(p, dict)
                                                  and p.get('type') == 'text' and isinstance(p.get('text'), str))
                                instructions.append({'text': clean(raw), 'truncated': len(raw) > 12000,
                                                     'attachments_omitted': any(isinstance(p, dict) and p.get('type') != 'text' for p in parts)})
                            elif kind == 'agentMessage':
                                raw = item.get('text') if isinstance(item.get('text'), str) else ''
                                messages.append({'text': clean(raw), 'phase': clean(item.get('phase'), 40),
                                                 'truncated': len(raw) > 12000})
                            elif kind == 'commandExecution':
                                commands.append({'status': clean(item.get('status'), 40), 'exit_code': item.get('exitCode')})
                            elif kind == 'fileChange':
                                changes.append({'status': clean(item.get('status'), 40)})
                        turns.append({'id': clean(turn.get('id'), 100), 'recorded_status': clean(turn.get('status'), 40),
                                      'started_at': turn.get('startedAt'), 'completed_at': turn.get('completedAt'),
                                      'instructions': instructions[-4:], 'omitted_instructions': max(0, len(instructions) - 4),
                                      'messages': messages[-12:], 'omitted_messages': max(0, len(messages) - 12),
                                      'commands': commands[-20:], 'changes': changes[-20:]})
                    data = {'thread': summary, 'turns': turns, 'has_older': bool(history.get('nextCursor'))}
            with self.chat.lock, getattr(self.chat.auth, 'lock', self.chat.lock):
                if (self._owner() != owner or self.grants.get(body['token']) is not grant
                        or grant['expires'] <= time.monotonic()):
                    raise ChatError('帳戶或讀取範圍已變更；資料未顯示，請重新連接。')
                data.update(captured_at=datetime.now(timezone.utc).isoformat(), workspace=self.workspace,
                            source=DOCS, live_state='UNKNOWN')
                return data
        except ChatError:
            raise
        except Exception:
            raise ChatError('無法確認 Codex 本機記錄；沒有推定完成，請回原生工具查看。') from None
        finally:
            self.lock.release()

    def respond(self, action, body, emit):
        """Keep the account check binding through HTTP serialization and emission."""
        with self.chat.lock, getattr(self.chat.auth, 'lock', self.chat.lock):
            owner = self._owner()
        result = self.handle(action, body)
        with self.chat.lock, getattr(self.chat.auth, 'lock', self.chat.lock):
            if self._owner() != owner:
                raise ChatError('帳戶已變更，請重新確認讀取範圍。')
            if action in ('list', 'detail'):
                grant = self.grants.get(body['token'])
                if not grant or grant['expires'] <= time.monotonic():
                    raise ChatError('讀取範圍已失效，請重新預覽連接。')
            emit(result)
