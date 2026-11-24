"""One explicitly authorized Python documentation snapshot."""

from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
from ipaddress import IPv4Address, IPv4Network
from queue import Empty, Queue
import re
import socket
import ssl
from threading import Event, Lock, Thread
from time import monotonic
from uuid import uuid4

import httpcore

from .siwc import ChatError


HOST = "docs.python.org"
URL = "https://docs.python.org/3.10/library/asyncio-platforms.html"
MAX_BODY = 512 * 1024
MAX_EXCERPT = 8192
LIFETIME = 300
TOTAL_SECONDS = 15
IO_SECONDS = 4
DNS_SECONDS = 4
DNS_SLOT = Lock()
# Include special-purpose ranges even when the platform's ipaddress reports
# them as globally reachable. Only canonical A-record IPv4 values reach TCP.
SPECIAL_IPV4 = tuple(map(IPv4Network, (
    "192.0.0.0/24", "192.0.2.0/24", "192.31.196.0/24", "192.52.193.0/24",
    "192.88.99.0/24", "192.175.48.0/24", "198.18.0.0/15", "198.51.100.0/24",
    "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4",
)))


def public_ipv4(value):
    address = IPv4Address(value)
    if not address.is_global or any(address in net for net in SPECIAL_IPV4):
        raise ChatError("官方網頁的 DNS 回傳不允許的位址，沒有建立連線。")
    return str(address)


def remaining(deadline, cancelled):
    if cancelled.is_set():
        raise ChatError("已取消這次網頁讀取或原授權已失效。")
    seconds = deadline - monotonic()
    if seconds <= 0:
        raise ChatError("網頁讀取逾時，沒有可分享的節錄。")
    return seconds


def resolve(deadline, cancelled):
    remaining(deadline, cancelled)
    if not DNS_SLOT.acquire(blocking=False):
        raise ChatError("上一筆 DNS 查詢尚未結束，沒有開始新的讀取。")
    answer = Queue(maxsize=1)

    def lookup():
        try:
            answer.put(socket.getaddrinfo(HOST, 443, socket.AF_INET, socket.SOCK_STREAM,
                                         socket.IPPROTO_TCP))
        except Exception:
            answer.put(None)
        finally:
            DNS_SLOT.release()

    try:
        Thread(target=lookup, daemon=True).start()
    except Exception:
        DNS_SLOT.release()
        raise ChatError("無法啟動 DNS 查詢。") from None
    try:
        records = answer.get(timeout=min(DNS_SECONDS, remaining(deadline, cancelled)))
    except Empty:
        raise ChatError("官方網頁 DNS 查詢逾時，沒有建立連線。") from None
    remaining(deadline, cancelled)
    if not records:
        raise ChatError("官方網頁沒有可用的 IPv4 解析結果。")
    try:
        addresses = [public_ipv4(record[4][0]) for record in records]
    except ValueError:
        raise ChatError("官方網頁 DNS 回傳不支援的位址。") from None
    return addresses[0]


class BoundedStream(httpcore.NetworkStream):
    def __init__(self, stream, deadline, cancelled):
        self.stream, self.deadline, self.cancelled = stream, deadline, cancelled

    def timeout(self, requested):
        return min(IO_SECONDS, requested if requested is not None else IO_SECONDS,
                   remaining(self.deadline, self.cancelled))

    def read(self, max_bytes, timeout=None):
        return self.stream.read(max_bytes, self.timeout(timeout))

    def write(self, buffer, timeout=None):
        return self.stream.write(buffer, self.timeout(timeout))

    def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        if (server_hostname != HOST or not ssl_context.check_hostname
                or ssl_context.verify_mode != ssl.CERT_REQUIRED):
            raise ChatError("官方網頁的 TLS 驗證條件不符。")
        stream = self.stream.start_tls(ssl_context, server_hostname, self.timeout(timeout))
        return BoundedStream(stream, self.deadline, self.cancelled)

    def close(self):
        self.stream.close()

    def get_extra_info(self, info):
        return self.stream.get_extra_info(info)


class PinnedBackend(httpcore.SyncBackend):
    def __init__(self, address, deadline, cancelled):
        self.address = public_ipv4(address)
        self.deadline, self.cancelled = deadline, cancelled
        self.used = False

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if host != HOST or port != 443 or local_address is not None or self.used:
            raise ChatError("這次網頁授權只能建立一條已核對的 HTTPS 連線。")
        self.used = True
        seconds = min(IO_SECONDS, timeout if timeout is not None else IO_SECONDS,
                      remaining(self.deadline, self.cancelled))
        stream = super().connect_tcp(self.address, 443, seconds, socket_options=socket_options)
        if stream.get_extra_info("server_addr") != (self.address, 443):
            stream.close()
            raise ChatError("TCP 實際目的地不符，未送出網頁請求。")
        return BoundedStream(stream, self.deadline, self.cancelled)


class DocumentText(HTMLParser):
    BLOCKS = {"h1", "h2", "h3", "h4", "p", "li", "dt", "dd", "pre", "tr", "br"}
    OMIT = {"script", "style", "template", "noscript", "svg", "nav", "header", "footer"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.body = None
        self.complete = False
        self.sections = []
        self.omit = None
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if self.complete or self.omit:
            return
        if self.body is None:
            if tag == "main" or (tag == "div" and dict(attrs).get("role") == "main"):
                self.body = tag
            return
        if tag in self.OMIT:
            self.omit = tag
        elif tag == "section":
            self.sections.append(dict(attrs).get("id"))
            self.parts.append("\n")
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.omit:
            if tag == self.omit:
                self.omit = None
        elif self.body and not self.complete:
            if tag == "section" and self.sections:
                self.sections.pop()
            if tag in self.BLOCKS or tag in {"section", "div"}:
                self.parts.append("\n")
            # Sphinx wraps the article in div[role=main]. Stop after the
            # containing section or main ends so its footer cannot enter.
            if tag == "main" or (tag == "section" and not self.sections and self.parts):
                self.complete = True

    def handle_data(self, data):
        if self.body and not self.complete and not self.omit:
            self.parts.append(re.sub(r"\s+", " ", data))


def read_snapshot(url, cancelled):
    if url != URL:
        raise ChatError("此版本只允許讀取指定的 Python 官方文件頁。")
    deadline = monotonic() + TOTAL_SECONDS
    address = resolve(deadline, cancelled)
    backend = PinnedBackend(address, deadline, cancelled)
    try:
        with httpcore.ConnectionPool(network_backend=backend, retries=0,
                                     max_connections=1, max_keepalive_connections=0) as pool:
            with pool.stream("GET", URL, headers={
                "Host": HOST, "Accept": "text/html, text/plain",
                "Accept-Encoding": "identity", "Connection": "close",
            }) as response:
                if response.status != 200:
                    raise ChatError(f"官方網頁取得失敗（HTTP {response.status}）。")
                types = [value.lower() for key, value in response.headers if key.lower() == b"content-type"]
                encodings = [value.strip().lower() for key, value in response.headers
                             if key.lower() == b"content-encoding"]
                content_type = types[0].split(b";", 1)[0].strip() if len(types) == 1 else b""
                if content_type not in (b"text/html", b"text/plain") or encodings not in ([], [b"identity"]):
                    raise ChatError("網頁的內容類型或壓縮格式不在 E1 支援範圍內。")
                charset = re.findall(rb";\s*charset\s*=\s*([^;]+)", types[0])
                if charset and (len(charset) != 1 or charset[0].strip(b' "\t') not in (b"utf-8", b"utf8")):
                    raise ChatError("只支援 UTF-8 公開文件。")
                body = bytearray()
                for chunk in response.iter_stream():
                    remaining(deadline, cancelled)
                    if len(body) + len(chunk) > MAX_BODY:
                        raise ChatError("網頁正文超過 512 KiB。")
                    body.extend(chunk)
    except (OSError, httpcore.NetworkError, httpcore.TimeoutException, httpcore.ProtocolError):
        raise ChatError("官方網頁取得失敗。請檢查網路、TLS 或服務狀態。") from None
    try:
        decoded = body.decode("utf-8-sig")
    except UnicodeError:
        raise ChatError("網頁正文無法以 UTF-8 讀取。") from None
    if content_type == b"text/html":
        parser = DocumentText()
        try:
            parser.feed(decoded)
            parser.close()
        except (AssertionError, ValueError):
            raise ChatError("網頁正文無法解析。") from None
        decoded = "".join(parser.parts) if parser.complete else ""
    lines = [line.strip() for line in decoded.splitlines() if line.strip()]
    excerpt = "\n".join(lines)
    if len(excerpt) < 40:
        raise ChatError("已收到網頁，但可辨識的正文不足。")
    if len(excerpt.encode()) > MAX_EXCERPT:
        raise ChatError("正文超過可預覽的 8 KiB，未產生可分享節錄。")
    remaining(deadline, cancelled)
    return {
        "id": "S1", "key": "web:" + str(uuid4()), "name": "Python 官方文件 · asyncio 平台支援",
        "url": URL, "captured_at": datetime.now(timezone.utc).isoformat(),
        "response_sha256": sha256(body).hexdigest(), "text": excerpt, "sha256": sha256(excerpt.encode()).hexdigest(),
        "peer_ipv4": address,
    }


class WebSource:
    def __init__(self, chat):
        self.chat = chat
        self.pending = self.preview = self.active = None

    def reset(self):
        self.pending = self.preview = None
        if self.active:
            self.active["cancelled"].set()

    def owner(self, chat_id):
        if chat_id is None:
            account = self.chat._project_owner(None)
        else:
            with self.chat.connect() as db:
                account = self.chat._project_owner(db, chat_id, require_chat=True)
        return account, self.chat.workspace, chat_id

    def respond(self, action, body):
        chat = self.chat
        with chat.lock, getattr(chat.auth, "lock", chat.lock):
            if action == "preview" and set(body) == {"chat", "url"}:
                if body["url"] != URL:
                    raise ChatError("請指定此版本核准的 Python 3.10 asyncio 平台頁。")
                owner = self.owner(body["chat"])
                if self.active:
                    raise ChatError("已有網頁讀取正在結束，請稍候。")
                self.reset()
                ticket = str(uuid4())
                self.pending = {"ticket": ticket, "owner": owner, "until": monotonic() + LIFETIME,
                                "cancelled": Event()}
                return {"ticket": ticket, "url": URL}
            if action not in ("fetch", "cancel") or set(body) != {"chat", "ticket"}:
                raise ChatError("網頁讀取要求格式不正確。")
            owner = self.owner(body["chat"])
            grant = next((item for item in (self.pending, self.preview, self.active)
                          if item and item["ticket"] == body["ticket"] and item["owner"] == owner), None)
            if action == "cancel":
                if grant is not None:
                    self.reset()
                return {}
            if grant is None or grant is not self.pending or self.active or monotonic() >= grant["until"]:
                raise ChatError("讀取授權已失效或已使用，請重新確認。")
            self.pending = None
            self.active = grant
        try:
            record = read_snapshot(URL, grant["cancelled"])
            with chat.lock, getattr(chat.auth, "lock", chat.lock):
                if grant["cancelled"].is_set() or owner != self.owner(body["chat"]):
                    raise ChatError("帳戶、對話或讀取授權已變更。")
                self.preview = dict(grant, until=monotonic() + LIFETIME, source=record)
                return record.copy()
        finally:
            with chat.lock:
                self.active = None

    def source(self, selection, chat_id, *, consume=False):
        with self.chat.lock, getattr(self.chat.auth, "lock", self.chat.lock):
            grant = self.preview
            if (not grant or grant["owner"] != self.owner(chat_id)
                    or monotonic() >= grant["until"] or selection != [grant["source"]["key"]]):
                raise ChatError("網頁節錄授權已失效，請重新確認讀取。")
            if consume:
                self.preview = None
            return [grant["source"].copy()]
