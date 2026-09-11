import ipaddress
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Password(StrictModel):
    password: str = Field(min_length=1, max_length=256)


class General(StrictModel):
    title: str = Field(min_length=1, max_length=80)
    hostname: str = Field(min_length=1, max_length=253)
    timezone: str

    @field_validator("hostname")
    @classmethod
    def hostname_valid(cls, value):
        parsed = urlsplit(value if "://" in value else "http://" + value)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
        ):
            raise ValueError("Use a hostname or an HTTP(S) origin without a path.")
        try:
            parsed.port
        except ValueError:
            raise ValueError("Invalid port.") from None
        if not re.fullmatch(r"[a-zA-Z0-9.:[\]-]+", parsed.netloc):
            raise ValueError("Invalid hostname.")
        return value.rstrip("/")

    @field_validator("timezone")
    @classmethod
    def timezone_valid(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Use an IANA timezone, such as Europe/London.") from None
        return value


class UniFiSettings(StrictModel):
    controller_url: str
    api_prefix: str = "/proxy/network/integration/v1"
    site_id: str = ""
    verify_tls: bool = True
    api_key: str = Field(default="", max_length=4096)

    @field_validator("controller_url")
    @classmethod
    def controller_valid(cls, value):
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Use the local controller HTTPS origin, without a path or credentials.")
        if parsed.hostname.lower() in ("api.ui.com", "unifi.ui.com"):
            raise ValueError("Use a local controller, not UniFi's cloud API.")
        try:
            parsed.port
        except ValueError:
            raise ValueError("Invalid controller port.") from None
        return value.rstrip("/")

    @field_validator("api_prefix")
    @classmethod
    def prefix_valid(cls, value):
        if value not in ("/proxy/network/integration/v1", "/integration/v1"):
            raise ValueError("Unsupported API prefix.")
        return value

    @field_validator("site_id")
    @classmethod
    def site_valid(cls, value):
        if value and not re.fullmatch(r"[a-zA-Z0-9-]{1,100}", value):
            raise ValueError("Invalid site identifier.")
        return value


class InternetTarget(StrictModel):
    ip: str
    port: int = Field(ge=1, le=65535)

    @field_validator("ip")
    @classmethod
    def ip_valid(cls, value):
        return str(ipaddress.ip_address(value))


class Monitoring(StrictModel):
    lockout_seconds: int = Field(ge=10, le=86400)
    health_interval: int = Field(ge=5, le=300)
    recovery_timeout: int = Field(ge=30, le=7200)
    recovery_successes: int = Field(ge=2, le=20)
    dns_names: list[str] = Field(min_length=2, max_length=10)
    internet_targets: list[InternetTarget] = Field(min_length=2, max_length=10)
    internet_threshold: int = Field(ge=1, le=10)

    @field_validator("dns_names")
    @classmethod
    def names_valid(cls, values):
        for value in values:
            if not re.fullmatch(r"(?=.{1,253}$)[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?", value):
                raise ValueError("Invalid DNS name.")
        return values

    @model_validator(mode="after")
    def checks_valid(self):
        if len({t.ip for t in self.internet_targets}) < 2:
            raise ValueError("Use at least two different connectivity destinations.")
        if len(set(self.dns_names)) < 2:
            raise ValueError("Use at least two different DNS names.")
        if self.internet_threshold >= len(self.internet_targets):
            raise ValueError("Threshold must tolerate at least one unavailable destination.")
        if self.recovery_timeout < self.health_interval * self.recovery_successes:
            raise ValueError("Recovery timeout must allow the required number of checks.")
        return self


class Operator(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    display_order: int = Field(default=0, ge=-100000, le=100000)


class Group(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    button_label: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    enabled: bool = True
    display_order: int = Field(default=0, ge=-100000, le=100000)
    lockout_seconds: int | None = Field(default=None, ge=10, le=86400)
    recovery_mode: str = "network"
    target_ids: list[int] = Field(min_length=1)
    confirm_targets: bool = False

    @field_validator("target_ids")
    @classmethod
    def targets_unique(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("A target can occur only once within a group.")
        return values

    @field_validator("recovery_mode")
    @classmethod
    def mode_valid(cls, value):
        if value not in ("network", "none"):
            raise ValueError("Choose network or none.")
        return value


class TargetEdit(StrictModel):
    label: str = Field(default="", max_length=100)
    enabled: bool = True


class RestartRequest(StrictModel):
    operator: str = Field(min_length=1, max_length=80)
