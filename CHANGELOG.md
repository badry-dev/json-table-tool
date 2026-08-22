# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-08-21 — "Hardening & Performance"

Implements `docs/roadmap-v1.2.md`, closing every finding in
`docs/security-review-v1.2.md` (F1–F17) and `docs/performance-review-v1.2.md`
(P1–P13).

No response key changed name, type or meaning; `/process` only gained keys.

### Security

- **CSV/Excel formula injection (F1, Critical).** Values beginning with
  `=`, `+`, `-`, `@`, tab, CR or LF were written verbatim into every export.
  CSV/TSV now prefix them with a single quote; XLSX pins the cell's `data_type`
  to a string, since openpyxl otherwise serializes a leading `=` as a formula.
  Applies to all four export paths, headers included. JSONL and Markdown exports
  are deliberately exempt — see *Added*.
- **Dependency CVEs (F2, High).** Flask 3.1.3, requests 2.33.0, gunicorn 22.0.0
  (CVE-2024-1135 request smuggling), openpyxl 3.1.5.
  `pip-audit -r requirements.txt` goes from 7 vulnerabilities to 0.
- **Rate limiting behind a proxy (F12, High).** Opt-in `TRUST_PROXY=1` installs
  ProxyFix with exactly one trusted hop, so users stop sharing a single bucket.
  Off by default; forwarded headers are ignored unless enabled.
- **Credential leakage into logs (F3/F9).** The API-fetch failure log is now a
  fixed string. `requests`' exception text carries the full URL, and the query
  string, fragment, userinfo *and* path can each hold a token.
- **Outbound header allowlist (F4).** The client supplies the header *name* for
  API-key auth; names are stripped and lowercased before an explicit allowlist
  check, so `Host`, `Proxy-Authorization` and `CoNnEcTiOn` no longer pass.
- **Security headers (F5).** Added HSTS (secure requests only),
  `Permissions-Policy`, `Cross-Origin-Opener-Policy` and
  `Cross-Origin-Resource-Policy`; CSP gained `object-src 'none'`,
  `base-uri 'self'`, `frame-ancestors 'none'`, `form-action 'self'` and
  `upgrade-insecure-requests`.
- **SSRF: bounded DNS and a port allowlist (F6).** Lookups run on a shared,
  fixed-size pool with admission control, so a slow nameserver can no longer
  pin a worker. `API_ALLOWED_PORTS` defaults to `80,443,8443`.
- **SECRET_KEY fail-fast (F7).** `APP_ENV=production` with the publicly known
  dev key (or an empty one) refuses to start. Integer settings now report which
  variable was mistyped.
- **Recursion-depth DoS (F8).** `extract_table_data` gained the depth cap
  `flatten_for_csv` already had, and `RecursionError` anywhere in the pipeline
  returns 400 `JSON nesting too deep` instead of 500.
- **JSON error handlers (F10).** 413, 500 and 404 return JSON, so the client's
  `response.json()` no longer throws on an HTML body.
- **`Cache-Control: no-store` (F11)** on all data-bearing and health responses.
- **Upload validation (F13).** Non-`.json`/`.jsonl` filenames and clearly wrong
  content types are rejected server-side.
- **Cookie hardening (F16).** `HttpOnly`, `SameSite=Lax`, and `Secure` tied to
  `APP_ENV=production`.

### Performance

- **gzip compression (P1).** ~40 lines of middleware, no new dependency. Skips
  streamed, bodyless, already-encoded and non-text responses.
- **Diskless, memory-bounded exports (P3).** CSV/TSV are generator-streamed and
  uncapped. XLSX keeps a normal-mode workbook (no OS temp files) plus
  `MAX_EXPORT_CELLS`, measured rather than guessed — see
  `docs/export-budget-v1.2.md`.
- **Lazy tree picker (P4)** and **client render caps (P5)**: children build on
  first toggle; nested objects stop at 20 keys, primitive arrays at 20 items,
  strings at 500 characters.
- **Non-mutating preview truncation (P2.2/P5).** The preview is a capped copy;
  `csv_data` and every export keep full fidelity.
- **Static asset caching (P6)** for a day, behind `?v=APP_VERSION` URLs.
- **Memory trims (P8/P12).** One-pass flatten-and-collect-columns, and the
  API path decodes its `bytearray` without an intermediate copy.
- **gunicorn `--timeout 60` (P9)** everywhere, above `API_FETCH_TIMEOUT`.
- **Chunked Blob for client exports (P13).**

### Added

- `/health/live` and `/health/ready` alongside the unchanged `/health`.
- **Load more / Load all** over the full dataset, with a 50,000-row DOM guard.
- **Row filter**: case-insensitive substring across all values.
- **JSONL and Markdown exports.** Neither is formula-sanitized: JSON has types
  and nothing evaluates it, and a leading `=` is inert in Markdown — Markdown
  gets pipe/newline escaping instead. Both write the same flattened columns the
  table shows (nested objects as dotted keys, nested arrays as JSON strings),
  because the unflattened rows are never sent to the browser; see
  "Known limitations".
- **Column visibility toggle** and **deep-linkable path selection**
  (`#path=users.0.orders`).
- `/process` returns `preview_limit`, `total_cells` and `max_export_cells`, so
  the badge reflects config and the Excel entry is greyed out before the click.
- CI (`.github/workflows/ci.yml`), `pyproject.toml` (ruff + pytest),
  `requirements-dev.txt`, `requirements-redis.txt`, `.env.example`, `Makefile`,
  and Node assertion suites for `static/js/app.js`.
- The rate-limit topology guard: `RATELIMIT_STORAGE_URI` is configurable at last,
  and a production deployment must declare `WEB_CONCURRENCY` and `APP_REPLICAS`.

### Changed

- `alert()` About dialog replaced with an in-page modal that reads the version
  from config; export dropdown is keyboard-accessible.
- Render auto-deploy now waits for CI (`autoDeployTrigger: checksPass`).
- License references corrected from MIT to GPL-3.0 (F17).

### Removed

- `find_candidate_arrays` and its four tests — dead code from the old candidates
  handshake the JSON tree picker replaced (P10/D2).

### Known limitations

- **JSONL export is not a faithful copy of the input document.** Roadmap 4.3
  called it "lossless — original values". It writes values verbatim (no formula
  prefixing, which was the security-relevant half of that decision), but over
  the server's *flattened* projection: `{"tags": [1, 2]}` exports as
  `"tags": "[1, 2]"`, and `{"meta": {"role": "x"}}` as `"meta.role": "x"`.
  Only `csv_data` (flattened) reaches the browser for the full dataset —
  `preview` is truncated and capped at `preview_limit` rows — so a
  round-tripping export would mean shipping the original rows alongside the
  flattened ones, doubling the payload and client memory that P2 and P12 exist
  to reduce. Flagged for a maintainer decision rather than resolved either way.

### Not included

- **Opt-in HTTP Basic Auth gate** (roadmap 4.6). Decision D4 is still open and
  needs maintainer sign-off. Nothing else in this release depends on it.

## [1.1.0] - 2026-05

- JSON tree picker replaces the multi-array `candidates` handshake.
- JSONL support across file, paste and API input.
- Client-side column sorting, light/dark theme, CSV/TSV/Excel export.
- CSRF protection, SSRF validation with DNS resolution, rate limiting, and a
  strict CSP with no inline scripts.
