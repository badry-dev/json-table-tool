# AGENTS.md

Contract for AI coding agents (Claude Code, Cursor, GitHub Copilot Workspace, Aider, Codex, etc.) working in this repository. This file mirrors and complements `CLAUDE.MD` — read both before making changes.

## TL;DR for Agents

- This is a **single-purpose Flask utility**: JSON → table → CSV. Keep it small.
- **No persistence, ever.** No DB, no disk writes, no payload logging.
- **One Python file** (`app.py`), **one HTML file** (`templates/index.html`). Resist splitting them without a reason.
- **No build step.** Vanilla JS, inline CSS. Don't introduce npm, Vite, React, Tailwind, etc.
- **No tests yet.** UI-affecting changes must be browser-verified; logic changes should add a quick smoke check or be explained.

## Project Snapshot

| Item              | Value                                                |
|-------------------|------------------------------------------------------|
| Language          | Python 3.11+ (Render targets 3.14.5)                 |
| Framework         | Flask 3.0.0                                          |
| HTTP client       | `requests` 2.31.0                                    |
| WSGI server       | gunicorn 21.2.0                                      |
| Frontend          | HTML + inline CSS + vanilla JS (no framework)        |
| Deployment        | Render (free tier) via `render.yaml`                 |
| Entry point       | `app.py` (`flask` dev) / `gunicorn app:app` (prod)   |
| Default port      | 5000 (dev) / `$PORT` (prod)                          |

## Setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
python app.py   # serves http://localhost:5000
```

## Code Map

- **`app.py`** — the entire backend.
  - `flatten_for_csv` (lines ~20-38): recursive dict-flatten; lists → JSON strings.
  - `extract_table_data` (lines ~41-76): finds the rows inside arbitrary JSON.
  - `get_all_columns` (lines ~79-85): sorted union of keys.
  - `/` (line ~88): renders the UI.
  - `/process` (lines ~94-213): the workhorse — handles `file` / `paste` / `api` input methods.
  - `/export-csv` (lines ~216-254): streams a CSV download.
- **`templates/index.html`** — the entire frontend.
  - `:root` CSS variables drive the dark theme.
  - Tab buttons (`.method-tab[data-method=…]`) toggle visible input blocks and the hidden `input_method` field.
  - `auth_method` `<select>` toggles `auth-fields-*` blocks for the `api` tab.
  - JS handlers: `form.submit` → `/process`; `exportBtn.click` → `/export-csv`.
- **`render.yaml`** — Render Blueprint; do not add `disk:` or stateful services.
- **`csv_export_api_routes.py`** — **STRAY DOC FRAGMENT, NOT WIRED IN.** Either ignore it, delete it, or convert it to a proper docs file — but don't `import` it.

## Conventions

### Do

- Return JSON `{"error": "..."}` with a 4xx/5xx status for all backend failure paths.
- Keep the 25-row preview / full-data CSV split intact.
- Preserve the 30-second timeout and `raise_for_status()` on outbound API fetches.
- Pin new dependencies in `requirements.txt` with exact versions.
- Use Python standard-library tools (`json`, `csv`, `io`) where possible; this project intentionally avoids heavy data libs (pandas, polars).
- Render Windows-aware paths; this is a Windows developer machine. Use raw strings or forward slashes in test snippets.

### Don't

- Don't add a database, ORM, file-based cache, or any persistence layer.
- Don't log request bodies, headers, or auth credentials.
- Don't introduce a frontend build step or framework.
- Don't split `app.py` into a package layout for the sake of "cleanliness" — it's intentionally flat.
- Don't bypass `MAX_CONTENT_LENGTH` (10 MB). Raise it explicitly if needed and document the reason.
- Don't echo secrets (bearer tokens, passwords) back in the response.

## Verification Checklist (before reporting a task done)

- [ ] `python app.py` starts without traceback.
- [ ] `GET /` returns 200 and the page renders in a browser.
- [ ] All three input methods (file / paste / API) still produce a table.
- [ ] CSV export downloads a file with the full row count, not just 25.
- [ ] Bad input (malformed JSON, missing file, unreachable URL) returns a JSON error, not a stack trace.
- [ ] No new dependency was added without a pinned version and a one-line justification.
- [ ] No new file writes, DB calls, or logging of payloads were introduced.

## When in Doubt

1. Re-read `CLAUDE.MD` and this file.
2. Skim `MEMORY.md` for prior decisions on the area you're touching.
3. If the task implies persistence, telemetry, auth, or a frontend framework: **stop and ask the user first** — those are deliberate "no"s, not oversights.

## Tooling Notes for Specific Agents

- **Claude Code**: prefer `Edit` over `Write` for `app.py` and `index.html`; both are read-then-edit targets. Use `Grep` instead of shell `grep`. Bash is available — PowerShell is the default shell on this machine.
- **Cursor / Aider / Copilot Workspace**: respect the single-file conventions above; auto-suggested refactors that split the app into packages are out of scope unless the user explicitly asks.
- **Any agent**: if you generate code that the user did not request (helper modules, utility files, type stubs), delete it before finishing the task.
