import time

import pytest

from app.health import classify
from app.restart import history
from conftest import group


@pytest.mark.parametrize(
    "internet,dns,unifi,expected",
    [
        (True, True, True, "healthy"),
        (True, False, True, "dns_problem"),
        (False, False, True, "internet_problem"),
        (True, True, False, "recovery_problem"),
        (None, None, None, "checking"),
    ],
)
def test_health_classification(internet, dns, unifi, expected):
    assert classify(internet, dns, unifi) == expected


async def test_checks_are_mockable_and_independent(app, monkeypatch):
    async def tcp(target):
        return target["ip"] == "1.1.1.1"

    async def dns(names):
        return False

    monkeypatch.setattr("app.health.tcp_check", tcp)
    monkeypatch.setattr("app.health.dns_check", dns)
    sample = await app.state.health.check_once()
    assert sample["internet"] is True and sample["dns"] is False
    assert sample["state"] == "dns_problem"
    app.state.fake.unavailable = True
    assert (await app.state.health.check_once())["unifi"] is False


async def test_disappeared_target_exposed_in_admin(configured, app):
    app.state.fake.inventory = app.state.fake.inventory[1:]
    assert await app.state.health.unifi_check(app.state.db.settings()) is False
    assert not configured.get("/api/admin/config").json()["targets"][0]["available"]


async def test_stable_recovery_requires_consecutive_distinct_checks(configured, app):
    event_id = app.state.restart.admit(1, "Operator A")
    await app.state.restart.execute(event_id)
    now = time.time()
    sample = {"internet": True, "dns": True, "unifi": True, "checked_at": now + 15}
    app.state.health.process_recovery(sample)
    app.state.health.process_recovery(sample)
    assert history(app.state.db, True)[0]["consecutive_successes"] == 1
    app.state.health.process_recovery({**sample, "dns": False, "checked_at": now + 30})
    assert history(app.state.db, True)[0]["consecutive_successes"] == 0
    for step in (45, 60):
        app.state.health.process_recovery({**sample, "checked_at": now + step})
        assert history(app.state.db)[0]["recovery_status"] == "monitoring"
    app.state.health.process_recovery({**sample, "checked_at": now + 75})
    event = history(app.state.db, True)[0]
    assert event["recovery_status"] == "recovered" and event["recovery_duration"] >= 75
    assert event["dns_recovered_at"] == now + 45


async def test_recovery_timeout_preserves_cooldown(configured, app):
    event_id = app.state.restart.admit(1, "Operator A")
    await app.state.restart.execute(event_id)
    with app.state.db.connect() as conn:
        until = conn.execute("SELECT locked_until FROM targets WHERE id=1").fetchone()[0]
    app.state.health.process_recovery({"internet": True, "dns": True, "checked_at": time.time() + 1000})
    assert history(app.state.db)[0]["recovery_status"] == "timed_out"
    with app.state.db.connect() as conn:
        assert conn.execute("SELECT locked_until FROM targets WHERE id=1").fetchone()[0] == until


async def test_none_mode_never_reports_recovery(configured, app):
    configured.request("PUT", "/api/admin/groups/1", group(recovery_mode="none"))
    event_id = app.state.restart.admit(1, "Operator A")
    await app.state.restart.execute(event_id)
    for step in (15, 30, 45):
        app.state.health.process_recovery({"internet": True, "dns": True, "checked_at": time.time() + step})
    event = history(app.state.db)[0]
    assert event["recovery_status"] == "not_requested" and event["recovery_duration"] is None


async def test_recovery_survives_restart_without_stale_success_count(configured, app):
    event_id = app.state.restart.admit(1, "Operator A")
    await app.state.restart.execute(event_id)
    app.state.health.process_recovery({"internet": True, "dns": True, "checked_at": time.time() + 10})
    app.state.restart.reconcile_interrupted()
    event = history(app.state.db, True)[0]
    assert event["recovery_status"] == "monitoring" and event["consecutive_successes"] == 0


def test_invalid_monitoring_settings(admin):
    from app.config import DEFAULTS

    keys = [
        "lockout_seconds",
        "health_interval",
        "recovery_timeout",
        "recovery_successes",
        "dns_names",
        "internet_targets",
        "internet_threshold",
    ]
    data = {key: DEFAULTS[key] for key in keys}
    assert admin.request("PUT", "/api/admin/monitoring", data).status_code == 200
    assert admin.request("PUT", "/api/admin/monitoring", {**data, "internet_threshold": 2}).status_code == 422
    assert (
        admin.request(
            "PUT",
            "/api/admin/monitoring",
            {**data, "internet_targets": [{"ip": "hostname.test", "port": 443}] * 2},
        ).status_code
        == 422
    )


def test_timezone_daylight_saving():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    zone = ZoneInfo("Europe/London")
    assert datetime(2026, 1, 1, tzinfo=zone).utcoffset().total_seconds() == 0
    assert datetime(2026, 7, 1, tzinfo=zone).utcoffset().total_seconds() == 3600
