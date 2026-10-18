# Phase 7.1 — bounding the remaining stores (handoff)

> **Status:** implemented 2026-10-19, base `v0.1.1` (`31d8fbb`).
> This file is the honest record; anything marked *unverified* was not run.

## Settings contract

All values are live-applied, validated **strictly** in `PUT /settings`
(out-of-range/non-integer/bool → `400 invalid_<key>`, never clamped) and
returned by `GET /settings`.

| Setting | Default | Accepted | `0` means | Unit |
|---|---|---|---|---|
| `attachment_storage_max_mb` | 512 | `0 … 102400` | unlimited | MiB |
| `attachment_retention_days` | 0 | `0 … 3650` | keep forever | days |
| `shared_storage_max_mb` | 1024 | `0 … 102400` | unlimited | MiB |
| `pages_storage_max_mb` | 256 | `0 … 10240` | unlimited | MiB |
| `message_retention_days` | 0 | `0 … 3650` | keep forever | days |
| `log_max_mb` | 10 | `0 … 1024` | unlimited | MiB |
| `page_cache_max_bytes` (6.3) | 67108864 | `0 … 1073741824` | unlimited | bytes |
| `propagation_storage_limit_mb` (6.3) | 256 | `0 … 10240` | unlimited | decimal MB (LXMF) |

## What each bound does

* **Chat attachments** (`storage/attachments.py`): blobs under
  `files/<peer>/<msg>/`. The byte cap evicts oldest-first (mtime); the age
  policy removes blobs older than N days. Runs at boot, after each inbound
  attachment (on the RNS thread; files only, never asyncio/DB/HTTP) and when
  the settings are saved. Message rows are never deleted. `GET
  /messages` adds `attachments_available: [bool]` for inbound messages, the
  download route returns `404 attachment_pruned` when metadata still lists
  the index, and `ChatView` renders a non-clickable tombstone.
* **Node-shared files / hosted pages** (`pages/files.py`,
  `pages/storage.py`): never pruned. `save()`/`write()` refuse a new write
  when `used - replaced + new > cap`; existing oversized stores stay. API
  codes: `shared_storage_full`, `pages_storage_full` (400).
* **Message history** (`storage/messages.py`): `prune_older_than(cutoff)` is a
  single bounded `DELETE`; peers/nodes are untouched. Runs at boot and in a
  24 h task (`MESSAGE_PRUNE_INTERVAL_SECONDS`). Saving a non-zero retention
  prunes immediately (explicit user action). **No automatic VACUUM** — a
  blocking VACUUM on a large history is not cheap/safe to run automatically;
  SQLite reuses freed pages and compaction stays an operator action.
* **Logs** (`util/logs.py`): `prepare_logging()` runs in `main()` before
  `CoreService.start()`/RNS. It reads `log_max_mb` from SQLite, renames
  `logs/{meshdeck,reticulum}.log` to `.1` when over the cap (replacing the
  previous backup), then a `FileHandler` is attached to MeshDeck's own log.
  Only the two managed files in the data dir are touched.

## API / status surface

`GET /api/v1/status` gains (all byte limits are bytes; `_days` are integers):

```
attachment_bytes, attachment_files,
attachment_storage_max_bytes, attachment_retention_days,
shared_bytes, shared_files, shared_storage_max_bytes,
pages_bytes, pages_entries, pages_storage_max_bytes,
message_count, message_retention_days,
log_bytes, log_max_bytes
```

`PUT /api/v1/settings` additionally returns `effects` with the side effects of
that save (`attachment_removed`, `attachment_freed_bytes`,
`messages_pruned`), so the UI can report what the explicit policy removed.

## Tests

* `tests/unit/test_storage_bounds.py` — usage/prune boundaries for
  attachments (age, byte cap, unlimited, symlink escape, empty dirs), shared
  and page caps (refusal, overwrite accounting, pre-existing oversized
  stores), message retention (peers kept), log rotation (one `.1`, unlimited,
  corrupt setting fallback) and status/settings shape for every new key.
* `tests/api/test_storage_api.py` — one real daemon (real RNS, real HTTP,
  loopback) exercising every invalid numeric value, `shared_storage_full`,
  `pages_storage_full`, attachment `404 attachment_pruned` + tombstone
  metadata, message retention, and usage changes in `/status`.

## Real-daemon probe (run this session)

Temp data dir, `connect_autointerface=False`, `log_max_mb=1`, two 2 MiB log
files written before boot:

```
$ ls -l "$DATA/logs"
-rw-r--r-- 672      meshdeck.log
-rw-r--r-- 2097152  meshdeck.log.1
-rw-r--r-- 2097152  reticulum.log.1

$ GET /status (before write)  shared_bytes=0 shared_files=0
$ POST /shared 64 KiB         -> 201 {"size": 65536}
$ GET /status (after write)   shared_bytes=65536 shared_files=1
```

Rotated backups are exactly the oversized originals; a fresh `meshdeck.log`
was recreated by the new file handler. `/status` usage changed after a real
write.

## Verified vs unverified

| Item | Status |
|---|---|
| Every new setting rejects string/float/bool/negative/over-max via `PUT /settings` (unit + real HTTP) | **verified** |
| Attachment age/byte pruning, message rows kept, tombstone + `attachment_pruned` 404 | **verified** |
| Shared/pages cap refusal + overwrite accounting + existing oversized stores | **verified** |
| Message retention keeps peers/nodes; boot + daily task wired | **verified** (daily task not waited out; method exercised directly) |
| Log rotation of both managed logs with a real 2 MiB file | **verified** |
| UI: all usage/limits, new page-cache field, retention warnings, aria-live notes | **verified by `svelte-check`/build and browser DOM probe** — see 7.3 |
| Automatic VACUUM after message pruning | **not implemented (deliberate)** — documented above |
| Disk-full/IO-error handling during a write | **unverified** — same as Phase 6.3 |
