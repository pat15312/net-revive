"""Bound and validate HTTP before sessions, JSON parsing or database work."""

import asyncio
import ipaddress
import re
import time
from urllib.parse import urlsplit

from starlette.responses import JSONResponse

from .logging import audit

LOCAL_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "127.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "::1/128",
        "fc00::/7",
    )
)
HEADERS = {
    "content-security-policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "permissions-policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "cache-control": "no-store",
}


def host_name(value):
    if not value or not re.fullmatch(r"[a-zA-Z0-9.\-:\[\]]+", value):
        raise ValueError("Invalid Host")
    parsed = urlsplit("http://" + value)
    if not parsed.hostname or (parsed.port is not None and not 1 <= parsed.port <= 65535):
        raise ValueError("Invalid Host")
    if value.endswith(":"):
        raise ValueError("Invalid Host")
    return parsed.hostname.lower().rstrip(".")


class HTTPBoundary:
    def __init__(self, app, allowed_hosts):
        self.app = app
        # No wildcard/suffix rules: custom names must be enumerated by the deployer.
        self.allowed = {host_name(value.strip()) for value in allowed_hosts.split(",") if value.strip()}
        self.active = 0
        self.window = time.monotonic()
        self.count = 0
        self.peers = {}

    def allowed_host(self, value):
        try:
            host = host_name(value)
            if host in self.allowed:
                return True
            address = ipaddress.ip_address(host)
            return any(address in network for network in LOCAL_NETWORKS)
        except ValueError:
            return False

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = False

        async def secured_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower().decode() not in HEADERS]
                message["headers"] = headers + [(k.encode(), v.encode()) for k, v in HEADERS.items()]
            await send(message)

        async def reject(status, message):
            # Fixed reason only: never attacker-supplied hosts, paths, headers or tokens.
            await JSONResponse({"detail": message}, status_code=status)(scope, receive, secured_send)

        headers = scope.get("headers", [])
        if sum(len(k) + len(v) for k, v in headers) > 16384 or len(scope.get("query_string", b"")) > 8192:
            return await reject(431, "Request headers or query too large.")
        values = {}
        for k, v in headers:
            values.setdefault(k.lower(), []).append(v)
        hosts = values.get(b"host", [])
        if len(hosts) != 1 or not self.allowed_host(hosts[0].decode("latin1")):
            return await reject(
                400, "Unrecognized Host. Use a private IP or a configured ALLOWED_HOSTS name."
            )
        for name in (b"content-length", b"origin", b"x-csrf-token"):
            if len(values.get(name, [])) > 1:
                return await reject(400, "Ambiguous request headers.")
        cookies = b";".join(values.get(b"cookie", []))
        if len(re.findall(rb"(?:^|;)\s*netrevive_session\s*=", cookies)) > 1:
            return await reject(400, "Ambiguous session cookie.")
        if b"transfer-encoding" in values and b"content-length" in values:
            return await reject(400, "Ambiguous request framing.")
        now = time.monotonic()
        if now - self.window >= 60:
            self.window, self.count, self.peers = now, 0, {}
        peer = scope.get("client", ("local", 0))[0]
        if peer not in self.peers and len(self.peers) >= 1024:
            return await reject(429, "Too many clients. Please wait.")
        self.count += 1
        self.peers[peer] = self.peers.get(peer, 0) + 1
        if len(self.peers) > 1024 or self.count > 2400 or self.peers[peer] > 600:
            return await reject(429, "Too many requests. Please wait.")
        if self.active >= 32:
            return await reject(503, "Server busy. Please try again.")
        self.active += 1
        try:
            try:
                length = int(values.get(b"content-length", [b"0"])[0])
            except ValueError:
                return await reject(400, "Invalid content length.")
            if length < 0 or length > 65536:
                return await reject(413, "Request body exceeds 64 KiB.")
            if b"content-encoding" in values and values[b"content-encoding"] != [b"identity"]:
                return await reject(415, "Compressed request bodies are not supported.")
            body = bytearray()
            async with asyncio.timeout(10):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    if len(body) + len(chunk) > 65536:
                        return await reject(413, "Request body exceeds 64 KiB.")
                    body.extend(chunk)
                    if not message.get("more_body", False):
                        break
            delivered = False

            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            await self.app(scope, bounded_receive, secured_send)
        except TimeoutError:
            if not started:
                await reject(408, "Request timed out.")
        except Exception:
            audit("http_request_failed")
            if not started:
                await reject(503, "Request could not be completed. Please try again.")
        finally:
            self.active -= 1
