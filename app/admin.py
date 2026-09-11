import sqlite3
from typing import Literal
from zoneinfo import available_timezones

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request

from .database import put_setting, setting
from .logging import audit
from .restart import group_targets, history
from .schemas import General, Group, Monitoring, MoveItem, Operator, TargetEdit, UniFiSettings
from .security import require_admin
from .unifi import UniFiError

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])
TIMEZONES = sorted(available_timezones() - {"localtime"})


def no_dispatch(conn):
    if conn.execute("SELECT 1 FROM events WHERE result='dispatching'").fetchone():
        raise HTTPException(
            409, "Wait for the current restart requests to finish before changing equipment settings."
        )


@router.get("/config")
def config(request: Request):
    app = request.app.state
    with app.db.connect() as conn:
        settings = app.db.settings()
        settings["api_key_configured"] = bool(
            app.bootstrap.unifi_api_key or setting(conn, "api_key_encrypted")
        )
        settings["api_key_from_environment"] = bool(app.bootstrap.unifi_api_key)
        settings["admin_password_from_environment"] = bool(app.bootstrap.admin_password)
        groups = [
            {**dict(row), "target_ids": [t["id"] for t in group_targets(conn, row["id"])]}
            for row in conn.execute("SELECT * FROM restart_groups ORDER BY display_order,id")
        ]
        return {
            "settings": settings,
            "timezones": TIMEZONES,
            "operators": [dict(r) for r in conn.execute("SELECT * FROM operators ORDER BY display_order,id")],
            "groups": groups,
            "targets": [
                dict(r) for r in conn.execute("SELECT * FROM targets ORDER BY switch_name,port_number,id")
            ],
            "setup_complete": setting(conn, "setup_complete", False),
        }


@router.put("/general")
def save_general(body: General, request: Request):
    with request.app.state.db.connect(write=True) as conn:
        for key, value in body.model_dump().items():
            put_setting(conn, key, value)
    audit("general_settings_changed")
    return {"ok": True}


@router.put("/monitoring")
def save_monitoring(body: Monitoring, request: Request):
    with request.app.state.db.connect(write=True) as conn:
        for key, value in body.model_dump().items():
            put_setting(conn, key, value)
    audit("monitoring_settings_changed")
    return {"ok": True}


@router.put("/unifi")
def save_unifi(body: UniFiSettings, request: Request):
    app = request.app.state
    with app.db.connect(write=True) as conn:
        no_dispatch(conn)
        changing_controller = setting(conn, "controller_url") not in ("", body.controller_url)
        if changing_controller and not body.api_key and not app.bootstrap.unifi_api_key:
            raise HTTPException(
                422, "Enter an API key when changing controller; stored keys are not sent to a new host."
            )
        if body.api_key and app.bootstrap.unifi_api_key:
            raise HTTPException(
                422, "UNIFI_API_KEY is set in the environment. Remove it before managing the key here."
            )
        if changing_controller or setting(conn, "site_id") != body.site_id:
            conn.execute("UPDATE targets SET available=0")
        for key, value in body.model_dump(exclude={"api_key"}).items():
            put_setting(conn, key, value)
        if body.api_key:
            put_setting(conn, "api_key_encrypted", app.cipher.encrypt(body.api_key.encode()).decode())
    audit("unifi_settings_changed")
    return {"ok": True}


@router.post("/unifi/test")
async def test_unifi(request: Request, body: UniFiSettings | None = None):
    app = request.app.state
    try:
        if body is None:
            client = app.client_factory()
        else:
            # Read the saved origin and key in one snapshot so a concurrent save
            # cannot cause a different controller's key to be sent by this test.
            with app.db.connect() as conn:
                conn.execute("BEGIN")
                saved_url = setting(conn, "controller_url", "")
                encrypted = setting(conn, "api_key_encrypted", "")
            if saved_url not in ("", body.controller_url) and not body.api_key:
                raise HTTPException(
                    422,
                    "Enter an API key when testing a different controller; stored keys are not sent to a new host.",
                )
            if body.api_key and app.bootstrap.unifi_api_key:
                raise HTTPException(
                    422, "UNIFI_API_KEY is set in the environment. Remove it before managing the key here."
                )
            api_key = body.api_key or app.bootstrap.unifi_api_key
            if not api_key and encrypted:
                api_key = app.cipher.decrypt(encrypted.encode()).decode()
            client = app.client_factory(settings=body.model_dump(exclude={"api_key"}), api_key=api_key)
        sites = await client.sites()
        return {
            "ok": True,
            "sites": [{"id": str(s["id"]), "name": s.get("name", "UniFi site")} for s in sites],
        }
    except (UniFiError, InvalidToken) as exc:
        raise HTTPException(
            502, str(exc) if isinstance(exc, UniFiError) else "The stored API key cannot be decrypted."
        ) from None


@router.post("/unifi/discover")
async def discover(request: Request):
    app = request.app.state
    settings = app.db.settings()
    try:
        inventory = await app.client_factory().discover(settings["site_id"])
    except UniFiError as exc:
        raise HTTPException(502, str(exc)) from None
    with app.db.connect(write=True) as conn:
        no_dispatch(conn)
        if settings != app.db.settings():
            raise HTTPException(409, "UniFi configuration changed during discovery. Please try again.")
        conn.execute("UPDATE targets SET available=0")
        for target in inventory:
            conn.execute(
                """INSERT INTO targets(site_id,switch_id,switch_name,port_id,port_number,port_name,poe_capable,available)
                VALUES (:site_id,:switch_id,:switch_name,:port_id,:port_number,:port_name,:poe_capable,:available)
                ON CONFLICT(site_id,switch_id,port_id) DO UPDATE SET switch_name=excluded.switch_name,
                port_name=excluded.port_name,poe_capable=excluded.poe_capable,available=excluded.available""",
                target,
            )
    audit("unifi_inventory_refreshed", target_count=len(inventory))
    return {"ok": True, "target_count": len(inventory)}


@router.put("/targets/{target_id}")
def edit_target(target_id: int, body: TargetEdit, request: Request):
    with request.app.state.db.connect(write=True) as conn:
        no_dispatch(conn)
        if not conn.execute("SELECT 1 FROM targets WHERE id=?", (target_id,)).fetchone():
            raise HTTPException(404, "Target not found.")
        conn.execute("UPDATE targets SET label=?,enabled=? WHERE id=?", (body.label, body.enabled, target_id))
    audit("target_changed", target_id=target_id)
    return {"ok": True}


def ordered_ids(conn, table):
    # Table names are supplied only by the fixed internal mapping/call sites.
    return [row[0] for row in conn.execute(f"SELECT id FROM {table} ORDER BY display_order,id")]


def save_order(conn, table, ids):
    conn.executemany(f"UPDATE {table} SET display_order=? WHERE id=?", enumerate(ids))


def append_order(conn, table):
    ids = ordered_ids(conn, table)
    save_order(conn, table, ids)
    return len(ids)


@router.post("/order/{collection}/{item_id}")
def move_item(collection: Literal["users", "groups"], item_id: int, body: MoveItem, request: Request):
    table = {"users": "operators", "groups": "restart_groups"}[collection]
    with request.app.state.db.connect(write=True) as conn:
        ids = ordered_ids(conn, table)
        if item_id not in ids:
            raise HTTPException(404, "Item no longer exists. Refresh the list.")
        current = ids.index(item_id)
        destination = current + (-1 if body.direction == "up" else 1)
        if 0 <= destination < len(ids):
            ids[current], ids[destination] = ids[destination], ids[current]
            save_order(conn, table, ids)
    audit("display_order_changed", collection=collection, item_id=item_id)
    return {"ok": True}


@router.post("/operators", status_code=201)
def add_operator(body: Operator, request: Request):
    try:
        with request.app.state.db.connect(write=True) as conn:
            row = conn.execute(
                "INSERT INTO operators(name,display_order) VALUES (?,?)",
                (
                    body.name,
                    body.display_order
                    if "display_order" in body.model_fields_set
                    else append_order(conn, "operators"),
                ),
            )
            user_id = row.lastrowid
    except sqlite3.IntegrityError:
        raise HTTPException(409, "That user already exists.") from None
    audit("operator_added", operator_id=user_id)
    return {"id": user_id}


@router.put("/operators/{operator_id}")
def edit_operator(operator_id: int, body: Operator, request: Request):
    try:
        with request.app.state.db.connect(write=True) as conn:
            cursor = conn.execute(
                "UPDATE operators SET name=?,display_order=COALESCE(?,display_order) WHERE id=?",
                (
                    body.name,
                    body.display_order if "display_order" in body.model_fields_set else None,
                    operator_id,
                ),
            )
            if not cursor.rowcount:
                raise HTTPException(404, "User not found.")
    except sqlite3.IntegrityError:
        raise HTTPException(409, "That user already exists.") from None
    audit("operator_changed", operator_id=operator_id)
    return {"ok": True}


@router.delete("/operators/{operator_id}")
def delete_operator(operator_id: int, request: Request):
    with request.app.state.db.connect(write=True) as conn:
        conn.execute("DELETE FROM operators WHERE id=?", (operator_id,))
    audit("operator_removed", operator_id=operator_id)
    return {"ok": True}


def write_group(db, body, group_id=None):
    with db.connect(write=True) as conn:
        no_dispatch(conn)
        old = (
            conn.execute("SELECT * FROM restart_groups WHERE id=?", (group_id,)).fetchone()
            if group_id
            else None
        )
        if group_id and not old:
            raise HTTPException(404, "Restart group not found.")
        previous = {t["id"] for t in group_targets(conn, group_id)} if group_id else set()
        for target_id in body.target_ids:
            target = conn.execute("SELECT * FROM targets WHERE id=?", (target_id,)).fetchone()
            if not target or not target["poe_capable"]:
                raise HTTPException(422, "Every target must be a discovered PoE-capable port.")
            if target["site_id"] != setting(conn, "site_id"):
                raise HTTPException(422, "Every target must belong to the configured site.")
            if body.enabled and (not target["enabled"] or not target["available"]):
                raise HTTPException(
                    422, "Enabled groups require enabled, available targets. Refresh UniFi discovery."
                )
        values = (
            body.name,
            body.button_label,
            body.description,
            body.enabled,
            body.display_order
            if "display_order" in body.model_fields_set
            else (old["display_order"] if old else append_order(conn, "restart_groups")),
            body.lockout_seconds,
            body.recovery_mode,
        )
        if old:
            conn.execute(
                """UPDATE restart_groups SET name=?,button_label=?,description=?,enabled=?,
                display_order=?,lockout_seconds=?,recovery_mode=? WHERE id=?""",
                (*values, group_id),
            )
            conn.execute("DELETE FROM group_targets WHERE group_id=?", (group_id,))
        else:
            group_id = conn.execute(
                """INSERT INTO restart_groups(name,button_label,description,enabled,
                display_order,lockout_seconds,recovery_mode) VALUES (?,?,?,?,?,?,?)""",
                values,
            ).lastrowid
        conn.executemany(
            "INSERT INTO group_targets VALUES (?,?)", [(group_id, tid) for tid in body.target_ids]
        )
    audit("restart_group_changed", group_id=group_id, membership_changed=previous != set(body.target_ids))
    return {"id": group_id}


@router.post("/groups", status_code=201)
def create_group(body: Group, request: Request):
    return write_group(request.app.state.db, body)


@router.put("/groups/{group_id}")
def edit_group(group_id: int, body: Group, request: Request):
    return write_group(request.app.state.db, body, group_id)


@router.delete("/groups/{group_id}")
def delete_group(group_id: int, request: Request):
    with request.app.state.db.connect(write=True) as conn:
        no_dispatch(conn)
        conn.execute("DELETE FROM restart_groups WHERE id=?", (group_id,))
    audit("restart_group_removed", group_id=group_id)
    return {"ok": True}


@router.post("/setup/finish")
async def finish_setup(request: Request):
    app = request.app.state
    settings = app.db.settings()
    try:
        discovered = await app.client_factory().discover(settings["site_id"])
    except UniFiError as exc:
        raise HTTPException(422, str(exc)) from None
    valid = {(t["site_id"], t["switch_id"], t["port_id"]) for t in discovered if t["available"]}
    with app.db.connect(write=True) as conn:
        if settings != app.db.settings():
            raise HTTPException(409, "Configuration changed. Please review setup again.")
        groups = conn.execute("SELECT id FROM restart_groups WHERE enabled=1").fetchall()
        if not groups or not conn.execute("SELECT 1 FROM operators").fetchone():
            raise HTTPException(422, "Add at least one user and one enabled restart group.")
        for group in groups:
            targets = group_targets(conn, group["id"])
            if not targets or any(
                (t["site_id"], t["switch_id"], t["port_id"]) not in valid or not t["enabled"] for t in targets
            ):
                raise HTTPException(422, "Every enabled group's targets must be available in UniFi.")
        put_setting(conn, "setup_complete", True)
    audit("setup_completed")
    return {"ok": True}


@router.get("/history")
def detailed_history(request: Request, offset: int = 0):
    if offset < 0:
        raise HTTPException(422, "Invalid history offset.")
    return {"events": history(request.app.state.db, detailed=True, limit=50, offset=offset)}
