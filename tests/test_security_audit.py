"""Adversarial regressions. All controllers and power-cycle operations are fake."""

import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient

from app.database import put_setting
from app.security import hash_password
from app.unifi import UniFiClient, UniFiError
from conftest import PASSWORD, Browser


def test_rebinding_host_cannot_obtain_session(browser):
    response = browser.client.get("/api/session", headers={"Host": "attacker.example:8080"})
    assert response.status_code == 400
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize("host", ["localhost,evil.test", "localhost@evil.test", "127.0.0.1:bad"])
def test_malformed_host_rejected(browser, host):
    assert browser.client.get("/", headers={"host": host}).status_code == 400


def test_duplicate_host_rejected(browser):
    assert browser.client.get("/", headers=[("host", "localhost"), ("host", "evil.test")]).status_code == 400


def test_request_body_bounded_before_parsing(browser):
    result = browser.client.post(
        "/api/login",
        content=b" " * 70000,
        headers={"x-csrf-token": browser.csrf, "content-type": "application/json"},
    )
    assert result.status_code == 413


def test_non_ascii_csrf_is_rejected_without_error(browser):
    result = browser.client.post("/api/logout", headers=[(b"x-csrf-token", b"\xff")])
    assert result.status_code == 403


def test_duplicate_session_cookie_rejected(browser):
    token = browser.client.cookies.get("netrevive_session")
    response = browser.client.get(
        "/api/session", headers={"cookie": f"netrevive_session={token}; netrevive_session=forged"}
    )
    assert response.status_code == 400


def test_anonymous_session_creation_is_throttled(browser, app):
    statuses = []
    for _ in range(65):
        browser.client.cookies.clear()
        statuses.append(browser.client.get("/api/session").status_code)
    assert 429 in statuses
    with app.state.db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM sessions").fetchone()[0] <= 60


def test_unknown_paths_do_not_allocate_sessions(browser, app):
    with app.state.db.connect() as conn:
        before = conn.execute("SELECT count(*) FROM sessions").fetchone()[0]
    browser.client.cookies.clear()
    assert browser.client.get("/not-a-route").status_code == 404
    with app.state.db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM sessions").fetchone()[0] == before


def test_password_rotation_wins_against_inflight_old_login(admin, app, monkeypatch):
    import app.main as main

    original = main.verify_password
    verified, release = threading.Event(), threading.Event()

    def delayed(password, stored):
        result = original(password, stored)
        verified.set()
        assert release.wait(5)
        return result

    monkeypatch.setattr(main, "verify_password", delayed)
    client = TestClient(app)
    with ThreadPoolExecutor() as pool:
        other = Browser(client)
        pending = pool.submit(other.request, "POST", "/api/login", {"password": PASSWORD})
        assert verified.wait(5)
        with app.state.db.connect(write=True) as conn:
            put_setting(conn, "admin_password_hash", hash_password("replacement-test-password"))
            conn.execute("DELETE FROM sessions WHERE admin=1")
        release.set()
        assert pending.result().status_code == 401
        assert other.get("/api/admin/config").status_code == 401


def test_environment_key_cannot_follow_controller_change(inventory, app):
    app.state.bootstrap.unifi_api_key = "fake-environment-key"
    result = inventory.request("PUT", "/api/admin/unifi", {"controller_url": "https://different.test"})
    assert result.status_code == 422


def client_with(handler):
    return UniFiClient(
        {"controller_url": "https://controller.test", "api_prefix": "/integration/v1", "verify_tls": True},
        "fake-key",
        httpx.MockTransport(handler),
    )


async def test_controller_response_size_limit():
    client = client_with(lambda r: httpx.Response(200, content=json.dumps({"data": ["x" * 2100000]})))
    with pytest.raises(UniFiError):
        await client.sites()


async def test_controller_listing_limit():
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "data": [{"id": str(i + calls * 100)} for i in range(100)] if calls <= 21 else [],
                "totalCount": 1000000,
            },
        )

    with pytest.raises(UniFiError):
        await client_with(handler).sites()
    assert calls <= 21


@pytest.mark.parametrize("identifier", ["..", ".", "a/b", "a%2fb", "a?b"])
async def test_controller_identifiers_are_opaque(identifier):
    calls = []
    client = client_with(lambda r: calls.append(r) or httpx.Response(200, json={"id": identifier}))
    with pytest.raises(UniFiError):
        await client.device("site-a", identifier)
    assert not calls


async def test_mismatched_port_identity_never_dispatches():
    calls = []
    client = client_with(
        lambda r: (
            calls.append(r)
            or httpx.Response(
                200,
                json={"id": "switch-a", "state": "ONLINE", "interfaces": {"ports": [{"idx": 1, "poe": {}}]}},
            )
        )
    )
    target = {"site_id": "site-a", "switch_id": "switch-a", "port_id": "1", "port_number": 2}
    with pytest.raises(UniFiError):
        await client.validate(target)
    with pytest.raises(UniFiError):
        await client.power_cycle(target)
    assert not any(r.method == "POST" for r in calls)


@pytest.mark.parametrize("path", ["/healthz", "/static/app.js", "/missing"])
def test_security_headers_cover_all_responses(browser, path):
    response = browser.get(path)
    assert "frame-ancestors 'none'" in response.headers.get("content-security-policy", "")
    assert response.headers.get("x-content-type-options") == "nosniff"


@pytest.mark.parametrize(
    "method,path,data",
    [
        ("GET", "/api/admin/config", None),
        ("GET", "/api/admin/history", None),
        ("PUT", "/api/admin/general", {"title": "attacker", "timezone": "UTC"}),
        ("PUT", "/api/admin/monitoring", {}),
        ("PUT", "/api/admin/unifi", {}),
        ("POST", "/api/admin/unifi/test", {}),
        ("POST", "/api/admin/unifi/discover", None),
        ("PUT", "/api/admin/targets/1", {"label": "attacker"}),
        ("POST", "/api/admin/operators", {"name": "attacker"}),
        ("PUT", "/api/admin/operators/1", {"name": "attacker"}),
        ("DELETE", "/api/admin/operators/1", None),
        ("POST", "/api/admin/groups", {}),
        ("PUT", "/api/admin/groups/1", {}),
        ("DELETE", "/api/admin/groups/1", None),
        ("POST", "/api/admin/order/users/1", {"direction": "down"}),
        ("POST", "/api/admin/order/groups/1", {"direction": "down"}),
        ("POST", "/api/admin/setup/finish", None),
        (
            "PUT",
            "/api/admin/password",
            {"current_password": PASSWORD, "new_password": "replacement-password"},
        ),
    ],
)
def test_all_admin_routes_deny_ordinary_sessions(browser, app, method, path, data):
    assert browser.request(method, path, data).status_code == 401
    assert app.state.fake.calls == []


@pytest.mark.parametrize(
    "origin", ["https://evil.example", "null", "http://testserver.evil.example", "https://testserver"]
)
def test_hostile_origins_cannot_write(admin, origin):
    response = admin.client.post("/api/logout", headers={"origin": origin, "x-csrf-token": admin.csrf})
    assert response.status_code == 403
    assert admin.get("/api/admin/config").status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/docs",
        "/redoc",
        "/openapi.json",
        "/data/netrevive.db",
        "/static/../security.py",
        "/static/%2e%2e/security.py",
    ],
)
def test_private_files_and_debug_routes_not_served(browser, path):
    assert browser.get(path).status_code == 404


@pytest.mark.parametrize(
    "host", ["localhost", "127.0.0.1:8080", "192.168.1.50:18081", "[::1]:8080", "[fd00::123]:8080"]
)
def test_private_ip_and_explicit_host_access_preserved(browser, host):
    assert browser.client.get("/api/session", headers={"host": host}).status_code == 200


def test_forwarded_headers_cannot_authorize_host(browser):
    response = browser.client.get(
        "/api/session",
        headers={"host": "evil.test", "x-forwarded-host": "localhost", "x-forwarded-for": "127.0.0.1"},
    )
    assert response.status_code == 400


def test_expired_admin_and_forged_cookie_rejected(admin, app):
    with app.state.db.connect(write=True) as conn:
        conn.execute("UPDATE sessions SET expires_at=0")
    assert admin.get("/api/admin/config").status_code == 401
    admin.client.cookies.clear()
    admin.client.cookies.set("netrevive_session", "forged")
    assert admin.get("/api/admin/config").status_code == 401


def test_database_failure_cannot_dispatch(configured, app):
    with app.state.db.connect() as conn:
        conn.execute(
            "CREATE TRIGGER fail_admission BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT, 'test fault'); END"
        )
    response = configured.request("POST", "/api/groups/1/restart", {"operator": "Operator A"})
    assert response.status_code == 503
    assert app.state.fake.calls == []
    assert "test fault" not in response.text


def test_replay_resolves_new_membership_and_rejects_old_session(configured, app):
    from app.restart import RestartService

    service = RestartService(app.state.db, app.state.health, lambda: app.state.fake)
    first = service.admit(1, "Operator A")
    asyncio.run(service.execute(first))
    with app.state.db.connect(write=True) as conn:
        conn.execute("UPDATE targets SET locked_until=0")
        conn.execute("UPDATE restart_groups SET locked_until=0")
        conn.execute("DELETE FROM group_targets WHERE group_id=1")
        conn.execute("INSERT INTO group_targets VALUES(1,2)")
    second = service.admit(1, "Operator A")
    asyncio.run(service.execute(second))
    assert app.state.fake.calls == [1, 2]
    old_token, old_csrf = configured.client.cookies.get("netrevive_session"), configured.csrf
    configured.request("POST", "/api/logout")
    response = configured.client.post(
        "/api/groups/1/restart",
        json={"operator": "Operator A"},
        headers={"cookie": "netrevive_session=" + old_token, "x-csrf-token": old_csrf},
    )
    assert response.status_code == 403


def test_legacy_password_upgraded_on_login(browser, app):
    import base64
    import hashlib
    from app.database import setting

    salt = b"0123456789abcdef"
    old_hash = base64.b64encode(
        salt + hashlib.scrypt(PASSWORD.encode(), salt=salt, n=16384, r=8, p=1)
    ).decode()
    with app.state.db.connect(write=True) as conn:
        put_setting(conn, "admin_password_hash", old_hash)
    assert browser.request("POST", "/api/login", {"password": PASSWORD}).status_code == 200
    with app.state.db.connect() as conn:
        assert setting(conn, "admin_password_hash").startswith("$argon2id$v=19$m=19456,t=2,p=1$")


def test_second_worker_cannot_change_bootstrap_password(admin, app):
    from app.config import Bootstrap
    from app.main import create_app
    from app.database import setting
    from app.security import verify_password

    other = create_app(
        Bootstrap(
            database_path=app.state.db.path,
            admin_password="other-test-password",
            background=False,
            allowed_hosts="testserver",
        )
    )
    with pytest.raises(RuntimeError, match="one NetRevive process"):
        with TestClient(other):
            pass
    with app.state.db.connect() as conn:
        assert verify_password(PASSWORD, setting(conn, "admin_password_hash"))
    assert admin.get("/api/admin/config").status_code == 200


def test_sqlite_files_private_from_first_open(tmp_path, monkeypatch):
    import os
    import sqlite3
    from app.database import Database

    original = sqlite3.connect

    def checked(path, **kwargs):
        assert os.stat(path).st_mode & 0o777 == 0o600
        return original(path, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", checked)
    db = Database(tmp_path / "private.db")
    with db.connect(write=True) as conn:
        put_setting(conn, "test", "synthetic")
        for path in tmp_path.glob("private.db*"):
            assert path.stat().st_mode & 0o777 == 0o600


def test_file_secrets_and_conflicting_sources(tmp_path, monkeypatch):
    from app.config import secret_value

    path = tmp_path / "secret"
    path.write_text("synthetic-key\n")
    monkeypatch.setenv("UNIFI_API_KEY_FILE", str(path))
    monkeypatch.delenv("UNIFI_API_KEY", raising=False)
    assert secret_value("UNIFI_API_KEY") == "synthetic-key"
    monkeypatch.setenv("UNIFI_API_KEY", "different-key")
    with pytest.raises(RuntimeError):
        secret_value("UNIFI_API_KEY")


async def test_custom_controller_ca_is_loaded(tmp_path, monkeypatch):
    import ssl

    original = ssl.create_default_context
    seen = []

    def context(*args, **kwargs):
        seen.append(kwargs.get("cafile"))
        return original()

    monkeypatch.setattr(ssl, "create_default_context", context)
    client = client_with(lambda r: httpx.Response(200, json={"data": []}))
    client.ca_file = str(tmp_path / "controller-ca.pem")
    await client.sites()
    assert client.ca_file in seen


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"id": "other-device"},
        {"id": "switch-a", "interfaces": []},
        {"id": "switch-a", "interfaces": {"ports": [{"idx": 1, "poe": {}}, {"idx": 1, "poe": {}}]}},
    ],
)
async def test_malformed_controller_details_fail_closed(payload):
    with pytest.raises(UniFiError):
        await client_with(lambda r: httpx.Response(200, json=payload)).device("site-a", "switch-a")


async def test_real_private_ca_tls_verification(tmp_path):
    import datetime
    import ipaddress
    import ssl
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Isolated audit CA")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    certpath, keypath = tmp_path / "ca.pem", tmp_path / "test-only-key.pem"
    certpath.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    keypath.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            assert self.headers["X-API-Key"] == "synthetic-tls-key"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"data": []}')

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certpath, keypath)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    settings = {
        "controller_url": f"https://127.0.0.1:{server.server_port}",
        "api_prefix": "/integration/v1",
        "verify_tls": True,
    }
    try:
        with pytest.raises(UniFiError, match="certificate could not be verified"):
            await UniFiClient(settings, "synthetic-tls-key").sites()
        assert await UniFiClient(settings, "synthetic-tls-key", ca_file=str(certpath)).sites() == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


async def test_chunked_request_body_limit():
    from app.http_security import HTTPBoundary

    called, sent = [], []

    async def inner(*args):
        called.append(True)

    chunks = iter(
        [
            {"type": "http.request", "body": b"x" * 40000, "more_body": True},
            {"type": "http.request", "body": b"x" * 40000, "more_body": False},
        ]
    )

    async def receive():
        return next(chunks)

    async def send(message):
        sent.append(message)

    await HTTPBoundary(inner, "localhost")(
        {"type": "http", "headers": [(b"host", b"localhost")], "client": ("127.0.0.1", 1)}, receive, send
    )
    assert not called
    assert sent[0]["status"] == 413


def test_session_capacity_evicts_only_anonymous(browser, app):
    from app.security import new_session

    with app.state.db.connect(write=True) as conn:
        conn.executemany(
            "INSERT INTO sessions VALUES (?,?,0,9999999999)", [(str(i), "synthetic") for i in range(1023)]
        )
        conn.execute(
            "UPDATE sessions SET admin=1 WHERE token_hash NOT IN (SELECT CAST(value AS TEXT) FROM json_each(?))",
            (json.dumps(list(range(1023))),),
        )
    _, session = new_session(app.state.db)
    assert not session["admin"]
    with app.state.db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM sessions").fetchone()[0] == 1024
        assert conn.execute("SELECT count(*) FROM sessions WHERE admin=1").fetchone()[0] == 1


def test_saved_key_and_origin_are_one_snapshot(inventory, app, monkeypatch):
    import app.main as main

    original = main.setting
    changed = False

    def interleave(conn, key, default=None):
        nonlocal changed
        value = original(conn, key, default)
        if key == "api_key_encrypted" and not changed:
            changed = True
            with app.state.db.connect(write=True) as writer:
                put_setting(writer, "controller_url", "https://replacement.test")
                put_setting(
                    writer, "api_key_encrypted", app.state.cipher.encrypt(b"new-synthetic-key").decode()
                )
        return value

    monkeypatch.setattr(main, "setting", interleave)
    client = app.state.real_client_factory()
    assert client.settings["controller_url"] == "https://controller.test"
    assert client.api_key == "private-test-key"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://controller.test",
        "gopher://controller.test",
        "https://user:password@controller.test",
        "https://controller.test/path",
        "https://controller.test?x=y",
        "https://controller.test\\@evil.test",
        "https://controller.test\n.evil.test",
    ],
)
def test_unsupported_outbound_origins_rejected(admin, url):
    assert (
        admin.request("PUT", "/api/admin/unifi", {"controller_url": url, "api_key": "synthetic"}).status_code
        == 422
    )


def test_only_one_concurrent_setup_claim_succeeds(browser, app):
    clients = [Browser(TestClient(app)), Browser(TestClient(app))]
    with ThreadPoolExecutor() as pool:
        results = list(
            pool.map(lambda b: b.request("POST", "/api/setup", {"password": PASSWORD}).status_code, clients)
        )
    assert sorted(results) == [200, 409]


def test_failed_login_logs_do_not_include_password(browser, caplog):
    marker = "synthetic-private-password-marker"
    browser.request("POST", "/api/login", {"password": marker})
    assert "admin_login_failed" in caplog.text
    assert marker not in caplog.text


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS", "PATCH", "DELETE"])
def test_alternate_methods_cannot_restart(configured, app, method):
    response = configured.client.request(
        method, "/api/groups/1/restart", headers={"x-csrf-token": configured.csrf}
    )
    assert response.status_code == 405
    assert not app.state.fake.calls
