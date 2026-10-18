# Contributing to MeshDeck

Thanks for looking. This project is small, plain-spoken and deliberately
boring in the places that matter: official protocol libraries, one local
daemon, SQLite, and no telemetry. The notes below are what previous sessions
wished they had read first.

If anything here disagrees with the code, the code wins — fix the doc in the
same change.

## Ground rules

1. **Never reimplement RNS or LXMF.** Use the official `rns` and `lxmf`
   packages for identity, announce, paths, Links, LXMF messages, stamps and
   encryption. The verified baseline is `rns 1.5.7` / `lxmf 1.2.1`;
   `pyproject.toml` allows newer releases in the same series, but do not code
   against an API you have not run. No vendored protocol code, no hand-rolled
   crypto, no home-grown wire formats.
2. **Never touch `~/.reticulum`.** MeshDeck owns `<data-dir>/reticulum/`, writes
   its config there and sets `share_instance = No`. It must not interfere with
   a system `rnsd`.
3. **Respect the threading boundary.** RNS/LXMF callbacks run on RNS worker
   threads; they must not touch asyncio, the database or the API server. See
   [Threading](#threading-the-one-rule-that-matters).
4. **No telemetry, no analytics, no accounts.** Guides must work offline.
5. **Verify, don't narrate.** A change is done when you can show the command
   output, test result or screenshot that proves it. If something is unverified
   (a packaging format without the tool installed, a flaky end-to-end test),
   say so in the change description instead of implying it works.

## Setup

Prerequisites: Python 3.11+, Node 22 and pnpm 10 (what CI uses), GNU make and
git.

```bash
git clone https://github.com/martintondel02/meshdeck.git
cd meshdeck
make install            # .venv + pip install -e ".[dev]"
make install-frontend   # pnpm install in frontend/
make dev                # build UI, run daemon, print the ?token= URL
```

Use `.venv/bin/python` for backend work — the Makefile does, and the system
Python is not the project environment. `make install-frontend` only needs to
run again when `frontend/package.json` or `frontend/pnpm-lock.yaml` changes.

To run an isolated instance without touching your normal data:

```bash
.venv/bin/python -m meshdeck --data-dir /tmp/meshdeck-dev --port 8571 --verbose
```

The default data directory is `${XDG_DATA_HOME:-~/.local/share}/meshdeck`. The
`--data-dir`, `--host`, `--port`, `--open-browser` and `--verbose` flags are
defined in `meshdeck/__main__.py`.

## Tests and checks

Run `make check` before opening a pull request. It runs the same three things
CI runs for a normal change: backend unit tests, frontend unit tests and lint.

| Command | What it runs | Notes |
|---|---|---|
| `make test` | `pytest tests/unit -q` | Fast, no network. Integration tests are excluded by default via `addopts` in `pyproject.toml`. |
| `make test-frontend` | `cd frontend && pnpm run test` | Vitest, currently the micron renderer including escaping/XSS cases. |
| `make test-integration` | `pytest tests/integration -m integration -q` | Spawns real RNS/LXMF subprocesses. Takes minutes and must stay hermetic. |
| `make lint` | `ruff check meshdeck tests` + `pnpm run check` | Ruff line length is 100; rules E, F, W, I. `tests/**` may exceed the line length. |
| `make check` | `test` + `test-frontend` + `lint` | The pre-PR baseline. |

The exact underlying commands, if you need to run one directly:

```bash
.venv/bin/python -m pytest tests/unit -q
.venv/bin/ruff check meshdeck tests
cd frontend && pnpm run check     # svelte-check
cd frontend && pnpm run test      # vitest run
cd frontend && pnpm run build     # vite build
```

CI's integration job additionally runs the API acceptance test:
`pytest tests/api tests/integration -m integration -q` (non-blocking, 20-minute
timeout). If you change the REST/WS surface, run that locally too.

### Integration-test rules

- Reuse the helpers in `tests/integration/test_two_nodes.py`
  (`launch_node`, `wait_for_file`, `_run_pair`) instead of writing a new
  harness. `tests/integration/node.py` is the standalone node script.
- Keep tests hermetic: temporary data directories, random free ports, loopback
  only. Never point a test at a public backbone or someone else's node.
- Do not pipe a node's stdout through `head` — it masks the process exit code.
- Sentinels (`ready.json`, `done.json`) are how the harness knows a node is up
  or finished; wait on files, not on sleeps where you can avoid it.
- RNS is process-global. Never construct two `RNS.Reticulum` instances in one
  process; that is why integration tests use subprocesses.

## Code map

| Path | Responsibility |
|---|---|
| `meshdeck/__main__.py` | CLI entry, startup banner, restart supervisor (`os.execv`) |
| `meshdeck/config.py` | Data-dir paths, settings store, token generation |
| `meshdeck/core/service.py` | `CoreService`: lifecycle, business logic, persistence |
| `meshdeck/core/events.py` | `EventBus`: the RNS-thread → asyncio bridge |
| `meshdeck/chat/` | LXMF router (send/receive, attachments, stamps), peer announces |
| `meshdeck/pages/` | Page storage, `/page` + `/file` hosting, browsing client, shared files |
| `meshdeck/rns/` | Config rendering/validation, identity, `RnsStack` |
| `meshdeck/storage/` | SQLite connection, migrations and repositories (raw SQL, no ORM) |
| `meshdeck/api/` | aiohttp REST + WebSocket, bearer auth, static UI |
| `frontend/src/components/` | Screens: Chats, Pages, Guides, Settings, onboarding |
| `frontend/src/lib/copy/tooltips.ts` | All tooltip and glossary copy |
| `frontend/src/lib/micron.ts` | Micron → HTML renderer (security-relevant) |
| `frontend/src/lib/api.ts`, `ws.ts`, `stores.ts` | Token handling, REST/WS clients, Svelte stores |

## Threading: the one rule that matters

RNS runs its own worker threads. Announce handlers, LXMF delivery callbacks,
link progress callbacks and transfer callbacks all fire there — not on the
asyncio loop.

- From an RNS callback, call `EventBus.publish_from_thread(...)`. It captures
  the loop once and uses `loop.call_soon_threadsafe`. Do not call asyncio APIs,
  `asyncio.get_running_loop()`, the database or the HTTP layer directly.
- A subscriber may be async; the EventBus awaits it on the loop. A subscriber
  that raises is logged and does not kill the bus.
- Construct `RNS.Reticulum(...)` and `LXMF.LXMRouter(...)` only on the main
  thread. Both install signal handlers on construction, so a worker-thread
  construction fails or exits the process.
- Blocking RNS work (Links, path requests that wait) goes through
  `asyncio.to_thread`; see the page browsing calls in `CoreService`.
- Database access happens on the asyncio loop thread. The event-persistence
  subscriber takes `CoreService._db_lock`, and the SQLite connection uses WAL
  and `check_same_thread=False`; keep it that way rather than adding a second
  writer.

More detail, including the event flow and the restart sequence, is in
[docs/architecture.md](docs/architecture.md).

## Copy, tooltips and guides

Explanatory text the user sees is centralised so it can be reviewed and compared
against the protocol libraries:

- **Tooltips and glossary:** `frontend/src/lib/copy/tooltips.ts` exports
  `TOOLTIPS` and `GLOSSARY`. Components use
  `<Tooltip text={TOOLTIPS.some_key} />`. Add a key there first, then use it.
- **In-app guides:** the Guides tab renders `SECTIONS` from
  `frontend/src/components/Guides.svelte`.
- **Long-form guides:** the same material lives as Markdown in `docs/guides/`
  (`getting-started.md`, `sending-files-and-contacts.md`, `hosting-pages.md`,
  `hosting-infrastructure.md`)
  for the repo and offline reading.

The Markdown files and the in-app `SECTIONS` are separate copies today. If you
change user-facing guidance, update both and keep them consistent. Never put
Reticulum jargon on screen without a tooltip or a guide that explains it.

Add new tooltips and glossary entries to the registry, not inline in a
component. There is no i18n layer yet; ordinary UI strings still live in the
components, so if you add one, match the existing style and keep it short. If
you introduce i18n, move the registry into it rather than sprinkling strings
through components.

## Adding a feature

Use [docs/architecture.md](docs/architecture.md) for the full checklist. The
short version:

1. Backend logic belongs in a module under `meshdeck/` (chat, pages, rns,
   storage), called from `CoreService` — the API layer should stay thin.
2. Add a repository function in `meshdeck/storage/` for new tables or queries,
   with a new append-only migration tuple in `meshdeck/storage/db.py`.
3. Expose it in `meshdeck/api/server.py` under `/api/v1`, validate input in
   `meshdeck/api/schemas.py`, and publish state changes through the EventBus so
   the WebSocket clients stay in sync.
4. Add the UI in `frontend/src/components/`, state in `lib/stores.ts`, network
   handling in `lib/api.ts` / `lib/ws.ts`, and copy in `lib/copy/tooltips.ts`.
5. Add tests at the right level: unit for pure logic, `tests/api` for the REST
   surface, `tests/integration` for real RNS Links/nodes, Vitest for frontend
   logic.
6. Update `CHANGELOG.md` under `## [Unreleased]`, tick the relevant box in
   `BUILD_PLAN.md` §15, and record anything unverified.

Do not add a dependency unless the alternative is clearly worse; prefer the
standard library. The current backend set is `rns`, `lxmf`, `aiohttp`,
`platformdirs` and `msgpack`; the frontend is Vite, Svelte 5, TypeScript,
Tailwind 4 and Vitest.

## Commit style

One focused change per commit, with a phase tag where it applies:

```
feat: Phase 4.1 — transfer progress for pages and node files
fix: Phase 4.4 — micron reader links, back stack and REST page path
test: Phase 4.5 — vitest suite for the micron renderer
ci: Phase 5.1 — GitHub Actions for backend, frontend and integration
docs: Phase 5.5 — README, CONTRIBUTING, SECURITY and architecture notes
```

- Say **what** changed and **why** in the body when it is not obvious.
- Do not mix refactors, formatting churn or unrelated fixes into the commit.
- If you find a bug while testing, fix it and add the regression test in the
  same change; add the mechanism to the pitfall list if it is generically
  useful.
- Update `CHANGELOG.md` in the same change. The human reviewers read the
  changelog and plan, not the diff.
- Never commit a real data directory, identity, API token, database, or a
  screenshot containing real addresses/messages. `.gitignore` covers the usual
  cases; check `git status` before committing.

## Before you ask for review

- `make check` is green.
- New behavior has a test at the cheapest level that actually exercises it.
- The change description names the commands you ran and anything you could not
  verify.
- User-facing text has a tooltip/guide and matches the plain tone: no marketing
  claims, no invented features, no version numbers you did not read from the
  code.

Read [BUILD_PLAN.md §14](BUILD_PLAN.md#14-pitfalls-learned-from-ecosystem-code--manual-reread-before-phases)
before touching RNS startup, interfaces, Links or packaging. It records the
failures that cost the most time, including `RNS.panic()` on bad interface
config, the TCPServer `listen_ip` spelling, the process-global Reticulum
singleton, route ordering in aiohttp, and the leading-slash trap in
`{path:.+}`.
