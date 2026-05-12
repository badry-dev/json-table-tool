# MEMORY.md

A living log of **non-obvious** decisions, constraints, gotchas, and context that any contributor (human or AI) should know before changing this codebase. This is **not** a changelog — see `git log` for that. This file captures the *why* behind choices that aren't visible in the code itself.

## How to Use This File

- **Read it** before starting any non-trivial change, especially in areas tagged below.
- **Append to it** when you make or learn something that future-you (or another agent) would otherwise have to rediscover.
- **Prune it** when an entry becomes stale or wrong — outdated memory is worse than no memory.

### Entry Format

Each entry should be self-contained and answer three questions:

```
### YYYY-MM-DD — Short title  (area: backend | frontend | deploy | security | ux)

**What:** the decision, constraint, or surprise.
**Why:** the reason — past incident, requirement, tradeoff, stakeholder ask.
**How to apply:** what a future contributor should *do* with this knowledge.
**Owner / source:** name, ticket, or commit (optional).
```

Keep entries short — if it grows past ~10 lines, it probably belongs in `README.md` or `CLAUDE.MD` as documentation.

---

## Active Memory

### 2026-05-12 — In-memory-only is a hard requirement  (area: security / privacy)

**What:** The app must never persist user-submitted JSON to disk, DB, or any external system.
**Why:** Designed as an internal tool for handling potentially sensitive payloads (API responses, exports). The free Render tier deliberately has no persistent disk to enforce this physically.
**How to apply:** Reject any PR that adds a DB driver, file write, third-party analytics, or request-body logging. The README's "Privacy First" section is contract, not aspiration.

### 2026-05-12 — Single-file frontend is intentional  (area: frontend)

**What:** `templates/index.html` contains all HTML, CSS, and JS (~1100 lines).
**Why:** Optimizes for deploy simplicity (no build step), readability (one file to grep), and the free-tier deployment model. The app is small enough that a framework would be more code than the app itself.
**How to apply:** Resist suggestions to split into `static/css`, `static/js`, or add Vite/webpack/React unless the user explicitly asks. If the file grows past ~2000 lines, revisit the tradeoff.

### 2026-05-12 — Preview is 25 rows; CSV is everything  (area: ux / backend)

**What:** `/process` returns the first 25 rows for in-browser display, and `csv_data` contains the full flattened dataset. Both are sent in the same response.
**Why:** Browser rendering of huge tables was the original UX problem. CSV export needs to be a separate, complete payload so the user gets the full data even when the preview is truncated.
**How to apply:** Don't conflate `preview` and `csv_data`. If you change the preview size, update the constant in `app.py`, the matching text in `index.html`, and `README.md` together.

### 2026-05-12 — `extract_table_data` is heuristic, not exhaustive  (area: backend)

**What:** The function picks the **first** list-of-objects it encounters in the JSON.
**Why:** Real-world JSON payloads are inconsistent — sometimes `{"data": [...]}`, sometimes `{"results": {"items": [...]}}`, sometimes a bare array. A heuristic covers the common cases without forcing the user to specify a JSONPath.
**How to apply:** Don't "fix" this by making it stricter. If a payload surfaces the wrong array, the right answer is to let the user specify a path (a future feature), not to break existing common cases.

### 2026-05-12 — `csv_export_api_routes.py` is dead weight  (area: backend)

**What:** A small `.py` file that looks like Python but is actually a markdown documentation fragment. It is **not imported** anywhere.
**Why:** Probably a refactoring leftover.
**How to apply:** Either delete it or convert it into `docs/api-routes.md`. Don't try to `import` from it.

### 2026-05-12 — Pinned dependencies are deliberate  (area: deploy)

**What:** `requirements.txt` uses exact `==` pins (Flask 3.0.0, requests 2.31.0, gunicorn 21.2.0).
**Why:** Render auto-deploys on push. Loose pins + auto-deploy = surprise breakage. Exact pins keep deploys reproducible.
**How to apply:** Bump versions intentionally in a dedicated commit, not as a side effect of another change. Test locally before pushing.

### 2026-05-12 — 30s timeout + raise_for_status on outbound fetches  (area: backend / reliability)

**What:** The `api` input method uses `requests.get(..., timeout=30)` and `response.raise_for_status()`.
**Why:** Without a timeout, a slow upstream API would hang gunicorn workers indefinitely on the free tier (which has limited workers). `raise_for_status` ensures 4xx/5xx from upstream surfaces as a clean error to the user, not a confusing empty-table.
**How to apply:** Keep both. If a use case genuinely needs more than 30s, make the timeout configurable rather than removing it.

### 2026-05-12 — Render free tier specifics  (area: deploy)

**What:** Free tier has no persistent disk, sleeps after inactivity (~15 min), and cold-starts on first request after sleep.
**Why:** Cost.
**How to apply:** Don't rely on in-process caches surviving across requests — the dyno may have been restarted. Don't add a heartbeat to keep it awake; that defeats the cost benefit. Document the cold-start in user-facing materials if it becomes a complaint.

---

## Conventions for Adding Entries

- **Date** in `YYYY-MM-DD` so entries sort naturally.
- **Tag the area** so contributors can filter (`backend`, `frontend`, `deploy`, `security`, `ux`, `meta`).
- **Past tense for what happened, present for the rule.** "We tried X, it broke. **Don't use X.**"
- **Don't duplicate code documentation.** If the answer is "read the docstring", don't write a memory entry — improve the docstring.
- **Prefer linking out** for long context (Linear ticket, PR, incident postmortem) rather than inlining a wall of text.

## When to Promote a Memory Entry

If an entry is referenced repeatedly or applies to *every* contributor (not just "people working in this area"), promote it:

- Project-wide conventions → `CLAUDE.MD` and/or `AGENTS.md`.
- User-facing behavior → `README.md`.
- Setup / deploy specifics → `README.md` or a dedicated `docs/` page.

Memory entries are for **non-obvious** context. Once an entry becomes obvious because the code, docs, or onboarding caught up, retire it.
