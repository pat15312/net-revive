import json

import httpx
import pytest

from app.config import DEFAULTS
from app.unifi import UniFiClient, UniFiError

SETTINGS = {**DEFAULTS, "controller_url": "https://controller.test"}
TARGET = {"site_id": "site-a", "switch_id": "switch-a", "port_id": "18", "port_number": 18}


async def test_official_port_action_exact_path_and_payload():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={})

    client = UniFiClient(SETTINGS, "secret-key", httpx.MockTransport(handler))
    await client.power_cycle(TARGET)
    assert len(requests) == 1
    assert (
        requests[0].url.path
        == "/proxy/network/integration/v1/sites/site-a/devices/switch-a/interfaces/ports/18/actions"
    )
    assert json.loads(requests[0].content) == {"action": "POWER_CYCLE"}
    assert requests[0].headers["X-API-Key"] == "secret-key"


@pytest.mark.parametrize("status", [301, 401, 403, 404, 429, 500])
async def test_api_failures_are_sanitized_and_never_retried(status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            status, text="sensitive-controller-body", headers={"Location": "https://other.test"}
        )

    client = UniFiClient(SETTINGS, "secret-key", httpx.MockTransport(handler))
    with pytest.raises(UniFiError) as error:
        await client.power_cycle(TARGET)
    assert "sensitive-controller-body" not in str(error.value)
    assert "secret-key" not in str(error.value)
    assert len(requests) == 1


async def test_ambiguous_timeout():
    def handler(request):
        raise httpx.ReadTimeout("secret-key in upstream exception")

    client = UniFiClient(SETTINGS, "secret-key", httpx.MockTransport(handler))
    with pytest.raises(UniFiError) as error:
        await client.power_cycle(TARGET)
    assert error.value.uncertain and "secret-key" not in str(error.value)


async def test_documented_discovery_schema_and_poe_filter():
    def handler(request):
        if request.url.path.endswith("/sites"):
            return httpx.Response(200, json={"data": [{"id": "site-a", "name": "Site"}], "totalCount": 1})
        if request.url.path.endswith("/devices"):
            return httpx.Response(200, json={"data": [{"id": "switch-a"}], "totalCount": 1})
        return httpx.Response(
            200,
            json={
                "id": "switch-a",
                "name": "Switch",
                "state": "ONLINE",
                "interfaces": {
                    "ports": [
                        {
                            "idx": 18,
                            "poe": {"enabled": False, "state": "DOWN", "type": 1, "standard": "802.3af"},
                        },
                        {"idx": 19},
                        {"idx": 20, "poe": None},
                    ]
                },
            },
        )

    client = UniFiClient(SETTINGS, "key", httpx.MockTransport(handler))
    targets = await client.discover("site-a")
    assert len(targets) == 1 and targets[0]["port_number"] == 18 and targets[0]["poe_capable"]
    await client.validate(TARGET)
    with pytest.raises(UniFiError):
        await client.validate({**TARGET, "port_id": "19"})


async def test_pagination():
    calls = []

    def handler(request):
        offset = int(request.url.params["offset"])
        calls.append(offset)
        rows = [{"id": str(i)} for i in range(offset, min(offset + 100, 105))]
        return httpx.Response(200, json={"data": rows, "totalCount": 105})

    client = UniFiClient(SETTINGS, "key", httpx.MockTransport(handler))
    assert len(await client.sites()) == 105
    assert calls == [0, 100]


async def test_self_hosted_prefix():
    paths = []

    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(200, json={"data": [], "totalCount": 0})

    client = UniFiClient({**SETTINGS, "api_prefix": "/integration/v1"}, "key", httpx.MockTransport(handler))
    assert await client.sites() == []
    assert paths == ["/integration/v1/sites"]
