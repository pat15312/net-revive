# Verification

Verified locally on 11 September 2026:

- Full automated suite: **73 passed**, including inside the Docker `test` stage on Linux AMD64 / Python 3.14.
- Ruff checks, frontend JavaScript syntax checks and installed Python dependency consistency passed.
- Production image `net-revive:local` built successfully.
- Production container startup verified with a read-only root filesystem, all capabilities dropped, UID 10001, persistent SQLite/key files and a healthy Docker healthcheck.
- Production Compose configuration validated from `.env.example`.
- Real-browser regression passed using the actual FastAPI endpoints and a mocked UniFi adapter: complete first-run setup, site/port discovery, group/operator creation, Admin routes, short-hold cancellation, keyboard restart, persisted cooldown, remembered operator, detailed history and mobile layout. No remote asset requests or JavaScript errors occurred.
- Official Ubiquiti port-action and device-port schemas were verified; see [API notes](unifi-api.md).

Scope limits: no live UniFi controller or physical switch was supplied, so real hardware was not contacted or power-cycled. The image was built and exercised locally on AMD64; the GitHub workflow is configured to build/publish both AMD64 and ARM64. No repository remote or registry owner was supplied, so the GHCR workflow has not been run against a remote repository and no image was published. Two upstream Starlette/AnyIO test-transport deprecation warnings are present; they do not fail tests.
