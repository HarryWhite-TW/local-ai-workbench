"""Visible Codex choices and historical evidence for the subscription route."""
from collections import defaultdict
from hashlib import file_digest
from pathlib import Path
from re import fullmatch
from time import monotonic
from typing import get_args

from .domain import Failure
from .native_execution import NativeClient, RpcRejected
from .runtime import RuntimeFailure
from .siwc import ChatError

MAX_AGE = 15 * 60
DESKTOP_CATALOG_EXE = Path(r"C:\Program Files\WindowsApps") / (
    "OpenAI.Codex_26.1120.6357.0_x64__2p2nqsd0c76g0/app/resources/codex.exe"
)
DESKTOP_CATALOG_SHA256 = "2a1ec3f1dd463fd30224be4c0c67d3fe83d3d863a3d7539ccad366952436d2aa"
# Accepted isolated Responses probes, not product turns or permission to list a model.
PROVIDER_EVIDENCE = {
    "gpt-6.2-sol": frozenset(("high", "xhigh", "max")),
    "gpt-6.2-astra": frozenset(("low", "medium", "high", "xhigh", "max")),
}


def supported_efforts():
    # Use the installed Responses SDK's declared wire values.
    from openai.types.shared import ReasoningEffort

    return set(get_args(get_args(ReasoningEffort)[0]))


def model_slug(value):
    return isinstance(value, str) and fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", value)


class CatalogClient(NativeClient):
    methods = frozenset(("account/read", "config/read", "model/list"))

    @staticmethod
    def subscription_ok(account):
        return NativeClient.subscription_ok(account) and account.get("planType") == "plus"

    def send(self, message):
        method, params = message.get("method"), message.get("params", {})
        if method is None and set(message) == {"id", "error"}:
            if message["error"] == {"code": -32601, "message": "Read-only Companion denies this request"}:
                return super().send(message)
        if (method not in self.methods | {"initialize", "initialized"}
                or (method == "model/list" and params.get("includeHidden") is not False)
                or (method == "account/read" and params.get("refreshToken") is not False)
                or (method == "config/read" and params.get("includeLayers") is not False)):
            raise RuntimeFailure(Failure.POLICY)
        return super().send(message)


def official_models(workspace, executable):
    from .native_collaboration import verified_executor

    try:
        verified_executor(executable)
    except ChatError:
        raise RuntimeFailure(Failure.AUTHENTICATION) from None
    return read_catalog(workspace, executable)


def desktop_models(workspace):
    path = DESKTOP_CATALOG_EXE
    # A different Store build needs a separate trust decision before execution.
    if path.resolve(strict=True) != path:
        raise ValueError("Unexpected desktop catalog path")
    with path.open("rb") as stream:
        if file_digest(stream, "sha256").hexdigest() != DESKTOP_CATALOG_SHA256:
            raise ValueError("Unexpected desktop catalog executable")
    return read_catalog(workspace, str(path))


def read_catalog(workspace, executable):
    rows, cursor, seen = {}, None, set()
    with CatalogClient(workspace, executable, settings=('history.persistence="none"',)) as client:
        if client.call("config/read", {"cwd": workspace, "includeLayers": False})["config"]["model_provider"] != "openai":
            raise ValueError("Unexpected catalog provider")
        for _ in range(5):
            params = {"limit": 100, "includeHidden": False}
            if cursor:
                params["cursor"] = cursor
            response = client.call("model/list", params)
            for row in response["data"]:
                slug = row["model"]
                if row["hidden"] or not model_slug(slug):
                    continue
                efforts = tuple(dict.fromkeys(item["reasoningEffort"] for item in row["supportedReasoningEfforts"]))
                if not all(isinstance(effort, str) and fullmatch("[a-z0-9_-]{1,24}", effort) for effort in efforts):
                    raise ValueError("Invalid catalog effort")
                rows[slug] = (efforts, row["defaultReasoningEffort"])
            cursor = response["nextCursor"]
            if cursor is None:
                if not rows:
                    raise ValueError("Empty catalog")
                return rows
            if not isinstance(cursor, str) or not cursor or len(cursor) > 512 or cursor in seen:
                break
            seen.add(cursor)
    raise ValueError("Invalid catalog pagination")


class CodexCatalog:
    def __init__(self, executable, *, prefer_desktop=False):
        self.executable = executable
        self.prefer_desktop = prefer_desktop
        self.owner = None
        self.official = {}
        self.unavailable = set()
        self.expires = 0
        self.refresh_state = "pending"

    def refresh(self, workspace, owner):
        self.owner, self.official, self.expires = owner, {}, 0
        self.unavailable.clear()
        loaded = "current"
        if self.prefer_desktop:
            try:
                self.official = desktop_models(workspace)
            except (RuntimeFailure, OSError, ValueError, AttributeError, KeyError, TypeError, RpcRejected):
                loaded = "fallback_current"
            else:
                self.expires = monotonic() + MAX_AGE
                self.refresh_state = loaded
                return
        try:
            self.official = official_models(workspace, self.executable)
        except RuntimeFailure as exc:
            self.refresh_state = "account_unavailable" if exc.reason is Failure.AUTHENTICATION else "fallback"
        except (OSError, ValueError, AttributeError, KeyError, TypeError, RpcRejected):
            self.refresh_state = "fallback"
        else:
            self.expires = monotonic() + MAX_AGE
            self.refresh_state = loaded

    def status(self, owner):
        if self.owner != owner:
            return "pending"
        if self.refresh_state in ("current", "fallback_current") and monotonic() >= self.expires:
            return "expired"
        return self.refresh_state

    def choices(self, chat, owner, baseline):
        status = self.status(owner)
        if status == "account_unavailable":
            return []
        official = self.official if status in ("current", "fallback_current") else {}
        wire = supported_efforts()
        history = defaultdict(list)
        labels = {}
        for row in baseline:
            slug = row["slug"]
            labels[slug] = row["display_name"], row["default_effort"]
            history[slug].extend(row["reasoning_efforts"])
        with chat.connect() as db:
            durable = db.execute("""SELECT DISTINCT t.model,d.effort FROM turns t
                JOIN chats c ON c.id=t.chat JOIN turn_delivery d ON d.turn=t.id
                WHERE c.account=? AND c.workspace=? AND d.owner=c.account AND d.workspace=c.workspace
                AND t.response_id IS NOT NULL AND t.status='complete' AND d.state='complete'
                ORDER BY t.model,d.effort""", (owner, chat.workspace)).fetchall()
        for slug, effort in durable:
            if model_slug(slug) and effort in wire and effort not in history[slug]:
                history[slug].append(effort)
        rows = []
        for slug in dict.fromkeys((*labels, *history, *official)):
            listed, recommended = official.get(slug, ((), None))
            label, default = labels.get(slug, (slug + " · Codex 訂閱", recommended))
            checked = history[slug]
            efforts = {}
            for effort in dict.fromkeys((*checked, *listed)):
                if effort not in wire:
                    efforts[effort] = "sdk_unsupported"
                elif self.owner == owner and (slug, effort) in self.unavailable:
                    efforts[effort] = "unsupported"
                elif effort in checked:
                    efforts[effort] = "verified"
                elif effort in PROVIDER_EVIDENCE.get(slug, ()):
                    efforts[effort] = "provider_verified"
                else:
                    efforts[effort] = "unverified"
            selectable = [effort for effort, evidence in efforts.items()
                          if evidence not in ("unsupported", "sdk_unsupported")]
            rows.append({"slug": slug, "display_name": label, "official_listed": slug in official,
                         "effort_status": efforts, "reasoning_efforts": selectable,
                         "default_effort": default if default in selectable else (selectable[0] if selectable else None)})
        return rows
