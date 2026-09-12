# Security policy

## Supported versions

Security fixes target the current `main` branch and the newest published release. Older images, including old `sha-*` tags, are not maintained separately. Update promptly and retain a compatible backup before upgrading. `latest` is convenient; a recorded image digest provides reproducibility. See [the security assessment](SECURITY_AUDIT.md) for the audited baseline and remaining risks.

## Reporting a vulnerability

Use the repository's **Security → Advisories → Report a vulnerability** option when available. Private vulnerability reporting is a GitHub repository setting; its enabled state has not been verified by this audit. If the option is unavailable, open a minimal issue asking the maintainer for a private reporting channel. Do not post exploit details, credentials, session cookies, database files or network topology publicly.

Include the affected version/image digest, prerequisites, expected/actual behavior and a minimal reproduction using fake equipment. Never demonstrate an issue by power-cycling someone else's production equipment. Coordinate disclosure with the maintainer and allow time to investigate and publish a fix; no response-time guarantee is currently offered.

## Deployment assumptions

NetRevive is for a controlled LAN. **Do not expose it directly to the public internet.** Restrict access with a firewall/VLAN or authenticated VPN. Anyone with ordinary dashboard/API access can restart enabled groups and can select another person's name. Names are attribution, not authentication; press-and-hold is accidental-click protection, not an API security boundary.

Use HTTPS for administrator access and keep UniFi certificate verification enabled with a trusted certificate or configured private CA. Plain HTTP exposes credentials and sessions to network interception; disabling controller verification permits API-key interception. Neither risk is solved merely by running on a LAN.

Protect the Docker host, database volume, backups, encryption key and GitHub publishing account. A reader with both database and encryption key can recover the UniFi credential. Use one process per database and durable local storage. Do not restore untrusted databases or roll back past recent lockouts without checking equipment state.

See [operational hardening](docs/security-operations.md), [HTTP surface](docs/security-routes.md), and [audit findings and evidence](SECURITY_AUDIT.md).
