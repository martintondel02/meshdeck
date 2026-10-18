# Changelog

All notable changes to MeshDeck. Format based on Keep a Changelog.

## [Unreleased]

### Added (Phase 7.1 — bounded remaining stores)

- **Chat attachments are bounded and retainable.** Inbound attachment blobs
  (under `files/<peer>/<msg>/`) now have a global ceiling
  `attachment_storage_max_mb` (default **512 MiB**, `0` = unlimited; oldest
  blobs evicted first) and an optional age policy
  `attachment_retention_days` (default `0` = keep forever). Pruning runs at
  boot, after every inbound attachment, and when the settings are saved. It
  removes only blobs — message rows keep their metadata, the download route
  answers `404 attachment_pruned`, and the chat chip becomes a non-clickable
  "attachment no longer stored" tombstone.
- **Node-shared files and hosted pages are capped without auto-deletion.**
  `shared_storage_max_mb` (default **1024 MiB**) and
  `pages_storage_max_mb` (default **256 MiB**) bound new writes. Existing
  oversized stores are left alone; once a write would exceed the cap the
  store refuses it and the API returns `400 shared_storage_full` /
  `400 pages_storage_full`.
- **Message history retention.** `message_retention_days` (default `0` =
  keep forever) prunes messages at boot and once a day; peers and discovered
  nodes are never removed. No automatic VACUUM (documented: the file is not
  compacted immediately).
- **Log rotation.** `log_max_mb` (default **10 MiB**, `0` = unlimited)
  rotates `logs/meshdeck.log` and the generated `logs/reticulum.log` at
  startup, before Reticulum starts, keeping one `.1` backup. Only MeshDeck's
  own data directory is touched.
- `GET /api/v1/status` now reports usage and limits for attachments, shared
  files, hosted pages, message history and logs; `GET /settings` returns
  every new key. Settings → Advanced → **Storage** shows used / limit for each
  store, adds the previously API-only `page_cache_max_bytes` field, and
  requires an explicit save before any retention pruning runs.
- Fixed a latent body-size bug found while testing: aiohttp's default 1 MiB
  request limit rejected legitimate 4 MiB pages and shared files below their
  documented caps with `413`. The API now accepts the documented maximum
  payload and lets the store layers enforce the real limits.
- Tests: 62 new backend unit tests (142 total), a real-HTTP Phase 7.1
  acceptance test, and a real-daemon probe (log rotation + `/status` usage
  changing after writes).

### Added (Phase 7.2 — Fedora RPM)

- `packaging/meshdeck.spec` (RPM) and `packaging/rpm.sh`: build the frontend +
  one-file binary, stage a `meshdeck-<version>/` source tarball, run
  `rpmbuild -bb`, and write `dist/meshdeck-<version>-1.<arch>.rpm` plus a
  `SHA256SUMS` line. The architecture comes from `uname -m`; ELF `Requires`
  stay auto-generated; the package is unsigned and targets the build host's
  glibc. If `rpmbuild` is absent the script tries a user-level
  `dnf download rpm-build` + extraction route, and fails cleanly (no fake RPM)
  if that is impossible. The former PyInstaller spec is now
  `packaging/pyinstaller.spec`; `make package` follows the rename.
- Verified on this host (Fedora 44): the user-level route built
  `meshdeck-0.1.1-1.x86_64.rpm`, `rpm -qip`/`rpm -qlp` are correct, and the
  RPM extracted with `rpm2cpio | cpio` runs `usr/bin/meshdeck --version` →
  `meshdeck 0.1.1`. `packaging/README.md` and the top-level README document
  the install command and the unsigned/glibc caveats.

### Added / verified (Phase 7.3 — closing verification gaps)

- **Keyboard-only walkthrough performed** on two real daemons over a loopback
  TCP pair with a one-off Playwright/Chromium run (no project dependency):
  onboarding → add peer → open chat → send message → attach a file → Pages
  create/save → Settings → Advanced → restart note. 9/9 steps passed, 0 console
  errors; the second daemon received the text and the attachment blob, and the
  typed page persisted. `docs/a11y-checklist.md` §6 records tab counts and the
  one exception (the native file chooser payload cannot be typed headlessly).
- **Screen-reader attempt with Orca 50.3** (already installed): Orca attached
  to Chromium, activated its Chromium script 154 times, and its debug log shows
  generated speech-dispatcher utterances for MeshDeck content (“Ada”, the
  identity hash, “Help”, “PEERS Help”). **Not verified:** no human listener
  heard or validated the announcements; the checklist leaves that item unticked.
- **Flatpak verified** with org.flatpak.Builder 1.4.9 (user-level from
  Flathub) and freedesktop 26.08: build + install, `--version` →
  `meshdeck 0.1.1`, and the installed app served `GET /` + authenticated
  `GET /api/v1/status` (200, `rns_running: true`). Manifest fixes: enable
  network in the build sandbox (pip), move the EOL 24.08 runtime to 26.08.
  **Caveat:** AutoInterface does not start inside the Flatpak sandbox on this
  host (RNS exits 255), so network discovery under Flatpak is unverified.
- **Timed fresh-clone onboarding:** clone → `make install` →
  `make install-frontend` → `make dev` → second isolated instance → mutual add →
  text + file received in **9.3 s** end-to-end (warm caches; not a human
  stranger). The first attempt exposed a README bug: two local instances both
  default to AutoInterface, contend for the multicast socket, and the second
  never reaches `rns_running`. README now documents the loopback TCP-pair
  workaround.

## [0.1.1] - 2026-10-19

### Added (Phase 6 — post-release hardening)

- **HTTP route contract tests** (8, `tests/api/test_routes.py`): boot the real
  CLI and speak HTTP with its bearer token over a loopback two-node pair.
  Covers browse page paths (the `/page/page/…` bug class), browse file route
  ordering, shared files upload/list/download/delete, attachment downloads,
  auth on every route, `/node` vs `/nodes`, and settings validation.
- **Boot-from-settings matrix** (6, `tests/integration/test_boot_settings.py`):
  proves persisted settings are applied on boot, not just echoed by `/status` —
  propagation hosting creates LXMF's real message store, `serve_pages` +
  `node_name` announce, propagated delivery + node apply, `transport_enabled`
  reaches RNS, structured interfaces come up online, advanced mode persists.
  The harness gained `--set KEY=JSON`, an optional API server, and runtime-truth
  fields in `ready.json`.
- **Bounded, visible disk usage.** The page cache now has a hard total ceiling
  (`page_cache_max_bytes`, default 64 MiB, `0` = unlimited) enforced on every
  write by evicting the oldest pages; the LXMF propagation store is capped via
  LXMF's own API (`propagation_storage_limit_mb`, default 256 MB,
  `0` = unlimited). `GET /api/v1/status` reports cache entries/bytes, store
  bytes and both limits. Settings → Advanced shows store usage + limit and a
  new *Storage* card with page-cache usage and **Clear cache**
  (`DELETE /api/v1/page_cache`). Limits are strictly validated (400, never
  clamped).
- Tests grew to 80 backend unit, 25 API/integration, 37 frontend.

### Notes

- LXMF enforces the propagation store cap in its own periodic clean job
  (≈2 minutes), not instantly; the page cache bound is immediate.
- Chat attachments, node-shared files, hosted pages, message history and logs
  are still unbounded — a follow-up phase.
- Flatpak remains unverified, and no screen-reader/keyboard-only walkthrough
  has been run.

## [0.1.0] - 2026-10-18

### Added (Phase 4 — propagation hosting)

- Advanced → Settings → **Host for others**: turn your MeshDeck node into an
  LXMF propagation node (store-and-forward for offline peers) with a live
  toggle (no restart), the node's stable propagation address with copy button,
  and honest cost/privacy notes. `GET /api/v1/status` now exposes
  `propagation_hosting` and `propagation_node_hash`.
- `docs/guides/hosting-infrastructure.md` plus a built-in Guides section.
- End-to-end integration test: A hosts a propagation node, B sends a
  propagated message to offline C through A, C comes online, syncs and
  receives it (with sender/signature checks).

### Added (Phase 5 — i18n scaffolding)

- Every user-facing string now lives in `frontend/src/lib/i18n/en.ts` and is
  rendered through a tiny dependency-free `t()` with `{placeholder}`
  interpolation, explicit plural keys, and per-key fallback to English.
  `tooltips.ts` is a thin re-export; components, `timeAgo()` and interface
  labels are migrated. `docs/i18n.md` explains how to add a locale;
  a deliberate 3-key `de.ts` proves fallback in the test suite.

### Added (Phase 5 — docs & first impressions)

- Rewritten README with a basic/advanced feature table, quick start, honest
  pre-release status, security/privacy notes, "what it is not", and four real
  screenshots captured from two throwaway daemons.
- `CONTRIBUTING.md`, `SECURITY.md` (private advisories), and
  `docs/architecture.md` (threading/EventBus/restart/migrations).
- `docs/screenshots/README.md` records the capture recipe and privacy rules.

### Added (Phase 5 — accessibility)

- Keyboard and screen-reader pass: the top nav is a real tablist (arrow /
  Home / End), the add-peer form and Onboarding are focus-trapped dialogs
  (autofocus, Escape restores focus), the peer ⋯ menu is keyboard-navigable,
  icon-only buttons have labels, status messages are polite live regions, and
  reduced-motion preferences disable transitions/autoscroll. Contrast checked
  (wp-dim ≥ 6.8:1 on panels). Checklist in `docs/a11y-checklist.md`;
  screen-reader walkthrough remains unverified.

### Added (Phase 5 — release artifacts)

- `packaging/release.sh`: builds the UI + one-file binary and produces
  `meshdeck-<version>-x86_64.tar.gz` (binary, desktop file, icon, README,
  LICENSE) with `SHA256SUMS`, verifying the extracted binary's `--version`.
- `packaging/appimage.sh`: genuine AppImage build via appimagetool (downloads
  the official continuous build if needed; fails cleanly if unavailable).
- Icon (`meshdeck.svg`), desktop entry, and a Flatpak manifest.
- **Verified**: tarball and AppImage built, checksummed, extracted/run
  (`meshdeck 0.1.0.dev0`), UI + API served. **Unverified**: Flatpak —
  `flatpak-builder` is absent, so the manifest is untested (documented in
  `packaging/README.md`).

### Added (Phase 4 — page cache)

- Offline browsing: every successfully fetched page is cached (DB schema v3,
  max 4 MiB per page, 500 pages, 30-day prune). Fresh hits answer instantly;
  when a node is unreachable the reader shows a “saved copy — node
  unreachable” badge instead of an error, with a Refresh button that forces
  a live re-fetch (`?refresh=1`). Cached pages show a “cached · 2h ago”
  badge.
- Tests: cache repo unit tests, fresh/stale/refresh service tests, and a
  two-node integration test that kills the host and serves the saved copy.

### Added (Phase 4 — transfer progress)

- Progress for large node transfers: page and `/file/` fetches report
  throttled progress over the WebSocket, and the reader/file downloader shows
  a thin progress bar with a percentage. Completion events carry bytes,
  elapsed time and (for files) SHA-256. Opt-in via `?transfer_id=` on the
  browse routes, so existing clients are unchanged.
- Integration test: 8 MiB download over a real two-node RNS link with
  monotonic progress and correct SHA-256.

### Fixed (pre-release)

- Propagation hosting enabled at startup now actually calls
  `LXMRouter.enable_propagation()` (the idempotence guard skipped it when the
  setting was already true, so status claimed hosting while no message store
  or handlers existed).
- Syncing from a propagation node now identifies the link with *our* identity
  (the private-key one), not the propagation node's public identity — the
  previous call failed with `KeyError: Signing failed because identity does
  not hold a private key` and never fetched stored messages.
- Sending to a peer whose announce had not yet been stored (a real race seen
  while setting up two fresh nodes) no longer returns `500 FOREIGN KEY
  constraint failed` after LXMF has already sent the message: the outbound
  path now creates the peer row first (`_ensure_peer_row`, regression test).

### Fixed (Phase 4 — micron reader)

- **Browsing pages from the UI actually works now.** The REST browse route
  captured paths without a leading slash and the service prefixed `/page/`
  again, so every fetch requested `/page/page/…` and timed out after 25 s.
  Integration tests missed it because they call the service directly.
- Internal micron links render as real links again (they used to be
  HTML-escaped into visible text, so no reader link could work). The reader
  follows them in place and has a ← back stack for multi-page nodes.
- Micron: `` `[literal]` `` inline code spans, documented `` `!``/`_`/`*`
  formatting toggles, unknown backtick tokens are stripped instead of leaking,
  and pages over 512 KiB are refused with a notice. 26 renderer unit tests.

### Added (Phase 5 — release readiness)

- Continuous integration on GitHub Actions: backend lint + unit tests on
  Python 3.12/3.13/3.14, frontend type-check/test/build with dependency
  caching, and a non-blocking integration job running the real two-node RNS
  tests. CI badge in the README.
- Frontend unit tests with vitest (`pnpm run test`) covering the micron
  renderer, including XSS/escaping checks; wired into `make check` and CI.

### Added (Phase 4 — node file sharing)

- File hosting on your node: `/file/<name>` handlers using NomadNet's scheme
  (up to 32 MiB per file, auto-compressed, fetched on demand over an
  encrypted link — no chat message needed). Shared-files section in the Pages
  tab: upload, list, download, stop sharing, and download from any node by
  address + filename.
- REST: `GET/POST /api/v1/shared`, `GET/DELETE /api/v1/shared/{name}`,
  `GET /api/v1/browse/{hash}/file/{name}`.
- Tests: shared-name sanitization/traversal unit tests, API upload/download/
  delete acceptance checks, and an integration test downloading a 256 KiB
  file over a real two-node RNS link with SHA-256 equality.

### Fixed (pre-release)

- aiohttp matches routes in registration order: the specific
  `/browse/{hash}/file/{name}` route is now registered before the
  `/browse/{hash}/{path:.+}` catch-all, so file downloads aren't swallowed by
  the page handler.

### Added (Phase 4)

- **Page hosting (NomadNet-compatible)**: your node can serve micron `.mu`
  pages over encrypted RNS links (destination `nomadnetwork.node`, the same
  wire scheme as NomadNet) — a tiny website with no web server, no DNS, no
  IP sharing. Pages are live the moment they're saved.
- Pages tab in the UI: create/edit/delete pages with live micron preview,
  node name + announce toggle, discovered-nodes chips, and a built-in
  reader that renders pages fetched from other nodes (with fetch timing).
- Node announces carry the node name; discovered nodes are remembered
  (new `nodes` table, DB schema v2).
- Unit + integration coverage: page store validation/traversal, node repo,
  API CRUD + publish + browse-validation, page round-trip over a real
  two-node link, and node announce discovery.

### Fixed (pre-release)

- Request-handler generators must declare exactly the six parameters RNS's
  Link dispatcher expects; the test suite caught the mismatch
  (`Invalid signature for response generator callback`).

### Added (Phase 3)


- Interfaces wizard (advanced): structured `interfaces` settings rendered
  into the managed Reticulum config — TCP server/client, backbone
  server/client (gateway mode), LAN auto-discovery — add/remove/toggle,
  **Save & restart** (daemon re-execs itself; the UI reconnects
  automatically), invalid configs are rejected with details before any
  restart instead of crashing the process.
- Paste-snippet import: copy a `[interfaces]` block from
  directory.rns.recipes / rmap.world straight into the wizard.
- Hosting wizard: share-snippet generator for your server interfaces,
  public-listener warning, automatic announce-rate limits for 0.0.0.0
  interfaces, gateway-mode flag; transport-node toggle (advanced).
- Basic mode: gentle "reach beyond your LAN" pointers to community
  directories inside Settings → Network.
- Chat: stamp-cost badge on peers that require PoW (stamps are generated by
  LXMF's worker pool automatically; reply tickets included), plus history
  search with match counts.
- Packaging: `make package` produces a one-file binary (~23 MB) with the web
  UI embedded — verified boot, version, API and UI serve.

### Fixed (pre-release)

- Generated config: `extra_config_text` is now merged section-by-section
  (duplicate `[interfaces]` headers broke configobj parsing on restart).
- Placeholder lines in empty config sections are comments now (INI-safe).
- Wizard settings validation rejects unknown interface kinds (`400`).

### Added (Phase 2)

- File attachments in chat: 📎 send button, upload cap 1.5 MiB, inbound
  storage under `files/<peer>/<msg>/`, sanitized filenames, SHA-256 metadata,
  download route, attachment chips in bubbles.
- Contacts: add-by-hash (`POST /api/v1/peers`) with automatic path requests,
  rename and block via the peer options menu.
- Delivery control (advanced): default LXMF method
  (direct/opportunistic/propagated) + propagation node address, applied live;
  startup sync from the propagation node when configured.
- In-app Guides view (getting started, messaging, files, contacts, offline
  delivery, glossary) — works fully offline.
- Tests: API acceptance test (real HTTP+WS vs a booted daemon); integration
  round-trip reply test; 1 MiB file transfer integration test asserting
  SHA-256 equality. 26 unit tests total.
- Errors: `no_propagation_node` code; friendly "no path yet" guidance in UI.

### Fixed (pre-release)

- LXMF message hashes are 64-hex (SHA-256) — attachment validation now uses
  the correct length (was 32 → downloads 404'd).
- Attachment filename sanitization now URL-decodes first (clients may
  percent-encode separators, hiding path components).
- `ApiServer.start(port=0)` resolves the real ephemeral port from the socket.

### Added (Phase 1)

- Backend daemon (`meshdeck` package): managed Reticulum instance with
  own configdir, identity management, LXMF chat router, peer discovery via
  `lxmf.delivery` announces, SQLite persistence, loopback REST + WebSocket API
  with token auth, CLI (`python -m meshdeck`).
- Web UI (Vite + Svelte 5 + Tailwind 4): onboarding, peer list with unread
  badges, chat view with delivery states, settings with basic/advanced mode
  toggle, tooltips everywhere jargon appears.
- Integration harness: two real nodes over a localhost TCP pair exchanging an
  LXMF message (`tests/integration/`).
- Docs: master build plan (BUILD_PLAN.md), first in-app guide.

### Fixed (pre-release)

- Start RNS + LXMRouter on the main thread (both install signal handlers).
- Pre-pack `LXMessage` before `handle_outbound` so outbound hash is known.
- Validate generated interface config before RNS start (RNS hard-exits on
  bad interfaces); `listen_ip` vs `listen_on` pitfall documented.
