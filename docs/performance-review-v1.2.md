# Performance Review — JSON Table Converter (v1.2 planning)

**Date:** 2026-08-20
**Scope:** `routes.py`, `helpers.py`, `security.py`, `static/js/app.js`, `config.py`, `render.yaml`
**Method:** Static analysis of the hot paths (parse → flatten → serialize → render → export). No benchmarks could be run in this sandbox (no pip); sizing figures are conservative estimates based on the code paths. Design constraints respected: **no server-side persistence of payloads** (the full-dataset-in-response design is deliberate — see §5) and **no frontend framework/build step**.

---

## 1. Executive Summary

The app's heavy operations are all in `/process` (parse + flatten + full-dataset response) and the export routes. With the default 10 MB input cap, a single request can hold **input JSON + flattened rows + response JSON in memory at once**, and the client downloads the *entire* dataset even though it only displays 25 preview rows. The single highest-leverage fix is **gzip compression of `/process` responses** (typical JSON compresses 5–10×). Second is **streaming/memory-bounded exports** (openpyxl `write_only` + generator responses). Frontend, the **eager JSON tree picker** and **unbounded nested-cell rendering** are the freeze risks.

| Severity | Count | Items |
|---|---|---|
| High | 2 | P1 Uncompressed multi-MB JSON responses, P3 XLSX export memory (openpyxl non-streaming + full buffering) |
| Medium | 6 | P2 Full dataset shipped per request, P4 Eager tree-picker DOM build, P5 Unbounded nested-cell render/stringify, P7 Blocking DNS lookup in worker, P9 Gunicorn timeout vs `API_FETCH_TIMEOUT` misalignment, P12 Multi-copy memory in `process_json` |
| Low | 4 | P6 No static-asset cache headers, P8 Double column scan + wasteful flatten intermediates, P10 Dead code `find_candidate_arrays`, P11 Hardcoded "25" preview badge |

**Quick wins:** P1 (gzip), P6 (cache headers), P8 (one-pass columns), P10 (dead code), P11 (preview_limit in payload).

---

## 2. Findings

### P1 — Large `/process` JSON responses are uncompressed — **High**

**Location:** `routes.py:188-195` (response), no gzip middleware anywhere.

**Description:** `/process` returns `preview` + `csv_data` (the **full** flattened dataset) + `csv_columns`. For a 10 MB JSON input the response body is commonly 5–20 MB of repetitive JSON. No compression layer exists (Flask serves it raw; gunicorn's default setup doesn't gzip; Nginx config in README has no `gzip`). Text/JSON compresses 5–10× — this is the largest single transfer-time and bandwidth win available, and it also cuts client memory and parse time.

**Remediation:** Add a small gzip middleware (Flask `after_request` that gzips bodies > ~1 KB when `Accept-Encoding` includes gzip, setting `Content-Encoding`/`Vary`; skip for already-small and for the streamed export responses). Avoid adding a dependency unless preferred — a ~20-line middleware in `app.py`/`security.py` fits the project's minimal-deps stance. If a dependency is acceptable, `Flask-Compress` is the standard choice (pin exactly).

**Effort:** 1h. **Verification:** `curl -H 'Accept-Encoding: gzip' -s -o /dev/null -w '%{size_download} %{time_total}'` on a large `/process` call before/after; compare sizes.

---

### P2 — Full dataset shipped to the client on every `/process` — **Medium** (design-constrained)

**Location:** `routes.py:185-194`.

**Description:** The server flattens **all** rows (`csv_data = [flatten_for_csv(row, ...) for row in table_data]`) and serializes them all to the client, although only `PREVIEW_ROW_LIMIT` (25) rows are rendered. Cost: server CPU for full flattening, ~3× peak memory (input + rows + response), full payload transfer, client memory, client parse time. The design is deliberate — CSV/TSV export is client-side from `csv_data`, and the no-persistence rule forbids holding the dataset server-side between requests (`MEMORY.md` 2026-05-12). **Do not** fix by caching payloads server-side.

**Remediation options (in order of fit):**
1. **Compress the response (P1)** — addresses transfer and parse cost without changing the architecture.
2. **Stream-aware preview truncation** — server-side cap nested values/long strings inside `preview` rows only (keep full fidelity in `csv_data`). Cheap, prevents the worst client-render cases (see P5).
3. **Client-side lazy rendering** — the data is already in the browser; implement "load more" pagination over `csv_data` so the DOM only ever holds a window of rows (also a feature; roadmap Phase 4).

**Effort:** P1: 1h; option 2: 30m; option 3: 2-3h (feature).

---

### P3 — XLSX export is fully buffered in memory — **High**

**Location:** `routes.py:245-289`.

**Description:** `Workbook()` (normal mode) holds all rows in memory, and `wb.save(output)` + `output.getvalue()` create a second full copy (plus the JSON request body already holds `csv_data`). With a ~10 MB `csv_data` payload the request can transiently consume several hundred MB — enough to OOM a free-tier dyno and a 413-adjacent DoS amplifier (60/min limit only partially mitigates). CSV export (`routes.py:217-238`) has the same pattern with `io.StringIO` (smaller but still full-buffer).

**Remediation:**
- `Workbook(write_only=True)` for XLSX — streams rows to a temp/SpooledTemporaryFile instead of keeping the tree in memory.
- Stream the response: build the file in a temp file (`tempfile.SpooledTemporaryFile`) and `send_file`/`Response(iter)` with proper headers; do **not** `output.getvalue()` into memory.
- For CSV: use a generator-based `Response` that yields rows (`csv` writer needs a text wrapper — yield `''.join`-chunked or use `io.StringIO` flush per N rows). Keep `extrasaction='ignore'` and the F1 sanitization.
- Add an export row-count guard (`MAX_EXPORT_ROWS`, default e.g. 100k) → 400 with a clear message instead of OOM.

**Effort:** 2h. **Verification:** export 100k rows; measure RSS before/after; assert response streams (Content-Length absent or chunked).

---

### P4 — JSON tree picker builds the entire tree eagerly — **Medium**

**Location:** `static/js/app.js:161-247` (`showTreePicker`/`buildTreeNode`).

**Description:** `showTreePicker(raw_json)` recursively builds DOM nodes for **every** key of every object (only array *lengths* are capped at 50 children). A 10 MB payload with a wide/deep structure → tens of thousands of DOM nodes synchronously → multi-second freeze and large memory spike. Objects are fully expanded into the tree regardless of whether the user opens them.

**Remediation:** Lazy build: render the root and, on first toggle of a node, build that node's children (`data-loaded` flag / `MutationObserver`-free approach). Cap per-level children (e.g. 200) with "…and N more" placeholders (already done for arrays at 50 — extend the pattern to objects and to total tree nodes).

**Effort:** 2h. **Verification:** open a 50 MB-ish structure (bounded by 10 MB upload) in the picker; DevTools Performance shows no long task; toggling builds incrementally.

---

### P5 — Unbounded nested-cell rendering / stringification — **Medium**

**Location:** `static/js/app.js:364-387` (`formatValue`), `390-405` (`renderNestedObject`), `408-438` (`renderNestedTable`), plus server `routes.py:182` (`preview_data`).

**Description:**
- `renderNestedObject` renders **all** keys of a nested object — an object with 50k keys → 50k `<tr>` in one cell → freeze.
- `formatValue` for arrays of primitives does `JSON.stringify(value)` over the **whole** array (a 100k-item array → huge string in one `td`).
- A single very long string cell (e.g. 5 MB base64) renders in full.
- Server side, `preview` rows carry full-fidelity nested structures, so all of the above are fed directly by the API.

**Remediation (server + client):**
- Server: truncate in `preview` only — long strings to ~256 chars, nested arrays to ~20 items, nested objects to ~20 keys, with `"… (truncated)"` markers; full data stays in `csv_data`/export.
- Client: cap `renderNestedObject` keys (e.g. 20 + "and N more"); cap `JSON.stringify` length for primitive arrays (render first N + count); add `max-width`/ellipsis already present via CSS but ensure no full-string `innerHTML` blow-ups.

**Effort:** 1-2h. **Verification:** cell containing a 10k-key object renders < 1 s and < N MB heap.

---

### P6 — No cache headers on static assets — **Low**

**Location:** `app.py` (no `SEND_FILE_MAX_AGE_DEFAULT`), `templates/index.html:11,237`.

**Description:** `style.css` and `app.js` are served via Flask's static handler with `Last-Modified`/304 support but **no `Cache-Control`**, so browsers revalidate every navigation. On the Render free tier (cold starts) this adds a round-trip per page load and extra requests during the cold window.

**Remediation:** In `config.py`: `SEND_FILE_MAX_AGE_DEFAULT = int(os.environ.get('STATIC_MAX_AGE', 86400))`; optionally add cache-busting query (`?v={{ config.APP_VERSION }}`) on the two asset URLs in `index.html`. Don't set a huge max-age without versioning, or updates will be stale.

**Effort:** 20m.

---

### P7 — Blocking DNS lookup inside the request path — **Medium**

**Location:** `security.py:24` (`socket.getaddrinfo`), called synchronously in `routes.py:82`.

**Description:** DNS resolution runs on the gunicorn worker thread with **no timeout** (see Security Review F6). A slow/malicious nameserver ties up the worker for seconds-to-minutes; with few workers (free tier defaults to 1-2), one request can stall the whole app. Also adds per-request latency to every API fetch (usually 5-50ms, but unbounded worst case).

**Remediation:** Run `getaddrinfo` under `ThreadPoolExecutor(max_workers=4).submit(...).result(timeout=API_DNS_TIMEOUT)` (default ~3s) → on timeout return the existing invalid-URL error. Optionally memoize validated hostnames with a short TTL (e.g. 60s, LRU cache) — but beware TTL-vs-rebinding tradeoffs; keep TTL short.

**Effort:** 1h. **Verification:** mock `getaddrinfo` sleeping 10s → `/process` returns in ~3s; no worker stall.

---

### P8 — Double column scan + costly flatten intermediates — **Low**

**Location:** `routes.py:180-186`, `helpers.py:17-31`.

**Description:**
- `get_all_columns(table_data)` and `get_all_columns(csv_data)` each do a full pass; flattening does a third.
- `flatten_for_csv` builds a `list` of tuples and then a `dict` for every row (`items = []` … `dict(items)`) — extra allocation per row, per level.
- `json.dumps` is called for every list-valued cell even when the row will only appear in the preview.

**Remediation:** One pass that both flattens and accumulates column names (`yield` flattened dict + update a shared column set); build the result dict directly instead of list-of-tuples. Micro-optimizations — measurable only on very large inputs, bundle with P2 work.

**Effort:** 1h. **Verification:** same outputs; `get_all_columns` result identical.

---

### P9 — Gunicorn worker timeout vs `API_FETCH_TIMEOUT` — **Medium** (reliability/performance)

**Location:** `render.yaml:9`, README gunicorn invocations, `config.py:16`.

**Description:** `API_FETCH_TIMEOUT` defaults to 30s and gunicorn's default `--timeout` is also 30s. An API fetch that takes ~30s races the worker kill: gunicorn SIGKILLs the worker mid-response → client sees 502, worker respawn cost, request fails with a confusing error. None of the documented gunicorn invocations set `--timeout` or `--workers`.

**Remediation:** Set `--timeout 60` (≥ API_FETCH_TIMEOUT × 2) in `render.yaml` and README/Docker/systemd examples; make the relationship explicit in config docs. Optionally lower `API_FETCH_TIMEOUT` to 15s for snappier failures. Add `--workers 2` note for the free tier (memory permitting) or keep 1 and document it.

**Effort:** 15m. **Verification:** a 35s mock API fetch no longer returns 502.

---

### P10 — Dead code: `find_candidate_arrays` — **Low**

**Location:** `helpers.py:82-111`; imported nowhere in `routes.py` (routes return `raw_json` for the tree picker instead).

**Description:** The function and its 4 tests (`tests/test_helpers.py:110-134`) exist solely for the **old** candidates handshake replaced by the JSON tree picker (commit `e537042`). It is recursive without a depth guard (security finding F8) and confuses contributors reading the code (and the docs — see F17).

**Remediation:** Delete the function and its tests, or repurpose it to pre-populate the tree picker's "recommended paths" (a small feature). If deleted, update the stale `MEMORY.md`/`CLAUDE.md`/`AGENTS.md` descriptions.

**Effort:** 15m.

---

### P11 — Hardcoded preview badge ("25") vs server config — **Low** (correctness/UX)

**Location:** `static/js/app.js:321-326`, `routes.py:181` (`PREVIEW_ROW_LIMIT`).

**Description:** `if (totalRows > 25) … 'Showing first 25'` hardcodes 25; an operator changing `PREVIEW_ROW_LIMIT` gets a wrong badge (and the earlier code-health review flagged the same). Sort also operates only on the 25 preview rows while exports contain all rows — order discrepancy users can't see.

**Remediation:** Return `preview_limit` in the `/process` payload and use it in the badge. Document "sort applies to the visible preview only" or upgrade to full-dataset client sort when rows are loaded (Phase 4 feature).

**Effort:** 20m + 2h (feature).

---

### P12 — Multi-copy memory inside `process_json` — **Medium**

**Location:** `routes.py:130-143` (API path), `routes.py:180-195`.

**Description:** Peak memory during `/process` (API path): streamed `bytearray` → `bytes(content)` copy → decoded `str` → parsed JSON objects → flattened rows → `jsonify` string — roughly 4-6× the payload size, plus JSON encoder overhead. Upload/paste paths skip the first two copies. For 10 MB inputs this is ~40-60 MB transient; with default free-tier memory (~512 MB) and a few concurrent requests this is the realistic OOM risk.

**Remediation:** Drop the intermediate `bytes(content)` copy (decode the `bytearray` directly via `content.decode('utf-8')`); consider `json.loads(text, parse_float=...)` untouched, but **do** add a peak-memory guard: cap effective input by measuring the parsed object depth/size (or simply document the 10 MB→~60 MB multiplier). P1 compression also shrinks the response copy.

**Effort:** 30m + testing.

---

### P13 — Client-side CSV/TSV string building — **Info**

**Location:** `static/js/app.js:482-513`.

**Description:** `downloadDelimited` concatenates the entire file into one string, then a Blob. For ~10 MB datasets this is a ~10-30 MB string + Blob copy → brief main-thread block and double memory. Acceptable at current scale.

**Remediation:** Optional: write to the Blob in chunks (`Blob([part1, part2, …])`) — trivial change, avoids one giant string. Include F1 sanitization in the same pass.

---

## 3. Finding-to-Remediation Matrix

| ID | Finding | Severity | Remediation | Effort |
|---|---|---|---|---|
| P1 | No response compression | High | gzip middleware for bodies >1 KB | 1h |
| P3 | XLSX/CSV fully buffered | High | `write_only` + spooled temp + generator; row guard | 2h |
| P2 | Full dataset shipped per request | Medium | P1 + preview truncation + lazy render (design-constrained) | 1h + feature |
| P4 | Eager tree-picker DOM | Medium | Lazy children build + caps | 2h |
| P5 | Unbounded nested-cell render | Medium | Server preview truncation + client caps | 1-2h |
| P7 | Blocking DNS in worker | Medium | Bounded resolver (shared with F6) | 1h |
| P9 | gunicorn timeout < API timeout | Medium | `--timeout 60` everywhere | 15m |
| P12 | Multi-copy memory in `/process` | Medium | Drop `bytes()` copy; document multiplier | 30m |
| P6 | No static cache headers | Low | `SEND_FILE_MAX_AGE_DEFAULT` + versioned URLs | 20m |
| P8 | Double column scan / tuple dicts | Low | Single-pass flatten+columns | 1h |
| P10 | Dead code `find_candidate_arrays` | Low | Delete + doc sync | 15m |
| P11 | Hardcoded "25" badge | Low | `preview_limit` in payload | 20m |
| P13 | Client CSV giant string | Info | Chunked Blob | 15m |

---

## 4. Recommended Perf Budget (acceptance targets for v1.2)

Measured on a reference payload (10 MB, ~200k rows of mixed nesting), single free-tier worker:

| Metric | Current (est.) | Target |
|---|---|---|
| `/process` transfer size | ~10-20 MB | ≤ 2-4 MB (gzip) |
| `/process` p95 latency | seconds (unbounded) | ≤ 3s |
| Peak RSS, `/process` | ~40-60 MB | ≤ ~30 MB |
| Peak RSS, `/export-xlsx` 100k rows | hundreds of MB (OOM risk) | ≤ 150 MB, streams |
| Tree-picker open, 10 MB payload | multi-second freeze | ≤ 500 ms initial; lazy children |
| Cell with 10k-key object | freeze | renders ≤ 20 keys + "more" |
| Static assets | revalidated every load | cached ≥ 1 day |

---

## 5. Design Constraints That Bound the Fixes

- **No server-side payload persistence** (`MEMORY.md` 2026-05-12): the full-dataset-in-`/process`-response design must not be replaced with server-side caching/sessions for export. All fixes must respect this (compression, streaming, client-side lazy rendering are compatible; a server-side export token is not).
- **No frontend framework / build step**: all client fixes are vanilla JS.
- **Strict CSP, no inline JS**: any new client code stays in `static/js/app.js`.
- **Exact-pinned dependencies**: any new dependency (e.g. `Flask-Compress`) must be pinned exactly and added deliberately; the zero-dependency middleware is preferred.
- **Per-worker in-memory rate limiter**: benchmark results should assume no shared counters across workers.
