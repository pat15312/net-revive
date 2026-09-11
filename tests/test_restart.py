import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException

from app.database import Database
from app.restart import RestartService, history
from conftest import group


def assert_conflict(service, group_id):
    with pytest.raises(HTTPException) as error:
        service.admit(group_id, "Operator A")
    assert error.value.status_code == 409


async def test_single_target_restart(configured, app):
    service = app.state.restart
    event = service.admit(1, "Operator A")
    await service.execute(event)
    result = history(app.state.db, True)[0]
    assert result["result"] == "successful"
    assert result["targets"][0]["accepted"] == 1 and result["targets"][0]["attempted"] == 1
    assert result["recovery_status"] == "monitoring"
    assert_conflict(service, 1)


@pytest.mark.parametrize(
    "failures,expected", [(set(), "successful"), ({2}, "partial"), ({1, 2, 3}, "unsuccessful")]
)
async def test_multi_target_results(configured, app, failures, expected):
    assert (
        configured.request("PUT", "/api/admin/groups/1", group([1, 2, 3], recovery_mode="none")).status_code
        == 200
    )
    app.state.fake.fail = failures
    event_id = app.state.restart.admit(1, "Operator A")
    await app.state.restart.execute(event_id)
    event = history(app.state.db, True)[0]
    assert sorted(app.state.fake.calls) == [1, 2, 3]
    assert event["result"] == expected
    assert event["recovery_status"] == "not_requested" and event["recovery_duration"] is None
    for target in event["targets"]:
        assert target["result"] == ("unknown" if target["target_id"] in failures else "accepted")


async def test_validation_failure_continues_remaining_targets(configured, app):
    configured.request("PUT", "/api/admin/groups/1", group([1, 2, 3]))
    app.state.fake.invalid = {2}
    event_id = app.state.restart.admit(1, "Operator A")
    await app.state.restart.execute(event_id)
    assert sorted(app.state.fake.calls) == [1, 3]
    event = history(app.state.db, True)[0]
    assert event["result"] == "partial"
    assert event["targets"][1]["attempted"] == 0


async def test_overlapping_and_independent_groups(configured, app):
    configured.request("POST", "/api/admin/groups", group([1, 2], name="Everything"))
    configured.request("POST", "/api/admin/groups", group([3], name="Independent"))
    service = app.state.restart
    event_id = service.admit(1, "Operator A")
    assert_conflict(service, 2)
    other = service.admit(3, "Operator A")
    await asyncio.gather(service.execute(event_id), service.execute(other))
    assert_conflict(service, 2)
    assert len(history(app.state.db)) == 2


def test_concurrent_admission(configured, app):
    def request():
        try:
            return app.state.restart.admit(1, "Operator A")
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _: request(), range(8)))
    assert outcomes.count(409) == 7
    assert len(history(app.state.db)) == 1


def test_concurrent_overlap_admission(configured, app):
    configured.request("POST", "/api/admin/groups", group([1, 3]))

    def request(gid):
        try:
            return app.state.restart.admit(gid, "Operator A")
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(request, [1, 2]))
    assert outcomes.count(409) == 1


def test_allowed_disallowed_operators(configured, app):
    with pytest.raises(HTTPException) as exc:
        app.state.restart.admit(1, "Not configured")
    assert exc.value.status_code == 422
    assert app.state.restart.admit(1, "Operator A")


def test_ordinary_api_cannot_supply_targets(configured):
    for extra in ({"target_ids": [3]}, {"switch_id": "anything"}, {"action": "OFF"}, {"path": "/arbitrary"}):
        response = configured.request("POST", "/api/groups/1/restart", {"operator": "Operator A", **extra})
        assert response.status_code == 422


async def test_persistent_cooldowns(configured, app):
    service = app.state.restart
    event_id = service.admit(1, "Operator A")
    await service.execute(event_id)
    reloaded = RestartService(Database(app.state.db.path), app.state.health, lambda: app.state.fake)
    reloaded.reconcile_interrupted()
    assert_conflict(reloaded, 1)
    assert history(reloaded.db)[0]["result"] == "successful"


def test_crash_reconciliation_never_replays(configured, app):
    configured.request("PUT", "/api/admin/groups/1", group([1, 2]))
    event_id = app.state.restart.admit(1, "Operator A")
    with app.state.db.connect(write=True) as conn:
        conn.execute("UPDATE event_targets SET attempted=1,result='sending' WHERE target_id=1")
        conn.execute("UPDATE targets SET locked_until=0")
    app.state.restart.reconcile_interrupted()
    event = history(app.state.db, True)[0]
    assert event["id"] == event_id and event["result"] == "interrupted"
    assert [t["result"] for t in event["targets"]] == ["unknown", "not_attempted"]
    assert not app.state.fake.calls
    assert_conflict(app.state.restart, 1)


async def test_history_immutable_after_configuration_edits(configured, app):
    event_id = app.state.restart.admit(1, "Operator A")
    await app.state.restart.execute(event_id)
    before = history(app.state.db, True)[0]
    configured.request("PUT", "/api/admin/targets/1", {"label": "Renamed target", "enabled": True})
    configured.request("PUT", "/api/admin/groups/1", group(name="New group name", button_label="New label"))
    configured.request("DELETE", "/api/admin/operators/1")
    configured.request("DELETE", "/api/admin/groups/1")
    after = history(app.state.db, True)[0]
    assert before == after
    assert after["targets"][0]["snapshot"]["label"] == ""


async def test_lockout_survives_deleting_group(configured, app):
    event_id = app.state.restart.admit(1, "Operator A")
    await app.state.restart.execute(event_id)
    configured.request("DELETE", "/api/admin/groups/1")
    replacement = configured.request("POST", "/api/admin/groups", group()).json()["id"]
    assert_conflict(app.state.restart, replacement)


def test_admin_cannot_mutate_targets_during_dispatch(configured, app):
    app.state.restart.admit(1, "Operator A")
    assert configured.request("PUT", "/api/admin/groups/1", group([1, 2])).status_code == 409
    assert configured.request("DELETE", "/api/admin/groups/1").status_code == 409


def test_healthy_state_does_not_block_restart(configured, app):
    from app.database import put_setting

    with app.state.db.connect(write=True) as conn:
        put_setting(
            conn,
            "health",
            {"internet": True, "dns": True, "unifi": True, "state": "healthy", "checked_at": time.time()},
        )
    assert app.state.restart.admit(1, "Operator A")


async def test_group_lockout_independent_of_new_membership(configured, app):
    event_id = app.state.restart.admit(1, "Operator A")
    await app.state.restart.execute(event_id)
    assert configured.request("PUT", "/api/admin/groups/1", group([3])).status_code == 200
    assert_conflict(app.state.restart, 1)


def test_disabled_group_and_target(configured, app):
    configured.request("PUT", "/api/admin/groups/1", group(enabled=False))
    with pytest.raises(HTTPException) as exc:
        app.state.restart.admit(1, "Operator A")
    assert exc.value.status_code == 404
    configured.request("PUT", "/api/admin/groups/1", group())
    configured.request("PUT", "/api/admin/targets/1", {"enabled": False})
    assert_conflict(app.state.restart, 1)
