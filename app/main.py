import asyncio
import fcntl
import hmac
import logging
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .admin import router as admin_router
from .config import Bootstrap
from .database import Database, put_setting, setting
from .health import HealthMonitor
from .logging import audit
from .restart import RestartService, availability, group_targets, history
from .schemas import ChangePassword, Password, RestartRequest
from .security import (
    cipher_for,
    digest,
    hash_password,
    new_session,
    rate_limit,
    require_admin,
    verify_password,
)
from .unifi import UniFiClient, UniFiError

ROOT = Path(__file__).parent


def create_app(bootstrap=None):
    bootstrap = bootstrap or Bootstrap()
    db = Database(bootstrap.database_path)
    cipher = cipher_for(bootstrap)
    with db.connect(write=True) as conn:
        if bootstrap.admin_password:
            if len(bootstrap.admin_password) < 12:
                raise RuntimeError("ADMIN_PASSWORD must contain at least 12 characters.")
            if not verify_password(bootstrap.admin_password, setting(conn, "admin_password_hash", "")):
                put_setting(conn, "admin_password_hash", hash_password(bootstrap.admin_password))
                conn.execute("DELETE FROM sessions")

    @asynccontextmanager
    async def lifespan(app):
        # One service process per database. SQLite still serializes admission across request threads.
        lock = open(str(db.path) + ".lock", "a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            lock.close()
            raise RuntimeError("Only one NetRevive process may use this database; run one worker.") from None
        app.state.restart.reconcile_interrupted()
        audit("startup")
        monitor_task = asyncio.create_task(app.state.health.run()) if bootstrap.background else None
        try:
            yield
        finally:
            if monitor_task:
                monitor_task.cancel()
                with suppress(asyncio.CancelledError):
                    await monitor_task
            pending = list(app.state.restart.tasks)
            if pending:
                done, waiting = await asyncio.wait(pending, timeout=25)
                for task in waiting:
                    task.cancel()
                await asyncio.gather(*waiting, return_exceptions=True)
            audit("shutdown")
            lock.close()

    app = FastAPI(title="NetRevive", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db, app.state.bootstrap, app.state.cipher = db, bootstrap, cipher

    def client_factory(settings=None, api_key=None):
        if api_key is None:
            with db.connect() as conn:
                encrypted = setting(conn, "api_key_encrypted", "")
            api_key = bootstrap.unifi_api_key or (
                cipher.decrypt(encrypted.encode()).decode() if encrypted else ""
            )
        return UniFiClient(settings if settings is not None else db.settings(), api_key)

    app.state.client_factory = client_factory
    app.state.health = HealthMonitor(db, lambda: app.state.client_factory())
    app.state.restart = RestartService(db, app.state.health, lambda: app.state.client_factory())
    templates = Jinja2Templates(directory=str(ROOT / "templates"))

    @app.middleware("http")
    async def security_middleware(request, call_next):
        if request.url.path == "/healthz" or request.url.path.startswith("/static/"):
            return await call_next(request)
        token = request.cookies.get("netrevive_session", "")
        with db.connect() as conn:
            row = (
                conn.execute(
                    "SELECT * FROM sessions WHERE token_hash=? AND expires_at>?", (digest(token), time.time())
                ).fetchone()
                if token
                else None
            )
        new_token = None
        if row:
            session = dict(row)
        else:
            new_token, session = new_session(db)
        request.state.session = session
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            supplied = request.headers.get("x-csrf-token", "")
            if not hmac.compare_digest(supplied, session["csrf"]):
                return JSONResponse(
                    {"detail": "Session expired or CSRF token missing. Reload this page."}, status_code=403
                )
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "Cross-origin requests are not allowed."}, status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "Cross-site requests are not allowed."}, status_code=403)
            try:
                rate_limit(db, "write:" + (request.client.host if request.client else "local"), maximum=60)
            except HTTPException as exc:
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        response = await call_next(request)
        if new_token and "set-cookie" not in response.headers:
            response.set_cookie(
                "netrevive_session",
                new_token,
                httponly=True,
                samesite="strict",
                secure=bootstrap.secure_cookie,
                max_age=28800,
            )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # FastAPI's default echoes invalid inputs, which can include passwords or API keys.
        return JSONResponse(
            status_code=422,
            content={"detail": [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]},
        )

    @app.exception_handler(UniFiError)
    async def unifi_error(request, exc):
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    def authenticated_response(request):
        with db.connect(write=True) as conn:
            conn.execute(
                "DELETE FROM sessions WHERE token_hash=?",
                (digest(request.cookies.get("netrevive_session", "")),),
            )
        token, session = new_session(db, admin=True)
        response = JSONResponse({"ok": True, "csrf": session["csrf"]})
        response.set_cookie(
            "netrevive_session",
            token,
            httponly=True,
            samesite="strict",
            secure=bootstrap.secure_cookie,
            max_age=28800,
        )
        return response

    @app.post("/api/setup")
    def setup(body: Password, request: Request):
        rate_limit(db, "setup", maximum=5, window=300)
        if len(body.password) < 12:
            raise HTTPException(422, "Choose an administrator password of at least 12 characters.")
        with db.connect(write=True) as conn:
            if setting(conn, "admin_password_hash"):
                raise HTTPException(
                    409, "An administrator password is already set. Sign in to continue setup."
                )
            put_setting(conn, "admin_password_hash", hash_password(body.password))
        audit("admin_initialized")
        return authenticated_response(request)

    @app.post("/api/login")
    def login(body: Password, request: Request):
        rate_limit(db, "login:" + (request.client.host if request.client else "local"), maximum=5, window=300)
        rate_limit(db, "login:global", maximum=30, window=300)
        with db.connect() as conn:
            stored = setting(conn, "admin_password_hash", "")
        if not verify_password(body.password, stored):
            raise HTTPException(401, "The administrator password is incorrect.")
        audit("admin_signed_in")
        return authenticated_response(request)

    @app.put("/api/admin/password")
    def change_password(body: ChangePassword, request: Request):
        require_admin(request)
        if bootstrap.admin_password:
            raise HTTPException(
                409,
                "The administrator password is managed through ADMIN_PASSWORD in the container environment.",
            )
        rate_limit(db, "password-change", maximum=5, window=300)
        with db.connect(write=True) as conn:
            if not verify_password(body.current_password, setting(conn, "admin_password_hash", "")):
                raise HTTPException(401, "The current password is incorrect.")
            put_setting(conn, "admin_password_hash", hash_password(body.new_password))
            conn.execute("DELETE FROM sessions WHERE admin=1")
        audit("admin_password_changed")
        return authenticated_response(request)

    @app.post("/api/logout")
    def logout(request: Request):
        with db.connect(write=True) as conn:
            conn.execute(
                "DELETE FROM sessions WHERE token_hash=?",
                (digest(request.cookies.get("netrevive_session", "")),),
            )
        response = JSONResponse({"ok": True})
        response.delete_cookie("netrevive_session")
        return response

    @app.get("/api/session")
    def session_info(request: Request):
        with db.connect() as conn:
            return {
                "admin": bool(request.state.session["admin"]),
                "csrf": request.state.session["csrf"],
                "setup_complete": setting(conn, "setup_complete", False),
                "has_password": bool(setting(conn, "admin_password_hash")),
            }

    @app.get("/api/status")
    def status():
        now = time.time()
        settings = db.settings()
        with db.connect() as conn:
            groups = []
            for row in conn.execute("SELECT * FROM restart_groups WHERE enabled=1 ORDER BY display_order,id"):
                group = dict(row)
                allowed, until, reason = availability(group, group_targets(conn, group["id"]), now)
                groups.append(
                    {
                        key: group[key]
                        for key in ("id", "name", "button_label", "description", "recovery_mode")
                    }
                    | {"available": allowed, "locked_until": until, "unavailable_reason": reason}
                )
            users = [dict(r) for r in conn.execute("SELECT * FROM operators ORDER BY display_order,id")]
        return {
            "server_time": now,
            "health": app.state.health.current(),
            "groups": groups,
            "operators": users,
            "title": settings["title"],
            "hostname": settings["hostname"],
            "timezone": settings["timezone"],
            "events": history(db, limit=8),
        }

    @app.post("/api/groups/{group_id}/restart", status_code=202)
    async def restart(group_id: int, body: RestartRequest, request: Request):
        rate_limit(db, "restart:" + (request.client.host if request.client else "local"), maximum=10)
        event_id = app.state.restart.admit(group_id, body.operator)
        app.state.restart.launch(event_id)
        return {
            "event_id": event_id,
            "message": "Restart requested. You can leave this page open to follow progress.",
        }

    @app.get("/healthz")
    def healthz():
        with db.connect() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok"}

    @app.get("/")
    @app.get("/admin")
    @app.get("/setup")
    def page(request: Request):
        settings = db.settings()
        canonical = settings["hostname"]
        if "://" not in canonical:
            canonical = "http://" + canonical
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "csrf": request.state.session["csrf"],
                "title": settings["title"],
                "hostname": settings["hostname"],
                "canonical": canonical,
            },
        )

    app.include_router(admin_router)
    app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")
    return app


logging.basicConfig(level=logging.INFO, format="%(message)s")
# Suppress third-party request logging, including configured controller URLs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
