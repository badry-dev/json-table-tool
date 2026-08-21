# AGENTS.md

Contract for AI coding agents (Claude Code, Cursor, GitHub Copilot Workspace, Aider, Codex, etc.) working in this repository. Read this **and** `CLAUDE.md` before making changes — they share scope but this file is the agent-specific quick reference and verification checklist.

## TL;DR for Agents

- **App-factory pattern.** Flask app is built by `create_app()` in `app.py`. Gunicorn is started with `"app:create_app()"` — never `"app:app"`.
- **Modular layout.** Backend is split across `app.py`, `config.py`, `extensions.py`, `security.py`, `helpers.py`, `routes.py`. Frontend is split into `templates/index.html` (structure only), `static/css/style.css`, `static/js/app.js`.
- **Strict CSP enforced.** `script-src 'self'`, no `unsafe-inline`. Do not add inline `<script>` or `style="..."` attributes to the HTML or you will break the page.
- **CSRF is mandatory on POST.** Token is in the `csrf-token` meta tag; JS reads it and attaches `csrf_token` (FormData) or `X-CSRFToken` header. Don't bypass.
- **SSRF guard runs first.** Every `/process` API fetch passes through `security.validate_url()` (resolves DNS, rejects non-global IPs). Don't disable it.
- **No persistence, ever.** No DB, no disk writes of payloads, no payload-level logging (only metadata via `logger.warning/exception`).
- **Tests exist** (`pytest`, under `tests/`). New backend behavior should come with tests — fixtures are in `tests/conftest.py`.
- **No build step.** Vanilla HTML/CSS/JS — don't introduce npm, Vite, React, Tailwind, etc.

## Project Snapshot

| Item              | Value                                                          |
|-------------------|----------------------------------------------------------------|
| Language          | Python 3.11+ (Render targets 3.14.5)                           |
| Web framework     | Flask 3.1.3 (app factory)                                      |
| Security libs     | Flask-WTF 1.2.1 (CSRF), Flask-Limiter 3.5.0 (rate limit)       |
| HTTP client       | requests 2.33.0                                                |
| Excel export      | openpyxl 3.1.5                                                 |
| WSGI server       | gunicorn 22.0.0 — `gunicorn "app:create_app()" --workers "$WEB_CONCURRENCY" --timeout 60` |
| Test runner       | pytest 9.0.3 (`requirements-dev.txt`) + ruff, coverage, pip-audit |
| Frontend          | HTML + external CSS/JS (no framework, no build)                |
| Deployment        | Render (free tier) via `render.yaml`; also docs for Docker/Nginx |
| App version       | `Config.APP_VERSION = '1.2.0'` (returned by `/health`)         |

## Setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements-dev.txt
python app.py                    # http://localhost:5000

# enable debug
$env:FLASK_DEBUG = "1"           # PowerShell
# export FLASK_DEBUG=1           # bash
python app.py
```

Run tests:

```bash
python -m pytest tests/ -v
```

## Code Map

### Backend

- **`app.py`** — `create_app(config_class=Config)` factory. Asserts the production SECRET_KEY, runs `check_rate_limit_topology`, optionally installs `ProxyFix` (`TRUST_PROXY=1`), initializes CSRF + Limiter, registers `apply_security_headers` and `compress_response` as `after_request` middleware plus the JSON 413/500/404 handlers, and registers the `routes.bp` Blueprint. Module-level `app = create_app()` exists for tooling that expects it, but production uses the factory directly.
- **`config.py`** — `Config` class plus `is_production()`, `env_int()` and `env_int_set()`. Every setting reads from the environment with a default; integers report which variable was mistyped instead of raising a bare `ValueError`. Includes `SECRET_KEY`, `MAX_CONTENT_LENGTH`, `PREVIEW_ROW_LIMIT`, `API_FETCH_*`, `API_DNS_*`, `API_ALLOWED_PORTS`, `FLATTEN_MAX_DEPTH`, `MAX_EXPORT_CELLS`, `RATELIMIT_*`, `WEB_CONCURRENCY`, `APP_REPLICAS`, `TRUST_PROXY`, `SESSION_COOKIE_*`, `SEND_FILE_MAX_AGE_DEFAULT`, `GZIP_MIN_SIZE`, `HEALTH_REVEAL_VERSION`, `APP_VERSION`, `DEBUG`. See `.env.example`.
- **`extensions.py`** — Bare `CSRFProtect()` and `Limiter(key_func=client_ip_key)` instances, bound by `app.py` via `init_app`. `client_ip_key` reads `request.remote_addr` and never the raw `X-Forwarded-For`, so the bucket is whatever ProxyFix decided rather than something a client can assert. Importing this module never has side effects on the Flask app — that's the point.
- **`security.py`**
  - `validate_url(url)` — returns `(is_valid, error_or_none)`. Rejects non-http(s) schemes, missing hostname, ports outside `API_ALLOWED_PORTS`, non-resolvable hostnames, and any resolved IP where `not ip.is_global or ip.is_multicast`.
  - `resolve_hostname(hostname)` / `get_resolver_pool()` — DNS on a shared fixed-size pool with admission control. Bounds the caller's wait and concurrency; **not** the lookup itself, and **not** teardown.
  - `apply_security_headers(response)` — sets CSP (strict, `script-src 'self'`, plus `object-src 'none'`, `base-uri 'self'`, `frame-ancestors 'none'`, `form-action 'self'`, `upgrade-insecure-requests`), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`, COOP/CORP, HSTS on secure requests only, and `Cache-Control: no-store` on the data and health endpoints. CSP allows Google Fonts (style/font) and `data:` images.
- **`helpers.py`**
  - `flatten_for_csv(data, parent_key='', sep='.', _depth=0, max_depth=10)` — depth-capped recursion; deep nesting is JSON-stringified instead of stack-overflowing.
  - `extract_table_data(json_data, _depth=0, max_depth=10)` — heuristic: list-of-dicts → use directly; dict with array value → that array; nested dicts → recurse (depth-capped); otherwise single-row.
  - `flatten_rows(rows, max_depth=10)` — one pass returning `(flattened_rows, sorted_columns)`; replaces flatten-then-`get_all_columns`.
  - `sanitize_cell(value)` / `serialize_cell_value(value)` / `is_formula_trigger(value)` — spreadsheet formula-injection defenses. **CSV/TSV/XLSX only.**
  - `preview_truncate(row)` — capped *copy* of a preview row; never mutates the source.
  - `parse_jsonl(text)` — line-by-line JSON; raises `ValueError` with the offending line number.
  - `extract_by_path(json_data, path)` — dot-notation navigation; `'(root)'` is the sentinel for top-level lists.
  - `get_all_columns(data)` — sorted union of keys.
- **`routes.py`** — Blueprint `bp`. Routes:
  - `GET /` → `templates/index.html`.
  - `GET /health` → `{"status": "ok", "version": APP_VERSION}` (version omitted when `HEALTH_REVEAL_VERSION=0`).
  - `GET /health/live` → process liveness; checks nothing, so a dependency outage cannot cause a restart loop.
  - `GET /health/ready` → readiness; 200 or 503 with a `checks` map.
  - `POST /process` → rate-limited (default `RATE_LIMIT_PROCESS=30/min`). Reads `input_method` (`file`/`paste`/`api`), `data_format` (`json`/`jsonl`), optional `json_path`. Returns `{success, columns, preview, preview_limit, total_rows, total_cells, max_export_cells, csv_data, csv_columns}` **or** `{needs_selection: true, raw_json: ...}` when no `json_path` was selected, so the frontend can render the JSON tree picker. The body is built by `_load_input()` and `_select_table_data()`; keep `process_json` itself thin.
  - `POST /export-csv` → rate-limited (default `RATE_LIMIT_EXPORT=60/min`). Generator-streamed and **uncapped**.
  - `POST /export-xlsx` → rate-limited. Server-side Excel via openpyxl, capped by `MAX_EXPORT_CELLS` (400 when exceeded, never truncated). Diskless: no OS temp files.

### Frontend

- **`templates/index.html`** — pure structure. CSRF meta tag at the top (`<meta name="csrf-token" content="{{ csrf_token() }}">`). References `style.css` and `app.js` via `url_for('static', ...)`. No inline JS/CSS (CSP would block it).
- **`static/css/style.css`** — `:root` (dark, default) + `:root.light` overrides. All component styles, sort indicators, modals, export dropdown, table toolbar (filter / load-more / column visibility), theme toggle.
- **`static/js/app.js`** — reads CSRF token from meta tag; attaches it to FormData and `X-CSRFToken`. Handles tab switching, drag-drop, JSON/JSONL toggle, auth method visibility, client-side sort/filter/pagination/column visibility, **client-side** CSV, TSV, JSONL and Markdown downloads, **server-side** Excel via `/export-xlsx`, theme persistence in `localStorage`, the lazily-built JSON tree picker triggered by `needs_selection: true` (with `#path=` deep links), and the About modal. No `alert()`.

### Tests

- **`tests/conftest.py`** — provides `app` (with `TESTING=True`, `WTF_CSRF_ENABLED=False`) and `client` fixtures.
- **`tests/test_helpers.py`** — pure-function tests for the data-processing layer.
- **`tests/test_security.py`** — `validate_url` with mocked `socket.getaddrinfo`; verifies private-IP/loopback/link-local rejection.
- **`tests/test_routes.py`** — integration tests for every route, including security headers, JSONL, path selection, exports, formula injection, log hygiene, config gates and the topology guard.
- **`tests/js/*.mjs`** — Node assertions that load the real `static/js/app.js` in a stubbed DOM (`dom_stub.mjs`). No build step, no dependencies. Run them with `make test-js`; CI runs them too.

### Deploy / Config

- **`render.yaml`** — Render Blueprint. The start command derives `--workers` from `$WEB_CONCURRENCY` and sets `--timeout 60`; `APP_ENV=production`, `WEB_CONCURRENCY` and `APP_REPLICAS` are declared; `SECRET_KEY` is `generateValue: true`; `autoDeployTrigger: checksPass` gates deploys on CI.
- **`requirements.txt`** — exact-pinned runtime deps. Don't loosen. `requirements-dev.txt` holds test tooling; `requirements-redis.txt` holds the optional Redis client for shared rate-limit storage.
- **`.github/workflows/ci.yml`** — ruff check, ruff format --check, pytest, the Node assertions, and `pip-audit`.
- **`Makefile` / `.env.example`** — developer entry points and every environment variable with its default.

## Conventions

### Do

- Return JSON `{"error": "..."}` with a 4xx/5xx status for backend failure paths.
- Use `logger.warning(...)` / `logger.exception(...)` for server-side issues — do **not** log request bodies.
- Apply `@limiter.limit(lambda: current_app.config.get('RATE_LIMIT_...'))` on any new mutating route.
- Read config via `current_app.config['KEY']`, not by re-importing `Config` at request time.
- For new auth methods on the API tab: add a select option in `index.html`, a `data-auth="..."` fieldset, the JS visibility branch in `app.js`, and the conditional in `routes.py`.
- For new exports: add the entry to the export dropdown, the handler in `app.js`, optionally a server route in `routes.py`. Pin any new dependency. **Decide the sanitization policy explicitly**: spreadsheet-compatible formats go through `sanitize_cell`; lossless or text formats (JSONL, Markdown) must not.
- Add or update tests under `tests/` for any backend behavior change. Class-style grouping (`class TestXxx:`) is the existing pattern.
- Preserve the CSP. If new third-party CSS/fonts are needed, edit `apply_security_headers` deliberately.

### Don't

- Don't add inline `<script>` blocks, `style="..."` attributes, or `onclick=` handlers in the HTML — CSP blocks them.
- Don't `app:app` in gunicorn args; the production command is `app:create_app()` (factory).
- Don't remove `allow_redirects=False` on the outbound `requests.get` — the SSRF guard only validated the *original* URL.
- Don't unbound the streamed download — `API_FETCH_MAX_RESPONSE` (10 MB default) is enforced inside the chunk loop.
- Don't lower `FLATTEN_MAX_DEPTH` recursion guard without checking known payload shapes.
- Don't log full exceptions to the response — the routes intentionally return generic messages and `logger.exception(...)` for server logs.
- Don't use the dev `SECRET_KEY` in production. Render generates one via `render.yaml`; for other deployments set the env var. `create_app` refuses to start on it when `APP_ENV=production`.
- Don't infer production from `not DEBUG`, and don't add a second spelling of `APP_ENV` — `config.is_production()` is the only signal.
- Don't log the URL, the exception, or any request field on the API-fetch failure path — a token can ride in the query string, fragment, userinfo *or* path.
- Don't describe the DNS resolver teardown as bounded. `API_DNS_TIMEOUT` bounds the caller's wait; `getaddrinfo` cannot be cancelled.
- Don't write payloads to disk. openpyxl's `write_only` mode and a rolled-over `SpooledTemporaryFile` both do.
- Don't truncate an oversized export — refuse it. A partial spreadsheet is worse than none.
- Don't hardcode a bare `--workers N` in a start command; derive it from `$WEB_CONCURRENCY` so the declared and running counts cannot drift.
- Don't relax the CSP, and don't reintroduce `alert()` — the About dialog is an in-page modal.

## Verification Checklist (before reporting a task done)

- [ ] `python -m pytest tests/ -v` passes (the passing command is the criterion, not a count).
- [ ] `ruff check .` and `ruff format --check .` exit 0.
- [ ] The Node assertions pass: `make test-js`.
- [ ] `pip-audit -r requirements.txt` reports 0 vulnerabilities.
- [ ] `python app.py` starts cleanly; `GET /` renders; `GET /health` returns the current `APP_VERSION`; `/health/live` and `/health/ready` respond.
- [ ] CSP headers still present (`curl -sI http://localhost:5000/ | findstr /i security` or browser DevTools).
- [ ] CSRF still required on POSTs (a POST without the token returns 400 from Flask-WTF).
- [ ] All three input methods (file / paste / API), both formats (JSON / JSONL), and all four auth methods still work end to end.
- [ ] Multi-array JSON triggers the JSON tree picker; selecting a path returns rows; `#path=...` pre-selects one.
- [ ] CSV, TSV, JSONL and Markdown (client-side) and XLSX (server-side) all download with full row counts, not just the preview.
- [ ] A cell value of `=SUM(A1)` opens as inert text in CSV and XLSX, and survives verbatim in JSONL and Markdown.
- [ ] SSRF guard blocks `http://127.0.0.1`, `http://localhost`, `http://169.254.169.254`, `http://2130706433`, `http://0x7f000001`, `http://[::ffff:7f00:1]`, and any port outside `API_ALLOWED_PORTS`.
- [ ] Rate limit kicks in at the configured threshold (manual: rapid-fire `/process`).
- [ ] No new file writes, DB calls, payload logging, inline JS/CSS, or CSP relaxations were introduced.
- [ ] Any new dependency is **exact-pinned** in `requirements.txt` (or `requirements-dev.txt` / `requirements-redis.txt`).
- [ ] `.env.example`, `README.md` and `CHANGELOG.md` cover any new environment variable.

## When in Doubt

1. Re-read `CLAUDE.md` and this file.
2. Skim `MEMORY.md` for prior decisions on the area you're touching.
3. If the task implies persistence, telemetry, weaker CSP, or a frontend framework: **stop and ask the user first** — those are deliberate "no"s, not oversights.

## Tooling Notes for Specific Agents

- **Claude Code**: prefer `Edit` over `Write` for `app.py`, `routes.py`, `helpers.py`, `static/js/app.js`, `static/css/style.css`, and `templates/index.html` (all read-then-edit targets). Use `Grep` instead of shell `grep`. PowerShell is the default shell on this machine; Bash is available.
- **Cursor / Aider / Copilot Workspace**: respect the modular split — there's a reason `extensions.py` is its own module (circular-import avoidance). Auto-collapse refactors that re-merge modules will break the test fixtures.
- **Any agent**: if you generate code the user did not request (helper modules, type stubs, scratch files), delete it before finishing the task.
