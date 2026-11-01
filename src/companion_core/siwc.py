"""Official SIWC public-client flow. No credentials from other applications.

Contract: https://developers.openai.com/siwc/token-sharing-open-source/sign-in
The foreground host holds an exclusive store lease for its whole lifetime.
"""
import base64
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import secrets
import ssl
import tempfile
import threading
import time
from urllib.parse import urlencode
from uuid import uuid4
import webbrowser

import httpx
import jwt
import truststore

ISSUER = "https://auth.openai.com"
RESOURCE = "https://api.openai.com/v1"
TOKEN = ISSUER + "/api/accounts/oauth/token"
AUTHORIZE = ISSUER + "/api/accounts/authorize"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"


class ChatError(ValueError):
    """Only a fixed, public message may cross into UI/logs."""


def client():
    return httpx.Client(verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
                        trust_env=False, follow_redirects=False,
                        timeout=httpx.Timeout(40, connect=15))


def dpapi(data, decrypt=False):
    """Windows current-user protection; no machine-wide or plaintext fallback."""
    if os.name != "nt":
        raise ChatError("此版本的受保護儲存需要 Windows。")

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]

    buf = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    target = Blob()
    library = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    function = library.CryptUnprotectData if decrypt else library.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ChatError("無法使用目前 Windows 帳戶的受保護儲存。")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))


class Vault:
    """One DPAPI encrypted file, atomic replacement, one process owner."""

    def __init__(self, directory, workspace):
        requested = Path(directory).absolute()
        self.directory = requested.resolve()
        if (requested != self.directory or self.directory.is_relative_to(Path(workspace).resolve())
                or any((p / ".git").exists() for p in (self.directory, *self.directory.parents))):
            raise ChatError("登入與對話資料必須存於 Repository 外的本機目錄。")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "accounts.dpapi"
        self.lease = None
        self._check()
        if os.name != "nt":
            raise ChatError("此版本的受保護儲存需要 Windows。")
        import msvcrt
        lockpath = self.directory / "host.lock"
        if lockpath.is_symlink():
            raise ChatError("本機資料位置不安全。")
        self.lease = open(lockpath, "a+b")
        try:
            # Windows denies reads of another owner's locked byte. Inspect size,
            # then acquire the lock before accessing its protected contents.
            if os.fstat(self.lease.fileno()).st_size == 0:
                self.lease.write(b"0")
                self.lease.flush()
            self.lease.seek(0)
            msvcrt.locking(self.lease.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self.lease.close()
            self.lease = None
            raise ChatError("另一個 Companion 已開啟此資料目錄。請先關閉它。") from None
        try:
            if self.path.exists():
                self.data = json.loads(dpapi(self.path.read_bytes(), decrypt=True))
                if self.data.get("version") != 1 or not isinstance(self.data.get("accounts"), dict):
                    raise ValueError()
            else:
                self.data = {"version": 1, "host": "urn:uuid:" + str(uuid4()),
                             "active": None, "accounts": {}}
                self.save()
        except Exception:
            self.close()
            raise ChatError("無法讀取受保護登入資料；沒有覆寫原檔。") from None

    def _check(self):
        if (self.directory.resolve() != self.directory or self.path.is_symlink()
                or (self.path.exists() and self.path.stat().st_size > 2_000_000)):
            raise ChatError("本機登入資料位置或大小不安全。")

    def save(self):
        self._check()
        encrypted = dpapi(json.dumps(self.data, ensure_ascii=False).encode("utf-8"))
        fd, name = tempfile.mkstemp(prefix=".account-", dir=self.directory)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(encrypted)
                f.flush()
                os.fsync(f.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def close(self):
        if self.lease:
            self.lease.close()
            self.lease = None


class SignIn:
    def __init__(self, vault, transport=None):
        self.vault = vault
        self.http = transport or client()
        self.lock = threading.RLock()
        self.pending = None
        self.notice = "請使用自己的 ChatGPT 帳戶登入。"

    def snapshot(self):
        with self.lock:
            data = self.vault.data
            if self.pending and time.monotonic() > self.pending["until"]:
                self.pending = None
                self.notice = "登入已逾時，請重新開始。"
            return {"active": data["active"], "pending": self.pending is not None,
                    "notice": self.notice, "accounts": [
                        {"id": key, "label": a["label"], "signed_in": bool(a.get("access_token"))}
                        for key, a in data["accounts"].items()]}

    def begin(self, origin, account=None):
        with self.lock:
            self.snapshot()
            if self.pending:
                raise ChatError("登入進行中，請完成瀏覽器操作或稍後重試。")
            old = self.vault.data["accounts"].get(account) if account else None
            if account and old is None:
                raise ChatError("找不到指定帳戶。")
            state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
            redirect = origin + "/auth/callback"
            params = {"client_id": old["client_id"] if old else "dynamic_agent_client",
                      "ext_agent_host_id": self.vault.data["host"], "response_type": "code",
                      "redirect_uri": redirect, "scope": SCOPES, "resource": RESOURCE,
                      "state": state, "nonce": nonce, "code_challenge_method": "S256",
                      "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")}
            if old:
                if old.get("id_token"):
                    params["id_token_hint"] = old["id_token"]
            else:
                params["agent_name_hint"] = "Local Companion"
            self.pending = {"state": state, "nonce": nonce, "verifier": verifier,
                            "redirect": redirect, "account": account, "until": time.monotonic() + 300}
            self.notice = "請在官方登入頁面完成登入與同意，再回到 Companion。"
            # Authorization URLs can contain ID tokens. Never return or log them.
            try:
                opened = webbrowser.open(AUTHORIZE + "?" + urlencode(params))
            except Exception:
                opened = False
            if not opened:
                self.pending = None
                raise ChatError("無法開啟系統瀏覽器，請確認預設瀏覽器後重試。")

    def _json(self, method, url, **kwargs):
        try:
            r = self.http.request(method, url, **kwargs)
        except httpx.TimeoutException:
            raise ChatError("登入服務連線逾時；請確認網路後再試。") from None
        except httpx.RequestError:
            raise ChatError("無法連接登入服務；尚未取得服務回應，請確認網路。") from None
        if r.status_code != 200:
            message = ("登入服務未接受授權；請重新登入此帳戶。" if r.status_code in (400, 401) else
                       "登入服務拒絕存取；請確認帳戶資格。" if r.status_code == 403 else
                       "登入服務暫時限制請求；請稍後再試。" if r.status_code == 429 else
                       "登入服務暫時無法使用；請稍後再試。" if r.status_code >= 500 else
                       "登入服務未接受要求；請確認連線或重新登入。")
            raise ChatError(message)
        try:
            if len(r.content) > 2_000_000:
                raise ValueError()
            return r.json()
        except Exception:
            raise ChatError("登入服務回應格式無法驗證；未啟用這次授權。") from None

    def _claims(self, encoded, audience, nonce=None):
        discovery = self._json("GET", ISSUER + "/.well-known/openid-configuration")
        if discovery.get("issuer") != ISSUER or discovery.get("jwks_uri") != ISSUER + "/.well-known/jwks.json":
            raise ChatError("登入服務身分資料不符合預期。")
        keys = self._json("GET", discovery["jwks_uri"])
        try:
            header = jwt.get_unverified_header(encoded)
            if header.get("alg") != "RS256":
                raise ValueError()
            matching = [k for k in keys["keys"] if k.get("kid") == header.get("kid")]
            if len(matching) != 1:
                raise ValueError()
            key = jwt.PyJWK.from_dict(matching[0], algorithm="RS256").key
            claims = jwt.decode(encoded, key, algorithms=["RS256"], issuer=ISSUER,
                                audience=audience, options={"require": ["iss", "aud", "exp", "iat", "sub"]})
            if not isinstance(claims["sub"], str) or not claims["sub"]:
                raise ValueError()
            if nonce is not None and not secrets.compare_digest(claims.get("nonce", ""), nonce):
                raise ValueError()
            if (isinstance(claims["aud"], list) and len(claims["aud"]) > 1
                    and claims.get("azp") != audience):
                raise ValueError()
            if claims.get("azp", audience) != audience:
                raise ValueError()
            return claims
        except Exception:
            raise ChatError("登入身分驗證失敗；未啟用這次授權。") from None

    def _record(self, response, client_id, nonce=None, old=None):
        try:
            scopes = response.get("scope", " ".join(old["scopes"]) if old else "").split()
            if not {"openid", "offline_access", "resource.invoke", "chatgpt.tokens.use.direct"}.issubset(scopes):
                raise ChatError("此授權未開啟 ChatGPT 方案推論權限。")
            if response.get("token_type", "").lower() != "bearer":
                raise ValueError()
            access = response["access_token"]
            refresh = response.get("refresh_token", old.get("refresh_token") if old else None)
            expiry = int(response["expires_in"])
            if not all(isinstance(v, str) and v for v in (access, refresh)) or expiry <= 0:
                raise ValueError()
            if access.startswith("sk-"):
                raise ValueError()
            if response.get("id_token"):
                claims = self._claims(response["id_token"], client_id, nonce)
            elif old and nonce is None:
                claims = {"sub": old["subject"], "email": old["email"]}
            else:
                raise ValueError()
            if old and claims["sub"] != old["subject"]:
                raise ChatError("登入帳戶與原帳戶不一致；沒有替換原授權。")
            return {"client_id": client_id, "subject": claims["sub"],
                    "email": claims.get("email", "ChatGPT"), "scopes": scopes,
                    "access_token": access, "refresh_token": refresh,
                    "id_token": response.get("id_token", old.get("id_token", "") if old else ""),
                    "expires_at": time.time() + expiry}
        except ChatError:
            raise
        except Exception:
            raise ChatError("登入授權資料不完整；未啟用這次授權。") from None

    def callback(self, query):
        with self.lock:
            attempt = self.pending
            if (not attempt or time.monotonic() > attempt["until"]
                    or not secrets.compare_digest(query.get("state", ""), attempt["state"])):
                raise ChatError("登入回應已過期或無法核對，請重新登入。")
            self.pending = None  # Single use, including denied and failed attempts.
            try:
                if "error" in query:
                    raise ChatError("登入未獲授權；未連接模型。")
                old = self.vault.data["accounts"].get(attempt["account"])
                issued = query.get("client_id", old["client_id"] if old else "")
                if (not issued.startswith("oaiapp_") or (old and issued != old["client_id"])
                        or not query.get("code")):
                    raise ChatError("登入註冊資訊不一致或不完整。")
                response = self._json("POST", TOKEN, data={"grant_type": "authorization_code",
                    "client_id": issued, "code": query["code"], "code_verifier": attempt["verifier"],
                    "redirect_uri": attempt["redirect"], "resource": RESOURCE})
                record = self._record(response, issued, attempt["nonce"], old)
                key = attempt["account"] or str(uuid4())
                # A reissued registration maps to the same local identity.
                for ident, saved in self.vault.data["accounts"].items():
                    if (saved["client_id"], saved["subject"]) == (issued, record["subject"]):
                        key = ident
                record["label"] = (old or self.vault.data["accounts"].get(key, {})).get(
                    "label", str(record["email"]) + " · " + key[:8])
                previous = self.vault.data
                self.vault.data = {**previous, "accounts": {**previous["accounts"], key: record}, "active": key}
                try:
                    self.vault.save()
                except Exception:
                    self.vault.data = previous
                    raise ChatError("登入資料無法安全保存；未啟用新授權。") from None
                self.notice = "已登入 ChatGPT。模型能否使用仍需實際推論確認。"
            except ChatError as exc:
                self.notice = str(exc)
                raise

    def access(self, account):
        with self.lock:
            data = self.vault.data
            saved = data["accounts"].get(account)
            if not saved or account != data["active"] or not saved.get("access_token"):
                raise ChatError("請先選擇帳戶並完成 ChatGPT 登入。")
            if saved["expires_at"] < time.time() + 90:
                try:
                    response = self._json("POST", TOKEN, data={"grant_type": "refresh_token",
                        "client_id": saved["client_id"], "refresh_token": saved["refresh_token"],
                        "resource": RESOURCE})
                    fresh = self._record(response, saved["client_id"], old=saved)
                    fresh["label"] = saved["label"]
                    data["accounts"][account] = fresh
                    self.vault.save()
                    saved = fresh
                except ChatError as exc:
                    for name in ("access_token", "refresh_token", "id_token"):
                        saved.pop(name, None)
                    self.vault.save()
                    self.notice = "登入更新未完成。" + str(exc) + " 請重新登入此帳戶；不會自動重試模型請求。"
                    raise ChatError(self.notice) from None
            return saved["access_token"]

    def select(self, account):
        with self.lock:
            if account not in self.vault.data["accounts"]:
                raise ChatError("找不到指定帳戶。")
            self.vault.data["active"] = account
            self.vault.save()

    def logout(self):
        with self.lock:
            self.pending = None
            a = self.vault.data["accounts"].get(self.vault.data["active"])
            confirmed = False
            if a and a.get("refresh_token"):
                try:
                    discovery = self._json("GET", ISSUER + "/.well-known/openid-configuration")
                    endpoint = discovery.get("revocation_endpoint")
                    if endpoint != ISSUER + "/api/accounts/oauth/revoke":
                        raise ValueError()
                    for wait in (0, .5):
                        time.sleep(wait)
                        try:
                            r = self.http.post(endpoint, data={"token": a["refresh_token"],
                                "token_type_hint": "refresh_token", "client_id": a["client_id"]})
                            confirmed = r.status_code == 200
                            if confirmed or r.status_code < 500:
                                break
                        except httpx.HTTPError:
                            pass
                except Exception:
                    pass
            if a:
                for name in ("access_token", "refresh_token", "id_token"):
                    a.pop(name, None)
            self.vault.data["active"] = None
            self.vault.save()
            self.notice = ("已登出並撤銷此登入。" if confirmed else
                           "已清除本機登入；遠端撤銷未確認，可到 ChatGPT Settings 中解除連接。")
