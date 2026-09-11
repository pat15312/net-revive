import asyncio
import time

import dns.asyncresolver
import dns.exception
from cryptography.fernet import InvalidToken

from .database import put_setting, setting
from .logging import audit
from .unifi import UniFiError


def classify(internet, dns_ok, unifi):
    if unifi is False:
        return "recovery_problem"
    if internet is False:
        return "internet_problem"
    if dns_ok is False:
        return "dns_problem"
    if None in (internet, dns_ok, unifi):
        return "checking"
    return "healthy"


async def tcp_check(target):
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(target["ip"], target["port"]), 2)
        writer.close()
        await asyncio.wait_for(writer.wait_closed(), 2)
        return True
    except (OSError, TimeoutError):
        return False


async def dns_check(names):
    # Read the container's actual resolver configuration on every check. No application DNS cache.
    try:
        resolver = dns.asyncresolver.Resolver(configure=True)
    except (dns.exception.DNSException, OSError):
        return False
    resolver.cache = None
    resolver.timeout = 1
    resolver.lifetime = 2

    async def resolve(name):
        try:
            return bool(await resolver.resolve(name + ".", "A", search=False, lifetime=2))
        except (dns.exception.DNSException, OSError, TimeoutError):
            return False

    return any(await asyncio.gather(*(resolve(name) for name in names)))


class HealthMonitor:
    def __init__(self, db, client_factory):
        self.db, self.client_factory = db, client_factory

    def current(self):
        with self.db.connect() as conn:
            value = setting(
                conn,
                "health",
                {"internet": None, "dns": None, "unifi": None, "state": "checking", "checked_at": None},
            )
        if value["checked_at"] and time.time() - value["checked_at"] > max(
            60, self.db.settings()["health_interval"] * 3
        ):
            return {**value, "internet": None, "dns": None, "unifi": None, "state": "checking", "stale": True}
        return value

    async def unifi_check(self, settings):
        try:
            inventory = await self.client_factory().discover(settings["site_id"])
            discovered = {(t["site_id"], t["switch_id"], t["port_id"]): t for t in inventory}
            valid = True
            with self.db.connect(write=True) as conn:
                for target in conn.execute("SELECT * FROM targets").fetchall():
                    found = discovered.get((target["site_id"], target["switch_id"], target["port_id"]))
                    available = bool(found and found["available"] and found["poe_capable"])
                    conn.execute("UPDATE targets SET available=? WHERE id=?", (available, target["id"]))
                    if target["enabled"] and not available:
                        valid = False
            return valid
        except (UniFiError, InvalidToken):
            return False

    async def check_once(self):
        settings = self.db.settings()
        internet_results, dns_ok, unifi = await asyncio.gather(
            asyncio.gather(*(tcp_check(target) for target in settings["internet_targets"])),
            dns_check(settings["dns_names"]),
            self.unifi_check(settings),
        )
        internet = sum(internet_results) >= settings["internet_threshold"]
        sample = {
            "internet": internet,
            "dns": dns_ok,
            "unifi": unifi,
            "state": classify(internet, dns_ok, unifi),
            "checked_at": time.time(),
        }
        with self.db.connect(write=True) as conn:
            previous = setting(conn, "health", {})
            put_setting(conn, "health", sample)
        if previous.get("state") != sample["state"]:
            audit("health_transition", state=sample["state"])
        self.process_recovery(sample)
        return sample

    def process_recovery(self, sample):
        now = sample["checked_at"]
        with self.db.connect(write=True) as conn:
            for event in conn.execute("SELECT * FROM events WHERE recovery_status='monitoring'").fetchall():
                if now <= event["last_check_at"] or now <= (event["completed_at"] or event["created_at"]):
                    continue
                if now >= event["recovery_deadline"]:
                    conn.execute("UPDATE events SET recovery_status='timed_out' WHERE id=?", (event["id"],))
                    audit("recovery_timeout", event_id=event["id"])
                    continue
                healthy = sample["internet"] is True and sample["dns"] is True
                count = event["consecutive_successes"] + 1 if healthy else 0
                dns_failed = event["dns_failed"] or sample["dns"] is False
                dns_recovered = event["dns_recovered_at"]
                if dns_failed and sample["dns"] is True and dns_recovered is None:
                    dns_recovered = now
                conn.execute(
                    """UPDATE events SET consecutive_successes=?, last_check_at=?,
                    saw_unhealthy=?, dns_failed=?, dns_recovered_at=? WHERE id=?""",
                    (
                        count,
                        now,
                        event["saw_unhealthy"] or not healthy,
                        dns_failed,
                        dns_recovered,
                        event["id"],
                    ),
                )
                if count >= event["required_successes"]:
                    conn.execute(
                        """UPDATE events SET recovery_status='recovered', recovered_at=?,
                        recovery_duration=? WHERE id=?""",
                        (now, now - event["created_at"], event["id"]),
                    )
                    audit(
                        "network_recovered", event_id=event["id"], duration=round(now - event["created_at"])
                    )

    async def run(self):
        while True:
            try:
                await self.check_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                # Never serialize arbitrary exception text from network libraries.
                audit("health_check_error")
                self.process_recovery({"internet": None, "dns": None, "checked_at": time.time()})
            await asyncio.sleep(self.db.settings()["health_interval"])
