# CLAUDE.md

This file provides guidance for AI assistants working with the JSON Table Converter codebase.

## Project Overview

A lightweight Flask web application that converts JSON/JSONL data into viewable HTML tables with multi-format export (CSV, TSV, Excel). Designed as a stateless, privacy-first internal tool with no data persistence.

**Key features:** file upload (drag-and-drop), paste JSON/JSONL, fetch from external APIs (with auth support), nested data expansion, JSON path selector for multi-array data, client-side column sorting, light/dark theme, CSV/TSV/Excel export.

## Project Structure

```
json-table-tool/
├── app.py               # Flask app factory, startup gates, gzip + error handlers
├── config.py            # All settings via environment variables; is_production()
├── extensions.py        # Flask-WTF (CSRF) and Flask-Limiter instances
├── security.py          # SSRF (port allowlist + bounded DNS) + security headers
├── helpers.py           # Data processing (flatten, extract, JSONL, sanitize, preview)
├── routes.py            # Flask Blueprint with all route handlers
├── static/
│   ├── css/
│   │   └── style.css    # All CSS (dark/light themes, components, utilities)
│   └── js/
│       └── app.js       # All JavaScript (UI, table, exports, theme, modals)
├── templates/
│   └── index.html       # HTML structure only (refs external CSS/JS)
├── tests/
│   ├── conftest.py      # Shared pytest fixtures (app, client)
│   ├── test_helpers.py  # Tests for data processing functions
│   ├── test_security.py # SSRF validation, port allowlist, bounded DNS resolver
│   ├── test_routes.py   # Integration tests for all routes + config gates
│   └── js/              # Node assertions against the real app.js (no build step)
│       ├── dom_stub.mjs
│       ├── test_export_sanitize.mjs
│       ├── test_render_caps.mjs
│       └── test_features.mjs
├── docs/
│   ├── code-health-final.md
│   ├── security-review-v1.2.md
│   ├── performance-review-v1.2.md
│   ├── roadmap-v1.2.md
│   └── export-budget-v1.2.md   # How MAX_EXPORT_CELLS was measured
├── .github/workflows/ci.yml    # lint, format, tests, JS assertions, pip-audit
├── pyproject.toml       # ruff + pytest configuration
├── requirements.txt     # Runtime dependencies (exact-pinned)
├── requirements-dev.txt # Test/lint tooling
├── requirements-redis.txt  # Optional Redis client for shared rate-limit storage
├── .env.example         # Every environment variable with its default
├── Makefile             # test / test-js / lint / format / audit / coverage / run
├── render.yaml          # Render.com deployment blueprint
├── CHANGELOG.md
├── AGENTS.md            # Agent contract / quick-reference
├── MEMORY.md            # Memory index for AI assistants
├── README.md
└── CLAUDE.md
```

## Tech Stack

- **Backend:** Python 3.11+ (Render deploys with 3.14.5), Flask 3.1.3 (app factory pattern)
- **Frontend:** Vanilla HTML/CSS/JavaScript (no frameworks, no build step)
- **Security:** Flask-WTF 1.2.1 (CSRF), Flask-Limiter 3.5.0 (rate limiting)
- **HTTP client:** requests 2.33.0
- **Excel export:** openpyxl 3.1.5
- **Production server:** gunicorn 22.0.0
- **Testing:** pytest 9.0.3 (dev deps in `requirements-dev.txt`); Node assertions for `app.js`
- **Deployment:** Render.com (free tier; auto-deploy gated on CI via `autoDeployTrigger: checksPass`)
- **App version:** 1.2.0 (`config.APP_VERSION`, exposed via `/health`)

## Development Setup

```bash
python -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

The dev server runs at `http://localhost:5000`. Debug mode is controlled by the `FLASK_DEBUG` env var (default: off).

```bash
export FLASK_DEBUG=1
python app.py
```

## Architecture

### Backend Modules

**`app.py`** — App factory (`create_app()`): loads config, initializes CSRF + rate limiter, registers the `apply_security_headers` `after_request` hook, and registers the route blueprint.

**`config.py`** — All settings read from environment variables with sensible defaults. See Configuration section below.

**`extensions.py`** — Shared Flask extension instances (`CSRFProtect`, `Limiter` keyed by remote address) to avoid circular imports.

**`security.py`** — Two functions:
- `validate_url(url)` — SSRF protection: validates scheme (http/https), resolves DNS via `getaddrinfo`, rejects any non-global or multicast IP across all resolved addresses. Returns `(is_valid, error_message_or_none)`.
- `apply_security_headers(response)` — Adds CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy.

**`helpers.py`** — Data processing:
- `flatten_for_csv(data, parent_key, sep, _depth, max_depth)` — Recursively flattens nested dicts (dot notation). Lists are serialized via `json.dumps`. Stops recursing at `max_depth`.
- `flatten_rows(rows, max_depth)` — Flattens every row and accumulates column names in one pass; returns `(rows, sorted_columns)`. Replaces flatten-then-`get_all_columns`.
- `extract_table_data(json_data, _depth, max_depth)` — Extracts tabular rows from various JSON shapes (top-level array, dict containing an array of objects, nested dicts, or a single object). Depth-capped like `flatten_for_csv`.
- `sanitize_cell(value)` / `serialize_cell_value(value)` / `is_formula_trigger(value)` — Formula-injection defenses for **spreadsheet formats only** (CSV/TSV/XLSX). JSONL and Markdown exports must not use them.
- `preview_truncate(row)` — Builds a capped **copy** of a preview row (long strings, wide nested objects/arrays). Never mutates the source, so exports stay full-fidelity.
- `format_size(num_bytes)` — Renders a byte count in the largest non-zero unit. Lives here, not in `app.py`, so `routes.py` can use it without importing `app.py` (that cycle broke every routes-first import).
- `get_all_columns(data)` — Returns sorted unique column names across rows.
- `parse_jsonl(text)` — Parses JSON Lines (one JSON value per non-empty line), raising `ValueError` with line numbers on errors.
- `extract_by_path(json_data, path)` — Navigates JSON by dot-notation path (`(root)` returns the document itself).

**`routes.py`** — Flask Blueprint (`bp`):
- `GET /` — Serves `index.html`.
- `GET /health` — Returns `{"status": "ok", "version": APP_VERSION}` for monitoring (`version` omitted when `HEALTH_REVEAL_VERSION=0`).
- `GET /health/live` — Liveness. Checks nothing on purpose, so a failing dependency cannot cause a restart loop.
- `GET /health/ready` — Readiness. 200, or 503 with a `checks` map when the limiter storage or the Excel writer is unusable.
- `POST /process` — Parses JSON/JSONL from file/paste/API, returns preview + full CSV-ready data. Returns `{"needs_selection": true, "raw_json": ...}` when no `json_path` was provided, so the client can render the JSON tree picker. Rate-limited via `RATE_LIMIT_PROCESS`. Body is assembled by `_load_input()` and `_select_table_data()`.
- `POST /export-csv` — Generator-streamed CSV, deliberately **uncapped**. Rate-limited via `RATE_LIMIT_EXPORT`.
- `POST /export-xlsx` — Server-side Excel via openpyxl, capped by `MAX_EXPORT_CELLS` (400 when exceeded — never truncated). Writes no OS temp files. Rate-limited via `RATE_LIMIT_EXPORT`.

The `/process` success payload is `{success, columns, preview, preview_limit, total_rows, total_cells, max_export_cells, csv_data, csv_columns}`.

API-fetch specifics: `requests.get` is called with `stream=True`, `allow_redirects=False`, and a streaming size cap. The outbound header **name** is checked against an allowlist. Failures log a fixed string with no interpolation — the exception text contains the full URL, and a token can ride in the query string, fragment, userinfo *or* path.

### Frontend

**`static/css/style.css`** — Dark theme (default) and light theme via `:root.light` CSS custom property overrides. Includes component styles, sort indicators, modal, export dropdown, theme toggle, and utility classes.

**`static/js/app.js`** — Vanilla JavaScript:
- CSRF token management (meta tag → FormData / X-CSRFToken header)
- Tab switching, file drag-drop, auth method selection, format toggle (JSON/JSONL)
- Client-side column sorting (click headers, asc/desc toggle), row filtering, "load more" pagination and column visibility toggles
- Client-side CSV, TSV, JSONL and Markdown export (no server round-trip needed)
- Server-side Excel export via `/export-xlsx`, greyed out ahead of time when `total_cells > max_export_cells`
- Theme detection (`prefers-color-scheme`) with localStorage override
- Lazily-built JSON tree picker modal for choosing which node becomes the table, with `#path=` deep links
- In-page About modal (no `alert()`), and a keyboard-accessible export dropdown

**`templates/index.html`** — HTML structure only. References external CSS/JS via `url_for('static', ...)`. Includes CSRF meta tag, theme toggle button, format selector, export dropdown, and path selector modal. No inline scripts or styles (CSP enforced).

### Data Flow

1. User provides JSON/JSONL (file / paste / API URL with optional auth).
2. Server validates input (SSRF check for API URLs, UTF-8 decoding, JSON/JSONL parsing, size caps).
3. If no `json_path` is supplied, the server returns `raw_json` so the UI can render a tree picker and let the user choose a node.
4. Server returns `preview` (first `PREVIEW_ROW_LIMIT` rows, as a truncated **copy**) plus full-fidelity `csv_data` / `csv_columns` and the export budget.
5. Frontend renders the sortable preview table; nested objects render as mini tables, with render caps.
6. Response bodies over `GZIP_MIN_SIZE` are gzipped.
7. Export: CSV/TSV/JSONL/Markdown generated client-side instantly; Excel via the server endpoint.

## Configuration

All settings live in `config.py`, configurable via environment variables:

| Setting | Env Var | Default | Description |
|---------|---------|---------|-------------|
| Secret key | `SECRET_KEY` | `dev-secret-key-change-in-production` | Flask/CSRF secret. The app **refuses to start** on the default when `APP_ENV=production` |
| Production signal | `APP_ENV` | unset | `production` is the single canonical signal (fail-fast, `Secure` cookie, topology guard). No alias is accepted |
| Max upload size | `MAX_UPLOAD_SIZE` | 10 MB | Request body limit |
| Preview rows | `PREVIEW_ROW_LIMIT` | 25 | Rows shown in preview table |
| API timeout | `API_FETCH_TIMEOUT` | 30s | Timeout for external API requests. Must stay below gunicorn's `--timeout` |
| API max response | `API_FETCH_MAX_RESPONSE` | 10 MB | Max size for streamed API responses |
| API ports | `API_ALLOWED_PORTS` | `80,443,8443` | Ports API fetch may connect to. Empty disables the check |
| DNS wait | `API_DNS_TIMEOUT` | 3s | Bounds how long a **request** waits, not the lookup |
| DNS workers | `API_DNS_MAX_WORKERS` | 4 | Concurrent lookups; this is the worker-starvation fix |
| DNS admission | `API_DNS_ADMISSION_TIMEOUT` | 1s | Wait for a permit before rejecting fast |
| Flatten depth | `FLATTEN_MAX_DEPTH` | 10 | Max recursion depth for flattening and extraction |
| Excel budget | `MAX_EXPORT_CELLS` | 250000 | XLSX-only cap in cells (`rows × columns`). `0` disables. CSV/TSV stay uncapped |
| Static cache | `STATIC_MAX_AGE` | 86400 | `Cache-Control` max-age for static assets (URLs carry `?v=APP_VERSION`) |
| gzip threshold | `GZIP_MIN_SIZE` | 1024 | Smallest body worth compressing |
| Health version | `HEALTH_REVEAL_VERSION` | on | `0` omits `version` from the health endpoints |
| Trust proxy | `TRUST_PROXY` | off | `1` installs `ProxyFix` for exactly one hop |
| Rate limit storage | `RATELIMIT_STORAGE_URI` | `memory://` | Counters are **process-local**; shared storage is required above 1 worker × 1 instance |
| Workers | `WEB_CONCURRENCY` | 1 | Single source of truth; start commands pass `--workers "$WEB_CONCURRENCY"`. Required under `APP_ENV=production` |
| Replicas | `APP_REPLICAS` | 1 | Mirrors `render.yaml`'s `numInstances`. Required under `APP_ENV=production` |
| Rate limit (default) | `RATE_LIMIT_DEFAULT` | 120/minute | Global default rate limit |
| Rate limit (process) | `RATE_LIMIT_PROCESS` | 30/minute | Rate limit on `/process` |
| Rate limit (export) | `RATE_LIMIT_EXPORT` | 60/minute | Rate limit on export endpoints |
| Debug mode | `FLASK_DEBUG` | off | Enable Flask debug mode |

`.env.example` lists every variable with its default. Rate-limiter storage defaults to `memory://`, whose counters are **process-local** — the effective limit is multiplied by `workers × replicas`, so any deployment above one worker and one instance must set a shared `RATELIMIT_STORAGE_URI` (install `requirements-redis.txt`). Under `APP_ENV=production` the app refuses to start otherwise.

## Security

- **CSRF:** `Flask-WTF` `CSRFProtect` on all POST routes. Token via meta tag + FormData / `X-CSRFToken` header.
- **SSRF:** DNS-validated URL checking blocks private, loopback, link-local, multicast, and other non-global IPs (including cloud metadata endpoints). The original URL is preserved for the actual request so TLS/SNI verification still works; `allow_redirects=False` prevents redirect-based bypass.
- **Rate limiting:** In-memory `Flask-Limiter`, configurable per-route.
- **Headers:** Strict `Content-Security-Policy` (self-only scripts; styles/fonts may load Google Fonts), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`.
- **Input validation:** UTF-8 decoding required for file uploads; JSON/JSONL parse errors return 400; API response size cap enforced while streaming.
- **Error sanitization:** Internal exceptions are logged but external responses use generic messages (e.g., `"API request failed"`).
- **No data persistence:** No database, no log of payloads, no session storage of user data.

## Testing

The passing command is the criterion, not a test count:

```bash
python -m pytest tests/ -v      # or: make test
```

Test files:
- `tests/test_helpers.py` — `flatten_for_csv`, `flatten_rows`, `extract_table_data` (incl. the depth guard), `get_all_columns`, `parse_jsonl`, `extract_by_path`, `preview_truncate`.
- `tests/test_security.py` — URL validation with mocked DNS, private/loopback/link-local IP blocking, scheme checks, the port allowlist, and the bounded DNS resolver (admission limit, permit accounting, fork lifecycle, and the *accepted* unbounded teardown).
- `tests/test_routes.py` — All route integration tests: security headers, JSONL, path selection, exports, formula injection, log hygiene via `caplog`, gzip, the config gates (`APP_ENV`, SECRET_KEY, integer validation), the rate-limit topology guard, and the health split.
- `tests/js/*.mjs` — Node assertions that load the real `static/js/app.js` in a stubbed DOM (`dom_stub.mjs`) and exercise the client export, render-cap and feature code. No build step and no npm dependencies; run with `make test-js`.

Fixtures in `tests/conftest.py` provide `app` (with `TESTING=True` and `WTF_CSRF_ENABLED=False`) and `client`. `tests/test_routes.py` adds a `fresh_config` fixture that reloads `config` under a patched environment, because `Config` holds class attributes evaluated at import time.

## Linting / Formatting

`ruff`, configured in `pyproject.toml` (target py311, line length 100, Python files only):

```bash
ruff check .            # or: make lint
ruff format --check .
ruff format .           # or: make format
```

CI runs lint, format-check, pytest, the Node assertions, and `pip-audit -r requirements.txt`.

## Deployment

### Production Requirements (All Methods)

- Set `APP_ENV=production`. This is the single canonical production signal.
- Set `SECRET_KEY` to a random value. With `APP_ENV=production` the app **refuses
  to start** on the dev default, an empty value, or an unset one.
- Set `FLASK_DEBUG=0`.
- Declare `WEB_CONCURRENCY` and `APP_REPLICAS`, and derive the start command's
  `--workers` from `$WEB_CONCURRENCY`. Above one worker or one instance, set a
  shared `RATELIMIT_STORAGE_URI` (and install `requirements-redis.txt`) — the app
  refuses to start otherwise, because `memory://` counters are process-local.
- Set gunicorn's `--timeout` above `API_FETCH_TIMEOUT` (60 vs 30 by default).
- Use HTTPS (TLS termination via Nginx, cloud provider, or reverse proxy). Set
  `TRUST_PROXY=1` behind a proxy you control so rate limiting and `Secure`
  cookies see the real client and scheme.

### Render.com (PaaS)

Configured via `render.yaml` blueprint:
- Runtime: Python 3.14.5
- Build: `pip install -r requirements.txt`
- Start: `gunicorn "app:create_app()" --bind 0.0.0.0:$PORT --workers "$WEB_CONCURRENCY" --timeout 60`
- `SECRET_KEY` is generated by Render; `APP_ENV=production`, `WEB_CONCURRENCY=1`
  and `APP_REPLICAS=1` are declared in the blueprint; `numInstances: 1`.
- `autoDeployTrigger: checksPass` — a push with failing or missing CI checks does
  not deploy. Free tier; no persistent storage.

### Own Server (Gunicorn + Systemd + Nginx)

1. **Gunicorn** runs the app: `gunicorn "app:create_app()" --bind 127.0.0.1:8000 --workers "$WEB_CONCURRENCY" --timeout 60`
2. **Systemd** manages the process (auto-restart, boot start) — see `README.md` for the unit file.
3. **Nginx** reverse-proxies and handles TLS termination; can also serve `/static/` directly.

Key config: bind gunicorn to `127.0.0.1` (not `0.0.0.0`) when behind Nginx.

### Docker

```bash
docker build -t json-table-tool .
docker run -p 8000:8000 -e SECRET_KEY="..." json-table-tool
```

Note: no `Dockerfile` is checked in yet — see `README.md` for Dockerfile and docker-compose.yml templates. The gunicorn command must use `"app:create_app()"` (app factory pattern).

### Other PaaS

Railway.app and Fly.io are also supported — see `README.md` for CLI commands.

## Common Tasks

### Adding a new route
Add the handler to `routes.py` on the `bp` Blueprint. Apply `@limiter.limit()` if needed (use a lambda reading from `current_app.config` to keep the limit configurable). Follow existing patterns: `jsonify()` for responses, try/except around external calls, generic error messages with proper HTTP status codes. Re-raise `HTTPException` before the generic `except Exception` so Flask's JSON error handlers still run. If the route returns payload data, add its endpoint to `security.NO_STORE_ENDPOINTS`.

### Modifying the UI
- **CSS:** Edit `static/css/style.css`. Use existing CSS custom properties. Add light-theme overrides under `:root.light` if needed.
- **JS:** Edit `static/js/app.js`. Attach the CSRF token on every POST.
- **HTML:** Edit `templates/index.html`. Structure only — no inline styles or scripts (CSP enforced).

### Adding a new auth method for API fetch
1. Add an option to the `auth_method` select in `index.html`.
2. Add the form fields inside a `data-auth="method_name"` div.
3. Handle the new method in `routes.py` inside the `auth_method` conditional block.
4. Add the JS visibility toggle in `app.js` (auth-method switching section).

### Adding a new export format
1. **Decide the sanitization policy first.** Spreadsheet-compatible formats
   (anything a spreadsheet will open and evaluate) must route every cell through
   `helpers.sanitize_cell`, or pin the cell type if the format has one. Lossless
   or plain-text formats (JSONL, Markdown) must **not** — a quote prefix would
   corrupt the data while protecting nothing. See MEMORY.md, 2026-08-21.
2. Client-side: add a `build*Chunks()` builder in `app.js` and dispatch it from
   the export-dropdown handler. Return chunks, not one giant string.
3. Server-side (if needed): add a route in `routes.py`. Stream it with a
   generator unless the format genuinely cannot be streamed; if it cannot, give
   it a measured budget the way `MAX_EXPORT_CELLS` works, and never truncate —
   refuse with a 400 and advertise the limit from `/process`.
4. Add the button to the export dropdown in `index.html` with
   `role="menuitem"`.
5. Add assertions to `tests/js/test_features.mjs` covering the sanitization
   decision explicitly, in both directions.
6. Add any new dependency to `requirements.txt` with an exact pin.

### Changing configuration defaults
Edit `config.py`. Read integers through `env_int()` (and integer lists through
`env_int_set()`) so a typo names the variable instead of raising a bare
`ValueError` at import. Add the variable to `.env.example`, the table above, and
the README table. Gate any production-only behavior on `is_production()` — never
on `not DEBUG`, and never on a second env-var spelling.

### Adding a dependency
Add to `requirements.txt` with an exact pin (e.g. `package==1.2.3`). Test and
lint tooling goes in `requirements-dev.txt`; anything only a specific deployment
shape needs goes in its own file (see `requirements-redis.txt`). Re-run
`pip-audit -r requirements.txt` and the full suite in the same commit — the
convention is a dedicated bump commit, not a bump ridden along with a feature.

### Re-deriving the Excel export budget
`MAX_EXPORT_CELLS` is a measured number, not a chosen one. Follow the method in
`docs/export-budget-v1.2.md` (fresh process per measured request, `ru_maxrss`
converted for the platform, delta across two runs), re-fit against the narrowest
aspect ratio you care about, and re-run a confirming point at the value you
intend to ship. Record the new data in that file.
