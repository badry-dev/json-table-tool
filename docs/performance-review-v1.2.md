# Performance Review — JSON Table Converter (v1.2 planning)

**Date:** 2026-08-20
**Scope:** `routes.py`, `helpers.py`, `security.py`, `static/js/app.js`, `config.py`, `render.yaml`
**Method:** Static analysis of the hot paths (parse → flatten → serialize → render → export). No benchmarks could be run in this sandbox (no pip); sizing figures are conservative estimates based on the code paths. Design constraints respected: **no server-side persistence of payloads** (the full-dataset-in-response design is deliberate — see §5) and **no frontend framework/build step**.

---

## 1. Executive Summary

The app's heavy operations are all in `/process` (parse + flatten + full-dataset response) and the export routes. With the default 10 MB input cap, a single request can hold **input JSON + flattened rows + response JSON in memory at once**, and the client downloads the *entire* dataset even though it only displays 25 preview rows. The single highest-leverage fix is **gzip compression of `/process` responses** (typical JSON compresses 5–10×). Second is **diskless, memory-bounded exports** (capped workbook + generator responses — no OS temp files). Frontend, the **eager JSON tree picker** and **unbounded nested-cell rendering** are the freeze risks.

| Severity | Count | Items |
|---|---|---|
| High | 2 | P1 Uncompressed multi-MB JSON responses, P3 XLSX export memory (openpyxl non-streaming + full buffering) |
| Medium | 6 | P2 Full dataset shipped per request, P4 Eager tree-picker DOM build, P5 Unbounded nested-cell render/stringify, P7 Blocking DNS lookup in worker, P9 Gunicorn timeout vs `API_FETCH_TIMEOUT` misalignment, P12 Multi-copy memory in `process_json` |
| Low | 4 | P6 No static-asset cache headers, P8 Double column scan + wasteful flatten intermediates, P10 Dead code `find_candidate_arrays`, P11 Hardcoded "25" preview badge |
| Info | 1 | P13 Client-side CSV/TSV string building |

**Quick wins:** P1 (gzip), P6 (cache headers), P8 (one-pass columns), P10 (dead code), P11 (preview_limit in payload).

---

## 2. Findings

### P1 — Large `/process` JSON responses are uncompressed — **High**

**Location:** `routes.py:188-195` (response), no gzip middleware anywhere.

**Description:** `/process` returns `preview` + `csv_data` (the **full** flattened dataset) + `csv_columns`. For a 10 MB JSON input the response body is commonly 5–20 MB of repetitive JSON. No compression layer exists (Flask serves it raw; gunicorn's default setup doesn't gzip; Nginx config in README has no `gzip`). Text/JSON compresses 5–10×, so gzip is the largest single transfer-time and bandwidth win available. It does **not** reduce the client's uncompressed `csv_data` representation or its JSON parse cost — the browser still receives, decompresses, parses, and stores the full dataset; those are P2 (payload size) and P5 (rendering) concerns.

**Remediation:** Add a small gzip middleware (Flask `after_request`) that compresses only when the response is eligible: `Accept-Encoding` includes gzip, the body is text/JSON over ~1 KB, and the response is compressible — skip bodyless responses, `HEAD`/`204`/`304`, bodies already carrying a `Content-Encoding`, and streamed responses (`response.is_streamed`, which covers the streaming export routes). Set `Content-Encoding: gzip` and `Vary: Accept-Encoding`, and remove or recompute `Content-Length` so it matches the compressed payload. Avoid adding a dependency unless preferred — a ~20-line middleware in `app.py`/`security.py` fits the project's minimal-deps stance. If a dependency is acceptable, `Flask-Compress` is the standard choice (pin exactly).

**Effort:** 1h. **Verification:** `curl -H 'Accept-Encoding: gzip' -s -o /dev/null -w '%{size_download} %{time_total}'` on a large `/process` call before/after; compare sizes.

---

### P2 — Full dataset shipped to the client on every `/process` — **Medium** (design-constrained)

**Location:** `routes.py:185-194`.

**Description:** The server flattens **all** rows (`csv_data = [flatten_for_csv(row, ...) for row in table_data]`) and serializes them all to the client, although only `PREVIEW_ROW_LIMIT` (25) rows are rendered. Cost: server CPU for full flattening, ~3× peak memory (input + rows + response), full payload transfer, client memory, client parse time. The design is deliberate — CSV/TSV export is client-side from `csv_data`, and the no-persistence rule forbids holding the dataset server-side between requests (`MEMORY.md` 2026-05-12). **Do not** fix by caching payloads server-side.

**Remediation options (in order of fit):**
1. **Compress the response (P1)** — reduces transfer size/time without changing the architecture (client parse and memory cost are unchanged; see P2/P5).
2. **Stream-aware preview truncation** — server-side cap nested values/long strings inside `preview` rows only (keep full fidelity in `csv_data`). Cheap, prevents the worst client-render cases (see P5).
3. **Client-side lazy rendering** — the data is already in the browser; implement "load more" pagination over `csv_data` so the DOM only ever holds a window of rows (also a feature; roadmap Phase 4).

**Effort:** P1: 1h; option 2: 30m; option 3: 2-3h (feature).

---

### P3 — XLSX export is fully buffered in memory — **High**

**Location:** `routes.py:245-289`.

**Description:** `Workbook()` (normal mode) holds all rows in memory, and `wb.save(output)` + `output.getvalue()` create a second full copy (plus the JSON request body already holds `csv_data`). With a ~10 MB `csv_data` payload the request can transiently consume several hundred MB — enough to OOM a free-tier dyno and a 413-adjacent DoS amplifier (60/min limit only partially mitigates). CSV export (`routes.py:217-238`) has the same pattern with `io.StringIO` (smaller but still full-buffer).

**Remediation:**
- **Diskless by default.** openpyxl's `write_only=True` mode and `tempfile.SpooledTemporaryFile` both rely on OS temporary files (transient payload-derived data on disk), which conflicts with the absolute "no disk writes of payloads" rule. The diskless path is a normal-mode `Workbook` plus a `MAX_EXPORT_ROWS` cap, which bounds peak memory without touching disk. The memory-light temp-file route is only acceptable under an explicit documented exception (roadmap D6). Note that even `write_only=True` does not eliminate the final `save()` zip assembly.
- **`MAX_EXPORT_ROWS` is XLSX-only and must not contradict the `/process` contract.** `/process` admits anything under `MAX_UPLOAD_SIZE` (10 MB), which can easily exceed 100k rows; a fixed 100k export cap would let `/process` return full `csv_data` for a dataset that `/export-xlsx` then rejects. Therefore:
  - Default `MAX_EXPORT_ROWS = 0` (**disabled**). This is a **compatibility setting, not a memory bound**: it exists so the export contract cannot be narrower than the `/process` contract by default. It does *not* make XLSX export memory-safe, and the 10 MB input cap does not bound XLSX memory either — a 10 MB JSON body expands into Python objects, then into openpyxl cell objects, then into the zip assembly, and the multiplier is data-dependent. Memory safety comes from the separate limits and from the measurement below, never from this default.
  - The cap is **scoped to XLSX only**. CSV/TSV are generator-streamed and stay uncapped, so they are always the fallback for any dataset.
  - **Response contract (additive, one field).** `/process` already returns `total_rows` (`routes.py:192`) — reuse it, do not add a second row-count field. The only new key is `max_export_rows`, echoing the effective limit, with **`0` meaning unlimited**. Client rule: disable the Excel entry iff `max_export_rows > 0 && total_rows > max_export_rows`, labelling it "use CSV/TSV for `total_rows` rows" *before* the user clicks. `/export-xlsx` independently returns `400 {"error": "Dataset has N rows, above the Excel export limit of M; export CSV or TSV instead."}` (defence in depth for direct API callers). No silent truncation — a partial spreadsheet is worse than a refusal.
- Deliver via `send_file`/`Response(iter)`; do **not** `output.getvalue()` the whole buffer into memory.
- For CSV: use a generator-based `Response` that yields rows (`csv` writer needs a text wrapper — yield `''.join`-chunked or use `io.StringIO` flush per N rows). CSV is natively streamable with no temp files. Keep `extrasaction='ignore'` and the F1 sanitization.

**Effort:** 2h. **Verification:** export 100k rows and measure RSS **during generation and during response delivery** — do not infer bounded memory from a missing `Content-Length` or chunked transfer, since those only indicate streaming, not peak usage.

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
- Server: truncate in `preview` only, **without mutating shared objects** — build a separate preview projection (copy) so `table_data`/`csv_data` keep full fidelity; add a test asserting exports still contain untruncated values. Long strings → ~256 chars, nested arrays → ~20 items, nested objects → ~20 keys, with `"… (truncated)"` markers.
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

**Remediation:** Use a **shared, module-level** `ThreadPoolExecutor` with a fixed `max_workers` and an in-flight semaphore; wait via `future.result(timeout=API_DNS_TIMEOUT)` (default ~3s) and return the existing invalid-URL error on timeout. Do **not** create a per-request executor — `result(timeout=...)` bounds only the caller's wait and cannot cancel a running `getaddrinfo` (per-request executors leak blocked threads; a shared unbounded pool can saturate). A *hard* execution bound needs process isolation or a cancellable resolver; document the timeout as a wait bound. Do **not** rely on memoizing validated hostnames as a rebinding control — a cached approval can differ from the address the client actually connects to; hostname caching (if ever added) is a latency optimization only, never a security control.

**Effort:** 1h. **Verification:** mock `getaddrinfo` sleeping 10s → `/process` returns in ~3s; no worker stall.

---

### P8 — Double column scan + costly flatten intermediates — **Low**

**Location:** `routes.py:180-186`, `helpers.py:17-31`.

**Description:**
- `get_all_columns(table_data)` and `get_all_columns(csv_data)` each do a full pass; flattening does a third.
- `flatten_for_csv` builds a `list` of tuples and then a `dict` for every row (`items = []` … `dict(items)`) — extra allocation per row, per level.
- `json.dumps` is called for every list-valued cell even when the row will only appear in the preview.

**Remediation:** One pass that both flattens and accumulates column names: collect names into a set during flattening and **sort once at the end** — this preserves the current `get_all_columns` sorted-output contract (do not rely on set iteration order, which is insertion-order-dependent); build the result dict directly instead of list-of-tuples. Micro-optimizations — measurable only on very large inputs, bundle with P2 work, and verify that `csv_columns`/rendered column order is byte-identical to today.

**Effort:** 1h. **Verification:** same outputs; `get_all_columns` result identical.

---

### P9 — Gunicorn worker timeout vs `API_FETCH_TIMEOUT` — **Medium** (reliability/performance)

**Location:** `render.yaml:9`, README gunicorn invocations, `config.py:16`.

**Description:** `API_FETCH_TIMEOUT` defaults to 30s and gunicorn's default `--timeout` is also 30s. An API fetch that takes ~30s races the worker kill: gunicorn SIGKILLs the worker mid-response → client sees 502, worker respawn cost, request fails with a confusing error. None of the documented gunicorn invocations set `--timeout` or `--workers`.

**Remediation:** Set `--timeout 60` (≥ API_FETCH_TIMEOUT × 2) in `render.yaml` and README/Docker/systemd examples; make the relationship explicit in config docs. Optionally lower `API_FETCH_TIMEOUT` to 15s for snappier failures. Keep **one worker and one instance** as the documented default: topology is coupled to rate-limit correctness (`memory://` counters are process-local, so the limit is multiplied by `workers × replicas`), so `--workers 2`, the README's `--workers 4` examples, and any `numInstances > 1` require a shared `RATELIMIT_STORAGE_URI` first (roadmap 2.10).

**Effort:** 15m. **Verification:** a 35s mock API fetch no longer returns 502.

---

### P10 — Dead code: `find_candidate_arrays` — **Low**

**Location:** `helpers.py:82-111`; imported nowhere in `routes.py` (routes return `raw_json` for the tree picker instead).

**Description:** The function and its 4 tests (`tests/test_helpers.py:110-134`) exist solely for the **old** candidates handshake replaced by the JSON tree picker (commit `e537042`). It is recursive without a depth guard (security finding F8) and confuses contributors reading the code (and the docs — see F17).

**Remediation:** Delete the function and its 4 tests (decided in roadmap D2, executed in Phase 0.8) and update the stale `MEMORY.md`/`CLAUDE.md`/`AGENTS.md` descriptions. Repurposing it to pre-populate the tree picker is explicitly not chosen.

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

**Remediation:** Drop the intermediate `bytes(content)` copy (decode the `bytearray` directly via `content.decode('utf-8')`) — this removes one copy only. Parsing, flattening, and `jsonify` still materialize the full dataset, and gzip applied after `jsonify` does **not** reduce that peak. Do not treat post-parse size measurement as a peak-memory guard; either add a pre-parse/streaming input limit (an effective cap on what can be submitted) or document the full-pipeline multiplier and set the §4 budget accordingly.

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
| P1 | No response compression | High | gzip middleware (guards + Content-Length fix) | 1h |
| P3 | XLSX/CSV fully buffered | High | Diskless capped export (or D6 temp-file exception); generator | 2h |
| P2 | Full dataset shipped per request | Medium | P1 + preview truncation + lazy render (design-constrained) | 1h + feature |
| P4 | Eager tree-picker DOM | Medium | Lazy children build + caps | 2h |
| P5 | Unbounded nested-cell render | Medium | Non-mutating preview projection + client caps | 1-2h |
| P7 | Blocking DNS in worker | Medium | Shared bounded resolver + in-flight limit (shared with F6) | 1h |
| P9 | gunicorn timeout < API timeout | Medium | `--timeout 60` everywhere | 15m |
| P12 | Multi-copy memory in `/process` | Medium | Drop `bytes()` copy; document full-pipeline peak | 30m |
| P6 | No static cache headers | Low | `SEND_FILE_MAX_AGE_DEFAULT` + versioned URLs | 20m |
| P8 | Double column scan / tuple dicts | Low | Single-pass flatten + sorted columns (order-preserving) | 1h |
| P10 | Dead code `find_candidate_arrays` | Low | Delete + doc sync | 15m |
| P11 | Hardcoded "25" badge | Low | `preview_limit` in payload | 20m |
| P13 | Client CSV giant string | Info | Chunked Blob | 15m |

---

## 4. Recommended Perf Budget (acceptance targets for v1.2)

Measured on a reference payload (10 MB, ~200k rows of mixed nesting), single free-tier worker:

| Metric | Current (est.) | Target |
|---|---|---|
| `/process` transfer size | ~10-20 MB | ≤ 2-4 MB (gzip) |
| `/process` p95 latency (paste/upload only) | seconds (unbounded) | ≤ 3s |
| Peak RSS **delta**, `/process` (10 MB input) | ~40-60 MiB | **≤ 50 MiB** delta (pass/fail), absolute high-water < 256 MiB |
| Peak RSS **delta**, `/export-xlsx` 100k rows | hundreds of MiB (OOM risk) | **≤ 150 MiB** delta (pass/fail), absolute high-water < 256 MiB, streams |
| Tree-picker open, 10 MB payload | multi-second freeze | ≤ 500 ms initial; lazy children |
| Cell with 10k-key object | freeze | renders ≤ 20 keys + "more" |
| Static assets | revalidated every load | cached ≥ 1 day |

The latency target explicitly **excludes API-fetch requests** — those are bounded separately by `API_FETCH_TIMEOUT` (default 30s) plus DNS time (P7/F6) and would otherwise make a single aggregate p95 meaningless. The peak-RSS target reflects the full parse → flatten → `jsonify` pipeline (P12); it is not a claim that gzip or dropping one copy makes the process fit under 30 MB.

**RSS measurement method (identical for `/process` and for the export measurement — both rows are pass/fail against these exact rules). Note `ru_maxrss` is a per-process high-water mark that cannot be reset, which drives the fresh-worker protocol below:**

| Parameter | Definition |
|---|---|
| Units | **`ru_maxrss` is not portable.** On Linux it is **KiB**; on macOS/Darwin the same field is **bytes**. Read it, multiply by 1024 on Linux, and report everything in **MiB** (1 MiB = 1048576 bytes). Every memory threshold in this budget is written in **MiB**, not decimal MB. A harness that skips the platform conversion silently reports numbers 1024× off. |
| Environment parity | Both runs of a pair must execute on the **same OS and kernel, the same container image, the same Python build, and the same cgroup/container resource limits**, on an otherwise idle host. A baseline from one image and a measurement from another is not a delta. Record all of these alongside the result. |
| Peak, and why not sampling | `resource.getrusage(RUSAGE_SELF).ru_maxrss`, read **in the worker** after the response is fully delivered. The kernel maintains this high-water mark continuously, so no transient spike during JSON serialization or XLSX zip assembly can slip between samples. 50 ms sampling from a monitor thread is kept only as a **supplementary trace** for locating *where* the peak occurs; a sampled maximum is never the number reported. |
| **No warm-up inside a measured process** | `ru_maxrss` is **monotonic for the lifetime of the process** — it cannot be reset, and any earlier peak stays in it. A warm-up request served by the same worker therefore leaves its own peak behind, and subtracting a post-warm-up baseline would not isolate the measured request (a large warm-up could even produce a false failure). So each measured run uses a **fresh worker that serves exactly one request** and is then discarded. First-request costs (lazy imports, the openpyxl module tree, cold allocator arenas) are deliberately *inside* the measurement — they are real memory the first request after a restart pays. |
| Two runs, not two samples | Because the counter cannot be reset mid-process, the delta is taken **across two fresh-worker runs of the same build**, never within one: `baseline` = `ru_maxrss` of a freshly booted worker that has served **zero** requests; `measured` = `ru_maxrss` of a freshly booted worker that has served **exactly one** request. `delta = measured − baseline`. Both operands are absolute high-water marks of comparable processes, so the subtraction is meaningful. |
| Optional refinement | On cgroup v2, `memory.peak` for a dedicated per-run cgroup **is** resettable (write to it), which allows a true within-process warm-up-then-measure delta. Use it if the harness has cgroup control; report which mechanism was used, since the two are not interchangeable. |
| Absolute vs delta | Both are recorded and reported. The **delta** is the portable pass/fail target (it cancels interpreter/build differences). The **absolute** high-water mark from the measured run is what the no-OOM criterion is checked against, since a delta says nothing about total footprint. |
| Concurrency | **1** — exactly one in-flight request, single gunicorn worker (`--workers 1 --threads 1`), no other traffic. |
| Payload | The fixed reference payload (10 MB, ~200k rows of mixed nesting) for `/process`; a 100k-row `csv_data` body for `/export-xlsx`. Both committed as fixtures/generators so runs are reproducible. |
| Verdict | **Pass** iff the cross-run delta `≤ 50 MiB` (`/process`) or `≤ 150 MiB` (`/export-xlsx`) **and** the measured run's absolute high-water mark stays under half the container limit (256 MiB of the default 512 MiB), as the **median of 3 run-pairs**; a single pair above a limit is retried, two of three above it is a fail. |
| Blocked pairs are failures | A pair that cannot produce a number — OOM kill, worker crash, request timeout, truncated or incomplete response, or a missing/unreadable `ru_maxrss` — **counts as a failed pair and stays in the set of three**. It is never dropped, re-rolled as though it had not happened, or treated as a clean sample. An OOM is the single most important signal this budget exists to catch; discarding it as "no data" would invert the result. Record the failure mode with the run. |

These are manual/CI-optional measurements (no perf tests gate CI in v1.2), but the numbers reported against this budget must be produced by exactly this method or they are not comparable.

---

## 5. Design Constraints That Bound the Fixes

- **No server-side payload persistence** (`MEMORY.md` 2026-05-12): the full-dataset-in-`/process`-response design must not be replaced with server-side caching/sessions for export. All fixes must respect this (compression, streaming, client-side lazy rendering are compatible; a server-side export token is not).
- **No disk writes of payloads** (`AGENTS.md`): export buffering must not rely on OS temp files. openpyxl `write_only` mode and `SpooledTemporaryFile` are therefore off the table unless a documented exception (roadmap D6) is approved.
- **No frontend framework / build step**: all client fixes are vanilla JS.
- **Strict CSP, no inline JS**: any new client code stays in `static/js/app.js`.
- **Exact-pinned dependencies**: any new dependency (e.g. `Flask-Compress`) must be pinned exactly and added deliberately; the zero-dependency middleware is preferred.
- **Process-local in-memory rate limiter**: `RATELIMIT_STORAGE_URI` defaults to `memory://`, whose counters are **process-local** — the effective limit is multiplied by `workers × replicas`, not by workers alone. The default deployment therefore stays at one worker and one instance; any configuration above that (roadmap 2.8/2.10) must set a shared `RATELIMIT_STORAGE_URI` (e.g. Redis). Benchmarks must record both counts and the storage backend, and assume no shared counters on `memory://`.
