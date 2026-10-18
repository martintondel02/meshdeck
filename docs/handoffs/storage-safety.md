# Phase 6.3 — bounded disk usage (handoff)

> **Status:** landed on branch `work/storage-safety`, 2026-10-18.
> **Scope:** page-cache byte cap, LXMF propagation message-store cap, usage in
> `GET /api/v1/status`, Settings → Advanced UI (usage + limit + clear cache).
> **Rule reminder:** this file is the honest record. Anything marked
> *unverified* below was **not** run end-to-end in this session.

---

## Changelog-ready entry

```markdown
- **Disk usage is now bounded and visible (Phase 6.3).** The offline page
  cache has a real total ceiling — `page_cache_max_bytes`, default 64 MiB,
  `0` = unlimited — enforced on every write by evicting the oldest pages
  (a single page over the ceiling is refused, the 4 MiB per-page cap stays).
  The LXMF propagation message store is capped too:
  `propagation_storage_limit_mb`, default 256 MB, `0` = unlimited, applied
  through LXMF's own API (LXMF culls the store in its periodic maintenance
  job). Settings → Advanced → *Host for others* shows store usage and a
  limit field, a new *Storage* card shows page-cache usage with **Clear
  cache**, and `GET /api/v1/status` gains `page_cache_bytes`,
  `page_cache_entries`, `page_cache_max_bytes`, `propagation_store_bytes`,
  `propagation_storage_limit_mb`, `propagation_storage_limit_bytes`.
```

---

## Setting and API contract

| Setting | Default | Range accepted by `PUT /settings` | `0` means |
|---|---|---|---|
| `page_cache_max_bytes` | `67108864` (64 MiB) | integer `0 … 1073741824` (1 GiB) | unlimited |
| `propagation_storage_limit_mb` | `256` | integer `0 … 10240` (10 GiB) | unlimited |

Both are live-applied (no restart) and both are in `DEFAULT_SETTINGS`, so
`GET /settings` returns them even on an existing database.

Validation is **strict and rejecting, never clamping**: a JSON string
(`"256"`), a float (`256.5`), a boolean, a negative number or anything above
the ceiling is a `400` with error code

* `invalid_page_cache_max_bytes`
* `invalid_propagation_storage_limit_mb`

Numeric limits are validated *before* any key of the same `PUT` is written, so
a bad limit cannot leave earlier keys half-applied. Logic:
`meshdeck/config.py::coerce_setting_int`, called from
`CoreService.update_settings`.

New API surface:

```
GET    /api/v1/status      → page_cache_bytes, page_cache_entries,
                             page_cache_max_bytes,
                             propagation_store_bytes (null = not hosting),
                             propagation_storage_limit_mb (setting),
                             propagation_storage_limit_bytes (applied)
DELETE /api/v1/page_cache  → {"cleared": n, "page_cache_bytes": 0, …}
```

`DELETE /api/v1/page_cache` only touches the `page_cache` table (auth
required like every `/api/*` route). It publishes `page_cache_cleared` on the
bus for other WS clients.

---

## Page cache: what changed and why

`meshdeck/storage/page_cache.py`

* `PageCache(db, max_bytes=64 MiB)`; `max_bytes=0` disables the total cap.
* `put()` makes room **before** inserting: it walks rows by
  `fetched_ts ASC, rowid ASC`, evicting the oldest until
  `used + incoming ≤ max_bytes`. The row being refreshed is excluded from
  eviction, so an overwrite never double-counts and the fresh entry always
  survives.
* A single page larger than the *total* ceiling is refused (`put()` returns
  `False`) instead of thrashing the cache, and refusing does not evict
  anything.
* The per-entry 4 MiB cap (`MAX_CACHE_BYTES`) is unchanged and independent.
* New `total_bytes()`, `count()`, `clear()`, `set_max_bytes()` (live shrink),
  and `prune()` gained a `max_bytes=` parameter (`None` = use the configured
  ceiling). The boot prune still drops >30-day entries and caps rows at 500,
  but it is now a belt on top of the per-write byte bound, not the bound.
* Eviction deletes in batches of 400 rowids to stay under SQLite's parameter
  limit.

Service wiring: `CoreService.start()` constructs the cache with the stored
ceiling; `update_settings` calls `set_max_bytes()` so lowering the limit
shrinks the cache immediately.

---

## Propagation store: how LXMF 1.2.1 actually applies the limit

Verified in the installed source, `.venv/lib/python3.14/site-packages/LXMF/LXMRouter.py`:

| Line | Fact |
|---|---|
| `147` | `__init__` sets `self.message_storage_limit = None` → **unlimited by default** |
| `720-740` | `set_message_storage_limit(kilobytes=, megabytes=, gigabytes=)`: multiplies by 1000/1e6/1e9 and assigns the public attribute. No immediate action, no validation beyond `> 0` |
| `747-751` | `message_storage_size()` sums the stored file sizes (`propagation_entries[..][3]`); returns `None` when `propagation_node` is `False` |
| `886`, `909-910` | `jobs()` calls `clean_message_store()` every `JOB_STORE_INTERVAL = 120` ticks (≈120 s) **and only while `propagation_node == True`** |
| `1193-1230` | `clean_message_store()` compares size against the limit and deletes entries/files by weight (oldest/largest first) until it is under the limit |

So the limit is real and enforced **by LXMF itself**, with two consequences we
do not hide:

1. It only bites while hosting is enabled.
2. It is periodic: after a limit change or a burst of inbound messages the
   store can sit above the limit for up to ~2 minutes (one job interval).
   Nothing in MeshDeck fakes or pre-empts that.

How MeshDeck applies it (`meshdeck/chat/router.py`):

* `ChatRouter(..., propagation_storage_limit_mb=…)` applies the cap in
  `start()` **before** hosting starts, and again every time hosting is
  enabled (`set_propagation_hosting(True)`), so a disable/enable cycle keeps
  the configured value.
* A limit > 0 uses the official setter:
  `LXMRouter.set_message_storage_limit(megabytes=n)`.
* `0` (unlimited) is applied by assigning the public attribute
  `router.message_storage_limit = None`. This is **not** a workaround for a
  missing feature — it is the only correct path: LXMF 1.2.1's setter ends in
  `int(None)` for `megabytes=0` and raises
  `ValueError("Cannot set LXMF information storage limit to None")`
  (reproduced in `tests/unit/test_storage_limits.py`). `None` is exactly what
  `LXMRouter.__init__` uses for "no limit". **LXMF is not patched or
  monkeypatched.**
* MeshDeck never calls `clean_message_store()` itself: that method mutates
  `propagation_entries` and deletes files, and LXMF's own job thread may run
  it concurrently. We let LXMF own its store.
* `propagation_store_bytes` is a defensive read of
  `message_storage_size()`; a torn read (`RuntimeError: dictionary changed
  size during iteration`, possible because LXMF's job thread mutates the dict)
  returns `None` and the next status poll succeeds. `/status` therefore never
  breaks because of a stats read, and `null` explicitly means "unknown / not
  hosting" rather than "0 bytes".

### Verified LXMF behaviour (real library code, this session)

A probe against the installed 1.2.1 code (five 100-byte entries, limit 250
bytes) — also pinned as
`tests/unit/test_storage_limits.py::test_lxmf_121_enforces_the_limit_in_its_own_store_clean`:

```
BEFORE used=500 limit=250 entries=5
AFTER  used=200 entries=2 disk=200        # files deleted too
BEFORE used=500 limit=None  entries=5
AFTER  used=500 entries=5                 # unlimited keeps everything
megabytes=256 -> 256000000
megabytes=0 raises: ValueError Cannot set LXMF information storage limit to None
```

Live daemon (real `LXMRouter`, temp data dir), log + `/status`:

```
23:52:26 I meshdeck.chat.router: Propagation message storage limit set to 256 MB
...
PUT {"propagation_storage_limit_mb":128} → 200
{propagation_hosting: True, propagation_store_bytes: 0,
 propagation_storage_limit_mb: 128, propagation_storage_limit_bytes: 128000000}
23:52:40 I meshdeck.chat.router: Propagation message storage limit set to 128 MB
```

`propagation_storage_limit_bytes == 128000000` is read back from the router,
i.e. LXMF is holding our limit.

---

## Worst-case disk math

### Before

* **Page cache:** 500 rows × 4 MiB = **2,048,000,000 B ≈ 2.05 GB**, and even
  that was soft: the 500-row cap was only applied by `prune()` at boot, so a
  long-running instance could exceed 500 rows (the only hard bound was 4 MiB
  per page, i.e. effectively disk-sized).
* **Propagation store:** LXMF default `message_storage_limit = None` →
  **unlimited**. With `MESSAGE_EXPIRY = 30*24*3600` the store could hold
  everything received in the last 30 days, at whatever size peers synced
  (each transfer is separately capped only by LXMF's per-transfer limits).
  A v0.1.0 host inviting strangers onto their box had no disk ceiling at all.

### After

* **Page cache:** hard ceiling **67,108,864 B (64 MiB)** enforced on every
  `put()` (plus the boot prune); each entry still ≤ 4 MiB.
* **Propagation store:** configured ceiling **256,000,000 B (256 MB decimal,
  matching LXMF's `megabytes` unit and `RNS.prettysize` output)** while
  hosting, enforced by LXMF's clean job. Transient overshoot up to the bytes
  accepted during the ≤120 s window between passes; a store that already
  exceeds a newly lowered limit shrinks within that window.
* **Combined bound:** ≈ 323 MB (64 MiB + 256 MB) versus ≈ 2.05 GB + unbounded
  before. Defaults only — 0 = unlimited remains available for operators who
  want it.

Still **not** capped by this phase (honest list): received chat attachments
(1.5 MiB per message, kept forever under `files/<peer>/<msg>/`), shared
files (32 MiB each), hosted pages (4 MiB each), the SQLite message/peer
history, and the Reticulum/LXMF logs. Those are candidates for a later phase;
they were explicitly out of scope here.

---

## Verified vs unverified

| Item | Status |
|---|---|
| Page-cache cap evicts oldest, total ≤ cap, oversize entry refused, unlimited mode, overwrite, live shrink, `prune(max_bytes=)` | **verified** — 9 new unit tests (16 in the file) in `tests/unit/test_page_cache.py` |
| `PUT /settings` returns 400 for string/float/bool/negative/over-range limits, 200 for valid in-range | **verified** — unit tests + real HTTP on a booted daemon (`"128"`→400, `128.5`→400, `20000`→400, `128`→200, `0`→200, `-5`→400) |
| `/status` contains all six new fields; `propagation_store_bytes` is `0` while hosting and `null` when not | **verified** — real daemon (see commands below) |
| Limit is installed on the real `LXMRouter` (applied byte value + log line), including when hosting is enabled at boot and enabled later | **verified** — real daemon |
| LXMF actually culls its message store to the configured limit | **verified against real LXMF 1.2.1 code** by calling `clean_message_store()` on a store with known files (see above); **not** observed live over a 120 s job cycle with >256 MB of synced messages |
| LXMF's periodic enforcement inside a live hosting daemon (wait ≥2 min, blow past the store cap, watch it trim) | **unverified** — not run; no real >256 MB propagation traffic was generated in this session |
| Settings UI: usage text, limit validation (client), save, immediate status refresh, Clear cache + refreshed usage, no console errors | **verified** — headless Chromium (Playwright 1.56 + cached Chromium 1248) against the real daemon; DOM text below |
| `DELETE /api/v1/page_cache` clears rows and returns the count | **verified** — unit test + real daemon (`{"cleared": 1, …}`) |
| `propagation_storage_limit_mb` reaching LXMF when hosting is toggled off/on again | **verified** — unit test on the ordering (`limit set before enable`, cap survives cycles) |
| Windows/macOS, Flatpak, frozen binary | **unverified** — not built in this session |
| Long-running disk pressure (e.g. disk full during a put) | **unverified** — SQLite errors are not specially handled; out of scope |

---

## UI copy added (`frontend/src/lib/i18n/en.ts`)

`settings.propagation_store_usage`, `..._usage_unlimited`, `..._not_hosting`,
`settings.propagation_limit_label`, `..._hint`, `..._saved`, `..._invalid`,
`settings.storage_section`, `settings.page_cache_usage`,
`..._usage_unlimited`, `..._hint`, `settings.clear_cache`,
`settings.cache_cleared_one/_other`, `settings.cache_clear_failed`.

Notes for the next session:

* Page-cache sizes are shown in binary units (the cap is 64 MiB → "64.0 MB")
  and the LXMF store in decimal units (LXMF's own MB → "256.0 MB"), so each
  line matches the number the setting actually holds.
* There is **no** UI field for `page_cache_max_bytes` yet — it is API-only
  (`PUT /settings`). The UI shows usage, the effective ceiling and Clear
  cache; adding a field is a small follow-up.
* The Settings component widens the shared `Status` type locally
  (`StorageStatus`) because `frontend/src/lib/stores.ts` was outside this
  task's file ownership. Moving those fields into the real `Status`
  interface is a one-line cleanup.
* `settings_updated` WS events now also carry `page_cache_max_bytes` /
  `page_cache_bytes` / `propagation_storage_limit_mb` /
  `propagation_storage_limit_bytes`.

---

## Commands run (real output, final state)

```
$ .venv/bin/python -m pytest tests/unit -q
80 passed in 0.42s

$ .venv/bin/ruff check meshdeck tests
All checks passed!

$ timeout 200 .venv/bin/python -m pytest tests/api -m integration -q
1 passed, 3 warnings in 0.14s

$ cd frontend && pnpm run check
svelte-check found 0 errors and 0 warnings
$ pnpm run test
Test Files  2 passed (2) / Tests  37 passed (37)
$ pnpm run build
dist/assets/index-CXqCXmZU.js   147.30 kB │ gzip: 49.35 kB
✓ built in 526ms
```

Real daemon (`python -m meshdeck --data-dir /tmp/md-store-demo --port 8591`):

```
$ curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8591/api/v1/status | python3 -m json.tool
{
    "version": "0.1.0", "mode": "basic", "rns_running": true,
    "transport_enabled": false,
    "propagation_hosting": false,
    "propagation_node_hash": "b2a573293bf1744899ac58f05bba5207",
    "propagation_store_bytes": null,
    "propagation_storage_limit_mb": 256,
    "propagation_storage_limit_bytes": 256000000,
    "page_cache_bytes": 0,
    "page_cache_entries": 0,
    "page_cache_max_bytes": 67108864
}

PUT /api/v1/settings {"propagation_storage_limit_mb": "128"}  → 400
  {"ok": false, "error": {"code": "invalid_propagation_storage_limit_mb", …}}
PUT /api/v1/settings {"propagation_storage_limit_mb": 128.5}  → 400
PUT /api/v1/settings {"propagation_storage_limit_mb": 20000}  → 400
PUT /api/v1/settings {"propagation_storage_limit_mb": 128}    → 200
PUT /api/v1/settings {"propagation_storage_limit_mb": 0}      → 200  (unlimited)
PUT /api/v1/settings {"page_cache_max_bytes": -5}             → 400
  {"ok": false, "error": {"code": "invalid_page_cache_max_bytes", …}}
DELETE /api/v1/page_cache → {"cleared": 1, "page_cache_bytes": 0,
                             "page_cache_entries": 0, "page_cache_max_bytes": 67108864}
```

Settings UI DOM text (headless Chromium, advanced mode, propagation hosting on,
1.2 MB of cached pages):

```
Host for others (propagation node)
  Host a propagation node            [x]
  Your propagation node address …    [Copy]
  Keep this machine online. …
  Store usage: 0 B of 512.0 MB
  Store limit (MB, 0 = unlimited)    [ 512 ] [Save]
  LXMF removes the oldest messages once the store is over this limit; it
  checks about every two minutes.
  (after an invalid 20000: "Enter a whole number from 0 to 10240.")
  (after Save: "Storage limit saved." and the usage line shows 512.0 MB)

Storage
  Page cache: 1.2 MB of 64.0 MB
  Pages you visit are cached so you can still read them when a node goes
  offline. The oldest pages are dropped first when the cache is full.
  [Clear cache]
  (after clearing: "Page cache: 0 B of 64.0 MB" + "Cache cleared — 1 page removed.")

CONSOLE ERRORS: none
```

Screenshots captured this session (scratch copies, not committed):
`/tmp/settings-storage.png` (both cards), `/tmp/settings-storage-full.png`,
`/tmp/settings-storage-after-save.png`. They were produced with a one-off
Playwright install in `/tmp/pw`; no project dependency was added.
