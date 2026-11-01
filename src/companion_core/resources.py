"""Bounded workspace text previews and owner-scoped reference URLs. No model/network IO."""
from contextlib import contextmanager, ExitStack
import hashlib
import os
from pathlib import Path
import re
import stat
import time
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from .siwc import ChatError

MAX_BYTES = 65_536
MAX_DOCUMENTS = 64
TEXT_TYPES = {'.md': 'Markdown', '.txt': '文字', '.rst': 'reStructuredText'}
SENSITIVE_NAME = re.compile(r'(?i)(secret|credential|password|private|token|vault|\.env|id_rsa|id_ed25519|\.pem|\.key|sk-[a-z0-9_-]{16,})')
SENSITIVE_TEXT = re.compile(r'(?i)-----BEGIN (?:[A-Z ]*PRIVATE KEY)|\bsk-[A-Za-z0-9_-]{16,}|\bBearer\s+[A-Za-z0-9._-]{16,}|\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|(?:api[_-]?key|access[_-]?token|password|client[_-]?secret)\s*[=:]\s*[\"\']?[^\s\"\'<>]{8,}')
CONTROL = re.compile(r'[\x00-\x20\x7f-\x9f\u202a-\u202e\u2066-\u2069]')


def reparse(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


@contextmanager
def windows_handle(path, directory=False):
    """Pin a non-reparse object against rename; verify its opened final path before reading."""
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    # Directory handles allow ordinary writes but disallow rename/delete. A file
    # handle excludes writes as well; sharing violations fail closed.
    handle = kernel.CreateFileW(str(path), 0x80000000, 3 if directory else 1, None, 3,
                                0x00200000 | (0x02000000 if directory else 0), None)
    if handle == wintypes.HANDLE(-1).value:
        raise OSError('Cannot safely open resource')
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = kernel.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
        if not 0 < size < len(buffer) or os.path.normcase(buffer.value.removeprefix('\\\\?\\')) != os.path.normcase(str(path)):
            raise OSError('Resource final path mismatch')
        if reparse(path.lstat()):
            raise OSError('Reparse point is not a document')
        yield handle
    finally:
        kernel.CloseHandle(handle)


def checked_path(root, relative):
    parts = relative.split('/')
    if parts[0] not in ('README.md', 'AGENTS.md', 'docs') or len(parts) > 2 or any(p in ('', '.', '..') or '\\' in p or ':' in p for p in parts):
        raise OSError('Outside document scope')
    path = root
    for part in parts:
        path = path / part
        if reparse(path.lstat()):
            raise OSError('Reparse point is not allowed')
    if path.resolve(strict=True) != path or not path.is_relative_to(root):
        raise OSError('Document path mismatch')
    return path


def read_text(root, relative):
    if SENSITIVE_NAME.search(relative) or Path(relative).suffix.lower() not in TEXT_TYPES:
        raise ValueError('這類文件不提供預覽。')
    try:
        with ExitStack() as stack:
            if os.name == 'nt':
                stack.enter_context(windows_handle(root, True))
                if relative.startswith('docs/'):
                    stack.enter_context(windows_handle(checked_path(root, 'docs'), True))
            path = checked_path(root, relative)
            before = path.stat()
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_BYTES or not before.st_mode & 0o444:
                raise OSError()
            if os.name == 'nt':
                import msvcrt
                import ctypes
                from ctypes import wintypes
                handle = stack.enter_context(windows_handle(path))
                kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                kernel.DuplicateHandle.argtypes = [wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE,
                    ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                kernel.GetCurrentProcess.restype = wintypes.HANDLE
                duplicate = wintypes.HANDLE()
                process = kernel.GetCurrentProcess()
                if not kernel.DuplicateHandle(process, handle, process, ctypes.byref(duplicate), 0, False, 2):
                    raise OSError()
                fd = msvcrt.open_osfhandle(duplicate.value, os.O_RDONLY | os.O_BINARY)
            else:
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, 'rb') as stream:
                opened = os.fstat(stream.fileno())
                if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
                    raise OSError()
                raw = stream.read(MAX_BYTES + 1)
                after = os.fstat(stream.fileno())
            latest = checked_path(root, relative).stat()
            identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_nlink)
            if len(raw) > MAX_BYTES or identity(opened) != identity(after) or identity(after) != identity(latest):
                raise OSError()
            content = raw.decode('utf-8-sig')
            if re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', content) or SENSITIVE_TEXT.search(content):
                raise ValueError('內容含有敏感或非文字資料，不提供預覽。')
            return content, hashlib.sha256(raw).hexdigest(), len(raw)
    except (OSError, UnicodeError):
        raise ValueError('無法安全讀取；可能不可讀、超過 64 KiB、已變動或位置受限。') from None


def safe_url(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 2048 or CONTROL.search(value) or any(c in value for c in '\\<>"`') or re.search(r'(?i)%(?:0[0-9a-f]|1[0-9a-f]|7f|5c)', value):
        raise ChatError('請使用不含登入資訊的 HTTP／HTTPS 參考網址。')
    try:
        p = urlsplit(value)
        if p.scheme not in ('http', 'https') or not p.hostname or p.username is not None or p.password is not None or not p.netloc or SENSITIVE_TEXT.search(value):
            raise ValueError()
        host = p.hostname.encode('idna').decode('ascii')
        if ':' in host:
            import ipaddress
            ipaddress.IPv6Address(host)
            host = '[' + host + ']'
        elif any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label) for label in host.rstrip('.').split('.')):
            raise ValueError()
        if re.search(r'(?i)(?:^|[?&#])(?:token|api[_-]?key|password|secret|access[_-]?token|auth)=', value):
            raise ValueError()
        port = p.port
        if port is not None and not 1 <= port <= 65535:
            raise ValueError()
        return urlunsplit((p.scheme, host.lower() + (f':{port}' if port else ''), p.path or '/', p.query, p.fragment))
    except (ValueError, UnicodeError):
        raise ChatError('網址格式不安全；只接受普通 HTTP／HTTPS 參考網址。') from None


class ProjectResources:
    def __init__(self, chat):
        self.chat = chat
        self.catalog = {}
        self.pending = None
        self.handoff = None
        with chat.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS project_reference_links (
                id TEXT PRIMARY KEY, workspace TEXT NOT NULL, account TEXT NOT NULL,
                name TEXT NOT NULL, url TEXT NOT NULL, created TEXT NOT NULL)''')

    def owner(self, body, keys):
        if not isinstance(body, dict) or set(body) != {'workspace', *keys} or body['workspace'] != self.chat.workspace:
            raise ChatError('目前工作區無權存取這份專案資源。')
        with self.chat.connect() as db:
            return self.chat._project_owner(db)

    def candidates(self):
        root = Path(self.chat.workspace)
        result = [name for name in ('README.md', 'AGENTS.md') if os.path.lexists(root / name)]
        try:
            folder = checked_path(root, 'docs')
            with ExitStack() as stack:
                if os.name == 'nt':
                    stack.enter_context(windows_handle(root, True))
                    stack.enter_context(windows_handle(folder, True))
                before = folder.stat()
                documents = []
                with os.scandir(folder) as entries:
                    # Enumeration and result sizes are both bounded, including non-doc entries.
                    for i, entry in enumerate(entries):
                        if i >= 256:
                            break
                        if Path(entry.name).suffix.lower() in TEXT_TYPES and not SENSITIVE_NAME.search(entry.name):
                            documents.append('docs/' + entry.name)
                after = checked_path(root, 'docs').stat()
                if (before.st_ino, before.st_mtime_ns) != (after.st_ino, after.st_mtime_ns):
                    raise OSError()
                result.extend(documents)
        except OSError:
            pass  # Missing/unsafe folder grants no access; root documents still work.
        return sorted(result)[:MAX_DOCUMENTS]

    def documents(self, body):
        with self.chat.lock:
            account = self.owner(body, set())
            items, catalog = [], {}
            for relative in self.candidates():
                ident = hashlib.sha256(relative.encode()).hexdigest()[:24]
                item = {'id': ident, 'name': Path(relative).name, 'relative': relative,
                        'type': TEXT_TYPES[Path(relative).suffix.lower()], 'workspace': self.chat.workspace,
                        'category': 'boundary' if relative == 'AGENTS.md' else 'documentation',
                        'available': False, 'version': None}
                try:
                    _, item['version'], item['bytes'] = read_text(Path(self.chat.workspace), relative)
                    item.update(available=True, status='可唯讀預覽')
                    catalog[ident] = (account, self.chat.workspace, relative, item['version'])
                except ValueError as exc:
                    item['status'] = str(exc)
                items.append(item)
            if self.owner(body, set()) != account:
                raise ChatError('目前帳戶已變更，請重新讀取文件索引。')
            self.catalog = catalog
            return {'workspace': self.chat.workspace, 'account': account, 'documents': items,
                    'scope': 'README.md、AGENTS.md 與 docs 第一層文字文件；最多 64 份、每份 64 KiB。',
                    'model_source': '瀏覽及預覽不會提供給模型；需另外確認僅名稱或可見節錄，限下一次對話送出。'}

    def preview(self, body):
        with self.chat.lock:
            account = self.owner(body, {'id', 'version'})
            item = self.catalog.get(body['id']) if isinstance(body['id'], str) else None
            if not item or item[:2] != (account, self.chat.workspace) or body['version'] != item[3]:
                raise ChatError('文件索引已失效或無權讀取，請重新整理索引。')
            try:
                content, version, size = read_text(Path(self.chat.workspace), item[2])
            except ValueError as exc:
                raise ChatError(str(exc)) from None
            if version != item[3]:
                raise ChatError('文件已變動，請重新整理索引後再預覽。')
            if self.owner(body, {'id', 'version'}) != account:
                raise ChatError('目前帳戶已變更，沒有提供文件內容。')
            return {'workspace': self.chat.workspace, 'account': account, 'id': body['id'],
                    'relative': item[2], 'version': version, 'bytes': size, 'text': content,
                    'status': '已唯讀預覽 · 未提供給模型'}

    def links(self, body):
        with self.chat.lock, self.chat.connect() as db:
            account = self.owner(body, set())
            rows = db.execute('SELECT id,name,url,created FROM project_reference_links WHERE workspace=? AND account=? ORDER BY created,id LIMIT 100', (self.chat.workspace, account)).fetchall()
            links = []
            for row in rows:
                item = dict(row)
                try:
                    item['url'] = safe_url(item['url'])
                    item['available'] = True
                except ChatError:
                    item.update(url=None, available=False)
                links.append(item)
            if self.owner(body, set()) != account:
                raise ChatError('目前帳戶已變更，沒有提供先前帳戶的參考網址。')
            return {'workspace': self.chat.workspace, 'account': account, 'links': links}

    def preview_source(self, body):
        """One ephemeral document grant, bound to the next send in this conversation."""
        with self.chat.lock, getattr(self.chat.auth, 'lock', self.chat.lock):
            account = self.owner(body, {'id', 'version', 'chat', 'scope', 'start', 'end'})
            if body['chat'] is not None:
                self.chat.get(body['chat'])
            document = self.preview({k: body[k] for k in ('workspace', 'id', 'version')})
            scope, start, end = body['scope'], body['start'], body['end']
            if scope == 'name' and start is None and end is None:
                content = Path(document['relative']).name
            elif scope == 'excerpt' and type(start) is int and type(end) is int:
                lines = document['text'].splitlines()
                if not 1 <= start <= end <= len(lines) or end - start >= 40:
                    raise ChatError('請選擇文件中連續 1 到 40 行的可見節錄。')
                content = '\n'.join(lines[start - 1:end])
                if not content.strip() or len(content.encode('utf-8')) > 8192:
                    raise ChatError('節錄需有可見內容，且不得超過 8 KiB。')
            else:
                raise ChatError('只能提供文件名稱或明確顯示的節錄。')
            from .chat import now
            source = {'id': 'S1', 'key': 'document:' + str(uuid4()),
                      'name': Path(document['relative']).name, 'relative': document['relative'],
                      'version': document['version'], 'captured_at': now(), 'scope': scope,
                      'start_line': start, 'end_line': end, 'text': content,
                      'sha256': hashlib.sha256(content.encode('utf-8')).hexdigest()}
            if self.owner(body, {'id', 'version', 'chat', 'scope', 'start', 'end'}) != account:
                raise ChatError('目前帳戶已變更，沒有授予文件來源。')
            self.handoff = {'source': source, 'account': account, 'workspace': self.chat.workspace,
                            'chat': body['chat'], 'expires': time.monotonic() + 300}
            return {'account': account, 'workspace': self.chat.workspace, 'chat': body['chat'],
                    'source': dict(source)}

    def source(self, selection, chat_id, *, consume=False):
        with self.chat.lock, getattr(self.chat.auth, 'lock', self.chat.lock):
            grant = self.handoff
            try:
                account = self.owner({'workspace': self.chat.workspace}, set())
                if (not grant or selection != [grant['source']['key']] or grant['chat'] != chat_id
                        or grant['workspace'] != self.chat.workspace or grant['account'] != account
                        or grant['expires'] < time.monotonic()):
                    raise ChatError('文件來源授權已失效，請返回文件重新確認本次範圍。')
                if chat_id is not None:
                    self.chat.get(chat_id)
                _, version, _ = read_text(Path(grant['workspace']), grant['source']['relative'])
                if version != grant['source']['version']:
                    raise ChatError('文件已變動，請重新預覽並確認本次提供的範圍。')
                if self.owner({'workspace': grant['workspace']}, set()) != account:
                    raise ChatError('目前帳戶已變更，沒有提供文件內容。')
                return [dict(grant['source'])]
            except ValueError as exc:
                self.handoff = None
                raise ChatError(str(exc)) from None
            finally:
                if consume:
                    self.handoff = None

    def discard_source(self, body):
        with self.chat.lock:
            account = self.owner(body, {'key'})
            if self.handoff and self.handoff['source']['key'] == body['key']:
                self.handoff = None
            return {'account': account, 'workspace': self.chat.workspace}

    def preview_link(self, body):
        with self.chat.lock:
            account = self.owner(body, {'name', 'url'})
            name = body['name']
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or re.search(r'[\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]', name) or SENSITIVE_TEXT.search(name):
                raise ChatError('連結名稱需要 1 到 80 個可顯示字元。')
            url = safe_url(body['url'])
            self.pending = {'account': account, 'workspace': self.chat.workspace, 'name': name.strip(),
                            'url': url, 'approval': str(uuid4()), 'expires': time.monotonic() + 300}
            return {k: self.pending[k] for k in ('account', 'workspace', 'name', 'url', 'approval')}

    def confirm_link(self, body):
        with self.chat.lock, self.chat.connect() as db:
            pending, self.pending = self.pending, None
            account = self.owner(body, {'approval'})
            if not pending or pending['expires'] < time.monotonic() or pending['approval'] != body['approval'] or pending['account'] != account or pending['workspace'] != self.chat.workspace:
                raise ChatError('參考網址預覽已失效，請重新檢查並確認。')
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT COUNT(*) FROM project_reference_links WHERE workspace=? AND account=?', (self.chat.workspace, account)).fetchone()[0] >= 100:
                raise ChatError('目前帳戶的專案參考網址已達 100 筆上限。')
            ident = str(uuid4())
            from datetime import datetime, timezone
            db.execute('INSERT INTO project_reference_links VALUES (?,?,?,?,?,?)', (ident, self.chat.workspace, account, pending['name'], safe_url(pending['url']), datetime.now(timezone.utc).isoformat()))
            return {'id': ident, 'workspace': self.chat.workspace, 'account': account}

    def open_link(self, body):
        with self.chat.lock:
            account = self.owner(body, {'id'})
            current = self.links({'workspace': self.chat.workspace})
            if current['account'] != account:
                raise ChatError('目前帳戶已變更，請重新檢查參考網址。')
            for item in current['links']:
                if item['id'] == body['id'] and item['available']:
                    return {'workspace': self.chat.workspace, 'account': account, **item}
            raise ChatError('目前帳戶與工作區無法開啟此參考網址。')
