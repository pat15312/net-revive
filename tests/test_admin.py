import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.config import Bootstrap
from app.database import Database
from app.main import create_app
from app.security import verify_password
from conftest import Browser, PASSWORD, group


def test_first_run_setup(configured):
    assert configured.get("/api/session").json()["setup_complete"]
    assert configured.get("/api/status").json()["groups"][0]["button_label"] == "Restart Router"


def test_setup_requires_equipment_and_operator(admin):
    assert admin.request("POST", "/api/admin/setup/finish").status_code == 422


def test_setup_is_one_time(admin):
    assert admin.request("POST", "/api/setup", {"password": "replacement-password"}).status_code == 409


def test_password_minimum(browser):
    assert browser.request("POST", "/api/setup", {"password": "short"}).status_code == 422


def test_auth_login_logout(admin):
    assert admin.get("/api/admin/config").status_code == 200
    admin.request("POST", "/api/logout")
    assert admin.get("/api/admin/config").status_code == 401
    browser = Browser(admin.client)
    assert browser.request("POST", "/api/login", {"password": "incorrect"}).status_code == 401
    assert browser.request("POST", "/api/login", {"password": PASSWORD}).status_code == 200
    assert browser.get("/api/admin/config").status_code == 200


def test_unauthorized_admin(browser):
    assert browser.get("/api/admin/config").status_code == 401
    assert browser.request("POST", "/api/admin/groups", group()).status_code == 401


def test_csrf_required(admin):
    assert admin.client.post("/api/admin/operators", json={"name": "forged"}).status_code == 403
    assert (
        admin.client.post(
            "/api/admin/operators",
            json={"name": "forged"},
            headers={"X-CSRF-Token": admin.csrf, "Origin": "https://elsewhere.test"},
        ).status_code
        == 403
    )


def test_session_rotation_and_cookie_flags(browser):
    before = browser.client.cookies.get("netrevive_session")
    response = browser.request("POST", "/api/setup", {"password": PASSWORD})
    assert browser.client.cookies.get("netrevive_session") != before
    assert (
        "HttpOnly" in response.headers["set-cookie"] and "SameSite=strict" in response.headers["set-cookie"]
    )


def test_login_rate_limit(admin):
    for _ in range(5):
        assert admin.request("POST", "/api/login", {"password": "wrong"}).status_code == 401
    assert admin.request("POST", "/api/login", {"password": "wrong"}).status_code == 429


def test_settings_persist_and_timezone(admin, app):
    data = {"title": "Recovery console", "hostname": "network-recovery.lan", "timezone": "America/New_York"}
    assert admin.request("PUT", "/api/admin/general", data).status_code == 200
    reopened = Database(app.state.db.path)
    assert all(reopened.settings()[key] == value for key, value in data.items())
    assert admin.get("/api/status").json()["hostname"] == "network-recovery.lan"
    data["timezone"] = "invalid/zone"
    assert admin.request("PUT", "/api/admin/general", data).status_code == 422


@pytest.mark.parametrize(
    "hostname",
    ["javascript:alert(1)", "https://user:password@host.test", "http://host.test/path", "bad hostname"],
)
def test_hostname_validation(admin, hostname):
    assert (
        admin.request(
            "PUT",
            "/api/admin/general",
            {"title": "NetRevive", "hostname": hostname, "timezone": "Europe/London"},
        ).status_code
        == 422
    )


def test_secrets_not_returned(inventory, app):
    for path in ("/", "/api/status", "/api/admin/config", "/api/session"):
        assert "private-test-key" not in inventory.get(path).text
        assert PASSWORD not in inventory.get(path).text
    with app.state.db.connect() as conn:
        text = " ".join(row[0] for row in conn.execute("SELECT value FROM settings"))
        assert "private-test-key" not in text and PASSWORD not in text
        encoded = json.loads(
            conn.execute("SELECT value FROM settings WHERE key='admin_password_hash'").fetchone()[0]
        )
        assert verify_password(PASSWORD, encoded)


def test_validation_does_not_echo_credentials(admin):
    response = admin.request(
        "PUT",
        "/api/admin/unifi",
        {
            "controller_url": "https://key-secret@controller.test",
            "api_key": "api-secret",
            "unexpected": "do-not-echo",
        },
    )
    assert response.status_code == 422
    assert not any(value in response.text for value in ("key-secret", "api-secret", "do-not-echo"))


def test_unifi_sites_and_discovery(inventory):
    response = inventory.request("POST", "/api/admin/unifi/test")
    assert response.json()["sites"] == [{"id": "site-a", "name": "Test site"}]
    targets = inventory.get("/api/admin/config").json()["targets"]
    assert len(targets) == 3
    assert targets[0]["port_number"] == targets[2]["port_number"]
    assert targets[0]["switch_id"] != targets[2]["switch_id"]


def test_groups_crud_order_and_overlap(inventory):
    first = inventory.request("POST", "/api/admin/groups", group([1, 2, 3], display_order=9)).json()["id"]
    second = inventory.request(
        "POST", "/api/admin/groups", group([1, 3], name="Access points", display_order=-1)
    ).json()["id"]
    assert [g["id"] for g in inventory.get("/api/status").json()["groups"]] == [second, first]
    response = inventory.request(
        "PUT", f"/api/admin/groups/{first}", group([1], button_label="Restart Gateway", enabled=False)
    )
    assert response.status_code == 200
    assert len(inventory.get("/api/status").json()["groups"]) == 1
    assert inventory.request("DELETE", f"/api/admin/groups/{first}").status_code == 200
    assert len(inventory.get("/api/admin/config").json()["groups"]) == 1


def test_duplicate_association_rejected(inventory, app):
    assert inventory.request("POST", "/api/admin/groups", group([1, 1])).status_code == 422
    gid = inventory.request("POST", "/api/admin/groups", group()).json()["id"]
    with pytest.raises(sqlite3.IntegrityError), app.state.db.connect(write=True) as conn:
        conn.execute("INSERT INTO group_targets VALUES (?,1)", (gid,))


def test_save_membership_without_extra_confirmation(inventory):
    response = inventory.request("POST", "/api/admin/groups", group())
    assert response.status_code == 201
    gid = response.json()["id"]
    assert inventory.request("PUT", f"/api/admin/groups/{gid}", group([1, 2])).status_code == 200
    saved = inventory.get("/api/admin/config").json()["groups"][0]
    assert saved["target_ids"] == [1, 2]
    # Older browser tabs can still submit the removed field.
    assert (
        inventory.request("PUT", f"/api/admin/groups/{gid}", group([1], confirm_targets=False)).status_code
        == 200
    )


@pytest.mark.parametrize("targets", [[999], []])
def test_invalid_empty_targets(inventory, targets):
    data = group()
    data["target_ids"] = targets
    assert inventory.request("POST", "/api/admin/groups", data).status_code == 422


def test_poe_capability_and_site(inventory, app):
    with app.state.db.connect(write=True) as conn:
        conn.execute("UPDATE targets SET poe_capable=0 WHERE id=1")
    assert inventory.request("POST", "/api/admin/groups", group()).status_code == 422
    with app.state.db.connect(write=True) as conn:
        conn.execute("UPDATE targets SET poe_capable=1,site_id='other' WHERE id=1")
    assert inventory.request("POST", "/api/admin/groups", group()).status_code == 422


def test_operator_crud(admin):
    uid = admin.request("POST", "/api/admin/operators", {"name": "Operator B"}).json()["id"]
    assert admin.request("POST", "/api/admin/operators", {"name": "Operator B"}).status_code == 409
    assert (
        admin.request(
            "PUT", f"/api/admin/operators/{uid}", {"name": "Operator C", "display_order": 8}
        ).status_code
        == 200
    )
    assert admin.request("DELETE", f"/api/admin/operators/{uid}").status_code == 200


def test_target_edits_survive_discovery(inventory):
    assert (
        inventory.request(
            "PUT", "/api/admin/targets/1", {"label": "Gateway power", "enabled": False}
        ).status_code
        == 200
    )
    inventory.request("POST", "/api/admin/unifi/discover")
    target = inventory.get("/api/admin/config").json()["targets"][0]
    assert target["label"] == "Gateway power" and not target["enabled"]


def test_bootstrap_password_requires_auth(tmp_path):
    instance = create_app(
        Bootstrap(database_path=str(tmp_path / "other.db"), admin_password=PASSWORD, background=False)
    )
    with TestClient(instance) as client:
        browser = Browser(client)
        assert browser.request("POST", "/api/setup", {"password": PASSWORD}).status_code == 409
        assert browser.request("POST", "/api/login", {"password": PASSWORD}).status_code == 200


def test_no_remote_assets(browser):
    html = browser.get("/")
    assert html.status_code == 200
    assert 'src="http' not in html.text and 'href="https://' not in html.text
    for path in ("/static/app.js", "/static/app.css", "/static/favicon.svg", "/healthz"):
        assert browser.get(path).status_code == 200
    assert "frame-ancestors 'none'" in html.headers["content-security-policy"]


@pytest.mark.parametrize("saved_key", [False, True])
def test_connection_draft_uses_entered_values_without_saving(admin, app, monkeypatch, saved_key):
    from app.unifi import UniFiClient
    import httpx

    if saved_key:
        assert (
            admin.request(
                "PUT",
                "/api/admin/unifi",
                {
                    "controller_url": "https://controller.test",
                    "api_key": "saved-secret",
                },
            ).status_code
            == 200
        )
    before = admin.get("/api/admin/config").json()
    calls = []

    def factory(settings, api_key):
        calls.append((settings, api_key))
        return UniFiClient(
            settings,
            api_key,
            httpx.MockTransport(
                lambda request: httpx.Response(200, json={"data": [{"id": "draft-site", "name": "Draft"}]})
            ),
        )

    monkeypatch.setattr("app.main.UniFiClient", factory)
    app.state.client_factory = app.state.real_client_factory
    response = admin.request(
        "POST",
        "/api/admin/unifi/test",
        {
            "controller_url": "https://controller.test",
            "api_prefix": "/integration/v1",
            "verify_tls": False,
            "api_key": "" if saved_key else "draft-secret",
        },
    )
    assert response.status_code == 200
    assert response.json()["sites"] == [{"id": "draft-site", "name": "Draft"}]
    assert calls[0][0]["api_prefix"] == "/integration/v1"
    assert calls[0][0]["verify_tls"] is False
    assert calls[0][1] == ("saved-secret" if saved_key else "draft-secret")
    assert admin.get("/api/admin/config").json() == before
    assert "secret" not in response.text


def test_connection_draft_does_not_forward_stored_key_to_new_host(inventory, app):
    app.state.client_factory = lambda **kwargs: pytest.fail("Must reject before contacting controller")
    before = inventory.get("/api/admin/config").json()
    response = inventory.request(
        "POST",
        "/api/admin/unifi/test",
        {
            "controller_url": "https://different.test",
        },
    )
    assert response.status_code == 422
    assert "stored keys are not sent" in response.text
    assert inventory.get("/api/admin/config").json() == before


def test_failed_connection_draft_keeps_working_configuration(inventory, app):
    before = inventory.get("/api/admin/config").json()
    app.state.fake.unavailable = True
    response = inventory.request(
        "POST",
        "/api/admin/unifi/test",
        {
            "controller_url": "https://different.test",
            "api_key": "invalid-draft-key",
        },
    )
    assert response.status_code == 502
    assert "invalid-draft-key" not in response.text
    assert inventory.get("/api/admin/config").json() == before


def test_connection_draft_validates_without_echoing_key(admin):
    response = admin.request(
        "POST",
        "/api/admin/unifi/test",
        {
            "controller_url": "http://controller.test",
            "api_key": "draft-secret",
        },
    )
    assert response.status_code == 422 and "draft-secret" not in response.text


def test_connection_draft_requires_admin(browser):
    response = browser.request(
        "POST",
        "/api/admin/unifi/test",
        {
            "controller_url": "https://controller.test",
            "api_key": "draft-secret",
        },
    )
    assert response.status_code == 401


def test_password_change_rotates_sessions_and_updates_login(admin, app):
    from app.security import new_session

    old_cookie = admin.client.cookies.get("netrevive_session")
    _, other = new_session(app.state.db, admin=True)
    response = admin.request(
        "PUT",
        "/api/admin/password",
        {
            "current_password": PASSWORD,
            "new_password": "replacement-administrator-password",
        },
    )
    assert response.status_code == 200
    assert admin.client.cookies.get("netrevive_session") != old_cookie
    assert "replacement-administrator-password" not in response.text
    assert admin.get("/api/admin/config").status_code == 200
    with app.state.db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM sessions WHERE admin=1").fetchone()[0] == 1
        assert not conn.execute("SELECT 1 FROM sessions WHERE csrf=?", (other["csrf"],)).fetchone()
    assert admin.request("POST", "/api/login", {"password": PASSWORD}).status_code == 401
    assert (
        admin.request("POST", "/api/login", {"password": "replacement-administrator-password"}).status_code
        == 200
    )


def test_password_change_rejects_wrong_current_password(admin):
    assert (
        admin.request(
            "PUT",
            "/api/admin/password",
            {
                "current_password": "incorrect",
                "new_password": "replacement-administrator-password",
            },
        ).status_code
        == 401
    )
    assert admin.request("POST", "/api/login", {"password": PASSWORD}).status_code == 200


def test_password_change_validation_does_not_echo_secret(admin):
    response = admin.request(
        "PUT",
        "/api/admin/password",
        {
            "current_password": PASSWORD,
            "new_password": "secret",
        },
    )
    assert response.status_code == 422 and "secret" not in response.text and PASSWORD not in response.text


def test_password_change_requires_authentication(browser):
    assert (
        browser.request(
            "PUT",
            "/api/admin/password",
            {
                "current_password": PASSWORD,
                "new_password": "replacement-administrator-password",
            },
        ).status_code
        == 401
    )


def test_password_change_respects_environment_control(admin, app):
    app.state.bootstrap.admin_password = PASSWORD
    assert admin.get("/api/admin/config").json()["settings"]["admin_password_from_environment"]
    response = admin.request(
        "PUT",
        "/api/admin/password",
        {
            "current_password": PASSWORD,
            "new_password": "replacement-administrator-password",
        },
    )
    assert response.status_code == 409
    assert admin.request("POST", "/api/login", {"password": PASSWORD}).status_code == 200
