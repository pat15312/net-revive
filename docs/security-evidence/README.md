# Audit evidence

Assessment date: 12 September 2026. Baseline: `4e72365ae859c9da6f590f14eacbdbadd8ca7a21`.

- [Machine-readable scanner summary](scan-summary.json): exact local image identity, scanner/database metadata, dependency inventory, counts and SHA-256 references to raw local scanner outputs.
- [Image-advisory inventory and reachability review](image-advisories.md): includes unpatched base-image findings rather than suppressing them.
- [Compressed CycloneDX production SBOM](production-sbom.cdx.json.gz): generated from the final local production image by Grype's embedded Syft cataloger. Decompress with `gzip -dc production-sbom.cdx.json.gz > production-sbom.cdx.json`.
- [Security regression source](../../tests/test_security_audit.py) and [browser attack harness](../../tests/browser/security.cjs).

Before remediation, 22 of 23 initial security regression cases failed; one existing header case already passed. They demonstrated hostile/duplicate Host acceptance, an old-password login race, environment-key forwarding on origin changes, session churn, oversized HTTP/controller payloads, insufficient inventory/path/port validation, malformed CSRF handling, and missing headers on static/health responses. New regression cases were subsequently added for additional controls. Not every defense-in-depth change had a failing before-test.

Reproduction uses temporary databases and fake controllers only:

```bash
pytest -q
ruff check app tests
ruff check app --select S
bandit -r app
semgrep scan --config p/python --config p/javascript --metrics off --no-git-ignore app
pip-audit -r requirements.lock --disable-pip --no-deps
pip-audit -r requirements-dev.lock --disable-pip --no-deps
gitleaks git --redact
zizmor --offline .github/workflows
actionlint
docker build --target test -t net-revive:audit-test .
docker build --target production -t net-revive:audit-final .
grype net-revive:audit-final -o json
grype net-revive:audit-final -o cyclonedx-json
```

Scanner databases change over time; reruns can legitimately produce different advisory counts. Raw reports were retained in the local audit workspace outside version control; the repository contains sanitized summaries and the complete image advisory list. No real credentials or production databases were copied into this evidence.
