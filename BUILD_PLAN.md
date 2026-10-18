# MeshDeck — Master Build Plan

This is the single source of truth for building MeshDeck. It is written to be
executed top-to-bottom by a builder (human or agent) without re-litigating
decisions. If a section conflicts with reality (API changed, environment
differs), update this file in the same commit that adapts the code.

- **Project:** MeshDeck (working title, rename freely — search/replace
  `meshdeck`/`MeshDeck` when final name is chosen)
- **Goal:** a free, open-source, all-in-one Reticulum application: chat, file
  transfer, page hosting, and server/entrypoint hosting — with a **basic
  mode** (guided, zero jargon) and an **advanced mode** (full control).
- **First milestone:** end-to-end LXMF peer chat daemon with a working local
  web UI.

---

## 1. Context and environment

### 1.1 Ecosystem facts (researched, verified)

- Reticulum (`rns` on PyPI) **1.5.7** and LXMF (`lxmf` on PyPI) **1.2.1** are
  installed in `./.venv` and import cleanly on **Python 3.14.8**.
- Reference app for patterns: MeshChatX (Python aiohttp+WS backend, Vite/TS
  frontend, Electron; 0BSD/MIT, forkable; EOL 2027-01-01). Read it for
  inspiration only: <https://github.com/Quad4-Software/MeshChatX>
- Reticulum manual: <https://reticulum.network/manual/index.html>
- Installed package source (ground truth for API questions):
  - `.venv/lib/python3.14/site-packages/RNS/`
  - `.venv/lib/python3.14/site-packages/LXMF/`

### 1.2 Community note (important)

The Reticulum community has publicly pushed back on fully AI-generated
**reimplementations of the protocol stack** (see "Brandolini's Reference" in
the manual). Our approach avoids that entirely: we **depend on the official
`rns`/`lxmf` packages** and build an application on top — same as NomadNet,
Sideband, and MeshChatX. Do not reimplement wire formats, crypto, or the
transport layer.

### 1.3 Host machine facts

- Python 3.14.8 (`python3`), **no system `pip`** — always use `./.venv`.
  Recreate with: `python3 -m venv .venv && .venv/bin/pip install -e .`
- Node v24.18.0, npm 11.16.0, pnpm 12.3.4 (global), cargo 1.99, git 2.56.
- OS: Linux (Fedora). Paths below use XDG conventions with fallbacks.

---

## 2. Locked decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Codebase | Fresh start (MeshChatX as reference reading) | Basic/advanced mode must shape the architecture; no legacy maintenance burden; LXMF keeps us interoperable |
| 2 | App shell | Browser web app served by the local daemon | Works on desktop + headless servers; desktop wrappers (Tauri/Electron) deferred to Phase 5 |
| 3 | First milestone | Peer chat over LXMF | Exercises identity, announce, discovery, transport — the foundation for everything else |
| 4 | Backend | Python ≥3.11, `asyncio` + `aiohttp` + `websockets` (aiohttp WS is fine; pick ONE: **aiohttp web + aiohttp WS**) | Same family as ecosystem apps; single HTTP+WS server in one process |
| 5 | Protocol libs | `rns`, `lxmf` from PyPI, pinned | Reference implementation, maintained |
| 6 | Storage | SQLite via stdlib `sqlite3` (raw SQL, no ORM) | Zero-dep, inspectable, matches MeshChatX's hard-won choice |
| 7 | Config ownership | MeshDeck manages its **own** RNS configdir (`<data>/reticulum/`), generated from our settings store. Never touches `~/.reticulum`, `share_instance = No` | A broken system rnsd or user's own experiments must not break MeshDeck, and vice versa |
| 8 | Frontend | Vite + **Svelte 5** + TypeScript + Tailwind CSS v4 | Fast to build, small output, beginner-friendly |
| 9 | DB migrations | Hand-rolled `PRAGMA user_version` migrations | No ORM → no migration framework needed |
| 10 | License | MIT for our code (see LICENSE) | Free, permissive, compatible with ecosystem norms |
| 11 | Lint/format | `ruff` (Python), `prettier` (frontend) | Fast, zero-config-ish |
| 12 | Testing | `pytest` + `pytest-asyncio`; subprocess-based integration harness (§13) | RNS module state is process-global → isolation via subprocesses |
| 13 | Copy/docs in app | Centralized copy registry keyed per screen + markdown guides rendered in-app | Guarantees "documented with built-in guides/tooltips" is structural, not aspirational |

Dependency policy: add a dependency only when the alternative is clearly
worse, and prefer stdlib. Approved initial set: `rns`, `lxmf`, `aiohttp`,
`platformdirs`, `msgpack` (already an LXMF dep). Dev: `pytest`,
`pytest-asyncio`, `ruff`.

---

## 3. Out of scope (recorded so nobody drifts)

Deferred, with intended phase noted: voice calls (LXST, Phase 6+), maps,
Android, plugin system, RRC relay chat, remote/headless multi-user mode,
Electron/Tauri shells (Phase 5), propagation-node hosting (Phase 4),
browsing others' NomadNet pages (Phase 3 stretch), I2P interface wizard
(Phase 4), blackhole list management UI (Phase 4).

Explicitly never, without a new decision record: reimplementing RNS/LXMF,
touching `~/.reticulum` silently, telemetry of any kind.

---

## 4. End-state feature matrix (basic vs advanced)

| Feature | Basic mode | Advanced mode |
|---|---|---|
| Create/import identity | guided wizard, "your address" explained | + raw key export, multiple identities |
| Connect to network | one click (AutoInterface + suggested public entrypoints) | + full interface editor (all RNS interface types), IFAC, announce rate control |
| Chat (LXMF DM) | ✔ full | ✔ + raw fields, stamp costs, propagation settings |
| Contacts | auto-named from announce, rename | + identities, trust/block, display-name resolution rules |
| File transfer | drag & drop into chat | + RNS `Resource` large-file transfer over Links |
| Message history | ✔ searchable | + export, retention rules |
| Host a page/site | "Create my page" wizard (visual micron editor with live preview) | + raw micron editing, files, node settings |
| Infrastructure | hidden | transport node toggle, public entrypoint wizard (BackboneInterface + announce-rate guidance), propagation node |
| Diagnostics | "connection doctor" (friendly status) | announce table, path table, rnpath/rnprobe equivalents, live log viewer |
| Settings | 5 friendly toggles | full config tree + raw config text editor |
| Guides/tooltips | on everything | same, plus technical depth |

The mode is a **display filter, not a security boundary**: advanced features
are gated by capability flags in settings; the backend always enforces
safety limits (announce rates, file size caps) regardless of mode.

---

## 5. Architecture

### 5.1 Process and threading model (the one rule that matters)

RNS runs its **own worker threads**. All RNS/LXMF callbacks (announce
received, message delivered, delivery state changes) fire on RNS threads —
never on the asyncio loop.

```
RNS worker threads ──► EventBus.publish_from_thread() ──► asyncio.Queue ──► loop task ──► WS clients + DB writes
asyncio loop (aiohttp) ──► commands ──► CoreService methods (call RNS directly; RNS is thread-safe for these)
```

Rules for the builder:
1. **Never** call asyncio APIs directly from an RNS callback. Capture the
   running loop once and use `loop.call_soon_threadsafe(...)`.
2. RNS calls from the asyncio loop are fine (RNS internals are locked).
   Avoid blocking calls (Link establishment) on the loop — run those in
   `asyncio.to_thread` / an executor.
3. SQLite: one connection, `check_same_thread=False`, guarded by an
   `asyncio.Lock`; or a single dedicated "db writer" task draining a queue.
   Prefer the queue writer — simplest mental model.

### 5.2 Components (backend package `meshdeck/`)

| Module | Responsibility |
|---|---|
| `meshdeck/__main__.py` | CLI entry: `python -m meshdeck [--data-dir X] [--port P] [--open-browser]` |
| `meshdeck/config.py` | Data-dir resolution (`platformdirs`), settings store (SQLite), first-run detection, auth-token generation/read |
| `meshdeck/rns/config_gen.py` | Renders `<data>/reticulum/config` from settings (interfaces, transport flag, logging). Pure function: settings dict → config text. Unit-test it heavily |
| `meshdeck/rns/stack.py` | `RnsStack`: owns `RNS.Reticulum(configdir=...)`, starts/stops with app, exposes interface list/status, restarts on config change |
| `meshdeck/rns/identity.py` | Load-or-create `RNS.Identity` at `<data>/identity` (0600), never logged; display-name management |
| `meshdeck/chat/router.py` | Wraps `LXMF.LXMRouter`: `register_delivery_identity`, delivery/announce callbacks → EventBus; `send(peer_hash, content, ...)`; outbound state tracking via per-message callbacks |
| `meshdeck/chat/peers.py` | Peer discovery: announce handler with `aspect_filter = "lxmf.delivery"`, decode display names (see §11), upsert into DB, announce self on start + on interval + on demand |
| `meshdeck/storage/db.py` | SQLite open/migrate (`PRAGMA user_version`), schema in §9 |
| `meshdeck/storage/messages.py` | Message CRUD, pagination queries, state updates |
| `meshdeck/core/events.py` | EventBus: `publish_from_thread(event_type, data)` → fan-out to WS subscribers + DB writer queue |
| `meshdeck/core/service.py` | Facade the API layer calls: `get_status()`, `send_message()`, `list_peers()`, etc. Owns component lifecycle (start/stop in order) |
| `meshdeck/api/server.py` | aiohttp app: REST + `/ws`, static frontend files, auth middleware (§8) |
| `meshdeck/util/hexid.py` | Hash prettifiers (first-8 display, etc.) |

Lifecycle order on start: config → db+migrate → RNS stack → identity → LXMF
router → announce handler + self-announce → API server. Reverse on stop.

### 5.3 Reticulum config strategy

MeshDeck's data dir layout:

```
${XDG_DATA_HOME:-~/.local/share}/meshdeck/
├── meshdeck.db            # SQLite (settings incl. mode, messages, peers, pages)
├── identity               # RNS.Identity private key file, chmod 0600
├── token                  # local API auth token, chmod 0600
├── reticulum/
│   └── config             # GENERATED by meshdeck/rns/config_gen.py
├── lxmf/                  # LXMRouter storagepath
├── files/                 # received attachments (Phase 2)
├── pages/                 # hosted site content (Phase 3)
└── logs/
```

Generated minimal config (basic mode default):

```ini
[reticulum]
  enable_transport = No
  share_instance = No

[logging]
  loglevel = 4

[interfaces]
  [[Local Network]]
    type = AutoInterface
    enabled = yes
```

Advanced mode adds: `[[Public Entrypoint]] type = TCPClientInterface ...`
entries, `enable_transport = Yes` toggle, `[[Hosted Gateway]] type =
BackboneInterface ...` (Phase 4). Always re-render the whole file from
settings; keep a raw-editor escape hatch that stores custom text and skips
generation (with a visible warning).

### 5.4 Example event flow (send a message)

1. UI: POST `/api/v1/messages {peer_hash, content}`
2. `service.send_message` → build peer OUT destination from recalled
   identity → `LXMF.LXMessage(dest, own_delivery_destination, content, desired_method=DIRECT)`
   → register per-message delivery/failed callbacks → `router.handle_outbound(lxm)`
3. DB writer inserts message row (state=`sending`)
4. LXMF delivery callback (RNS thread) → EventBus → DB update state=`delivered` + WS event `message_state` → UI ticks the checkmark

---

## 6. Repository layout (exact)

```
/
├── BUILD_PLAN.md              # this file
├── README.md  LICENSE  .gitignore
├── pyproject.toml             # hatchling or setuptools backend; deps per §2
├── meshdeck/                  # backend package
│   ├── __init__.py  __main__.py  version.py
│   ├── config.py
│   ├── api/{__init__.py,server.py,schemas.py}
│   ├── core/{__init__.py,events.py,service.py}
│   ├── chat/{__init__.py,router.py,peers.py,messages.py}
│   ├── rns/{__init__.py,config_gen.py,identity.py,stack.py}
│   ├── storage/{__init__.py,db.py,messages.py}
│   └── util/{__init__.py,hexid.py}
├── tests/
│   ├── unit/                  # pure logic: config_gen, db, schemas
│   └── integration/
│       ├── node.py            # standalone script: runs one standalone chat node (used by harness)
│       └── test_two_nodes.py  # spawns 2 subprocesses, asserts delivery
├── frontend/                  # Vite + Svelte + TS + Tailwind
│   ├── src/{App.svelte, main.ts, routes/, components/, lib/copy/}
│   └── package.json  vite.config.ts  ...
├── docs/
│   └── guides/                # markdown guides rendered in-app (EN first)
└── Makefile                   # venv, install, dev, test, lint, build-frontend
```

`rns/` subpackage name inside `meshdeck/` is fine because absolute imports
(`import RNS`) resolve against site-packages first when `meshdeck` is
installed/used as the top package — but to eliminate any shadowing doubt,
name it `meshdeck/rnsx/` if import weirdness ever appears. Default: `rns/`
inside the `meshdeck` package is safe.

---

## 7. Backend module specs (key signatures)

```python
# meshdeck/rns/config_gen.py
def render_config(settings: dict) -> str: ...
# meshdeck/rns/stack.py
class RnsStack:
    def __init__(self, configdir: Path): ...
    def start(self) -> None            # constructs RNS.Reticulum(configdir=...)
    def interfaces(self) -> list[dict] # name, type, online, bitrate...
    def stop(self) -> None
# meshdeck/rns/identity.py
class IdentityManager:
    def load_or_create(self) -> RNS.Identity
    @property
    def hash_hex(self) -> str: ...
# meshdeck/chat/router.py
class ChatRouter:
    def __init__(self, stack, identity, storage: Storage, bus: EventBus): ...
    def start(self) -> None   # LXMRouter(identity=..., storagepath=..., autopeer=True)
                              # router.register_delivery_identity(identity, display_name=...)
                              # router.register_delivery_callback(self._on_delivery)
    def send(self, peer_hash_hex: str, title: str, content: str) -> str  # returns msg hash hex
    def announce(self) -> None
# meshdeck/api/server.py
def create_app(service: CoreService, token: str, static_dir: Path) -> aiohttp.web.Application
```

---

## 8. Local API spec (v1)

**Binding:** `http://127.0.0.1:8570` (fallback: increment until free).
**Auth:** random token at `<data>/token`. REST: `Authorization: Bearer <t>`.
WS: `?token=<t>` query param. Constant-time compare; reject everything else
with 401. The CLI prints the URL with token on start; `--open-browser` opens it.

### REST

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/status` | `{version, mode, rns_running, interfaces[], transport_enabled, uptime}` |
| GET | `/api/v1/identity` | `{hash, display_name, short}` |
| POST | `/api/v1/identity/display_name` | set + re-announce |
| GET | `/api/v1/peers` | list known peers (hash, name, last_seen, nickname, blocked) |
| POST | `/api/v1/peers` | `{hash}` → add by address; `{peer, known, path_requested}` (Phase 2) |
| PATCH | `/api/v1/peers/{hash}` | rename/block |
| GET | `/api/v1/messages?peer={hash}&before={ts}&limit=50` | paginated history |
| POST | `/api/v1/messages` | `{peer, content, title?}` → `{hash, state}` |
| POST | `/api/v1/files` | multipart `peer` + `file` (+`caption`) → `{hash, state}` (Phase 2) |
| GET | `/api/v1/attachments/{peer}/{msg}/{index}` | download a stored attachment (Phase 2) |
| GET/PUT | `/api/v1/settings` | settings incl. `mode`, `delivery_method`, `propagation_node_hash` |
| POST | `/api/v1/announce` | re-announce self now |

### WebSocket `/ws`

All frames JSON.

Client→server: `{type:"cmd", id:<n>, cmd:"send_message", data:{...}}`
Server→client ack: `{type:"ack", id:<n>, ok:true, data:{...}}` or
`{type:"error", id:<n>, ok:false, error:{code, message}}`
Server→client events: `{type:"event", event:<name>, data:{...}}` with
`event ∈ peer_announced | peer_added | peer_updated | message_received |
message_state | network_status | interfaces_changed`.

Error codes over REST/WS include: `invalid_hash`, `no_path`, `too_large`,
`no_propagation_node`, `not_found`, `missing_peer`, `invalid_mode`,
`invalid_delivery_method`, `invalid_propagation_node`.

### Attachments (Phase 2 wire format)

Outbound sets `LXMF.FIELD_FILE_ATTACHMENTS (0x05)` to
`[[name_bytes, data_bytes], …]`. Filenames are sanitized before storage:
URL-decode → basename → replace non-`[A-Za-z0-9._-]` → cap 120 chars.
Inbound files land in `<data>/files/<peer_hash>/<msg_hash>/<index>_<name>`.
App cap **1.5 MiB per message**; router inbound `delivery_limit=2048` KB
(LXMF defaults to 1000 KB, and legacy clients enforce ~1 MB inbound —
oversize cross-client sends fail cleanly with state `failed`).

CAREFUL: LXMF **message** hashes are full SHA-256 → **64** hex chars,
unlike destination hashes (32). Mixing them in validators silently breaks
attachment download routes (`is_valid_msg_hash_hex` exists for this).

### Propagation (Phase 2 plumbing, Phase 3 polish)

Settings `delivery_method` (`direct|opportunistic|propagated`) and
`propagation_node_hash` apply live (no restart) via
`ChatRouter.apply_delivery_settings` (`router.set_outbound_propagation_node(bytes)`).
On startup, if a propagation node is configured and recallable,
`request_messages_from_propagation_node(identity)` syncs stored messages.
Stamp costs (proof-of-work for propagated delivery) surface as send errors;
automatic stamp generation is a Phase 3 task.

No auth beyond the token; bind is loopback-only.

---

## 9. SQLite schema (migration v1)

```sql
PRAGMA journal_mode = WAL;
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE peers(
  hash TEXT PRIMARY KEY,           -- destination hash hex
  identity_hash TEXT NOT NULL,
  display_name TEXT,
  nickname TEXT,
  stamp_cost INTEGER,
  first_seen REAL, last_seen REAL,
  blocked INTEGER DEFAULT 0
);
CREATE TABLE messages(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  hash TEXT UNIQUE NOT NULL,       -- lxm hash hex
  peer_hash TEXT NOT NULL REFERENCES peers(hash),
  direction TEXT NOT NULL,         -- 'in' | 'out'
  state TEXT NOT NULL,             -- sending|sent|delivered|failed|received
  method INTEGER,                  -- LXMF method used
  title TEXT, content TEXT,
  fields_json TEXT,
  created_ts REAL, delivered_ts REAL
);
CREATE INDEX idx_messages_peer ON messages(peer_hash, created_ts);
```

Phase 2 adds `files`, Phase 3 adds `pages`. Migrations: ordered list of
`callable(conn)` keyed to `PRAGMA user_version` bumps.

---

## 10. Frontend spec

### 10.1 Screens (basic mode set; advanced adds "Network" and "Hosting")

1. **Onboarding** (first run): welcome → create identity (auto) → pick
   display name → "connect" (AutoInterface default; optional public
   entrypoint picker) → done. Every step has a "Why?" expander.
2. **Chats** — peer list (announce-discovered), unread badges, last-seen.
3. **Chat view** — bubbles, delivery ticks (sending/sent/delivered/failed),
   reply box, (Phase 2: attachment button).
4. **Files** (Phase 2) — transfers in/out with progress.
5. **My Page** (Phase 3) — visual micron editor + preview + "publish" toggle.
6. **Settings** — profile, mode toggle (with explanation), connection,
   data folder, about.
7. **Network** (advanced, Phase 4) — interfaces table + editor, announces,
   transport toggle, entrypoint wizard.
8. **Help** — rendered markdown guides from `docs/guides/` + glossary.

### 10.2 Mode system

`GET /api/v1/settings.mode` drives a Svelte store; every advanced-only
component checks `mode === 'advanced'`. Navigation hides advanced routes in
basic mode. Mode toggle lives in Settings with a plain-language explainer.

### 10.3 Guides & tooltips system

- `frontend/src/lib/copy/tooltips.ts`: keyed map `screen.element → text`.
- `Tooltip.svelte`: `?` icon → popover with copy + optional "Learn more" link
  to a guide anchor.
- Guide pages: markdown in `docs/guides/*.md`, rendered via a tiny MD
  renderer (e.g. `marked`) — single source used by both the app and GitHub.
- Glossary terms to write (keep each ≤3 sentences): identity, destination
  hash, announce, path & hops, transport node, propagation node, interface,
  store-and-forward, stamp, entrypoint, micron.

---

## 11. RNS/LXMF API cheatsheet (verified against installed 1.5.7 / 1.2.1)

Ground truth paths: `.venv/lib/python3.14/site-packages/RNS/*.py`,
`.../LXMF/*.py`. Manual examples: `https://reticulum.network/manual/examples.html`.

```python
import RNS, LXMF

# Stack (single instance per process; configdir selects instance config)
ret = RNS.Reticulum(configdir=str(configdir))          # Reticulum.py:215

# Identity
ident = RNS.Identity()                                  # create
ident.to_file(path); ident = RNS.Identity.from_file(path)  # Identity.py:641/655

# Our LXMF delivery endpoint (router does this for you)
router = LXMF.LXMRouter(identity=ident, storagepath=str(lxmf_dir), autopeer=True)  # LXMRouter.py:102
router.register_delivery_identity(ident, display_name="Alice")   # :358
router.register_delivery_callback(on_message)                    # :385  on_message(lxm)
router.enable_propagation()                                      # :563  (Phase 4, server side)

# Outgoing message
peer_ident = RNS.Identity.recall(bytes.fromhex(peer_dest_hash))  # from announce
peer_dest = RNS.Destination(peer_ident, RNS.Destination.OUT,
                            RNS.Destination.SINGLE, "lxmf", "delivery")
own_dest  = router.delivery_destinations[ident.hash]             # registered delivery dest
lxm = LXMF.LXMessage(peer_dest, own_dest, content, title,
                     desired_method=LXMF.LXMessage.DIRECT)       # LXMessage.py:114
lxm.register_failed_callback(cb)        # :277 — mark failed in DB/WS
router.handle_outbound(lxm)             # LXMRouter.py:1862
# message states: SENT=0x04 DELIVERED=0x08 FAILED=0xFF
# methods: OPPORTUNISTIC=0x01 DIRECT=0x02 PROPAGATED=0x03
# file attachments: fields={LXMF.FIELD_FILE_ATTACHMENTS: [[name_bytes, data_bytes], ...]}  (0x05)

# Peer discovery announces
class PeerAnnounces:
    aspect_filter = "lxmf.delivery"
    receive_path_responses = False
    def received_announce(self, destination_hash, announced_identity, app_data,
                          announce_packet_hash=None, is_path_response=False):
        # app_data == msgpack.packb([display_name: bytes|None,
        #                            stamp_cost: int|None,
        #                            supported_functionality: list])
        ...                            # msgpack.unpackb(app_data) → upsert peer
RNS.Transport.register_announce_handler(PeerAnnounces())           # Transport.py:2956
```

Notes:
- `RNS.Identity.recall` only works after the peer has announced (path known).
  That's why discovery precedes chat; UI shows "waiting for announce…".
- Delivery confirmation to the UI comes from the inbound delivery callback on
  the sender side being the receipt... precisely: outbound state transitions
  surface via the per-LXMessage callbacks and `lxm.state` polling fallback —
  poll every 2s for ≤30s as belt-and-braces, it's cheap.
- For store-and-forward when direct delivery fails (Phase 2):
  `desired_method=LXMF.LXMessage.PROPAGATED`; receiving while offline uses
  `router.request_messages_from_propagation_node(identity)` (:512).

---

## 12. Phases

### Phase 0 — Bootstrap ✅ (done this session)
venv + `rns`/`lxmf` installed and verified; README, LICENSE, BUILD_PLAN.
Builder: run `.venv/bin/python -c "import RNS, LXMF"` to confirm.

### Phase 1 — MVP: daemon + chat over LXMF + minimal UI

**Backend tasks**
1. `pyproject.toml` (setuptools backend, deps: `rns==1.5.7 lxmf==1.2.1
   aiohttp>=3.14 platformdirs msgpack`, extras dev: pytest pytest-asyncio
   ruff). `pip install -e .` works.
2. `meshdeck/config.py` — dirs, token, settings defaults.
3. `meshdeck/rns/config_gen.py` + unit tests (snapshot the rendered config
   for 3 settings variants).
4. `meshdeck/rns/{identity,stack}.py` — start/stop stack with managed
   configdir; unit: starts without exceptions (temporary dir).
5. `meshdeck/core/events.py` — EventBus thread bridge; unit test.
6. `meshdeck/storage/*` — schema v1 + migrate; unit tests.
7. `meshdeck/chat/{router,peers}.py` — LXMF wrap + announce discovery.
8. `meshdeck/core/service.py` + `meshdeck/api/server.py` — REST + WS per §8,
   auth middleware, CLI entry.
9. Integration harness (§13) + `test_two_nodes.py` — **the acceptance test**.

**Frontend tasks**
1. `pnpm create vite frontend --template svelte-ts` (pnpm 12 is installed),
   add Tailwind v4 (`@tailwindcss/vite`), keep it vanilla-clean.
2. Token handling: read `?token=` once → `sessionStorage`; WS connect;
   reconnect backoff.
3. Three screens minimal: Onboarding-lite (display name), Chats (peer list
   from `/api/v1/peers` + `peer_announced` events), Chat view (send via WS
   cmd, history via REST, live updates via events).
4. Tooltips on every Reticulum term (identity hash, announce, peer).
5. `pnpm run build` → backend serves `frontend/dist` statically.

**Definition of done**
- `make test` green, including two-process LXMF delivery test.
- `python -m meshdeck` serves UI on `http://127.0.0.1:8570`; two instances
  (`--data-dir /tmp/a --port 8570`, `--data-dir /tmp/b --port 8571`) on the
  same LAN/loopback discover each other within ~60s and exchange messages
  with delivery ticks.

### Phase 2 — Contacts, history polish, files, propagation fallback
- Contacts: nickname editing, block, manual "add by hash"; richer peer cards.
- History: infinite scroll, full-text search, day separators.
- Attachments: `FIELD_FILE_ATTACHMENTS` (cap 8 MiB for DIRECT—verify by
  experiment; big files via RNS `Resource` over Link in Phase 4), progress,
  save-to-disk, inbox `files/` folder.
- Offline delivery: propagation fallback setting + sync on startup.
- DoD: integration test sends a 1 MiB file between two nodes and verifies
  hash equality; UI shows progress both sides.
- ✅ Shipped (commit `7c72cb2`): attachments, add-by-hash contacts, rename/
  block, delivery methods + propagation node setting, in-app guides.

### Phase 3 — Advanced mode tooling ✅ (shipped, renumbered)
Interfaces wizard (structured `interfaces` settings, snippet import, hosting
wizards, gateway mode, announce-rate presets), transport-node toggle,
`POST /restart` with config pre-flight + process re-exec, stamp-cost sending
via LXMF's deferred PoW pool, history search, and PyInstaller packaging
(`make package`). Commit `e51d10c`.

### Phase 4 — Pages, sites and node file hosting ✅ (part 1 + 2 shipped)
NomadNet-compatible `nomadnetwork.node` destination: `/page/<name>` and
`/file/<name>` request handlers, node announces + discovery (`nodes` table,
schema v2), RNS-Link client for fetching pages and files, micron editor with
live preview, reader, shared-file UI. Commits `a3f028e`, `107cff9`.

### Phase 5 — Release readiness (next)
CI, transfer progress, page cache, propagation-node hosting, a11y, i18n
extraction, release artifacts (tarball / AppImage / Flatpak), `v0.1.0` tag.
**Full execution spec: [`NEXT_STEPS.md`](NEXT_STEPS.md)** — that file is the
authoritative task list; this section is only the summary.

---

## 13. Testing strategy

**Unit**: config_gen snapshots, DB migrations, schemas/validators,
hexid utils, EventBus ordering. Fast, no network.

**Integration (two real nodes, subprocesses)** — recipe:

`tests/integration/node.py` (standalone script): parses `--configdir
--display-name --expect-from <hash> --send-to <hash> --message <text>
--ready-file --done-file`; boots RNS+LXMF exactly like the app does;
prints JSON lines to stdout; touches ready/done sentinel files; exit 0 on
success, 1 on timeout (120s).

Node A config: TCP server —
```ini
[reticulum]
enable_transport = No
share_instance = No
[logging]
loglevel = 4
[interfaces]
[[Test Server]]
type = TCPServerInterface
enabled = yes
listen_ip = 127.0.0.1
port = 4255
```
Node B config: TCP client — same but
```ini
[[Test Client]]
type = TCPClientInterface
enabled = yes
target_host = 127.0.0.1
target_port = 4255
```
`test_two_nodes.py`: temp dirs → write configs → spawn both with
`subprocess.Popen` → wait for ready files → trigger B to send → assert A's
done file + B's delivery receipt → teardown (terminate, collect logs on
failure). Run under a generous timeout; mark `integration` (pytest marker
registered in pyproject) so unit runs stay fast. Phase 1 CI runs these too.

**Frontend**: `vitest` for store/util logic; screenshots/manual QA per
phase; Playwright optional from Phase 5.

---

## 14. Pitfalls (learned from ecosystem code + manual; reread before phases)

1. **Threads**: RNS callbacks ≠ asyncio. Only `call_soon_threadsafe`.
2. **Process-global RNS state**: never construct two `RNS.Reticulum` in one
   process; tests use subprocesses.
3. **`share_instance = No`** in generated config — otherwise MeshDeck
   silently binds to a running system `rnsd` and appears "broken".
4. **Announce storms**: respect rate limits; on hosted/gateway interfaces
   always set `announce_rate_target/grace/penalty` presets (see manual).
   Test only on loopback/private interfaces, never on public backbones.
5. **Identity recall**: sending to a peer requires a known path; if not
   known, `RNS.Transport.request_path(dest_hash)` then wait/retry — LXMF's
   autopeer does much of this for DIRECT; show "waiting for path" in UI.
6. **AutoInterface needs IPv6 link-local** — in Docker/CI prefer explicit
   TCP interfaces (our harness does).
7. **SQLite + threads**: single writer task; WAL mode.
8. **Secrets**: identity file and API token are `0600`; never log them;
   `.gitignore` the data dir.
9. **Message size**: LXMF DIRECT has practical size limits; enforce caps and
   route big payloads via fields→attachments→(later) Resources.
10. **Port conflicts**: auto-increment default port; never bind non-loopback
    without an explicit advanced setting.
11. **License hygiene**: keep MIT headers on our files; vendor nothing from
    MeshChatX without preserving its license notices.
12. **Constructors must run on the main thread of the main interpreter**:
    both `RNS.Reticulum(...)` and `LXMF.LXMRouter(...)` install SIGINT/SIGTERM
    handlers on construction → `ValueError: signal only works in main
    thread` (or a hard process exit) if built in a worker thread. Call them
    from the asyncio main task, never via `asyncio.to_thread`.
13. **`RNS.panic()` is `os._exit(255)`** — misconfigured interfaces kill the
    process silently, and if `logfile` is set the error never even reaches
    stdout. Always pre-validate interface blocks
    (`RnsStack.validate_interface_config`) before constructing RNS.
14. **Interface key names (rns 1.5.7)**: `TCPServerInterface`/
    `BackboneInterface` take **`listen_ip`** + `port` (or `listen_port`);
    the older docs spelling `listen_on` is auto-remapped — **only for the
    Backbone types** (`Reticulum.py:1119-1122`); TCPServer silently lacks the
    alias and RNS panics (see #13). Emit canonical keys per type.
15. **`LXMessage.hash` is `None` until `pack()`** — call `lxm.pack()`
    yourself right after construction (guarded, deterministic) before
    `handle_outbound`, or you cannot track outbound state.
16. **`RNS.Reticulum` is a never-cleared process singleton**
    (`Reticulum.__instance` has no reset in 1.5.7) → runtime reconfiguration
    must re-exec the process (`os.execv` under the CLI supervisor after
    persisting settings to sqlite). `POST /api/v1/restart` implements this.
17. **PyInstaller + RNS**: `from RNS.Interfaces import *` (in
    `RNS.Reticulum`) discovers submodule names by enumerating the package
    DIRECTORY, which vanishes inside a frozen binary → `NameError:
    BackboneInterface is not defined` at boot. Fix in the packaging shim:
    import every `RNS.Interfaces.*` module (hiddenimports) and bind them as
    attributes on the REAL `RNS.Reticulum` module — via
    `importlib.import_module("RNS.Reticulum")`, because `RNS.Reticulum`
    attribute access yields the re-exported **class**, not the module.
18. **Stamp handling is free**: `LXMessage(stamp_cost=N)` with default
    `defer_stamp=True` is parked in `pending_deferred_stamps`; LXMF's job
    loop mines the PoW in a worker pool and re-packs (hash unchanged — the
    stamp is outside the hashed payload). Pass the peer's announced
    stamp_cost; `include_ticket=True` lets them reply free.
19. **RNS validates response-generator arity exactly**: request handlers must
    take six params `(path, data, request_id, link_id, remote_identity,
    requested_at)`. A `*args` variant dies in the Link job thread with
    "Invalid signature for response generator callback" and the client only
    sees a link that never answers.
20. **aiohttp matches routes in registration order**: register
    `/browse/{hash}/file/{name}` BEFORE the `/browse/{hash}/{path:.+}`
    catch-all, or file downloads are swallowed by the page handler.
21. **`{path:.+}` drops the leading slash**: the REST route hands
    `browse_page` `page/index.mu`, while direct service callers pass
    `/page/index.mu`. A naive `startswith("/page/")` check produced
    `/page/page/index.mu`, so every UI page fetch timed out after 25 s with
    `link_timeout` while integration tests (which called the service
    directly) stayed green. Normalise both forms in
    `pages.client.normalize_page_path` (unit-tested).
22. **Never escape generated markup together with page text**: the micron
    renderer escaped links along with their labels, so `<a>` reached the DOM
    as text and no reader link worked. Escape text at the point of insertion
    and build tags afterwards; unit-test the DOM shape, not just safety.
23. **`messages.peer_hash` is a foreign key to `peers`.** A send can win the
    race with the peer's first announce (or target a manually added hash), so
    `_record_outbound` must `ensure_peer` *before* inserting. Otherwise LXMF
    sends the message successfully and the API then returns 500
    `FOREIGN KEY constraint failed`, leaving the UI to think it failed.

---

## 15. Build order checklist (execute in order; commit per step)

**Phase 1 (MVP) — DONE 2026-10-18.** Verified: 24 unit tests, two-node
integration test (5.4s), full manual E2E with two daemons over the real
REST/WS API (auth enforced, discovery, delivery receipts, live WS events).

- [x] 1. `pyproject.toml` + package skeleton + `python -m meshdeck` stub
- [x] 2. `config.py` + `storage/db.py` + migrations + unit tests
- [x] 3. `rns/config_gen.py` + unit tests (snapshot 3 variants)
- [x] 4. `core/events.py` + unit test
- [x] 5. `rns/identity.py` + `rns/stack.py` (smoke: stack starts in temp dir)
- [x] 6. `chat/peers.py` (announce decode unit test with crafted msgpack)
- [x] 7. `chat/router.py` + `core/service.py` skeletons
- [x] 8. Integration harness `node.py` + `test_two_nodes.py` — passing
- [x] 9. `api/server.py` (REST + WS + auth) + tests for auth + happy paths
      (auth + endpoints verified in manual E2E; automated API tests = Phase 2 task)
- [x] 10. Frontend scaffold (Svelte+TS+Tailwind) + token + WS store
- [x] 11. Onboarding-lite + Chats + Chat view wired to real API
- [x] 12. Backend serves `frontend/dist`; `make dev` flow documented
- [x] 13. Phase 1 DoD manual test: two instances exchange chat (curl/WS-driven)
- [x] 14. `Makefile`, README dev quickstart refresh, CHANGELOG start

**Phase 2 — contacts, attachments, delivery control — DONE 2026-10-18.**
Verified with `tests/api` (real HTTP+WS against a booted daemon) and three
two-node tests: chat, reply round-trip, 1 MiB file transfer with SHA-256
equality on the receiver side; oversize uploads return `too_large` (400).

- [x] 15. Manual add-by-hash (`POST /peers`), path requested when unknown
- [x] 16. Contacts UX: rename, block, add; peer options menu
- [x] 17. File attachments send/receive + download route + sanitization
- [x] 18. Integration tests: reply round-trip + 1 MiB file hash check
- [x] 19. Automated API tests (auth, validation, no_path, WS ping/err)
- [x] 20. Delivery settings: method + propagation node, live-applied
- [x] 21. In-app Guides view + repo guide docs

**Phase 3 — connectivity & hosting wizards, stamps, packaging — DONE 2026-10-18.**
Verified with a wizard-only E2E: two daemons, zero hand-written configs —
PUT interfaces → POST /restart (process re-exec) → announce discovery →
chat delivery across the wizard-built link; restart integration test proves
the new interface is live after re-exec.

- [x] 22. Structured `interfaces` settings list + INI renderer (rate-limit
      presets for public listeners; gateway mode for backbone)
- [x] 23. `POST /api/v1/restart`: pre-validates config, re-execs via CLI
      supervisor (RNS singleton never clears — pitfall §14.16)
- [x] 24. Interfaces wizard UI: add/remove/toggle, paste-snippet parser
      (directory.rns.recipes / rmap.world compatible), hosting wizards with
      share-snippet generator + firewall explainer
- [x] 25. Transport-node toggle (advanced) with stewardship warning
- [x] 26. Stamp-cost sending: `LXMessage(stamp_cost=…, include_ticket=True)`
      defers PoW to LXMF's worker pool; hash stays stable (stamp ∉ hashed
      payload); UI stamp badge + hint
- [x] 27. Chat history search (client filter) + match counter
- [x] 28. PyInstaller packaging: `make package` → one-file binary with the UI
      embedded (frontend/dist as data files)

**Phase 4 done so far (2026-10-18):** NomadNet-compatible page hosting over
RNS Links: `nomadnetwork.node` destination + `/page/<name>` request handlers
(same wire behaviour as the reference NomadNet node — plain utf-8 content is
the response), node announces with the node name, discovery of other nodes
via announce handler (`nomadnetwork.node` aspect), client-side page fetching
via `RNS.Link.request` (blocking in a thread; `no_path`/`link_timeout`
codes). UI: Pages view (editor + live micron preview + publish toggle +
discovered-nodes chips + reader with rendered micron + timing), guide pages
for hosting/browsing.

Pitfall §14.19: RNS validates response-generator arity exactly — the six-arg
`(path, data, request_id, link_id, remote_identity, requested_at)` signature
from NomadNet's Node.py is mandatory (a `*args` variant dies in the Link job
thread with "Invalid signature for response generator callback" and the
client just sees link established then no response).

**Phase 4 part 2 done (2026-10-18):** node file sharing — `/file/<name>`
request handlers per shared file with `auto_compress=32 MiB` (NomadNet's
scheme), shared store with traversal-safe names, client `fetch_file` over a
Link, REST `/shared` CRUD + `/browse/{hash}/file/{name}`, UI share/download
section. Integration test downloads 256 KiB with SHA-256 equality.

Route-order pitfall (§14.20): aiohttp matches in REGISTRATION order, so
`/browse/{hash}/file/{name}` must be registered BEFORE the
`/browse/{hash}/{path:.+}` catch-all, or file downloads silently hit the
page handler.

**P4.1 done (2026-10-18):** transfer progress for pages and node files.
`link.request(progress_callback=…)` runs on an RNS thread, so the service
throttles (10 % / 250 ms) and publishes only through
`EventBus.publish_from_thread`; optional `transfer_id` keeps the synchronous
REST shape. Verified with an 8 MiB two-node integration test and a browser
run of the progress bar.

**P4.2 done (2026-10-18):** page cache — DB v3 `page_cache`, 4 MiB/entry,
500 rows, 30-day prune; fresh hits are instant, unreachable nodes fall back
to a stale saved copy, `?refresh=1` forces a live fetch. Verified with a
kill-the-host integration test and a browser run of the cached/stale badges.

**Phase 4 remaining:** `/media` handler (image conversion needs Pillow;
deferred), executable pages (deliberately not supported).

**P5.4 done (2026-10-18):** accessibility pass — tablist nav, focus-trapped
add-peer/onboarding dialogs, keyboard ⋯ menu, aria-labels, polite live
regions, visible focus ring, reduced-motion support. Contrast verified
(wp-dim 7.32:1 on wp-bg, 6.81:1 on wp-panel). Screen-reader/keyboard-only
walkthrough not run; recorded in `docs/a11y-checklist.md`.

**P5.2 done, Flatpak unverified (2026-10-18):** release tarball + genuine
AppImage + icon/desktop entry + Flatpak manifest. Independently re-verified:
`sha256sum -c`, tarball contents, and `--version` from both the extracted
tarball and the AppImage (`meshdeck 0.1.0.dev0`). `flatpak-builder` is not
installed, so the manifest has never been built — `packaging/README.md` says
so and lists the exact recipe. Rebuild at 0.1.0 for the tag.

**P4.5 + P4.4 done (2026-10-18):** vitest suite (26 tests) plus the reader
fix. Two real bugs were found by browser E2E that the unit/integration suites
had missed: (a) micron links were HTML-escaped into text because escaping ran
after markup generation, and (b) the REST browse route dropped the leading
slash and the service re-prefixed `/page/`, producing `/page/page/...` and a
25 s timeout — so browsing from the UI had never worked. Fixed both, added
`normalize_page_path` + tests, and verified with headless Chromium against
two real daemons over a TCP link: page 1 → click link → page 2 → ← back →
page 1. Reader now has a back stack, inline `` `[literal]` `` spans, stripped
unknown backtick tokens, and a 512 KiB render cap.

**Phase 5 (after):** i18n scaffolding, packaged releases (Flatpak/AppImage/
Windows exe from the PyInstaller base), accessibility pass, first public tag.

**Phase 5 started (2026-10-18):** GitHub Actions CI
(`.github/workflows/ci.yml`): `backend` matrix over Python 3.12/3.13/3.14
(ruff + unit tests), `frontend` (pnpm `check`/`test`/`build`, pnpm + pip
caches), and a `continue-on-error` `integration` job (20 min timeout) that
spawns real RNS nodes. CI badge added to the README. The frontend `test`
step becomes effective with the vitest suite in P4.5.

**P4.5 done:** frontend unit tests exist — vitest (`pnpm run test`,
10 tests) with node-environment config; `make check` and CI both run them.

---

## 16. RNS/LXMF integration recipe (appendix: the critical path)

---

*Plan written 2026-10-18 against rns 1.5.7 / lxmf 1.2.1 on Python 3.14.8.
Update the "verified" cheatsheet (§11) whenever dependencies are bumped.*
