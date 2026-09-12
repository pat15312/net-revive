# Audited HTTP surface

All HTTP routes pass `HTTPBoundary`: exact allowed host or private IP, duplicate-header/cookie checks, 16 KiB headers, 8 KiB query, 64 KiB body/10-second body deadline, 32 in-flight requests, 600 requests per peer/minute and 2,400 globally/minute. Unrecognized hosts return 400 before allocating sessions. No CORS middleware, WebSockets, method override, uploads, arbitrary proxy or command endpoints exist.

State-changing routes require a valid session CSRF header, same Origin when supplied, no `Sec-Fetch-Site: cross-site`, and 60 writes per peer/minute. Missing/invalid CSRF returns 403 before route execution. GET does not change business configuration, although page/session reads may allocate an anonymous session. Models reject extra fields. All inputs below are JSON unless specified. Unauthorized Admin access returns 401; validation 422; absent records 404; conflicts 409; throttling 429; database failures 503; sanitized controller failures 502 (setup completion uses 422). No submitted secret values or raw controller bodies are returned.

| Method | Path | Authority / inputs | Database / effects | Network / response |
| --- | --- | --- | --- | --- |
| GET | `/`, `/admin`, `/setup` | Public; no input | Read title; session allocation if needed | Local HTML shell; no configuration/secret embedded |
| GET | `/static/{path}` | Public; fixed directory, traversal checked by StaticFiles | None | Bundled JS/CSS/favicon; GET/HEAD only |
| GET | `/healthz` | Public; no input | `SELECT 1` | Generic availability only; no outbound checks |
| GET | `/api/session` | Public | Read password/setup flags and session | CSRF, admin flag, setup state; no password/hash |
| POST | `/api/setup` | Unclaimed installation; password 12–256 characters | Atomically create hash and rotate session; only first claimant succeeds | No outbound; new CSRF and session cookie; global 5/5min |
| POST | `/api/login` | Password 1–256 characters | Verify hash, recheck credential generation, upgrade legacy hash, atomically rotate session | No outbound; new CSRF/cookie; 5/peer/5min and 30/global/5min |
| POST | `/api/logout` | Current session + CSRF | Revoke current session | No outbound; delete cookie |
| PUT | `/api/admin/password` | Admin + current and new password | Verify current; atomically replace hash/revoke Admin sessions/issue replacement; environment-managed password cannot change here | No outbound; 5/global/5min |
| GET | `/api/status` | Public | Read enabled groups, user names, recent events and cached health | Limited dashboard state; no controller address/key or device topology |
| POST | `/api/groups/{group_id}/restart` | Ordinary session; configured user name; integer group ID | Atomically validate and reserve current group/targets, persist snapshots; deny disabled/deleted/wrong-site/locked targets | Background fixed UniFi preflight and POWER_CYCLE only; event ID; 10/peer/min |
| GET | `/api/admin/config` | Admin | Read settings/users/groups/targets | Full administrative inventory, credential-present flags only |
| PUT | `/api/admin/general` | Admin; title ≤80, valid timezone ≤100 | Save general settings | No outbound; success |
| PUT | `/api/admin/monitoring` | Admin; bounded timing/thresholds, 2–10 DNS names and IP/port destinations | Save monitoring configuration | Later background DNS/TCP probes; no payloads sent to TCP endpoints |
| PUT | `/api/admin/unifi` | Admin; HTTPS origin ≤2048, fixed prefix, site ID, TLS choice, optional key ≤4096 | Guard in-flight dispatch; save origin/site/config; encrypt new key; invalidate discovery on origin/site change | No immediate outbound; stored/environment key cannot silently follow changed origin |
| POST | `/api/admin/unifi/test` | Admin; optional draft UniFi settings | Consistent saved origin/key read; no configuration write | Bounded read-only site listing; key is origin-bound |
| POST | `/api/admin/unifi/discover` | Admin; no input | Check unchanged settings and no dispatch; upsert inventory preserving labels/membership/lockouts | Bounded site/device GETs; target count only |
| PUT | `/api/admin/targets/{target_id}` | Admin; integer ID, label ≤100, enabled bool | Guard dispatch; edit existing target label/availability policy | No outbound; cannot edit hardware identity |
| POST | `/api/admin/operators` | Admin; unique name ≤80, optional bounded legacy order | Insert user, append order by default | No outbound; new ID |
| PUT | `/api/admin/operators/{operator_id}` | Admin; ID/name/order | Update existing user; history unchanged | No outbound |
| DELETE | `/api/admin/operators/{operator_id}` | Admin; ID | Delete user; history unchanged | No outbound |
| POST | `/api/admin/order/{collection}/{item_id}` | Admin; collection enum users/groups, integer ID, up/down enum | Atomic reorder using fixed SQL mapping | No outbound |
| POST | `/api/admin/groups` | Admin; name/button ≤80, description ≤500, 1–256 unique discovered target IDs, timing/mode | Guard dispatch; validate site/PoE/enabled/availability; insert group/membership | No outbound; new ID |
| PUT | `/api/admin/groups/{group_id}` | Admin; same schema | Guard dispatch; replace validated membership; history and target locks retained | No outbound |
| DELETE | `/api/admin/groups/{group_id}` | Admin; ID | Guard dispatch; delete group, not target lockouts/history | No outbound |
| POST | `/api/admin/setup/finish` | Admin; no input | Recheck unchanged settings and valid enabled groups/users; mark setup complete | Read-only live discovery; no power cycle |
| GET | `/api/admin/history?offset=N` | Admin; nonnegative integer offset | Read 50 event snapshots/results | Detailed historical topology, no keys; bounded page size |

`/api/admin/operators` remains the internal API name for compatibility; UI terminology is “Users”. Optional `display_order` and ignored `confirm_targets` remain accepted for older clients; neither bypasses authorization or target checks. Unknown/debug paths return 404 and unsupported methods 405. Trailing-slash redirects do not add routes or authorization bypasses.
