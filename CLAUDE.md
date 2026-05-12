# CLAUDE.md

This file provides guidance for AI assistants working with the JSON Table Converter codebase.

## Project Overview

A lightweight Flask web application that converts JSON/JSONL data into viewable HTML tables with multi-format export (CSV, TSV, Excel). Designed as a stateless, privacy-first internal tool with no data persistence.

**Key features:** file upload (drag-and-drop), paste JSON/JSONL, fetch from external APIs (with auth support), nested data expansion, JSON path selector for multi-array data, client-side column sorting, light/dark theme, CSV/TSV/Excel export.

## Project Structure

```
json-table-tool/
├── app.py               # Flask app factory, middleware registration
├── config.py            # All settings via environment variables
├── extensions.py        # Flask-WTF (CSRF) and Flask-Limiter instances
├── security.py          # SSRF protection (DNS validation) + security headers
├── helpers.py           # Data processing (flatten, extract, JSONL parse, path selector)
├── routes.py            # Flask Blueprint with all route handlers
├── static/
│   ├── css/
│   │   └── style.css    # All CSS (dark/light themes, components, utilities)
│   └── js/
│       └── app.js       # All JavaScript (UI, sorting, export, theme, modal)
├── templates/
│   └── index.html       # HTML structure only (refs external CSS/JS)
├── tests/
│   ├── conftest.py      # Shared pytest fixtures (app, client)
│   ├── test_helpers.py  # Tests for data processing functions
│   ├── test_security.py # Tests for SSRF validation
│   └── test_routes.py   # Integration tests for all routes
├── docs/
│   └── code-health-final.md
├── requirements.txt     # Python dependencies (pinned versions)
├── render.yaml          # Render.com deployment blueprint
├── AGENTS.md            # Agent contract / quick-reference
├── MEMORY.md            # Memory index for AI assistants
├── README.md
└── CLAUDE.md
```

## Tech Stack

- **Backend:** Python 3.11+ (Render deploys with 3.14.5), Flask 3.0.0 (app factory pattern)
- **Frontend:** Vanilla HTML/CSS/JavaScript (no frameworks, no build step)
- **Security:** Flask-WTF 1.2.1 (CSRF), Flask-Limiter 3.5.0 (rate limiting)
- **HTTP client:** requests 2.31.0
- **Excel export:** openpyxl 3.1.2
- **Production server:** gunicorn 21.2.0
- **Testing:** pytest 7.4.4
- **Deployment:** Render.com (free tier, auto-deploy on push)
- **App version:** 1.1.0 (`config.APP_VERSION`, exposed via `/health`)

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
- `extract_table_data(json_data)` — Extracts tabular rows from various JSON shapes (top-level array, dict containing an array of objects, nested dicts, or a single object).
- `get_all_columns(data)` — Returns sorted unique column names across rows.
- `parse_jsonl(text)` — Parses JSON Lines (one JSON value per non-empty line), raising `ValueError` with line numbers on errors.
- `find_candidate_arrays(json_data)` — Discovers arrays of objects with their `path`, `length`, and first 5 `sample_keys` (used for the multi-array selector modal).
- `extract_by_path(json_data, path)` — Navigates JSON by dot-notation path (`(root)` returns the document itself).

**`routes.py`** — Flask Blueprint (`bp`):
- `GET /` — Serves `index.html`.
- `GET /health` — Returns `{"status": "ok", "version": APP_VERSION}` for monitoring.
- `POST /process` — Parses JSON/JSONL from file/paste/API, returns preview + full CSV-ready data. Returns `{"needs_selection": true, "candidates": [...]}` if multiple arrays found and no `json_path` was provided. Rate-limited via `RATE_LIMIT_PROCESS`.
- `POST /export-csv` — Server-side CSV generation (fallback). Rate-limited via `RATE_LIMIT_EXPORT`.
- `POST /export-xlsx` — Server-side Excel generation via openpyxl. Rate-limited via `RATE_LIMIT_EXPORT`.

API-fetch specifics: `requests.get` is called with `stream=True`, `allow_redirects=False`, and a streaming size cap. Errors are logged but the user-facing message is a generic `"API request failed"` to avoid leaking internal hostnames.

### Frontend

**`static/css/style.css`** — Dark theme (default) and light theme via `:root.light` CSS custom property overrides. Includes component styles, sort indicators, modal, export dropdown, theme toggle, and utility classes.

**`static/js/app.js`** — Vanilla JavaScript:
- CSRF token management (meta tag → FormData / X-CSRFToken header)
- Tab switching, file drag-drop, auth method selection, format toggle (JSON/JSONL)
- Client-side column sorting (click headers, asc/desc toggle)
- Client-side CSV/TSV export (no server round-trip needed)
- Server-side Excel export via `/export-xlsx`
- Theme detection (`prefers-color-scheme`) with localStorage override
- Path selector modal when multiple candidate arrays are detected

**`templates/index.html`** — HTML structure only. References external CSS/JS via `url_for('static', ...)`. Includes CSRF meta tag, theme toggle button, format selector, export dropdown, and path selector modal. No inline scripts or styles (CSP enforced).

### Data Flow

1. User provides JSON/JSONL (file / paste / API URL with optional auth).
2. Server validates input (SSRF check for API URLs, UTF-8 decoding, JSON/JSONL parsing, size caps).
3. If multiple candidate arrays found and no `json_path` is supplied, server returns the candidates so the UI can prompt the user to pick one.
4. Server returns `preview` (first `PREVIEW_ROW_LIMIT` rows) plus full `csv_data` / `csv_columns`.
5. Frontend renders the sortable preview table; nested objects render as mini tables.
6. Export: CSV/TSV generated client-side instantly; Excel via the server endpoint.

## Configuration

All settings live in `config.py`, configurable via environment variables:

| Setting | Env Var | Default | Description |
|---------|---------|---------|-------------|
| Secret key | `SECRET_KEY` | `dev-secret-key-change-in-production` | Flask/CSRF secret (change in production) |
| Max upload size | `MAX_UPLOAD_SIZE` | 10 MB | Request body limit |
| Preview rows | `PREVIEW_ROW_LIMIT` | 25 | Rows shown in preview table |
| API timeout | `API_FETCH_TIMEOUT` | 30s | Timeout for external API requests |
| API max response | `API_FETCH_MAX_RESPONSE` | 10 MB | Max size for streamed API responses |
| Flatten depth | `FLATTEN_MAX_DEPTH` | 10 | Max recursion depth for CSV flattening |
| Rate limit (default) | `RATE_LIMIT_DEFAULT` | 120/minute | Global default rate limit |
| Rate limit (process) | `RATE_LIMIT_PROCESS` | 30/minute | Rate limit on `/process` |
| Rate limit (export) | `RATE_LIMIT_EXPORT` | 60/minute | Rate limit on export endpoints |
| Debug mode | `FLASK_DEBUG` | off | Enable Flask debug mode |

Rate-limiter storage is in-memory (`RATELIMIT_STORAGE_URI = 'memory://'`); switch to Redis if running multiple workers and you want shared counters.

## Security

- **CSRF:** `Flask-WTF` `CSRFProtect` on all POST routes. Token via meta tag + FormData / `X-CSRFToken` header.
- **SSRF:** DNS-validated URL checking blocks private, loopback, link-local, multicast, and other non-global IPs (including cloud metadata endpoints). The original URL is preserved for the actual request so TLS/SNI verification still works; `allow_redirects=False` prevents redirect-based bypass.
- **Rate limiting:** In-memory `Flask-Limiter`, configurable per-route.
- **Headers:** Strict `Content-Security-Policy` (self-only scripts; styles/fonts may load Google Fonts), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`.
- **Input validation:** UTF-8 decoding required for file uploads; JSON/JSONL parse errors return 400; API response size cap enforced while streaming.
- **Error sanitization:** Internal exceptions are logged but external responses use generic messages (e.g., `"API request failed"`).
- **No data persistence:** No database, no log of payloads, no session storage of user data.

## Testing

82 tests using pytest:

```bash
python -m pytest tests/ -v
```

Test files:
- `tests/test_helpers.py` (31 tests) — `flatten_for_csv`, `extract_table_data`, `get_all_columns`, `parse_jsonl`, `find_candidate_arrays`, `extract_by_path`.
- `tests/test_security.py` (16 tests) — URL validation with mocked DNS, private/loopback/link-local IP blocking, scheme checks.
- `tests/test_routes.py` (35 tests) — All route integration tests, security headers, JSONL, path selection, API-fetch SSRF/size/timeout/error-leak coverage, CSV/Excel export edge cases.

Fixtures in `tests/conftest.py` provide `app` (with `TESTING=True` and `WTF_CSRF_ENABLED=False`) and `client`.

## Linting / Formatting

No linting tools currently configured. Recommended: `ruff` for linting + formatting.

## Deployment

### Production Requirements (All Methods)

- Set `SECRET_KEY` to a random value (never use the dev default).
- Set `FLASK_DEBUG=0`.
- Use HTTPS (TLS termination via Nginx, cloud provider, or reverse proxy).

### Render.com (PaaS)

Configured via `render.yaml` blueprint:
- Runtime: Python 3.14.5
- Build: `pip install -r requirements.txt`
- Start: `gunicorn "app:create_app()" --bind 0.0.0.0:$PORT`
- `SECRET_KEY` is generated by Render; auto-deploy on push; free tier; no persistent storage.

### Own Server (Gunicorn + Systemd + Nginx)

1. **Gunicorn** runs the app: `gunicorn "app:create_app()" --bind 127.0.0.1:8000 --workers 4`
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
Add the handler to `routes.py` on the `bp` Blueprint. Apply `@limiter.limit()` if needed (use a lambda reading from `current_app.config` to keep the limit configurable). Follow existing patterns: `jsonify()` for responses, try/except around external calls, generic error messages with proper HTTP status codes.

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
1. Client-side: add a handler in `app.js` (extend `downloadDelimited()` or add a new function).
2. Server-side: add a route in `routes.py` and a button in the export dropdown.
3. Add any new dependency to `requirements.txt` with a pinned version.

### Changing configuration defaults
Edit `config.py`. All values read from `os.environ.get()` with defaults.

### Adding a dependency
Add to `requirements.txt` with a pinned version (e.g., `package==1.2.3`).
