# Running NetRevive

Installation uses the public image `ghcr.io/pat15312/net-revive:latest`. See the [README](../README.md) for the quick start.

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
- **Security:** change the administrator password using the current password. Other administrator sessions are signed out. Environment-managed passwords are changed through the container configuration.
- **UniFi:** connection/key settings, site selection, connection test, discovery, target labels and enabled flags.
- **Restart Groups:** create, edit, disable, order and delete groups; assign any number of discovered targets; customize buttons, descriptions, lockouts and recovery modes.
- **Health Monitoring:** intervals, timeouts, stable-recovery checks, DNS names and IP connectivity destinations.
- **Restart History:** paginated events, per-target details, pre-restart health, recovery outcomes and original configuration snapshots.

Deleting or renaming configuration never changes previous event snapshots. Deleting a group does not erase target lockouts.


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

The friendly hostname/URL setting is stored as the HTML canonical link (page metadata). It does not configure DNS, a reverse proxy, or the listening address. NetRevive has no footer displaying it. Direct IP/alternate-host access is intentionally preserved for DNS failures; NetRevive does not redirect or enforce a Host allowlist. For HTTPS proxying, preserve `Host` and the original `Origin`, set `COOKIE_SECURE=true`, and configure Uvicorn to trust forwarded scheme headers **only from that proxy's IP**. The default command disables proxy headers; replace that option with `--proxy-headers --forwarded-allow-ips=<proxy-ip>` when deploying behind the proxy. No wildcard proxy trust is needed.


## Persistence, secrets and backup

The `netrevive-data` named volume holds the SQLite database, its WAL/SHM files, the application process lock and an auto-generated encryption key when `SECRET_KEY` is omitted. Keep `DATABASE_PATH` inside `/data`. **Do not use `docker compose down -v` unless you intend to delete configuration and history.** SQLite must be on reliable local storage, not a network share with uncertain locking semantics.

Bootstrap variables are documented in [.env.example](../.env.example). Application settings are editable without recreating a container. Passwords use salted scrypt. Sessions are random server-side tokens stored as hashes, expire after eight hours, and rotate on login. Database-managed API keys use authenticated Fernet encryption. Protect the volume and `.env`: encryption does not protect against someone who can read both the database and its encryption key.

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


## Portainer

Create a stack using **Web editor** and paste the contents of [docker-compose.yml](../docker-compose.yml). Add `GHCR_OWNER=pat15312` under environment variables. Optionally set `NETREVIVE_PORT` if port 8080 is already in use. Deploy the stack, then open `http://<docker-host>:<port>` and complete setup.

For existing Web editor stacks, keep your current port mapping and data volume. Update the stack with **Re-pull image and redeploy** enabled.

## Updates and rollback

```bash
docker compose pull
docker compose up -d
```

Configuration and history survive image replacement. Updates are manual. Images are published for AMD64 and ARM64; `latest` follows `main`, and `sha-<short-commit>` identifies a particular build. To roll back, set `NETREVIVE_TAG` in `.env` to a previously published tag and run the commands above. Back up first and check database schema compatibility before downgrading.

Run one application process per database. Do not add replicas or Uvicorn workers sharing the same volume. The Docker healthcheck measures application availability, so an internet or UniFi outage does not mark the container unhealthy.
