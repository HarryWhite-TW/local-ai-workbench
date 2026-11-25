"""Official picker observations are separate from verified Responses choices."""
import pytest

from src.companion_core import model_catalog
from src.companion_core.codex_work_agent import CodexWorkAgent
from src.companion_core.domain import Failure
from src.companion_core.native_collaboration import verified_executor
from src.companion_core.runtime import RuntimeFailure
from tests.companion_core.test_codex_work_agent import host, new_turn  # noqa: F401


def test_catalog_preserves_picker_omission_and_provider_scope(host, monkeypatch):
    account = host.auth.vault.data["active"]
    catalog = model_catalog.CodexCatalog("official.exe")
    monkeypatch.setattr(model_catalog, "official_models", lambda *_: {
        "gpt-6.1-terra": (("medium", "high", "ultra"), "high"),
        "gpt-new": (("high",), "high"),
    })
    catalog.refresh(host.workspace, account)

    def choices(owner=account):
        return {row["slug"]: row for row in catalog.choices(host, owner, CodexWorkAgent.catalog())}

    initial = choices()
    assert initial["gpt-6.2-sol"]["reasoning_efforts"] == ["low", "medium"]
    assert not initial["gpt-6.2-sol"]["official_listed"]
    assert initial["gpt-6.1-terra"]["effort_status"] == {
        "medium": "verified", "high": "unverified", "ultra": "sdk_unsupported",
    }
    assert initial["gpt-6.1-terra"]["reasoning_efforts"] == ["medium", "high"]
    assert initial["gpt-6.1-terra"]["default_effort"] == "medium"
    assert initial["gpt-new"]["effort_status"] == {"high": "unverified"}
    assert "gpt-new" not in choices("other")
    _, turn = new_turn(host)
    with host.connect() as db:
        db.execute("UPDATE turns SET model='gpt-new',status='complete',response_id='test' WHERE id=?", (turn,))
        db.execute("UPDATE turn_delivery SET state='complete',effort='high' WHERE turn=?", (turn,))
    catalog.expires = 0
    assert catalog.status(account) == "expired"
    assert choices()["gpt-new"]["effort_status"] == {"high": "verified"}
    assert "gpt-new" not in choices("other")
    assert choices()["gpt-6.1-terra"]["reasoning_efforts"] == ["medium"]
    assert all(not row["official_listed"] for row in choices().values())


@pytest.mark.parametrize("failure,status", [
    (Failure.CONNECTION, "fallback"), (Failure.AUTHENTICATION, "account_unavailable"),
])
def test_failed_refresh_isolated_from_stale_official_choices(host, monkeypatch, failure, status):
    def fail(*_):
        raise RuntimeFailure(failure)

    account = host.auth.vault.data["active"]
    catalog = model_catalog.CodexCatalog("official.exe")
    catalog.official = {"gpt-stale": (("high",), "high")}
    monkeypatch.setattr(model_catalog, "official_models", fail)
    catalog.refresh(host.workspace, account)
    rows = catalog.choices(host, account, CodexWorkAgent.catalog())
    assert catalog.status(account) == status
    assert [row["slug"] for row in rows] == ([] if status == "account_unavailable" else [
        "gpt-6.2-sol", "gpt-6.1-terra",
    ])


def test_missing_verified_executable_cannot_confirm_plus(host, tmp_path):
    account = host.auth.vault.data["active"]
    catalog = model_catalog.CodexCatalog(tmp_path / "missing.exe")
    catalog.refresh(host.workspace, account)
    assert catalog.status(account) == "account_unavailable"
    assert not catalog.choices(host, account, CodexWorkAgent.catalog())


def test_desktop_catalog_separates_product_and_provider_proof_and_falls_back(host, monkeypatch):
    owner = host.auth.vault.data["active"]
    catalog = model_catalog.CodexCatalog("pinned.exe", prefer_desktop=True)
    efforts = ("low", "medium", "high", "xhigh", "max", "ultra")
    monkeypatch.setattr(model_catalog, "desktop_models", lambda _: {
        slug: (efforts, "low") for slug in ("gpt-6.2-sol", "gpt-6.2-astra")
    })
    catalog.refresh(host.workspace, owner)

    def choices():
        return {row["slug"]: row for row in catalog.choices(host, owner, CodexWorkAgent.catalog())}

    for slug, row in choices().items():
        if not slug.startswith("gpt-6.2-"):
            continue
        assert row["official_listed"] and row["reasoning_efforts"] == list(efforts[:-1])
        assert row["effort_status"]["ultra"] == "sdk_unsupported"
        assert row["effort_status"]["high"] == "provider_verified"
    assert choices()["gpt-6.2-sol"]["effort_status"]["low"] == "verified"
    assert choices()["gpt-6.2-astra"]["effort_status"]["max"] == "provider_verified"
    _, turn = new_turn(host)
    with host.connect() as db:
        db.execute("UPDATE turns SET model='gpt-6.2-astra',status='complete',response_id='test' WHERE id=?", (turn,))
        db.execute("UPDATE turn_delivery SET state='complete',effort='max' WHERE turn=?", (turn,))

    def fail(_):
        raise OSError("previously approved build unavailable")

    def pinned(_, executable):
        assert executable == "pinned.exe"
        return {"gpt-6.1-terra": (("medium", "high"), "medium")}

    monkeypatch.setattr(model_catalog, "desktop_models", fail)
    monkeypatch.setattr(model_catalog, "official_models", pinned)
    catalog.refresh(host.workspace, owner)
    assert catalog.status(owner) == "fallback_current"
    assert choices()["gpt-6.2-sol"]["reasoning_efforts"] == ["low", "medium"]
    assert choices()["gpt-6.2-astra"]["effort_status"] == {"max": "verified"}
    assert not choices()["gpt-6.2-astra"]["official_listed"]
    assert "high" in choices()["gpt-6.1-terra"]["reasoning_efforts"]


def test_desktop_digest_is_checked_before_launch_and_does_not_grant_execution(tmp_path, monkeypatch):
    path = tmp_path / "codex.exe"
    path.write_bytes(b"unapproved")
    monkeypatch.setattr(model_catalog, "DESKTOP_CATALOG_EXE", path)
    monkeypatch.setattr(model_catalog, "read_catalog", lambda *_: pytest.fail("untrusted catalog launched"))
    with pytest.raises(ValueError, match="catalog executable"):
        model_catalog.desktop_models(str(tmp_path))
    from hashlib import sha256
    monkeypatch.setattr(model_catalog, "DESKTOP_CATALOG_SHA256", sha256(path.read_bytes()).hexdigest())
    with pytest.raises(model_catalog.ChatError):
        verified_executor(path)


@pytest.mark.parametrize(("method", "params"), [
    ("thread/start", {}), ("turn/start", {}), ("command/exec", {}), ("config/value/write", {}),
    ("model/list", {"includeHidden": True}), ("account/read", {"refreshToken": True}),
])
def test_catalog_rejects_disallowed_wire_messages_before_io(method, params):
    client = model_catalog.CatalogClient(".", "catalog.exe")
    with pytest.raises(RuntimeFailure) as error:
        client.send({"id": 1, "method": method, "params": params})
    assert error.value.reason == Failure.POLICY and client.process is None
