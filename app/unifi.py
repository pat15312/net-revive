"""Official local Network integration v1 API. No legacy API, cloud proxy or automatic POST retries."""

import asyncio
import ssl
import json
import re

import httpx


class UniFiError(Exception):
    def __init__(self, message, uncertain=False):
        super().__init__(message)
        self.uncertain = uncertain


def display_text(value):
    if not isinstance(value, str) or len(value) > 200:
        raise UniFiError("UniFi returned an invalid display name.")
    return value


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9-]{1,100}", value):
        raise UniFiError("UniFi returned an invalid equipment identifier.")
    return value


def port_identity(target):
    idx = target.get("port_number")
    if type(idx) is not int or not 1 <= idx <= 1024 or target.get("port_id") != str(idx):
        raise UniFiError("The configured port identity is inconsistent. Rediscover equipment.")
    return idx


class UniFiClient:
    def __init__(self, settings, api_key, transport=None, ca_file="", slots=None):
        self.settings = settings
        self.api_key = api_key
        self.transport = transport
        self.slots = slots if slots is not None else asyncio.Semaphore(4)
        self.ca_file = ca_file

    async def request(self, method, path, **kwargs):
        if not self.settings["controller_url"] or not self.api_key:
            raise UniFiError("Configure a local controller and API key in Admin.")
        url = self.settings["controller_url"] + self.settings["api_prefix"] + path
        try:
            async with (
                asyncio.timeout(12),
                self.slots,
                httpx.AsyncClient(
                    verify=ssl.create_default_context(cafile=self.ca_file or None)
                    if self.settings["verify_tls"]
                    else False,
                    timeout=httpx.Timeout(8, connect=3),
                    transport=self.transport,
                    trust_env=False,
                    follow_redirects=False,
                ) as client,
            ):
                async with client.stream(
                    method, url, headers={"X-API-Key": self.api_key, "Accept-Encoding": "identity"}, **kwargs
                ) as response:
                    if response.status_code in (401, 403):
                        raise UniFiError("UniFi denied access. Check the API key and its permissions.")
                    if not 200 <= response.status_code < 300:
                        raise UniFiError(
                            f"UniFi returned HTTP {response.status_code}.",
                            uncertain=method == "POST" and response.status_code >= 500,
                        )
                    if method == "POST":
                        return None
                    # No decompression of hostile compressed payloads; bound before JSON parsing.
                    if response.headers.get("content-encoding", "identity") != "identity":
                        raise UniFiError("UniFi returned unsupported response compression.")
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(content) + len(chunk) > 2_000_000:
                            raise UniFiError("UniFi response exceeds the supported size limit.")
                        content.extend(chunk)
                    return json.loads(content)
        except (httpx.HTTPError, ValueError, TimeoutError, RecursionError, OSError) as exc:
            cause, seen = exc, set()
            while cause is not None and id(cause) not in seen:
                seen.add(id(cause))
                if isinstance(cause, ssl.SSLCertVerificationError):
                    raise UniFiError(
                        "The controller's TLS certificate could not be verified. It may be self-signed, "
                        "expired, or not valid for the Controller URL. Use a matching address and a "
                        "certificate trusted by NetRevive, or explicitly disable certificate verification "
                        "if you accept the risk of controller impersonation.",
                        uncertain=method == "POST",
                    ) from None
                cause = cause.__cause__ or cause.__context__
            raise UniFiError(
                "UniFi did not return a valid response. Check connectivity and TLS settings.",
                uncertain=method == "POST",
            ) from None

    async def listing(self, path):
        rows, offset = [], 0
        try:
            async with asyncio.timeout(30):
                for _ in range(20):
                    page = await self.request("GET", path, params={"offset": offset, "limit": 100})
                    if not isinstance(page, dict) or not isinstance(page.get("data"), list):
                        raise UniFiError("UniFi returned an unexpected listing format.")
                    items, total = page["data"], page.get("totalCount")
                    if len(items) > 100 or any(not isinstance(item, dict) for item in items):
                        raise UniFiError("UniFi returned an unexpected listing format.")
                    if total is not None and (type(total) is not int or not 0 <= total <= 2000):
                        raise UniFiError("UniFi listing exceeds the supported inventory limit.")
                    for item in items:
                        identifier(item.get("id"))
                    rows.extend(
                        {"id": item["id"], "name": display_text(item.get("name") or "UniFi site")}
                        for item in items
                    )
                    offset += len(items)
                    if len({item["id"] for item in rows}) != len(rows):
                        raise UniFiError("UniFi returned duplicate equipment identifiers.")
                    if (
                        not items
                        or (total is not None and offset >= total)
                        or (total is None and len(items) < 100)
                    ):
                        return rows
        except TimeoutError:
            raise UniFiError("UniFi listing timed out.") from None
        raise UniFiError("UniFi listing exceeds the supported inventory limit.")

    async def sites(self):
        return await self.listing("/sites")

    async def device(self, site_id, switch_id):
        result = await self.request("GET", f"/sites/{identifier(site_id)}/devices/{identifier(switch_id)}")
        if not isinstance(result, dict) or result.get("id") != switch_id:
            raise UniFiError("The configured switch could not be verified.")
        interfaces = result.get("interfaces", {})
        if not isinstance(interfaces, dict) or not isinstance(interfaces.get("ports", []), list):
            raise UniFiError("UniFi returned malformed switch interfaces.")
        ports = interfaces.get("ports", [])
        if len(ports) > 1024:
            raise UniFiError("UniFi returned too many switch ports.")
        seen = set()
        for port in ports:
            if not isinstance(port, dict) or type(port.get("idx")) is not int or not 1 <= port["idx"] <= 1024:
                raise UniFiError("UniFi returned an invalid port identity.")
            if port["idx"] in seen:
                raise UniFiError("UniFi returned duplicate port identities.")
            seen.add(port["idx"])
            if port.get("poe") is not None and not isinstance(port["poe"], dict):
                raise UniFiError("UniFi returned invalid PoE details.")
        return result

    async def discover(self, site_id):
        try:
            async with asyncio.timeout(60):
                return await self._discover(site_id)
        except TimeoutError:
            raise UniFiError("UniFi discovery timed out.") from None

    async def _discover(self, site_id):
        if not any(site["id"] == site_id for site in await self.sites()):
            raise UniFiError("The selected site is not available to this API key.")
        devices = await self.listing(f"/sites/{identifier(site_id)}/devices")
        targets = []
        # Process each bounded batch immediately; never retain every raw device response.
        for offset in range(0, len(devices), 4):
            details = await asyncio.gather(
                *(self.device(site_id, device["id"]) for device in devices[offset : offset + 4])
            )
            for device in details:
                name = display_text(device.get("name") or device.get("model") or "UniFi switch")
                for port in device.get("interfaces", {}).get("ports", []):
                    if port.get("poe") is None:
                        continue
                    idx = port["idx"]
                    targets.append(
                        {
                            "site_id": site_id,
                            "switch_id": device["id"],
                            "switch_name": name,
                            "port_id": str(idx),
                            "port_number": idx,
                            "port_name": display_text(port.get("name") or ""),
                            "poe_capable": True,
                            "available": device.get("state") == "ONLINE",
                        }
                    )
                    if len(targets) > 10000:
                        raise UniFiError("UniFi inventory exceeds the supported port limit.")
        return targets

    async def validate(self, target):
        port_identity(target)
        device = await self.device(target["site_id"], target["switch_id"])
        if str(device.get("id")) != target["switch_id"]:
            raise UniFiError("The configured switch could not be verified.")
        if device.get("state") != "ONLINE":
            raise UniFiError("The configured switch is not online.")
        for port in device.get("interfaces", {}).get("ports", []):
            if str(port.get("idx")) == target["port_id"] and port.get("poe") is not None:
                return
        raise UniFiError("The configured port is missing or does not support PoE.")

    async def power_cycle(self, target):
        port_identity(target)
        await self.request(
            "POST",
            f"/sites/{identifier(target['site_id'])}/devices/"
            f"{identifier(target['switch_id'])}/interfaces/ports/"
            f"{int(target['port_number'])}/actions",
            json={"action": "POWER_CYCLE"},
        )
