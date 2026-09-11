# Development

```bash
python3.14 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.lock
ruff check app tests
pytest -q
node --check app/static/app.js
node --check app/static/theme.js
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8080 --no-access-log
```

Development defaults to `data/netrevive.db`, ignored by Git. `requirements.txt` records direct dependencies; `requirements.lock` pins the entire runtime closure; `requirements-dev.lock` pins test dependencies as well. Update these together and rerun both native and Docker tests.

Tests mock all UniFi, DNS and internet interactions. They cover first-run setup, authentication, configuration, many-to-many membership, multi-switch identity, validation, admission races, cooldown persistence, interrupted dispatch, partial/complete failure, official API request shapes, stable recovery and immutable history. The production container does not contain tests or any simulated controller. Real-hardware compatibility must be checked on the deployment's installed UniFi version before assigning operational equipment.

NetRevive is distributed under the [MIT License](../LICENSE).

For end-to-end UI checks, see the [browser regression guide](../tests/browser/README.md).

## Local Docker build

```bash
cp .env.example .env
docker build --target test -t net-revive:test .
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

## Publishing images

The GitHub Actions workflow runs Ruff, pytest, JavaScript syntax checks and the Docker test stage. Pull requests test without publishing. Pushes to `main` publish `latest` and a commit-derived tag; `v*` tags publish matching version tags. Images support Linux AMD64 and ARM64.

Forks publish under their own GitHub owner. The workflow requires package-write permission, and the GHCR package must be public for anonymous pulls. Set `GHCR_OWNER` in `.env` to your lowercase owner name when using your own images.
