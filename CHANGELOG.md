# Changelog

All notable changes to Waypoint. Format based on Keep a Changelog.

## [Unreleased]

### Added

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
