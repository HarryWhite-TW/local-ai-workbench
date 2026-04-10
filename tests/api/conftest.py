from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app.db import init_db
from api.app.main import create_app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "test_app.db"
    monkeypatch.setenv("APP_DB_PATH", str(db_path))
    init_db()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client

