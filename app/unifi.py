"""Official local Network integration v1 API. No legacy API, cloud proxy or automatic POST retries."""

import asyncio
import ssl
from urllib.parse import quote

import httpx


class UniFiError(Exception):
    def __init__(self, message, uncertain=False):
        super().__init__(message)
        self.uncertain = uncertain


class UniFiClient:
    def __init__(self, settings, api_key, transport=None):
        self.settings = settings
        self.api_key = api_key
        self.transport = transport
        self.slots = asyncio.Semaphore(4)

    async def request(self, method, path, **kwargs):
        if not self.settings["controller_url"] or not self.api_key:
            raise UniFiError("Configure a local controller and API key in Admin.")
        url = self.settings["controller_url"] + self.settings["api_prefix"] + path
        try:
            async with (
                self.slots,
                asyncio.timeout(12),
                httpx.AsyncClient(
                    verify=ssl.create_default_context() if self.settings["verify_tls"] else False,
                    timeout=httpx.Timeout(8, connect=3),
                    transport=self.transport,
                    trust_env=False,
                    follow_redirects=False,
                ) as client,
            ):
                response = await client.request(method, url, headers={"X-API-Key": self.api_key}, **kwargs)
            if response.status_code in (401, 403):
                raise UniFiError("UniFi denied access. Check the API key and its permissions.")
            if not 200 <= response.status_code < 300:
                raise UniFiError(
                    f"UniFi returned HTTP {response.status_code}.",
                    uncertain=method == "POST" and response.status_code >= 500,
                )
            if method == "POST":
                return None
            return response.json()
        except (httpx.HTTPError, ValueError, TimeoutError):
            raise UniFiError(
                "UniFi did not return a valid response. Check connectivity and TLS settings.",
                uncertain=method == "POST",
            ) from None

    async def listing(self, path):
        rows, offset = [], 0
        while True:
            page = await self.request("GET", path, params={"offset": offset, "limit": 100})
            if not isinstance(page, dict) or not isinstance(page.get("data"), list):
                raise UniFiError("UniFi returned an unexpected listing format.")
            items = page["data"]
            rows.extend(items)
            offset += len(items)
            total = page.get("totalCount")
            if not items or (total is not None and offset >= total) or (total is None and len(items) < 100):
                return rows

    async def sites(self):
        return await self.listing("/sites")

    async def device(self, site_id, switch_id):
        return await self.request(
            "GET", f"/sites/{quote(site_id, safe='')}/devices/{quote(switch_id, safe='')}"
        )

    async def discover(self, site_id):
        if not any(str(site["id"]) == site_id for site in await self.sites()):
            raise UniFiError("The selected site is not available to this API key.")
        devices = await self.listing(f"/sites/{quote(site_id, safe='')}/devices")
        details = await asyncio.gather(*(self.device(site_id, str(device["id"])) for device in devices))
        targets = []
        for device in details:
            for port in device.get("interfaces", {}).get("ports", []):
                # The documented nullable PoE object identifies PoE-capable ports, even when disabled.
                if port.get("poe") is None:
                    continue
                idx = port.get("idx")
                if not isinstance(idx, int) or idx < 1:
                    continue
                targets.append(
                    {
                        "site_id": site_id,
                        "switch_id": str(device["id"]),
                        "switch_name": device.get("name") or device.get("model") or "UniFi switch",
                        "port_id": str(idx),
                        "port_number": idx,
                        "port_name": port.get("name") or "",
                        "poe_capable": True,
                        "available": device.get("state") == "ONLINE",
                    }
                )
        return targets

    async def validate(self, target):
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
        await self.request(
            "POST",
            f"/sites/{quote(target['site_id'], safe='')}/devices/"
            f"{quote(target['switch_id'], safe='')}/interfaces/ports/"
            f"{int(target['port_number'])}/actions",
            json={"action": "POWER_CYCLE"},
        )
