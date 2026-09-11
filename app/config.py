"""Bootstrap settings only; routine settings live in SQLite."""

import os
from dataclasses import dataclass, field


@dataclass
class Bootstrap:
    database_path: str = field(default_factory=lambda: os.getenv("DATABASE_PATH", "data/netrevive.db"))
    admin_password: str = field(default_factory=lambda: os.getenv("ADMIN_PASSWORD", ""))
    unifi_api_key: str = field(default_factory=lambda: os.getenv("UNIFI_API_KEY", ""))
    secret_key: str = field(default_factory=lambda: os.getenv("SECRET_KEY", ""))
    secure_cookie: bool = field(default_factory=lambda: os.getenv("COOKIE_SECURE", "false").lower() == "true")
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
