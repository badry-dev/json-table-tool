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
**How to apply:** Reject any change that adds a DB driver, file write of payload bytes, third-party analytics, or request-body logging. `logger.warning("API request failed: %s", e)` is fine; `logger.warning("payload was: %s", body)` is not.

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

### 2026-05-12 — Multi-array JSON triggers a path-selector handshake  (area: backend / ux)

**What:** `/process` returns `{"needs_selection": true, "candidates": [...]}` (HTTP 200) when `find_candidate_arrays` reports more than one array of objects in the payload. The frontend opens a modal; the user picks; the request is re-submitted with `json_path` set to the chosen dotted path.
**Why:** The original heuristic (`extract_table_data`) silently picked the first array it found, which surfaced the wrong data for nested API responses. Returning candidates is more honest than guessing.
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

**What:** `requirements.txt` uses exact `==` pins (Flask 3.0.0, requests 2.31.0, gunicorn 21.2.0, Flask-WTF 1.2.1, Flask-Limiter 3.5.0, pytest 7.4.4, openpyxl 3.1.2).
**Why:** Render auto-deploys on push. Loose pins + auto-deploy = surprise breakage. Exact pins keep deploys reproducible and make security audits possible.
**How to apply:** Bump versions intentionally in a dedicated commit, run the full test suite, and verify the Render build before merging. Don't bump on a feature commit "while we're in here".

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
