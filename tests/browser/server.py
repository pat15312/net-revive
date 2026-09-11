"""Isolated browser-test server. No production database or controller connections."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn
from app.main import create_app
from app.config import Bootstrap
from conftest import FakeUniFi

if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="netrevive-browser-") as directory:
        app = create_app(Bootstrap(database_path=str(Path(directory) / "test.db"), background=False))
        fake = FakeUniFi()
        app.state.client_factory = lambda: fake
        uvicorn.run(app, host="127.0.0.1", port=8019, access_log=False)
