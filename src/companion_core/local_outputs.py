"""Explicit, Windows-only delivery of saved Companion answers."""

from contextlib import ExitStack, contextmanager
import ctypes
from ctypes import wintypes as w
from hashlib import sha256
import msvcrt
import os
from pathlib import Path
import re
from time import monotonic
from uuid import uuid4

from .siwc import ChatError


ROOT = Path.home() / "NEXUS-Outputs"
NAME = re.compile(r"nexus-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.md")
LIMIT = 128 * 1024
READ = 0x80000000
WRITE = 0x40000000
DIRECTORY = 0x10
REPARSE = 0x400
OPEN_EXISTING = 3
CREATE_NEW = 1
SHARE_READ = 1
OPEN_REPARSE_POINT = 0x00200000
BACKUP_SEMANTICS = 0x02000000


class FileInfo(ctypes.Structure):
    _fields_ = [("attributes", w.DWORD), ("created", w.FILETIME), ("accessed", w.FILETIME),
                ("written", w.FILETIME), ("volume", w.DWORD), ("size_high", w.DWORD),
                ("size_low", w.DWORD), ("links", w.DWORD), ("id_high", w.DWORD),
                ("id_low", w.DWORD)]


def bind(library, name, result, *args):
    function = getattr(library, name)
    function.argtypes, function.restype = args, result
    return function


class OutputFolder:
    def __init__(self, root=ROOT):
        self.root = root
        self.identity = None
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.open = bind(kernel, "CreateFileW", w.HANDLE, w.LPCWSTR, w.DWORD, w.DWORD,
                         w.LPVOID, w.DWORD, w.DWORD, w.HANDLE)
        self.close = bind(kernel, "CloseHandle", w.BOOL, w.HANDLE)
        self.file_info = bind(kernel, "GetFileInformationByHandle", w.BOOL, w.HANDLE, ctypes.POINTER(FileInfo))
        self.final_path = bind(kernel, "GetFinalPathNameByHandleW", w.DWORD,
                               w.HANDLE, w.LPWSTR, w.DWORD, w.DWORD)
        self.drive_type = bind(kernel, "GetDriveTypeW", w.UINT, w.LPCWSTR)

    def open_path(self, path, *, directory=False, create=False):
        # Keep all ancestors open without write/delete sharing while using the
        # path. This denies replacement and reparse metadata updates.
        flags = OPEN_REPARSE_POINT | (BACKUP_SEMANTICS if directory else 0)
        handle = self.open(str(path), READ | (WRITE if create else 0), 0 if create else SHARE_READ,
                           None, CREATE_NEW if create else OPEN_EXISTING, flags, None)
        if handle == w.HANDLE(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        return handle

    def checked(self, handle, path, directory=False):
        info = FileInfo()
        path_buffer = ctypes.create_unicode_buffer(32768)
        count = self.final_path(handle, path_buffer, len(path_buffer), 0)
        actual = path_buffer.value.removeprefix("\\\\?\\")
        if (not 0 < count < len(path_buffer) or os.path.normcase(actual) != os.path.normcase(str(path))
                or not self.file_info(handle, ctypes.byref(info)) or info.attributes & REPARSE
                or bool(info.attributes & DIRECTORY) != directory
                or (not directory and info.links != 1)):
            raise ChatError("成果位置或檔案身分無法安全核對。")
        return info.volume, info.id_high, info.id_low

    @contextmanager
    def pin(self):
        if self.drive_type(self.root.anchor) != 3:
            raise ChatError("成果位置必須在本機固定磁碟。")
        with ExitStack() as stack:
            for path in (*reversed(self.root.parents), self.root):
                try:
                    handle = self.open_path(path, directory=True)
                except FileNotFoundError:
                    if path != self.root or self.identity is not None:
                        raise ChatError("成果資料夾或上層位置已不存在。") from None
                    try:
                        path.mkdir()
                    except FileExistsError:
                        pass
                    handle = self.open_path(path, directory=True)
                stack.callback(self.close, handle)
                identity = self.checked(handle, path, directory=True)
            if self.identity is not None and self.identity != identity:
                raise ChatError("成果資料夾已被替換，已停止操作。")
            self.identity = identity
            yield identity

    @contextmanager
    def file(self, name, *, create=False):
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise ChatError("只接受成果清單中的 Markdown 檔案。")
        path = self.root / name
        handle = self.open_path(path, create=create)
        try:
            identity = self.checked(handle, path)
            fd = msvcrt.open_osfhandle(handle, os.O_BINARY | (os.O_RDWR if create else os.O_RDONLY))
        except Exception:
            self.close(handle)
            if create:
                raise UncertainOutput from None
            raise
        try:
            stream = os.fdopen(fd, "r+b" if create else "rb")
        except Exception:
            os.close(fd)
            if create:
                raise UncertainOutput from None
            raise
        with stream:
            yield stream, handle, path, identity

    def save(self, grant):
        with self.pin() as root_id:
            if root_id != grant["root_id"]:
                raise ChatError("目的資料夾已變更，請重新預覽。")
            name, data = grant["name"], grant["data"]
            created = False
            try:
                with self.file(name, create=True) as (stream, handle, path, identity):
                    created = True
                    if stream.write(data) != len(data):
                        raise OSError("Incomplete write")
                    stream.flush()
                    os.fsync(stream.fileno())
                    stream.seek(0)
                    actual = stream.read(LIMIT + 1)
                    if actual != data or self.checked(handle, path) != identity:
                        raise UncertainOutput
            except FileExistsError:
                if not created:
                    raise ChatError("同名成果已存在，沒有覆寫。") from None
                return {"status": "UNKNOWN", "name": name}
            except (OSError, ChatError, UncertainOutput) as exc:
                if created or isinstance(exc, UncertainOutput):
                    return {"status": "UNKNOWN", "name": name}
                raise
            return {"status": "SAVED", "name": name, "path": str(path),
                    "size": len(actual), "sha256": sha256(actual).hexdigest()}

    def list(self):
        records = []
        with self.pin(), os.scandir(self.root) as files:
            for index, entry in enumerate(files):
                if index >= 1024:
                    raise ChatError("成果資料夾項目超出查詢上限。")
                if not NAME.fullmatch(entry.name):
                    continue
                try:
                    # Windows DirEntry.stat() can return a zero link count.
                    info = os.lstat(entry.path)
                except FileNotFoundError:
                    continue
                if (info.st_file_attributes & (REPARSE | DIRECTORY) or info.st_nlink != 1
                        or info.st_size > LIMIT):
                    continue
                records.append({"name": entry.name, "size": info.st_size, "modified": info.st_mtime})
        return sorted(records, key=lambda r: (r["modified"], r["name"]), reverse=True)

    def inspect(self, name, expected=None, locate=False):
        with self.pin() as root_id, self.file(name) as (stream, handle, path, identity):
            data = stream.read(LIMIT + 1)
            if len(data) > LIMIT or self.checked(handle, path) != identity:
                raise ChatError("無法核對成果檔案。")
            content = data.decode("utf-8")
            digest = sha256(data).hexdigest()
            record = {"name": name, "path": str(path), "text": content, "size": len(data), "sha256": digest}
            # The receipt is bound to the file object, not solely its name/bytes.
            key = (root_id, identity, digest)
            if locate:
                if expected != key:
                    raise ChatError("成果自預覽後已變更，請重新檢視。")
                locate_in_explorer(path)
            return record, key


class UncertainOutput(Exception):
    pass


def locate_in_explorer(path):
    ole, shell = ctypes.OleDLL("ole32"), ctypes.WinDLL("shell32")
    initialize = bind(ole, "CoInitializeEx", ctypes.c_long, w.LPVOID, w.DWORD)
    parse = bind(shell, "SHParseDisplayName", ctypes.c_long, w.LPCWSTR, w.LPVOID,
                 ctypes.POINTER(w.LPVOID), w.DWORD, w.LPVOID)
    select = bind(shell, "SHOpenFolderAndSelectItems", ctypes.c_long, w.LPVOID, w.UINT, w.LPVOID, w.DWORD)
    free = bind(ole, "CoTaskMemFree", None, w.LPVOID)
    item = w.LPVOID()
    try:
        initialize(None, 2)
    except OSError:
        raise ChatError("無法在目前的 Windows 工作階段開啟檔案總管。") from None
    try:
        if parse(str(path), None, ctypes.byref(item), 0, None) < 0 or not item:
            raise ChatError("檔案總管無法識別這份成果。")
        if select(item, 0, None, 0) < 0:
            raise ChatError("檔案總管定位失敗。")
    finally:
        if item:
            free(item)
        ole.CoUninitialize()


class LocalOutputs:
    def __init__(self, chat, folder=None):
        self.chat = chat
        self.folder = folder if folder is not None else OutputFolder()
        self.pending = self.view = None

    def reset(self):
        self.pending = self.view = None

    def respond(self, action, body, *, work=None):
        chat = self.chat
        chat_id = body.get("chat")
        with chat.lock, getattr(chat.auth, "lock", chat.lock):
            if chat_id is None:
                account = chat._project_owner(None)
            else:
                with chat.connect() as db:
                    account = chat._project_owner(db, chat_id, require_chat=True)
            owner = (account, chat.workspace, chat_id)
            try:
                return self.operation(action, body, owner, work)
            except FileNotFoundError:
                raise ChatError("成果檔案已不存在。") from None
            except (OSError, UnicodeError):
                raise ChatError("Windows 無法安全完成這項成果操作。") from None

    def operation(self, action, body, owner, work):
        if action == "list" and set(body) == {"chat"}:
            return self.folder.list()
        if action == "preview" and set(body) == {"chat", "turn"} and owner[2]:
            conversation = self.chat.get(owner[2])
            turn = next((t for t in conversation["turns"] if t["id"] == body["turn"] and
                         t["status"] == "complete" and t.get("delivery_state", "complete") == "complete"
                         and t.get("answer")), None)
            if turn is None:
                raise ChatError("請選擇這段對話中已完成的回答。")
            name = "nexus-" + turn["id"] + ".md"
            if not NAME.fullmatch(name):
                raise ChatError("此回答的識別無法用於建立成果。")
            content = turn["answer"].replace("\r\n", "\n").rstrip() + "\n"
            data = content.encode("utf-8")
            if len(data) > LIMIT:
                raise ChatError("此回答超過成果上限 128 KiB。")
            digest = sha256(data).hexdigest()
            with self.folder.pin() as root_id:
                pass
            token = str(uuid4())
            self.pending = {"token": token, "owner": owner, "work": work, "name": name, "data": data,
                            "root_id": root_id, "until": monotonic() + 300}
            return {"token": token, "name": name, "path": str(self.folder.root / name),
                    "text": content, "sha256": digest}
        if action in ("save", "cancel") and set(body) == {"chat", "token"}:
            grant = self.pending
            if (not grant or grant["owner"] != owner or grant["work"] != work or grant["token"] != body["token"]
                    or grant["until"] <= monotonic()):
                raise ChatError("成果確認已失效，請重新預覽。")
            self.pending = None
            return self.folder.save(grant) if action == "save" else {}
        if action == "inspect" and set(body) == {"chat", "name"}:
            self.view = None
            record, key = self.folder.inspect(body["name"])
            token = str(uuid4())
            self.view = (owner, token, body["name"], key, monotonic() + 300)
            return {**record, "token": token}
        if action == "locate" and set(body) == {"chat", "token"}:
            view = self.view
            if not view or view[:2] != (owner, body["token"]) or view[4] <= monotonic():
                raise ChatError("請先重新檢視要定位的成果。")
            record, _ = self.folder.inspect(view[2], expected=view[3], locate=True)
            return {"status": "EXPLORER_REQUESTED", "name": record["name"]}
        raise ChatError("成果操作格式不正確。")
