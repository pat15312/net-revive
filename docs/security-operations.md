# Operational security

## Reachability and browser protection

Keep NetRevive on a controlled LAN; firewall its published port to intended clients. A compromised device with ordinary API access has the same restart authority as a household user. Hold-to-restart cannot establish human intent against an arbitrary HTTP client.

`ALLOWED_HOSTS` is a comma-separated list of **exact hostnames**, without schemes, paths or wildcard suffixes. Defaults: `localhost,net-revive.lan`. Direct RFC1918 IPv4, IPv4 loopback, IPv6 loopback and IPv6 ULA access remains available for DNS failures, with any valid TCP port. Add other names explicitly, including `netrevive.local` if used. Public IP literals require explicit configuration. Do not add attacker-controlled public hostnames. Host validation does not restrict which clients may connect; use a firewall for that.

The retired friendly-hostname setting does not influence Host validation. No CORS access is enabled. The default Docker command ignores forwarded headers. A reverse proxy must preserve Host/Origin and must not rewrite a hostile incoming hostname into an allowed one. Accept only configured hostnames at the proxy too.

## Optional HTTPS through an existing LAN proxy

1. Give NetRevive a stable local DNS name and a certificate trusted by household devices. A private CA works if installed on those devices; public certificates may be obtained using DNS validation without exposing the app publicly.
2. Proxy that HTTPS hostname to NetRevive on its private Docker network. Remove the public backend port, bind it to loopback when the proxy runs on the same host, or firewall it to the proxy alone.
3. Set `ALLOWED_HOSTS` to include that exact name and `COOKIE_SECURE=true`.
4. Replace Uvicorn's `--no-proxy-headers` with `--proxy-headers --forwarded-allow-ips=<exact-proxy-IP>`. Retain the other command flags. Never use `*` for trusted proxies. Configure the proxy to preserve the original Host and report the true HTTPS scheme; restrict direct backend access so clients cannot spoof that trusted peer.
5. Verify login, logout, CSRF, device themes and normal restart behavior using fake/test equipment before operational use. Add HSTS at the HTTPS proxy only after validating the certificate/trust arrangement; do not add it indiscriminately to HTTP/IP access.

This is an optional deployment model, not a claim that an existing HTTP installation has been converted. The audit did not change live Portainer/proxy settings. Existing HTTP stacks remain usable with `COOKIE_SECURE=false`, with the interception risk explicitly retained.

## Trusting a private UniFi certificate

Mount a PEM CA certificate read-only and set `UNIFI_CA_FILE=/run/secrets/unifi-ca.pem`; keep **Verify the controller's TLS certificate** enabled. The controller URL must match the certificate's DNS/IP subject alternative name. This uses Python's normal chain and hostname verification, with no silent fallback to `verify=False`.

For a truly self-signed server certificate, explicitly trusting that certificate can work when it has valid certificate extensions and matches the configured URL. Prefer a properly issued private-CA certificate. Verify its fingerprint through a separate trusted channel before installing it. Rotate the UniFi API key if interception is suspected.

## Secrets

`ADMIN_PASSWORD_FILE`, `UNIFI_API_KEY_FILE` and `SECRET_KEY_FILE` read secrets from mounted files. Setting both the ordinary variable and its `_FILE` form fails startup. Docker Compose `secrets` mounts are one supported way to supply these files. Give the container UID 10001 read access, protect the host originals, and keep files out of source control. Plain Compose secrets protect image metadata exposure; they are not a vault and host administrators can still read them.

Example fragment to merge into a stack (create the file privately first):

```yaml
services:
  net-revive:
    environment:
      UNIFI_API_KEY: ""
      UNIFI_API_KEY_FILE: /run/secrets/unifi_api_key
    secrets:
      - unifi_api_key
secrets:
  unifi_api_key:
    file: ./private/unifi-api-key.txt
```

Do not embed the credential in Compose YAML. Blank API-key fields preserve the saved key; the UI never populates a masked placeholder. Environment/file-managed keys cannot be carried to a different controller by editing its URL: reconfigure the bootstrap source and connection deliberately. Database-managed keys require a newly entered key when changing origins. Encryption protects a database copied without its key, not a compromised running container/host.

Set a bootstrap Admin password through a protected file before first exposure, or restrict the initial setup page to your own client. First-run setup deliberately allows the first reachable client to claim the installation; its transaction prevents multiple successful claimants, not an attacker winning the first claim.

## Limits, storage and updates

HTTP limits: 64 KiB body, 10-second upload deadline, 16 KiB headers, 8 KiB query, 32 active requests, 600 requests/client/minute, 2,400 globally/minute. Session creation: 60/client/minute, 120 globally/minute, 1,024 retained sessions; oldest anonymous sessions are evicted before administrator sessions. Sessions expire after eight hours (absolute lifetime, no inactivity timeout).

UniFi: four concurrent requests process-wide, 12-second request deadline including queue time, 2 MB uncompressed response limit, 30-second/2,000-item listing limit, 60-second discovery deadline, four-device batches, 10,000 discovered PoE ports and 256 targets/group. Malformed/duplicate identities fail closed. There are no automatic power-cycle retries. These limits are intended for local/home deployments, not an unbounded enterprise controller.

Administrators can configure HTTPS controller destinations on private or public networks; only fixed integration paths are used. Health TCP destinations are literal IP/ports and receive no application payload. DNS checks use the container resolver. These are privileged network-probe capabilities, not an unprivileged URL-fetch API. Redirects and environment HTTP proxies are disabled. Use container/host egress rules to exclude metadata, management networks and other unnecessary destinations if the Admin boundary is not sufficient for your environment. DNS rebinding of an outbound configured controller still requires valid TLS identity to receive credentials when verification is enabled; disabling verification removes this safeguard.

Use the shipped non-root, read-only, capability-dropped Compose defaults. Protect `/data` and backup files; watch disk utilization and apply a volume quota suited to retained history. Application history is intentionally retained, so long-term authorized activity can consume disk. Login throttling can temporarily deny legitimate logins during a sustained attack; firewall abusive clients. Backups include password hashes and session state: restore only trusted backups, restrict access during restoration and rotate sessions/passwords if a backup may have leaked. Restored lockouts/history may be stale; wait the longest configured cooldown and inspect equipment before resuming access.

Update through Portainer's **Re-pull image and redeploy**, preserving the volume. `latest` is mutable; `v*` and `sha-*` tags identify releases/builds by convention but repository owners can still retag them. Pin an image digest for immutable selection and record it with backups. Candidate tags are unpromoted build outputs and must not be deployed. Release tags are promoted from the scanned multi-platform digest without rebuilding. CI blocks fixable High/Critical advisories; unfixed advisories remain visible and require review rather than being silently suppressed.

Enable GitHub private vulnerability reporting, branch protections, required review/checks, protected release tags, strong MFA and recovery controls. The audit could inspect workflow code, but could not verify account/organization enforcement settings. Dependabot proposes weekly action/base/dependency updates; regenerate hash locks and run tests before merging. Do not let automation merge dependency changes or deploy unattended merely because a scanner is green.
