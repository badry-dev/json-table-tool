# CLAUDE.md

This file provides guidance for AI assistants working with the JSON Table Converter codebase.

## Project Overview

A lightweight Flask web application that converts JSON data into viewable HTML tables with CSV export. Designed as a stateless, privacy-first internal tool with no data persistence.

**Key features:** file upload (drag-and-drop), paste JSON, fetch from external APIs (with auth support), nested data expansion, CSV export.

## Project Structure

```
json-table-tool/
├── app.py               # Flask backend (all routes and logic)
├── templates/
│   └── index.html       # Single-page frontend (HTML + CSS + JS)
├── requirements.txt     # Python dependencies (Flask, requests, gunicorn)
├── render.yaml          # Render.com deployment blueprint
├── .gitignore
└── README.md
```

This is a deliberately simple, single-file architecture. `app.py` contains all backend logic. `templates/index.html` contains the entire frontend (embedded CSS and vanilla JavaScript).

## Tech Stack

- **Backend:** Python 3.11+, Flask 3.0.0
- **Frontend:** Vanilla HTML/CSS/JavaScript (no frameworks, no build step)
- **HTTP client:** requests 2.31.0
- **Production server:** gunicorn 21.2.0
- **Deployment:** Render.com (free tier, auto-deploy on push)

## Development Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

The dev server runs at `http://localhost:5000` with `debug=True`.

To enable Flask debug mode explicitly:
```bash
export FLASK_DEBUG=1
python app.py
```

## Architecture

### Backend (`app.py`)

Three routes:
- `GET /` — serves the main page
- `POST /process` — accepts JSON from file upload, pasted text, or API fetch; returns columns, preview (first 25 rows), total count, and flattened CSV data
- `POST /export-csv` — accepts processed data, returns a CSV file download

Three helper functions:
- `flatten_for_csv(data)` — recursively flattens nested dicts (dot notation), converts lists to JSON strings
- `extract_table_data(json_data)` — extracts tabular rows from various JSON shapes (array of objects, nested arrays, single objects)
- `get_all_columns(data)` — collects unique column names across all rows

### Frontend (`templates/index.html`)

Single HTML file (~1,115 lines) containing:
- **CSS** (~600 lines): Dark theme, CSS custom properties, responsive design, component styles
- **HTML**: Tab-based input (File/Paste/API), auth options, results table, export button
- **JavaScript** (~300 lines): Tab switching, drag-drop file upload, fetch API communication, dynamic table rendering with nested object/array expansion, CSV export

### Data Flow

1. User provides JSON (file / paste / API URL with optional auth)
2. Server parses JSON, extracts tabular structure
3. Server returns preview (25 rows) + full flattened data for CSV
4. Frontend renders preview table; nested objects show as mini key-value tables
5. On export: full data is POSTed back, server generates CSV for download

## Key Configuration

| Setting | Value | Location |
|---------|-------|----------|
| Max upload size | 10 MB | `app.py` line 17 |
| Preview row limit | 25 rows | `app.py` line 197 |
| API fetch timeout | 30 seconds | `app.py` line 174 |
| Dev server port | 5000 | `app.py` line 258 |

## Code Conventions

- **Python:** Procedural style, PEP 8 formatting, docstrings on all functions, try/except with user-facing error messages returned as JSON
- **JavaScript:** Vanilla JS only, no frameworks or bundlers. Uses `fetch` API, async/await, DOM manipulation via `querySelector`/`getElementById`
- **CSS:** Custom properties for theming (primary color: `#3d5afe`), dark theme throughout, mobile-responsive
- **Security:** HTML escaping on frontend output, file type validation, size limits, no data persistence, no database

## Testing

No automated tests exist yet. If adding tests:
- Use `pytest` for backend tests
- Test files should go in a `tests/` directory
- Run with: `python -m pytest tests/`

## Linting / Formatting

No linting or formatting tools are currently configured. If adding:
- Python: `flake8` or `ruff` for linting, `black` for formatting
- No frontend linting is configured (vanilla JS, no build pipeline)

## Deployment

Deployed to **Render.com** via `render.yaml` blueprint:
- Runtime: Python 3.11
- Build: `pip install -r requirements.txt`
- Start: `gunicorn app:app --bind 0.0.0.0:$PORT`
- Auto-deploy on push, free tier, no persistent storage

## Common Tasks

### Adding a new route
Add the route handler to `app.py`. Follow existing patterns: return `jsonify()` for data, wrap in try/except, return error JSON with appropriate HTTP status codes.

### Modifying the UI
Edit `templates/index.html`. CSS is in `<style>` tags at the top, JavaScript is in `<script>` tags at the bottom. Use existing CSS custom properties for consistency.

### Adding a new auth method for API fetch
1. Add a new option to the `auth_method` select in `index.html`
2. Add corresponding form fields (hidden by default, shown via JS)
3. Handle the new method in the `POST /process` route in `app.py` (see the `auth_method` conditional block starting at line 144)

### Adding a dependency
Add to `requirements.txt` with a pinned version (e.g., `package==1.2.3`).
