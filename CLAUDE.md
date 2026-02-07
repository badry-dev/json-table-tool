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
├── requirements.txt     # Python dependencies (pinned versions)
├── render.yaml          # Render.com deployment blueprint
├── .gitignore
├── README.md
└── CLAUDE.md
```

## Tech Stack

- **Backend:** Python 3.11+, Flask 3.0.0 (app factory pattern)
- **Frontend:** Vanilla HTML/CSS/JavaScript (no frameworks, no build step)
- **Security:** Flask-WTF 1.2.1 (CSRF), Flask-Limiter 3.5.0 (rate limiting)
- **HTTP client:** requests 2.31.0
- **Excel export:** openpyxl 3.1.2
- **Production server:** gunicorn 21.2.0
- **Testing:** pytest 7.4.4
- **Deployment:** Render.com (free tier, auto-deploy on push)

## Development Setup

```bash
python -m venv venv
source venv/bin/activate
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

**`app.py`** — App factory (`create_app()`): loads config, initializes CSRF + rate limiter, registers security headers middleware, registers route blueprint.

**`config.py`** — All settings read from environment variables with sensible defaults. See Configuration section below.

**`extensions.py`** — Shared Flask extension instances (CSRFProtect, Limiter) to avoid circular imports.

**`security.py`** — Two functions:
- `validate_url(url)` — SSRF protection: validates scheme (http/https), resolves DNS, rejects private/reserved/loopback/link-local IPs
- `apply_security_headers(response)` — Adds CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy

**`helpers.py`** — Data processing:
- `flatten_for_csv(data, max_depth)` — Recursively flattens nested dicts (dot notation) with depth limit
- `extract_table_data(json_data)` — Extracts tabular rows from various JSON shapes
- `get_all_columns(data)` — Collects unique column names across rows
- `parse_jsonl(text)` — Parses JSON Lines format (one JSON object per line)
- `find_candidate_arrays(json_data)` — Discovers all nested arrays of objects with path/length/sample keys
- `extract_by_path(json_data, path)` — Navigates JSON by dot-notation path

**`routes.py`** — Flask Blueprint with routes:
- `GET /` — Serves main page
- `GET /health` — Returns `{"status": "ok", "version": "..."}` for monitoring
- `POST /process` — Parses JSON/JSONL from file/paste/API, returns preview + CSV data. Returns `needs_selection: true` with candidates if multiple arrays found
- `POST /export-csv` — Server-side CSV generation (fallback)
- `POST /export-xlsx` — Server-side Excel generation via openpyxl

### Frontend

**`static/css/style.css`** — Dark theme (default) and light theme via `:root.light` CSS custom property overrides. Includes component styles, sort indicators, modal, export dropdown, theme toggle, and utility classes.

**`static/js/app.js`** — Vanilla JavaScript:
- CSRF token management (meta tag → FormData / X-CSRFToken header)
- Tab switching, file drag-drop, auth method selection, format toggle (JSON/JSONL)
- Client-side column sorting (click headers, asc/desc toggle)
- Client-side CSV/TSV export (no server round-trip needed)
- Server-side Excel export via /export-xlsx
- Theme detection (prefers-color-scheme) with localStorage override
- Path selector modal when multiple arrays detected

**`templates/index.html`** — HTML structure only. References external CSS/JS via `url_for('static', ...)`. Includes CSRF meta tag, theme toggle button, format selector, export dropdown, and path selector modal.

### Data Flow

1. User provides JSON/JSONL (file / paste / API URL with optional auth)
2. Server validates input (SSRF check for API URLs, format parsing)
3. If multiple candidate arrays found, returns them for user selection via modal
4. Server returns preview (configurable rows) + full flattened data
5. Frontend renders sortable preview table; nested objects show as mini tables
6. Export: CSV/TSV generated client-side instantly; Excel via server endpoint

## Configuration

All settings are in `config.py`, configurable via environment variables:

| Setting | Env Var | Default | Description |
|---------|---------|---------|-------------|
| Secret key | `SECRET_KEY` | `dev-secret-key-...` | Flask/CSRF secret (change in production) |
| Max upload size | `MAX_UPLOAD_SIZE` | 10 MB | Request body limit |
| Preview rows | `PREVIEW_ROW_LIMIT` | 25 | Rows shown in preview table |
| API timeout | `API_FETCH_TIMEOUT` | 30s | Timeout for external API requests |
| API max response | `API_FETCH_MAX_RESPONSE` | 10 MB | Max size for API responses |
| Flatten depth | `FLATTEN_MAX_DEPTH` | 10 | Max recursion depth for CSV flattening |
| Rate limit (process) | `RATE_LIMIT_PROCESS` | 30/minute | Rate limit on /process |
| Rate limit (export) | `RATE_LIMIT_EXPORT` | 60/minute | Rate limit on export endpoints |
| Rate limit (default) | `RATE_LIMIT_DEFAULT` | 120/minute | Default rate limit for all routes |
| Debug mode | `FLASK_DEBUG` | off | Enable Flask debug mode |

## Security

- **CSRF:** Flask-WTF CSRFProtect on all POST routes. Token via meta tag + FormData/header
- **SSRF:** DNS-validated URL checking blocks private IPs, localhost, link-local, cloud metadata endpoints
- **Rate limiting:** In-memory Flask-Limiter, configurable per-route
- **Headers:** Content-Security-Policy (strict, no inline), X-Frame-Options: DENY, X-Content-Type-Options: nosniff, Referrer-Policy
- **Input validation:** File type/size limits, JSON parse error handling, API response size cap
- **No data persistence:** No database, no logs, no session storage

## Testing

66 tests using pytest:

```bash
python -m pytest tests/ -v
```

Test files:
- `tests/test_helpers.py` — flatten, extract, columns, JSONL parsing, path finding
- `tests/test_security.py` — URL validation (mocked DNS), private IP blocking
- `tests/test_routes.py` — All route integration tests, security headers, JSONL, path selection, Excel export

Fixtures in `tests/conftest.py` provide `app` (CSRF disabled for testing) and `client`.

## Linting / Formatting

No linting tools currently configured. Recommended: `ruff` for linting + formatting.

## Deployment

### Production Requirements (All Methods)

- Set `SECRET_KEY` to a random value (never use the dev default)
- Set `FLASK_DEBUG=0`
- Use HTTPS (TLS termination via Nginx, cloud provider, or reverse proxy)

### Render.com (PaaS)

Configured via `render.yaml` blueprint:
- Runtime: Python 3.11
- Build: `pip install -r requirements.txt`
- Start: `gunicorn "app:create_app()" --bind 0.0.0.0:$PORT`
- Auto-deploy on push, free tier, no persistent storage

### Own Server (Gunicorn + Systemd + Nginx)

Direct deployment on any Linux server:

1. **Gunicorn** runs the app: `gunicorn "app:create_app()" --bind 127.0.0.1:8000 --workers 4`
2. **Systemd** manages the process (auto-restart, boot start) — see `README.md` for unit file
3. **Nginx** reverse proxy handles TLS termination and serves `/static/` files directly

Key config: bind gunicorn to `127.0.0.1` (not `0.0.0.0`) when behind Nginx.

### Docker

```bash
docker build -t json-table-tool .
docker run -p 8000:8000 -e SECRET_KEY="..." json-table-tool
```

Note: no `Dockerfile` is checked in yet — see `README.md` for the Dockerfile and docker-compose.yml templates. The gunicorn command must use `"app:create_app()"` (app factory pattern).

### Other PaaS

Railway.app and Fly.io are also supported — see `README.md` for CLI commands.

## Common Tasks

### Adding a new route
Add the route to `routes.py` on the `bp` Blueprint. Apply `@limiter.limit()` if needed. Follow existing patterns: `jsonify()` for data, try/except, error JSON with HTTP status codes.

### Modifying the UI
- **CSS:** Edit `static/css/style.css`. Use existing CSS custom properties. Add light-theme overrides in `:root.light` if needed.
- **JS:** Edit `static/js/app.js`. Attach CSRF token on POST requests.
- **HTML:** Edit `templates/index.html`. Structure only — no inline styles or scripts (CSP enforced).

### Adding a new auth method for API fetch
1. Add option to `auth_method` select in `index.html`
2. Add form fields in a `data-auth="method_name"` div
3. Handle in `routes.py` in the auth_method conditional block
4. Add JS visibility toggle in `app.js` (auth method switching section)

### Adding a new export format
1. For client-side: add handler in `app.js` `downloadDelimited()` or new function
2. For server-side: add route in `routes.py`, add button in export dropdown
3. Add dependency to `requirements.txt` if needed

### Changing configuration defaults
Edit `config.py`. All values read from `os.environ.get()` with defaults.

### Adding a dependency
Add to `requirements.txt` with a pinned version (e.g., `package==1.2.3`).
