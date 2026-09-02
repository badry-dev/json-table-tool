# XLSX export budget — how `MAX_EXPORT_CELLS` was measured

**Date:** 2026-08-21
**Applies to:** roadmap task 2.3 / D6, performance finding P3.
**Result:** `DEFAULT_MAX_EXPORT_CELLS = 250_000` cells (`config.py`).

D6 requires the guard's default to come from the Performance Review §4
measurement rather than being chosen by feel. This file records the numbers it
was derived from, so it can be re-derived when the measurement is re-run.

## Method

Performance Review §4's protocol, with one documented deviation.

Followed as written:

| Parameter | This run |
|---|---|
| Units | `ru_maxrss` read on Linux (KiB), multiplied by 1024, reported in MiB |
| Peak | `resource.getrusage(RUSAGE_SELF).ru_maxrss`, read after the response was fully delivered |
| No warm-up in a measured process | Each measured process serves **exactly one** request, then exits |
| Two runs, not two samples | `baseline` = a freshly booted process that served **zero** requests; `measured` = a freshly booted process that served exactly one. `delta = measured − baseline` |
| Concurrency | 1 |
| Absolute and delta | Both recorded |
| Blocked pairs | None occurred; none were discarded |

**Deviation:** requests were issued through the Flask test client inside a fresh
Python process rather than through a fresh gunicorn worker, and the sizing sweep
used one run-pair per shape rather than the median of three. The property the
protocol exists to protect — that `ru_maxrss` is monotonic per process and so
cannot be reset mid-process — is preserved: every measured number comes from a
process that served exactly one request. Numbers produced this way are
comparable to each other but should not be quoted against the §4 budget as if
they had come from the full gunicorn/median-of-three protocol.

`MAX_CONTENT_LENGTH` was raised for the measurement only, so request-body size
would not mask the workbook cost.

## Data

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
expensive (84.3 vs 73.6 MiB at 150,000 cells; 161.7 vs 137.3 at 300,000) —
openpyxl carries per-row overhead on top of per-cell. Three columns is therefore
the worst aspect ratio tested and the one the budget is sized against.

This is also why the budget is expressed in **cells** rather than rows: 50,000
rows costs 84.3 MiB at 3 columns and 40,000 rows costs 195.6 MiB at 10, so a row
count says almost nothing about the footprint on its own.

## Derivation

Fitting the two bracketing points of the 3-column series:

```text
(150,000 cells, 84.3 MiB) and (274,998 cells, 152.2 MiB)
slope     = 0.000543 MiB/cell
intercept = 2.8 MiB
150 MiB crossing = (150 − 2.8) / 0.000543 ≈ 270,900 cells
```

The 274,998-cell run measured **152.2 MiB — over the 150 MiB target**, so the
crossing is real and not an artifact of extrapolation. The budget is set at
**250,000 cells**, roughly 8% below the crossing, which is the margin
run-to-run variance on these measurements needs.

That value was then measured directly rather than left as an extrapolation:
83,333 × 3 = 249,999 cells came back at **138.9 MiB delta / 179.6 MiB absolute**
(the fit predicted 138.6). It passes both halves of the §4 verdict — under the
150 MiB delta target, and well under the 256 MiB absolute ceiling for a 512 MiB
container.

## What the budget does and does not cover

- It is **XLSX-only**. CSV and TSV are generator-streamed and stay uncapped, so
  every dataset `/process` accepts remains exportable by some route. That, not
  an unbounded XLSX path, is what keeps the export contract as wide as the input
  contract.
- It is **enabled by default**. An unlimited default would leave P3 (High)
  unmitigated. `MAX_EXPORT_CELLS=0` disables it for operators who knowingly opt
  out.
- It is **advertised, never silent**. `/process` returns `total_cells` and
  `max_export_cells` so the client greys the Excel entry out before the user
  clicks; `/export-xlsx` independently returns 400 for direct API callers. There
  is no truncation — a partial spreadsheet is worse than a refusal.
- The 10 MiB request cap makes memory finite but not usefully bounded: the
  JSON → Python → openpyxl → zip expansion multiplier is large and
  data-dependent. The measured cell budget is the bound; the request cap is not
  a substitute for it.

## Reproducing

The harness is not committed (it is a throwaway measurement script, and the
roadmap keeps perf tests out of CI). It does two things:

1. `baseline`: boot `create_app()`, serve nothing, print `ru_maxrss`.
2. `measured`: boot `create_app()`, POST one synthetic `csv_data` body of
   `rows × cols` cells to `/export-xlsx` with `MAX_EXPORT_CELLS=0`, assert 200,
   then print `ru_maxrss`.

Run each in its own process and subtract. Re-derive the fit above from at least
two points on the narrowest aspect ratio you care about, and re-run the
confirming point at the value you intend to ship.
