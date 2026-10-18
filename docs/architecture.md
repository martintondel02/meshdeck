# MeshDeck architecture

This is the condensed version of [BUILD_PLAN.md §5](../BUILD_PLAN.md#5-architecture),
updated to match the code. It is meant to be read before changing anything that
touches RNS, threads, the database or the restart path.

The short version: one process, one asyncio loop on the main thread, RNS and
LXMF running their own worker threads, and a single event bus bridging the two.
Everything else follows from that.

## 1. Process and thread model

MeshDeck is a local daemon. It serves the web UI and the REST/WebSocket API from
the same aiohttp application and owns its own Reticulum instance — it does not
start or attach to `rnsd`. The generated config sets `share_instance = No` and
lives in `<data-dir>/reticulum/config`, so the user's `~/.reticulum` is never
read or written.

```
┌────────────────────────────── main thread ───────────────────────────────┐
│                                                                          │
│  asyncio event loop                                                      │
│    ├── aiohttp server: REST /api/v1, WS /ws, static frontend             │
│    ├── CoreService: lifecycle + business logic                           │
│    ├── EventBus._run: drains the queue, awaits subscribers               │
│    ├── announce loop (periodic self-announce)                            │
│    ├── pending-message poll (outbound state fallback)                    │
│    └── restart watcher (waits for restart_requested)                     │
│                                                                          │
└───────────────▲───────────────────────────────────┬──────────────────────┘
                │ loop.call_soon_threadsafe          │ direct calls
                │ (EventBus.publish_from_thread)      │ (RNS is thread-safe
                │                                     │  for these)
┌───────────────┴────────────────┐   ┌──────────────▼──────────────────────┐
│ RNS worker threads             │   │ LXMF router threads                 │
│ announces, Link jobs,          │   │ outbound queue, stamp mining        │
│ interface I/O                  │   │                                     │
└────────────────────────────────┘   └─────────────────────────────────────┘
```

Thread families and who may touch what:

| Thread | Runs | May touch |
|---|---|---|
| Main thread / asyncio loop | aiohttp handlers, `CoreService`, EventBus subscribers, DB repositories | Everything, but never block it on a Link or a long RNS wait |
| RNS worker threads | announce handlers, Link request/response callbacks, transfer progress | Only thread-safe primitives and `EventBus.publish_from_thread` |
| LXMF router threads | outbound sending, stamp proof-of-work, propagation sync | Same as RNS threads |

The frontend is static files (`frontend/dist`) served by the same aiohttp app.
There is no separate frontend server in production; Vite is only used to build
those files.

### Main components

| Module | Responsibility |
|---|---|
| `meshdeck/__main__.py` | CLI parsing, startup banner, restart supervisor (`os.execv`) |
| `meshdeck/config.py` | `AppPaths`, token creation, `SettingsStore` over SQLite |
| `meshdeck/rns/config_gen.py` | Pure `render_config(settings)` + interface validation |
| `meshdeck/rns/stack.py` | `RnsStack`: writes config, pre-validates it, constructs `RNS.Reticulum` |
| `meshdeck/rns/identity.py` | Load-or-create the RNS identity file (mode `0600`) |
| `meshdeck/chat/router.py` | `ChatRouter`: LXMF send/receive, attachments, stamps, delivery status |
| `meshdeck/chat/peers.py` | Announce handler for `lxmf.delivery`, display-name decoding |
| `meshdeck/pages/storage.py`, `files.py` | Page CRUD and shared-file storage with size caps |
| `meshdeck/pages/hosting.py` | `PageHost`: `nomadnetwork.node` destination, `/page/`, `/file/` |
| `meshdeck/pages/client.py` | Blocking `RNS.Link` fetches (pages and files), progress callbacks |
| `meshdeck/core/service.py` | `CoreService`: the facade the API talks to; owns lifecycle and persistence |
| `meshdeck/core/events.py` | `EventBus`: the only bridge from RNS threads into asyncio |
| `meshdeck/storage/*` | One SQLite connection, append-only migrations, repositories (including the page cache) |
| `meshdeck/api/server.py` | aiohttp routes, bearer auth, WebSocket, static UI |

## 2. Startup and shutdown order

`CoreService.start()` is explicit about ordering because several steps depend on
the previous one:

1. Create/open the SQLite database and run migrations (`storage/db.py`).
2. Bind the `EventBus` to the running loop and start its consumer task.
3. Load or create the identity (`RNS.Identity.from_file` / `to_file`).
4. Write and validate the Reticulum config, then construct `RNS.Reticulum`
   **on the main thread** (`rns/stack.py`).
5. Construct `LXMF.LXMRouter` **on the main thread** (`chat/router.py`), register
   the delivery identity and callbacks.
6. If a propagation node is configured, sync stored messages.
7. Register the LXMF peer announce handler and the `nomadnetwork.node` announce
   handler.
8. Start page hosting, announce ourselves, then start the periodic announce and
   pending-message poll tasks.
9. `__main__.amain` starts the aiohttp server, prints the tokenised URL and
   starts the restart watcher.

Shutdown is best-effort and roughly reverse: cancel the background tasks,
deregister the LXMF announce handler, stop the EventBus, drop the `RnsStack`
reference, close the database. RNS has no clean public shutdown for an in-process
instance in this version, so the process itself is the real teardown.

## 3. The EventBus bridge

`meshdeck/core/events.py` is deliberately small. It exists so that RNS threads
never have to know about asyncio.

- `EventBus.bind(loop)` captures the loop and creates the queue; `start()` runs
  one consumer task.
- `publish(type, data)` is for code already on the loop thread.
- `publish_from_thread(type, data)` is for RNS/LXMF callbacks. It calls
  `loop.call_soon_threadsafe()` and nothing else.
- The consumer awaits each subscriber in turn. A subscriber that raises is
  logged and does not kill the bus. Subscribers may be sync or async.
- The queue is unbounded. Do not publish per packet or per byte; throttle
  progress events (the transfer emitter does this).

Current event types, for orientation (grep `publish` in `meshdeck/` for the
authoritative list): `peer_announced`, `peer_added`, `peer_updated`,
`node_announced`, `message_received`, `message_state`, `settings_updated`,
`restart_scheduled`, `transfer_progress`, `transfer_complete`, `transfer_failed`.

The WebSocket layer subscribes to the same bus and forwards each event as
`{"type": "event", "event": ..., "data": ...}` after the `{"type": "hello"}`
frame. REST handlers never push events directly to sockets.

### The rules that make this safe

1. **Never call asyncio APIs from an RNS callback.** No `get_running_loop()`, no
   `await`, no `asyncio.Queue` access. Use `publish_from_thread`.
2. **Never touch the database from an RNS callback.** Publish an event and let
   the persistence subscriber do the write on the loop.
3. **Construct `RNS.Reticulum` and `LXMF.LXMRouter` on the main thread only.**
   Both install SIGINT/SIGTERM handlers on construction, which Python only
   allows on the main thread. Do not move them into `asyncio.to_thread`.
4. **Blocking RNS operations go through `asyncio.to_thread`.** Link
   establishment, `link.request` and propagation sync are blocking; call them
   from a worker thread, then hand results back through the loop.
5. **A callback that raises must not escape.** Wrap RNS callbacks in
   `try/except`, log, and return. An exception in an announce handler is an
   outage in a thread you do not control.

## 4. Request and event flows

### Sending a message

```
UI POST /api/v1/messages
  → server._send_message (loop)
  → CoreService.send_message (loop)
  → ChatRouter.send (loop): build LXMessage, pack(), handle_outbound
  → SQLite row state=sending
  → LXMF worker thread sends it
  → delivery/failed callback (LXMF worker thread)
  → EventBus.publish_from_thread("message_state", ...)
  → loop persists state=delivered and forwards the event over /ws
```

The outbound path also keeps a per-message pending map and a two-second poll as
a fallback, because a callback can be missed; the poll only moves a message
forward, never backward.

### Browsing a page or downloading a node file

```
UI GET /api/v1/browse/{hash}/{path}
  → CoreService.browse_page (loop)
  → normalize_page_path (REST passes paths without the leading slash)
  → asyncio.to_thread(fetch_page, ..., progress_cb=...)
      → RNS.Link + link.request on a worker thread
      → progress_cb fires on an RNS thread
          → CoreService emits transfer_progress via publish_from_thread
  → result returned to the loop, transfer_complete emitted, content returned
```

`fetch_path` guards the user callback so a raising progress callback cannot
abort the transfer. File downloads emit a SHA-256 with the completion event.
Page paths must be normalised exactly once; see the `{path:.+}` pitfall in
BUILD_PLAN §14.

`CoreService.browse_page` also consults `meshdeck/storage/page_cache.py`: a
fresh cached page answers without opening a Link, a successful live fetch is
cached, and if the node is unreachable the last saved copy is returned with
`stale=True` and the fetch error. `?refresh=1` forces a live fetch. The cache is
bounded (4 MiB per entry, 500 rows, 30 days) and pruned once at startup.

## 5. Database and migrations

- One `sqlite3.Connection` for the process (`check_same_thread=False`), opened
  with WAL and foreign keys enabled. No ORM.
- Migrations are a list of `(target_user_version, sql)` tuples in
  `meshdeck/storage/db.py`. `Database.migrate()` reads `PRAGMA user_version` and
  applies every tuple newer than the current version inside a transaction, then
  sets `user_version`.
- Migrations are **append-only and forward-only**. Never edit a tuple that has
  shipped and never assume a downgrade exists. To add a table or index: append a
  new tuple, add a repository module, and update the expectations in
  `tests/unit/test_db.py`.
- The current head is whatever the last tuple says; do not hardcode the number
  in a doc. v1 created settings/peers/messages, and later migrations added the
  node table and other features.
- Repositories are plain functions taking the `Database`. They run on the loop
  thread. The event-persistence subscriber holds `CoreService._db_lock` while
  writing; keep writes on that path rather than opening a second writer.

## 6. Restarting: the `os.execv` supervisor

`RNS.Reticulum` is a never-cleared process singleton in this `rns` version.
Creating a second instance in the same process is not supported, and tearing
the first one down cleanly is not exposed. Network configuration changes are
therefore applied by re-executing the process.

```
UI changes interfaces → PUT /api/v1/settings (persisted to SQLite;
                            the response sets restart_required=true)
UI POST /api/v1/restart
  → CoreService.request_restart()
      render config from current settings into a temp file
      validate_interface_config() → 400 invalid_config if it cannot boot
      EventBus.publish("restart_scheduled")
      loop.call_later(0.4, restart_requested.set)   # let the HTTP response finish
  → __main__.restart_watch wakes up
      server.stop(); service.stop()
      os.execv(sys.executable, [python, "-m", "meshdeck",
                                "--data-dir", <dir>, "--host", <host>,
                                "--port", <resolved port>])
```

Notes:

- Settings are written to SQLite before the restart request, so the new process
  re-reads them.
- The CLI passes the **resolved** port (after auto-increment), so a restart does
  not silently move to a different port.
- The config is validated before re-exec. RNS calls `os._exit(255)` on interface
  configuration errors, so a bad config must be rejected while we can still
  return a readable API error.
- The new process is a fresh PID with the same data directory; open browser
  connections reconnect to the WebSocket on their own.

## 7. Static UI and packaging

- `__main__.resolve_static_dir()` first looks for the UI inside a PyInstaller
  bundle (`sys._MEIPASS/frontend/dist`), then for `frontend/dist` relative to
  the package. If neither exists, the API still runs and `/` returns a minimal
  page.
- Authentication middleware protects `/api/*` and `/ws`; static assets are
  served without a token because they contain no user data. All data access is
  behind the token.
- The PyInstaller spec (`packaging/meshdeck.spec`) embeds `frontend/dist` and
  force-imports every `RNS.Interfaces.*` module. Reticulum's star import cannot
  enumerate a frozen package directory; without the shim the binary dies at
  boot with `NameError: BackboneInterface is not defined`.

## 8. Where to add a feature

A feature usually crosses these layers. Touch them in this order:

1. **Storage (only if new state).** Add a migration tuple in
   `meshdeck/storage/db.py`, a repository module in `meshdeck/storage/`, and a
   unit test. Do not put business logic in the repository.
2. **Domain module.** Put protocol work in the relevant package (`chat/`,
   `pages/`, `rns/`) and keep it synchronous where RNS is synchronous. If it
   runs a Link or a long RNS wait, it is blocking and will be called through
   `asyncio.to_thread`.
3. **`CoreService`.** Add the use case here: validation, orchestration, DB
   writes, event publishing. API handlers should stay thin and call one service
   method.
4. **API + events.** Register the route in `meshdeck/api/server.py` (specific
   routes before catch-alls), validate input in `api/schemas.py`, and publish a
   bus event for anything the UI must see live. Update the WebSocket command
   handler only if the action genuinely belongs there.
5. **Frontend.** Component in `frontend/src/components/`, state in
   `lib/stores.ts`, HTTP in `lib/api.ts`, event handling in `lib/ws.ts`, and
   explanatory copy (tooltips/glossary) in `lib/copy/tooltips.ts`. Add guide
   text in `Guides.svelte` and mirror it under `docs/guides/`.

Then add tests at the cheapest level that exercises the behavior: unit for pure
logic, `tests/api` for the REST surface, `tests/integration` for real RNS
Links/subprocesses, Vitest for frontend logic. Finish by updating
`CHANGELOG.md`, `BUILD_PLAN.md` §15 and the phase log.

### Before you start

- Read [BUILD_PLAN.md §2](../BUILD_PLAN.md#2-locked-decisions) for the decisions
  that are not up for renegotiation.
- Read [BUILD_PLAN.md §14](../BUILD_PLAN.md#14-pitfalls-learned-from-ecosystem-code--manual-reread-before-phases)
  for the traps that have already cost time.
- Advanced mode is a display filter, not a security boundary. Backend caps,
  validation and authentication apply in both modes.
- Never reimplement RNS/LXMF. If the official API cannot do it, document the
  limitation or raise it upstream; do not hand-roll crypto, announces or wire
  formats.
