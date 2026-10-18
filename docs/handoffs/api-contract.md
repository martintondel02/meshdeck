# Handoff — Phase 6.1: API/route contract tests

- **Branch:** `work/api-contract` (base `aedfe8a`, v0.1.0 docs tip)
- **Owned files:** `tests/api/test_routes.py` (new), this document.
- **Not touched:** `meshdeck/`, `frontend/`, `tests/integration/`,
  `tests/api/test_api.py`, `CHANGELOG.md`, `BUILD_PLAN.md`, `NEXT_STEPS.md`,
  `README.md`.

## Why this exists

Two real, user-visible bugs shipped with a green test suite because every
existing test called `CoreService` directly and never exercised the aiohttp
routes the UI actually fetches:

1. **`{path:.+}` drops the leading slash** (BUILD_PLAN §14.21). The UI asks for
   `/api/v1/browse/<hash>/page/index.mu`; aiohttp hands `browse_page` the
   string `page/index.mu`. The pre-fix naive check
   `if not path.startswith("/page/")` built `/page/page/index.mu`, which is not
   a registered RNS request handler — every UI page fetch sat until the 25 s
   link timeout while the service-level integration tests stayed green.
   Fixed in `meshdeck/pages/client.py:normalize_page_path` (unit-tested only).
2. **aiohttp matches routes in registration order** (BUILD_PLAN §14.20). The
   page catch-all `/browse/{hash}/{path:.+}` swallows
   `/browse/{hash}/file/<name>` unless the file route is registered first.
   `server.py` carries the comment; nothing exercised it over HTTP.

These tests are deliberately *not* service-level: each one boots the real CLI
(`python -m meshdeck --data-dir <tmp> --port <free>`), reads `<tmp>/token`, and
speaks HTTP with the real bearer token.

## What was added

`tests/api/test_routes.py` — 8 integration tests plus a hermetic harness.

Harness properties:

- **Pre-seeded settings, no in-process service.** `seed_settings()` writes the
  SQLite `settings` table through the same `SettingsStore` the daemon reads
  (mirrors `tests/integration/node.py`), before the subprocess boots.
- **Real CLI subprocess** per node: `sys.executable -m meshdeck` (the venv
  interpreter locally, the installed interpreter in CI). Logs go to
  `<data>/daemon.log`, included in assertion messages on failure.
- **Readiness** = `<data>/token` exists *and* an authenticated
  `GET /api/v1/status` returns 200 with `rns_running: true`.
- **Two nodes** use a loopback TCP pair through the structured `interfaces`
  setting: A is `tcp_server` (`listen_ip = 127.0.0.1`), B is `tcp_client`
  (`target_host = 127.0.0.1`). No AutoInterface/IPv6, no host network.
- **Random free ports** from the OS for both the RNS interface and each HTTP
  port; temp data dirs via `tmp_path_factory`.
- **Discovery is explicit**: A re-announces via `POST /api/v1/announce` until B's
  `/nodes` contains A's node destination and B's `/peers` contains A's LXMF
  destination (A's boot announce can precede B's TCP connection).
- **Clean shutdown is asserted**: both daemons are SIGTERM'd in fixture teardown
  and must exit 0 (`RNS`' SIGTERM handler exits 0).
- One module-scoped pair keeps the whole file at ~3.4 s.

### Covered contract

| Test | Route(s) | Contract asserted |
|---|---|---|
| `test_browse_page_route_keeps_exact_node_path` | `GET /browse/{hash}/{path:.+}` | 200; `path == "/page/index.mu"` exactly (live **and** cached re-read); content matches the page seeded in A's pages dir; `served_from_cache` flips true on the second request |
| `test_browse_missing_page_returns_page_not_found` | `PUT/DELETE /pages/{name}`, `GET /browse/...` | create page → delete page → peer browse returns **200** with the `>Page not found` body (no 500, no 25 s hang) |
| `test_browse_file_route_not_swallowed_by_page_catchall` | `GET /browse/{hash}/file/{name:.+}` | exact bytes, `Content-Disposition: attachment; filename="payload.bin"`, SHA-256 match |
| `test_shared_upload_list_download_delete` | `POST/GET /shared`, `GET/DELETE /shared/{name}` | real multipart upload → 201; list; download bytes + disposition + SHA; missing file → **400 `not_found`** (documented client error, not 200/500); delete → 200; second download → 400 `not_found` |
| `test_attachment_download_after_file_message` | `POST /files`, `GET /messages`, `GET /attachments/{peer}/{msg}/{index}` | a real LXMF file message B→A is persisted with attachment metadata; A serves the bytes with `filename="contract-attachment.bin"`, SHA-256 match; unknown index → 404 `not_found` |
| `test_new_routes_require_bearer_token` | every route above + `/nodes`, `/node`, `PUT /settings` | all return **401 `unauthorized`** without the token |
| `test_nodes_and_node_agree` | `GET /node`, `GET /nodes` | A's own `/node` (hash, `Contract Node`, `serve_pages`) appears in B's `/nodes`; B does not list its own node |
| `test_settings_route_rejects_invalid_delivery_method` | `PUT /settings` | invalid value → 400 `invalid_delivery_method`; valid value → 200 |

Deliberately not duplicated: the offline single-daemon acceptance flow in
`tests/api/test_api.py` (WS auth/ping, peers, messages validation, page CRUD,
propagation toggle) stays as-is.

## How to run

```bash
.venv/bin/python -m pytest tests/api/test_routes.py -m integration -q
.venv/bin/python -m pytest tests/api -m integration -q      # + test_api.py
.venv/bin/ruff check meshdeck tests
```

## Verification (all run in this worktree on the merge candidate)

Baseline before writing code:

```
$ .venv/bin/python -m pytest tests/unit -q
48 passed in 0.44s
$ .venv/bin/ruff check meshdeck tests
All checks passed!
$ cd frontend && pnpm run check && pnpm run test && pnpm run build
svelte-check found 0 errors and 0 warnings
Tests  37 passed (37)
✓ built in 576ms
```

New tests (green):

```
$ .venv/bin/python -m pytest tests/api/test_routes.py -m integration -q --durations=10
........                                                                 [100%]
2.31s setup  tests/api/test_routes.py::test_browse_page_route_keeps_exact_node_path
0.58s teardown tests/api/test_routes.py::test_settings_route_rejects_invalid_delivery_method
0.26s call   tests/api/test_routes.py::test_attachment_download_after_file_message
8 passed in 3.36s
```

Full API suite:

```
$ .venv/bin/python -m pytest tests/api -m integration -q
9 passed, 3 warnings in 3.45s
```

Existing two-node/restart/propagation suite still green (no source changes):

```
$ .venv/bin/python -m pytest tests/integration -m integration -q
10 passed in 73.20s (0:01:13)
```

Lint:

```
$ .venv/bin/ruff check meshdeck tests
All checks passed!
```

### Regression demonstration (old bug class must fail)

Temporarily replaced `path = normalize_page_path(path)` in
`meshdeck/core/service.py:browse_page` with the pre-fix logic
(`if not path.startswith("/page/"): path = "/page/" + path`):

```
$ .venv/bin/python -m pytest tests/api/test_routes.py::test_browse_page_route_keeps_exact_node_path -m integration -q
F                                                                        [100%]
>           assert status == 200, f"browse page failed with HTTP {status}: {raw!r}"
E           AssertionError: browse page failed with HTTP 400: b'{"ok": false, "error": {"code": "link_timeout", "message": "request failed validation"}}'
E           assert 400 == 200
FAILED tests/api/test_routes.py::test_browse_page_route_keeps_exact_node_path
1 failed in 27.89s
```

Restored with `git checkout -- meshdeck/core/service.py`; re-ran the green suite
above (8 passed). `git status` showed only the new test file.

## Known limits / honestly unverified

- **A page that was never registered still times out.** `PageHost` registers
  one exact RNS request handler per known page; there is no wildcard. A request
  for a path with no handler gets no response, so `browse_page` raises
  `link_timeout` after 25 s and the route returns **400 `link_timeout`**. I
  verified this with a throwaway two-node probe (not part of the suite):
  `GET /browse/<A>/page/never-registered.mu -> HTTP 400 in 25.0s
  {"code":"link_timeout"}`. The suite asserts the reachable
  `>Page not found` case instead (handler registered, file deleted); making
  unknown paths return a fast not-found would be a product change, not a test
  change.
- **WebSocket `/ws` contract is not covered here** (it already has auth/ping/
  unknown-command coverage in `test_api.py`); this file is HTTP-route focused.
- **No browser/E2E replay.** The routes are the ones `frontend/src/lib/api.ts`
  and `stores.ts:attachmentUrl()` build, but the UI itself was not re-run in a
  browser.
- `POST /api/v1/restart` is not exercised (it re-execs the daemon; the CLI
  restart path has its own integration test).
- CI's `integration` job is `continue-on-error: true`, so a red run there is
  visible but not blocking by design.

## Changelog-ready entry

```markdown
### Added (Phase 6 — test integrity)

- `tests/api/test_routes.py`: HTTP/route contract tests that boot the real
  `python -m meshdeck` CLI (real bearer token, real multipart, two loopback TCP
  nodes) instead of calling `CoreService` in-process. They pin the two bugs
  that slipped through service-level tests: the `{path:.+}` normalisation of
  `/browse/<hash>/page/...` (must request exactly `/page/index.mu`, not
  `/page/page/...`) and route registration order for
  `/browse/<hash>/file/<name>`. Also covers `/shared` multipart
  upload→list→download→delete, `/attachments` after a real file message,
  `/nodes` vs `/node`, `/settings` validation, and 401 on every route without
  the bearer token. `docs/handoffs/api-contract.md` records scope, evidence and
  limits (an unregistered page path still times out by RNS design).
```
