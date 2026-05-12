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
| Web framework     | Flask 3.0.0 (app factory)                                      |
| Security libs     | Flask-WTF 1.2.1 (CSRF), Flask-Limiter 3.5.0 (rate limit)       |
| HTTP client       | requests 2.31.0                                                |
| Excel export      | openpyxl 3.1.2                                                 |
| WSGI server       | gunicorn 21.2.0 — invoked as `gunicorn "app:create_app()"`     |
| Test runner       | pytest 7.4.4                                                   |
| Frontend          | HTML + external CSS/JS (no framework, no build)                |
| Deployment        | Render (free tier) via `render.yaml`; also docs for Docker/Nginx |
| App version       | `Config.APP_VERSION = '1.1.0'` (returned by `/health`)         |

## Setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
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

- **`app.py`** — `create_app(config_class=Config)` factory. Initializes CSRF + Limiter, registers `apply_security_headers` as an `after_request` middleware, registers the `routes.bp` Blueprint. Module-level `app = create_app()` exists for tooling that expects it, but production uses the factory directly.
- **`config.py`** — `Config` class; every setting reads from `os.environ.get(...)` with a default. Includes `SECRET_KEY`, `MAX_CONTENT_LENGTH`, `PREVIEW_ROW_LIMIT`, `API_FETCH_TIMEOUT`, `API_FETCH_MAX_RESPONSE`, `FLATTEN_MAX_DEPTH`, `RATELIMIT_*`, `APP_VERSION`, `DEBUG`.
- **`extensions.py`** — Bare `CSRFProtect()` and `Limiter(key_func=get_remote_address)` instances, bound by `app.py` via `init_app`. Importing this module never has side effects on the Flask app — that's the point.
- **`security.py`**
  - `validate_url(url)` — returns `(is_valid, error_or_none)`. Rejects non-http(s) schemes, missing hostname, non-resolvable hostnames, and any resolved IP where `not ip.is_global or ip.is_multicast`.
  - `apply_security_headers(response)` — sets CSP (strict, `script-src 'self'`), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`. CSP allows Google Fonts (style/font) and `data:` images.
- **`helpers.py`**
  - `flatten_for_csv(data, parent_key='', sep='.', _depth=0, max_depth=10)` — depth-capped recursion; deep nesting is JSON-stringified instead of stack-overflowing.
  - `extract_table_data(json_data)` — heuristic: list-of-dicts → use directly; dict with array value → that array; nested dicts → recurse; otherwise single-row.
  - `parse_jsonl(text)` — line-by-line JSON; raises `ValueError` with the offending line number.
  - `find_candidate_arrays(json_data, prefix='', candidates=None)` — discovers every array-of-objects with `{path, length, sample_keys}` metadata so the frontend can prompt the user.
  - `extract_by_path(json_data, path)` — dot-notation navigation; `'(root)'` is the sentinel for top-level lists.
  - `get_all_columns(data)` — sorted union of keys.
- **`routes.py`** — Blueprint `bp`. Routes:
  - `GET /` → `templates/index.html`.
  - `GET /health` → `{"status": "ok", "version": APP_VERSION}`.
  - `POST /process` → rate-limited (default `RATE_LIMIT_PROCESS=30/min`). Reads `input_method` (`file`/`paste`/`api`), `data_format` (`json`/`jsonl`), optional `json_path`. Returns `{success, columns, preview, total_rows, csv_data, csv_columns}` **or** `{needs_selection: true, candidates: [...]}` when multiple arrays found and no `json_path` selected.
  - `POST /export-csv` → rate-limited (default `RATE_LIMIT_EXPORT=60/min`). Server-side CSV fallback.
  - `POST /export-xlsx` → rate-limited. Server-side Excel via openpyxl.

### Frontend

- **`templates/index.html`** — pure structure. CSRF meta tag at the top (`<meta name="csrf-token" content="{{ csrf_token() }}">`). References `style.css` and `app.js` via `url_for('static', ...)`. No inline JS/CSS (CSP would block it).
- **`static/css/style.css`** — `:root` (dark, default) + `:root.light` overrides. All component styles, sort indicators, modal, export dropdown, theme toggle.
- **`static/js/app.js`** — reads CSRF token from meta tag; attaches it to FormData and `X-CSRFToken`. Handles tab switching, drag-drop, JSON/JSONL toggle, auth method visibility, client-side sort, **client-side** CSV/TSV download, **server-side** Excel via `/export-xlsx`, theme persistence in `localStorage`, and the path-selection modal triggered by `needs_selection: true`.

### Tests

- **`tests/conftest.py`** — provides `app` (with `TESTING=True`, `WTF_CSRF_ENABLED=False`) and `client` fixtures.
- **`tests/test_helpers.py`** — pure-function tests for the data-processing layer.
- **`tests/test_security.py`** — `validate_url` with mocked `socket.getaddrinfo`; verifies private-IP/loopback/link-local rejection.
- **`tests/test_routes.py`** — integration tests for every route, including security headers, JSONL, path selection, Excel export.

### Deploy / Config

- **`render.yaml`** — Render Blueprint. `startCommand: gunicorn "app:create_app()" --bind 0.0.0.0:$PORT`. `SECRET_KEY` is `generateValue: true` so Render auto-fills it.
- **`requirements.txt`** — exact-pinned. Don't loosen.

## Conventions

### Do

- Return JSON `{"error": "..."}` with a 4xx/5xx status for backend failure paths.
- Use `logger.warning(...)` / `logger.exception(...)` for server-side issues — do **not** log request bodies.
- Apply `@limiter.limit(lambda: current_app.config.get('RATE_LIMIT_...'))` on any new mutating route.
- Read config via `current_app.config['KEY']`, not by re-importing `Config` at request time.
- For new auth methods on the API tab: add a select option in `index.html`, a `data-auth="..."` fieldset, the JS visibility branch in `app.js`, and the conditional in `routes.py`.
- For new exports: add the entry to the export dropdown, the handler in `app.js`, optionally a server route in `routes.py`. Pin any new dependency.
- Add or update tests under `tests/` for any backend behavior change. Class-style grouping (`class TestXxx:`) is the existing pattern.
- Preserve the CSP. If new third-party CSS/fonts are needed, edit `apply_security_headers` deliberately.

### Don't

- Don't add inline `<script>` blocks, `style="..."` attributes, or `onclick=` handlers in the HTML — CSP blocks them.
- Don't `app:app` in gunicorn args; the production command is `app:create_app()` (factory).
- Don't remove `allow_redirects=False` on the outbound `requests.get` — the SSRF guard only validated the *original* URL.
- Don't unbound the streamed download — `API_FETCH_MAX_RESPONSE` (10 MB default) is enforced inside the chunk loop.
- Don't lower `FLATTEN_MAX_DEPTH` recursion guard without checking known payload shapes.
- Don't log full exceptions to the response — the routes intentionally return generic messages and `logger.exception(...)` for server logs.
- Don't use the dev `SECRET_KEY` in production. Render generates one via `render.yaml`; for other deployments set the env var.

## Verification Checklist (before reporting a task done)

- [ ] `python -m pytest tests/ -v` passes.
- [ ] `python app.py` starts cleanly; `GET /` renders; `GET /health` returns the current `APP_VERSION`.
- [ ] CSP headers still present (`curl -sI http://localhost:5000/ | findstr /i security` or browser DevTools).
- [ ] CSRF still required on POSTs (a POST without the token returns 400 from Flask-WTF).
- [ ] All three input methods (file / paste / API), both formats (JSON / JSONL), and all four auth methods still work end to end.
- [ ] Multi-array JSON triggers the path-selector modal; selecting a path returns rows.
- [ ] CSV (client-side), TSV (client-side), and XLSX (server-side) all download with full row counts, not just 25.
- [ ] SSRF guard blocks `http://127.0.0.1`, `http://localhost`, `http://169.254.169.254`, and similar private IPs.
- [ ] Rate limit kicks in at the configured threshold (manual: rapid-fire `/process`).
- [ ] No new file writes, DB calls, payload logging, or inline JS/CSS were introduced.
- [ ] Any new dependency is **exact-pinned** in `requirements.txt`.

## When in Doubt

1. Re-read `CLAUDE.md` and this file.
2. Skim `MEMORY.md` for prior decisions on the area you're touching.
3. If the task implies persistence, telemetry, weaker CSP, or a frontend framework: **stop and ask the user first** — those are deliberate "no"s, not oversights.

## Tooling Notes for Specific Agents

- **Claude Code**: prefer `Edit` over `Write` for `app.py`, `routes.py`, `helpers.py`, `static/js/app.js`, `static/css/style.css`, and `templates/index.html` (all read-then-edit targets). Use `Grep` instead of shell `grep`. PowerShell is the default shell on this machine; Bash is available.
- **Cursor / Aider / Copilot Workspace**: respect the modular split — there's a reason `extensions.py` is its own module (circular-import avoidance). Auto-collapse refactors that re-merge modules will break the test fixtures.
- **Any agent**: if you generate code the user did not request (helper modules, type stubs, scratch files), delete it before finishing the task.
