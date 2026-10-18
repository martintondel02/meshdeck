# Phase 6.2 handoff — boot-from-settings matrix

Status: **complete** (2026-10-18). Branch `work/boot-matrix`.

## Why this exists

v0.1.0 shipped a real startup bug: if `host_propagation_node` was already
`true` in settings, `set_propagation_hosting(True)` early-returned because its
in-memory flag matched, so `LXMRouter.enable_propagation()` never ran — no
message store, no handlers, no announce — while `/status` still reported
hosting. It was fixed in `dfc1424`, but nothing tested the general class:

> a persisted setting is actually applied when the daemon boots.

`/status` is not enough to answer that question for several settings because it
echoes the settings store (`transport_enabled`, `mode`) or an internal flag
(`propagation_hosting`). These tests therefore check *external truth* wherever
one exists.

## Harness changes (`tests/integration/node.py`)

All existing flags and ready.json fields still work; these are additive.

| Change | Meaning |
|---|---|
| `--set KEY=JSON` (repeatable **or** comma-separated) | Seeds `SettingsStore` in `<data>/meshdeck.db` **before** `CoreService.start()`. JSON values may contain commas (strings, `interfaces` lists) — the splitter only breaks on top-level commas. Unknown keys and non-JSON values exit with a clear error instead of silently doing nothing. Legacy flags still work; `--set` wins if both name the same key. |
| `--api-port N` | Optionally starts the real loopback `ApiServer` (auth token minted at `<data>/token`); `0` = ephemeral. Port and token are written to ready.json so a test can assert against the actual `/api/v1/...` endpoints. |
| richer `ready.json` | Adds `mode`, `transport_enabled`, **`rns_transport_enabled`** (runtime truth from `RNS.Reticulum.transport_enabled()`), `interfaces`, `serve_pages`, `node_name`, `node_hash`, `delivery_method`, `propagation_node_setting`, **`outbound_propagation_node`** (runtime truth from `LXMRouter.get_outbound_propagation_node()`), and `api_port`/`api_token` when the API is on. Existing keys unchanged. |
| clean shutdown helper | Stops the optional API server before `CoreService.stop()` on every exit path (ready/timeout/done/restart). |

## Matrix (`tests/integration/test_boot_settings.py`)

All tests seed via `--set`, use temp data dirs, random loopback ports, disable
AutoInterface, and boot real subprocesses (RNS state is process-global).

| # | Test | Seeded at boot | Assertion of applied effect |
|---|---|---|---|
| 1 | `test_host_propagation_node_true_at_boot_starts_message_store` | `host_propagation_node=true` | status says hosting **and** `<data>/lxmf/lxmf/messagestore` exists; propagation address is 32-hex |
| 2 | `test_serve_pages_and_node_name_at_boot_announce_node` | `serve_pages=true`, `node_name="Boot Page Node"` | real `/api/v1/node` reports both; a watcher node receives the `nomadnetwork.node` announce with that hash and name |
| 3 | `test_delivery_method_and_propagation_node_apply_at_boot` | `delivery_method="propagated"`, `propagation_node_hash=<hex>` | settings reflect it; `LXMRouter.get_outbound_propagation_node()` returns the configured peer (no PUT/restart) |
| 4 | `test_transport_enabled_true_at_boot_enables_rns_transport` | `transport_enabled=true` | `RNS.Reticulum.transport_enabled()` is true, and the generated config says `enable_transport = Yes` |
| 5 | `test_structured_interface_online_at_boot` | structured `interfaces=[{kind:tcp_server,...}]` | `status.interfaces` contains an **online** `TCPServerInterface` |
| 6 | `test_advanced_mode_persists_across_boot` | `mode="advanced"` | applied on the seeded boot **and** on a second boot with no `--set` (read back from SQLite) |

Verified command (`.venv/bin/python -m pytest
tests/integration/test_boot_settings.py -m integration -q`): **6 passed in
7.12 s**; slowest case 5.37 s (the two-node announce case), the rest ≤ 0.61 s.

Harness-intact check: `tests/integration/test_pages.py` +
`tests/integration/test_propagation.py` → **6 passed in 51.09 s**;
`test_two_nodes.py` + `test_restart.py` + `tests/api` → **5 passed in 22.77 s**;
`tests/unit` → **48 passed**; `ruff check meshdeck tests` → clean.

## Product bugs found

**None.** No xfail was needed; all six tests are active. The current code
applies every seeded setting correctly at boot.

Sensitivity evidence (so the tests are not vacuous): with
`host_propagation_node=false` the same boot creates no `messagestore`
directory, and `serve_pages=false` produces no node announce for a watcher —
i.e. the positive assertions can only pass when the setting is applied.

## Notes / limitations (honest)

- **Message-store path is deeper than the docs' shorthand.** LXMF 1.2.1
  appends `/lxmf` to the `storagepath` that `ChatRouter` passes
  (`<data>/lxmf`), so the real store is `<data>/lxmf/lxmf/messagestore`, not
  `<data>/lxmf/messagestore`. The test asserts the real path (and documents
  why). This is a path-layout observation, not a functional bug: the store is
  created and used correctly.
- `/status` still has self-reported fields (`transport_enabled` reads the
  settings value; `propagation_hosting` reads the router wrapper's flag).
  The tests deliberately do not rely on them alone: test 4 checks RNS's own
  flag and test 1 checks the on-disk store.
- Test 2 proves announcement via a second node. Because the host boots before
  the watcher connects, the announce that reaches the watcher is normally the
  5-second periodic one (`node.py`'s announce loop), which only exists when
  `serve_pages` is true; the boot-time announce is exercised by
  `CoreService.start()` itself.
- The optional `--api-port` uses the real API/auth path but does not replace
  `tests/api/test_api.py`, which remains the broad REST/WS contract test.

## CHANGELOG-ready entry

```markdown
### Tests
- Phase 6.2 — added a boot-from-settings integration matrix
  (`tests/integration/test_boot_settings.py`): propagation hosting (message
  store actually created), page hosting + node announce, propagated delivery +
  propagation node, RNS transport enablement, structured interfaces online, and
  advanced-mode persistence across a real process restart. The integration
  harness gained a generic `--set KEY=JSON` pre-boot settings seeder, an
  optional loopback API (`--api-port`) for endpoint-level assertions, and
  richer `ready.json` fields including runtime truth (`rns_transport_enabled`,
  `outbound_propagation_node`). No product bugs found; no product code changed.
```
