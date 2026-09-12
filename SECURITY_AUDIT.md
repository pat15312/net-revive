# NetRevive security assessment

**Assessment date:** 12 September 2026. **Pre-remediation baseline:** `4e72365ae859c9da6f590f14eacbdbadd8ca7a21`.

## 1. Executive summary

The assessment found exploitable browser-origin and session-revocation weaknesses, plus resource, credential-binding and supply-chain weaknesses. Remediation preserves the existing UI and ordinary household restart workflow. The entire tracked repository was reviewed before security changes; an initial threat model was recorded first. Tests used disposable databases, injected fake UniFi adapters and isolated loopback services. **No real UniFi power-cycle operation was performed.**

| Application/operational finding severity | Count | Outcome |
| --- | ---: | --- |
| Critical | 0 | No confirmed application finding |
| High | 3 | Two code defects fixed; one deployment transport risk remains open |
| Medium | 7 | Six fixed; dependency remediation completed for Python packages, with base-image advisory residuals |
| Low | 3 | Fixed/defense-in-depth controls added |
| Informational | 1 | Intentional LAN authority and first-run trust model documented |

**Open High operational risk — NR-13:** an HTTP deployment exposes administrator credentials/sessions to interception. Explicitly disabling UniFi certificate verification permits controller impersonation/API-key interception. Optional HTTPS guidance and private-CA support are provided, but the live deployment was not converted or reconfigured during this audit. Do not interpret the code fixes as resolving those deployment choices.

No additional exploitable Critical/High application-code issue was demonstrated after remediation within the tested threat model. This is not a claim of complete security, ASVS certification, exhaustive native-library reachability analysis, or a clean container vulnerability scan. The final local image still has **7 Critical and 58 High scanner matches** in inherited OS packages, alongside lower-severity matches; these were retained, investigated and separated from demonstrated application exploitability. See sections 7 and 9.

## 2. Architecture and trust boundaries

```text
Browser / arbitrary LAN client / remote malicious website
  -> HTTPBoundary: Host, framing, size, concurrency and request limits
  -> session lookup + CSRF + Origin/Fetch-Metadata checks
     -> public dashboard/status or group restart admission
     -> Admin dependency -> configuration CRUD / credential changes
  -> SQLite BEGIN IMMEDIATE -> durable target reservations and event snapshots
  -> fixed UniFi integration API: preflight GETs, then POWER_CYCLE POST

Background monitor -> bounded DNS / TCP / UniFi reads -> cached health/recovery state
Privileged deployment -> environment or mounted secrets, private database/key volume
GitHub source -> pinned actions/base/build tools -> candidate image + SBOM/provenance
  -> scan AMD64 and ARM64 -> promote the same digest to release/latest tags
```

The browser never supplies switch/port identities to the restart endpoint. Admin group configuration uses IDs of already-discovered database targets. The worker uses an immutable admission snapshot and records attempted dispatch before sending. Group and shared-target cooldowns remain durable across process restarts; ambiguous outcomes are not replayed automatically. Health monitoring does not trigger restarts.

Boundaries requiring separate protection: browser/device integrity; LAN transport; controller identity and privileges; host/volume read access; Docker daemon/root access; GitHub owner, branch/tag policies and registry publishing credentials. Encryption cannot protect a credential from a reader who has both the database and encryption key, or from a compromised running application.

## 3. Threat model

Protected assets are administrator authority, session/password confidentiality, the UniFi credential, correct PoE target selection, availability/lockouts, configuration/history integrity and published-image integrity.

Attackers include a compromised LAN/IoT device, ordinary dashboard user, arbitrary HTTP client, malicious remote website/rebinding domain, hostile controller response, host-file reader and supply-chain adversary. Administrator-configured destinations are privileged network-probe authority; they are not an unprivileged URL-fetch service. The audit nevertheless prevents stored credentials silently moving between configured origins.

Intentional product authority: anyone able to access the ordinary app can choose any configured name and request enabled restart groups. Names are attribution, not authentication. Browser hold-to-restart protects against accidental clicks, not scripts or replay after a legitimate cooldown. There is no claim of cryptographically attributable household actions. First-run setup trusts the first reachable claimant; deployers should isolate setup or provide a bootstrap password first.

## 4. Testing methodology

Guidance verified during the assessment:

- [OWASP ASVS 5.0.0](https://owasp.org/www-project-application-security-verification-standard/), [Top 10:2025](https://top10.owasp.org/2025/), and [API Security Top 10:2023](https://owasp.org/API-Security/editions/2023/en/0x00-header/). Relevant authentication, authorization, input/output, configuration, resource, dependency and exceptional-condition controls were assessed; no formal verification level is asserted.
- OWASP [CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html), [password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), [SSRF](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) and [cryptographic storage](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html) guidance.
- [FastAPI proxy guidance](https://fastapi.tiangolo.com/advanced/behind-a-proxy/), [Starlette middleware](https://starlette.dev/middleware/), [Python security considerations](https://docs.python.org/3/library/security_warnings.html), [Docker build practices](https://docs.docker.com/build/building/best-practices/), [Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/), and [GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use).

Manual review covered every tracked Python module, route/schema, template, JavaScript renderer/storage/event path, security-relevant CSS, database/backup logic, network integration, Docker/Compose file, workflow, dependency lock, test and document. The [complete route inventory](docs/security-routes.md) records methods, authority, validation, persistence, network behavior, output and common error/rate policy, including legacy-compatible API names/fields.

Automated work included pytest adversarial/functional/concurrency regressions; Chromium functional and attack tests; a real isolated HTTPS server with a generated private CA; Bandit; Semgrep Python/JavaScript rules; Ruff security rules; pip-audit runtime and development scans; redacted Gitleaks history/source scans; actionlint and zizmor; Docker builds/tests/runtime checks; Grype actual-image scans and CycloneDX inventory generation. Before-fix regression evidence and tool/database/image metadata are summarized in [evidence](docs/security-evidence/README.md).

Limitations: no live controller security testing, production traffic capture, real DNS-timing exploit against a household browser, ZAP/CodeQL run, automated iOS Safari test, host penetration test, or verification of GitHub account/organization protection settings. Rebinding tests exercised the hostile Host boundary and browser routing to loopback; modern browser private-network restrictions were not assumed as the application's defense.

## 5. Findings

### NR-01 — High — Arbitrary Host accepted, undermining the browser-origin boundary

**CWE-346, CWE-352. Location:** original `app/main.py:security_middleware`; now `app/http_security.py`.

A hostile hostname was accepted for pages and session issuance. A website whose DNS subsequently resolves to NetRevive could obtain a same-origin session/CSRF token and request an enabled restart group without the normal UI interaction. Exploitability depends on browser/network rebinding behavior; plain arbitrary-Host HTTP acceptance was reproduced. LAN intent does not make this safe.

**Fix:** reject unknown/ambiguous Host headers before sessions or database work. Only explicit DNS names and direct private/loopback IP literals are accepted. Host suffixes, userinfo, invalid ports, multiple Host headers and forwarded-host substitution are rejected. No wildcard CORS was introduced.

**Evidence:** `test_rebinding_host_cannot_obtain_session`, malformed/duplicate Host tests failed before the fix and pass after it; private-IP access remains tested. Chromium rebinding-style hostname routing returns 400 without CSRF. **Status: fixed.**

### NR-02 — High — In-flight old-password login survived password revocation

**CWE-362, CWE-613. Location:** `app/main.py:login`, `authenticated_response`, `change_password`.

A client knowing the old password could begin verification, wait while another administrator changed the password/revoked sessions, then obtain a fresh administrator session afterward. The verification and session insertion were separate transactions. A deterministic interleaving reproduced the post-revocation login.

**Fix:** recheck the exact stored password hash inside the write transaction that creates the authenticated session. Setup/password changes and session rotation now commit atomically. Existing anonymous/login tokens are revoked during rotation.

**Evidence:** `test_password_rotation_wins_against_inflight_old_login` failed before and passes after; existing password-change/session-fixation/logout tests pass. **Status: fixed.**

### NR-03 — Medium — Stored credential could be paired with a different controller origin

**CWE-200, CWE-367. Location:** `app/main.py:client_factory`, `app/admin.py:save_unifi`.

Controller settings and the encrypted key were read separately, allowing a concurrent authorized connection change to pair an old key with a new URL. Separately, environment-managed credentials bypassed the saved-origin change guard. A privileged editor or concurrent legitimate migration could send a credential to an unintended controller; ordinary clients could not change these settings.

**Fix:** origin/settings/key use one SQLite read snapshot. Environment/file-managed keys cannot silently follow a changed origin. Database-managed origin changes require newly supplied credentials. Redirects and environment HTTP proxies remain disabled.

**Evidence:** environment-key origin change failed before/pass after; `test_saved_key_and_origin_are_one_snapshot` deliberately interleaves a save and confirms matching old-origin/old-key use. Existing draft-key binding and no-redirect tests pass. **Status: fixed.**

### NR-04 — Medium — Unbounded HTTP/session allocation

**CWE-400, CWE-770. Location:** `app/main.py`, new `app/http_security.py`, `app/security.py`.

An arbitrary HTTP client could allocate a database session on every unknown path and send oversized bodies before schema validation. Sustained requests could consume memory/storage or monopolize work.

**Fix:** pre-parsing body/header/query limits, upload deadline, bounded active requests and bounded per-peer/global counters. Only page/session entrypoints allocate sessions; creation is throttled and storage capped at 1,024, evicting oldest anonymous records while preserving Admin sessions. Existing login/write/restart throttles remain. Uvicorn receives connection/parser/keepalive limits.

**Evidence:** oversized-body/session-churn/unknown-path regressions failed before/pass after; chunked-body and capacity-eviction tests pass. This bounds work, not volumetric LAN traffic or indefinite authorized event history. **Status: fixed within the documented capacity model.**

### NR-05 — Medium — Unbounded controller responses, pagination and fan-out

**CWE-400, CWE-770. Location:** `app/unifi.py`.

A compromised/malformed controller or impersonator when TLS verification is disabled could send huge JSON, endlessly paginated listings or large device inventories. Per-request timeouts alone did not bound aggregate work/memory.

**Fix:** stream and cap responses before JSON parsing; reject compressed controller bodies; cap/validate listing totals and duplicate IDs; apply listing/discovery deadlines; share four request slots across clients; process device batches immediately rather than retaining every raw response. Bound display names, ports and group target count; fail explicitly instead of silently truncating inventory.

**Evidence:** oversized-response/listing regressions failed before/pass after; malformed controller detail tests and existing timeout/error/partial-dispatch tests pass. Limits are listed in [operations](docs/security-operations.md). **Status: fixed.**

### NR-06 — Medium — Password work factor below current guidance

**CWE-916. Location:** `app/security.py`.

An attacker obtaining password hashes had a cheaper offline guessing target than current recommended parameters: legacy scrypt used N=16384/r=8/p=1. Random salts and constant-time comparison were already present; no plaintext/reversible administrator passwords were stored.

**Fix:** Argon2id, 19 MiB memory, two iterations, one lane, random 16-byte salt and 32-byte output. Legacy hashes remain verifiable and are upgraded on successful login; users do not need to reset passwords. Malformed/unsupported hash encodings fail closed. Login throttling bounds expensive work.

**Evidence:** legacy migration, successful/failed authentication, password change and container restart/login tests pass. **Status: fixed for new/upgraded hashes; dormant legacy hashes upgrade at next login.**

### NR-07 — Low — Equipment identities insufficiently validated at the adapter boundary

**CWE-20, CWE-22. Location:** `app/unifi.py:device`, `validate`, `power_cycle`.

URL quoting does not escape standalone dot segments. Malformed controller IDs could therefore alter path interpretation. A corrupted target whose `port_id` differed from `port_number` could validate one port and dispatch another. No ordinary API route let a user write these fields; this is defense in depth against malformed upstream/stored data, not a demonstrated ordinary-user target-substitution exploit.

**Fix:** accept bounded opaque alphanumeric/hyphen IDs only; check returned device identity, port types/ranges/uniqueness/PoE shape; require matching numeric port identity at both validation and dispatch.

**Evidence:** dot/path-like identifier and mismatched-port regressions failed before/pass after, with zero POSTs for invalid targets. Existing exact official POWER_CYCLE shape tests pass. **Status: fixed.**

### NR-08 — Low — Database permissions tightened only after creation

**CWE-732. Location:** `app/database.py`, `Dockerfile`.

Database creation initially relied on the process umask before a later chmod. This was a brief local-file permission weakness; the audit did not demonstrate exposure of a real secret during that window.

**Fix:** private file opening without symlink following, mode 0600 before SQLite access, restrictive new data directories, mode 0700 `/data` in the image. Runtime application files are root-owned/readable, with the read-only root filesystem enforced by Compose. Backups/key creation already used private exclusive files.

**Evidence:** first-open and WAL/SHM permission tests; backup/key tests; non-root container storage/restart smoke tests. **Status: fixed/defense in depth.**

### NR-09 — Low — Inconsistent response hardening and malformed-CSRF handling

**CWE-20, CWE-693. Location:** original `security_middleware`; `HTTPBoundary`.

Static/health responses and early failures skipped the common security headers. A non-ASCII CSRF header caused a comparison exception instead of a controlled denial. Duplicate session cookies had ambiguous selection behavior.

**Fix:** outer response policy covers static, health, errors and early rejection; CSP remains restrictive without unsafe-inline/eval, frame denial is explicit, nosniff/no-referrer/no-store and Permissions-Policy are consistent. CSRF compares encoded bytes, duplicate security headers/cookies are rejected and failures/logs use bounded safe messages. Failed logins and denied restart requests are logged without secrets.

**Evidence:** initial header/CSRF/duplicate-cookie cases failed before/pass after; Chromium framing attack blocked; sensitive-login-log test passes. **Status: fixed.**

### NR-10 — Medium — Rejected second worker could change bootstrap authentication

**CWE-362. Location:** `app/main.py:create_app/lifespan`.

With shared storage and a different bootstrap password, a second process could alter authentication before the single-process lock rejected it. This required deployment/process-start authority, not an HTTP-only attacker, but could invalidate or replace the running instance's password unexpectedly.

**Fix:** apply bootstrap password changes only after acquiring the exclusive process lock. Multiple workers/replicas per database remain unsupported and fail startup.

**Evidence:** `test_second_worker_cannot_change_bootstrap_password` verifies rejection without changing the original password/session. **Status: fixed.**

### NR-11 — Medium — Mutable build inputs and incomplete publication gates

**CWE-829, CWE-494. Location:** `Dockerfile`, dependency locks, `.dockerignore`, `.github/workflows/ci.yml`.

Action tags/base tags were mutable; dependency files lacked artifact hashes; checkout credentials persisted; context exclusion did not cover every local deployment directory. An upstream tag rewrite or contaminated build context could affect a privileged build/published image. No actual compromise or secret-bearing published layer was found.

**Fix:** pin action commits and base/emulation/BuildKit/SBOM images; hash-lock dependencies; narrow Docker context to explicit inputs; disable checkout credential persistence and package-manager caching; preserve least-privilege permissions and PR/publish separation. Build a candidate with SBOM/provenance, scan both architectures, then promote its digest without rebuilding. Release-tag commits must belong to main. Automatic latest-tag generation is explicitly disabled so tagging an older release does not implicitly replace latest; the explicit latest tag belongs only to main pushes. Weekly Dependabot updates are configured.

**Evidence:** actionlint/zizmor clean after remediation; initial zizmor findings reviewed; image history/context reviewed and redacted secret scans clean. GitHub account/branch enforcement is not verifiable from code. **Status: code/workflow hardening fixed; external governance remains operational.**

### NR-12 — Medium — Vulnerable dependencies and inherited image advisories

**CWE-1104. Location:** dependency locks and Python Debian base image.

pip-audit identified 11 advisory records for `cryptography==46.0.5` and a duplicated advisory record for development-only `pytest==9.0.2`. Not all affected cryptography APIs are used by NetRevive: Fernet is the relevant application use; controller TLS uses Python ssl. The audit did not demonstrate those advisory exploits through NetRevive routes.

**Fix:** reviewed [cryptography release changes](https://cryptography.io/en/latest/changelog/) and upgraded to 50.0.1; pytest upgraded to 9.0.3; regenerated hash locks and reran compatibility tests. Runtime and development pip-audit scans are clean. The final image retains unpatched inherited OS matches, with explicit reachability review and a scan gate for fixable High/Critical issues.

**Evidence:** exact versions/advisory IDs and final image inventory in [scanner summary](docs/security-evidence/scan-summary.json) and [image review](docs/security-evidence/image-advisories.md). **Status: Python packages fixed; inherited-image residuals tracked, not suppressed or claimed eliminated.**

### NR-13 — High — HTTP or unverified controller TLS allows credential interception

**CWE-319, CWE-295. Location:** deployment transport, `COOKIE_SECURE`, controller `verify_tls`.

A network observer can steal administrator credentials/sessions over plain HTTP. An active network attacker can impersonate a controller when its certificate is not verified and receive the UniFi key. These are realistic LAN threats. The known deployment used HTTP and had explicitly disabled controller verification; production was not probed or modified to re-check these settings.

**Remediation supplied:** optional HTTPS/proxy instructions, explicit proxy trust and Host rules, secure-cookie configuration, mounted-secret support and `UNIFI_CA_FILE` with a real isolated TLS trust test. Default UniFi verification remains enabled; disabling it is never silent. Simply forcing Secure cookies on existing HTTP would break the deployment without providing HTTPS.

**Status: OPEN operational decision.** Configure trusted HTTPS for browser access and a trusted/matching controller certificate before considering this risk resolved. This requires deployment/certificate decisions and is deliberately not represented as an application-code fix.

### NR-14 — Informational — LAN restart authority, first-run claim and attribution are intentional

**CWE-306 where stronger authentication is required by a different deployment model. Location:** setup/dashboard/restart product model.

A reachable client can claim an uninitialized instance or select another configured user's name. After setup, any ordinary session can request enabled groups without a password; replay after cooldown uses current membership. These are explicit household product choices, not administrator authorization. A compromised LAN device can therefore cause disruption within configured groups, and log names are not proof of identity.

**Response:** document firewall/VLAN/VPN controls, isolate first setup/use bootstrap credentials, retain CSRF/lockouts/current-membership resolution and do not add unnecessary household sign-ins. **Status: intentional residual; deployments needing authenticated restart authority require a product/architecture decision.**

## 6. Security controls confirmed

- Every privileged route rejects ordinary sessions server-side, including direct CRUD, history, password, discovery, setup-completion and reordering calls. Missing/forged/expired sessions and alternate methods do not confer Admin authority.
- Setup has one atomic successful claimant. Login rotates session/CSRF; logout and password change revoke prior authority. Cookies are HttpOnly, SameSite=Strict and eight-hour absolute lifetime; Secure is deployment-controlled.
- Restart admission is transactional; concurrent same/overlapping-group requests cannot both reserve shared targets. Disjoint groups remain independent. Disabled/deleted/wrong-site targets and browser-supplied extra target fields are rejected. Admin hardware changes during dispatch are blocked.
- Restart replay during lockout is denied; after expiry it resolves current membership. Snapshots preserve history rather than authorizing future requests. Crash/partial/unknown failures retain cooldown and do not retry POSTs. An injected database write failure produced no power-cycle call.
- Stored XSS payloads in title, names, labels and group content remained text in Chromium. Template autoescaping and explicit JavaScript escaping/textContent were reviewed. No dynamic shell execution, unsafe deserialization, user-supplied SQL identifiers or general UniFi command proxy exists.
- Controller requests use fixed HTTPS integration paths, no redirect/proxy credential forwarding, bounded work and sanitized failures. Generated private-CA TLS fails without trust and succeeds with explicit trust.
- Debug/OpenAPI paths and data/source traversal requests do not expose files. Configuration responses never return stored API keys/hashes. Backup creation is private/exclusive, and database/key persistence works under non-root read-only Docker constraints.

## 7. Dependency and image status

Final runtime and development pip-audit scans: **zero known Python dependency vulnerabilities** with the queried advisory database. Production excludes pytest/Ruff/Semgrep/scanners. New cryptography functionality remained compatible with credential encryption and authentication tests.

Grype 0.118.0 scanned the actual local production image, not just requirements. Final raw package/advisory matches: **7 Critical, 58 High, 46 Medium, 7 Low, 44 Negligible, 8 Unknown** (170 matches, 85 unique advisory IDs). These include duplicated source-package matches across installed binary packages. **No fixable High/Critical match remained.** That statement does not mean the image is free of vulnerabilities.

Examples checked against the distribution tracker: [glibc scanf issue](https://security-tracker.debian.org/tracker/CVE-2026-5450), [32-bit Perl regex issue](https://security-tracker.debian.org/tracker/CVE-2026-8376), [SQLite FTS5 issue](https://security-tracker.debian.org/tracker/CVE-2026-11822), [zlib nonblocking write issue](https://security-tracker.debian.org/tracker/CVE-2026-85091). The app does not invoke the affected scanf/Perl/FTS5/gzwrite operations; privileged utility paths are restricted by the container configuration. These are reachability observations, not universal exploitability proofs. Some fixes listed by broad Python CPE matching are prereleases; the audit did not replace stable Python with a release candidate solely to remove a scanner label.

The [full advisory table](docs/security-evidence/image-advisories.md), [CycloneDX SBOM](docs/security-evidence/production-sbom.cdx.json.gz), exact image identity and scanner database metadata are preserved. Refresh the pinned base and reassess as vendor patches become available. AMD64 runtime was exercised locally; ARM64 is built/scanned by the publication workflow, not claimed as a local hardware test.

## 8. CI/CD and supply-chain status

PRs run tests with read-only contents permission; they do not publish. Publishing requires a push and package-write authority, with release commit ancestry checked against main. Inputs are passed through environment variables rather than interpolated into shell programs. Checkout credentials/caches are not retained for later untrusted use. Candidate images receive SBOM and BuildKit provenance; both architectures are scanned before version/latest tag promotion from the same digest. Failed candidate scans do not update release tags.

The gate blocks **fixable** High/Critical advisories; all other results are printed for review, not ignored as “safe”. Candidate tags are not releases. Signed identity verification was not introduced: provenance/SBOM availability improves inspection but is not a substitute for independent signing, protected branches/tags or account security. Immutable digests provide stronger selection guarantees than mutable `latest`, `sha-*` or version-tag names. GitHub-owned runner/tool downloads and registry services remain supply-chain trust dependencies.

The metadata action [automatically adds latest for release-tag events](https://github.com/docker/metadata-action#latest-tag) unless its flavor disables this; the final review made that behavior explicit rather than relying only on the raw latest-tag condition.

Repository-level private reporting, branch protections, required checks/reviews, tag immutability, owner MFA and GHCR administrative controls could not be confirmed with available access. The branch-protection API returned 403 (integration lacks access); the private-reporting endpoint was not available through the connector. Recommended settings are documented rather than falsely asserted enabled.

## 9. Residual risks

- **NR-13 remains High until deployment transport is hardened.** The audit did not deploy a certificate or change the live UniFi trust setting.
- Authorized LAN restart capability and spoofable selected names are intentional. Host validation is not a client-IP firewall. First-run setup can be won by the first reachable client.
- Host/container compromise or access to database plus key defeats application-level encryption. Bootstrap environment variables and plain Compose secret files remain readable by privileged host/container administrators.
- Unpatched base-image advisories remain. The absence of demonstrated route reachability is not a promise about all native dependency paths or future changes.
- Rate limits can themselves temporarily deny legitimate users under sustained attacks; network floods and storage exhaustion require host controls. Event history is retained indefinitely. Stable clock/local storage are required; forward wall-clock jumps and old backups can alter effective lockouts.
- Restored backups can contain stale sessions/reservations. Restore only trusted backups under restricted access and rotate credentials if exposure is suspected. Physical access, compromised user devices, broad UniFi API-key privileges and compromised GitHub publishing accounts remain outside what these code controls can solve.

## 10. Recommended operational configuration

Use the shipped non-root/read-only/capability-dropped deployment with a restricted LAN listener/firewall, one process per database, reliable local storage, protected backups and monitored disk usage. Configure exact local hostnames, trusted browser HTTPS, `COOKIE_SECURE=true` when HTTPS is actually used, explicit proxy IP trust and verified UniFi TLS with a matching certificate/private CA. Prefer mounted bootstrap secret files over long-lived plaintext environment entries. Keep UniFi key privileges no broader than required by the installed controller's supported permission model.

Follow [operational security](docs/security-operations.md) for concrete settings and migration instructions. Preserve the volume during Portainer updates. Pin release digests when reproducibility matters; do not deploy candidate tags. Review Dependabot changes and enable repository/account protections separately.

## 11. Final verification

**Audited final code/workflow commit:** `2aa8de60d449756f6c422e90951dafeee2206eb5`. Application remediation was introduced in `d0882ff1124f433fe4381fc12b87647e5313b1c6` (also release `v0.1.0`); the later commit changes only publication rules and audit documentation. Production source/assets were individually hashed and matched the tested container. A final workflow follow-up disables automatic latest-tag generation on release-tag events; production application code is unchanged. The exact local image, dependency versions, database timestamps and scanner counts are also in [scan-summary.json](docs/security-evidence/scan-summary.json).

**Locally exercised image:** `net-revive:audit-final`, Docker image index ID `sha256:12822adf345dc94a012792d98ee4a192a28686d3c55c99494b34222cbbc277b2`, AMD64, 245,514,009 bytes. Registry publication evidence is recorded separately because build provenance and platform manifests give it a different digest.

- Functional/security pytest suite: **173 passed** locally with fake equipment (85 pre-audit tests plus 88 added cases); GitHub runner and Docker test-stage runs also passed all 173 tests (two existing dependency deprecation warnings).
- Chromium functional suite and browser attack harness passed; no production controller was contacted.
- Bandit and Ruff security checks: clean after replacing fixed-table SQL interpolation with explicit query mappings (initial findings were reviewed false positives, not claimed SQL injection exploits).
- Semgrep: 219 Python/JavaScript rules, 15 source targets, zero findings.
- actionlint and zizmor: zero findings after remediation.
- Gitleaks: 15 pre-audit commits scanned with redaction, no detected secrets; final source scan clean. The staged-diff scan flagged two SHA-256 evidence-file checksums as generic API keys; both were manually confirmed false positives. All 10 exported production image layers (6,124 regular files) and image configuration were scanned with redaction, with zero findings. This is detection evidence, not proof that every possible secret format would be recognized.
- Final local container ran as UID/GID 10001, with zero capabilities, no-new-privileges, read-only code, private persistent database/key, no development tools, successful setup/login/settings and successful restart/persistence checks. Its network was disabled throughout runtime smoke testing.
- One introduced file-permission issue was found by the production smoke test and corrected before final acceptance; local source modes no longer prevent non-root reads in the image.
- Raw scan/test outputs remain in the local audit workspace; sanitized summaries, advisory inventory, SBOM, regressions and reproduction instructions are versioned. All changes were reread for security and accidental secret exposure.

### Publication verification

[Initial audited-build workflow](https://github.com/pat15312/net-revive/actions/runs/34662957803) passed both test and publish jobs. It ran 173 tests on the runner and 173 in Docker, built AMD64/ARM64, scanned each architecture, and promoted index `sha256:c2ab615fa48cb25fff0a220dac18521bbdb8b567d516e3c49e80ba4a3d52a60e`. Registry inspection confirmed separate SPDX SBOM and SLSA provenance v1 attestations for both platforms. This is build metadata, not a claim of independently signed publisher identity.

[Versioned release workflow](https://github.com/pat15312/net-revive/actions/runs/34663198758) passed tests and both-platform scans. Published `ghcr.io/pat15312/net-revive:v0.1.0` resolves to `sha256:072ab26382446a1d1042a579f4fda7e60602bdc1954e93e89899b53484b14822`; its application code matches the audited implementation. Neither this release nor the main build was deployed to the live Pi during the audit.

[Final code/workflow verification](https://github.com/pat15312/net-revive/actions/runs/34663290845) passed both jobs for `2aa8de60d449756f6c422e90951dafeee2206eb5`, including the complete test suite and both architecture scans. Final main image index: `sha256:db8eceb3468644a79a0fdcc8c5c7d39bb20fdba6aac3dd13e46ff7598027799a` (`ghcr.io/pat15312/net-revive:sha-2aa8de6`, also promoted to `latest`). The subsequent commit containing this final evidence record changes documentation only; it intentionally does not rebuild or replace the tested image.
