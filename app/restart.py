"""Durable admission, bounded concurrent dispatch and immutable audit snapshots."""

import asyncio
import json
import time

from fastapi import HTTPException

from .database import setting
from .logging import audit
from .unifi import UniFiError


def group_targets(conn, group_id):
    return [
        dict(row)
        for row in conn.execute(
            """SELECT t.* FROM targets t JOIN group_targets gt
        ON t.id=gt.target_id WHERE gt.group_id=? ORDER BY t.switch_name,t.port_number,t.id""",
            (group_id,),
        )
    ]


def availability(group, targets, now=None):
    now = now or time.time()
    until = max([group["locked_until"]] + [target["locked_until"] for target in targets])
    if group["active_event_id"] or any(t["active_event_id"] for t in targets):
        return False, until, "A restart involving this equipment is in progress."
    if until > now:
        return False, until, "This group or some of its equipment was restarted recently."
    if not targets or any(not t["enabled"] or not t["poe_capable"] for t in targets):
        return False, until, "An administrator needs to check this group's equipment settings."
    return bool(group["enabled"]), until, ""


class RestartService:
    def __init__(self, db, health, client_factory):
        self.db, self.health, self.client_factory = db, health, client_factory
        self.tasks = set()
        self.slots = asyncio.Semaphore(4)

    def admit(self, group_id, operator):
        now = time.time()
        health = self.health.current()
        with self.db.connect(write=True) as conn:
            if not setting(conn, "setup_complete", False):
                raise HTTPException(409, "An administrator must complete setup first.")
            if not conn.execute("SELECT 1 FROM operators WHERE name=?", (operator,)).fetchone():
                raise HTTPException(422, "Select a configured user.")
            row = conn.execute("SELECT * FROM restart_groups WHERE id=?", (group_id,)).fetchone()
            if not row or not row["enabled"]:
                raise HTTPException(404, "This restart group is not available.")
            group = dict(row)
            targets = group_targets(conn, group_id)
            allowed, until, reason = availability(group, targets, now)
            if not allowed:
                raise HTTPException(409, {"message": reason, "locked_until": until})
            # Availability from health is advisory: fresh validation runs before every power cycle.
            if any(t["site_id"] != setting(conn, "site_id") for t in targets):
                raise HTTPException(409, "This group belongs to a different configured UniFi site.")
            duration = group["lockout_seconds"] or setting(conn, "lockout_seconds")
            cursor = conn.execute(
                """INSERT INTO events(created_at,operator,group_id,group_name,
                button_label,group_snapshot,health_before,recovery_mode,recovery_status,recovery_deadline,
                required_successes,lockout_seconds,dns_failed) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    now,
                    operator,
                    group_id,
                    group["name"],
                    group["button_label"],
                    json.dumps(group),
                    json.dumps(health),
                    group["recovery_mode"],
                    "pending" if group["recovery_mode"] == "network" else "not_requested",
                    now + setting(conn, "recovery_timeout"),
                    setting(conn, "recovery_successes"),
                    duration,
                    health.get("dns") is False,
                ),
            )
            event_id = cursor.lastrowid
            conn.execute(
                "UPDATE restart_groups SET locked_until=?,active_event_id=? WHERE id=?",
                (now + duration, event_id, group_id),
            )
            for target in targets:
                conn.execute(
                    "INSERT INTO event_targets(event_id,target_id,snapshot) VALUES (?,?,?)",
                    (event_id, target["id"], json.dumps(target)),
                )
                conn.execute(
                    "UPDATE targets SET locked_until=?,active_event_id=? WHERE id=?",
                    (now + duration, event_id, target["id"]),
                )
        audit("restart_admitted", event_id=event_id, group_id=group_id, operator=operator)
        return event_id

    def launch(self, event_id):
        task = asyncio.create_task(self.execute(event_id))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def execute(self, event_id):
        try:
            await self._execute(event_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            audit("restart_worker_error", event_id=event_id)
            self.reconcile_interrupted(event_id)

    async def _execute(self, event_id):
        with self.db.connect() as conn:
            rows = [
                dict(row) for row in conn.execute("SELECT * FROM event_targets WHERE event_id=?", (event_id,))
            ]
        client = self.client_factory()

        async def validate(row):
            try:
                async with self.slots:
                    await client.validate(json.loads(row["snapshot"]))
                return None
            except UniFiError as exc:
                return str(exc)
            except Exception:
                return "The configured target could not be validated."

        # Validate the entire group before any power cycle can disconnect the controller.
        errors = await asyncio.gather(*(validate(row) for row in rows))

        async def dispatch(row, validation_error):
            attempted, accepted, result, error = False, False, "failed", validation_error
            if not error:
                async with self.slots:
                    attempted = True
                    with self.db.connect(write=True) as conn:
                        conn.execute(
                            "UPDATE event_targets SET attempted=1,timestamp=?,result='sending' WHERE id=?",
                            (time.time(), row["id"]),
                        )
                    try:
                        await client.power_cycle(json.loads(row["snapshot"]))
                        accepted, result = True, "accepted"
                    except UniFiError as exc:
                        error = str(exc)
                        if exc.uncertain:
                            accepted, result = None, "unknown"
                    except Exception:
                        accepted, result, error = (
                            None,
                            "unknown",
                            "Acceptance could not be determined. No retry was sent.",
                        )
            with self.db.connect(write=True) as conn:
                conn.execute(
                    """UPDATE event_targets SET attempted=?,accepted=?,result=?,error=?,timestamp=?
                    WHERE id=?""",
                    (attempted, accepted, result, error, time.time(), row["id"]),
                )
            audit(
                "target_result",
                event_id=event_id,
                target_id=row["target_id"],
                attempted=attempted,
                result=result,
            )

        await asyncio.gather(*(dispatch(row, error) for row, error in zip(rows, errors)))
        now = time.time()
        with self.db.connect(write=True) as conn:
            event = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
            results = conn.execute(
                "SELECT accepted FROM event_targets WHERE event_id=?", (event_id,)
            ).fetchall()
            accepted = sum(row[0] == 1 for row in results)
            result = "successful" if accepted == len(results) else "partial" if accepted else "unsuccessful"
            recovery = (
                "monitoring"
                if accepted and event["recovery_mode"] == "network"
                else ("not_requested" if event["recovery_mode"] == "none" else "not_started")
            )
            conn.execute(
                "UPDATE events SET result=?,recovery_status=?,completed_at=? WHERE id=?",
                (result, recovery, now, event_id),
            )
            # Conservatively retain cooldown for failures/unknown acceptance too. Start at final dispatch.
            until = now + event["lockout_seconds"]
            conn.execute(
                "UPDATE targets SET active_event_id=NULL,locked_until=MAX(locked_until,?) WHERE active_event_id=?",
                (until, event_id),
            )
            conn.execute(
                "UPDATE restart_groups SET active_event_id=NULL,locked_until=MAX(locked_until,?) WHERE active_event_id=?",
                (until, event_id),
            )
        audit("restart_result", event_id=event_id, result=result)

    def reconcile_interrupted(self, event_id=None):
        """Never replay a POST after a crash. Retain known results and reserve a fresh cooldown."""
        now = time.time()
        with self.db.connect(write=True) as conn:
            for event in conn.execute(
                "SELECT * FROM events WHERE result='dispatching' AND (? IS NULL OR id=?)",
                (event_id, event_id),
            ).fetchall():
                conn.execute(
                    """UPDATE event_targets SET result=CASE WHEN attempted=1 THEN 'unknown' ELSE 'not_attempted' END,
                    error='Application stopped during dispatch. No automatic retry was sent.'
                    WHERE event_id=? AND result IN ('pending','sending')""",
                    (event["id"],),
                )
                conn.execute(
                    """UPDATE events SET result='interrupted',completed_at=?,
                    recovery_status=CASE WHEN recovery_mode='none' THEN 'not_requested' ELSE 'not_started' END
                    WHERE id=?""",
                    (now, event["id"]),
                )
                for table in ("targets", "restart_groups"):
                    conn.execute(
                        f"UPDATE {table} SET active_event_id=NULL,locked_until=MAX(locked_until,?) WHERE active_event_id=?",
                        (now + event["lockout_seconds"], event["id"]),
                    )
                audit("restart_interrupted", event_id=event["id"])
            if event_id is None:
                conn.execute(
                    "UPDATE events SET recovery_status='timed_out' WHERE recovery_status='monitoring' AND recovery_deadline<?",
                    (now,),
                )
                # Consecutive samples must not bridge a period when the application was offline.
                conn.execute("UPDATE events SET consecutive_successes=0 WHERE recovery_status='monitoring'")


def history(db, detailed=False, limit=20, offset=0):
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM events ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?", (limit, offset)
        )
        events = []
        for row in rows:
            event = dict(row)
            for key in ("group_snapshot", "health_before"):
                event[key] = json.loads(event[key])
            results = [
                dict(t) for t in conn.execute("SELECT * FROM event_targets WHERE event_id=?", (row["id"],))
            ]
            event["accepted_count"] = sum(t["accepted"] == 1 for t in results)
            event["target_count"] = len(results)
            if detailed:
                event["targets"] = [{**t, "snapshot": json.loads(t["snapshot"])} for t in results]
            else:
                event = {
                    key: event[key]
                    for key in (
                        "id",
                        "created_at",
                        "operator",
                        "group_name",
                        "button_label",
                        "result",
                        "recovery_mode",
                        "recovery_status",
                        "recovered_at",
                        "recovery_duration",
                        "accepted_count",
                        "target_count",
                        "saw_unhealthy",
                        "dns_recovered_at",
                    )
                }
            events.append(event)
        return events
