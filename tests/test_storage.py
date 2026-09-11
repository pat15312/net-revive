import os
import sqlite3

import pytest

from app.backup import backup
from app.config import Bootstrap
from app.database import Database
from app.main import create_app
from app.restart import history


def test_online_backup_preserves_configuration(configured, app, tmp_path):
    destination = tmp_path / "backup.db"
    backup(app.state.db.path, destination)
    with sqlite3.connect(destination) as conn:
        assert conn.execute("SELECT name FROM operators").fetchone()[0] == "Operator A"
    assert os.stat(destination).st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        backup(app.state.db.path, destination)
    with pytest.raises(ValueError):
        backup(app.state.db.path, app.state.db.path)


async def test_unexpected_worker_failure_reconciles_only_its_event(configured, app):
    from conftest import group

    configured.request("POST", "/api/admin/groups", group([3]))
    first = app.state.restart.admit(1, "Operator A")
    second = app.state.restart.admit(2, "Operator A")

    def broken_factory():
        raise RuntimeError("Private exception detail must not be logged.")

    app.state.client_factory = broken_factory
    await app.state.restart.execute(first)
    events = {e["id"]: e for e in history(app.state.db)}
    assert events[first]["result"] == "interrupted"
    assert events[second]["result"] == "dispatching"


def test_newer_schema_rejected(tmp_path):
    path = tmp_path / "new.db"
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA user_version=999")
    with pytest.raises(RuntimeError, match="newer"):
        Database(path)


def test_secret_key_persists(tmp_path):
    config = Bootstrap(database_path=str(tmp_path / "database.db"), background=False)
    first = create_app(config)
    ciphertext = first.state.cipher.encrypt(b"sample-private-key")
    second = create_app(config)
    assert second.state.cipher.decrypt(ciphertext) == b"sample-private-key"
    assert os.stat(tmp_path / "secret.key").st_mode & 0o777 == 0o600
