# CLAUDE.MD

Guidance for Claude Code and other Claude-based coding agents working in this repository.

## Project Overview

A lightweight Flask web application that converts JSON into a viewable HTML table and supports CSV export. Designed as a small internal utility with a **privacy-first**, **in-memory-only** approach — no database, no persistence, no logs of user data.

### Core Capabilities

- Upload a JSON file (max 10 MB)
- Paste JSON directly into a textarea
- Fetch JSON from an external API with optional auth:
  - API key header (custom header name)
  - HTTP Basic Authentication
  - Bearer token
  - Query parameter token
- Preview the first **25** extracted rows in-browser
- Export **all** processed rows to CSV (flattened — nested objects become dot-paths, arrays are JSON-stringified)
- Process data entirely in memory — nothing is written to disk or a database

## Repository Structure

```
json-table-tool/
├── app.py                       # Flask app: routes, JSON extraction, CSV export
├── csv_export_api_routes.py     # Stray documentation fragment (NOT imported)
├── requirements.txt             # Flask, requests, gunicorn (pinned)
├── render.yaml                  # Render Blueprint config (free tier, Python 3.14.5)
├── templates/
│   └── index.html               # Single-page UI (HTML + CSS + vanilla JS, ~1100 lines)
├── static/                      # Currently empty — reserved for assets
├── README.md                    # User-facing setup and deployment guide
├── CLAUDE.MD                    # This file — agent guidance
├── AGENTS.md                    # Generic AI-agent contract (mirrors CLAUDE.MD scope)
└── MEMORY.md                    # Long-lived project knowledge / decisions log
```

## Architecture at a Glance

### Backend (`app.py`)

Three routes:

- `GET /` — renders `templates/index.html`.
- `POST /process` — accepts JSON from `file` upload, `paste`, or `api` fetch. Extracts rows, returns JSON with `columns`, `preview` (first 25), `total_rows`, `csv_data` (flattened), `csv_columns`.
- `POST /export-csv` — accepts the previously-returned `csv_data` + `csv_columns`, streams back a `text/csv` attachment named `exported_data.csv`.

Key helpers (all in `app.py`):

- `flatten_for_csv(data, parent_key='', sep='.')` — recursively flattens nested dicts into dot-separated keys; lists are `json.dumps`-stringified.
- `extract_table_data(json_data)` — heuristically finds the tabular payload: top-level list → use directly; dict with an array value → use that array; dict-of-dicts → recurse; otherwise treat the dict as a single row.
- `get_all_columns(data)` — returns the sorted union of keys across all rows.

### Frontend (`templates/index.html`)

Single self-contained file. Three tabs (`file`, `paste`, `api`) drive a hidden `input_method` field. JS handles tab switching, form submission via `fetch('/process')`, table rendering (with nested-object/array inline previews), and CSV download via `fetch('/export-csv')` + Blob.

### Deployment

Render Blueprint (`render.yaml`) on the free tier — no persistent disk, autodeploy on push, served by gunicorn (`gunicorn app:app --bind 0.0.0.0:$PORT`).

## Running Locally

```bash
python -m venv .venv
.venv\Scripts\activate          # PowerShell (Windows)
# source .venv/bin/activate     # bash / zsh
pip install -r requirements.txt
python app.py                   # http://localhost:5000  (debug=True)
```

There is no test suite yet. UI changes must be verified in a browser.

## Conventions & House Rules

- **Privacy is load-bearing.** Do not add database drivers, file-write side effects, request logging that captures payloads, or third-party analytics. If a change would persist user JSON anywhere outside the request lifecycle, surface it explicitly.
- **Keep the single-file frontend.** `templates/index.html` is intentionally one file with inline CSS/JS — easy to deploy, easy to read. Don't introduce a build step, bundler, or framework without discussing first.
- **Pinned deps.** `requirements.txt` is exact-pinned; bump deliberately, not casually.
- **Errors return JSON.** All `/process` and `/export-csv` failure paths return `{"error": "..."}` with a 4xx/5xx status. Match this shape when adding routes.
- **Preview is fixed at 25 rows.** CSV export always covers the full dataset. Don't conflate the two.
- **External API fetch has a 30 s timeout** and uses `response.raise_for_status()`. Preserve both when editing the `api` branch.

## Common Tasks

- **Add a new auth method**: extend the `auth_method` branch in `app.py` (`/process` handler) and add a corresponding `auth-fields-*` block + option in `index.html`.
- **Change preview size**: edit `preview_data = table_data[:25]` in `app.py` and any matching copy in `index.html` and `README.md`.
- **Adjust upload size limit**: `app.config['MAX_CONTENT_LENGTH']` in `app.py`.
- **Add a static asset**: drop it in `static/` and reference via `url_for('static', filename=...)`.

## Caveats to Know

- `csv_export_api_routes.py` is **not** imported — it's a stray documentation fragment. Don't treat it as live code.
- `static/` is currently empty.
- `app.py` runs with `debug=True` when invoked directly (`python app.py`). Production uses gunicorn (no debug).
- The `extract_table_data` heuristic picks the **first** list-of-objects it finds — payloads with multiple candidate arrays may surface the wrong one.
- Bearer tokens, API keys, and basic-auth passwords flow through standard HTML form fields; they live in memory for the duration of one request and are not echoed back to the client.

## Out of Scope (Do Not Add Without Discussion)

- Authentication for the app itself (the README documents an optional Basic Auth pattern, but the codebase ships open).
- Multi-user state, sessions, accounts.
- Any form of caching or persistence between requests.
