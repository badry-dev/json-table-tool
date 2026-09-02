# Planned Points — Consolidated Status

**Date:** 2026-09-02
**Shipped version:** `Config.APP_VERSION = '1.2.0'` (CHANGELOG entry dated 2026-08-21)

The single planning document for this project. It replaces five separate files,
which were consolidated into it and deleted:

| Deleted file | What it held | Where it went |
|---|---|---|
| `roadmap-v1.2.md` | Phases 0–5, decisions D1–D6 | §1.3, §1.4 |
| `security-review-v1.2.md` | Findings F1–F17 | §1.1, §2.2 |
| `performance-review-v1.2.md` | Findings P1–P13, perf budget §4 | §1.2, §2.3, Appendix B |
| `code-health-final.md` | 2026-05 review: top-10, quick wins, refactors | §1.5, §2.3 |
| `export-budget-v1.2.md` | How `MAX_EXPORT_CELLS` was derived | Appendix A |

**What the consolidation kept and dropped.** The appendices carry the two things
later work has to *execute* — the export-budget measurement and the RSS protocol
it runs under. Dropped: each finding's own location/description/effort write-up
and the 2026-05 category scores. Those are narrative about work already shipped;
the full text stays in git history at `065883f`, the commit before the deletion.

Status is against the code in this repository, not against the CHANGELOG's own
claims: every "Done" line below was checked against `config.py`, `routes.py`,
`helpers.py`, `security.py`, `static/js/app.js`, `Makefile`, `.github/workflows/ci.yml`
and `requirements*.txt`.

---

## Section 1 — Done

### 1.1 Security findings (F1–F17)

| ID | Point | Where it landed |
|---|---|---|
| F1 | CSV/XLSX formula injection (Critical) | `helpers.sanitize_cell` / `is_formula_trigger` for CSV/TSV/XLSX; XLSX pins `data_type='s'`; JSONL/Markdown deliberately exempt |
| F2 | 7 dependency CVEs | Flask 3.1.3, requests 2.33.0, gunicorn 22.0.0, openpyxl 3.1.5; pytest moved out of the runtime file into `requirements-dev.txt`; `pip-audit -r requirements.txt` runs in CI |
| F3 / F9 | Credential leakage into logs; API JSONL `ValueError` → 500 | Fixed log string with no interpolation; JSONL parse failure returns 400 |
| F4 | User-controlled outbound header name | `routes.is_allowed_outbound_header` — strip + lowercase, then explicit allowlist |
| F5 | Security-header gaps | HSTS on secure requests, `Permissions-Policy`, COOP, CORP; CSP gained `object-src`, `base-uri`, `frame-ancestors`, `form-action`, `upgrade-insecure-requests` |
| F6 | SSRF: blocking DNS, no port restriction | Bounded resolver pool with admission control (`API_DNS_*`); `API_ALLOWED_PORTS` default `80,443,8443` |
| F7 | Default SECRET_KEY accepted in production | `is_production()` fail-fast in the app factory; `env_int()` names the mistyped variable |
| F8 | Recursion-depth DoS | `extract_table_data` depth cap; `RecursionError` → 400 `JSON nesting too deep` |
| F10 | 413 returned HTML | JSON handlers for 413/500/404 |
| F11 | No `Cache-Control: no-store` on data responses | `security.NO_STORE_ENDPOINTS` |
| F12 | Rate limiting ineffective behind a proxy | Opt-in `TRUST_PROXY=1` → `ProxyFix` with exactly one hop; key derived after ProxyFix |
| F13 | Upload extension/content-type unchecked | `routes.validate_upload` |
| F14 | Plain-HTTP credential exposure | Docs-only remediation: HTTPS stated per deploy path; `upgrade-insecure-requests` in CSP |
| F15 | `/health` version disclosure | Kept on by default, gated by `HEALTH_REVEAL_VERSION` |
| F16 | Cookie hardening | `HttpOnly`, `SameSite=Lax`, `Secure` tied to `APP_ENV=production` |
| F17 | Documentation drift | Candidates-handshake references replaced with the tree picker; MIT → GPL-3.0 |

### 1.2 Performance findings (P1–P13)

| ID | Point | Where it landed |
|---|---|---|
| P1 | Uncompressed `/process` responses | In-repo gzip middleware (D1), no new dependency; honours `Accept-Encoding` q-values; skips streamed/bodyless/already-encoded responses |
| P2.2 / P5 | Preview mutation, unbounded nested rendering | `helpers.preview_truncate` returns a capped **copy**; client caps at 20 keys / 20 items / 500 chars |
| P3 | XLSX fully buffered in memory (High) | Diskless normal-mode workbook + `MAX_EXPORT_CELLS` (measured, default 250 000); CSV/TSV generator-streamed and uncapped; 400 rather than truncation |
| P4 | Eager tree-picker build | Lazy children on first toggle, per-level and total node caps |
| P6 | No static cache headers | `STATIC_MAX_AGE` (86 400) with `?v=APP_VERSION` URLs |
| P7 | Blocking DNS in the request path | Shared bounded resolver pool (shared with F6) |
| P8 / P12 | Double column scan; multi-copy memory | `flatten_rows` does one pass; API path decodes the `bytearray` without an intermediate copy |
| P9 | gunicorn timeout vs `API_FETCH_TIMEOUT` | `--timeout 60` everywhere; the invariant is now enforced at startup |
| P10 | Dead code `find_candidate_arrays` | Removed with its four tests (D2) |
| P11 | Hardcoded "25" preview badge | `/process` returns `preview_limit` |
| P13 | Client-side CSV/TSV string building | Chunked Blob builders |

### 1.3 Roadmap phases

- **Phase 0 — Foundations.** Dependency pins, `requirements-dev.txt`, `.github/workflows/ci.yml`, `pyproject.toml` (ruff + pytest), ruff clean, GPL-3.0 correction, `autoDeployTrigger: checksPass`, dead-code removal.
- **Phase 1 — Security.** All 15 tasks (1.1–1.15); see F-table above.
- **Phase 2 — Performance.** All 10 tasks (2.1–2.10), including the rate-limit topology guard: `RATELIMIT_STORAGE_URI` is configurable, `WEB_CONCURRENCY` is the single source of truth for workers, `APP_REPLICAS` mirrors `numInstances`, and production refuses to start on `memory://` above one worker × one replica.
- **Phase 3 — Refactor.** `_load_input` / `_select_table_data` extracted, `process_json` reduced, `openpyxl` imported at module top, `preview_limit` returned, type annotations added to `helpers.py` and `security.py`.
- **Phase 4 — Features.** 4.1 load more / load all with a 50 000-row DOM guard, 4.2 row filter, 4.3 JSONL + Markdown exports, 4.4 column visibility, 4.5 `#path=` deep links, 4.7 `/health/live` + `/health/ready`, 4.8 in-page About modal and keyboard-accessible export dropdown. (4.6 was dropped with D4 — see §1.4.)
- **Phase 5 — Docs/DX.** `MEMORY.md`, `CLAUDE.md`, `AGENTS.md`, `README.md` synced; `.env.example`; `Makefile`; `CHANGELOG.md`; version bumped to 1.2.0.

### 1.4 Decisions closed

| ID | Decision |
|---|---|
| D1 | gzip via in-repo middleware, not `Flask-Compress` |
| D2 | `find_candidate_arrays` deleted in Phase 0, before the depth-guard work |
| D3 | Proxy trust is opt-in via `TRUST_PROXY`, off by default |
| D5 | Port allowlist adopted, default `80,443,8443` |
| D6 | Exports stay diskless and memory-bounded: normal-mode workbook + measured cell budget; `write_only` and `SpooledTemporaryFile` both rejected, each on its own grounds |
| D4 | **Declined (2026-09-02).** No Basic Auth gate. Roadmap task 4.6 and its acceptance line are dropped; per the roadmap, nothing else changes |

### 1.5 Code-health review (2026-05) items now closed

Top-10 issues 1, 2, 3, 4, 5, 7, 8, 9, 10 are done (CI, CVEs, dev/prod dependency
split, ruff, `process_json` complexity, preview badge, LICENSE, `.env.example`,
depth guard). Quick wins 1–8 are done. Larger refactors 7.1, 7.3, 7.4 and 7.5 are
done; 7.2 is partial (see Section 2).

### 1.6 Measurement work

`MAX_EXPORT_CELLS = 250 000` is a measured number, derived by the two-fresh-process
`ru_maxrss` protocol, with a confirming point re-run at the shipped value. Method,
data and derivation: **Appendix A**.

---

## Section 2 — Pending / Planned

### 2.1 Known limitation awaiting a decision

- **JSONL export is not a faithful copy of the input document.** Roadmap 4.3 called
  it "lossless — original values". Shipped behaviour: values are written verbatim
  (the security-relevant half), but over the server's *flattened* projection, so
  `{"tags": [1,2]}` exports as `"tags": "[1, 2]"` and `{"meta": {"role": "x"}}` as
  `"meta.role": "x"`. Fixing it means shipping the original rows alongside the
  flattened ones, doubling the payload and client memory that P2/P12 exist to
  reduce. Explicitly flagged for a maintainer decision, not resolved either way.

### 2.2 Accepted exposures, documented rather than fixed

- **Unbounded DNS teardown (F6.1 / P7 residual).** `getaddrinfo` exposes no timeout
  and cannot be cancelled. `API_DNS_TIMEOUT` bounds only the caller's wait; a pool
  thread stays occupied until the platform resolver returns, and interpreter exit
  can still block on it — realistically tens of seconds with glibc defaults. A
  killable subprocess resolver is the documented escalation and remains out of v1.2
  scope. Best-effort narrowing where the deployment allows: pin
  `options timeout:2 attempts:1` in the container's `resolv.conf`.
- **DNS rebinding (SSRF residual).** Mitigated by `allow_redirects=False` and
  documented in `routes.py`. Escalation path if the threat model changes from
  internal tool to public service: a custom `HTTPAdapter` that resolves once and
  passes the IP with an explicit `Host` header.

### 2.3 Carried-over engineering work

- **Type annotations (code-health 7.2, roadmap 3.5) — partial.** `helpers.py` and
  `security.py` are annotated. `routes.py` and `config.py` have no annotated
  signatures, and `mypy` is not in `requirements-dev.txt`, `pyproject.toml`, the
  `Makefile`, or CI. The roadmap deliberately marked mypy optional and skipped
  strict mode; the remaining work is the two unannotated modules plus a mypy
  configuration if it is wanted.
- **Perf budget verification (Appendix B).** The XLSX row of the budget
  was measured. The rest of the table — `/process` transfer size ≤ 2–4 MB,
  `/process` p95 ≤ 3 s, `/process` peak-RSS delta ≤ 50 MiB, tree-picker open
  ≤ 500 ms on a 10 MB payload — is defined but has no recorded run. No perf test
  gates CI (`pytest-benchmark` was deferred by decision), so these stay manual.
- **Measurement harness is not committed.** The export-budget script is a throwaway;
  re-deriving the budget means rebuilding it from Appendix A. Committing
  fixtures/generators for the 10 MB reference payload and the 100 k-row `csv_data`
  body would make the budget reproducible rather than re-derivable.
- **Transitive dependency drift (code-health §12).** Direct dependencies are
  exact-pinned; transitives are not. A lock file (`pip-compile`) was noted as a
  post-review iteration and has not been added.
- **Docker artifacts.** `README.md` carries Dockerfile and docker-compose templates,
  but no `Dockerfile` is checked in. Phase 5 deliberately kept these docs-only; a
  committed Dockerfile is a fresh decision, not pending roadmap work.

### 2.4 Explicitly out of scope — do not implement without a new decision

These are settled exclusions, listed so they are not mistaken for a backlog:

- Server-side payload caching or session storage for export — violates the
  no-persistence requirement. Perf is served by compression, streaming and
  client-side rendering instead.
- Redis rate-limit storage as the default. It ships as an optional
  `requirements-redis.txt`, required only above one worker or one replica.
- Any frontend framework or build step.
- Any CSP relaxation, `unsafe-inline` included. Phase 1 only tightened it.
- Payload-level logging or telemetry.
- Auto keep-alive pings against the Render free tier.
- Committed `docker-compose` / systemd unit files.
- **Any app-level authentication gate**, HTTP Basic Auth included (roadmap 4.6 / D4,
  declined 2026-09-02). Access control stays a deployment concern — put the app
  behind whatever the network or reverse proxy already enforces.

---

## Verification checklists still requiring a manual sign-off

Two lines in the (now folded-in) security review's post-fix checklist are marked manual and have
no automated equivalent: **F14** (every deployment path states HTTPS is required)
and **F17** (no stale `candidates` or MIT references remain in the docs). The rest
of that checklist is covered by `tests/test_routes.py`, `tests/test_security.py`
and the Node assertions in `tests/js/`.

---

## Appendix A — XLSX export budget: how `MAX_EXPORT_CELLS` was measured

**Measured:** 2026-08-21. **Applies to:** roadmap 2.3 / D6, finding P3.
**Result:** `DEFAULT_MAX_EXPORT_CELLS = 250_000` cells (`config.py`).

D6 requires the guard's default to be measured, not chosen. These are the numbers
it came from, kept so it can be re-derived when the measurement is re-run.

### Method

Appendix B's protocol, with one documented deviation.

Followed as written: `ru_maxrss` read on Linux (KiB) × 1024, reported in MiB;
`resource.getrusage(RUSAGE_SELF).ru_maxrss` read after the response was fully
delivered; each measured process serves **exactly one** request then exits;
`delta = measured − baseline` across two fresh processes (baseline served zero
requests); concurrency 1; absolute and delta both recorded; no blocked pairs
occurred and none were discarded.

**Deviation:** requests went through the Flask test client in a fresh Python
process rather than a fresh gunicorn worker, and the sizing sweep used one
run-pair per shape rather than the median of three. The property the protocol
exists to protect — `ru_maxrss` is monotonic per process and cannot be reset
mid-process — is preserved, since every number comes from a process that served
exactly one request. These numbers are comparable to each other but must not be
quoted against the Appendix B budget as though they came from the full
gunicorn / median-of-three protocol.

`MAX_CONTENT_LENGTH` was raised for the measurement only, so request-body size
would not mask the workbook cost.

### Data

| rows × cols | cells | delta (MiB) | absolute (MiB) |
|---|---|---|---|
| 15,000 × 10 | 150,000 | 73.6 | 114.3 |
| 83,333 × 3 | 249,999 | **138.9** | 179.6 |
| 50,000 × 3 | 150,000 | **84.3** | 125.0 |
| 20,000 × 10 | 200,000 | 98.6 | 139.2 |
| 2,000 × 150 | 300,000 | 137.3 | 178.0 |
| 91,666 × 3 | 274,998 | **152.2** | 193.0 |
| 100,000 × 3 | 300,000 | **161.7** | 202.4 |
| 40,000 × 10 | 400,000 | 195.6 | 236.3 |

At equal cell counts the **narrow, tall** shape is consistently the most
expensive (84.3 vs 73.6 MiB at 150,000 cells; 161.7 vs 137.3 at 300,000):
openpyxl carries per-row overhead on top of per-cell. Three columns is the worst
aspect ratio tested and the one the budget is sized against.

It is also why the budget is expressed in **cells**, not rows — 50,000 rows costs
84.3 MiB at 3 columns while 40,000 rows costs 195.6 MiB at 10, so a row count says
almost nothing about the footprint.

### Derivation

Fitting the two bracketing points of the 3-column series:

```text
(150,000 cells, 84.3 MiB) and (274,998 cells, 152.2 MiB)
slope     = 0.000543 MiB/cell
intercept = 2.8 MiB
150 MiB crossing = (150 − 2.8) / 0.000543 ≈ 270,900 cells
```

The 274,998-cell run measured **152.2 MiB — over the 150 MiB target** — so the
crossing is real, not an extrapolation artifact. The budget sits at **250,000
cells**, ~8% below the crossing, which is the margin run-to-run variance on these
measurements needs.

That value was then measured directly rather than left as a fit: 83,333 × 3 =
249,999 cells came back at **138.9 MiB delta / 179.6 MiB absolute** (the fit
predicted 138.6). It passes both halves of the verdict — under the 150 MiB delta
target and well under the 256 MiB absolute ceiling for a 512 MiB container.

### What the budget does and does not cover

- **XLSX-only.** CSV and TSV are generator-streamed and stay uncapped, so every
  dataset `/process` accepts remains exportable by some route. That, not an
  unbounded XLSX path, is what keeps the export contract as wide as the input one.
- **Enabled by default.** An unlimited default would leave P3 (High) unmitigated.
  `MAX_EXPORT_CELLS=0` disables it for operators who knowingly opt out.
- **Advertised, never silent.** `/process` returns `total_cells` and
  `max_export_cells` so the client greys Excel out before the click, and
  `/export-xlsx` returns 400 for direct API callers. No truncation — a partial
  spreadsheet is worse than a refusal.
- The 10 MiB request cap makes memory finite but not usefully bounded: the
  JSON → Python → openpyxl → zip multiplier is large and data-dependent. The cell
  budget is the bound; the request cap is not a substitute.

### Reproducing

The harness is not committed (throwaway script; no perf tests in CI). It does two
things, each in its own process:

1. `baseline`: boot `create_app()`, serve nothing, print `ru_maxrss`.
2. `measured`: boot `create_app()`, POST one synthetic `csv_data` body of
   `rows × cols` cells to `/export-xlsx` with `MAX_EXPORT_CELLS=0`, assert 200,
   print `ru_maxrss`.

Subtract. Re-derive the fit from at least two points on the narrowest aspect ratio
you care about, and re-run a confirming point at the value you intend to ship.
Record the new data in this appendix. Do not round the result to something tidy.

---

## Appendix B — Perf budget and the RSS measurement protocol

Targets on a reference payload (10 MB, ~200k rows of mixed nesting), single
free-tier worker. Only the `/export-xlsx` row has a recorded run (Appendix A);
the rest are defined but unmeasured — see §2.3.

| Metric | Before v1.2 (est.) | Target |
|---|---|---|
| `/process` transfer size | ~10–20 MB | ≤ 2–4 MB (gzip) |
| `/process` p95 latency (paste/upload only) | seconds, unbounded | ≤ 3 s |
| Peak RSS **delta**, `/process` (10 MB input) | ~40–60 MiB | **≤ 50 MiB**, absolute high-water < 256 MiB |
| Peak RSS **delta**, `/export-xlsx` 100k rows | hundreds of MiB (OOM risk) | **≤ 150 MiB**, absolute < 256 MiB, streams |
| Tree-picker open, 10 MB payload | multi-second freeze | ≤ 500 ms initial, lazy children |
| Cell with a 10k-key object | freeze | ≤ 20 keys + "more" |
| Static assets | revalidated every load | cached ≥ 1 day |

The latency target **excludes API-fetch requests** — those are bounded separately
by `API_FETCH_TIMEOUT` plus DNS time, which would make a single aggregate p95
meaningless. The RSS target covers the whole parse → flatten → `jsonify` pipeline;
it is not a claim that gzip or dropping one copy fits the process under 30 MB.

### Protocol (identical for both RSS rows; both are pass/fail against these rules)

`ru_maxrss` is a per-process high-water mark that **cannot be reset**, which is
what forces the fresh-process protocol.

| Parameter | Definition |
|---|---|
| Units | `ru_maxrss` is **not portable**: KiB on Linux, **bytes** on macOS. Convert and report in **MiB**. Every threshold here is MiB, not decimal MB. Skipping the conversion reports numbers 1024× off. |
| Environment parity | Both runs of a pair on the **same OS and kernel, container image, Python build, and cgroup limits**, on an otherwise idle host. A baseline from one image and a measurement from another is not a delta. Record all of it. |
| Peak, not sampling | `resource.getrusage(RUSAGE_SELF).ru_maxrss`, read **in the worker** after the response is fully delivered. The kernel maintains it continuously, so no transient spike can slip between samples. 50 ms sampling is a supplementary trace for locating the peak only — never the reported number. |
| No warm-up inside a measured process | The counter is monotonic for the process lifetime, so a warm-up request leaves its own peak behind and a post-warm-up baseline would not isolate the measured request. Each measured run uses a **fresh worker serving exactly one request**, then discarded. First-request costs (lazy imports, the openpyxl module tree, cold arenas) are deliberately inside the measurement — they are memory the first request after a restart really pays. |
| Two runs, not two samples | `baseline` = freshly booted worker, **zero** requests served. `measured` = freshly booted worker, **exactly one**. `delta = measured − baseline`. Both are absolute high-water marks of comparable processes, so the subtraction means something. |
| Optional refinement | On cgroup v2, `memory.peak` for a dedicated per-run cgroup **is** resettable, allowing a true within-process warm-up-then-measure delta. Report which mechanism was used; the two are not interchangeable. |
| Absolute vs delta | Record both. The **delta** is the portable pass/fail target (it cancels interpreter/build differences); the **absolute** high-water mark is what the no-OOM criterion is checked against, since a delta says nothing about total footprint. |
| Concurrency | **1** — one in-flight request, `--workers 1 --threads 1`, no other traffic. |
| Payload | The fixed 10 MB / ~200k-row reference payload for `/process`; a 100k-row `csv_data` body for `/export-xlsx`. Both should be committed as fixtures so runs are reproducible (they are not — see §2.3). |
| Verdict | **Pass** iff the cross-run delta is ≤ 50 MiB (`/process`) or ≤ 150 MiB (`/export-xlsx`) **and** the measured run's absolute high-water mark stays under half the container limit (256 MiB of 512 MiB), as the **median of 3 run-pairs**. One pair over a limit is retried; two of three over it is a fail. |
| Blocked pairs are failures | A pair that produces no number — OOM kill, worker crash, timeout, truncated response, unreadable `ru_maxrss` — **counts as a failed pair and stays in the set of three**. Never dropped or re-rolled. An OOM is the single most important signal this budget exists to catch; discarding it as "no data" inverts the result. Record the failure mode. |

These are manual measurements — no perf test gates CI — but numbers reported
against this budget must come from exactly this method or they are not comparable.

### Design constraints that bound any future fix

- **No server-side payload persistence.** The full-dataset-in-`/process` design
  must not become server-side caching or sessions for export. Compression,
  streaming and client-side lazy rendering are compatible; an export token is not.
- **No disk writes of payloads.** openpyxl `write_only` is off the table (it writes
  worksheet parts to OS temp files), and `SpooledTemporaryFile` is off it for a
  different reason: at its default `max_size=0` it never rolls over and saves no
  memory, while any non-zero threshold — or a `fileno()` call — puts payload bytes
  on disk. Either pointless or disk-backed, never both diskless and memory-light.
- **No frontend framework or build step**; all client code stays vanilla in
  `static/js/app.js`.
- **Strict CSP, no inline JS.**
- **Exact-pinned dependencies.** Any new one is added deliberately; the
  zero-dependency middleware is preferred (this is why gzip is in-repo, D1).
- **Process-local rate limiter.** `memory://` counters multiply the effective limit
  by `workers × replicas`. Benchmarks must record both counts and the backend.
