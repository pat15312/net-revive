# NetRevive

**Simple, local network recovery for UniFi PoE equipment.**

Give your household an easy way to restart a router, firewall or access point without opening UniFi Network. Choose a name, then hold a clearly labelled restart button for two seconds. NetRevive power-cycles the configured PoE ports and records the result.

Runs on your LAN, including on a Raspberry Pi. The dashboard and restart controls work without an internet connection, provided the local controller remains reachable.

## Features

- **Named restart groups** spanning one or more switches, with shared-port cooldowns to prevent repeated restarts.
- **Live health status** for internet connectivity, DNS and UniFi, with optional recovery monitoring.
- **Restart history** showing who requested each restart and what happened to each target.
- **Simple administration** for connection settings, users, groups, monitoring and passwords. Reorder users and groups with up/down buttons. Browse switches in collapsible sections with clickable, 12-column port grids.
- **Mobile-friendly interface** with a sticky navigation bar, remembered user selection and automatic, light or dark appearance.
- **Self-contained deployment:** Docker, SQLite and local assets. No cloud login or external database required.

## Requirements

- An always-on Linux host running Docker Compose or Portainer; AMD64 and ARM64 images are available.
- A UniFi Network controller with the official local integration API and PoE port power-cycle support, plus an API key with the necessary permissions.
- A UniFi PoE switch and equipment powered through PoE or a compatible splitter.

Keep NetRevive and its controller reachable while equipment restarts. Use a trusted LAN: dashboard users can restart configured equipment, and their selected names are attribution labels, not authenticated accounts.

## Quick start

```bash
git clone https://github.com/pat15312/net-revive.git
cd net-revive
cp .env.example .env
docker compose up -d
```

Open **`http://<docker-host>:8080`**. The default configuration uses the public image, so no registry login is needed. If port 8080 is occupied, change `NETREVIVE_PORT` in `.env` first. For Portainer, see the [deployment guide](docs/operations.md#portainer).

Complete the setup wizard:

1. Create an administrator password and save your general settings.
2. Enter your controller’s local HTTPS address and API key. Test the connection, save it, then select a site and discover its ports.
3. Create restart groups, add user names, review monitoring settings and finish setup.

Find API-key creation under **Integrations** in your installed UniFi Network application; the menu location varies by version. Use the local controller address, not `unifi.ui.com`. See [UniFi connection guidance](docs/unifi-api.md#connection-setup) for details. Setup and discovery do not restart equipment.

All settings remain available in **Admin** after setup. Click the NetRevive logo to return to the dashboard.

## Updating

```bash
docker compose pull
docker compose up -d
```

Configuration and history persist in the data volume. Back it up before updates; do not delete the volume when redeploying. [Backup and restore instructions](docs/operations.md#persistence-secrets-and-backup).

## Documentation

- [Configuration, backups and troubleshooting](docs/operations.md)
- [UniFi API and compatibility](docs/unifi-api.md)
- [Restart safeguards and failure handling](docs/safety.md)
- [Development and testing](docs/development.md)
- [Verification notes](docs/verification.md)
- [Security policy and audit](SECURITY.md)

Built with Python, FastAPI, SQLite and vanilla JavaScript. [MIT licensed](LICENSE).
