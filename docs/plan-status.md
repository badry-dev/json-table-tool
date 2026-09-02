# Planned Points — Consolidated Status

**Date:** 2026-09-02
**Shipped version:** `Config.APP_VERSION = '1.2.0'` (CHANGELOG entry dated 2026-08-21)

Single index of every point planned across the four planning documents:

- `docs/roadmap-v1.2.md` — Phases 0–5, decisions D1–D6
- `docs/security-review-v1.2.md` — findings F1–F17
- `docs/performance-review-v1.2.md` — findings P1–P13, perf budget §4
- `docs/code-health-final.md` — 2026-05 review: top-10 issues, quick wins, larger refactors
- `docs/export-budget-v1.2.md` — how `MAX_EXPORT_CELLS` was derived

Status is against the code in this repository, not against the CHANGELOG's own
claims: every "Done" line below was checked against `config.py`, `routes.py`,
`helpers.py`, `security.py`, `static/js/app.js`, `Makefile`, `.github/workflows/ci.yml`
and `requirements*.txt`.

---

## Section 1 — Done

### 1.1 Security findings (F1–F17)

| ID | Point | Where it landed |
|---|---|---|
| F1 | CSV/XLSX formula injection (Critical) | `helpers.sanitize_cell` / `is_formula_trigger` for CSV/TSV/XLSX; XLSX pins `data_type='s'`; JSONL/Markdown deliberately exempt |
| F2 | 7 dependency CVEs | Flask 3.1.3, requests 2.33.0, gunicorn 22.0.0, openpyxl 3.1.5; pytest moved out of the runtime file into `requirements-dev.txt`; `pip-audit -r requirements.txt` runs in CI |
| F3 / F9 | Credential leakage into logs; API JSONL `ValueError` → 500 | Fixed log string with no interpolation; JSONL parse failure returns 400 |
| F4 | User-controlled outbound header name | `routes.is_allowed_outbound_header` — strip + lowercase, then explicit allowlist |
| F5 | Security-header gaps | HSTS on secure requests, `Permissions-Policy`, COOP, CORP; CSP gained `object-src`, `base-uri`, `frame-ancestors`, `form-action`, `upgrade-insecure-requests` |
| F6 | SSRF: blocking DNS, no port restriction | Bounded resolver pool with admission control (`API_DNS_*`); `API_ALLOWED_PORTS` default `80,443,8443` |
| F7 | Default SECRET_KEY accepted in production | `is_production()` fail-fast in the app factory; `env_int()` names the mistyped variable |
| F8 | Recursion-depth DoS | `extract_table_data` depth cap; `RecursionError` → 400 `JSON nesting too deep` |
| F10 | 413 returned HTML | JSON handlers for 413/500/404 |
| F11 | No `Cache-Control: no-store` on data responses | `security.NO_STORE_ENDPOINTS` |
| F12 | Rate limiting ineffective behind a proxy | Opt-in `TRUST_PROXY=1` → `ProxyFix` with exactly one hop; key derived after ProxyFix |
| F13 | Upload extension/content-type unchecked | `routes.validate_upload` |
| F14 | Plain-HTTP credential exposure | Docs-only remediation: HTTPS stated per deploy path; `upgrade-insecure-requests` in CSP |
| F15 | `/health` version disclosure | Kept on by default, gated by `HEALTH_REVEAL_VERSION` |
| F16 | Cookie hardening | `HttpOnly`, `SameSite=Lax`, `Secure` tied to `APP_ENV=production` |
| F17 | Documentation drift | Candidates-handshake references replaced with the tree picker; MIT → GPL-3.0 |

### 1.2 Performance findings (P1–P13)

| ID | Point | Where it landed |
|---|---|---|
| P1 | Uncompressed `/process` responses | In-repo gzip middleware (D1), no new dependency; honours `Accept-Encoding` q-values; skips streamed/bodyless/already-encoded responses |
| P2.2 / P5 | Preview mutation, unbounded nested rendering | `helpers.preview_truncate` returns a capped **copy**; client caps at 20 keys / 20 items / 500 chars |
| P3 | XLSX fully buffered in memory (High) | Diskless normal-mode workbook + `MAX_EXPORT_CELLS` (measured, default 250 000); CSV/TSV generator-streamed and uncapped; 400 rather than truncation |
| P4 | Eager tree-picker build | Lazy children on first toggle, per-level and total node caps |
| P6 | No static cache headers | `STATIC_MAX_AGE` (86 400) with `?v=APP_VERSION` URLs |
| P7 | Blocking DNS in the request path | Shared bounded resolver pool (shared with F6) |
| P8 / P12 | Double column scan; multi-copy memory | `flatten_rows` does one pass; API path decodes the `bytearray` without an intermediate copy |
| P9 | gunicorn timeout vs `API_FETCH_TIMEOUT` | `--timeout 60` everywhere; the invariant is now enforced at startup |
| P10 | Dead code `find_candidate_arrays` | Removed with its four tests (D2) |
| P11 | Hardcoded "25" preview badge | `/process` returns `preview_limit` |
| P13 | Client-side CSV/TSV string building | Chunked Blob builders |

### 1.3 Roadmap phases

- **Phase 0 — Foundations.** Dependency pins, `requirements-dev.txt`, `.github/workflows/ci.yml`, `pyproject.toml` (ruff + pytest), ruff clean, GPL-3.0 correction, `autoDeployTrigger: checksPass`, dead-code removal.
- **Phase 1 — Security.** All 15 tasks (1.1–1.15); see F-table above.
- **Phase 2 — Performance.** All 10 tasks (2.1–2.10), including the rate-limit topology guard: `RATELIMIT_STORAGE_URI` is configurable, `WEB_CONCURRENCY` is the single source of truth for workers, `APP_REPLICAS` mirrors `numInstances`, and production refuses to start on `memory://` above one worker × one replica.
- **Phase 3 — Refactor.** `_load_input` / `_select_table_data` extracted, `process_json` reduced, `openpyxl` imported at module top, `preview_limit` returned, type annotations added to `helpers.py` and `security.py`.
- **Phase 4 — Features.** 4.1 load more / load all with a 50 000-row DOM guard, 4.2 row filter, 4.3 JSONL + Markdown exports, 4.4 column visibility, 4.5 `#path=` deep links, 4.7 `/health/live` + `/health/ready`, 4.8 in-page About modal and keyboard-accessible export dropdown. (4.6 is not done — see Section 2.)
- **Phase 5 — Docs/DX.** `MEMORY.md`, `CLAUDE.md`, `AGENTS.md`, `README.md` synced; `.env.example`; `Makefile`; `CHANGELOG.md`; version bumped to 1.2.0.

### 1.4 Decisions closed

| ID | Decision |
|---|---|
| D1 | gzip via in-repo middleware, not `Flask-Compress` |
| D2 | `find_candidate_arrays` deleted in Phase 0, before the depth-guard work |
| D3 | Proxy trust is opt-in via `TRUST_PROXY`, off by default |
| D5 | Port allowlist adopted, default `80,443,8443` |
| D6 | Exports stay diskless and memory-bounded: normal-mode workbook + measured cell budget; `write_only` and `SpooledTemporaryFile` both rejected, each on its own grounds |

### 1.5 Code-health review (2026-05) items now closed

Top-10 issues 1, 2, 3, 4, 5, 7, 8, 9, 10 are done (CI, CVEs, dev/prod dependency
split, ruff, `process_json` complexity, preview badge, LICENSE, `.env.example`,
depth guard). Quick wins 1–8 are done. Larger refactors 7.1, 7.3, 7.4 and 7.5 are
done; 7.2 is partial (see Section 2).

### 1.6 Measurement work

`MAX_EXPORT_CELLS = 250 000` is a measured number, derived by the two-fresh-worker
`ru_maxrss` protocol recorded in `docs/export-budget-v1.2.md`, with a confirming
point re-run at the shipped value.

---

## Section 2 — Pending / Planned

### 2.1 Open decision

- **D4 — opt-in HTTP Basic Auth gate (roadmap 4.6).** Still unresolved; needs
  maintainer sign-off. Scope if approved: `APP_BASIC_AUTH_USER` / `APP_BASIC_AUTH_PASS`
  → `before_request` 401 with constant-time compare and `WWW-Authenticate`, off by
  default, no persistence. Nothing else depends on it. The roadmap's own
  recommendation is to approve. No `BASIC_AUTH` code exists in the repository today.

### 2.2 Known limitation awaiting a decision

- **JSONL export is not a faithful copy of the input document.** Roadmap 4.3 called
  it "lossless — original values". Shipped behaviour: values are written verbatim
  (the security-relevant half), but over the server's *flattened* projection, so
  `{"tags": [1,2]}` exports as `"tags": "[1, 2]"` and `{"meta": {"role": "x"}}` as
  `"meta.role": "x"`. Fixing it means shipping the original rows alongside the
  flattened ones, doubling the payload and client memory that P2/P12 exist to
  reduce. Explicitly flagged for a maintainer decision, not resolved either way.

### 2.3 Accepted exposures, documented rather than fixed

- **Unbounded DNS teardown (F6.1 / P7 residual).** `getaddrinfo` exposes no timeout
  and cannot be cancelled. `API_DNS_TIMEOUT` bounds only the caller's wait; a pool
  thread stays occupied until the platform resolver returns, and interpreter exit
  can still block on it — realistically tens of seconds with glibc defaults. A
  killable subprocess resolver is the documented escalation and remains out of v1.2
  scope. Best-effort narrowing where the deployment allows: pin
  `options timeout:2 attempts:1` in the container's `resolv.conf`.
- **DNS rebinding (SSRF residual).** Mitigated by `allow_redirects=False` and
  documented in `routes.py`. Escalation path if the threat model changes from
  internal tool to public service: a custom `HTTPAdapter` that resolves once and
  passes the IP with an explicit `Host` header.

### 2.4 Carried-over engineering work

- **Type annotations (code-health 7.2, roadmap 3.5) — partial.** `helpers.py` and
  `security.py` are annotated. `routes.py` and `config.py` have no annotated
  signatures, and `mypy` is not in `requirements-dev.txt`, `pyproject.toml`, the
  `Makefile`, or CI. The roadmap deliberately marked mypy optional and skipped
  strict mode; the remaining work is the two unannotated modules plus a mypy
  configuration if it is wanted.
- **Perf budget verification (performance review §4).** The XLSX row of the budget
  was measured. The rest of the table — `/process` transfer size ≤ 2–4 MB,
  `/process` p95 ≤ 3 s, `/process` peak-RSS delta ≤ 50 MiB, tree-picker open
  ≤ 500 ms on a 10 MB payload — is defined but has no recorded run. No perf test
  gates CI (`pytest-benchmark` was deferred by decision), so these stay manual.
- **Measurement harness is not committed.** The export-budget script is a throwaway;
  re-deriving the budget means rebuilding it from the method section. Committing
  fixtures/generators for the 10 MB reference payload and the 100 k-row `csv_data`
  body would make the budget reproducible rather than re-derivable.
- **Transitive dependency drift (code-health §12).** Direct dependencies are
  exact-pinned; transitives are not. A lock file (`pip-compile`) was noted as a
  post-review iteration and has not been added.
- **Docker artifacts.** `README.md` carries Dockerfile and docker-compose templates,
  but no `Dockerfile` is checked in. Phase 5 deliberately kept these docs-only; a
  committed Dockerfile is a fresh decision, not pending roadmap work.

### 2.5 Explicitly out of scope — do not implement without a new decision

These are settled exclusions, listed so they are not mistaken for a backlog:

- Server-side payload caching or session storage for export — violates the
  no-persistence requirement. Perf is served by compression, streaming and
  client-side rendering instead.
- Redis rate-limit storage as the default. It ships as an optional
  `requirements-redis.txt`, required only above one worker or one replica.
- Any frontend framework or build step.
- Any CSP relaxation, `unsafe-inline` included. Phase 1 only tightened it.
- Payload-level logging or telemetry.
- Auto keep-alive pings against the Render free tier.
- Committed `docker-compose` / systemd unit files.

---

## Verification checklists still requiring a manual sign-off

Two lines in the security review's post-fix checklist are marked manual and have
no automated equivalent: **F14** (every deployment path states HTTPS is required)
and **F17** (no stale `candidates` or MIT references remain in the docs). The rest
of that checklist is covered by `tests/test_routes.py`, `tests/test_security.py`
and the Node assertions in `tests/js/`.
