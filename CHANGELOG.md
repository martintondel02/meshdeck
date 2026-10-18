# Changelog

All notable changes to Waypoint. Format based on Keep a Changelog.

## [Unreleased]

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

- Backend daemon (`waypoint` package): managed Reticulum instance with
  own configdir, identity management, LXMF chat router, peer discovery via
  `lxmf.delivery` announces, SQLite persistence, loopback REST + WebSocket API
  with token auth, CLI (`python -m waypoint`).
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
