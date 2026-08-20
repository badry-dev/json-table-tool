# Roadmap — v1.2.0 "Hardening & Performance" — JSON Table Converter

**Date:** 2026-08-20
**Inputs:** `docs/security-review-v1.2.md` (17 findings, F1–F17), `docs/performance-review-v1.2.md` (13 findings, P1–P13), prior `docs/code-health-final.md` (2026-05), project goals in `README.md`/`CLAUDE.md`/`AGENTS.md`/`MEMORY.md`.
**Target:** `Config.APP_VERSION = '1.2.0'`, shipped as one milestone with zero data-persistence changes, zero CSP relaxations, zero new build tooling.

---

## 1. Goals (recap) and How This Roadmap Serves Them

| Project goal | Roadmap coverage |
|---|---|
| **Privacy-first, zero storage** | All fixes respect no-persistence; credential/log hygiene (F3, F9); no payload caching (P2 constraint) |
| **Secure by default** | F1 (formula injection), F2 (CVEs), F4-F8, F10-F16 |
| **Lightweight & fast** | P1-P9, P12 (compression, streaming, lazy rendering) |
| **Reliable deploys** | F2 (re-audit), P9 (gunicorn timeout), Phase 0 CI gate |
| **Internal-team usable** | Phase 4 features (load more, filter, new exports, opt-in auth) |
| **Maintainable** | Phase 3 refactor, Phase 5 doc sync (F17), dead-code removal (P10) |

---

## 2. Version Plan

**v1.2.0** = Security hardening + performance + reliability (Phases 0-3 below) and a small set of low-risk features (Phase 4). Phases 0-3 are designed to be individually shippable; each ends green (full test suite + manual checklist).

**Decision points.** D1, D2, D3, D5 and D6 are **decided** below and their dependent tasks are committed v1.2 scope. D4 is the only open item; every task and acceptance criterion that depends on it is marked *conditional (D4)* and is dropped without further impact if D4 is declined.

- **D1.** gzip implementation — **decided: in-repo middleware** (~20 lines, no new pinned dependency; keeps the dep count at 7 and honors the "lean deps" value). `Flask-Compress` is the documented fallback only if the middleware cannot meet the P1 budget. (P1)
- **D2.** `find_candidate_arrays` lifecycle — **decided: delete** (it is dead code superseded by the tree picker). Deletion happens in Phase 0, *before* the Phase 1 recursion-guard work, so guards are added only to `extract_table_data` and no guard tests for the deleted function are written. (P10/F8)
- **D3.** Proxy-aware rate limiting — **decided: opt-in `TRUST_PROXY`/`ProxyFix`, off by default.** `X-Forwarded-For` is never trusted unless `TRUST_PROXY=1` is set; with it unset, behavior is unchanged from v1.1. (F12)
- **D4.** Opt-in HTTP Basic Auth gate for the whole app via env (`APP_BASIC_AUTH_USER`/`APP_BASIC_AUTH_PASS`, off by default) — **OPEN, needs maintainer sign-off** before Phase 4 starts. It is the internal-tool use case from README §"Access Control" (small, opt-in, no persistence), but it *is* a new access-control surface. **Dependent scope:** task 4.6 only. If D4 is declined, drop 4.6 and its acceptance line; nothing else in v1.2 changes. (Recommendation: approve.)
- **D5.** Port allowlist for API fetch — **decided: yes**, `API_ALLOWED_PORTS` default `80,443,8443` only. (F6.2)
- **D6.** Export buffering vs the no-disk-writes rule: openpyxl `write_only` mode and `SpooledTemporaryFile` both rely on OS temp files (transient payload-derived data). Default recommendation: **diskless and row-count-compatible** — a normal-mode `Workbook` writing no OS temp files, plus an **XLSX-only** `MAX_EXPORT_ROWS` cap that defaults to `0`/disabled so the export contract is never narrower than what `/process` accepts, with CSV/TSV streaming uncapped as the always-available fallback (see 2.3 and Performance Review P3). That default is a compatibility setting, **not** a memory bound: memory safety is established by the separate limits and by the measured budget in Performance Review §4, not by the row cap or the 10 MB input cap. The memory-light temp-file route only under an explicit documented exception. (P3)

**Explicit production signal:** the fail-fast (1.6) and `Secure` cookie (1.14) behaviors are gated on an explicit `APP_ENV=production` (or `PRODUCTION=true`) env var — never inferred from `not DEBUG`, because the documented local run `python app.py` has `DEBUG=False` by default.

---

## 3. Phases

### Phase 0 — Foundations: Dependencies, CI, Tooling  (≈ 0.5 day)

**Goal:** eliminate known CVEs, stop test tooling reaching production, add a CI gate before the auto-deploy (`render.yaml` deploys every push with zero checks today).

| # | Task | Files | Fixes |
|---|---|---|---|
| 0.1 | Pin upgrades: `Flask==3.1.3`, `requests==2.33.0`, `gunicorn==22.0.0`, `openpyxl==3.1.5` | `requirements.txt` | F2 |
| 0.2 | Move `pytest==9.0.3` to new `requirements-dev.txt` (`-r requirements.txt` + pytest, ruff, coverage, pip-audit) | `requirements-dev.txt` (new) | F2 |
| 0.3 | Add `.github/workflows/ci.yml`: install dev deps → `ruff check .` → `ruff format --check .` → `python -m pytest tests/ -v` → `pip-audit -r requirements.txt` | `.github/workflows/ci.yml` (new) | F2 |
| 0.4 | Add `pyproject.toml` (ruff + pytest config, `target-version = "py311"`, line-length 100) | `pyproject.toml` (new) | — |
| 0.5 | Run `ruff check . --fix`; fix remaining warnings manually; verify format | all `.py` | — |
| 0.6 | License consistency: README/CLAUDE badge "MIT" → GPL-3.0 (LICENSE file is GPL-3.0) | `README.md`, `CLAUDE.md` | F17 |
| 0.7 | Set `autoDeployTrigger: checksPass` in `render.yaml` (replaces `autoDeploy: true`) so Render waits for CI checks and blocks deployment when checks fail or are missing | `render.yaml` | — |
| 0.8 | Remove dead code `find_candidate_arrays` + its 4 tests (D2); update the stale candidates-handshake references in `MEMORY.md`/`CLAUDE.md`/`AGENTS.md` | `helpers.py`, `tests/test_helpers.py`, docs | P10, F8 |

**Acceptance:** `pip-audit -r requirements.txt` = 0 vulnerabilities; CI green; **`python -m pytest tests/ -v` exits 0** after the upgrades — the passing command, not a fixed count, is the criterion, because 0.8 deliberately removes the four `find_candidate_arrays` tests (baseline **82 → 78**); `pip install -r requirements.txt` no longer installs pytest; `render.yaml` gates deploys on CI checks; `find_candidate_arrays` and its tests are gone.

---

### Phase 1 — Security Hardening  (≈ 1.5-2 days)

**Goal:** close every open security finding (F15 is aligned with the existing `/health` contract, not deferred).

| # | Task | Files | Fixes |
|---|---|---|---|
| 1.1 | **Formula-injection sanitization (spreadsheet formats only)**: `sanitize_cell(value)` in `helpers.py` for CSV/TSV/XLSX (triggers `= + - @`, tab, CR, LF — per-format policy in Security Review F1); apply in `export_csv`, `export_xlsx` (replace duplicated `isinstance(v,(dict,list))` branches), and in `app.js` `downloadDelimited()` escape. JSONL (4.3) stays lossless; Markdown (4.3) uses Markdown escaping — neither gets formula sanitization. Tests: `=SUM(A1)`, `@cmd`, `+1`, `-1`, tab/CR/LF-prefixed on all four export paths (2 server routes + client CSV + client TSV) | `helpers.py`, `routes.py`, `static/js/app.js`, `tests/test_routes.py` | **F1** |
| 1.2 | **Log hygiene**: fixed message `logger.warning('API request failed')` — never log the URL (query, fragment, userinfo, and path can all carry tokens); `caplog` assertions that no URL component or token reaches logs | `routes.py`, `tests/test_routes.py` | F3, F9 |
| 1.3 | **API-fetch JSONL ValueError → 400** generic message (before outer handler); keeps the exception out of logs and returns the correct client-error status | `routes.py`, `tests/test_routes.py` | F9 |
| 1.4 | **Outbound header-name allowlist**: regex `^[A-Za-z0-9-]+$` + reject hop-by-hop/reserved names (`host`, `content-length`, `transfer-encoding`, `connection`, `proxy-*`, `authorization`, `cookie`) → 400 | `routes.py`, `tests/test_routes.py` | F4 |
| 1.5 | **Header hardening**: add HSTS (secure requests only), `Permissions-Policy`, `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy`; extend CSP with `object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'` (build directives as a list or keep the trailing `;` separator — see Security Review F5); keep `X-Frame-Options: DENY` | `security.py`, `tests/test_routes.py` | F5 |
| 1.6 | **SECRET_KEY fail-fast**: `create_app` raises when `APP_ENV=production` is set and `SECRET_KEY` is the dev default/unset (explicit production signal — not `not DEBUG`, which would block the documented local run); env-var int validation with clear messages | `app.py`, `config.py`, `tests/test_routes.py` | F7 |
| 1.7 | **Recursion-depth guard**: `_depth`/`max_depth` on `extract_table_data` (mirror `flatten_for_csv`); `find_candidate_arrays` is removed in Phase 0 (D2), so no guard or tests for it; wrap `json.loads`/`parse_jsonl` callers to catch `RecursionError` → 400 "JSON nesting too deep"; 1500-deep nesting test | `helpers.py`, `routes.py`, `tests/test_helpers.py`, `tests/test_routes.py` | F8 |
| 1.8 | **Bounded DNS admission**: shared, per-process `ThreadPoolExecutor` (fixed `max_workers`, e.g. 4), created **lazily inside the worker after fork** (module-level lazy init under a lock, or `os.register_at_fork(after_in_child=...)`). **Teardown is documented, not guaranteed:** `shutdown(wait=False, cancel_futures=True)` returns immediately but cannot cancel a running `getaddrinfo`, and `concurrent.futures` joins its non-daemon threads at interpreter exit regardless of `wait`, so worker recycling **can block for up to the remaining lookup time**. Accept that (bounded in practice by the resolver's own timeout) or move resolution into a killable subprocess — process isolation and a cancellable resolver are the only hard bounds. `API_DNS_TIMEOUT` (default 3s) bounds **only `Future.result()`** — it cannot cancel a running `getaddrinfo`, so an in-flight **semaphore permit is acquired before submit and released from the future's done-callback**, never on caller timeout (equivalently: a bounded submission queue). When no permit is available within a short admission wait, return 503/400 rather than queueing unboundedly. Tests: repeated timeouts do not leak permits or threads, saturation returns the admission error instead of blocking, and the lifecycle test asserts the *documented* recycling behavior (shutdown may wait on an in-flight lookup) rather than a non-blocking exit | `security.py`, `config.py`, `tests/test_security.py` | F6.1, P7 |
| 1.9 | **Port allowlist** for API fetch (D5): `API_ALLOWED_PORTS` default `80,443,8443` | `security.py`/`routes.py`, `config.py`, tests | F6.2 |
| 1.10 | **Proxy-aware rate limiting** (D3): `TRUST_PROXY=1` → `ProxyFix(app, x_for=1, x_proto=1, x_host=1)` (exact trusted hop count); rate-limit key derived from `request.remote_addr` *after* ProxyFix — never from the raw `X-Forwarded-For` header; forged-header and multi-proxy tests; document Redis storage for multi-instance in `MEMORY.md` | `app.py`, `extensions.py`, `config.py`, tests | F12 |
| 1.11 | **JSON error handlers**: 413 → `{"error": "Request too large (max 10MB)"}` JSON; generic 500 → JSON | `app.py`, tests | F10 |
| 1.12 | **`Cache-Control: no-store`** on `/process`, `/export-csv`, `/export-xlsx`, `/health` | `security.py` or routes, tests | F11 |
| 1.13 | **Upload validation**: reject non-`.json`/`.jsonl` filenames and unexpected content-types → 400 | `routes.py`, tests | F13 |
| 1.14 | **Cookie hardening**: `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE='Lax'`, `SESSION_COOKIE_SECURE` tied to the explicit `APP_ENV=production` signal (not `not DEBUG`) | `config.py`, tests | F16 |
| 1.15 | **Version disclosure** (aligned with the current `/health` contract): keep `version` returned by default; optional `HEALTH_REVEAL_VERSION` gate defaults to **on** (no behavior change); add tests only if the gate is implemented | `routes.py`, `config.py` | F15 |

**Acceptance:** Security Review §4 checklist fully passes (formula files open inert in Excel; SSRF battery incl. decimal/hex/mapped-IPv6; CSRF 400 without token; no token in `caplog`; HSTS+CSP headers present; 413/500 JSON; depth-1500 JSON → 400; per-client rate buckets with `TRUST_PROXY=1`).

---

### Phase 2 — Performance  (≈ 1.5-2 days)

**Goal:** meet the perf budget in Performance Review §4.

| # | Task | Files | Fixes |
|---|---|---|---|
| 2.1 | **gzip middleware** (D1): compress JSON/text bodies >1 KB when client accepts gzip; set `Content-Encoding: gzip`, `Vary: Accept-Encoding`; skip bodyless/`HEAD`/`204`/`304`/already-encoded/streamed (`response.is_streamed`) responses; remove or recompute `Content-Length` | `app.py` (or `security.py`), tests | P1 |
| 2.2 | **Static cache headers**: `SEND_FILE_MAX_AGE_DEFAULT=86400` + `?v=APP_VERSION` on CSS/JS URLs | `config.py`, `templates/index.html` | P6 |
| 2.3 | **Diskless, memory-bounded exports** (D6): normal-mode `Workbook` + an XLSX-only `MAX_EXPORT_ROWS` cap → 400 instead of OOM; no OS temp files (openpyxl `write_only` and `SpooledTemporaryFile` both use them — off the table unless a documented exception is approved); no `output.getvalue()`; CSV/TSV stay **uncapped** via a generator response (natively streamable). `MAX_EXPORT_ROWS` is **XLSX-only** and defaults to `0` (= unlimited) so it can never reject a dataset `/process` accepted — a compatibility default, not a memory bound. Response contract is **additive, one new key**: reuse the existing `total_rows` (`routes.py:192`) and add `max_export_rows`; the client greys out Excel iff `max_export_rows > 0 && total_rows > max_export_rows` and points at CSV/TSV, and `/export-xlsx` independently returns 400 `{"error": "…rows exceeds the Excel export limit…; use CSV/TSV"}` (see Performance Review P3) | `routes.py`, `config.py`, `static/js/app.js`, tests | P3 |
| 2.4 | **Preview truncation (non-mutating)**: build a separate preview projection (copy) capping long strings / nested arrays / nested objects; `table_data`/`csv_data` keep full fidelity — test that exports stay untruncated | `routes.py`, `helpers.py`, tests | P2.2, P5 |
| 2.5 | **Lazy tree picker**: build children on first toggle; cap per-level children and total nodes | `static/js/app.js` | P4 |
| 2.6 | **Client render caps**: `renderNestedObject` ≤ 20 keys + "more"; `formatValue` stringify cap for primitive arrays; long-string truncation | `static/js/app.js` | P5 |
| 2.7 | **Memory trim**: decode `bytearray` directly (drop `bytes()` copy) in API-fetch; single-pass flatten + column accumulation (collect into a set, sort once — preserves current column order) | `routes.py`, `helpers.py`, tests | P12, P8 |
| 2.8 | **gunicorn tuning**: `--timeout 60` everywhere (`render.yaml`, README, Docker/systemd snippets); document the `API_FETCH_TIMEOUT < gunicorn timeout` invariant. **Deployment topology is coupled to rate-limit storage (see 2.10): one worker *and* one instance stays the default whenever `RATELIMIT_STORAGE_URI` is `memory://`**; `--workers 2`, the README's three `--workers 4` examples (`README.md:189`, `:207`, `:256`), and any `numInstances > 1` require shared storage first | `render.yaml`, `README.md` | P9 |
| 2.9 | **Chunked Blob** for client CSV/TSV | `static/js/app.js` | P13 |
| 2.10 | **Rate-limit storage matches the deployment topology**: `memory://` counters are process-local, so the effective limit is multiplied by **`workers × replicas`**, not workers alone. The app cannot discover this reliably at runtime — an explicit `gunicorn --workers` overrides `WEB_CONCURRENCY`, and Render's `numInstances` is invisible to the process — so **the topology is declared, not inferred**: add `APP_WORKERS` and `APP_REPLICAS` (both default `1`) that deployments set alongside their real values. Startup check in `create_app()`: when `APP_WORKERS × APP_REPLICAS > 1` and `RATELIMIT_STORAGE_URI` is still `memory://`, log a loud warning, and fail fast under `APP_ENV=production`. Fix the three README/Docker/systemd `--workers 4` examples (`README.md:189`, `:207`, `:256`) to either drop to 1 or set shared storage, and document `RATELIMIT_STORAGE_URI=redis://…` as the supported multi-process setup. Tests: two limiter instances on `memory://` do **not** share counters (the multiplier is real), the guard warns when declared topology > 1, and it raises under `APP_ENV=production` | `app.py`, `extensions.py`, `config.py`, `README.md`, `render.yaml`, tests | F12 |

**Acceptance:** Performance Review §4 budget met on the reference payload; export of 100k rows completes without OOM; tree picker opens instantly on a 10 MB payload; perf regression spot-checked manually (no automated perf tests in CI — optional `pytest-benchmark` deferred).

---

### Phase 3 — Refactor & Correctness  (≈ 1 day)

**Goal:** reduce `process_json` complexity (cyclomatic ≈ 15), eliminate known correctness nits. Carries forward the unimplemented recommendations from `docs/code-health-final.md` §4.1/§4.3/§7. (Dead-code removal for `find_candidate_arrays` is already done in Phase 0.)

| # | Task | Files | Fixes |
|---|---|---|---|
| 3.1 | Extract `_load_input(request, data_format) -> (data, error_response)` (file/paste/api) and `_select_table_data(data, path) -> (rows, error_response)`; `process_json` body ≤ ~50 lines | `routes.py`, tests | — |
| 3.2 | Extract `serialize_cell_value(v)` (already needed by 1.1) and `preview_truncate(row)` (needed by 2.4) | `helpers.py` | — |
| 3.3 | Return `preview_limit` in `/process` payload; use it for the badge; note sort-scope in UI text | `routes.py`, `static/js/app.js` | P11 |
| 3.4 | Move `openpyxl` import to module top (fails fast on missing dep) | `routes.py` | — |
| 3.5 | Type annotations on `helpers.py`/`security.py` signatures (mypy optional; skip strict mode to limit scope) | `helpers.py`, `security.py` | — |

**Acceptance:** `python -m pytest tests/ -v` exits 0 with the remaining tests unchanged (the post-0.8 baseline of 78, plus everything added in Phases 1–2); `process_json` ≤ 50 lines; badge reflects config; **no breaking behavior change** for API consumers — the response gains keys (`preview_limit`, `max_export_rows`) but no existing key changes name, type, or meaning.

---

### Phase 4 — Features (v1.2 scope, all client-side / opt-in)  (≈ 2-3 days)

**Goal:** features that use data already available client-side (respecting no-persistence) plus the opt-in internal-team access gate. Anything needing server-side storage is explicitly out of scope (see §5).

| # | Feature | Files | Notes |
|---|---|---|---|
| 4.1 | **Load more / pagination**: since `csv_data` is already in the browser, add "Load next 500" / "Load all" over the full dataset with a row-count warning (freeze guard at ~50k DOM rows) | `static/js/app.js`, `templates/index.html` | Serves P2.3 and fixes the sort-only-preview quirk (full-dataset client sort once loaded) |
| 4.2 | **Row filter/search**: case-insensitive substring filter across visible/full data | `static/js/app.js` | Pure client-side |
| 4.3 | **New client-side exports**: JSONL (lossless — original values, **no** formula sanitization) and Markdown table (Markdown-specific escaping only; the spreadsheet sanitizer from 1.1 does not apply) per `MEMORY.md` guidance | `static/js/app.js`, `templates/index.html` | Dropdown additions |
| 4.4 | **Column visibility toggle** (hide/show columns in preview) | `static/js/app.js`, `static/css/style.css`, `templates/index.html` | |
| 4.5 | **Deep-linkable path selection** (`#path=users.0.orders` pre-fills the tree selection) | `static/js/app.js` | Small UX win for repeat conversions |
| 4.6 | **Opt-in Basic Auth gate** — *conditional (D4), implement only if approved*: `APP_BASIC_AUTH_USER/PASS` env → `before_request` 401 (constant-time compare, `WWW-Authenticate`); off by default | `app.py`, `config.py`, `security.py`, `render.yaml` comment | Internal-tool goal; no persistence |
| 4.7 | **`/health` split**: `/health/live` (process) + `/health/ready` (deps/limits) for Render health checks | `routes.py` | Small ops win |
| 4.8 | Replace `alert()` About dialog with in-page modal (also fixes the hardcoded v1.1.0 string); make export dropdown keyboard-accessible (`aria-expanded`, Escape) | `static/js/app.js`, `templates/index.html`, `static/css/style.css` | From `code-health-final.md` §4.10 |

**Acceptance:** manual pass of each *in-scope* feature; all exports include full row counts (not just 25); no new dependencies; CSP intact (no inline JS); `alert()` removed. **Conditional (D4):** if and only if D4 is approved, the Basic Auth gate rejects unauthenticated requests with 401 when the env vars are set and is fully transparent when they are unset; if D4 is declined this criterion does not apply.

---

### Phase 5 — Docs, Memory, DX  (≈ 0.5 day)

| # | Task | Files |
|---|---|---|
| 5.1 | Sync `MEMORY.md`: multi-array handshake entry → tree-picker handshake; add entries for formula injection, fixed API-fetch log message (no URL), ProxyFix/TRUST_PROXY, DNS timeout, gunicorn timeout invariant, port allowlist | `MEMORY.md` |
| 5.2 | Sync `CLAUDE.md` + `AGENTS.md` (project snapshot: `/process` response shape, preview_limit, exports, license) | `CLAUDE.md`, `AGENTS.md` |
| 5.3 | `README.md`: license badge (GPL-3.0), new env vars table rows, HTTPS-required note per deploy path, perf notes | `README.md` |
| 5.4 | Add `.env.example` (all vars, safe placeholders) and `Makefile` (`test`, `lint`, `format`, `audit`, `coverage`) | `.env.example`, `Makefile` (new) |
| 5.5 | `CHANGELOG.md` starting at 1.1.0; bump `APP_VERSION='1.2.0'` | `CHANGELOG.md` (new), `config.py`, `static/js/app.js` (About text) |

**Acceptance:** a fresh contributor can set up, lint, test, and run coverage using only README + CONTRIBUTING-level docs; no stale candidates/MIT references remain.

---

## 4. Effort Summary & Suggested Sequencing

| Phase | Effort | Depends on | Shippable alone? |
|---|---|---|---|
| 0 Foundations | 0.5 day | — | Yes |
| 1 Security | 1.5-2 days | Phase 0 (clean base) | Yes |
| 2 Performance | 1.5-2 days | Phase 0 (and F1 for export changes) | Yes |
| 3 Refactor | 1 day | Phase 1 (serialize helper), Phase 2 (truncate) | Yes |
| 4 Features | 2-3 days | Phase 2 (lazy render, caps) | Yes |
| 5 Docs/DX | 0.5 day | all (doc accuracy) | Yes |

**Total: ≈ 7-9 days** (single engineer, including test updates and the manual verification checklists).

**Risk order:** Phase 0 first (deploying with gunicorn 21.2.0 while knowing about CVE-2024-1135 is the standing exposure), then Phase 1.1 (formula injection) before any further feature work on exports. Phase 3 (refactor) intentionally follows Phase 2 (performance); both touch `routes.py`/`helpers.py`, so keep each phase's commits scoped per file. Do not assume a refactored `process_json` exists during Phase 2 — Phase 2 works against the current structure, and the 3.1/3.2 helper extractions land in Phase 3.

---

## 5. Explicitly Out of Scope (do not implement without a decision)

- **Server-side payload caching/session storage for export** — violates the no-persistence hard requirement (`MEMORY.md` 2026-05-12). Perf is solved via compression + streaming + client-side rendering instead.
- **Redis rate-limit storage by default** — the default stays `memory://` with a **single worker and a single instance** (see 2.10). Redis (or any shared `RATELIMIT_STORAGE_URI`) becomes *required*, not optional, as soon as more than one worker or instance is run; v1.2 ships the guard-rail and the docs, not a bundled Redis dependency.
- **Frontend framework / build step** — forbidden by project conventions.
- **CSP relaxation** (e.g. `unsafe-inline`) — never; Phase 1 only *tightens* CSP.
- **Payload-level logging / telemetry** — never; Phases 1.2/1.3 are about *removing* such leaks.
- **Auto-keep-alive pings** — defeats Render free-tier cost model.
- **`docker-compose`/systemd file additions** — docs only in Phase 5.

---

## 6. Definition of Done (v1.2.0)

- [ ] `python -m pytest tests/ -v` exits 0 (the command is the criterion, not a count). Baseline for v1.2 is the **78** tests remaining after Phase 0.8 removes the four `find_candidate_arrays` tests (82 − 4), plus every test added in Phases 1–5.
- [ ] `pip-audit -r requirements.txt` → 0 vulnerabilities; CI (Phase 0.3) green on push/PR.
- [ ] Rate limiting is coherent with the shipped topology: the default deployment runs one worker and one instance on `memory://`, every multi-worker or multi-instance example in the docs sets a shared `RATELIMIT_STORAGE_URI`, and the declared-topology guard fires (Phase 2.10).
- [ ] `ruff check .` and `ruff format --check .` exit 0.
- [ ] Security Review §4 checklist passes (formula injection inert, SSRF battery, log hygiene via caplog, headers, fail-fast SECRET_KEY, depth guards, JSON error handlers, no-store, proxy-aware limiting).
- [ ] Performance Review §4 budget met on the reference payload; 100k-row XLSX export does not OOM.
- [ ] All three input methods × both formats × all auth methods work end-to-end; multi-array JSON triggers the tree picker; picking a path returns rows.
- [ ] All exports download full row counts; Markdown/JSONL exports added; `alert()` removed.
- [ ] `GET /health` returns `{"status":"ok","version":"1.2.0"}`; `/health/live` + `/health/ready` present.
- [ ] `MEMORY.md`/`CLAUDE.md`/`AGENTS.md`/`README.md` describe the tree-picker handshake, GPL-3.0 license, and all new env vars.
- [ ] No new file writes, DB calls, payload logging, inline JS/CSS, or CSP relaxations introduced.
