# MEMORY.md

A living log of **non-obvious** decisions, constraints, gotchas, and context that any contributor (human or AI) should know before changing this codebase. This is **not** a changelog — see `git log` for that. This file captures the *why* behind choices that aren't visible in the code itself.

## How to Use This File

- **Read it** before starting any non-trivial change, especially in areas tagged below.
- **Append to it** when you make or learn something that future-you (or another agent) would otherwise have to rediscover.
- **Prune it** when an entry becomes stale or wrong — outdated memory is worse than no memory.

### Entry Format

Each entry should be self-contained and answer three questions:

```
### YYYY-MM-DD — Short title  (area: backend | frontend | security | deploy | testing | ux)

**What:** the decision, constraint, or surprise.
**Why:** the reason — past incident, requirement, tradeoff, stakeholder ask.
**How to apply:** what a future contributor should *do* with this knowledge.
**Owner / source:** name, ticket, or commit (optional).
```

Keep entries short — if it grows past ~10 lines, it probably belongs in `README.md` or `CLAUDE.md` as documentation.

---

## Active Memory

### 2026-05-12 — In-memory-only is a hard requirement  (area: security)

**What:** The app must never persist user-submitted JSON to disk, database, or any external system. The only writes are stdout logs (and those deliberately omit payloads).
**Why:** Designed as an internal tool for handling potentially sensitive payloads (API responses, exports). The Render free tier deliberately has no persistent disk to enforce this physically.
**How to apply:** Reject any change that adds a DB driver, file write of payload bytes, third-party analytics, or request-body logging. Log **fixed strings**: `logger.warning('API request failed')` is fine; interpolating the payload, the URL, or the exception is not — `requests`' exception text embeds the full URL, which can carry a token (see the 2026-08-21 log-hygiene entry).

### 2026-05-12 — Gunicorn must call the factory, not a module-level `app`  (area: deploy)

**What:** Production start command is `gunicorn "app:create_app()" --bind 0.0.0.0:$PORT`, **not** `gunicorn app:app`.
**Why:** `app.py` does export a module-level `app = create_app()` for tooling that expects it (REPL inspection, test client), but the factory form is the supported deployment path — extensions, config loading, and middleware all run inside `create_app()`. Bypassing it via `app:app` works today but can mask config-load issues.
**How to apply:** When editing `render.yaml`, Dockerfiles, systemd units, or deploy docs, always use the factory form. If you see `app:app` in deploy config, fix it.

### 2026-05-12 — Strict CSP — no inline JS or CSS  (area: frontend / security)

**What:** The CSP set in `security.apply_security_headers` is `script-src 'self'; style-src 'self' https://fonts.googleapis.com; ...`. No `'unsafe-inline'`, no `'unsafe-eval'`.
**Why:** Defense in depth against XSS — any payload that escapes our escaping wouldn't be able to execute injected scripts.
**How to apply:** Don't add inline `<script>` blocks, `onclick=` handlers, or `style="..."` attributes to `templates/index.html`. All JS lives in `static/js/app.js`, all CSS in `static/css/style.css`. If a third-party widget needs a CSP relaxation, change it deliberately and document the reason.

### 2026-05-12 — SSRF guard runs *before* the request, not via `requests` hooks  (area: security / backend)

**What:** `security.validate_url()` resolves the hostname via `socket.getaddrinfo` and rejects any non-global IP **before** the outbound `requests.get` call. The actual request uses `allow_redirects=False` and `stream=True`.
**Why:** Validating after the request is too late (data may already have left). Disabling redirects prevents a TOCTOU bypass where a public host 302s to an internal one. Streaming lets us enforce `API_FETCH_MAX_RESPONSE` mid-download.
**How to apply:** Never remove `allow_redirects=False` from the `requests.get` in `routes.py`. If a feature legitimately needs redirects, validate the redirect target before following it. Don't replace the streamed read with `resp.json()` — that loses the size cap.

### 2026-05-12 — Acknowledged residual DNS-rebinding risk  (area: security)

**What:** There is a small TOCTOU window between `validate_url`'s DNS lookup and the `requests` library's connect. An attacker with sub-millisecond TTL DNS control could in theory rebind the hostname between the two.
**Why:** The alternative — patching `requests` to reuse our resolved IP and passing the original hostname via `Host:`/SNI — is fragile and breaks TLS verification in many configurations. The comment in `routes.py` documents the tradeoff.
**How to apply:** If this risk becomes unacceptable (e.g. moving from "internal tool" to "public SaaS"), the next step is a custom `HTTPAdapter` that re-resolves once and passes the IP plus a `Host` header. Don't quietly remove the comment in `routes.py` — it explains the threat model.

### 2026-05-12 — CSRF token is on every POST; tests disable it  (area: security / testing)

**What:** Flask-WTF CSRFProtect is initialized for the whole app. The token is exposed via `<meta name="csrf-token" ...>` and `app.js` attaches it to every POST as `csrf_token` (FormData) or `X-CSRFToken` (JSON body). `tests/conftest.py` sets `WTF_CSRF_ENABLED=False` for test client convenience.
**Why:** All state-changing routes accept browser form posts, so CSRF is mandatory. Disabling it in tests keeps fixtures simple — production behavior is exercised manually and via the security headers test.
**How to apply:** When adding a route that mutates state or returns sensitive data, it inherits CSRF protection automatically. Don't add `@csrf.exempt` without justification. When testing CSRF behavior, do so in a dedicated test that flips `WTF_CSRF_ENABLED` back on.

### 2026-05-12 — Unselected JSON triggers the tree-picker handshake  (area: backend / ux)

**What:** `/process` returns `{"needs_selection": true, "raw_json": <document>}` (HTTP 200) whenever no `json_path` was supplied. The frontend renders a JSON **tree picker** over `raw_json`; the user clicks any array or object node; the request is re-submitted with `json_path` set to the chosen dotted path.
**Why:** The original heuristic (`extract_table_data`) silently picked the first array it found, which surfaced the wrong data for nested API responses. Handing the client the document and letting the user point at a node is more honest than guessing — and unlike the earlier `candidates` list it can reach any level, not just arrays of objects.
**How to apply:** Don't "fix" the heuristic by being smarter — the selection prompt *is* the fix. The sentinel `'(root)'` is used when the top-level value is itself a list.

### 2026-05-12 — `flatten_for_csv` has a recursion-depth cap  (area: backend)

**What:** The recursion is bounded by `max_depth` (default 10, configurable via `FLATTEN_MAX_DEPTH`). At the cap, the remaining structure is JSON-stringified into a single cell instead of continuing to recurse.
**Why:** Adversarial or buggy payloads with cyclic-like deep nesting used to blow the Python stack. The cap turns "server 500" into "ugly but readable cell".
**How to apply:** If a legitimate use case needs deeper flattening, raise `FLATTEN_MAX_DEPTH` via env var rather than removing the guard.

### 2026-05-12 — Rate limiter is in-memory (single-process)  (area: deploy / security)

**What:** `RATELIMIT_STORAGE_URI = 'memory://'`. Each gunicorn worker has its own counter.
**Why:** The free tier runs one dyno; a Redis dependency would add cost and an external runtime requirement. Per-worker counting is good enough for abuse protection at this scale.
**How to apply:** If we ever scale to multi-worker or multi-instance, switch to `redis://...` and configure a Redis service. Do not assume the current limits are exact under load.

### 2026-05-12 — Frontend export split: CSV/TSV client-side, XLSX server-side  (area: frontend / backend)

**What:** CSV and TSV are generated in the browser from the `csv_data` already returned by `/process`. Excel goes to `POST /export-xlsx` because openpyxl runs server-side.
**Why:** CSV/TSV are trivial to build in JS and skipping the round-trip removes one extra request (and the associated CSRF + rate-limit accounting). XLSX needs a binary library; keeping `openpyxl` server-side avoids shipping a 1 MB JS bundle to every user.
**How to apply:** When adding new text-formatted exports (JSONL, NDJSON, Markdown table), prefer the client-side path. When adding binary formats (Parquet, ODS), add a server route and dependency.

### 2026-05-12 — `extensions.py` is its own module on purpose  (area: backend)

**What:** Flask-WTF and Flask-Limiter instances live in `extensions.py`, separate from `app.py`. `routes.py` imports `limiter` from there.
**Why:** Avoids circular imports — `routes.py` needs the limiter, but `app.py` needs to import `routes.py` to register the blueprint. Putting extensions in a third module breaks the cycle. This is the standard Flask app-factory pattern.
**How to apply:** Don't "consolidate" by moving the extension instances into `app.py` — the import graph will deadlock. New extensions belong in `extensions.py`.

### 2026-05-12 — Render free tier specifics  (area: deploy)

**What:** Free tier has no persistent disk, sleeps after ~15 minutes of inactivity, and cold-starts on the first request after sleep. `render.yaml` uses `generateValue: true` to auto-provision `SECRET_KEY`.
**Why:** Cost. The privacy stance (no disk) is also a free-tier feature, not a coincidence.
**How to apply:** Don't rely on in-process caches surviving across requests — workers can be restarted. Don't add a keep-alive ping; that defeats the cost benefit. Document the cold-start in user-facing materials if it becomes a complaint. Never commit a real `SECRET_KEY` to source control.

### 2026-05-12 — Pinned dependencies are deliberate  (area: deploy)

**What:** `requirements.txt` uses exact `==` pins (Flask 3.1.3, requests 2.33.0, gunicorn 22.0.0, Flask-WTF 1.2.1, Flask-Limiter 3.5.0, openpyxl 3.1.5). Test tooling lives in `requirements-dev.txt`, and the optional Redis client in `requirements-redis.txt`.
**Why:** Render auto-deploys on push. Loose pins + auto-deploy = surprise breakage. Exact pins keep deploys reproducible and make security audits possible.
**How to apply:** Bump versions intentionally in a dedicated commit, run the full test suite, and verify the Render build before merging. Don't bump on a feature commit "while we're in here".

### 2026-08-21 — Spreadsheet exports are formula-sanitized; JSONL and Markdown are not  (area: security)

**What:** Values starting with `=`, `+`, `-`, `@`, tab, CR or LF are formula triggers (CWE-1236). CSV/TSV prefix them with a single quote; XLSX instead pins the cell's `data_type` to `'s'`, because openpyxl serializes a leading `=` as a *formula cell* and Excel then runs it without the CSV warning. JSONL and Markdown exports are deliberately exempt.
**Why:** The tool's whole job is turning untrusted API/file JSON into spreadsheets, so an attacker who controls a cell controls the exported file's formulas. The exemptions are not oversights: JSON carries types and nothing evaluates it, so a quote prefix would corrupt data while protecting nothing; Markdown does not evaluate `=` either, but an unescaped pipe or newline breaks the table, so it gets Markdown-specific escaping.
**How to apply:** Any new **spreadsheet-compatible** export must route cells through `helpers.sanitize_cell` (or pin the data type, for typed formats). Any new **non-spreadsheet** format (JSONL, Markdown, ...) must not. There are four sanitized paths today — two server routes plus the client CSV and TSV builders — and `tests/js/test_export_sanitize.mjs` exists so none of them can regress silently.

### 2026-08-21 — The API-fetch failure log is a fixed string  (area: security)

**What:** `logger.warning('API request failed')` — no interpolation, ever.
**Why:** `requests`' exception text embeds the full URL. With query-param auth the token rides in that URL, so the old `'API request failed: %s'` wrote secrets to stdout. Query strings, fragments, userinfo **and paths** can all carry tokens, so a redaction helper that preserves the path is not sufficient.
**How to apply:** Never add the URL, the exception, or any request field to a log line on this path. `caplog` tests assert no URL component reaches the logs; keep them passing.

**Owner / source:** security review F3/F9.

### 2026-08-21 — DNS is bounded in *concurrency*, not in execution  (area: security / performance)

**What:** Lookups run on a shared, fixed-size `ThreadPoolExecutor` created lazily inside the worker (it records its pid, so a pool inherited across a fork is replaced). The admission permit is taken *before* `submit` and released from the future's **done-callback**, never from the caller's `finally`.
**Why:** `getaddrinfo` takes no timeout and cannot be cancelled. `API_DNS_TIMEOUT` bounds only how long the *request* waits; the lookup keeps running. Releasing the permit on caller timeout would re-admit work into an already-blocked pool, which is exactly how it saturates under repeated slow-DNS requests. **Teardown is not bounded by anything this code controls** — glibc's defaults are ~5s per nameserver × 2 attempts × every nameserver in `resolv.conf`, so tens of seconds is the realistic worst case.
**How to apply:** Do **not** describe teardown as bounded in any doc, comment or test. Assert the caller wait and the admission error instead. `options timeout:2 attempts:1` in the container's `resolv.conf` is a best-effort narrowing; a killable subprocess resolver is the only real bound and is not in v1.2.

**Owner / source:** security review F6.1, performance review P7.

### 2026-08-21 — `APP_ENV=production` is the only production signal  (area: deploy / security)

**What:** One env var, read through one helper (`config.is_production()`), gating the SECRET_KEY fail-fast, `SESSION_COOKIE_SECURE`, and the rate-limit topology guard.
**Why:** Two accepted spellings let a deployment satisfy one gate and silently miss another — e.g. passing the secret-key check with `Secure` cookies still off, a live vulnerability produced purely by the inconsistency. And production is never inferred from `not DEBUG`: the documented local run `python app.py` has `DEBUG=False`, so that would block ordinary development.
**How to apply:** New production-only behavior calls `is_production()`. Never add `PRODUCTION=true`, `ENV=prod`, or any alias — a test asserts `PRODUCTION=true` alone is *not* honored.

**Owner / source:** security review F7/F16.

### 2026-08-21 — `memory://` rate-limit counters multiply by workers × replicas  (area: deploy)

**What:** The default storage is process-local, so N workers on M instances enforce N×M times the configured limit. `RATELIMIT_STORAGE_URI` is configurable (it was hardcoded before v1.2). Under `APP_ENV=production` the app refuses to start unless `WEB_CONCURRENCY` and `APP_REPLICAS` are declared, the start command's `--workers` agrees with `WEB_CONCURRENCY`, and storage is shared whenever either count exceeds one.
**Why:** Defaults of 1 fail *open* — an undeclared 4-worker deployment reads as single-worker, which is exactly where the guard matters most. `WEB_CONCURRENCY` is the single source of truth because gunicorn reads it natively, so the number the app validates cannot drift from the number gunicorn runs.
**How to apply:** To run more than one worker or instance: install `requirements-redis.txt`, set `RATELIMIT_STORAGE_URI=redis://…`, then raise the counts. Never write a bare `--workers N` into a start command — derive it from `$WEB_CONCURRENCY`. `APP_REPLICAS` must mirror `render.yaml`'s `numInstances`.

**Owner / source:** security review F12, roadmap 2.10.

### 2026-08-21 — API fetch is restricted to ports 80, 443 and 8443  (area: security)

**What:** `API_ALLOWED_PORTS` (default `80,443,8443`), checked before DNS so a rejected URL costs no lookup. An empty value disables the check.
**Why:** Only the resolved IP was validated, so `http://public.example.com:22` or `:6379` passed and the tool would connect to any port on any public host.
**How to apply:** Widen the list via env rather than in code, and keep the check ahead of resolution.

**Owner / source:** security review F6.2, decision D5.

### 2026-08-21 — The XLSX export budget is measured, in cells, and on by default  (area: performance)

**What:** `MAX_EXPORT_CELLS` (default 250,000) caps Excel exports only. CSV/TSV are generator-streamed and stay uncapped.
**Why:** openpyxl memory tracks `rows × columns`, not rows — at equal cell counts a narrow, tall sheet costs *more* (84.3 MiB at 50k×3 vs 73.6 at 15k×10), so a row limit says almost nothing about the footprint. The default comes from the measurement in `docs/export-budget-v1.2.md`, not from feel. An unlimited default would leave a High finding unmitigated; uncapped CSV/TSV is what keeps the export contract as wide as the input contract.
**How to apply:** Re-derive the number whenever the measurement is re-run — do not round it to something tidy. Never truncate an oversized export: `/process` advertises `total_cells`/`max_export_cells` so the client greys Excel out beforehand, and `/export-xlsx` returns 400 for direct callers. And keep exports diskless: openpyxl's `write_only` mode writes worksheet parts to OS temp files, and `SpooledTemporaryFile` is either pointless (its default `max_size=0` never rolls over) or disk-backed.

**Owner / source:** performance review P3, decision D6.

### 2026-08-21 — gunicorn's `--timeout` must exceed `API_FETCH_TIMEOUT`  (area: deploy)

**What:** Every documented invocation sets `--timeout 60` against a default `API_FETCH_TIMEOUT` of 30s.
**Why:** gunicorn's default timeout is also 30s, so a slow API fetch raced the worker kill: the worker was SIGKILLed mid-response and the client saw a 502 instead of the timeout message.
**How to apply:** If you raise `API_FETCH_TIMEOUT`, raise `--timeout` with it — roughly double is the documented margin.

**Owner / source:** performance review P9.

### 2026-08-21 — The preview is a truncated copy; exports are not  (area: backend)

**What:** `helpers.preview_truncate` builds a *new* row capping long strings, nested objects and nested arrays. `table_data` and `csv_data` are never mutated.
**Why:** Preview rows used to carry full-fidelity nested structures, so a 50k-key object or a 5 MB string cell froze the tab. Truncating in place would have silently corrupted every export.
**How to apply:** Anything that trims data for display must build a projection. Tests assert the server CSV and XLSX exports still contain the untruncated values — keep them.

**Owner / source:** performance review P2.2/P5.


---
### 2026-08-22 — `routes.py` must never import `app.py`  (area: backend)

**What:** Shared utilities go in `helpers.py` (or another leaf module), never in `app.py`. `helpers.format_size` is there for exactly this reason.
**Why:** `create_app()` imports `bp` from `routes.py`, so a module-level `from app import ...` in `routes.py` makes `import routes` re-enter a half-initialized module and raise `ImportError`. It hid for a while because gunicorn's `app:create_app()` imports app-first, which happens to work — only routes-first entry points broke.
**How to apply:** `TestNoImportCycle` in `tests/test_routes.py` imports each module first in a fresh subprocess and AST-checks that `routes.py` does not import `app`. If you need something from `app.py` in a route, move it down, don't import up.

**Owner / source:** CodeRabbit review on the v1.2.0 PR.


---

### 2026-08-22 — A blank element in an integer-list env var is an error, not a default  (area: deploy / security)

**What:** `config.env_int_set` rejects `80,,443`, `80,443,` and a lone `,`. Only an *unset* variable selects the default; only a fully empty value disables the check.
**Why:** `security.validate_url` reads an empty allowlist as "no port restriction". Skipping blank elements meant `API_ALLOWED_PORTS=,` silently removed the outbound port restriction, and `80,,443` silently narrowed it — both from a typo, with no startup error.
**How to apply:** Any list-valued setting whose empty state weakens a check must fail loudly on a malformed element. Never `if part.strip()` your way past bad input in a security setting.

**Owner / source:** CodeRabbit review on the v1.2.0 PR.


---

## Conventions for Adding Entries

- **Date** in `YYYY-MM-DD` so entries sort naturally.
- **Tag the area** so contributors can filter (`backend`, `frontend`, `security`, `deploy`, `testing`, `ux`, `meta`).
- **Past tense for what happened, present for the rule.** "We tried X, it broke. **Don't use X.**"
- **Don't duplicate code documentation.** If the answer is "read the docstring", don't write a memory entry — improve the docstring.
- **Prefer linking out** for long context (Linear ticket, PR, incident postmortem) rather than inlining a wall of text.

## When to Promote a Memory Entry

If an entry is referenced repeatedly or applies to *every* contributor (not just "people working in this area"), promote it:

- Project-wide conventions → `CLAUDE.md` and/or `AGENTS.md`.
- User-facing behavior → `README.md`.
- Setup / deploy specifics → `README.md` or a dedicated `docs/` page.

Memory entries are for **non-obvious** context. Once an entry becomes obvious because the code, docs, or onboarding caught up, retire it.
