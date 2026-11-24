"""E1 tests use synthetic DNS/HTTP or local TLS. No public network or models."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from http.client import HTTPConnection
import json
import socket
import ssl
from threading import Event, RLock, Thread
from time import monotonic
from types import SimpleNamespace

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import httpcore
import pytest

from src.companion_core import web_source as web
from src.companion_core.chat import Conversations, now
from src.companion_core.daily import WorkNotConnected
from src.companion_core.review import ReviewStore
from src.companion_core.siwc import ChatError
from src.companion_core.surface import Surface, make_server


@pytest.mark.parametrize("address", [
    "127.0.0.1", "192.168.0.1", "169.254.169.254", "100.64.0.1",
    "192.0.0.9", "192.0.2.1", "224.0.0.1", "240.0.0.1", "::1", "::ffff:127.0.0.1",
])
def test_destination_refuses_special_address(address):
    with pytest.raises((ChatError, ValueError)):
        web.PinnedBackend(address, monotonic() + 1, Event())


def test_transport_uses_validated_numeric_peer_and_original_hostname(monkeypatch):
    transcript = []
    payload = (b"<div role='main'><section><h1>Windows</h1><p>"
               b"Some event loop features are unavailable on this platform."
               b"</p><script>not visible</script></section></div>")
    raw = (b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
           + b"Content-Length: " + str(len(payload)).encode() + b"\r\n\r\n" + payload)
    chunks = iter((raw, b""))
    address = "151.101.0.223"

    class Stream:
        def read(self, size, timeout):
            return next(chunks, b"")

        def write(self, data, timeout):
            transcript.append(data)

        def start_tls(self, context, hostname, timeout):
            assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
            transcript.append(hostname)
            return self

        def get_extra_info(self, name):
            return (address, 443) if name == "server_addr" else None

        def close(self):
            pass

    def dial(self, host, port, timeout=None, **kwargs):
        transcript.append((host, port))
        return Stream()

    def dns(host, port, *args):
        transcript.append((host, port))
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 443))]

    monkeypatch.setattr(socket, "getaddrinfo", dns)
    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", dial)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9999")
    record = web.read_snapshot(web.URL, Event())
    assert transcript[:3] == [(web.HOST, 443), (address, 443), web.HOST]
    sent = b"".join(transcript[3:]).lower()
    assert sent.count(b"get ") == 1 and b"host: docs.python.org\r\n" in sent
    assert all(header not in sent for header in (b"cookie:", b"authorization:", b"referer:"))
    assert record["peer_ipv4"] == address and record["response_sha256"] == sha256(payload).hexdigest()
    assert record["text"].startswith("Windows\nSome event") and "not visible" not in record["text"]


def test_real_tls_rejects_wrong_hostname_before_http(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "local-fixture.invalid")])
    instant = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(instant - timedelta(days=1))
            .not_valid_after(instant + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("local-fixture.invalid")]), critical=False)
            .sign(key, hashes.SHA256()))
    key_file = tmp_path / "key.pem"
    cert_file = tmp_path / "cert.pem"
    key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(cert_file, key_file)
    received = []
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        listener.settimeout(4)
        port = listener.getsockname()[1]

        def serve():
            with listener.accept()[0] as connected:
                connected.settimeout(4)
                try:
                    with server_context.wrap_socket(connected, server_side=True) as tls:
                        received.append(tls.recv(4096))
                except ssl.SSLError:
                    received.append("TLS refused")

        thread = Thread(target=serve)
        thread.start()
        # Inject a loopback test socket below the destination guard. The
        # production TLS wrapper still sees the real certificate and SNI.
        stream = httpcore.SyncBackend().connect_tcp("127.0.0.1", port, 3)
        bounded = web.BoundedStream(stream, monotonic() + 4, Event())
        context = ssl.create_default_context(cafile=str(cert_file))
        try:
            with pytest.raises(httpcore.ConnectError, match="Hostname mismatch"):
                bounded.start_tls(context, web.HOST)
        finally:
            bounded.close()
            thread.join(5)
        assert received == ["TLS refused"]


def test_dns_timeout_cannot_trigger_late_dial(monkeypatch):
    release = Event()
    monkeypatch.setattr(web, "DNS_SECONDS", 0.01)

    def lookup(*args):
        release.wait(2)
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("151.101.0.223", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", lookup)
    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp",
                        lambda *a, **k: pytest.fail("expired DNS must never dial"))
    try:
        with pytest.raises(ChatError, match="DNS 查詢逾時"):
            web.read_snapshot(web.URL, Event())
    finally:
        release.set()
        assert web.DNS_SLOT.acquire(timeout=2)
        web.DNS_SLOT.release()


def test_numeric_socket_dial_rejects_different_peer(monkeypatch):
    address = "151.101.0.223"
    called = []
    fake_socket = SimpleNamespace(
        setsockopt=lambda *args: None,
        getpeername=lambda: ("151.101.64.223", 443),
        close=lambda: called.append("closed"),
    )

    def socket_connect(endpoint, timeout, source_address=None):
        called.append(endpoint)
        return fake_socket

    monkeypatch.setattr(socket, "create_connection", socket_connect)
    backend = web.PinnedBackend(address, monotonic() + 3, Event())
    with pytest.raises(ChatError, match="TCP 實際目的地不符"):
        backend.connect_tcp(web.HOST, 443)
    with pytest.raises(ChatError, match="只能建立一條"):
        backend.connect_tcp(web.HOST, 443)
    assert called == [(address, 443), "closed"]


@pytest.mark.parametrize(("code", "content_type", "encoding", "body", "error"), [
    (302, b"text/html", b"", b"", "HTTP 302"),
    (200, b"application/pdf", b"", b"pdf", "內容類型"),
    (200, b"text/html", b"gzip", b"compressed", "壓縮格式"),
    (200, b"text/plain; charset=latin1", b"", b"", "UTF-8"),
    (200, b"text/html", b"", b"<!doctype html><p>Only layout</p>", "正文不足"),
    (200, b"text/plain", b"", b"x" * (web.MAX_BODY + 1), "512 KiB"),
], ids=["redirect", "pdf", "compressed", "charset", "no-main", "oversized"])
def test_rejects_unsupported_responses(monkeypatch, code, content_type, encoding, body, error):
    from contextlib import contextmanager
    request = []

    @contextmanager
    def stream(self, method, url, **options):
        request.append((method, url))
        yield SimpleNamespace(status=code, iter_stream=lambda: iter((body,)),
                              headers=[(b"content-type", content_type)] +
                              ([(b"content-encoding", encoding)] if encoding else []))

    monkeypatch.setattr(web, "resolve", lambda *_: "151.101.0.223")
    monkeypatch.setattr(httpcore.ConnectionPool, "stream", stream)
    with pytest.raises(ChatError, match=error):
        web.read_snapshot(web.URL, Event())
    assert request == [("GET", web.URL)]


def test_http_confirmations_conversation_identity_and_history(tmp_path, monkeypatch):
    auth = SimpleNamespace(lock=RLock(), pending=None, vault=SimpleNamespace(data={"active": "owner"}),
                           access=lambda account: "synthetic-token")
    chat = Conversations(tmp_path, tmp_path, auth)
    chat.resources.web = web.WebSource(chat)
    chat.models, chat.models_account = [{"slug": "fixture"}], "owner"
    downloads, inputs = [], []
    excerpt = "Windows fixture line one. Windows fixture line two."
    snapshot = {"id": "S1", "key": "web:test", "name": "fixture", "text": excerpt, "url": web.URL,
                "captured_at": now(), "sha256": sha256(excerpt.encode()).hexdigest()}

    def download(url, cancel):
        downloads.append(url)
        return snapshot

    def infer(ident, model, token, messages, sources, *, routing=None):
        assert routing is None
        inputs.append(messages)
        with chat.lock, chat.connect() as db:
            db.execute("UPDATE turns SET status='complete',answer=? WHERE id=?",
                       ("Fixture answer repeats " + excerpt if sources else "other answer", ident))
            chat.busy = None

    monkeypatch.setattr(web, "read_snapshot", download)
    monkeypatch.setattr(chat, "_run", infer)
    with chat.connect() as db:
        db.executemany("INSERT INTO chats VALUES (?,?,?,?,?)",
                       [(ident, chat.workspace, owner, ident, now())
                        for ident, owner in (("a", "owner"), ("b", "owner"), ("foreign", "other"))])
    surface = Surface(WorkNotConnected(), tmp_path, ReviewStore(tmp_path / "reviews"))
    with make_server(surface, chat) as server:
        worker = Thread(target=server.serve_forever)
        worker.start()

        def post(action, body):
            with_connection = HTTPConnection("127.0.0.1", server.server_port, timeout=4)
            try:
                with_connection.request("POST", "/api/chat/" + action, json.dumps(body), {
                    "Origin": f"http://127.0.0.1:{server.server_port}",
                    "Content-Type": "application/json", "X-Companion-UI": "1",
                })
                response = with_connection.getresponse()
                return response.status, json.loads(response.read())
            finally:
                with_connection.close()

        try:
            assert post("web-preview", {"chat": "a", "url": web.URL + "?x=1"})[0] == 409
            assert post("web-preview", {"chat": "foreign", "url": web.URL})[0] == 409
            ticket = post("web-preview", {"chat": "a", "url": web.URL})[1]["ticket"]
            assert post("web-fetch", {"chat": "b", "ticket": ticket})[0] == 409
            assert downloads == inputs == []
            assert post("web-fetch", {"chat": "a", "ticket": ticket}) == (200, snapshot)
            assert post("web-fetch", {"chat": "a", "ticket": ticket})[0] == 409
            body = {"chat": "a", "question": "Windows support?", "model": "fixture", "sources": ["web:test"],
                    "preview": {"web:test": "wrong"}, "request_id": "one"}
            assert post("send", body)[0] == 409 and not inputs
            ticket = post("web-preview", {"chat": "a", "url": web.URL})[1]["ticket"]
            assert post("web-fetch", {"chat": "a", "ticket": ticket})[0] == 200
            assert post("web-cancel", {"chat": "a", "ticket": ticket})[0] == 200
            body["preview"]["web:test"] = snapshot["sha256"]
            assert post("send", body)[0] == 409 and not inputs
            ticket = post("web-preview", {"chat": "a", "url": web.URL})[1]["ticket"]
            assert post("web-fetch", {"chat": "a", "ticket": ticket})[0] == 200
            assert post("send", {**body, "chat": "b"})[0] == 409 and not inputs
            code, receipt = post("send", body)
            assert code == 200
            chat.worker.join(5)
            assert excerpt in inputs[0][-1]["content"]
            assert post("send", body) == (200, receipt) and len(inputs) == 1
            assert post("get", {"chat": "a"})[1]["turns"][0]["sources"] == [snapshot]
            assert post("send", {**body, "request_id": "two", "question": "later", "sources": [], "preview": None})[0] == 200
            chat.worker.join(5)
            assert len(inputs) == 2 and excerpt not in str(inputs[1])
            assert "Windows support?" not in str(inputs[1]) and downloads == [web.URL] * 3
        finally:
            server.shutdown()
            worker.join(5)
