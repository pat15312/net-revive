from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.config import Bootstrap
from app.main import create_app
from app.unifi import UniFiError

PASSWORD = "test-administrator-password"


class FakeUniFi:
    def __init__(self):
        self.inventory = [
            {
                "site_id": "site-a",
                "switch_id": switch,
                "switch_name": switch,
                "port_id": str(port),
                "port_number": port,
                "port_name": f"Device {index}",
                "poe_capable": True,
                "available": True,
            }
            for index, (switch, port) in enumerate([("switch-a", 1), ("switch-a", 2), ("switch-b", 1)], 1)
        ]
        self.calls, self.fail, self.invalid = [], set(), set()
        self.unavailable = False

    async def sites(self):
        if self.unavailable:
            raise UniFiError("Controller unavailable.")
        return [{"id": "site-a", "name": "Test site"}]

    async def discover(self, site_id):
        await self.sites()
        return deepcopy(self.inventory)

    async def validate(self, target):
        if target["id"] in self.invalid:
            raise UniFiError("Port is not PoE capable.")

    async def power_cycle(self, target):
        self.calls.append(target["id"])
        if target["id"] in self.fail:
            raise UniFiError("UniFi returned HTTP 500.", uncertain=True)


class Browser:
    def __init__(self, client):
        self.client = client
        self.csrf = client.get("/api/session").json()["csrf"]

    def get(self, path):
        return self.client.get(path)

    def request(self, method, path, data=None):
        response = self.client.request(method, path, json=data, headers={"X-CSRF-Token": self.csrf})
        if response.headers.get("content-type", "").startswith("application/json") and response.json().get(
            "csrf"
        ):
            self.csrf = response.json()["csrf"]
        return response


@pytest.fixture
def app(tmp_path):
    instance = create_app(Bootstrap(database_path=str(tmp_path / "db.sqlite"), background=False))
    instance.state.fake = FakeUniFi()
    instance.state.client_factory = lambda: instance.state.fake
    return instance


@pytest.fixture
def browser(app):
    with TestClient(app) as client:
        yield Browser(client)


@pytest.fixture
def admin(browser):
    assert browser.request("POST", "/api/setup", {"password": PASSWORD}).status_code == 200
    return browser


@pytest.fixture
def inventory(admin):
    assert (
        admin.request(
            "PUT",
            "/api/admin/unifi",
            {"controller_url": "https://controller.test", "site_id": "site-a", "api_key": "private-test-key"},
        ).status_code
        == 200
    )
    assert admin.request("POST", "/api/admin/unifi/discover").status_code == 200
    return admin


def group(targets=None, **kwargs):
    return {
        "name": "Router",
        "button_label": "Restart Router",
        "target_ids": targets or [1],
        "confirm_targets": True,
        **kwargs,
    }


@pytest.fixture
def configured(inventory):
    assert inventory.request("POST", "/api/admin/operators", {"name": "Operator A"}).status_code == 201
    assert inventory.request("POST", "/api/admin/groups", group()).status_code == 201
    assert inventory.request("POST", "/api/admin/setup/finish").status_code == 200
    return inventory
