# NEXT STEPS — Phase 4 remainder & Phase 5 (execution spec)

> **Audience:** the next agent session (and the human reviewing it).
> **Status:** written 2026-10-18 at commit `107cff9`, after Phase 4 part 2
> (node file sharing) landed green.
> **Rule:** this document is a *specification*. Verify every claim against the
> code before trusting it; if reality and this doc disagree, reality wins and
> this doc gets corrected in the same commit.

---

## 0. Session bootstrap (do these first, in order)

```bash
cd /home/martintondel/Projects/reticulum
git log --oneline | head -5          # expect 107cff9 at the tip
git status --short                   # expect clean
.venv/bin/python -m pytest tests/unit -q                       # expect 39 passed
cd frontend && pnpm run check && pnpm run build && cd ..       # expect 0 errors, ~110 kB
.venv/bin/ruff check meshdeck tests                            # expect clean
```

If any of those fail, **stop and fix the baseline first** — do not build on a
red tree.

Environment facts:

| Thing | Value |
|---|---|
| Python | 3.14 in `.venv/` — always `.venv/bin/python`; system `pip` does not exist |
| Backend deps | `rns 1.5.7`, `lxmf 1.2.1`, aiohttp, platformdirs, msgpack (pinned in `pyproject.toml`) |
| Frontend | Vite + Svelte 5 (runes) + TS + Tailwind 4, pnpm |
| Run | `.venv/bin/python -m meshdeck --data-dir /tmp/x --port 8570` (prints UI URL with `?token=`) |
| Default API | `127.0.0.1:8570`, bearer token in `<data-dir>/token` |
| DB | SQLite `<data-dir>/meshdeck.db`, raw SQL, `PRAGMA user_version` migrations (currently **v3**: + `page_cache`) |
| GitHub | `martintondel02/meshdeck`, `gh` CLI authenticated with `repo` scope |
| Push policy | commit per task with a descriptive message, then `git push origin main` |

Test commands (memorise):

```bash
.venv/bin/python -m pytest tests/unit -q                                  # fast, no network
.venv/bin/python -m pytest tests/api tests/integration -m integration -q  # ~40 s, real RNS nodes
.venv/bin/ruff check meshdeck tests [--fix]                               # E501 = 100 cols
cd frontend && pnpm run check && pnpm run build
```

Integration tests spawn real subprocesses (`tests/integration/node.py`) and use
sentinel files (`ready.json` / `done.json`). **Never pipe node stdout through
`head`** — it masks exit codes. Reuse `tests/integration/test_two_nodes.py`
helpers (`launch_node`, `wait_for_file`, `_run_pair`) instead of writing new
harnesses.

---

## 1. What already exists (so you don't rebuild it)

### Backend (`meshdeck/`)

| Module | Responsibility |
|---|---|
| `config.py` | `AppPaths` (db/token/identity/reticulum/lxmf/files/pages/shared/logs), `SettingsStore`, `DEFAULT_SETTINGS` |
| `rns/identity.py` | identity load/create, `identity_info()` |
| `rns/stack.py` | RNS startup/shutdown on the **main thread** |
| `rns/config_gen.py` | INI rendering from settings (`interfaces` list, rate presets, extras merge) + preflight validation |
| `chat/router.py` | LXMF send/receive, attachments (`FIELD_FILE_ATTACHMENTS`), stamps, delivery methods, propagation sync |
| `chat/peers.py` | announce handler for `lxmf.delivery` |
| `pages/storage.py` | `.mu` page CRUD, name validation |
| `pages/files.py` | shared files: sanitize, 32 MiB cap, CRUD |
| `pages/hosting.py` | `PageHost`: `nomadnetwork.node` destination, `/page/<name>` + `/file/<name>` handlers, node announce |
| `pages/client.py` | `fetch_page` / `fetch_file` / `fetch_path` over `RNS.Link` (blocking) |
| `core/service.py` | orchestration, all business logic, event persistence |
| `core/events.py` | EventBus + `publish_from_thread` (RNS threads → asyncio) |
| `api/server.py` | aiohttp REST + `/ws`, bearer auth, static UI serving |
| `storage/*` | peers, messages, nodes repos; schema v1 (settings/peers/messages) + v2 (nodes) |
| `__main__.py` | CLI, restart supervisor (`os.execv`), static dir resolution |

### REST surface (all under `/api/v1`, bearer auth)

```
GET    /status                GET  /identity          POST /identity/display_name
GET    /peers                 POST /peers             PATCH /peers/{hash}
GET    /messages?peer=        POST /messages          POST /files   (multipart)
GET    /attachments/{peer}/{msg}/{index}
GET    /pages                 GET/PUT/DELETE /pages/{name}
GET    /node                  POST /node/publish      GET  /nodes
GET    /browse/{hash}/{path:.+}
GET    /shared                POST /shared (multipart) GET/DELETE /shared/{name}
GET    /browse/{hash}/file/{name}
GET/PUT /settings             POST /announce          POST /restart
/ws (hello frame, {type:cmd}, events: peer_announced, message_received,
     message_state, node_announced, settings_updated, restart_scheduled,
     transfer_progress, transfer_complete, transfer_failed)
```

### Frontend (`frontend/src/`)

`App.svelte` (nav: Chats / Pages / Guides / Settings), `components/{PeerList,
ChatView, Settings, Guides, Pages, InterfacesCard, Onboarding, Tooltip}.svelte`,
`lib/{api,ws,stores,interfaces,micron}.ts`, `lib/copy/tooltips.ts` (all copy
centralised), Tailwind tokens `wp-bg wp-panel wp-panel2 wp-border wp-text
wp-dim wp-accent wp-danger`.

### Packaging

`make package` → `dist/meshdeck` (~23 MB one-file PyInstaller binary with the
UI embedded). `packaging/meshdeck_main.py` force-binds `RNS.Interfaces` modules
(required — the star-import cannot enumerate a frozen package dir);
`packaging/meshdeck.spec` holds `hiddenimports`.

### Non-negotiable constraints (from BUILD_PLAN §2, still binding)

- Only official `rns`/`lxmf` libraries — never reimplement protocol pieces.
- Never touch `~/.reticulum`; MeshDeck owns its data dir, `share_instance = No`.
- RNS/LXMF objects construct on the **main thread** (both install signal handlers).
- RNS singleton cannot be re-initialised in-process → restart = `os.execv`
  under the CLI supervisor (`POST /restart` already does this).
- Raw SQL + hand-rolled migrations; no ORM.
- MIT, no analytics, no telemetry, guides work offline.

---

## 2. Phase 4 remainder

Goal: pages/files feel finished on slow links and unreliable peers, and the
node is useful as infrastructure, not just a demo.

### P4.1 — Transfer progress for large responses  ★ highest value  ✅ DONE

> **Landed (2026-10-18):** `pages/client.fetch_path/fetch_page/fetch_file`
> take a `progress_cb` (wrapped so a raising callback cannot abort the
> transfer); `CoreService` throttles it to 10 % / 250 ms and publishes
> `transfer_progress` via `publish_from_thread` from the RNS thread, then
> `transfer_complete` (with SHA-256 for files) or `transfer_failed`.
> `?transfer_id=` accepted on both browse routes; WS store + thin
> `TransferBar.svelte` in the reader and file downloader.
> Verified: new integration test hosts an 8 MiB file, downloads it over a
> real two-node Link, asserts ≥3 monotonic progress events ending at 1.0 and
> a complete event with the correct SHA-256 (5.4 s). Browser E2E on two
> daemons: bar showed 0 % → 10 % → 20 % … and the saved 8 MiB file matched
> SHA-256.

**Why:** `link.request` already reports progress; today an 8 MiB download over
a slow link is a silent spinner. NomadNet shows a progress bar; we should too.

**Verified API**

```python
# RNS/Link.py:473
receipt = link.request(path, data={}, timeout=T, max_response_size=N,
                       progress_callback=cb)   # cb(request_receipt)
# RequestReceipt.progress: float 0.0–1.0 (updated during Resource transfer)
```

**Backend tasks**
1. `pages/client.py`: add `progress_cb: Callable[[float], None] | None` to
   `fetch_path`; wire it into `link.request(progress_callback=lambda r: progress_cb(r.progress))`,
   guarding exceptions from the callback (it runs on an RNS thread).
2. `services.browse_page` / `download_shared`: accept a `transfer_id: str`
   and emit `bus.publish_from_thread("transfer_progress", {"id", "path",
   "progress", "kind"})` — **from the callback**, since the callback fires on
   an RNS thread. Throttle to ≥10 % deltas or 0.25 s to avoid WS flooding.
3. On completion emit `transfer_complete` with `{id, path, bytes, elapsed_ms,
   sha256}` (sha256 for files only) and on failure `transfer_failed`
   `{id, error}`.
4. REST: accept optional `?transfer_id=` on both browse routes. Keep the
   synchronous response shape unchanged (backwards compatible).

**Frontend tasks**
5. `ws.ts`: handle `transfer_progress` / `transfer_complete` /
   `transfer_failed` → update a `transfers` store keyed by id.
6. `Pages.svelte`: when downloading a page/file, generate
   `crypto.randomUUID()`, pass `transfer_id`, render a thin progress bar +
   "N %" while active, then the result. Reuse for both the reader and the
   "Get file" button.

**Acceptance**
- Integration test (`tests/integration/test_pages.py`): host an 8 MiB shared
  file; reader fetches it; assert ≥3 monotonic `transfer_progress` events with
  a final `1.0`, then `transfer_complete` with correct sha256; total wall time
  under 120 s.
- Do **not** make the existing synchronous tests slower: progress is optional.

**Pitfalls**
- Progress callback is on an RNS thread — never touch asyncio objects
  directly; use the EventBus bridge, and never call `asyncio.get_running_loop()`
  from that callback.
- A `progress_callback` raising will abort the transfer: wrap user code in
  `try/except Exception: log`.

### P4.2 — Page cache (offline browsing of visited pages)  ★ medium  ✅ DONE

> **Landed (2026-10-18):** DB migration v3 + `storage/page_cache.py`
> (`put/get/list/prune`, 4 MiB per-entry cap, ≤500 rows, 30-day age prune at
> boot). `browse_page(..., refresh=False, max_age=3600)` serves fresh hits
> with `elapsed_ms=0`, caches successful fetches, and on
> `no_path`/`link_timeout` returns a stale entry with
> `served_from_cache=True, stale=True, error=<code>`; `?refresh=1` forces a
> fetch. Reader shows “cached · 2h ago” / “saved copy — node unreachable”
> plus an always-available Refresh button.
> Verified: 7 new unit tests (repo + fresh/stale/refresh/no-cache service
> paths) and an integration test that fetches live, kills node A, refetches
> with `max_age=0`, and gets byte-identical content with `stale=True`
> (19.4 s, dominated by the 15 s link timeout). Browser E2E: live fetch had
> no badge; after killing the host, Refresh showed the saved-copy badge and
> the same page.

**Why:** NomadNet caches pages; revisiting a node offline currently errors.

**Backend**
1. DB **migration v3** in `storage/db.py`: append to `MIGRATIONS`
   `(3, """CREATE TABLE IF NOT EXISTS page_cache(node_hash TEXT NOT NULL,
   path TEXT NOT NULL, content TEXT NOT NULL, content_bytes INTEGER, fetched_ts REAL,
   PRIMARY KEY(node_hash, path));""")` — and update `tests/unit/test_db.py`
   expectations (`user_version == 3`, table present). Keep v1/v2 untouched.
2. `storage/page_cache.py`: `put/get/list/prune(older_than_seconds, max_rows)`.
   Prune on service start (keep ≤ 500 pages).
3. `service.browse_page(node_hash, path, *, refresh=False, max_age=3600)`:
   - cache hit + fresh → return with `served_from_cache=True, elapsed_ms=0`
   - miss → fetch, `put`, return `served_from_cache=False`
   - fetch fails (`no_path`/`link_timeout`) **and** a stale entry exists →
     return stale content with `served_from_cache=True, stale=True` + `error`
     field, so the UI can say "showing a saved copy".
4. REST: `GET /browse/{hash}/{path}` gains `?refresh=1`; response gains
   `served_from_cache`, `stale`, `cached_ts`.

**Frontend**
5. Reader shows a small badge: "cached · 2 h ago" / "saved copy — node
   unreachable" with a **Refresh** button that re-fetches with `refresh=1`.

**Acceptance**
- Unit: cache put/get/prune; stale-fallback path with a monkeypatched
  `fetch_page` raising `PageFetchError("no_path")`.
- Integration: fetch page once (live), then kill node A, fetch again on B →
  served from cache with `stale=True`; assert the content is byte-identical.
- Cache must never store > 4 MiB per entry (same cap as pages).

### P4.3 — Propagation-node hosting (advanced toggle)  ★ high value, small  ✅ DONE

> **Landed (2026-10-18):** `host_propagation_node` setting (default off,
> live-applied — no restart); `ChatRouter.set_propagation_hosting()` calls
> `LXMRouter.enable_propagation()`/`disable_propagation()` and exposes the
> node's stable `propagation_node_hash`; `GET /status` reports both;
> `PUT /settings` applies the toggle and publishes `settings_updated`.
> Settings (advanced) has the toggle, cost/privacy explanation and the
> propagation address with a copy button; `docs/guides/
> hosting-infrastructure.md` + a Guides-tab section explain hosting.
> **Verified:** real daemon PUT true → `propagation_hosting: true`, router log
> “Propagation node hosting enabled”, address unchanged, PUT false → false;
> API acceptance test added; and the end-to-end store-and-forward integration
> test (A hosts, B sends to offline C via A, C syncs and receives) passes in
> ~12 s — it exposed and now guards two real router bugs (BUILD_PLAN
> §14.24/§14.25).

**Why:** "all-in-one" should include being infrastructure: a store-and-forward
node others can use when peers are offline.

**Verified API:** `LXMRouter.enable_propagation()` (`LXMRouter.py:563`) /
`disable_propagation()` (`:702`).

**Tasks**
1. `config.py`: setting `host_propagation_node: False`; add to
   `RESTART_SETTINGS` (it is router-level state; safest is live-apply if it
   works, otherwise mark restart-required — **test it**: call
   `enable_propagation()` at runtime and send a propagated message between two
   nodes; if it works live, apply live and skip restart).
2. `chat/router.py`: `set_propagation_hosting(enabled)` → call the router
   method, log, emit `settings_updated`.
3. `service.update_settings`: validate + apply; expose current state in
   `GET /status` as `propagation_hosting: bool`.
4. `Settings.svelte` (advanced only): toggle + explanation (storage grows,
   bandwidth cost, announce interval) + a note that the node's own address is
   the one to share; show a "propagation node address" line with copy button.
5. Guide section "Hosting for others" in `Guides.svelte` +
   `docs/guides/hosting-pages.md` (or a new `docs/guides/hosting-infrastructure.md`).

**Acceptance**
- Integration: A hosts propagation (`host_propagation_node=True`), B routes a
  message to an offline C's address via A (`delivery_method=propagated`,
  `propagation_node_hash=A`), C comes online and syncs (`route` from
  propagation) and receives the message. This is the hardest test in the
  suite; if it proves flaky, ship with an API-level test (assert
  `status.propagation_hosting`) and file the end-to-end as follow-up **without
  claiming it verified**.

### P4.4 — Micron reader polish (real bug + small features)  ★ small  ✅ DONE

> **Landed (2026-10-18):** the reader bug was worse than described — links
> never reached the DOM as anchors at all (escaping ran *after* markup
> generation), and every UI page fetch timed out because the REST route
> dropped the leading slash and `browse_page` re-prefixed `/page/`
> (`/page/page/…`). Both fixed. Added a reader action that intercepts
> `a.micron-link` clicks (relative links use the current node), a ← back
> stack, inline `` `[literal]` `` spans, documented `` `!``/`_`/`*` toggles,
> unknown-backtick stripping, and a 512 KiB render cap. 16 new vitest cases
> (26 total). Verified in headless Chromium with two real daemons over TCP:
> Home → link → Second page → ← back → Home, 0 `#/browse/` anchors.
> Screenshots: `/tmp/p44-page1.png`, `/tmp/p44-page2.png` (not committed).
> See BUILD_PLAN §14.21/§14.22.

**Bug (fix first):** internal links rendered by `lib/micron.ts` emit
`<a href="#/browse/…" data-node=… data-path=…>`, but nothing handles the click
and there is no router — clicking a link to `/page/other.mu` does nothing.

**Tasks**
1. On the reader container in `Pages.svelte`, add a click handler: if the
   anchor has `data-node`/`data-path`, `preventDefault()` and navigate the
   reader (set `browseHash`/`browsePath`, call `browse()`).
2. Add a breadcrumb/back stack in the reader (array of visited paths, "← back")
   so multi-page nodes are navigable.
3. Micron gaps worth closing (all in `micron.ts`, each with a unit test — see
   P4.6): inline `` `[code]` `` literal span, `>>`/`>>>` already handled,
   `-` rule, `•` bullets; and **strip** unknown backtick tokens instead of
   leaking them as text (current regex misses multi-letter tokens).
4. Cap rendered output: refuse pages > 512 KiB with a "page too large to
   render" notice (protect the browser).

**Acceptance**
- Manual: serve two linked pages from node A, browse A from B, click the link
  → page 2 renders, back returns to page 1.
- No `href="#/browse/..."` left in the DOM after the fix (links become
  buttons or anchors with click handlers).

### P4.5 — TS unit tests for micron (new tooling)  ★ small, enables P4.4  ✅ DONE

> **Landed (2026-10-18):** `vitest` 5 installed, `pnpm run test` script,
> node-environment test config in `vite.config.ts`, and
> `src/lib/micron.test.ts` (10 tests: headings, paragraphs, bullets, rule,
> code fences incl. unterminated, empty input, and four XSS/escaping cases).
> `make check` now runs `test-frontend`; CI runs `pnpm run test`.
> Verified the XSS suite catches a regression by temporarily breaking
> `escapeHtml` (4 tests failed), then restoring it (10 passed).
> Link/backtick/literal tests landed with the P4.4 fix, because they encode
> behaviour that was itself broken (see the note there).

Backend has 39 unit tests; the renderer has none and it is security-relevant
(it produces `{@html}`).

**Tasks**
1. Add `vitest` (`pnpm add -D vitest`), script `"test": "vitest run"`,
   config in `vite.config.ts` (`test: { environment: "node" }`).
2. `frontend/src/lib/micron.test.ts`: headings/levels, code fences, bullets,
   hr, bold/underline, links with host:/page targets, **XSS**: `<script>`,
   `"><img onerror=…>`, backtick token leakage, 512 KiB refusal (once added).
3. Add `pnpm run test` to the Makefile `check` target and to CI (P5.1).

**Acceptance:** `cd frontend && pnpm run test` green; deliberately introduce an
`<script>` XSS case and confirm a test catches it.

### P4.6 — Explicitly deferred (do **not** rabbit-hole)

- **`/media` image handler.** NomadNet's media path serves webp images with
  server-side conversion (Pillow, cache, quality settings). Cost/benefit is
  bad for now: adds a heavy dependency and a whole conversion pipeline.
  Document in README that images are best shared as files (`/file/`) and that
  MeshDeck does not render inline images. If it ever ships, it is its own
  spec.
- **Executable pages.** NomadNet runs executable `.mu` files server-side.
  MeshDeck deliberately does not (security); keep the note in the guide.
- **Node-to-node peering/mirroring of pages.** Out of scope.

---

## 3. Phase 5 — release readiness

Goal: a stranger can install it, trust it, and a maintainer can ship updates
with one tag.

### P5.1 — CI on GitHub Actions  ★ do first (cheap, catches regressions)  ✅ DONE

> **Landed (2026-10-18):** `.github/workflows/ci.yml` with `backend`
> (3.12/3.13/3.14 matrix: install → ruff → unit tests), `frontend`
> (pnpm install --frozen-lockfile → check → test → build), and a
> `continue-on-error` `integration` job (20 min). README badge added.
> `pnpm run test` is wired now and exercised by the P4.5 vitest work.

**Tasks**
1. `.github/workflows/ci.yml`:
   - job `backend`: matrix `python-version: ["3.12", "3.13", "3.14"]`,
     ubuntu-latest; steps: checkout → setup-python → `pip install -e ".[dev]"`
     → `ruff check meshdeck tests` → `pytest tests/unit -q`.
   - job `frontend`: pnpm/action-setup + actions/setup-node (cache pnpm) →
     `pnpm install --frozen-lockfile` → `pnpm run check` → `pnpm run test`
     → `pnpm run build`.
   - job `integration` (non-blocking): `pytest tests/api tests/integration -m
     integration -q` with `timeout-minutes: 20`; allow failure.
2. Cache pip + pnpm.
3. If Python 3.14 is unavailable in `setup-python` on the runner, drop it from
   the matrix (keep 3.12/3.13), and note it in a comment — do not let CI be red
   for a missing interpreter.

**Acceptance:** a red test locally turns CI red; the badge link works in the
README. Verify by pushing a throwaway commit that breaks a test, then reverting
(do this on a branch, not main, to keep history clean).

### P5.2 — Release artifacts (tarball now, AppImage if tooling allows)  ✅ DONE (Flatpak unverified)

> **Landed (2026-10-18):** `packaging/meshdeck.svg` (256×256 node grid),
> `meshdeck.desktop`, `release.sh` (frontend → `make package` → tarball with
> binary/desktop/icon/README/LICENSE + SHA256SUMS + extracted `--version`
> self-check), `appimage.sh` (AppDir + appimagetool, downloads the official
> continuous build if absent, fails cleanly otherwise), and the Flatpak
> manifest. `packaging/README.md` records verified vs unverified.
> Independently verified in this session: `sha256sum -c` passes for both
> artifacts; tarball lists exactly the five files; extracted binary and the
> AppImage both print `meshdeck 0.1.0.dev0`. Flatpak is **UNVERIFIED**:
> `flatpak-builder` is not installed, so the manifest (and its
> `org.freedesktop.Platform//24.08` runtime claim) has never been built.
> Artifacts will be rebuilt at 0.1.0 for P5.6.

**Tasks**
1. Icon + desktop file: `packaging/meshdeck.svg` (simple, MIT-clean glyph —
   nodes linked in a deck/grid), `packaging/meshdeck.desktop`
   (`Exec=meshdeck`, `Terminal=false`, categories `Network;Chat;`).
2. `packaging/release.sh`: builds frontend → `make package` → assembles
   `dist/meshdeck-<version>-x86_64.tar.gz` containing the binary, desktop file,
   icon, README, LICENSE → writes `SHA256SUMS`.
3. AppImage (optional, gated): `packaging/appimage.sh` builds an AppDir
   (`usr/bin/meshdeck`, icon, desktop, `AppRun` that execs the binary) and runs
   `appimagetool` if available (`curl` the continuous build release if not
   installed). If `appimagetool` cannot be obtained, **stop and document** —
   do not hand-roll a fake AppImage.
4. Flatpak (stretch, gated on `flatpak-builder`): manifest
   `packaging/flatpak/org.meshdeck.MeshDeck.yml` with
   `finish-args: ["--share=network", "--socket=wayland", "--socket=fallback-x11",
   "--device=dri"]`, building from the PyPI-less source tree with
   `pip install --prefix=/app`. Verification requires `flatpak-builder
   --user --install --force-clean`; if the tool is absent, ship the manifest
   + a documented verification recipe and **say it is unverified**.

**Acceptance:** extracted tarball runs standalone on a clean path
(`./meshdeck --version` → version, UI serves). Release notes list install
methods that are actually verified.

### P5.3 — i18n scaffolding (English-only extraction)  ✅ DONE

> **Landed (2026-10-18):** `lib/i18n/index.ts` (`t`, `tList`, `$locale`,
> `setLocale`, per-key fallback, `{name}` interpolation, no dependency);
> `en.ts` holds every user-facing string (common, chats, pages, settings,
> guides, onboarding, tooltips, glossary, interfaces); `tooltips.ts` is now a
> thin re-export; `de.ts` is a deliberate 3-key fake locale proving fallback
> in 11 vitest cases (37 frontend tests total). All 11 components + App +
> `format.ts` (timeAgo) + `interfaces.ts` (kind labels/imported names) use
> `t()`. `docs/i18n.md` documents keys, plurals, fallback and the no-inline-
> strings rule.
> **Verified:** `pnpm run check` 0/0, `pnpm run test` 37 passed, build green;
> browser smoke on a real daemon rendered “Pages & Node”/“Settings” with zero
> raw i18n keys visible. **Known limitation:** `t()` reads `get(locale)`, so a
> runtime locale switch needs a reload (no picker exists yet; documented).
> Backend error codes (e.g. `no_path`) remain machine codes, not translated.

**Why now:** retrofitting translation later is expensive; extraction now is
mechanical.

**Tasks**
1. `frontend/src/lib/i18n/index.ts`: `t(key: string, vars?: Record<string,
   string|number>): string` with `{name}` interpolation, `$locale` store,
   `setLocale()` that falls back to `en`. No third-party dependency.
2. `frontend/src/lib/i18n/en.ts`: move **all** user-facing strings from
   components + `lib/copy/tooltips.ts` into it (nested objects, `common.*`,
   `chats.*`, `pages.*`, `settings.*`, `guides.*`, `tooltips.*`). Keep
   `TOOLTIPS` as a thin re-export so imports don't churn.
3. Migrate components one at a time, running `pnpm run check` after each.
4. `docs/i18n.md`: how to add a locale, key naming rules, pluralisation note
   (use explicit keys, not naive `s`), and the rule that **no user-facing
   string may be inlined** (enforce with a review checklist entry, not a
   linter).

**Acceptance:** UI is pixel-identical; `grep -rE '"[A-Z][a-z]+ [a-z]' src/components`
finds (almost) nothing user-facing; adding a fake `de.ts` with 3 keys proves
fallback works.

### P5.4 — Accessibility pass  ✅ DONE (browser/screen-reader walkthrough unverified)

> **Landed (2026-10-18):** real tablist/tabpanel nav with roving tabindex and
> arrow/Home/End keys; add-peer form as a focus-trapped dialog (autofocus,
> Escape closes and restores the ＋ trigger) plus a keyboard-navigable ⋯ menu;
> Onboarding as an `aria-modal` dialog with label association and focus trap;
> aria-labels for icon-only ＋/⋯/📎 and the Pages/Settings delete/copy
> buttons; always-mounted polite live regions for peer/chat/onboarding/
> page/settings statuses; global `:focus-visible` ring;
> `prefers-reduced-motion` disables transitions and smooth autoscroll.
> Contrast measured: `wp-dim` #8ca3b2 on `wp-bg` #0b0f14 = 7.32:1, on
> `wp-panel` #11181f = 6.81:1 (both pass AA; token unchanged).
> `pnpm run check` 0/0, build green. Checklist: `docs/a11y-checklist.md`.
> **Unverified:** no screen reader or manual keyboard-only end-to-end run was
> possible in this environment; the checklist marks those items as not
> exercised rather than pretending they passed.

**Tasks**
1. Modals (`PeerList` add-peer, rename; any `confirm()` replacements): focus
   the first field on open, trap Tab, `Escape` closes, restore focus on close.
2. Icon-only buttons (✕, ⋯, 📎, ＋, copy): `aria-label`, and `title` where it
   helps.
3. Nav tabs: `role="tablist"`/`aria-selected`, or at minimum `aria-current`.
4. Live regions (`aria-live="polite"`) for "saved ✓", "announced ✓",
   transfer progress text.
5. Contrast: check `wp-dim` on `wp-panel`/`wp-bg` ≥ 4.5:1 (adjust the token if
   not); `prefers-reduced-motion` disables transitions.
6. Keyboard-only pass through: onboarding → add peer → chat → attach →
   pages → save → settings → restart note.

**Acceptance:** a written checklist in the PR description with each item
ticked by actually doing it; `pnpm run check` still 0 warnings.

### P5.5 — Docs & first impressions  ✅ DONE (fresh-clone ten-minute test not run)

> **Landed (2026-10-18):** README rewritten (hero, honest pre-release status,
> basic/advanced feature table, quick start, packaged-binary note,
> architecture summary, security/privacy, "what it is not"); `CONTRIBUTING.md`,
> `SECURITY.md` (private advisories verified enabled), and
> `docs/architecture.md` (threading, EventBus, startup, `os.execv` restart,
> migrations, where to add a feature). Four real screenshots captured from two
> throwaway daemons with Playwright/Chromium at 1440×900 and embedded in the
> README; capture/privacy rules in `docs/screenshots/README.md`.
> Every documented command was checked against the Makefile/CLI; the
> `meshdeck --version`/`--help` flags, caps and auth claims were verified
> against the code. **Not verified:** a real stranger going from a fresh clone
> to chatting in under ten minutes (no second human/timing run), and
> screen-reader behaviour (see P5.4).

**Tasks**
1. README: hero paragraph, 3–4 screenshots (`docs/screenshots/`), feature
   table (basic vs advanced), quick start (`make install && make dev`, and
   "or download the binary"), architecture summary linking BUILD_PLAN §5,
   security/privacy statement, "what it is not" (no cloud, no accounts).
2. `CONTRIBUTING.md`: setup, test commands, commit style, where to add a
   guide/tooltip, "no protocol reimplementation" rule.
3. `SECURITY.md`: private disclosure address/process, supported versions.
4. `docs/architecture.md`: condense BUILD_PLAN §5 (process/threading model,
   EventBus bridge, restart supervisor) — the single most useful doc for a new
   contributor.
5. Screenshot capture: if Playwright/Chromium is available, script it
   (`pnpm add -D @playwright/test` is heavy — prefer a one-off
   `npx playwright screenshot` run and commit PNGs); otherwise ask the human
   for captures and leave `docs/screenshots/README.md` listing what's needed.

**Acceptance:** a person who has never seen the repo can go from clone to
chatting with a second instance using only the README.

### P5.6 — Versioning & the v0.1.0 tag  ✅ DONE

> **Landed (2026-10-18):** `meshdeck/version.py` + `pyproject.toml` = `0.1.0`;
> CHANGELOG Unreleased → `[0.1.0] - 2026-10-18`; README/SECURITY updated.
> Rebuilt artifacts from the tagged tree and verified:
> `meshdeck-0.1.0-x86_64.tar.gz` and `meshdeck-0.1.0-x86_64.AppImage`, both
> `sha256sum -c` clean and both print `meshdeck 0.1.0`. Annotated tag `v0.1.0`
> pushed; GitHub release created with tarball + AppImage + `SHA256SUMS`.
> Re-downloaded the release assets, checked checksums, ran both binaries, and
> served the extracted binary standalone (UI 200, authenticated API 200,
> `version: 0.1.0`, RNS running).

**Tasks**
1. `pyproject.toml` version `0.1.0.dev0` → `0.1.0`; `meshdeck/__init__.py`
   `__version__` consistency (single source: read from `__init__`).
2. `CHANGELOG.md`: move Unreleased content under `## [0.1.0] - YYYY-MM-DD`,
   keep the honest "Fixed (pre-release)" entries.
3. `git tag -a v0.1.0 -m …`; `gh release create v0.1.0 dist/*.tar.gz
   dist/SHA256SUMS --title … --notes-file` (notes generated from CHANGELOG).
4. Verify `./dist/meshdeck --version` → `0.1.0` and that the release page
   downloads work.
5. Update README badge/binary link to the release.

**Acceptance:** `gh release view v0.1.0` shows assets; binary from the release
runs and chats.

---

## 4. Working agreements (how the last sessions succeeded — keep doing this)

1. **Verify, don't narrate.** Every "done" needs a command output: test count,
   build size, curl/WS evidence, or a screenshot. If something is unverified
   (e.g. Flatpak without `flatpak-builder`), say so explicitly.
2. **One commit per task**, message = what + why, with the phase tag
   (`feat: Phase 4.1 — transfer progress`). Push to `origin main` right after.
3. **Tick the plan.** Update `BUILD_PLAN.md` §15 and this file when a task
   lands; keep `CHANGELOG.md` current — the human reads those, not the diffs.
4. **Bug found while testing → fix + regression test in the same commit**, and
   add the mechanism to BUILD_PLAN §14 pitfall list.
5. **Never trust a subagent's or a previous session's claim** without running
   the verification command yourself.
6. **Keep integration tests hermetic**: random free ports, temp dirs, no
   reliance on the host network beyond loopback.
7. **Threading rules are load-bearing**: RNS/LXMF callbacks are on RNS threads;
   only the EventBus bridges to asyncio. `link.request(progress_callback=…)`
   is such a callback.
8. **Don't gold-plate.** Phase 4.6 lists the traps; if a task balloons past its
   acceptance criteria, stop, ship the smaller thing, and write down the rest.

---

## 5. Suggested order & sizing

| # | Task | Size | Depends on |
|---|---|---|---|
| 1 | P5.1 CI | S | — |
| 2 | P4.5 micron TS tests | S | — |
| 3 | P4.4 reader links/back (bug) | S | P4.5 |
| 4 | P4.1 transfer progress | M | — |
| 5 | P4.2 page cache (DB v3) | M | — |
| 6 | P4.3 propagation hosting | M/L | — |
| 7 | P5.4 a11y | M | P5.3? (no) |
| 8 | P5.3 i18n extraction | M | after P5.4 string churn |
| 9 | P5.5 docs + screenshots | M | after UI stabilises |
| 10 | P5.2 release artifacts | M | 9 |
| 11 | P5.6 v0.1.0 tag | S | 10 |

Do CI and the micron tests first: they make every later step safer. i18n comes
after the a11y changes so strings don't churn twice.

---

## 6. Definition of done for the whole thing

- [x] `make test`, `ruff`, `pnpm run check`, `pnpm run test`, `pnpm run build`
      all green; CI badge green on `main` (backend 3.12/3.13/3.14, frontend,
      integration job non-blocking). Final release commit + docs run: see the
      CI run on `6e26e4e`/the docs follow-up.
- [x] Two fresh installs discover each other and chat, send files, host +
      browse pages, host + download node files. Verified with real two-node
      integration tests (11 passed, 73.8 s) **and** per-flow browser E2E:
      peer list/chat+attachment, 8 MiB progress bar + SHA match, page reader
      with links/back, cached/stale copy. Not one uninterrupted manual
      walkthrough of every flow in a single session.
- [ ] A stranger follows the README, installs, and chats in under ten minutes —
      **not verified** (no second person / timed fresh-clone run).
- [x] `v0.1.0` released with binaries that run standalone and a changelog that
      matches reality (downloaded from GitHub, checksums + `--version` + UI/API
      re-verified).
- [ ] No user-facing string outside `lib/i18n/en.ts` (frontend done; backend
      error *codes* remain machine strings); a11y checklist **not complete**:
      keyboard-only and screen-reader walkthroughs were never run. See
      `docs/a11y-checklist.md`.

### Known gaps after v0.1.0 (honest list)

- Flatpak manifest is unbuilt/unverified (`flatpak-builder` absent).
- Screen-reader and keyboard-only end-to-end walkthroughs were not performed.
- Fresh-clone ten-minute onboarding was not timed with a real stranger.
- Release binaries are Linux x86_64 built against this host's glibc; no
  Windows/macOS builds.
- Runtime locale switching needs a reload; only English ships.

---

## 7. Phase 6 — post-v0.1.0 hardening (done 2026-10-19)

Three parallel sessions, merged via PRs (see `docs/handoffs/`). All verification
commands were rerun after merge.

### P6.1 — HTTP route contract tests  ✅
`tests/api/test_routes.py` boots two real CLI daemons and exercises the routes
the UI calls: browse page/file, shared files, attachments, auth, node
discovery, settings validation. Reproduces the v0.1.0 bug class by asserting
the exact `path` value and the file-route ordering.

### P6.2 — Boot-from-settings matrix  ✅
`tests/integration/test_boot_settings.py` proves six persisted settings are
actually applied at boot (propagation store exists on disk, node announce,
delivery/propagation node, RNS transport flag, structured interface, mode).
No product bugs found; the harness now supports `--set KEY=JSON` and an
optional API server.

### P6.3 — Bounded disk usage  ✅
Page cache: hard 64 MiB total ceiling (configurable 0…1 GiB, oldest-first
eviction per write). Propagation store: 256 MB default cap via LXMF's own API
(0…10240 MB, 0 = unlimited), enforced by LXMF's periodic clean job. Usage is
in `/status` and Settings, with Clear cache. Limits reject invalid input with
400.

### Remaining follow-ups
- ✅ **Phase 7.1 (2026-10-19):** the other unbounded stores are now capped —
  chat attachments (byte cap + optional age retention, blobs only), shared
  files and hosted pages (refuse new writes above a cap; never auto-delete),
  SQLite message history (optional age retention), and logs (startup rotation
  with one `.1` backup). See `CHANGELOG.md` and `docs/handoffs/storage-bounds.md`.
- ✅ `page_cache_max_bytes` is exposed in Settings → Advanced → Storage.
- LXMF store-cap enforcement is periodic; optionally surface "will shrink
  within ~2 min" in the UI.
- Flatpak build; screen-reader/keyboard-only walkthrough; timed fresh-clone
  onboarding.
