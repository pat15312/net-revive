# Verification

Status as of 12 September 2026:

- **85 automated tests passed** locally. Tests use mocked UniFi, DNS and internet interactions.
- The browser regression passed against the real FastAPI endpoints and a mock UniFi adapter. It covers setup, administration, port discovery/editing, concurrent user/group ordering, hold-to-restart behaviour, cooldowns, user selection, restart history, themes and desktop/mobile layouts. Retired hostname-validation tests were replaced with coverage for removing the setting.
- Ruff and JavaScript syntax checks passed. GitHub Actions also passed the Python suite and Docker test stage, then published Linux AMD64 and ARM64 images.
- The production container was exercised locally on AMD64 with a read-only filesystem, dropped capabilities, UID 10001 and persistent database/key storage.
- The maintainer deployed NetRevive on a Raspberry Pi through Portainer and reported a successful functional test with their UniFi installation. This is a user-reported hardware test, not a compatibility claim for every controller, switch or firmware version.

See the [latest workflow runs](https://github.com/pat15312/net-revive/actions) for build results and the [UniFi API notes](unifi-api.md) for endpoint compatibility. Browser automation uses Chromium; iOS Safari behaviour has also informed fixes through user feedback, but is not covered by the automated suite.
