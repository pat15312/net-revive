# NetRevive

NetRevive is a local network recovery application. It lets people deliberately restart configured PoE-powered equipment using large, named controls, without opening UniFi Network. The interface, administrator authentication, configuration and control path work locally. Internet access is needed to download updates, not to render the application or request a restart.

## Restart Groups

A **Restart Group** is a named action such as “Restart Router” or “Restart APs”. Its administrator-selected ports can span multiple switches. One port may belong to several groups. Switch identity is always part of port identity; port 18 on two switches represents two different targets.

On your first dashboard visit, choose your name in the welcome dialog. NetRevive remembers it on this browser; click your name to switch users. Then hold a restart button for two seconds. Mouse, touch, Space and Enter are supported. Releasing early, leaving the button, losing focus or hiding the page cancels the hold. Operators are attribution labels, not authenticated identities.

The appearance buttons in the top navigation offer **Dark**, **Light**, and **Auto** (the default). Auto follows your device’s current theme, including changes while the page is open. Light and Dark override it; choose Auto again to clear the override. Your preference is remembered on this browser across dashboard and Admin pages. Click the NetRevive logo to return to the dashboard.

Each request is recorded with its group settings, operator, health state and target snapshots. A multi-port restart continues if an individual target fails. History distinguishes confirmed acceptance, rejection, unknown acceptance and requests that were never attempted. UniFi accepting a power-cycle request does **not** prove that the equipment has finished booting.

## Architecture

- Python 3.14, FastAPI, server-rendered HTML, vanilla JavaScript and plain CSS.
- Python's `sqlite3` data layer with parameterized queries, foreign keys, WAL journaling and explicit transactions. No separate database service.
- Normalized `targets`, `restart_groups`, `group_targets`, `events` and `event_targets` tables. A composite membership primary key prevents duplicates within a group without prohibiting overlap.
- Background asynchronous DNS, IP connectivity and UniFi health checks; lightweight dashboard polling.
- Official local UniFi Network integration v1 API; no legacy commands, cloud connector or general-purpose proxy.
- One application process per database, enforced with a process file lock. Do not run multiple replicas or Uvicorn workers against the same volume.

See [UniFi API verification](docs/unifi-api.md) for the documented endpoints and compatibility notes, and [safety and failure behaviour](docs/safety.md) for dispatch details.

## Requirements

- Docker Engine with Docker Compose v2 on an always-on Linux LAN host, AMD64 or ARM64.
- A local UniFi Network application exposing the integration v1 API and the documented port `POWER_CYCLE` action.
- An API key authorized to read sites/devices and execute port actions.
- PoE-capable UniFi switches and correctly configured PoE-powered equipment or PoE splitters.
- A network path from NetRevive to its controller/switches that remains usable during recovery. Consider management dependencies before grouping a controller or gateway with equipment it manages.

No Home Assistant, Homebridge, CDN, external font, cloud authentication or SaaS dependency is used.

## Deploy with Docker Compose

After the image has been published to your GitHub Container Registry namespace:

```bash
cp .env.example .env
# Edit .env: set GHCR_OWNER to the image owner's lowercase GitHub name.
docker compose pull
docker compose up -d
```

Open `http://<docker-host>:8080`. The default Compose mapping listens on all host interfaces; restrict it with `NETREVIVE_BIND` or your host firewall to the trusted LAN. If the GHCR package is private, authenticate the host with `docker login ghcr.io` using a token with package-read access. A repository clone alone does not create an image in GHCR.

For a local build before publishing:

```bash
cp .env.example .env
# Keep a nonempty GHCR_OWNER placeholder so Compose can resolve the base file.
docker build --target test -t net-revive:test .
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

The container runs as UID/GID `10001`, drops capabilities, uses a read-only root filesystem and stores data in a named volume. A process healthcheck tests `/healthz`; it deliberately does not fail when the internet or UniFi is down. A network outage is when NetRevive is most useful.

## Initial setup

1. Create an administrator password of at least 12 characters. If `ADMIN_PASSWORD` was provided, sign in with it instead. Until a password is claimed, first-run setup is available to visitors: complete setup on a trusted network before allowing general access.
2. Save the display title, friendly hostname and IANA display timezone.
3. Enter the local controller's HTTPS URL, controller type and API key; test the entered details, then save the connection. Testing does not change the saved configuration.
4. Choose a discovered site and select **Save site & discover ports**. Switch/port IDs come from UniFi, not manual text entry.
5. Create a group, choose its targets, label the restart button, set recovery behaviour and save.
6. Add the initial operator names.
7. Review health and restart settings, then finish setup. Completion rechecks the site's selected equipment.

Setup progress is stored immediately. If interrupted, sign in to resume. Nothing is power-cycled during setup, discovery, connection tests or health checks. After setup, `/` opens the dashboard; `/admin` opens the separate administrator area.

## UniFi configuration and equipment

Generate a local API key through your UniFi Network application's integration settings. The menu location and permissions depend on the installed release; consult its built-in API documentation. NetRevive sends this key as `X-API-Key` to your local HTTPS controller.

| Controller type | API prefix |
| --- | --- |
| UniFi OS console | `/proxy/network/integration/v1` |
| Self-hosted Network application | `/integration/v1` |

Supply the controller **origin**, such as `https://controller.lan` or `https://controller.lan:8443`, without a path. An IP address is useful if local DNS might be affected. Keep TLS verification enabled where possible. For a private CA, build a derived image containing that CA in the system trust bundle; alternatively configure a local trusted certificate on the controller. Admin can explicitly disable verification for a self-signed controller, accepting the impersonation risk.

Discovery preserves administrator labels, enabled flags, group memberships and lockouts. Missing/offline ports become unavailable; they are retained for review and history. PoE capability comes from the documented port `poe` object. UniFi does not document port display names in every release; NetRevive uses names when supplied and otherwise displays the port number. Add your own label in Admin.

A group's selected ports must be available, enabled and PoE capable when saving an enabled group. Disabled targets are never silently omitted during a restart; a group containing one is unavailable until its configuration is corrected. At dispatch, every target is checked against live switch details before any power-cycle requests are sent. General health remains advisory, so a stale health failure does not permanently prevent a fresh validation/restart attempt.

Changing the configured site does not move existing targets or groups to that site. Discover equipment and review group membership after changing sites. To avoid forwarding a saved credential to another controller, changing controller URL requires a newly supplied key unless the key is explicitly managed through the environment.

## Admin sections

- **General:** display title, preferred local hostname/URL and timezone.
- **Users:** add, edit, remove and order operator names.
- **UniFi:** connection/key settings, site selection, connection test, discovery, target labels and enabled flags.
- **Restart Groups:** create, edit, disable, order and delete groups; assign any number of discovered targets; customize buttons, descriptions, lockouts and recovery modes.
- **Health Monitoring:** intervals, timeouts, stable-recovery checks, DNS names and IP connectivity destinations.
- **Restart History:** paginated events, per-target details, pre-restart health, recovery outcomes and original configuration snapshots.

Deleting or renaming configuration never changes previous event snapshots. Deleting a group does not erase target lockouts.

## Overlapping groups and lockouts

The global default lockout is **300 seconds**. Each group can inherit it or override it. An admission transaction reserves the entire group and all its targets before any I/O. Other clients cannot admit a conflicting request. Groups with disjoint targets remain independently usable.

A group remains disabled while it or any required target is locked. NetRevive never silently skips a locked port. Lockouts use persisted UTC deadlines and survive browser refreshes, different devices, configuration edits and container restarts. The browser countdown is informational; the backend is authoritative.

Conservative policy: all admitted targets keep their cooldown even after a validation failure, API error or uncertain timeout, because immediate repeated attempts can be unsafe. The deadline is extended from completion of dispatch. In-flight reservations remain active even if dispatch outlasts the original deadline. If the process stops mid-dispatch, startup marks unfinished results as interrupted/unknown and applies a fresh cooldown; it never replays a power-cycle request automatically.

## Health monitoring and recovery

Defaults: checks every **15 seconds**, **600-second** recovery timeout, **three consecutive healthy checks**.

- **Internet:** short TCP connections to at least two configurable IP/port destinations, independent of DNS. The default requires one success, tolerating one endpoint failure. A TCP response suggests connectivity, not that every internet service works.
- **DNS:** asynchronous queries through the container's normal resolver configuration, using multiple names. NetRevive has no application DNS cache. Upstream caches can still hide a partial DNS failure; the test measures user-visible resolver availability, not authoritative DNS reachability.
- **UniFi:** read-only discovery checks authentication, the site, switches and configured ports. A missing target is surfaced in Admin and UniFi health.

The status differentiates healthy connectivity, DNS trouble, internet trouble and a recovery-system problem. All three individual results stay visible when multiple problems occur. Outdated health samples are shown as unknown, not healthy. The browser disables controls if it cannot get a recent response from NetRevive; server-side lockouts remain in force.

**Network health mode** watches DNS and internet access after dispatch. Only distinct, post-dispatch samples count; a failed sample resets the consecutive-success count. If an outage was observed, history says the network recovered. If no outage was observed, it says network health was confirmed; this does not establish device readiness. DNS returning after an observed failure is recorded separately. A timeout ends that event's recovery monitoring, not the normal background checks. After an application restart, pending recovery monitoring resumes before its original deadline, with consecutive-success count reset.

**None mode** records only whether UniFi accepted each power-cycle request. It never reports a network-recovery duration. Use it for access points, cameras and equipment whose recovery cannot be inferred from the wired server's internet access. The group lockout still applies.

## Local DNS and friendly hostname

Create a local DNS record pointing `net-revive.lan` (or your chosen hostname) to the Docker host. Configure your LAN DNS server/router; NetRevive does not change DNS records. If using the default port, browse to `http://net-revive.lan:8080`, and store that full origin as the friendly URL if desired. For a portless URL, use a local reverse proxy or map host port 80 to container port 8080.

The configured origin is displayed and used for the HTML canonical link. Direct IP/alternate-host access is intentionally preserved for DNS failures; NetRevive does not redirect or enforce a Host allowlist. For HTTPS proxying, preserve `Host` and the original `Origin`, set `COOKIE_SECURE=true`, and configure Uvicorn to trust forwarded scheme headers **only from that proxy's IP**. The default command disables proxy headers; replace that option with `--proxy-headers --forwarded-allow-ips=<proxy-ip>` when deploying behind the proxy. No wildcard proxy trust is needed.

## Persistence, secrets and backup

The `netrevive-data` named volume holds the SQLite database, its WAL/SHM files, the application process lock and an auto-generated encryption key when `SECRET_KEY` is omitted. Keep `DATABASE_PATH` inside `/data`. **Do not use `docker compose down -v` unless you intend to delete configuration and history.** SQLite must be on reliable local storage, not a network share with uncertain locking semantics.

Bootstrap variables are documented in [.env.example](.env.example). Application settings are editable without recreating a container. Passwords use salted scrypt. Sessions are random server-side tokens stored as hashes, expire after eight hours, and rotate on login. Database-managed API keys use authenticated Fernet encryption. Protect the volume and `.env`: encryption does not protect against someone who can read both the database and its encryption key.

Make a consistent online backup with SQLite's backup API:

```bash
docker compose exec net-revive python -m app.backup /data/netrevive-backup.db
docker compose cp net-revive:/data/netrevive-backup.db ./netrevive-backup.db
# If SECRET_KEY is blank, also copy the generated key:
docker compose cp net-revive:/data/secret.key ./netrevive-secret.key
chmod 600 netrevive-backup.db netrevive-secret.key
```

If `SECRET_KEY` is set, back it up separately instead of copying `secret.key`. Never copy only the live `.db` file while writes are occurring, because committed data may still be in the WAL. Alternatively stop the service and back up the complete volume.

To restore, stop NetRevive, restore the backup and matching key into the volume, remove obsolete WAL/SHM files **only while the service is stopped**, ensure UID/GID `10001` owns the restored files, then start it. A restored old database can lack more recent lockouts; wait at least your longest cooldown and confirm equipment state before enabling operators. Schema version 1 is initialized automatically; newer unknown schemas are rejected rather than silently downgraded.

To recover a forgotten admin password, set `ADMIN_PASSWORD` to a new long password and recreate the container. Startup hashes the replacement and invalidates existing sessions. Remove the variable and recreate once more if you want to retain only the database-managed hash.

## GitHub Container Registry and updates

Create a GitHub repository such as `net-revive`, push this source and enable Actions. The workflow runs Ruff, the full mocked pytest suite, JavaScript syntax checking and the Docker test target before the publish job can start. Pull requests test without publishing. Pushes to `main` publish `latest`; tags such as `v1.0.0` publish that exact version. Images include AMD64 and ARM64 manifests and commit-derived tags. GitHub's built-in token needs permission to write packages; make the package public if anonymous pulls are desired.

The production Compose file stays pointed at:

```text
ghcr.io/<owner>/net-revive:latest
```

Update with:

```bash
docker compose pull
docker compose up -d
```

Configuration survives image replacement. There is no automatic deployment, updater or Watchtower. For rollback, set `NETREVIVE_TAG=v1.0.0` in `.env` and run the same two commands. Back up first and check schema compatibility; restore the matching backup when downgrading across schema changes.

## Logs and troubleshooting

```bash
docker compose logs -f --tail=100 net-revive
docker compose ps
```

Application logs are JSON records for startup/shutdown, safe configuration changes, health transitions, admission, per-target outcomes and recovery. HTTP access logging and third-party request logging are suppressed. Logs do not include passwords, API keys, session tokens or raw controller response bodies.

| Symptom | Check |
| --- | --- |
| Controller unavailable | Local URL/port, controller API support, API-key permissions and TLS trust. Use **Test UniFi connection**. |
| No sites or ports | Correct controller type/prefix, site access and whether the device details expose PoE ports. Update UniFi if the documented API is unavailable. No legacy fallback is attempted. |
| A port disappeared | Refresh discovery, review the switch in UniFi and inspect Admin target availability. |
| Restart unavailable | Selected operator, group enabled state, disabled members, group/target cooldown or in-flight request. |
| Partial/unknown result | Open detailed history; a timeout can mean UniFi received the request. Do not bypass the cooldown. |
| DNS fails but IP checks pass | Inspect the container's `/etc/resolv.conf`, host resolver, Docker DNS configuration and LAN DNS server. |
| Recovery times out | Inspect equipment separately. Wired internet health cannot measure every device's readiness. |
| Login/CSRF fails | Reload to refresh the session; check HTTP versus HTTPS cookie settings and trusted proxy scheme/Host forwarding. |
| Database permissions error | Named volume ownership, or UID/GID `10001` ownership for a manually prepared bind mount. |
| Database already in use | Stop the other NetRevive instance; use one worker and one replica per database. |
| GHCR pull denied | Confirm the image was published, its owner/path, package visibility and registry login. |

## Security boundaries

Use a trusted LAN and a host firewall. Do not expose this service to the public internet. Anyone able to use the ordinary dashboard can select a configured operator and trigger its configured restart groups; that is intentional. Admin sessions, CSRF checks, strict input schemas, per-IP/global login throttling, restart rate limits and transactional lockouts protect configuration and repeated actions. Local HTTPS is preferable wherever practical. HTTP on a trusted LAN cannot protect credentials from a network observer.

There is no general UniFi proxy and no endpoint accepts arbitrary commands, API paths, PoE states or browser-supplied target lists. Target IDs sent to Admin group configuration refer only to already-discovered database records. API validation errors omit submitted secret inputs, and controller errors are sanitized. Secrets are never returned in configuration responses.

## Development and testing

```bash
python3.14 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.lock
ruff check app tests
pytest -q
node --check app/static/app.js
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8080 --no-access-log
```

Development defaults to `data/netrevive.db`, ignored by Git. `requirements.txt` records direct dependencies; `requirements.lock` pins the entire runtime closure; `requirements-dev.lock` pins test dependencies as well. Update these together and rerun both native and Docker tests.

Tests mock all UniFi, DNS and internet interactions. They cover first-run setup, authentication, configuration, many-to-many membership, multi-switch identity, validation, admission races, cooldown persistence, interrupted dispatch, partial/complete failure, official API request shapes, stable recovery and immutable history. The production container does not contain tests or any simulated controller. Real-hardware compatibility must be checked on the deployment's installed UniFi version before assigning operational equipment.

NetRevive is distributed under the [MIT License](LICENSE).
