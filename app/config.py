"""Bootstrap settings only; routine settings live in SQLite."""

import os
from dataclasses import dataclass, field
from pathlib import Path


def secret_value(name):
    value, filename = os.getenv(name, ""), os.getenv(name + "_FILE", "")
    if value and filename:
        raise RuntimeError(f"Set either {name} or {name}_FILE, not both.")
    if filename:
        value = Path(filename).read_text().strip()
    return value


@dataclass
class Bootstrap:
    database_path: str = field(default_factory=lambda: os.getenv("DATABASE_PATH", "data/netrevive.db"))
    admin_password: str = field(default_factory=lambda: secret_value("ADMIN_PASSWORD"))
    unifi_api_key: str = field(default_factory=lambda: secret_value("UNIFI_API_KEY"))
    secret_key: str = field(default_factory=lambda: secret_value("SECRET_KEY"))
    secure_cookie: bool = field(default_factory=lambda: os.getenv("COOKIE_SECURE", "false").lower() == "true")
    allowed_hosts: str = field(default_factory=lambda: os.getenv("ALLOWED_HOSTS", "localhost,net-revive.lan"))
    unifi_ca_file: str = field(default_factory=lambda: os.getenv("UNIFI_CA_FILE", ""))
    background: bool = True


DEFAULTS = {
    "title": "NetRevive",
    "timezone": "Europe/London",
    "controller_url": "",
    "api_prefix": "/proxy/network/integration/v1",
    "site_id": "",
    "verify_tls": True,
    "lockout_seconds": 300,
    "health_interval": 15,
    "recovery_timeout": 600,
    "recovery_successes": 3,
    "dns_names": ["example.com", "iana.org"],
    "internet_targets": [{"ip": "1.1.1.1", "port": 443}, {"ip": "8.8.8.8", "port": 443}],
    "internet_threshold": 1,
}
