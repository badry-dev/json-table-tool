# Code-Health Review — JSON Table Converter

**Date:** 2026-05-02  
**Reviewer:** Automated senior code-health review  
**Repository:** https://github.com/Badry-Kudu/json-table-tool  
**Revision reviewed:** `main` branch (HEAD at time of review)

---

## 1. Initial Score Estimate

| Category | Score | Weight |
|---|---|---|
| Maintainability | 7/10 | 10% |
| Test coverage & quality | 8/10 | 15% |
| Complexity | 7/10 | 10% |
| Duplication | 8/10 | 5% |
| Architecture consistency | 8/10 | 10% |
| Dependency / security risk | 3/10 | 15% |
| Documentation | 7/10 | 10% |
| CI/CD reliability | 0/10 | 15% |
| Input validation & error handling | 9/10 | 10% |
| Usability & developer experience | 7/10 | 10% |

**Overall weighted score: ~68 / 100**

**Target score: 85+ / 100**

---

## 2. Project Overview (Verified)

**Stack:** Python 3.11+, Flask 3.0.0 (app-factory pattern), Flask-WTF (CSRF), Flask-Limiter, gunicorn, requests, openpyxl. Frontend: Vanilla HTML / CSS / JS (no framework, no build step). Tests: pytest.

**Purpose:** Lightweight stateless web tool that converts JSON and JSONL data into viewable HTML tables, with CSV, TSV, and Excel export. Supports file upload, paste, and external API fetch with auth.

**Directory layout:**
```
app.py          Flask app factory
config.py       All settings via env vars
extensions.py   Shared CSRF + limiter instances
security.py     SSRF validation + security headers
helpers.py      Data parsing, flattening, path selection
routes.py       Blueprint with /, /health, /process, /export-csv, /export-xlsx
static/         css/style.css  js/app.js
templates/      index.html (structure only, no inline scripts/styles)
tests/          conftest.py, test_helpers.py, test_routes.py, test_security.py
render.yaml     Render.com deployment blueprint
requirements.txt
```

---

## 3. Commands Run & Results

### Install
```bash
pip install -r requirements.txt
# → Success. All 7 direct dependencies installed.
```

### Tests
```bash
python -m pytest tests/ -v
# → 82 passed, 2 warnings (openpyxl DeprecationWarning from library internals), 0 failures
```

### Coverage
```bash
coverage run -m pytest tests/ && coverage report -m
```

| File | Stmts | Miss | Cover |
|---|---|---|---|
| app.py | 16 | 1 | 94% |
| config.py | 14 | 0 | 100% |
| extensions.py | 5 | 0 | 100% |
| helpers.py | 78 | 1 | 99% |
| routes.py | 181 | 33 | 82% |
| security.py | 33 | 3 | 91% |
| tests/ | 446 | 0 | 100% |
| **TOTAL** | **773** | **38** | **95%** |

### Dependency Audit
```bash
pip-audit -r requirements.txt
```
**Found 7 known vulnerabilities in 4 packages:**

| Package | Current | CVE | Fix Version | Severity |
|---|---|---|---|---|
| Flask | 3.0.0 | CVE-2026-27205 | 3.1.3 | — |
| requests | 2.31.0 | CVE-2024-35195 | 2.32.0 | Medium |
| requests | 2.31.0 | CVE-2024-47081 | 2.32.4 | Medium |
| requests | 2.31.0 | CVE-2026-25645 | 2.33.0 | — |
| gunicorn | 21.2.0 | CVE-2024-1135 | 22.0.0 | High |
| gunicorn | 21.2.0 | CVE-2024-6827 | 22.0.0 | — |
| pytest | 7.4.4 | CVE-2025-71176 | 9.0.3 | — |

### Linting / Formatting
```
No linting or formatting tools are configured for this project.
```
Run (locally or in CI):
```bash
pip install ruff
ruff check .
ruff format --check .
```

### Type checking
```
No type annotations present. No mypy or pyright configured.
```

### CI/CD Workflows
```
No .github/workflows/ directory found. Zero CI/CD configuration.
```

---

## 4. Category-by-Category Findings

### 4.1 Maintainability — 7/10

**Strengths:**
- Clean app-factory pattern (`create_app()`) with proper extension initialization.
- Well-separated modules: `config.py`, `extensions.py`, `security.py`, `helpers.py`, `routes.py`.
- Consistent docstrings on all public functions.
- Naming conventions are clear and consistent throughout.

**Issues:**
- `process_json()` in `routes.py` is ~150 lines with three nested branches (file/paste/api), five auth sub-branches, and a post-parse block — cyclomatic complexity ≈ 15+.
- No type annotations anywhere. With Flask's dynamic nature, type hints would catch many errors at development time.
- No linter or formatter configured; code style is consistent now but will drift as contributors add code.
- `openpyxl` is imported lazily inside `export_xlsx()` — inconsistent with all other imports at module top, and hides ImportError until runtime.

### 4.2 Test Coverage & Quality — 8/10

**Strengths:**
- **95% overall coverage** — exceptional for a Flask project.
- 82 tests across three well-organized files (`test_helpers`, `test_routes`, `test_security`).
- All auth paths tested via mock. SSRF blocking well-covered (16 URL validation tests).
- Edge cases covered: UTF-8 decoding failure, max-size exceeded, JSONL invalid line, path selection modal flow.

**Issues:**
- `routes.py` is 82% covered; uncovered lines include auth header/key/bearer/query-param branches (lines 92–109) and the `ValueError` path in `parse_jsonl` when called from API fetch.
- No edge-case input tests for helpers: `null` values in JSON objects, Unicode / emoji column names, boolean-only arrays, numbers as top-level JSON, empty-object arrays `[{}, {}]`, extremely large number of columns.
- No test confirming the `PREVIEW_ROW_LIMIT` server config is reflected in the JS badge (hardcoded "25" in `app.js` line 219 and 220 is inconsistent with server config).
- No test for file upload with no `json_file` field (line 50 branch is untested).

### 4.3 Complexity — 7/10

**Strengths:**
- `helpers.py` functions are small, single-purpose, and easy to reason about.
- `security.py` is clear and minimal.

**Issues:**
- `process_json()` has high cyclomatic complexity and should be refactored: extract `_parse_input(request, data_format)` → returns `(json_data, error_response)` and `_apply_path_selection(json_data, json_path)` → returns `(table_data, error_response)`.
- `extract_table_data()` falls through multiple isinstance checks with no early return at each branch; a match/case or helper would improve clarity (Python 3.10+).
- `renderTable` / `renderTableDOM` split in `app.js` is unnecessary — `renderTable` just stores refs then calls `renderTableDOM`, creating indirection without benefit.

### 4.4 Duplication — 8/10

**Strengths:**
- `escapeHtml()` is defined once and reused across all JS rendering functions — no XSS risk from duplication.
- `get_all_columns()` is reused for both preview and CSV columns.

**Issues:**
- `export_csv` and `export_xlsx` both implement identical `dict/list → JSON string` serialization for cell values:
  ```python
  if isinstance(v, (dict, list)):
      clean_row[k] = json.dumps(v)
  ```
  This logic should live in a shared helper (e.g., `serialize_cell_value(v)`).
- `downloadDelimited` in `app.js` and `export_csv` route in `routes.py` both implement CSV serialization independently. This is intentional (client-side fallback + server fallback) but should be documented as such.

### 4.5 Architecture Consistency — 8/10

**Strengths:**
- Blueprint pattern used correctly. Extensions initialized with `init_app()` pattern.
- Security headers applied globally via `after_request`. No inline styles/scripts (CSP-safe).
- Config exclusively from environment variables with documented defaults.

**Issues:**
- `app = create_app()` at module level in `app.py` (line 28) is fine for `python app.py` dev use, but means importing `app` in tests or tools always creates an app instance with production config. Tests avoid this by calling `create_app()` directly, but it's a subtle trap.
- `RATE_LIMIT_PROCESS` / `RATE_LIMIT_EXPORT` are stored as custom config keys rather than using Flask-Limiter's standard `RATELIMIT_*` namespace, requiring the lambda wrapper on every route decorator.
- No `pyproject.toml` or `setup.cfg` — project metadata (name, version, Python constraint) exists only in `config.py` and `render.yaml`, not in a standard packaging file.

### 4.6 Dependency / Security Risk — 3/10

**Strengths:**
- All direct dependencies are pinned to exact versions — no floating ranges.
- Minimal dependency footprint: 7 direct deps for a full web app is lean.
- No unused dependencies found.

**Issues:**
- **7 CVEs across 4 packages** — all have published fixes:
  - `gunicorn 21.2.0` → CVE-2024-1135 (HTTP Request Smuggling, **High**) + CVE-2024-6827. Fix: `gunicorn==22.0.0`.
  - `requests 2.31.0` → 3 CVEs. Fix: `requests==2.33.0` (supersedes all three).
  - `Flask 3.0.0` → CVE-2026-27205. Fix: `Flask==3.1.3`.
  - `pytest 7.4.4` → CVE-2025-71176 (test-only, lower risk). Fix: `pytest==9.0.3`.
- No `requirements-dev.txt` / `requirements-test.txt` separation — `pytest` (test-only) is mixed with production dependencies, meaning it gets installed in production.
- No transitive dependency pinning (`pip-compile` or lock file). Transitive deps are resolved fresh on every `pip install`, so builds are not fully reproducible.
- `openpyxl==3.1.2` triggers `DeprecationWarning: datetime.datetime.utcnow()` (library-internal issue, tracked upstream). Fix: upgrade to `openpyxl==3.1.5`.

### 4.7 Documentation — 7/10

**Strengths:**
- `README.md` is thorough: quick start, full deployment section (Render, gunicorn+systemd+nginx, Docker, Railway, Fly.io), usage guide, security notes, troubleshooting, environment variable table.
- `CLAUDE.md` provides excellent internal contributor guidance.
- All Python functions have docstrings.

**Issues:**
- No `CONTRIBUTING.md` or `DEVELOPMENT.md` — new contributors must infer linting/testing conventions from `CLAUDE.md`.
- No `CHANGELOG.md` — no history of changes or versioning rationale.
- No `docs/` directory or architecture decision records.
- README does not mention linting, type checking, or coverage — the "Development" section only shows `python app.py` and `pytest`.
- README badge for "License" points to no `LICENSE` file (the file doesn't exist in the repo).
- Missing: JSON format edge-case examples (null values, booleans, Unicode, deeply nested, large files).
- `APP_VERSION = '1.1.0'` in `config.py` is not linked to any tag or release — version can drift silently.

### 4.8 CI/CD Reliability — 0/10

**Critical gap.** There is no `.github/workflows/` directory. No CI pipeline exists.

This means:
- No automated test runs on pull requests or pushes to `main`.
- Dependency vulnerabilities are never automatically flagged.
- Linting and formatting checks never run automatically.
- Regressions can be merged without detection.
- The `render.yaml` auto-deploys on every push — with no CI gate, broken code deploys directly to production.

**Required:** A GitHub Actions workflow running on `push` and `pull_request` to `main` that:
1. Installs dependencies
2. Runs `pytest` with coverage
3. Runs `ruff check` and `ruff format --check`
4. Runs `pip-audit`

### 4.9 Input Validation & Error Handling — 9/10

**Strengths:**
- CSRF protection on all POST routes via Flask-WTF.
- SSRF protection with DNS validation blocking private/loopback/link-local/multicast IPs.
- Rate limiting on all routes (configurable).
- `MAX_CONTENT_LENGTH` enforced (10MB default).
- API response size capped + streamed (no full-load-then-check).
- `allow_redirects=False` on API fetch.
- UTF-8 decoding error caught and returns 400.
- `UnicodeDecodeError`, `JSONDecodeError`, `ValueError`, `Timeout`, `RequestException` all handled with appropriate HTTP status codes.
- All `RequestException` detail is swallowed and a generic message returned (no internal host leakage).
- `escapeHtml()` used consistently in all JS rendering paths (no XSS risk from JSON data).

**Issues:**
- No JSON parsing depth limit — a specially crafted JSON with 10,000 levels of nesting could exhaust the Python call stack before `flatten_for_csv`'s `max_depth` guard is reached (Python's default recursion limit is ~1000; `json.loads` itself is C-level and handles it, but `extract_table_data` is recursive Python with no depth guard).
- No file extension validation on upload (any file extension accepted; only content parsing catches non-JSON).
- No explicit `Content-Type` validation on file upload (`accept=".json,.jsonl"` is client-side only).
- The JS `formatValue()` function does not guard against extremely large arrays/objects in a cell — rendering a cell with 50,000-item nested array would freeze the browser tab.

### 4.10 Usability & Developer Experience — 7/10

**Strengths:**
- Drag-and-drop file upload, dark/light theme with `localStorage` persistence, format toggle (JSON/JSONL), multi-format export dropdown.
- Keyboard-accessible tabs (they are `<button>` elements, not `<div>`, so naturally keyboard-reachable via Tab + Enter).
- Clear loading/error state management.
- Path-selector modal for multi-array JSON.

**Issues:**
- `previewBadge` text "Showing first 25" is hardcoded in `app.js` (lines 219–225) — does not reflect the server-side `PREVIEW_ROW_LIMIT` config. If an operator changes the config to 50, the badge will still say "25".
- No `.env.example` file — operators must read `README.md` or `config.py` to learn required env vars.
- No `Makefile` or `justfile` for standard dev commands. `make test`, `make lint`, `make coverage` would lower the contribution friction.
- `alert()` used for the About dialog (line 477 in `app.js`) — blocks the main thread and is not keyboard dismissible on all browsers in the same way.
- The export dropdown has no keyboard trigger — `exportBtn` opens/closes the dropdown but the dropdown items are not in the natural Tab focus flow when it is closed.
- No visual indication when a sort is active after re-submission (sort state is preserved in `sortColumn`/`sortDirection` but the table re-renders without a visual indicator until columns are redrawn).
- No `LICENSE` file exists despite the README saying MIT.

---

## 5. Top 10 Issues Affecting the Score

| # | Issue | Category | Impact | Effort |
|---|---|---|---|---|
| 1 | **No CI/CD pipeline** — zero automated checks on PRs or pushes | CI/CD | Critical | Low |
| 2 | **7 CVEs with published fixes** — gunicorn (HTTP Request Smuggling), requests (3 CVEs), Flask, pytest | Deps/Security | Critical | Low |
| 3 | **Dev dependencies mixed with production** — `pytest` installed in production | Deps/Security | High | Low |
| 4 | **No linter or formatter configured** — style drift is inevitable | Maintainability | High | Low |
| 5 | **`process_json()` is ~150 lines with cyclomatic complexity ≈ 15** | Complexity | Medium | Medium |
| 6 | **No type annotations** — no static analysis safety net | Maintainability | Medium | Medium |
| 7 | **Hardcoded "25" in JS badge** inconsistent with server config | Usability/DX | Medium | Low |
| 8 | **No `LICENSE` file** despite README declaring MIT | Documentation | Medium | Low |
| 9 | **No `.env.example`** for operator onboarding | DX | Low | Low |
| 10 | **No JSON depth guard in `extract_table_data()`** — recursive Python with no depth cap | Input Validation | Low | Low |

---

## 6. Quick Wins (1–2 hours each)

1. **Bump all vulnerable deps** — update `requirements.txt` to `Flask==3.1.3`, `requests==2.33.0`, `gunicorn==22.0.0`, `openpyxl==3.1.5`, `pytest==9.0.3`.
2. **Split `requirements.txt`** — create `requirements-dev.txt` for `pytest` (and future `ruff`, `coverage`), keep `requirements.txt` production-only.
3. **Add GitHub Actions workflow** — basic `ci.yml` that installs, lints, tests, and audits on push/PR to `main`.
4. **Add `ruff` to dev deps and configure** — add `pyproject.toml` with `[tool.ruff]` section; run `ruff check .` and fix any issues.
5. **Add `LICENSE` file** — MIT, matching README statement.
6. **Add `.env.example`** — document all env vars with safe placeholder values.
7. **Fix hardcoded "25" in `app.js`** — have the server return `preview_limit` in the `/process` response, use it in the badge.
8. **Extract `serialize_cell_value()` helper** in `routes.py` to remove the duplicated `dict/list → json.dumps` logic.

---

## 7. Larger Refactoring Recommendations

### 7.1 Refactor `process_json()` into sub-functions
Extract three helpers:
- `_load_from_file(request, data_format) -> tuple[Any, Response | None]`
- `_load_from_paste(request, data_format) -> tuple[Any, Response | None]`  
- `_load_from_api(request, data_format, config) -> tuple[Any, Response | None]`
- `_select_table_data(json_data, json_path) -> tuple[list, Response | None]`

This reduces `process_json` to ~30 lines of orchestration and makes each path independently testable.

### 7.2 Add type annotations
Add type hints to all function signatures in `helpers.py`, `security.py`, `routes.py`, and `config.py`. Add `mypy` to dev deps and configure it in `pyproject.toml`. Type hints will catch subtle bugs (e.g., `extract_table_data` returning `[]` vs `None`) without changing behavior.

### 7.3 Separate dev and production dependency files
```
requirements.txt          # Flask, requests, gunicorn, Flask-WTF, Flask-Limiter, openpyxl
requirements-dev.txt      # -r requirements.txt + pytest, coverage, ruff, mypy, pip-audit
```
This prevents test tooling from being deployed to production.

### 7.4 Add `pyproject.toml`
Centralizes project metadata, Python version constraint, ruff config, mypy config, and pytest config — replacing scattered `setup.cfg`, `pytest.ini`, or bare `pyproject.toml` fragments.

### 7.5 Add recursion depth guard to `extract_table_data()`
Add a `_depth=0, max_depth=20` parameter pair matching `flatten_for_csv`'s pattern — prevents Python stack overflow on pathological inputs before they even reach flattening.

---

## 8. Security Findings

| Finding | Severity | Status |
|---|---|---|
| gunicorn CVE-2024-1135 (HTTP Request Smuggling) | High | Fix available: 22.0.0 |
| gunicorn CVE-2024-6827 | Medium | Fix available: 22.0.0 |
| requests CVE-2024-35195 | Medium | Fix available: 2.33.0 |
| requests CVE-2024-47081 | Medium | Fix available: 2.33.0 |
| requests CVE-2026-25645 | Medium | Fix available: 2.33.0 |
| Flask CVE-2026-27205 | Medium | Fix available: 3.1.3 |
| pytest CVE-2025-71176 | Low (test-only) | Fix available: 9.0.3 |
| SSRF via API fetch | Mitigated | DNS validation + `allow_redirects=False` in place |
| XSS in table rendering | Mitigated | `escapeHtml()` used on all dynamic content |
| CSRF | Mitigated | Flask-WTF CSRFProtect on all POST routes |
| Information leakage in API errors | Mitigated | Generic messages returned; details logged server-side |
| `SECRET_KEY` default | Risk | Dev default documented; `generateValue: true` in render.yaml |

---

## 9. Prioritized Execution Plan

### Phase 1 — Security & CI Foundations (Day 1, ~3 hours, zero behavior change)

**Goal:** Eliminate all CVEs, add CI gate before production deploys.

| Step | File(s) | Command |
|---|---|---|
| 1a. Bump vulnerable deps | `requirements.txt` | Edit versions |
| 1b. Split dev deps | `requirements-dev.txt` (new) | `pip install -r requirements-dev.txt` |
| 1c. Add `LICENSE` | `LICENSE` (new) | Copy MIT template |
| 1d. Add GitHub Actions CI | `.github/workflows/ci.yml` (new) | — |
| 1e. Verify tests still pass | — | `python -m pytest tests/ -v` |
| 1f. Run `pip-audit` clean | — | `pip-audit -r requirements.txt` |

**`requirements.txt` after Phase 1:**
```
Flask==3.1.3
requests==2.33.0
gunicorn==22.0.0
Flask-WTF==1.2.1
Flask-Limiter==3.5.0
openpyxl==3.1.5
```

**`requirements-dev.txt` after Phase 1:**
```
-r requirements.txt
pytest==9.0.3
coverage==7.6.1
ruff==0.4.4
pip-audit==2.7.3
```

**`.github/workflows/ci.yml`:**
```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements-dev.txt
      - run: ruff check .
      - run: ruff format --check .
      - run: python -m pytest tests/ -v --tb=short
      - run: pip-audit -r requirements.txt
```

**Acceptance criteria:**
- `pip-audit -r requirements.txt` reports zero vulnerabilities.
- All 82 tests pass.
- CI workflow runs on every push/PR and goes green.

---

### Phase 2 — Linting, Formatting & Quick Fixes (Day 1–2, ~2 hours)

**Goal:** Enforce consistent code style; fix small DX/correctness issues.

| Step | File(s) | Notes |
|---|---|---|
| 2a. Add `pyproject.toml` | `pyproject.toml` (new) | ruff + pytest config |
| 2b. Run `ruff check . --fix` | All `.py` files | Auto-fix lint issues |
| 2c. Fix hardcoded "25" in badge | `routes.py`, `static/js/app.js` | Return `preview_limit` in `/process` response |
| 2d. Add `.env.example` | `.env.example` (new) | Safe placeholder values |
| 2e. Add `Makefile` | `Makefile` (new) | `make test`, `make lint`, `make coverage` |
| 2f. Update README dev section | `README.md` | Add lint + coverage commands |

**`pyproject.toml`:**
```toml
[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP"]
ignore = ["E501"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

**Acceptance criteria:**
- `ruff check .` exits 0.
- `ruff format --check .` exits 0.
- Preview badge correctly reflects server-side `PREVIEW_ROW_LIMIT`.
- All 82 tests still pass.

---

### Phase 3 — Test Coverage Improvements (Day 2–3, ~3 hours)

**Goal:** Cover the remaining 18 uncovered lines; add edge-case inputs.

| Step | File(s) | New tests |
|---|---|---|
| 3a. Auth method coverage | `tests/test_routes.py` | API key, basic auth, bearer token, query param |
| 3b. No-file upload branch | `tests/test_routes.py` | POST file with no `json_file` field |
| 3c. JSONL ValueError in API fetch | `tests/test_routes.py` | Mock API returning malformed JSONL |
| 3d. Null/boolean/Unicode inputs | `tests/test_helpers.py` | `null`, `true`, `false`, `\u0000`, emoji column names |
| 3e. Empty-object rows | `tests/test_helpers.py` | `[{}, {}]` input |
| 3f. Large column count | `tests/test_helpers.py` | Object with 500 keys |
| 3g. Security: invalid IPv6 formats | `tests/test_security.py` | IPv4-mapped IPv6 addresses |

**Target coverage after Phase 3:** ≥97% overall, ≥90% routes.py.

**Acceptance criteria:**
- All new and existing tests pass.
- `coverage report` shows ≥90% for `routes.py`.
- `coverage report` shows ≥97% overall.

---

### Phase 4 — Complexity & Refactoring (Day 3–4, ~4 hours)

**Goal:** Reduce `process_json` complexity; extract shared serialization helper.

| Step | File(s) | Notes |
|---|---|---|
| 4a. Extract `serialize_cell_value()` | `routes.py` | Used by both `export_csv` and `export_xlsx` |
| 4b. Extract `_load_input()` helper | `routes.py` | Returns `(json_data, error_response_or_None)` |
| 4c. Extract `_apply_path()` helper | `routes.py` | Path selection logic extracted |
| 4d. Add depth guard to `extract_table_data()` | `helpers.py` | Mirror `flatten_for_csv` pattern |
| 4e. Move `openpyxl` import to module top | `routes.py` | Consistency; fails fast on missing dep |
| 4f. Update tests for refactored functions | `tests/test_routes.py` | No behavior change, same assertions |

**Acceptance criteria:**
- All existing tests pass unchanged.
- `process_json` function body ≤ 50 lines.
- No behavior change visible to API consumers.

---

### Phase 5 — Type Annotations & Static Analysis (Day 4–5, ~3 hours)

**Goal:** Add type hints to all Python modules; run mypy clean.

| Step | File(s) | Notes |
|---|---|---|
| 5a. Add `mypy` to dev deps | `requirements-dev.txt` | `mypy==1.10.0` |
| 5b. Add mypy config | `pyproject.toml` | `[tool.mypy]` section |
| 5c. Annotate `helpers.py` | `helpers.py` | All function signatures |
| 5d. Annotate `security.py` | `security.py` | Return `tuple[bool, str | None]` |
| 5e. Annotate `config.py` | `config.py` | Class attribute types |
| 5f. Annotate `routes.py` | `routes.py` | After refactor in Phase 4 |
| 5g. Add mypy to CI | `.github/workflows/ci.yml` | `- run: mypy .` |

**Acceptance criteria:**
- `mypy . --ignore-missing-imports` exits 0.
- No runtime behavior change.

---

### Phase 6 — Documentation & DX Polish (Day 5, ~2 hours)

**Goal:** Close remaining documentation gaps; improve contributor experience.

| Step | File(s) | Notes |
|---|---|---|
| 6a. Add `CONTRIBUTING.md` | `CONTRIBUTING.md` (new) | Setup, lint, test, PR checklist |
| 6b. Add `CHANGELOG.md` | `CHANGELOG.md` (new) | Starting from v1.1.0 |
| 6c. Update README | `README.md` | Add lint, type-check, coverage commands; fix missing LICENSE note; link CONTRIBUTING |
| 6d. Add JSON edge-case examples | `README.md` | Null, boolean, Unicode, mixed-type arrays |
| 6e. Fix `alert()` in About | `static/js/app.js` | Replace with accessible modal or `<dialog>` |
| 6f. Keyboard-accessible export dropdown | `static/js/app.js`, `templates/index.html` | Add `aria-expanded`, focus trap, Escape key close |

**Acceptance criteria:**
- A new contributor can set up the project, run lint, run tests, and view coverage using only `README.md` + `CONTRIBUTING.md`.
- `CHANGELOG.md` exists.
- Export dropdown is reachable by keyboard.
- No `alert()` calls in production code.

---

## 10. Implementation Checklist

### Phase 1 — Security & CI
- [ ] Upgrade `Flask` to `3.1.3` in `requirements.txt`
- [ ] Upgrade `requests` to `2.33.0` in `requirements.txt`
- [ ] Upgrade `gunicorn` to `22.0.0` in `requirements.txt`
- [ ] Upgrade `openpyxl` to `3.1.5` in `requirements.txt`
- [ ] Move `pytest` out of `requirements.txt`, create `requirements-dev.txt`
- [ ] Add `ruff`, `coverage`, `pip-audit` to `requirements-dev.txt`
- [ ] Add `pytest==9.0.3` to `requirements-dev.txt`
- [ ] Create `LICENSE` file (MIT)
- [ ] Create `.github/workflows/ci.yml`
- [ ] Verify `pip-audit -r requirements.txt` → 0 vulnerabilities
- [ ] Verify all 82 tests pass with new dependency versions

### Phase 2 — Linting & Quick Fixes
- [ ] Create `pyproject.toml` with ruff + pytest config
- [ ] Run `ruff check . --fix` and commit
- [ ] Add `preview_limit` field to `/process` JSON response
- [ ] Update `app.js` to use `data.preview_limit` for badge text
- [ ] Create `.env.example`
- [ ] Create `Makefile`
- [ ] Update README development section
- [ ] `ruff check .` exits 0
- [ ] `ruff format --check .` exits 0

### Phase 3 — Test Coverage
- [ ] Test all four auth methods (api_key, basic, bearer, query_param)
- [ ] Test missing `json_file` field in file upload
- [ ] Test JSONL parse error from API fetch
- [ ] Test null/boolean/Unicode column names in helpers
- [ ] Test empty-object rows `[{}, {}]`
- [ ] Coverage report shows ≥90% routes.py
- [ ] Coverage report shows ≥97% overall

### Phase 4 — Complexity Reduction
- [ ] Extract `serialize_cell_value(v)` helper in `routes.py`
- [ ] Extract `_load_input(request, data_format)` from `process_json`
- [ ] Extract `_apply_path(json_data, json_path)` from `process_json`
- [ ] Add `_depth` guard to `extract_table_data()`
- [ ] Move `openpyxl` import to module top in `routes.py`
- [ ] `process_json` body ≤ 50 lines
- [ ] All existing tests pass

### Phase 5 — Type Annotations
- [ ] Annotate all functions in `helpers.py`
- [ ] Annotate all functions in `security.py`
- [ ] Annotate `Config` class in `config.py`
- [ ] Annotate route functions in `routes.py`
- [ ] `mypy . --ignore-missing-imports` exits 0
- [ ] Add mypy step to CI workflow

### Phase 6 — Documentation & DX
- [ ] Create `CONTRIBUTING.md`
- [ ] Create `CHANGELOG.md`
- [ ] Update README: lint/type-check/coverage commands, remove "Feature Requests" references to missing issue tracker
- [ ] Add JSON edge-case examples to README
- [ ] Replace `alert()` with accessible modal in `app.js`
- [ ] Make export dropdown keyboard-accessible
- [ ] A first-time contributor can complete setup in < 5 minutes using only docs

---

## 11. Final Verification Checklist

Run all of these after completing all phases:

```bash
# 1. Install production deps and audit
pip install -r requirements.txt
pip-audit -r requirements.txt
# Expected: 0 vulnerabilities

# 2. Install dev deps
pip install -r requirements-dev.txt

# 3. Lint
ruff check .
# Expected: 0 issues

# 4. Format check
ruff format --check .
# Expected: no reformatting needed

# 5. Type check
mypy . --ignore-missing-imports
# Expected: 0 errors

# 6. Run full test suite
python -m pytest tests/ -v
# Expected: all tests pass, 0 failures, 0 errors

# 7. Coverage
coverage run -m pytest tests/ && coverage report -m
# Expected: ≥97% overall, ≥90% routes.py

# 8. CI workflow validation (local with act, or inspect YAML)
# All steps in .github/workflows/ci.yml pass

# 9. Dev server smoke test
FLASK_DEBUG=1 python app.py
# Expected: starts on port 5000, /health returns {"status":"ok","version":"1.1.0"}
# curl http://localhost:5000/health

# 10. Export smoke test
# POST /process with sample JSON → preview renders
# Export CSV, TSV, Excel → files download correctly

# 11. SSRF smoke test
# POST /process with api_url=http://169.254.169.254/ → 400, "private"

# 12. CSRF smoke test
# POST /process without csrf_token → 400 (CSRF protection active outside test mode)

# 13. Security headers check
# curl -I http://localhost:5000/ | grep -E "(CSP|X-Frame|X-Content|Referrer)"
```

---

## 12. Remaining Risks & Tradeoffs

| Risk | Likelihood | Mitigation |
|---|---|---|
| DNS rebinding (SSRF residual) | Low | Documented in `routes.py` comment; mitigated by `allow_redirects=False` |
| Memory exhaustion on deeply nested JSON (recursive `extract_table_data`) | Low | Fix in Phase 4; `max_depth` guard already on `flatten_for_csv` |
| `SECRET_KEY` misconfiguration in production | Medium | `render.yaml` uses `generateValue: true`; README warns; add startup assertion |
| Browser tab freeze on large nested cell values | Low | Phase 6: cap nested table rendering at N cells |
| openpyxl `DeprecationWarning` (internal) | Info | Will resolve with openpyxl upstream; pin to 3.1.5+ |
| Transitive dep version drift | Medium | Add `pip-compile` / lock file in post-85 iteration |

---

## 13. Projected Score After All Phases

| Category | Current | Projected |
|---|---|---|
| Maintainability | 7/10 | 9/10 |
| Test coverage & quality | 8/10 | 9/10 |
| Complexity | 7/10 | 9/10 |
| Duplication | 8/10 | 9/10 |
| Architecture consistency | 8/10 | 9/10 |
| Dependency / security risk | 3/10 | 9/10 |
| Documentation | 7/10 | 9/10 |
| CI/CD reliability | 0/10 | 9/10 |
| Input validation & error handling | 9/10 | 10/10 |
| Usability & developer experience | 7/10 | 9/10 |
| **Overall weighted** | **~68/100** | **~91/100** |

The two categories with the largest score gain are **CI/CD** (0→9) and **Dependency/Security** (3→9), which together account for +30% of the overall score improvement. Both are achievable in Phase 1 with low effort and zero behavior change.

---

*Report generated: 2026-05-02. Review the [implementation checklist](#10-implementation-checklist) to track progress.*
