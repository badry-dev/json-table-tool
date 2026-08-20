# Security Review — JSON Table Converter (v1.2 planning)

**Date:** 2026-08-20
**Scope:** `app.py`, `config.py`, `extensions.py`, `security.py`, `helpers.py`, `routes.py`, `templates/index.html`, `static/js/app.js`, `requirements.txt`, `render.yaml`, deployment docs
**Method:** Manual source audit + standard-library probing of SSRF edge cases (`urlparse`/`getaddrinfo`/`ipaddress`). Full `pip-audit`/pytest could not be re-run in this sandbox (no pip); the dependency findings below were originally confirmed by `pip-audit` in `docs/code-health-final.md` (2026-05-02) and the pins are unchanged since.
**Threat model:** Unauthenticated, internet-facing web service (Render free tier, no persistence, no auth). Attacker can submit arbitrary JSON/JSONL via paste/file and arbitrary URLs via the API-fetch feature.

---

## 1. Executive Summary

The application has a strong security posture for its size: mandatory CSRF, SSRF pre-validation with `allow_redirects=False`, strict CSP with no inline scripts, consistent `escapeHtml()` on all dynamic frontend rendering, generic error messages, and deliberate no-storage/no-payload-logging. Those fundamentals are solid and must be preserved.

However, the audit found **1 Critical, 3 High, and 7 Medium** issues that should be addressed in the next version. The most serious is **CSV/Excel formula injection (CWE-1236)** — the core feature of this tool (converting untrusted API/file JSON into spreadsheet files) actively enables it. The second most urgent is the **unpatched dependency set** (`gunicorn 21.2.0` carries a High-severity HTTP request-smuggling CVE). Several smaller issues (credential leakage in error logs, user-controlled outbound header names, missing hardening headers, DNS-lookup DoS, no SECRET_KEY fail-fast) are cheap to fix.

| Severity | Count | Items |
|---|---|---|
| Critical | 1 | F1 CSV/Excel formula injection |
| High | 3 | F2 Dependency CVEs (gunicorn smuggling), F6 SSRF worker starvation (DNS, no timeout), F12 Rate limiting ineffective behind proxy |
| Medium | 7 | F3 Credential leak in error logs, F4 User-controlled outbound header name, F5 Security-header gaps + no HSTS, F7 Default SECRET_KEY no fail-fast, F8 Recursion-depth DoS, F9 API JSONL → 500 + response snippet in logs, F11 Missing no-store cache control |
| Low | 5 | F10 413 handled by HTML, F13 Upload validation, F14 Credentials over plain HTTP (deploy guidance), F15 `/health` version disclosure, F16 JWT/CSRF session cookie flags |
| Info | 1 | F17 Documentation drift (MIT vs GPL, stale candidates handshake) |

**Quick wins (≤1h each):** F4, F5, F7, F9, F10, F11, F15.
**Must-do before next deploy:** F1, F2.

---

## 2. Findings

### F1 — CSV / Excel formula injection (CWE-1236) — **Critical**

**Location:** `routes.py:217-238` (`export_csv`), `routes.py:262-277` (`export_xlsx`), `static/js/app.js:482-513` (`downloadDelimited`).

**Description:** Cell values beginning with `=`, `+`, `-`, or `@` are written verbatim into CSV/TSV/XLSX output. When the exported file is opened in Excel/LibreOffice, those values are evaluated as formulas (e.g. `=HYPERLINK("http://evil.example","click")`, `=cmd|' /C calc'!A0`, `=1+1`). The app's core workflow is converting *untrusted* API responses and file uploads into spreadsheets — an attacker who controls any cell value controls the exported file's formulas.

For XLSX this is confirmed behavior of `openpyxl` (3.1.2): a string value starting with `=` is serialized as a formula cell, not a string. Both the server-side CSV path (`csv.DictWriter`) and the client-side CSV/TSV path write the raw string.

**Exploitation:** User (or automated pipeline) converts `[{"name": "=HYPERLINK(\"https://evil.example/\",\"click\")"}]` and exports CSV or XLSX; opening the file in Excel triggers the formula → credential/CSV exfiltration or malware download. The XLSX path is worse because Excel formulas run without the "formula in CSV" warning.

**Remediation:** Sanitize all cell values before serialization in all four export paths (server CSV, server XLSX, client CSV, client TSV): if the value starts with `=`, `+`, `-`, `@` (or tab/CR), prefix it with a single quote `'` (Excel's string-escape) — or refuse/blank it. Centralize in one helper on each side:
- Backend: `sanitize_cell(value)` in `helpers.py`, used by both `export_csv` and `export_xlsx` (replaces the duplicated `isinstance(v, (dict, list))` branches — see roadmap refactor).
- Frontend: sanitize inside `downloadDelimited()`'s `escape()` and in the `formatValue()` path only for exports (preview can keep rendering raw text, but display-only).

**Effort:** 1-2h. **Tests:** extend `tests/test_routes.py` with `=SUM(A1)`, `@cmd`, `+`, `-` values for both export routes; add a JS-adjacent assertion path if feasible.

---

### F2 — Unpatched dependency vulnerabilities — **High**

**Location:** `requirements.txt` (all pins unchanged since 2026-05 audit).

**Description:** `pip-audit` in `docs/code-health-final.md` reported 7 known CVEs; the pins are still old:

| Package | Pin | CVE(s) | Fix |
|---|---|---|---|
| `gunicorn` | `21.2.0` | CVE-2024-1135 (**High**, HTTP request smuggling), CVE-2024-6827 | `22.0.0` |
| `requests` | `2.31.0` | CVE-2024-35195, CVE-2024-47081, CVE-2026-25645 | `2.33.0` |
| `Flask` | `3.0.0` | CVE-2026-27205 | `3.1.3` |
| `pytest` | `7.4.4` | CVE-2025-71176 (test-only) | `9.0.3` |
| `openpyxl` | `3.1.2` | `datetime.utcnow()` DeprecationWarning (informational) | `3.1.5` |

**Impact:** gunicorn request smuggling is reachable only when combined with a front proxy that de-duplicates Content-Length/Transfer-Encoding differently than gunicorn — precisely the Render/Nginx deployment described in the README.

**Remediation (roadmap Phase 0):**
- `requirements.txt`: `Flask==3.1.3`, `requests==2.33.0`, `gunicorn==22.0.0`, `openpyxl==3.1.5`.
- Move `pytest==9.0.3` (and future `ruff`, `coverage`, `pip-audit`) into a new `requirements-dev.txt`.
- Re-run `pip-audit -r requirements.txt` at implementation time (newer fixes may exist) and pin exactly.
- Keep "exact pins + dedicated bump commit + full test suite" convention from `MEMORY.md`.

**Effort:** 30-60m + full test pass. **Risk:** Flask 3.1 deprecates nothing used here; verify `WTF_CSRF_ENABLED` and limiter behavior in tests.

---

### F3 — Credential leakage into server logs (query-param auth) — **Medium**

**Location:** `routes.py:148` — `logger.warning('API request failed: %s', e)`.

**Description:** When the connection fails, `requests` exception messages include the **full URL including query string**. With `auth_method == 'query_param'` (routes.py:105-109) the token rides in the URL, so `logger.warning(...)` writes the secret into stdout logs — a direct violation of the "no payload logging / no credential logging" stance. Example message: `HTTPConnectionPool(host='api.example.com', port=443): Max retries exceeded with url: /data?api_key=SECRET ...`.

**Remediation:** Log a sanitized representation only:
```python
except requests.exceptions.RequestException:
    logger.warning('API request failed for %s', redact_url(api_url))
```
Add `redact_url()` (strip query + fragment + userinfo) to `security.py` or `helpers.py`. Keep the generic user-facing `'API request failed'` response.

**Effort:** 30m. **Tests:** unit-test `redact_url`; extend `TestApiFetch` to assert the log message (via `caplog`) does not contain the token.

---

### F4 — User-controlled outbound HTTP header name — **Medium**

**Location:** `routes.py:91-95` — `header_name = request.form.get('api_key_header', 'X-API-Key')` then `headers[header_name] = api_key`.

**Description:** The client supplies the header *name*. A malicious user can set it to `Host`, `Content-Length`, `Transfer-Encoding`, `Connection`, `Authorization`, `Referer`, etc. and `requests` will forward it to the target. `Host` override + the DNS-validated hostname is a (limited) SSRF-adjacent capability; `Transfer-Encoding`/`Content-Length` on the outbound request can produce malformed requests to the target.

**Remediation:** Allowlist header names: only `[A-Za-z0-9-]` plus reject reserved/ hop-by-hop headers (`host`, `content-length`, `transfer-encoding`, `connection`, `proxy-*`, `authorization`, `cookie`, `x-csrf*`). Simplest robust rule: only permit `X-`-prefixed custom headers (matches the UI's default `X-API-Key`), or a fixed allowlist. Validate with a regex and 400 on violation.

**Effort:** 30m. **Tests:** parameterized test in `TestApiFetch`.

---

### F5 — Security-header gaps — **Medium**

**Location:** `security.py:45-58` (`apply_security_headers`).

**Description:** Current headers are good but incomplete:

| Missing | Why it matters |
|---|---|
| `Strict-Transport-Security` (HSTS) | No HSTS on a TLS-terminated deploy; users are vulnerable to SSL-stripping on first visit |
| `object-src 'none'`, `base-uri 'self'`, `frame-ancestors 'none'`, `form-action 'self'` in CSP | Shrinks XSS blast radius (object/embed/plugin attacks, `<base>` hijacking, clickjacking via iframes, form exfiltration) |
| `Permissions-Policy` | Disables unused browser features (geolocation, camera, mic) |
| `Cross-Origin-Opener-Policy: same-origin` | Mitigates cross-origin window-opener attacks |
| `Cross-Origin-Resource-Policy: same-origin` | Prevents other origins from embedding/reading our responses |

Also consider `upgrade-insecure-requests` in CSP for HTTPS-only deploys.

**Remediation:**
```python
response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'  # only when request.is_secure / X-Forwarded-Proto=https
response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
CSP += "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
```
`X-Frame-Options: DENY` stays as legacy fallback. Guard HSTS behind `is_secure` (or a `FORCE_HTTPS` config) so local `http://localhost` dev is unaffected.

**Effort:** 1h. **Tests:** extend `TestSecurityHeaders` to assert each new header; ensure CSP still allows Google Fonts and `data:` images.

---

### F6 — SSRF gaps: blocking DNS lookup, no port restriction, residual rebinding — **Medium**

**Location:** `security.py:23-26` (`socket.getaddrinfo(hostname, None)`), `routes.py:119-127`.

**Description:** Three distinct items:

1. **No timeout on `getaddrinfo`.** The call blocks the gunicorn worker for as long as DNS takes. An attacker can submit URLs with slow/unresponsive DNS nameservers and starve workers (rate limit 30/min bounds but does not eliminate this). This is both a security and a performance finding (see `PERFORMANCE_REVIEW` P7).
2. **Ports are unrestricted.** `http://public.example.com:22` or `:6379` passes validation because only the IP is checked; the tool will happily connect to any port on any public host. Low severity (public hosts only) but worth a documented decision.
3. **DNS rebinding TOCTOU** is acknowledged in `routes.py:116-118` and `MEMORY.md`; acceptable for an internal tool. Revisit if the app ever becomes a public SaaS.

**What I verified as solid (do not regress):** decimal/hex IP forms (`2130706433`, `0x7f000001`) resolve via `getaddrinfo` to `127.0.0.1` and are rejected; IPv4-mapped IPv6 (`[::ffff:7f00:1]`) has `is_global=False` and is rejected; userinfo tricks (`http://evil@127.0.0.1`) yield hostname `127.0.0.1` and are rejected; `nip.io`-style wildcard domains resolve to real IPs and are checked; `allow_redirects=False` + `raise_for_status()` means 3xx responses never re-connect.

**Remediation (item 1, High-ish priority):**
- Resolve DNS in a bounded way: run `getaddrinfo` in a `ThreadPoolExecutor` with `API_DNS_TIMEOUT` (default ~3s), or use a resolver with an explicit timeout (`socket.setdefaulttimeout` does not reliably cover `getaddrinfo`).
- Add `API_ALLOWED_PORTS` (default `80,443,8443`) — cheap and kills most non-HTTP abuse.
- Keep the residual-rebinding comment; document the port decision in `MEMORY.md`.

**Effort:** 1-2h. **Tests:** mock `getaddrinfo` to raise/sleep and assert bounded wall time; port rejection tests.

---

### F7 — Default SECRET_KEY has no production fail-fast — **Medium**

**Location:** `config.py:9`, `app.py:9-25`.

**Description:** `SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')`. If an operator forgets to set it (README calls it "Required: Yes"), the app silently runs with a *publicly known* key: CSRF tokens are forgeable and the session cookie can be signed. `render.yaml` sets `generateValue: true`, but self-hosted / Docker deploys from README rely on the operator.

**Remediation:**
- In `create_app()`, after config load: if `DEBUG` is False and `SECRET_KEY` equals the dev default (or is `None`/empty), `raise RuntimeError('SECRET_KEY must be set in production')`.
- Also validate that config integers are actually integers (env typo like `MAX_UPLOAD_SIZE=abc` currently raises `ValueError` at import time with a confusing traceback; wrap with clear messages).

**Effort:** 30m. **Tests:** `create_app` raises when `Config(SECRET_KEY='dev-secret-key-change-in-production')` + `DEBUG=False`; no regression for the test fixture (tests run with `TESTING=True` — bypass check when `TESTING`).

---

### F8 — Recursion-depth DoS in data-processing helpers — **Medium**

**Location:** `helpers.py:34-62` (`extract_table_data` recurses at lines 54-58), `helpers.py:82-111` (`find_candidate_arrays` recurses at line 109).

**Description:** `flatten_for_csv` has a `max_depth` guard, but the other two recursive helpers do not. A 10 MB JSON payload nested ~1000+ levels deep (valid JSON) will hit Python's recursion limit inside `extract_table_data`/`find_candidate_arrays` → `RecursionError` → 500 (or worse, in older interpreters, C-stack issues). The server also has no JSON-parse depth control.

**Remediation:**
- Add `_depth=0, max_depth=...` guards to `extract_table_data` and `find_candidate_arrays` mirroring `flatten_for_csv`'s pattern (deep remainder → JSON-stringify or bail to a single row).
- Defensively wrap `json.loads`/`parse_jsonl` calls: catch `RecursionError` and return a 400 (`'JSON nesting too deep'`).
- Note: CPython's `json` C parser can itself raise `RecursionError` on pathological nesting — that is caught by the same wrapper.

**Effort:** 1h. **Tests:** construct a 1500-deep nested structure (iteratively, no recursion in the test) and assert 400 or graceful degradation; `extract_table_data` on depth-capped input.

---

### F9 — API JSONL parse failure returns 500 and logs a response snippet — **Medium / Low**

**Location:** `routes.py:139-151` (API branch) + `routes.py:197-199` (outer handler).

**Description:** In the API branch, `parse_jsonl(text)` raises `ValueError` (with a message containing the *offending line of the API response*), but only `Timeout`, `RequestException`, and `JSONDecodeError` are caught. The `ValueError` propagates to the outer `except Exception` → returns `500 'An internal error occurred'` (wrong status: client error → should be 400) **and** `logger.exception` writes the `ValueError` message — which includes a snippet of the API response — into server logs. Same class of leak as F3.

**Remediation:** In the API branch, add `except ValueError: return jsonify({'error': 'API response is not valid JSONL'}), 400` (before the generic handler), and never let `parse_jsonl` messages reach `logger.exception` for the API path. For file/paste the `ValueError` path is already handled with 400 (`routes.py:62-63, 74-75`) and is the user's own data — acceptable to keep verbatim.

**Effort:** 30m. **Tests:** mock API returning malformed JSONL → assert 400 and (via `caplog`) that no response snippet is logged (this is the known-uncovered branch from `docs/code-health-final.md` §4.2).

---

### F10 — Oversized-request rejection is HTML, not JSON — **Low**

**Location:** `config.py:12` (`MAX_CONTENT_LENGTH`), app-wide.

**Description:** Requests over 10 MB hit Flask's built-in 413 handler which returns an HTML page. Every other error path in this app returns `{"error": ...}` JSON, so client code (`response.json()` in `app.js:127`) will throw a `SyntaxError` on the HTML body and surface a confusing error.

**Remediation:** Register an `app.errorhandler(413)` returning `jsonify({'error': 'Request too large (max 10MB)'}), 413`. Optionally also a generic `500` JSON handler for non-route errors.

**Effort:** 20m. **Tests:** POST a >10 MB body → assert 413 + JSON.

---

### F11 — No `Cache-Control: no-store` on data-bearing responses — **Low**

**Location:** `routes.py:188-195` (`/process`), `routes.py:230-238`, `routes.py:283-289`.

**Description:** `/process` and the export endpoints return sensitive payload data. Without `Cache-Control`, shared caches/proxies/browser bfcache may retain it. The index page can be cached; data responses should not.

**Remediation:** In `apply_security_headers` or per-route: `response.headers['Cache-Control'] = 'no-store'` for `/process`, `/export-csv`, `/export-xlsx`, `/health`; keep default/`public` for `/` and static assets (see performance review P6).

**Effort:** 20m. **Tests:** assert header on the four routes.

---

### F12 — Rate limiting is ineffective behind a proxy — **High**

**Location:** `extensions.py:7` (`Limiter(key_func=get_remote_address)`), `config.py:21` (`memory://`), deployment (Render/Nginx).

**Description:** `get_remote_address` uses `request.remote_addr`. Behind Render's load balancer / Nginx, every request appears to come from the proxy IP, so **all users share one rate-limit bucket** — an attacker can exhaust the entire site's `/process` quota for everyone (availability), and per-user limits don't exist. Additionally, `memory://` storage is per-gunicorn-worker: with N workers the effective limit is N× the configured one (documented in `MEMORY.md`, but the proxy issue is not).

**Remediation:**
- Configure `ProxyFix` (Werkzeug) in `create_app()` with `x_for=1, x_proto=1, x_host=1` **only when behind a trusted proxy** (opt-in via env var, e.g. `TRUST_PROXY=1` — do not trust client-supplied `X-Forwarded-For` unconditionally, that's spoofable).
- Alternatively set a custom `key_func` that uses the rightmost non-trusted hop.
- Keep `memory://` for single-instance; document Redis (`RATELIMIT_STORAGE_URI=redis://...`) as the multi-worker/multi-instance upgrade (project decision point, see roadmap).

**Effort:** 1h. **Tests:** with `TRUST_PROXY=1`, assert `request.remote_addr` is the client IP from `X-Forwarded-For`.

---

### F13 — Upload validation: extension and content-type unchecked — **Low**

**Location:** `routes.py:48-63`.

**Description:** `accept=".json,.jsonl"` is client-side only; the server accepts any filename/extension and any `Content-Type`. Not a vulnerability by itself (content is parsed strictly), but it enables confusion and wastes processing on binary junk.

**Remediation:** Reject uploads whose filename does not end in `.json`/`.jsonl` (or whose declared `Content-Type` is not `application/json` / `application/x-ndjson` / `text/plain`) with a 400.

**Effort:** 30m. **Tests:** upload `evil.txt` → 400.

---

### F14 — Credentials flow over plain HTTP when deployed without TLS — **Low (deployment)**

**Location:** README deployment options (own server / Railway / Fly).

**Description:** API keys, bearer tokens, and basic-auth passwords are POSTed from the browser to this app. Any deployment without HTTPS exposes them. Render and the Nginx guide provide TLS; the other quick-start options do not state it.

**Remediation:** Documentation only: make "HTTPS required" explicit in every deployment path; add `upgrade-insecure-requests` to CSP (F5); optionally refuse to run the API-fetch feature over plain HTTP.

**Effort:** 30m (docs).

---

### F15 — `/health` discloses version — **Low / Info**

**Location:** `routes.py:29-35`.

**Description:** Version string aids attackers in targeting known CVEs. Common tradeoff for ops tooling.

**Remediation:** Keep the endpoint but make version disclosure configurable (`HEALTH_REVEAL_VERSION=1` default off, or include it only when an `X-Health-Token` matches). Not urgent; log the decision in `MEMORY.md`.

---

### F16 — Session/cookie hardening — **Low**

**Location:** `config.py` (no `SESSION_COOKIE_*`), `render.yaml`.

**Description:** Flask's default session cookie lacks explicit `HttpOnly`/`SameSite`/`Secure` configuration (defaults: `HttpOnly` yes, `SameSite=None` in recent Flask, `Secure` only when `is_secure` — i.e. misdetected behind the proxy without ProxyFix). Given no server-side sessions are used, the CSRF token is the real secret — still worth locking down.

**Remediation:** Set explicitly: `SESSION_COOKIE_HTTPONLY = True`, `SESSION_COOKIE_SAMESITE = 'Lax'`, `SESSION_COOKIE_SECURE = not DEBUG` (coupled with ProxyFix from F12 so `is_secure` is correct). Optionally `WTF_CSRF_SSL_STRICT`.

**Effort:** 20m. **Tests:** config assertions.

---

### F17 — Documentation drift — **Info**

**Location:** `MEMORY.md:66-70`, `CLAUDE.md:96`, `AGENTS.md` (project snapshot), `README.md:6,434-436`, `LICENSE` (GPL-3.0 vs README/CLAUDE MIT).

**Description:** Several docs describe the **old** multi-array handshake (`/process` returns `candidates`) but the code (commit `e537042`) returns `raw_json` and the frontend shows a JSON tree picker. Also the repo license is now GPL-3.0 (`LICENSE`, commit `400f15a`) while README/CLAUDE still claim MIT and the README badge references no file. Stale docs mislead future contributors (e.g. an agent could "re-add" the candidates field).

**Remediation:** Update `MEMORY.md` (multi-array handshake entry → tree-picker), `CLAUDE.md` `/process` description, `AGENTS.md` snapshot, README license text/badge; add CHANGELOG. Folded into roadmap Phase 5.

---

## 3. Finding-to-Remediation Matrix

| ID | Finding | Severity | Remediation | Effort |
|---|---|---|---|---|
| F1 | CSV/XLSX formula injection | Critical | Sanitize `=+-@` leading chars in all 4 export paths | 1-2h |
| F2 | 7 dependency CVEs (gunicorn smuggling High) | High | Pin upgrades + dev-deps split + re-audit | 1h |
| F12 | Rate limit shared-bucket behind proxy | High | ProxyFix opt-in + key_func | 1h |
| F6 | DNS lookup no timeout / ports unrestricted | Medium | Bounded resolver + port allowlist | 1-2h |
| F3 | Query-param token in error logs | Medium | `redact_url()` + generic log | 30m |
| F4 | User-controlled outbound header name | Medium | Header-name allowlist/regex | 30m |
| F5 | Missing hardening headers / HSTS | Medium | Extend `apply_security_headers` | 1h |
| F7 | Dev SECRET_KEY accepted in prod | Medium | Startup fail-fast + config validation | 30m |
| F8 | Recursion-depth DoS in helpers | Medium | Depth guards + RecursionError → 400 | 1h |
| F9 | API JSONL ValueError → 500 + log snippet | Medium | Catch ValueError in API branch | 30m |
| F11 | No `Cache-Control: no-store` on data | Low | Headers on data routes | 20m |
| F10 | 413 returns HTML | Low | JSON error handlers | 20m |
| F13 | Upload extension/type unchecked | Low | Filename/content-type checks | 30m |
| F14 | Plain-HTTP credential exposure | Low | Docs + CSP upgrade-insecure-requests | 30m |
| F15 | `/health` version disclosure | Low | Config-gated version | 30m |
| F16 | Session cookie flags | Low | Explicit cookie config | 20m |
| F17 | Docs drift (license, handshake) | Info | Doc sync in roadmap Phase 5 | 1h |

---

## 4. Verification Checklist (post-fix)

- [ ] Export CSV, TSV, XLSX with values `=SUM(A1)`, `@cmd`, `+1`, `-1`, `'`, tab, CR — open result in a spreadsheet and confirm **no formula executes** (values render as text).
- [ ] `pip-audit -r requirements.txt` → 0 vulnerabilities; full `pytest` suite green.
- [ ] SSRF: `http://127.0.0.1`, `http://169.254.169.254`, `http://2130706433`, `http://[::ffff:7f00:1]`, `http://0x7f000001` all → 400.
- [ ] Slow-DNS hostname (mock) does not block a worker beyond the configured DNS timeout.
- [ ] A POST without CSRF token → 400; with forged SECRET_KEY default in prod mode → app refuses to start.
- [ ] `logger.warning` output contains no URL query strings, tokens, or API-response snippets (`caplog`-based tests).
- [ ] Response headers: HSTS (secure requests), `Permissions-Policy`, `COOP`, `CRP`, extended CSP (`object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'`).
- [ ] Data routes send `Cache-Control: no-store`.
- [ ] >10 MB POST → JSON 413; 1500-deep JSON → 400 not 500.
- [ ] API-fetch of malformed JSONL → 400 with generic message.
- [ ] With `TRUST_PROXY=1`, rate-limit buckets are per-client-IP.
